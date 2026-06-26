"""
链客宝 — 支付回调路由集成测试
===============================
涵盖: Mock 微信支付回调、支付宝回调
使用 FastAPI TestClient + 依赖注入 mock
"""

import json
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest
from fastapi.testclient import TestClient


# ===================================================================
# Mock 模型与 DB 工厂
# ===================================================================


class MockPaymentOrder:
    """模拟 PaymentOrder 模型"""
    def __init__(self, order_no="RC20240001", user_id="test_user", amount=100.0,
                 status="pending", channel_order_no=None, paid_at=None):
        self.order_no = order_no
        self.user_id = user_id
        self.amount = amount
        self.status = status
        self.channel_order_no = channel_order_no
        self.paid_at = paid_at


class MockUserBalance:
    """模拟 UserBalance 模型"""
    def __init__(self, user_id="test_user", balance=0.0, total_recharged=0.0,
                 total_consumed=0.0, frozen_amount=0.0, version=1):
        self.user_id = user_id
        self.balance = balance
        self.total_recharged = total_recharged
        self.total_consumed = total_consumed
        self.frozen_amount = frozen_amount
        self.version = version


class MockBalanceLog:
    """模拟 BalanceLog 模型"""
    def __init__(self, user_id="", amount=0.0, balance_before=0.0, balance_after=0.0,
                 direction="IN", biz_type="recharge", biz_id="", remark=""):
        self.user_id = user_id
        self.amount = amount
        self.balance_before = balance_before
        self.balance_after = balance_after
        self.direction = direction
        self.biz_type = biz_type
        self.biz_id = biz_id
        self.remark = remark


class MockDB:
    """模拟数据库会话"""
    def __init__(self):
        self.is_active = True
        self._orders = {}
        self._balances = {}
        self._logs = []
        self._committed = False
        self._rolled_back = False
        self._flushed = False

    def query(self, model):
        return MockQuery(self, model)

    def add(self, obj):
        if isinstance(obj, MockPaymentOrder):
            self._orders[obj.order_no] = obj
        elif isinstance(obj, MockUserBalance):
            self._balances[obj.user_id] = obj
        elif isinstance(obj, MockBalanceLog):
            self._logs.append(obj)

    def flush(self):
        self._flushed = True

    def commit(self):
        self._committed = True

    def rollback(self):
        self._rolled_back = True

    def close(self):
        self.is_active = False


class MockQuery:
    """模拟 SQLAlchemy Query"""
    def __init__(self, db, model):
        self._db = db
        self._model = model

    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        if self._model == MockPaymentOrder:
            for order in self._db._orders.values():
                return order
        elif self._model == MockUserBalance:
            for bal in self._db._balances.values():
                return bal
        return None

    def all(self):
        return []


def mock_get_db_session_factory():
    """返回 MockDB 会话的工厂"""
    db = MockDB()
    return db


@pytest.fixture(autouse=True)
def reset_mocks():
    """每个测试前清理 mock 状态"""
    yield


# ===================================================================
# 工具函数：为支付回调路由补全依赖
# ===================================================================


def patch_payment_dependencies():
    """
    为 payment_callback 路由 patch 所有外部依赖。
    包括 _get_db(), _get_payment_order_model() 等。
    """
    from app.routers import payment_callback as pc

    patches = [
        patch.object(pc, '_get_db', return_value=iter([MockDB()])),
        patch.object(pc, '_get_payment_order_model', return_value=MockPaymentOrder),
        patch.object(pc, '_get_user_balance_model', return_value=MockUserBalance),
        patch.object(pc, '_get_balance_log_model', return_value=MockBalanceLog),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


class TestPaymentCallbackMock:
    """Mock 支付回调端点测试 — 最易测试的入口"""

    MOCK_URL = "/api/payment/callback/wxpay/mock"

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前 patch 依赖"""
        from app.routers import payment_callback as pc

        self._patches = [
            patch.object(pc, '_get_db', return_value=iter([MockDB()])),
            patch.object(pc, '_get_payment_order_model', return_value=MockPaymentOrder),
            patch.object(pc, '_get_user_balance_model', return_value=MockUserBalance),
            patch.object(pc, '_get_balance_log_model', return_value=MockBalanceLog),
        ]
        for p in self._patches:
            p.start()
        yield
        for p in self._patches:
            p.stop()

    def test_mock_callback_success(self, client: TestClient):
        """Mock 支付回调处理成功"""
        resp = client.post(
            self.MOCK_URL,
            json={
                "out_trade_no": "RC20240001",
                "transaction_id": "mock_tx_001",
                "success_time": "2024-06-26T12:00:00Z",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SUCCESS"
        assert "message" in data

    def test_mock_callback_missing_order_no(self, client: TestClient):
        """缺少订单号返回 FAIL"""
        resp = client.post(
            self.MOCK_URL,
            json={"transaction_id": "mock_tx_002"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "FAIL"
        assert "缺少订单号" in data["message"]

    def test_mock_callback_empty_body(self, client: TestClient):
        """空请求体返回 FAIL"""
        resp = client.post(self.MOCK_URL, json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "FAIL"

    def test_mock_callback_with_full_fields(self, client: TestClient):
        """完整字段的 Mock 回调"""
        resp = client.post(
            self.MOCK_URL,
            json={
                "out_trade_no": "RC20240002",
                "transaction_id": "wx_mock_20240002",
                "success_time": "2024-06-26T10:30:00+08:00",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SUCCESS"


class TestWxPayCallbackRoute:
    """微信支付回调路由测试（依赖完全 mock）"""

    WXPAY_URL = "/api/payment/callback/wxpay"

    @pytest.fixture(autouse=True)
    def setup(self):
        """Mock wxpay_callback 内部所有外部依赖"""
        from app.routers import payment_callback as pc

        self._patches = [
            patch.object(pc, '_get_db', return_value=iter([MockDB()])),
            patch.object(pc, '_get_payment_order_model', return_value=MockPaymentOrder),
            patch.object(pc, '_get_user_balance_model', return_value=MockUserBalance),
            patch.object(pc, '_get_balance_log_model', return_value=MockBalanceLog),
        ]
        for p in self._patches:
            p.start()

        # Mock WxPayCallbackService
        self._wxpay_patch = patch(
            'app.routers.payment_callback.WxPayCallbackService',
        )
        mock_service_class = self._wxpay_patch.start()
        mock_instance = mock_service_class.return_value
        mock_instance.verify_and_process = AsyncMock(return_value={
            "code": "SUCCESS",
            "message": "成功",
        })

        # Mock build_on_payment_success
        mock_service_class.build_on_payment_success = AsyncMock(
            return_value=AsyncMock(return_value={"success": True, "message": "支付成功"})
        )

        yield

        for p in self._patches:
            p.stop()
        self._wxpay_patch.stop()

    def test_wxpay_callback_success(self, client: TestClient):
        """微信回调成功处理"""
        resp = client.post(
            self.WXPAY_URL,
            json={"resource": {"ciphertext": "mock", "nonce": "abc", "associated_data": "def"}},
            headers={
                "Wechatpay-Signature": "mock_signature",
                "Wechatpay-Serial": "mock_serial",
                "Wechatpay-Timestamp": "1234567890",
                "Wechatpay-Nonce": "mock_nonce",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SUCCESS"

    def test_wxpay_callback_without_headers(self, client: TestClient):
        """缺少微信签名头 — 路由层会调用 verify_and_process 但 mock 返回 SUCCESS"""
        resp = client.post(
            self.WXPAY_URL,
            json={"out_trade_no": "test"},
        )
        assert resp.status_code == 200


class TestAliPayCallbackRoute:
    """支付宝支付回调路由测试（依赖完全 mock）"""

    ALIPAY_URL = "/api/payment/callback/alipay"

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.routers import payment_callback as pc

        self._patches = [
            patch.object(pc, '_get_db', return_value=iter([MockDB()])),
            patch.object(pc, '_get_payment_order_model', return_value=MockPaymentOrder),
            patch.object(pc, '_get_user_balance_model', return_value=MockUserBalance),
            patch.object(pc, '_get_balance_log_model', return_value=MockBalanceLog),
        ]
        for p in self._patches:
            p.start()

        # Mock AliPayCallbackService
        self._alipay_patch = patch(
            'app.routers.payment_callback.AliPayCallbackService',
        )
        mock_service_class = self._alipay_patch.start()
        mock_instance = mock_service_class.return_value
        mock_instance.verify_and_process = AsyncMock(return_value={
            "code": "SUCCESS",
            "message": "成功",
            "data": {"out_trade_no": "RC20240001", "trade_no": "alipay_001", "trade_status": "TRADE_SUCCESS"},
        })

        # Mock build_on_payment_success
        mock_service_class.build_on_payment_success = AsyncMock(
            return_value=AsyncMock(return_value={"success": True, "message": "支付成功"})
        )

        yield

        for p in self._patches:
            p.stop()
        self._alipay_patch.stop()

    def test_alipay_callback_success(self, client: TestClient):
        """支付宝回调成功处理"""
        resp = client.post(
            self.ALIPAY_URL,
            data={
                "out_trade_no": "RC20240001",
                "trade_no": "alipay_001",
                "trade_status": "TRADE_SUCCESS",
                "total_amount": "100.00",
                "gmt_payment": "2024-06-26 12:00:00",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SUCCESS"

    def test_alipay_callback_trade_finished(self, client: TestClient):
        """支付宝 TRADE_FINISHED 状态的处理"""
        resp = client.post(
            self.ALIPAY_URL,
            data={
                "out_trade_no": "RC20240002",
                "trade_no": "alipay_002",
                "trade_status": "TRADE_FINISHED",
                "total_amount": "200.00",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SUCCESS"


# ===================================================================
# recharge_callback 核心逻辑单元测试
# ===================================================================


class TestProcessSuccessfulPayment:
    """process_successful_payment 核心逻辑测试"""

    def test_process_pending_order(self):
        """pending 状态的订单处理成功"""
        from app.features.payment_callback.recharge_callback import process_successful_payment

        db = MockDB()
        order = MockPaymentOrder(order_no="RC001", user_id="u1", amount=100.0, status="pending")
        db._orders["RC001"] = order

        result = process_successful_payment(
            db=db,
            order_no="RC001",
            transaction_id="tx_001",
            paid_at_str="2024-06-26T12:00:00Z",
            payment_order_model=MockPaymentOrder,
            user_balance_model=MockUserBalance,
            balance_log_model=MockBalanceLog,
        )
        assert result["success"] is True
        assert result["order_no"] == "RC001"
        assert order.status == "paid"

    def test_process_already_paid_order(self):
        """已支付订单幂等跳过"""
        from app.features.payment_callback.recharge_callback import process_successful_payment

        db = MockDB()
        order = MockPaymentOrder(order_no="RC002", user_id="u1", amount=100.0, status="paid")
        db._orders["RC002"] = order

        result = process_successful_payment(
            db=db,
            order_no="RC002",
            transaction_id="tx_002",
            payment_order_model=MockPaymentOrder,
            user_balance_model=None,
            balance_log_model=None,
        )
        assert result["success"] is True
        assert "幂等" in result["message"]

    def test_process_nonexistent_order(self):
        """不存在的订单返回失败"""
        from app.features.payment_callback.recharge_callback import process_successful_payment

        db = MockDB()

        result = process_successful_payment(
            db=db,
            order_no="NONEXIST",
            transaction_id="tx_003",
            payment_order_model=MockPaymentOrder,
            user_balance_model=None,
            balance_log_model=None,
        )
        assert result["success"] is False
        assert "不存在" in result["message"]

    def test_process_closed_order(self):
        """已关闭订单不允许支付"""
        from app.features.payment_callback.recharge_callback import process_successful_payment

        db = MockDB()
        order = MockPaymentOrder(order_no="RC003", user_id="u1", amount=100.0, status="closed")
        db._orders["RC003"] = order

        result = process_successful_payment(
            db=db,
            order_no="RC003",
            transaction_id="tx_004",
            payment_order_model=MockPaymentOrder,
            user_balance_model=None,
            balance_log_model=None,
        )
        assert result["success"] is False
        assert "不允许" in result["message"]
