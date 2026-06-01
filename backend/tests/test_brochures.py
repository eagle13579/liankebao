"""
画册 CRUD & 权限隔离测试
===========================
覆盖 digital_brochure_api.py 中已实现和待实现的图册功能:

已实现:
- get_brochure (直接函数)
- record_visit / get_visitor_logs
- API: GET /api/digital-brochure/{id}
- API: POST /api/digital-brochure/{id}/visit
- API: GET /api/digital-brochure/{id}/visitors

待实现 (标记 skip):
- 创建/更新/删除图册
- 权限隔离
"""
import pytest


# ============================================================
# 已实现的函数测试
# ============================================================


class TestGetBrochure:
    """获取图册功能测试"""

    def test_get_brochure_exists(self, test_db, sample_brochure):
        """已存在的图册应能正确返回"""
        from digital_brochure_api import get_brochure

        brochure = get_brochure(sample_brochure["id"])
        assert brochure is not None
        assert brochure["id"] == sample_brochure["id"]
        assert brochure["title"] == sample_brochure["title"]
        assert brochure["status"] == sample_brochure["status"]

    def test_get_brochure_not_found(self, test_db):
        """不存在的图册应返回 None"""
        from digital_brochure_api import get_brochure

        result = get_brochure(99999)
        assert result is None

    def test_get_brochure_fields(self, test_db, sample_brochure):
        """返回的图册应包含所有必要字段"""
        from digital_brochure_api import get_brochure

        brochure = get_brochure(sample_brochure["id"])
        expected_fields = {
            "id", "user_id", "title", "cover", "pages_count",
            "description", "status", "is_public", "view_count",
            "share_count", "created_at", "updated_at",
        }
        actual_fields = set(brochure.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"缺少字段: {missing}"


class TestGetUserBrochures:
    """获取用户图册列表测试"""

    def test_get_user_brochures(self, test_db, sample_user_data, sample_brochure):
        """应返回用户的所有图册"""
        from digital_brochure_api import get_user_brochures

        brochures = get_user_brochures(sample_user_data["profile_id"])
        assert len(brochures) >= 1
        ids = [b["id"] for b in brochures]
        assert sample_brochure["id"] in ids

    def test_get_user_brochures_order(self, test_db, sample_user_data, sample_brochure):
        """图册应按 updated_at 降序排列"""
        from digital_brochure_api import get_user_brochures

        brochures = get_user_brochures(sample_user_data["profile_id"])
        if len(brochures) >= 2:
            times = [b["updated_at"] for b in brochures]
            assert times == sorted(times, reverse=True), "应按 updated_at 降序"

    def test_get_user_brochures_empty(self, test_db):
        """无图册用户应返回空列表"""
        from digital_brochure_api import get_user_brochures

        result = get_user_brochures(99999)
        assert result == []


class TestRecordVisit:
    """记录访客功能测试"""

    def test_record_visit(self, test_db, sample_brochure):
        """访问记录应创建访客日志并增加浏览计数"""
        from digital_brochure_api import get_brochure, record_visit

        before_count = get_brochure(sample_brochure["id"])["view_count"]

        log_id = record_visit(sample_brochure["id"])
        assert log_id > 0

        after_count = get_brochure(sample_brochure["id"])["view_count"]
        assert after_count == before_count + 1, "浏览计数应增加 1"

    def test_record_visit_with_visitor(self, test_db, sample_brochure, sample_user_data):
        """带访客 ID 的记录应保存 visitor_id"""
        from digital_brochure_api import record_visit

        log_id = record_visit(sample_brochure["id"], visitor_id=sample_user_data["profile_id"])

        cursor = test_db.cursor()
        cursor.execute("SELECT visitor_id FROM visitor_logs WHERE id = ?", (log_id,))
        row = cursor.fetchone()
        assert row[0] == sample_user_data["profile_id"]

    def test_record_visit_nonexistent_brochure(self, test_db):
        """不存在的图册应因 FK 约束报 IntegrityError"""
        from digital_brochure_api import record_visit

        with pytest.raises(Exception) as excinfo:
            record_visit(99999)
        # FK 约束错误
        assert "FOREIGN KEY" in str(excinfo.value) or "IntegrityError" in str(excinfo.value)


class TestGetVisitorLogs:
    """访客日志查询测试"""

    def test_get_visitor_logs(self, test_db, sample_brochure, sample_user_data):
        """应返回图册的访客记录"""
        from digital_brochure_api import get_visitor_logs, record_visit

        # 先创建几条访问记录
        record_visit(sample_brochure["id"])
        record_visit(sample_brochure["id"], visitor_id=sample_user_data["profile_id"])

        logs = get_visitor_logs(sample_brochure["id"])
        assert len(logs) >= 2
        assert logs[0]["brochure_id"] == sample_brochure["id"]
        assert "visit_type" in logs[0]

    def test_get_visitor_logs_limit(self, test_db, sample_brochure):
        """应支持 limit 参数"""
        from digital_brochure_api import get_visitor_logs, record_visit

        for _ in range(5):
            record_visit(sample_brochure["id"])

        logs = get_visitor_logs(sample_brochure["id"], limit=3)
        assert len(logs) <= 3

    def test_get_visitor_logs_empty(self, test_db, sample_brochure):
        """无访问记录的图册应返回空列表"""
        from digital_brochure_api import get_visitor_logs

        logs = get_visitor_logs(sample_brochure["id"])
        assert logs == []


# ============================================================
# API 端点测试
# ============================================================


class TestBrochureAPI:
    """图册 API 端点测试 (已实现)"""

    def test_api_get_brochure_success(self, client, test_db, sample_brochure):
        """GET /api/digital-brochure/{id} 应返回图册信息"""
        resp = client.get(f"/api/digital-brochure/{sample_brochure['id']}")
        assert resp.status_code == 200, f"获取图册失败: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["id"] == sample_brochure["id"]
        assert data["data"]["title"] == sample_brochure["title"]

    def test_api_get_brochure_not_found(self, client):
        """不存在的图册应返回 404"""
        resp = client.get("/api/digital-brochure/99999")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"] == "图册不存在"
        assert resp.status_code == 404

    def test_api_record_visit(self, client, sample_brochure):
        """POST /api/digital-brochure/{id}/visit 应记录访问"""
        resp = client.post(f"/api/digital-brochure/{sample_brochure['id']}/visit")
        assert resp.status_code == 200, f"记录访问失败: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "已记录"

    def test_api_record_visit_not_found(self, client):
        """不存在的图册返回 404"""
        resp = client.post("/api/digital-brochure/99999/visit")
        assert resp.status_code == 404

    def test_api_get_visitors(self, client, test_db, sample_brochure):
        """GET /api/digital-brochure/{id}/visitors 应返回访客列表"""
        # 先创建一条访问记录
        from digital_brochure_api import record_visit
        record_visit(sample_brochure["id"])

        resp = client.get(f"/api/digital-brochure/{sample_brochure['id']}/visitors")
        assert resp.status_code == 200, f"获取访客失败: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)

    def test_api_get_visitors_limit(self, client, test_db, sample_brochure):
        """访客列表应支持 limit 参数"""
        from digital_brochure_api import record_visit
        for _ in range(5):
            record_visit(sample_brochure["id"])

        resp = client.get(f"/api/digital-brochure/{sample_brochure['id']}/visitors?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) <= 2


# ============================================================
# 待实现的 CRUD & 权限隔离测试
# ============================================================


class TestBrochureCRUD:
    """图册 CRUD 功能测试 (待实现)"""

    @pytest.mark.skip(reason="创建图册端点尚未实现")
    def test_create_brochure(self, client, auth_headers):
        """POST /api/digital-brochure/ 应创建新图册"""
        resp = client.post(
            "/api/digital-brochure/",
            headers=auth_headers,
            json={
                "title": "新图册",
                "description": "描述",
                "pages_count": 5,
                "status": "draft",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["data"]["title"] == "新图册"
        assert "id" in data["data"]

    @pytest.mark.skip(reason="更新图册端点尚未实现")
    def test_update_brochure(self, client, auth_headers, sample_brochure):
        """PUT /api/digital-brochure/{id} 应更新图册"""
        resp = client.put(
            f"/api/digital-brochure/{sample_brochure['id']}",
            headers=auth_headers,
            json={"title": "更新后的标题"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "更新后的标题"

    @pytest.mark.skip(reason="删除图册端点尚未实现")
    def test_delete_brochure(self, client, auth_headers, sample_brochure):
        """DELETE /api/digital-brochure/{id} 应删除图册"""
        resp = client.delete(
            f"/api/digital-brochure/{sample_brochure['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # 确认已删除
        resp = client.get(f"/api/digital-brochure/{sample_brochure['id']}")
        assert resp.status_code == 404

    @pytest.mark.skip(reason="图册列表端点尚未实现")
    def test_list_my_brochures(self, client, auth_headers, sample_brochure):
        """GET /api/digital-brochure/ 应返回当前用户的图册列表"""
        resp = client.get("/api/digital-brochure/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) >= 1
        assert any(b["id"] == sample_brochure["id"] for b in data["data"])


class TestBrochurePermissions:
    """图册权限隔离测试 (待实现)"""

    @pytest.mark.skip(reason="权限隔离尚未实现")
    def test_cannot_update_other_users_brochure(
        self, client, test_db, auth_headers, sample_brochure, second_user
    ):
        """用户不应能修改其他用户的图册"""
        # second_user 试图修改 sample_user 的图册
        resp = client.put(
            f"/api/digital-brochure/{sample_brochure['id']}",
            headers=auth_headers,  # 需要 second_user 的 headers
            json={"title": "被篡改的标题"},
        )
        assert resp.status_code in (403, 404)

    @pytest.mark.skip(reason="权限隔离尚未实现")
    def test_cannot_delete_other_users_brochure(
        self, client, test_db, auth_headers, sample_brochure, second_user
    ):
        """用户不应能删除其他用户的图册"""
        resp = client.delete(
            f"/api/digital-brochure/{sample_brochure['id']}",
            headers=auth_headers,
        )
        assert resp.status_code in (403, 404)

    @pytest.mark.skip(reason="权限隔离尚未实现")
    def test_unauthorized_create(self, client):
        """未认证用户不应能创建图册"""
        resp = client.post(
            "/api/digital-brochure/",
            json={"title": "无权限创建"},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason="权限隔离尚未实现")
    def test_unauthorized_update(self, client, sample_brochure):
        """未认证用户不应能更新图册"""
        resp = client.put(
            f"/api/digital-brochure/{sample_brochure['id']}",
            json={"title": "无权更新"},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason="权限隔离尚未实现")
    def test_public_brochure_accessible_without_auth(self, client, sample_brochure):
        """公开图册应允许未认证访问"""
        resp = client.get(f"/api/digital-brochure/{sample_brochure['id']}")
        assert resp.status_code == 200

    @pytest.mark.skip(reason="权限隔离尚未实现")
    def test_private_brochure_requires_auth(self, client, test_db, sample_brochure):
        """私有图册应要求认证"""
        cursor = test_db.cursor()
        cursor.execute(
            "UPDATE brochures SET is_public = 0 WHERE id = ?",
            (sample_brochure["id"],),
        )
        test_db.commit()

        resp = client.get(f"/api/digital-brochure/{sample_brochure['id']}")
        assert resp.status_code in (401, 403)
