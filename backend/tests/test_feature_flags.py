"""
链客宝 Feature Flags 功能开关 — 测试
======================================
测试范围:
  1. is_enabled — 全局开关 True
  2. is_enabled — 全局开关 False
  3. is_enabled — 不存在 flag 返回 False
  4. is_enabled — 白名单规则 (user_id 命中)
  5. is_enabled — 白名单规则 (user_id 不命中)
  6. is_enabled — 百分比规则 (命中)
  7. is_enabled — 百分比规则 (不命中)
  8. is_enabled — 地域规则 (命中)
  9. is_enabled — 地域规则 (不命中)
 10. is_enabled — 叠加规则 (AND: 白名单+百分比 全部命中)
 11. is_enabled — 叠加规则 (AND: 百分比命中但地域不命中)
 12. enable / disable 方法
 13. add_flag / remove_flag 方法
 14. list_flags 方法
 15. set_rule 方法
 16. API: GET /api/v1/flags
 17. API: GET /api/v1/flags/{name}
 18. API: PUT /api/v1/flags/{name} — 启用
 19. API: PUT /api/v1/flags/{name} — 禁用
 20. API: GET /api/v1/flags/{nonexistent} → 404
"""

import os
import tempfile
import json
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.feature_flags import (
    FeatureFlag,
    FeatureFlagManager,
    UserContext,
    _evaluate_rules,
    feature_flags_bp,
    DEFAULT_FLAGS,
)


# ===================================================================
# 辅助函数：用 user_id hash 反推百分比桶
# ===================================================================

def _hash_bucket(user_id: str) -> int:
    h = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
    return h % 100


# ===================================================================
# FeatureFlagManager 单元测试（使用临时文件避免污染）
# ===================================================================


@pytest.fixture
def tmp_flags_file():
    """提供临时 flags 文件路径，测试后清理"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        path = f.name
        json.dump([], f)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def manager(tmp_flags_file):
    """返回使用临时文件的 FeatureFlagManager"""
    m = FeatureFlagManager(flags_file=tmp_flags_file)
    # 添加预设 flags 用于测试
    for flag in DEFAULT_FLAGS:
        m.add_flag(flag)
    return m


class TestFeatureFlagManager:
    """FeatureFlagManager 基础功能"""

    # ----- 全局开关 -----

    def test_global_enabled_true(self, manager: FeatureFlagManager):
        """flag.enabled=True 且无规则 → 应返回 True"""
        # 创建一个无规则的 flag 并启用
        f = FeatureFlag(name="test_global_on", description="", enabled=True, rules={})
        manager.add_flag(f)
        assert manager.is_enabled("test_global_on") is True

    def test_global_enabled_false(self, manager: FeatureFlagManager):
        """flag.enabled=False → 应返回 False"""
        f = FeatureFlag(name="test_global_off", description="", enabled=False, rules={})
        manager.add_flag(f)
        assert manager.is_enabled("test_global_off") is False

    def test_nonexistent_flag(self, manager: FeatureFlagManager):
        """不存在的 flag → 应返回 False"""
        assert manager.is_enabled("nonexistent_flag_xyz") is False

    # ----- 白名单规则 -----

    def test_whitelist_hit(self, manager: FeatureFlagManager):
        """白名单命中 → 应返回 True"""
        manager.enable("multi_language")
        user = UserContext(user_id="tester_001")
        assert manager.is_enabled("multi_language", user_context=user) is True

    def test_whitelist_miss(self, manager: FeatureFlagManager):
        """白名单未命中 → 应返回 False"""
        manager.enable("multi_language")
        user = UserContext(user_id="random_user_99")
        assert manager.is_enabled("multi_language", user_context=user) is False

    # ----- 百分比规则 -----

    def test_percentage_hit(self, manager: FeatureFlagManager):
        """百分比命中 → 应返回 True"""
        manager.enable("new_matching_engine")
        # 规则是 percentage=10, 找一个哈希 < 10 的 user_id
        hit_uid = None
        for i in range(200):
            uid = f"pct_hit_{i}"
            if _hash_bucket(uid) < 10:
                hit_uid = uid
                break
        assert hit_uid is not None, "无法找到哈希 < 10 的用户 ID"
        user = UserContext(user_id=hit_uid)
        assert manager.is_enabled("new_matching_engine", user_context=user) is True

    def test_percentage_miss(self, manager: FeatureFlagManager):
        """百分比未命中 → 应返回 False"""
        manager.enable("new_matching_engine")
        # 找一个哈希 >= 10 的用户
        for i in range(100):
            uid = f"miss_user_{i}"
            if _hash_bucket(uid) >= 10:
                user = UserContext(user_id=uid)
                result = manager.is_enabled("new_matching_engine", user_context=user)
                assert result is False
                return
        pytest.fail("无法找到百分比未命中的用户 ID")

    # ----- 地域规则 -----

    def test_region_hit(self, manager: FeatureFlagManager):
        """地域命中 → 应返回 True"""
        manager.enable("cross_border")
        user = UserContext(user_id="user_sg", region="SG")
        assert manager.is_enabled("cross_border", user_context=user) is True

    def test_region_miss(self, manager: FeatureFlagManager):
        """地域不命中 → 应返回 False"""
        manager.enable("cross_border")
        user = UserContext(user_id="user_cn", region="CN")
        assert manager.is_enabled("cross_border", user_context=user) is False

    # ----- 叠加规则 (AND) -----

    def test_combined_rules_all_pass(self, manager: FeatureFlagManager):
        """叠加规则: 白名单+百分比 全部通过 → True"""
        manager.enable("beta_feature")
        # beta_feature: whitelist=["alpha_user_01", "alpha_user_02"], percentage=5
        # alpha_user_01 在白名单中，白名单优先放行
        user = UserContext(user_id="alpha_user_01")
        assert manager.is_enabled("beta_feature", user_context=user) is True

    def test_combined_rules_some_fail(self, manager: FeatureFlagManager):
        """叠加规则: 百分比通过但地域不通过 → False"""
        # 临时加一个 flag 测试 AND 叠加
        f = FeatureFlag(
            name="test_and_rules",
            description="AND 叠加测试",
            enabled=True,
            rules={"percentage": 50, "regions": ["US"]},
        )
        manager.add_flag(f)
        # 用户哈希 < 50 但 region = CN → 应 False
        for i in range(100):
            uid = f"and_user_{i}"
            if _hash_bucket(uid) < 50:
                user = UserContext(user_id=uid, region="CN")
                assert manager.is_enabled("test_and_rules", user_context=user) is False
                return
        pytest.fail("无法找到符合条件的测试用户")

    # ----- enable / disable -----

    def test_enable_disable(self, manager: FeatureFlagManager):
        """enable/disable 方法应正确切换状态"""
        flag_name = "new_matching_engine"
        manager.enable(flag_name)
        assert manager.get_flag(flag_name).enabled is True
        manager.disable(flag_name)
        assert manager.get_flag(flag_name).enabled is False

    def test_enable_nonexistent(self, manager: FeatureFlagManager):
        """enable 不存在的 flag → 返回 False"""
        assert manager.enable("no_such_flag") is False

    def test_disable_nonexistent(self, manager: FeatureFlagManager):
        """disable 不存在的 flag → 返回 False"""
        assert manager.disable("no_such_flag") is False

    # ----- add_flag / remove_flag -----

    def test_add_flag(self, manager: FeatureFlagManager):
        """add_flag 应成功添加新 flag"""
        f = FeatureFlag(name="new_test_flag", description="test", enabled=True)
        assert manager.add_flag(f) is True
        assert manager.get_flag("new_test_flag") is not None

    def test_add_duplicate_flag(self, manager: FeatureFlagManager):
        """添加重复 flag → 返回 False"""
        f = FeatureFlag(name="new_matching_engine", description="dup", enabled=False)
        assert manager.add_flag(f) is False

    def test_remove_flag(self, manager: FeatureFlagManager):
        """remove_flag 应成功删除 flag"""
        f = FeatureFlag(name="temp_flag", description="to remove")
        manager.add_flag(f)
        assert manager.remove_flag("temp_flag") is True
        assert manager.get_flag("temp_flag") is None

    def test_remove_nonexistent(self, manager: FeatureFlagManager):
        """删除不存在的 flag → 返回 False"""
        assert manager.remove_flag("no_such_flag") is False

    # ----- list_flags -----

    def test_list_flags(self, manager: FeatureFlagManager):
        """list_flags 应返回所有 flags"""
        flags = manager.list_flags()
        names = [f["name"] for f in flags]
        assert "new_matching_engine" in names
        assert "cross_border" in names
        assert "multi_language" in names
        assert "beta_feature" in names

    # ----- set_rule -----

    def test_set_rule(self, manager: FeatureFlagManager):
        """set_rule 应更新指定 flag 的规则"""
        assert manager.set_rule("new_matching_engine", "percentage", 50) is True
        flag = manager.get_flag("new_matching_engine")
        assert flag.rules["percentage"] == 50

    def test_set_rule_nonexistent(self, manager: FeatureFlagManager):
        """set_rule 对不存在的 flag → 返回 False"""
        assert manager.set_rule("no_such_flag", "percentage", 10) is False

    # ----- is_enabled 无 user_context 但有规则 -----

    def test_no_user_context_with_rules(self, manager: FeatureFlagManager):
        """启用但有规则的 flag，无 user_context → 应返回 False（安全默认）"""
        manager.enable("new_matching_engine")
        assert manager.is_enabled("new_matching_engine") is False


# ===================================================================
# API 端点测试
# ===================================================================


@pytest.fixture
def api_app(tmp_flags_file):
    """返回全新 FastAPI 应用，每次使用孤立 manager"""
    app = FastAPI()

    # 在模块中直接创建新的 manager 并绑定到 blueprint
    new_mgr = FeatureFlagManager(flags_file=tmp_flags_file)
    for flag in DEFAULT_FLAGS:
        new_mgr.add_flag(flag)

    # 覆写模块级 manager（route handlers 引用的是模块级变量）
    import app.features.feature_flags as ff_mod
    ff_mod.manager = new_mgr

    app.include_router(feature_flags_bp)
    return app


@pytest.fixture
def api_client(api_app):
    return TestClient(api_app)


class TestFeatureFlagsAPI:
    """Feature Flags API 端点测试"""

    def test_get_all_flags(self, api_client: TestClient):
        """GET /api/v1/flags 应返回所有 flags"""
        resp = api_client.get("/api/v1/flags")
        assert resp.status_code == 200
        data = resp.json()
        assert "flags" in data
        assert data["total"] >= 4
        names = [f["name"] for f in data["flags"]]
        assert "new_matching_engine" in names

    def test_get_single_flag(self, api_client: TestClient):
        """GET /api/v1/flags/{name} 应返回单个 flag"""
        resp = api_client.get("/api/v1/flags/new_matching_engine")
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag"]["name"] == "new_matching_engine"
        assert data["flag"]["enabled"] is False

    def test_get_nonexistent_flag_404(self, api_client: TestClient):
        """GET /api/v1/flags/{name} 不存在的 flag → 404"""
        resp = api_client.get("/api/v1/flags/nonexistent_flag")
        assert resp.status_code == 404

    def test_put_enable_flag(self, api_client: TestClient):
        """PUT /api/v1/flags/{name} {enabled: true} 应启用 flag"""
        resp = api_client.put("/api/v1/flags/new_matching_engine", json={"enabled": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag"]["name"] == "new_matching_engine"
        assert data["flag"]["enabled"] is True

    def test_put_disable_flag(self, api_client: TestClient):
        """PUT /api/v1/flags/{name} {enabled: false} 应禁用 flag"""
        # 先启用
        api_client.put("/api/v1/flags/new_matching_engine", json={"enabled": True})
        # 再禁用
        resp = api_client.put("/api/v1/flags/new_matching_engine", json={"enabled": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag"]["enabled"] is False

    def test_put_nonexistent_flag_404(self, api_client: TestClient):
        """PUT /api/v1/flags/{name} 不存在的 flag → 404"""
        resp = api_client.put("/api/v1/flags/no_such_flag", json={"enabled": True})
        assert resp.status_code == 404


# ===================================================================
# _evaluate_rules 单元测试（不依赖 Manager）
# ===================================================================


class TestEvaluateRules:
    """_evaluate_rules 纯函数测试"""

    def test_no_rules(self):
        """无规则 → True"""
        flag = FeatureFlag(name="t", enabled=True, rules={})
        assert _evaluate_rules(flag, UserContext()) is True

    def test_whitelist_only_hit(self):
        """仅白名单命中 → True"""
        flag = FeatureFlag(name="t", enabled=True, rules={"whitelist": ["u1", "u2"]})
        assert _evaluate_rules(flag, UserContext(user_id="u1")) is True

    def test_whitelist_only_miss(self):
        """仅白名单未命中 → False (因为无其他规则时, whitelist不命中则percentage/region都没设, 返回False)"""
        flag = FeatureFlag(name="t", enabled=True, rules={"whitelist": ["u1"]})
        assert _evaluate_rules(flag, UserContext(user_id="u3")) is False

    def test_percentage_only_hit(self):
        """仅百分比命中 → True"""
        # 用白名单里未出现的用户
        for i in range(100):
            uid = f"eval_pct_{i}"
            if _hash_bucket(uid) < 30:
                flag = FeatureFlag(name="t", enabled=True, rules={"percentage": 30})
                assert _evaluate_rules(flag, UserContext(user_id=uid)) is True
                return
        pytest.fail("无法找到哈希 < 30 的用户")

    def test_regions_only_hit(self):
        """仅地域命中 → True"""
        flag = FeatureFlag(name="t", enabled=True, rules={"regions": ["US", "JP"]})
        assert _evaluate_rules(flag, UserContext(user_id="u1", region="JP")) is True

    def test_regions_only_miss(self):
        """仅地域未命中 → False"""
        flag = FeatureFlag(name="t", enabled=True, rules={"regions": ["US"]})
        assert _evaluate_rules(flag, UserContext(user_id="u1", region="CN")) is False
