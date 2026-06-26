"""
冷启动引导 API — pytest 单元测试
===================================
覆盖模板列表、默认配置、数据结构验证、服务层、边界情况。

Author: 蟜 (P6, 技术部后端开发)
"""

import re
import sys
from pathlib import Path

# ── 确保项目根目录在 sys.path ────────────────────────────────────
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.onboarding_service import (
    get_templates,
    get_defaults,
    ONBOARDING_TEMPLATES,
    ONBOARDING_STEPS,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def client() -> TestClient:
    """每个测试用例独立的 TestClient"""
    with TestClient(app) as c:
        yield c


# ===================================================================
# 1. 模板列表 API: GET /api/v1/onboarding/templates
# ===================================================================


class TestTemplatesAPI:
    """模板列表 API 端点测试"""

    def test_templates_returns_200(self, client: TestClient):
        """返回 200"""
        resp = client.get("/api/v1/onboarding/templates")
        assert resp.status_code == 200

    def test_templates_response_structure(self, client: TestClient):
        """返回 JSON 含 code/message/data 顶层字段"""
        resp = client.get("/api/v1/onboarding/templates")
        body = resp.json()
        assert "code" in body
        assert "message" in body
        assert "data" in body
        assert body["code"] == 0
        assert body["message"] == "success"

    def test_templates_data_is_array(self, client: TestClient):
        """data 是数组且包含 6 个模板"""
        resp = client.get("/api/v1/onboarding/templates")
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 6

    def test_templates_each_has_required_fields(self, client: TestClient):
        """每个模板包含 id/name/description/preview_color"""
        resp = client.get("/api/v1/onboarding/templates")
        data = resp.json()["data"]
        for tpl in data:
            assert "id" in tpl, f"模板缺少 id: {tpl}"
            assert "name" in tpl, f"模板 {tpl['id']} 缺少 name"
            assert "description" in tpl, f"模板 {tpl['id']} 缺少 description"
            assert "preview_color" in tpl, f"模板 {tpl['id']} 缺少 preview_color"

    def test_templates_each_has_tags_array(self, client: TestClient):
        """每个模板的 tags 是数组"""
        resp = client.get("/api/v1/onboarding/templates")
        data = resp.json()["data"]
        for tpl in data:
            assert "tags" in tpl, f"模板 {tpl['id']} 缺少 tags"
            assert isinstance(tpl["tags"], list), f"模板 {tpl['id']} 的 tags 不是数组"

    def test_templates_ids_are_unique(self, client: TestClient):
        """所有模板 id 唯一"""
        resp = client.get("/api/v1/onboarding/templates")
        data = resp.json()["data"]
        ids = [tpl["id"] for tpl in data]
        assert len(ids) == len(set(ids)), "模板 id 不唯一"

    def test_templates_preview_color_valid(self, client: TestClient):
        """preview_color 是合法颜色值（十六进制色值或 linear-gradient）"""
        resp = client.get("/api/v1/onboarding/templates")
        data = resp.json()["data"]
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        gradient_pattern = re.compile(r"^linear-gradient\(.*\)$")
        for tpl in data:
            color = tpl["preview_color"]
            assert hex_pattern.match(color) or gradient_pattern.match(color), (
                f"模板 {tpl['id']} 的 preview_color 非法: {color}"
            )


# ===================================================================
# 2. 默认配置 API: GET /api/v1/onboarding/defaults
# ===================================================================


class TestDefaultsAPI:
    """默认配置 API 端点测试"""

    def test_defaults_returns_200(self, client: TestClient):
        """返回 200"""
        resp = client.get("/api/v1/onboarding/defaults")
        assert resp.status_code == 200

    def test_defaults_response_structure(self, client: TestClient):
        """返回 JSON 含 code/message/data 顶层字段"""
        resp = client.get("/api/v1/onboarding/defaults")
        body = resp.json()
        assert "code" in body
        assert "message" in body
        assert "data" in body
        assert body["code"] == 0
        assert body["message"] == "success"

    def test_defaults_data_has_total_steps(self, client: TestClient):
        """data 包含 total_steps=3"""
        resp = client.get("/api/v1/onboarding/defaults")
        data = resp.json()["data"]
        assert "total_steps" in data
        assert data["total_steps"] == 3

    def test_defaults_data_has_steps_array(self, client: TestClient):
        """data.steps 是包含 3 步的数组"""
        resp = client.get("/api/v1/onboarding/defaults")
        steps = resp.json()["data"]["steps"]
        assert isinstance(steps, list)
        assert len(steps) == 3

    def test_defaults_each_step_has_required_fields(self, client: TestClient):
        """每一步包含 name/description/fields"""
        resp = client.get("/api/v1/onboarding/defaults")
        steps = resp.json()["data"]["steps"]
        for step in steps:
            assert "name" in step, f"步骤缺少 name: {step.get('step')}"
            assert "description" in step, f"步骤 {step.get('name')} 缺少 description"
            assert "fields" in step, f"步骤 {step.get('name')} 缺少 fields"

    def test_defaults_each_step_fields_non_empty(self, client: TestClient):
        """每一步的 fields 列表非空"""
        resp = client.get("/api/v1/onboarding/defaults")
        steps = resp.json()["data"]["steps"]
        for step in steps:
            assert len(step["fields"]) > 0, (
                f"步骤 {step.get('name')} 的 fields 为空"
            )


# ===================================================================
# 3. 服务层测试
# ===================================================================


class TestOnboardingService:
    """服务层函数单元测试"""

    def test_get_templates_returns_6(self):
        """get_templates() 返回 6 个模板"""
        templates = get_templates()
        assert isinstance(templates, list)
        assert len(templates) == 6

    def test_get_defaults_returns_3_steps(self):
        """get_defaults() 返回 3 步"""
        result = get_defaults()
        assert result["total_steps"] == 3
        assert len(result["steps"]) == 3

    def test_get_defaults_each_step_fields_non_empty(self):
        """每一步的 fields 列表非空"""
        result = get_defaults()
        for step in result["steps"]:
            assert len(step["fields"]) > 0, (
                f"步骤 {step.get('name')} 的 fields 为空"
            )

    def test_source_data_consistency(self):
        """源数据 ONBOARDING_TEMPLATES 与 ONBOARDING_STEPS 结构正确"""
        # 验证模板源数据
        assert len(ONBOARDING_TEMPLATES) == 6
        for tpl in ONBOARDING_TEMPLATES:
            assert isinstance(tpl["tags"], list)

        # 验证步骤源数据
        assert len(ONBOARDING_STEPS) == 3
        for step in ONBOARDING_STEPS:
            assert "step" in step
            assert isinstance(step["fields"], list)
            assert len(step["fields"]) > 0


# ===================================================================
# 4. 边界情况
# ===================================================================


class TestBoundaryCases:
    """边界与异常情况测试"""

    def test_routes_registered(self):
        """路由已注册到 app 中"""
        routes = [r.path for r in app.routes]
        assert "/api/v1/onboarding/templates" in routes
        assert "/api/v1/onboarding/defaults" in routes

    def test_response_content_type_json(self, client: TestClient):
        """响应 Content-Type 包含 application/json"""
        resp = client.get("/api/v1/onboarding/templates")
        assert "application/json" in resp.headers.get("content-type", "").lower()

        resp = client.get("/api/v1/onboarding/defaults")
        assert "application/json" in resp.headers.get("content-type", "").lower()

    def test_templates_field_types(self, client: TestClient):
        """模板字段类型验证: id/name 是字符串"""
        resp = client.get("/api/v1/onboarding/templates")
        data = resp.json()["data"]
        for tpl in data:
            assert isinstance(tpl["id"], str)
            assert isinstance(tpl["name"], str)
            assert isinstance(tpl["description"], str)
            assert isinstance(tpl["preview_color"], str)

    def test_defaults_step_numbers(self, client: TestClient):
        """三步的 step 编号为 1, 2, 3"""
        resp = client.get("/api/v1/onboarding/defaults")
        steps = resp.json()["data"]["steps"]
        for i, step in enumerate(steps, start=1):
            assert step["step"] == i, (
                f"步骤 {step.get('name')} 的编号应为 {i}，实际为 {step['step']}"
            )
