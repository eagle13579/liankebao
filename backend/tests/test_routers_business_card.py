"""
链客宝 — 企业数字名片路由集成测试
=================================
涵盖: 名片 CRUD、AI 生成、分享令牌
使用 FastAPI TestClient + SQLite 内存数据库
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.models import BROCHURE_SYNC_STORE


class TestBusinessCardCRUD:
    """名片完整 CRUD 集成测试"""

    CARDS_URL = "/api/business-card/cards"
    USER_ID = "test_user_001"

    @pytest.fixture(autouse=True)
    def setup_db(self, app):
        """每个测试前创建独立内存数据库并覆盖依赖"""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = TestSession()

        # 清理同步存储
        BROCHURE_SYNC_STORE.clear()

        app.dependency_overrides[get_db] = lambda: db
        self._db = db

        # 获取 admin token 用于认证
        login_resp = TestClient(app).post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        self._token = login_resp.json()["token"]
        self._headers = {"Authorization": f"Bearer {self._token}"}

        yield

        db.close()
        app.dependency_overrides.clear()
        BROCHURE_SYNC_STORE.clear()

    def test_create_card(self, client: TestClient):
        """创建名片成功"""
        resp = client.post(
            self.CARDS_URL,
            headers=self._headers,
            json={
                "user_id": self.USER_ID,
                "fields": {
                    "name": "张三",
                    "company": "链客宝科技",
                    "position": "CTO",
                    "phone": "13900000001",
                    "email": "zhangsan@chainke.com",
                },
            },
        )
        assert resp.status_code == 200, f"创建名片失败: {resp.text}"
        data = resp.json()
        assert data["user_id"] == self.USER_ID
        assert data["fields"]["name"] == "张三"
        assert data["fields"]["company"] == "链客宝科技"
        assert "id" in data
        assert "share_token" in data
        assert data["share_token"] is not None

    def test_list_cards(self, client: TestClient):
        """获取名片列表"""
        client.post(
            self.CARDS_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "fields": {"name": "名片A"}},
        )
        client.post(
            self.CARDS_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "fields": {"name": "名片B"}},
        )

        resp = client.get(
            f"{self.CARDS_URL}?user_id={self.USER_ID}",
            headers=self._headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "cards" in data
        assert "total" in data
        assert data["total"] >= 2
        assert len(data["cards"]) >= 2

    def test_list_cards_pagination(self, client: TestClient):
        """名片列表分页正常"""
        for i in range(5):
            client.post(
                self.CARDS_URL,
                headers=self._headers,
                json={"user_id": self.USER_ID, "fields": {"name": f"名片{i}"}},
            )

        resp = client.get(
            f"{self.CARDS_URL}?skip=0&limit=2",
            headers=self._headers,
        )
        data = resp.json()
        assert len(data["cards"]) == 2
        assert data["skip"] == 0
        assert data["limit"] == 2

    def test_get_card_by_id(self, client: TestClient):
        """根据 ID 获取名片详情"""
        create_resp = client.post(
            self.CARDS_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "fields": {"name": "查询测试"}},
        )
        card_id = create_resp.json()["id"]

        resp = client.get(f"{self.CARDS_URL}/{card_id}", headers=self._headers)
        assert resp.status_code == 200
        assert resp.json()["fields"]["name"] == "查询测试"

    def test_get_card_not_found(self, client: TestClient):
        """不存在的名片返回 404"""
        resp = client.get(f"{self.CARDS_URL}/99999", headers=self._headers)
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_update_card(self, client: TestClient):
        """更新名片信息（合并而非覆盖）"""
        create_resp = client.post(
            self.CARDS_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "fields": {"name": "原名", "company": "原公司"}},
        )
        card_id = create_resp.json()["id"]

        resp = client.put(
            f"{self.CARDS_URL}/{card_id}",
            headers=self._headers,
            json={"fields": {"name": "新名", "position": "CEO"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fields"]["name"] == "新名"
        assert data["fields"]["position"] == "CEO"
        # company 应保留（合并而非覆盖）
        assert data["fields"]["company"] == "原公司"

    def test_update_card_not_found(self, client: TestClient):
        """更新不存在的名片返回 404"""
        resp = client.put(
            f"{self.CARDS_URL}/99999",
            headers=self._headers,
            json={"fields": {"name": "无"}},
        )
        assert resp.status_code == 404

    def test_delete_card(self, client: TestClient):
        """删除名片"""
        create_resp = client.post(
            self.CARDS_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "fields": {"name": "待删除"}},
        )
        card_id = create_resp.json()["id"]

        resp = client.delete(f"{self.CARDS_URL}/{card_id}", headers=self._headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "名片已删除"

        # 确认已删除
        get_resp = client.get(f"{self.CARDS_URL}/{card_id}", headers=self._headers)
        assert get_resp.status_code == 404

    def test_delete_card_not_found(self, client: TestClient):
        """删除不存在的名片返回 404"""
        resp = client.delete(f"{self.CARDS_URL}/99999", headers=self._headers)
        assert resp.status_code == 404


class TestBusinessCardGenerate:
    """AI 生成名片测试"""

    GENERATE_URL = "/api/business-card/generate-card"
    USER_ID = "gen_test_user"

    @pytest.fixture(autouse=True)
    def setup_db(self, app):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = TestSession()
        BROCHURE_SYNC_STORE.clear()

        app.dependency_overrides[get_db] = lambda: db

        login_resp = TestClient(app).post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        self._token = login_resp.json()["token"]
        self._headers = {"Authorization": f"Bearer {self._token}"}

        yield

        db.close()
        app.dependency_overrides.clear()
        BROCHURE_SYNC_STORE.clear()

    def test_generate_card_from_text(self, client: TestClient):
        """从原始文本 AI 生成名片"""
        raw_text = "姓名：李四\n公司：创新科技\n职位：产品经理\n手机：13600000000\n邮箱：lisi@example.com"
        resp = client.post(
            self.GENERATE_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "raw_text": raw_text},
        )
        assert resp.status_code == 200, f"生成名片失败: {resp.text}"
        data = resp.json()
        assert "card" in data
        assert data["card"]["user_id"] == self.USER_ID
        assert data["card"]["fields"]["name"] == "李四"
        assert data["card"]["fields"]["company"] == "创新科技"
        assert "ai_summary" in data
        assert "suggestions" in data

    def test_generate_card_syncs_to_brochure_store(self, client: TestClient):
        """生成名片后自动同步至 brochure 共享存储"""
        raw_text = "姓名：王五\n公司：数据科技"
        client.post(
            self.GENERATE_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "raw_text": raw_text},
        )

        # 验证同步存储中有数据
        assert self.USER_ID in BROCHURE_SYNC_STORE
        assert BROCHURE_SYNC_STORE[self.USER_ID]["fields"]["name"] == "王五"

    def test_generate_card_with_all_fields(self, client: TestClient):
        """生成名片含完整结构化字段"""
        raw_text = (
            "姓名：赵六\n公司：AI科技\n职位：算法工程师\n"
            "手机：13700000000\n邮箱：zhao@ai.com\n微信：zhao_ai\n"
            "网站：https://ai.tech\n地址：北京市朝阳区\n简介：专注AI十年\n标签：AI、大数据、云计算"
        )
        resp = client.post(
            self.GENERATE_URL,
            headers=self._headers,
            json={"user_id": self.USER_ID, "raw_text": raw_text, "template": "modern"},
        )
        assert resp.status_code == 200
        fields = resp.json()["card"]["fields"]
        assert fields["name"] == "赵六"
        assert fields["company"] == "AI科技"
        assert fields["position"] == "算法工程师"
        assert fields["phone"] == "13700000000"
        assert fields["email"] == "zhao@ai.com"
        assert fields["wechat"] == "zhao_ai"
        assert fields["website"] == "https://ai.tech"
        assert fields["address"] == "北京市朝阳区"
        assert fields["description"] == "专注AI十年"
        assert "AI" in fields["tags"]

    def test_generate_card_fallback_to_description(self, client: TestClient):
        """无结构化字段时，全文作为 description"""
        raw_text = "我是一名自由职业者，主要做UI设计和品牌策划，有十年经验。"
        resp = client.post(
            self.GENERATE_URL,
            headers=self._headers,
            json={"user_id": "freelancer", "raw_text": raw_text},
        )
        assert resp.status_code == 200
        fields = resp.json()["card"]["fields"]
        assert fields["description"] == raw_text


class TestBusinessCardShare:
    """名片分享令牌测试"""

    USER_ID = "share_test_user"

    @pytest.fixture(autouse=True)
    def setup_db(self, app):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = TestSession()

        app.dependency_overrides[get_db] = lambda: db

        login_resp = TestClient(app).post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        self._client = TestClient(app)

        # 创建名片获取 share_token
        create_resp = self._client.post(
            "/api/business-card/cards",
            headers=headers,
            json={"user_id": self.USER_ID, "fields": {"name": "分享测试"}},
        )
        self._share_token = create_resp.json()["share_token"]

        yield

        db.close()
        app.dependency_overrides.clear()

    def test_get_card_by_share_token(self):
        """通过 share_token 获取名片（公开接口，无需认证）"""
        resp = self._client.get(f"/api/business-card/share/{self._share_token}")
        assert resp.status_code == 200
        assert resp.json()["fields"]["name"] == "分享测试"
        assert resp.json()["user_id"] == self.USER_ID

    def test_get_card_by_invalid_token_returns_404(self):
        """无效的 share_token 返回 404"""
        resp = self._client.get("/api/business-card/share/invalid_token_xyz")
        assert resp.status_code == 404

    def test_card_created_with_share_token(self):
        """创建的名片自动生成唯一 share_token (16字符)"""
        resp = self._client.get(f"/api/business-card/share/{self._share_token}")
        assert resp.status_code == 200
        assert len(self._share_token) == 16
