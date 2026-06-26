"""
链客宝测试 - 全局配置与 Fixtures
=================================
提供 FastAPI TestClient、共享测试数据、以及模块状态重置。
"""

import copy
import os
import sys
from collections.abc import Generator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import pytest

# ---------------------------------------------------------------------------
# 将项目根目录加入 sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# 必须在任何 app 模块导入前设定测试环境变量
# ---------------------------------------------------------------------------
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("PAYMENT_MODE", "mock")
os.environ.setdefault("SEARCH_BACKEND", "memory")

# ---------------------------------------------------------------------------
# 创建测试用 SQLite 引擎
# ---------------------------------------------------------------------------
import tempfile
import uuid

_TEST_DB_NAME = f"chainke_test_{uuid.uuid4().hex[:8]}.db"
_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), _TEST_DB_NAME)
if os.path.exists(_TEST_DB_PATH):
    try:
        os.remove(_TEST_DB_PATH)
    except PermissionError:
        pass

TEST_ENGINE = create_engine(
    f"sqlite:///{_TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

# 导入 app 模块并替换数据库
import app.database as db_module
from app.database import Base

# 保存原始 get_db 引用
_original_get_db = db_module.get_db

# 替换全局对象
db_module.engine = TEST_ENGINE
db_module.SessionLocal = TestSessionLocal

# ---------------------------------------------------------------------------
# FastAPI App 构造器
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """构建包含所有路由模块的 FastAPI 应用"""
    app = FastAPI(title="链客宝 Test", version="0.0.0")

    # 导入并注册各个路由器
    from app.routers import hypothesis_gate
    from app.routers import unit_economics
    from app.routers import sales_script
    from app.routers import learning_center
    from app.routers import retention_insights
    from app.routers import retro_board

    modules = [
        ("hypothesis_gate", hypothesis_gate),
        ("unit_economics", unit_economics),
        ("sales_script", sales_script),
        ("learning_center", learning_center),
        ("retention_insights", retention_insights),
        ("retro_board", retro_board),
    ]

    for name, mod in modules:
        if mod.router is not None:
            app.include_router(mod.router)
        else:
            raise RuntimeError(f"{name}.router 为 None，模块未正确加载")

    # ── 业务模块路由器（所有模块都将 APIRouter 实例命名为 router） ──
    _try_include_router(app, "app.routers.auth", "router")
    _try_include_router(app, "app.routers.business_card", "router")
    _try_include_router(app, "app.routers.contacts", "router")
    _try_include_router(app, "app.routers.activities", "router")
    _try_include_router(app, "app.routers.products", "router")
    _try_include_router(app, "app.routers.orders", "router")
    _try_include_router(app, "app.routers.needs", "router")
    _try_include_router(app, "app.routers.promoter", "router")
    _try_include_router(app, "app.routers.recharge", "router")
    _try_include_router(app, "app.routers.wxpay", "wxpay_router")
    _try_include_router(app, "app.routers.matching_engine", "router")
    _try_include_router(app, "app.routers.trust_score", "router")
    _try_include_router(app, "app.routers.trust_engine_api", "router")
    _try_include_router(app, "app.routers.brochure_bridge", "router")

    # 健康检查端点
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "service": "链客宝AI API", "version": "1.0.0"}

    @app.get("/health")
    async def health_check_short():
        return {"status": "ok"}

    @app.get("/health/live")
    async def health_live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def health_ready():
        return {"status": "ok", "database": "ok", "payment": "mock", "system": "ok"}

    @app.get("/")
    async def root():
        return {"service": "链客宝AI API", "status": "running", "version": "1.0.0"}

    app.dependency_overrides[_original_get_db] = _override_get_db

    return app


def _try_include_router(app: FastAPI, module_path: str, router_attr: str):
    """安全地尝试导入并注册路由器"""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        router = getattr(mod, router_attr, None)
        if router is not None:
            app.include_router(router)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 全局 Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def app() -> FastAPI:
    """返回 FastAPI 应用实例（session 级，只构建一次）"""
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """每个测试用例独立的 TestClient"""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 辅助：deep-copy 快照保存与恢复（用于有状态模块）
# ---------------------------------------------------------------------------

Snapshot = dict[str, Any]


def _take_snapshot(targets: dict[str, list]) -> Snapshot:
    """保存模块内可变列表的深拷贝快照"""
    return {k: copy.deepcopy(v) for k, v in targets.items()}


def _restore_snapshot(snapshot: Snapshot, targets: dict[str, list]) -> None:
    """从快照恢复模块内可变列表"""
    for k, v in snapshot.items():
        if k in targets:
            targets[k].clear()
            targets[k].extend(v)


# ---------------------------------------------------------------------------
# 按模块的状态管理 Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_hypothesis_gate():
    """重置 hypothesis_gate 模块的内存数据与 ID 计数器"""
    import app.routers.hypothesis_gate as mod

    snap = _take_snapshot({
        "HYPOTHESES": mod.HYPOTHESES,
        "EXPERIMENTS": mod.EXPERIMENTS,
        "VALIDATION_RESULTS": mod.VALIDATION_RESULTS,
    })
    counters = {
        "_next_hypothesis_id": mod._next_hypothesis_id,
        "_next_experiment_id": mod._next_experiment_id,
        "_next_result_id": mod._next_result_id,
    }
    yield
    _restore_snapshot(snap, {
        "HYPOTHESES": mod.HYPOTHESES,
        "EXPERIMENTS": mod.EXPERIMENTS,
        "VALIDATION_RESULTS": mod.VALIDATION_RESULTS,
    })
    mod._next_hypothesis_id = counters["_next_hypothesis_id"]
    mod._next_experiment_id = counters["_next_experiment_id"]
    mod._next_result_id = counters["_next_result_id"]


@pytest.fixture
def reset_unit_economics():
    """重置 unit_economics 模块的内存数据与 ID 计数器"""
    import app.routers.unit_economics as mod

    snap = _take_snapshot({
        "COST_ENTRIES": mod.COST_ENTRIES,
        "REVENUE_ENTRIES": mod.REVENUE_ENTRIES,
        "SNAPSHOTS": mod.SNAPSHOTS,
        "CHANNEL_ECONOMICS": mod.CHANNEL_ECONOMICS,
    })
    counters = {
        "_next_cost_id": mod._next_cost_id,
        "_next_revenue_id": mod._next_revenue_id,
        "_next_snapshot_id": mod._next_snapshot_id,
    }
    yield
    _restore_snapshot(snap, {
        "COST_ENTRIES": mod.COST_ENTRIES,
        "REVENUE_ENTRIES": mod.REVENUE_ENTRIES,
        "SNAPSHOTS": mod.SNAPSHOTS,
        "CHANNEL_ECONOMICS": mod.CHANNEL_ECONOMICS,
    })
    mod._next_cost_id = counters["_next_cost_id"]
    mod._next_revenue_id = counters["_next_revenue_id"]
    mod._next_snapshot_id = counters["_next_snapshot_id"]


@pytest.fixture
def reset_sales_script():
    """重置 sales_script 模块的内存数据与 ID 计数器"""
    import app.routers.sales_script as mod

    snap = _take_snapshot({
        "ABACC_PRESETS": mod.ABACC_PRESETS,
    })
    counters = {"_next_id": mod._next_id}
    yield
    _restore_snapshot(snap, {"ABACC_PRESETS": mod.ABACC_PRESETS})
    mod._next_id = counters["_next_id"]


@pytest.fixture
def reset_learning_center():
    """重置 learning_center 模块的内存数据与 ID 计数器"""
    import app.routers.learning_center as mod

    snap = _take_snapshot({
        "COURSES": mod.COURSES,
        "MODULES": mod.MODULES,
        "LESSONS": mod.LESSONS,
        "PROGRESSES": mod.PROGRESSES,
        "AI_TUTOR_MESSAGES": mod.AI_TUTOR_MESSAGES,
        "CERTIFICATIONS": mod.CERTIFICATIONS,
    })
    counters = {
        "_next_course_id": mod._next_course_id,
        "_next_module_id": mod._next_module_id,
        "_next_lesson_id": mod._next_lesson_id,
        "_next_progress_id": mod._next_progress_id,
        "_next_tutor_id": mod._next_tutor_id,
        "_next_cert_id": mod._next_cert_id,
    }
    yield
    _restore_snapshot(snap, {
        "COURSES": mod.COURSES,
        "MODULES": mod.MODULES,
        "LESSONS": mod.LESSONS,
        "PROGRESSES": mod.PROGRESSES,
        "AI_TUTOR_MESSAGES": mod.AI_TUTOR_MESSAGES,
        "CERTIFICATIONS": mod.CERTIFICATIONS,
    })
    for k, v in counters.items():
        setattr(mod, k, v)


@pytest.fixture
def reset_retention_insights():
    """重置 retention_insights 模块的内存数据与 ID 计数器"""
    import app.routers.retention_insights as mod

    snap = _take_snapshot({
        "COHORTS": mod.COHORTS,
        "COHORT_RETENTION": mod.COHORT_RETENTION,
        "ACTIVITIES": mod.ACTIVITIES,
        "CHURN_SIGNALS": mod.CHURN_SIGNALS,
        "RETENTION_STRATEGIES": mod.RETENTION_STRATEGIES,
    })
    counters = {
        "_next_cohort_id": mod._next_cohort_id,
        "_next_retention_id": mod._next_retention_id,
        "_next_activity_id": mod._next_activity_id,
        "_next_churn_id": mod._next_churn_id,
        "_next_strategy_id": mod._next_strategy_id,
    }
    yield
    _restore_snapshot(snap, {
        "COHORTS": mod.COHORTS,
        "COHORT_RETENTION": mod.COHORT_RETENTION,
        "ACTIVITIES": mod.ACTIVITIES,
        "CHURN_SIGNALS": mod.CHURN_SIGNALS,
        "RETENTION_STRATEGIES": mod.RETENTION_STRATEGIES,
    })
    for k, v in counters.items():
        setattr(mod, k, v)


@pytest.fixture
def reset_retro_board():
    """重置 retro_board 模块的内存数据与 ID 计数器"""
    import app.routers.retro_board as mod

    snap = _take_snapshot({
        "BOARDS": mod.BOARDS,
        "RETRO_ITEMS": mod.RETRO_ITEMS,
        "ACTION_ITEMS": mod.ACTION_ITEMS,
    })
    counters = {
        "_next_board_id": mod._next_board_id,
        "_next_item_id": mod._next_item_id,
        "_next_action_id": mod._next_action_id,
    }
    yield
    _restore_snapshot(snap, {
        "BOARDS": mod.BOARDS,
        "RETRO_ITEMS": mod.RETRO_ITEMS,
        "ACTION_ITEMS": mod.ACTION_ITEMS,
    })
    for k, v in counters.items():
        setattr(mod, k, v)


# ---------------------------------------------------------------------------
# 数据库 Fixtures —— 兼容测试 (test_db fixture)
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db():
    """
    提供 SQLite 内存数据库会话，用于需要数据库支持的测试。

    每个测试函数独立获得一个全新数据库，
    自动创建所有表 (基于 app.database.Base 的子类)，
    测试结束后自动关闭会话并丢弃数据库。
    """
    engine_test = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(bind=engine_test)

    TestSessionLocal2 = sessionmaker(
        autocommit=False, autoflush=False, bind=engine_test
    )
    db = TestSessionLocal2()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine_test)


# ---------------------------------------------------------------------------
# 数据库 session fixture（使用测试引擎）
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """提供测试数据库的会话"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 覆盖 FastAPI 依赖注入 —— 使用测试数据库
# ---------------------------------------------------------------------------


def _override_get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖覆盖：使用测试数据库的 session"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Token / Header Fixtures（适配 chainke-full 的认证系统）
# ---------------------------------------------------------------------------
# chainke-full 使用硬编码的 dev 认证：
#   admin / admin123 → role: admin
#   dev   / dev123   → role: developer
# JWT token 返回格式: {"token": "...", "user": {...}}


@pytest.fixture
def admin_token(client: TestClient) -> str:
    """获取 admin 用户的 JWT token"""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"admin 登录失败: {resp.text}"
    data = resp.json()
    # chainke-full 返回 token 在 "token" 字段
    return data.get("token") or data.get("access_token", "")


@pytest.fixture
def dev_token(client: TestClient) -> str:
    """获取 dev 用户的 JWT token"""
    resp = client.post("/api/auth/login", json={"username": "dev", "password": "dev123"})
    assert resp.status_code == 200, f"dev 登录失败: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("access_token", "")


@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def dev_headers(dev_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {dev_token}"}
