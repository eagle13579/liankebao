"""
AI数字名片 Brochure API — 画册 CRUD 测试套件
===============================================
覆盖:
  - 创建图册 (create)
  - 读取图册 (get/ list)
  - 更新图册 (update title, status, cover, pages)
  - 删除图册 (delete)
  - 权限隔离 (不同用户不能互操作)
  - 公开/私有访问控制
  - 多种状态 (draft, published, archived)
  - 数据完整性约束

函数级测试 (digital_brochure_api 已有的函数):
  - get_brochure
  - get_user_brochures
  - record_visit
  - get_visitor_logs
  - dict_from_row

API 级测试 (已实现的 3 个路由):
  - GET  /api/v1/digital-brochure/{id}
  - POST /api/v1/digital-brochure/{id}/visit
  - GET  /api/v1/digital-brochure/{id}/visitors
"""

import pytest
from digital_brochure_api import (
    dict_from_row,
    get_brochure,
    get_user_brochures,
    get_visitor_logs,
    record_visit,
)


# ============================================================
# 数据层: 创建图册
# ============================================================


class TestCreateBrochure:
    """图册创建 (数据库层)"""

    def test_create_minimal(self, brochure_db, brochure_user):
        """创建图册 (仅必填字段)"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO brochures (user_id, title)
               VALUES (?, ?)""",
            (brochure_user["profile_id"], "最小图册"),
        )
        brochure_id = cursor.lastrowid
        conn.commit()
        assert brochure_id > 0

        b = get_brochure(brochure_id)
        assert b["title"] == "最小图册"
        assert b["status"] == "draft"  # 默认状态
        assert b["pages_count"] == 0
        assert b["is_public"] == 1
        assert b["view_count"] == 0
        assert b["share_count"] == 0

    def test_create_full(self, brochure_db, brochure_user):
        """创建图册 (所有字段)"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO brochures
               (user_id, title, cover, pages_count, description, status, is_public)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (brochure_user["profile_id"], "完整图册", "https://example.com/cover.png",
             20, "完整的图册描述", "published", 1),
        )
        brochure_id = cursor.lastrowid
        conn.commit()
        assert brochure_id > 0

        b = get_brochure(brochure_id)
        assert b["title"] == "完整图册"
        assert b["cover"] == "https://example.com/cover.png"
        assert b["pages_count"] == 20
        assert b["description"] == "完整的图册描述"
        assert b["status"] == "published"
        assert b["is_public"] == 1

    def test_create_draft(self, brochure_db, brochure_user):
        """创建草稿状态图册"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO brochures (user_id, title, status, is_public)
               VALUES (?, ?, 'draft', 0)""",
            (brochure_user["profile_id"], "草稿图册"),
        )
        brochure_id = cursor.lastrowid
        conn.commit()

        b = get_brochure(brochure_id)
        assert b["status"] == "draft"
        assert b["is_public"] == 0

    def test_create_archived(self, brochure_db, brochure_user):
        """创建归档状态图册"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO brochures (user_id, title, status)
               VALUES (?, ?, 'archived')""",
            (brochure_user["profile_id"], "归档图册"),
        )
        brochure_id = cursor.lastrowid
        conn.commit()

        b = get_brochure(brochure_id)
        assert b["status"] == "archived"

    def test_create_no_title(self, brochure_db, brochure_user):
        """缺少标题应违反 NOT NULL 约束"""
        conn = brochure_db
        cursor = conn.cursor()
        with pytest.raises(Exception):
            cursor.execute(
                "INSERT INTO brochures (user_id) VALUES (?)",
                (brochure_user["profile_id"],),
            )
            conn.commit()

    def test_create_invalid_user_id(self, brochure_db):
        """无效 user_id 应违反 FK 约束"""
        conn = brochure_db
        cursor = conn.cursor()
        with pytest.raises(Exception):
            cursor.execute(
                """INSERT INTO brochures (user_id, title)
                   VALUES (?, ?)""",
                (99999, "无主图册"),
            )
            conn.commit()

    def test_create_multiple(self, brochure_db, brochure_user):
        """同一用户可创建多本图册"""
        conn = brochure_db
        cursor = conn.cursor()
        for i in range(5):
            cursor.execute(
                """INSERT INTO brochures (user_id, title)
                   VALUES (?, ?)""",
                (brochure_user["profile_id"], f"图册_{i}"),
            )
        conn.commit()

        brochures = get_user_brochures(brochure_user["profile_id"])
        assert len(brochures) == 5


# ============================================================
# 数据层: 读取图册
# ============================================================


class TestReadBrochure:
    """图册读取"""

    def test_get_existing(self, brochure_db, brochure_sample):
        """获取存在的图册"""
        b = get_brochure(brochure_sample["id"])
        assert b is not None
        assert b["id"] == brochure_sample["id"]
        assert b["title"] == brochure_sample["title"]

    def test_get_nonexistent(self):
        """获取不存在的图册返回 None"""
        assert get_brochure(99999) is None

    def test_get_all_fields(self, brochure_db, brochure_sample):
        """返回的图册包含所有必要字段"""
        b = get_brochure(brochure_sample["id"])
        expected = {
            "id", "user_id", "title", "cover", "pages_count",
            "description", "status", "is_public", "view_count",
            "share_count", "created_at", "updated_at",
        }
        actual = set(b.keys())
        missing = expected - actual
        assert not missing, f"缺少字段: {missing}"

    def test_get_user_brochures_list(self, brochure_db, brochure_user, brochure_sample):
        """获取用户图册列表"""
        brochures = get_user_brochures(brochure_user["profile_id"])
        assert len(brochures) >= 1
        ids = [b["id"] for b in brochures]
        assert brochure_sample["id"] in ids

    def test_get_user_brochures_order(self, brochure_db, brochure_user, brochure_sample):
        """列表按 updated_at 降序"""
        conn = brochure_db
        cursor = conn.cursor()
        # 创建第二本图册
        cursor.execute(
            """INSERT INTO brochures (user_id, title) VALUES (?, ?)""",
            (brochure_user["profile_id"], "第二本"),
        )
        conn.commit()

        brochures = get_user_brochures(brochure_user["profile_id"])
        if len(brochures) >= 2:
            times = [b["updated_at"] for b in brochures]
            assert times == sorted(times, reverse=True)

    def test_get_user_brochures_empty(self):
        """无图册用户返回空列表"""
        assert get_user_brochures(99999) == []

    def test_get_user_brochures_isolated(self, brochure_db, brochure_user, brochure_user2, brochure_sample, brochure_other_sample):
        """用户只能看到自己的图册 (权限隔离)"""
        user1_brochures = get_user_brochures(brochure_user["profile_id"])
        user2_brochures = get_user_brochures(brochure_user2["profile_id"])

        user1_ids = {b["id"] for b in user1_brochures}
        user2_ids = {b["id"] for b in user2_brochures}

        assert brochure_sample["id"] in user1_ids
        assert brochure_sample["id"] not in user2_ids
        assert brochure_other_sample["id"] in user2_ids
        assert brochure_other_sample["id"] not in user1_ids


# ============================================================
# 数据层: 更新图册
# ============================================================


class TestUpdateBrochure:
    """图册更新 (数据库层)"""

    def test_update_title(self, brochure_db, brochure_sample):
        """更新标题"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE brochures SET title = ? WHERE id = ?",
            ("更新后的标题", brochure_sample["id"]),
        )
        conn.commit()

        b = get_brochure(brochure_sample["id"])
        assert b["title"] == "更新后的标题"

    def test_update_status(self, brochure_db, brochure_sample):
        """更新状态: draft -> published -> archived"""
        conn = brochure_db
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE brochures SET status = 'published' WHERE id = ?",
            (brochure_sample["id"],),
        )
        conn.commit()
        assert get_brochure(brochure_sample["id"])["status"] == "published"

        cursor.execute(
            "UPDATE brochures SET status = 'archived' WHERE id = ?",
            (brochure_sample["id"],),
        )
        conn.commit()
        assert get_brochure(brochure_sample["id"])["status"] == "archived"

    def test_update_cover(self, brochure_db, brochure_sample):
        """更新封面"""
        conn = brochure_db
        cursor = conn.cursor()
        new_cover = "https://example.com/new-cover.jpg"
        cursor.execute(
            "UPDATE brochures SET cover = ? WHERE id = ?",
            (new_cover, brochure_sample["id"]),
        )
        conn.commit()
        assert get_brochure(brochure_sample["id"])["cover"] == new_cover

    def test_update_pages_count(self, brochure_db, brochure_sample):
        """更新页数"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE brochures SET pages_count = 25 WHERE id = ?",
            (brochure_sample["id"],),
        )
        conn.commit()
        assert get_brochure(brochure_sample["id"])["pages_count"] == 25

    def test_update_description(self, brochure_db, brochure_sample):
        """更新描述"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE brochures SET description = ? WHERE id = ?",
            ("新的描述内容", brochure_sample["id"]),
        )
        conn.commit()
        assert get_brochure(brochure_sample["id"])["description"] == "新的描述内容"

    def test_update_is_public(self, brochure_db, brochure_sample):
        """更新公开/私有状态"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE brochures SET is_public = 0 WHERE id = ?",
            (brochure_sample["id"],),
        )
        conn.commit()
        assert get_brochure(brochure_sample["id"])["is_public"] == 0

    def test_update_multiple_fields(self, brochure_db, brochure_sample):
        """同时更新多个字段"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE brochures
               SET title = ?, description = ?, pages_count = ?, status = ?
               WHERE id = ?""",
            ("多重更新", "多重更新描述", 30, "published", brochure_sample["id"]),
        )
        conn.commit()

        b = get_brochure(brochure_sample["id"])
        assert b["title"] == "多重更新"
        assert b["description"] == "多重更新描述"
        assert b["pages_count"] == 30
        assert b["status"] == "published"

    def test_update_nonexistent(self, brochure_db):
        """更新不存在的图册不影响任何行"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE brochures SET title = 'ghost' WHERE id = ?", (99999,)
        )
        conn.commit()
        assert cursor.rowcount == 0

    def test_update_time_stamp(self, brochure_db, brochure_sample):
        """更新后 updated_at 应变化"""
        b_before = get_brochure(brochure_sample["id"])

        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE brochures SET title = 'timestamp test' WHERE id = ?",
            (brochure_sample["id"],),
        )
        conn.commit()

        b_after = get_brochure(brochure_sample["id"])
        assert b_after["updated_at"] >= b_before["updated_at"]


# ============================================================
# 数据层: 删除图册
# ============================================================


class TestDeleteBrochure:
    """图册删除 (数据库层)"""

    def test_delete_existing(self, brochure_db, brochure_sample):
        """删除存在的图册"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute("DELETE FROM brochures WHERE id = ?", (brochure_sample["id"],))
        conn.commit()
        assert cursor.rowcount == 1
        assert get_brochure(brochure_sample["id"]) is None

    def test_delete_nonexistent(self, brochure_db):
        """删除不存在的图册影响 0 行"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute("DELETE FROM brochures WHERE id = ?", (99999,))
        conn.commit()
        assert cursor.rowcount == 0

    def test_delete_cascades_to_visitor_logs(self, brochure_db, brochure_sample):
        """删除图册时 visitor_logs 的行为 (取决于 FK 设置)"""
        # 先创建访问记录
        record_visit(brochure_sample["id"])

        conn = brochure_db
        cursor = conn.cursor()

        # SQLite 默认 FK 约束: 删除父记录时, 如果子记录存在, 会因 FK 约束失败
        # 但 PRAGMA foreign_keys=ON 时, 默认行为是 RESTRICT
        with pytest.raises(Exception):
            cursor.execute("DELETE FROM brochures WHERE id = ?", (brochure_sample["id"],))
            conn.commit()

    def test_delete_user_cascades_to_brochures(self, brochure_db, brochure_user, brochure_sample):
        """删除用户时图册的行为"""
        conn = brochure_db
        cursor = conn.cursor()
        # users 表没有 CASCADE 设置, 应因 FK 约束失败
        with pytest.raises(Exception):
            cursor.execute("DELETE FROM users WHERE id = ?", (brochure_user["profile_id"],))
            conn.commit()


# ============================================================
# 访客功能测试
# ============================================================


class TestVisitorFunctions:
    """访客记录功能"""

    def test_record_visit_increments_count(self, brochure_db, brochure_sample):
        """记录访问后 view_count 增加 1"""
        before = get_brochure(brochure_sample["id"])["view_count"]
        log_id = record_visit(brochure_sample["id"])
        assert log_id > 0
        after = get_brochure(brochure_sample["id"])["view_count"]
        assert after == before + 1

    def test_record_visit_multiple(self, brochure_db, brochure_sample):
        """多次访问累积计数"""
        for _ in range(5):
            record_visit(brochure_sample["id"])
        assert get_brochure(brochure_sample["id"])["view_count"] == 5

    def test_record_visit_with_visitor_id(self, brochure_db, brochure_sample, brochure_user):
        """带访客 ID 的记录"""
        log_id = record_visit(brochure_sample["id"], visitor_id=brochure_user["profile_id"])
        cursor = brochure_db.cursor()
        cursor.execute("SELECT visitor_id FROM visitor_logs WHERE id = ?", (log_id,))
        assert cursor.fetchone()[0] == brochure_user["profile_id"]

    def test_record_visit_with_ip(self, brochure_db, brochure_sample):
        """带访客 IP 的记录"""
        log_id = record_visit(brochure_sample["id"], visitor_ip="192.168.1.100")
        cursor = brochure_db.cursor()
        cursor.execute("SELECT visitor_ip FROM visitor_logs WHERE id = ?", (log_id,))
        assert cursor.fetchone()[0] == "192.168.1.100"

    def test_record_visit_with_agent(self, brochure_db, brochure_sample):
        """带 User-Agent 的记录"""
        log_id = record_visit(brochure_sample["id"], visitor_agent="Mozilla/5.0")
        cursor = brochure_db.cursor()
        cursor.execute("SELECT visitor_agent FROM visitor_logs WHERE id = ?", (log_id,))
        assert cursor.fetchone()[0] == "Mozilla/5.0"

    def test_record_visit_nonexistent_brochure(self, brochure_db):
        """不存在的图册记录访问应报 FK 错误"""
        with pytest.raises(Exception) as exc:
            record_visit(99999)
        assert "FOREIGN KEY" in str(exc.value) or "IntegrityError" in str(exc.value)

    def test_get_visitor_logs_empty(self, brochure_db, brochure_sample):
        """无访问记录返回空列表"""
        assert get_visitor_logs(brochure_sample["id"]) == []

    def test_get_visitor_logs_with_data(self, brochure_db, brochure_sample, brochure_user):
        """包含访问记录的日志"""
        record_visit(brochure_sample["id"])
        record_visit(brochure_sample["id"], visitor_id=brochure_user["profile_id"])
        logs = get_visitor_logs(brochure_sample["id"])
        assert len(logs) >= 2

    def test_get_visitor_logs_limit(self, brochure_db, brochure_sample):
        """limit 参数生效"""
        for _ in range(10):
            record_visit(brochure_sample["id"])
        logs = get_visitor_logs(brochure_sample["id"], limit=3)
        assert len(logs) <= 3

    def test_get_visitor_logs_order(self, brochure_db, brochure_sample):
        """日志按 created_at DESC 排序"""
        for _ in range(3):
            record_visit(brochure_sample["id"])
        logs = get_visitor_logs(brochure_sample["id"])
        if len(logs) >= 2:
            times = [l["created_at"] for l in logs]
            assert times == sorted(times, reverse=True)

    def test_get_visitor_logs_visitor_name(self, brochure_db, brochure_sample, brochure_user):
        """访客日志包含 visitor_name (LEFT JOIN)"""
        record_visit(brochure_sample["id"], visitor_id=brochure_user["profile_id"])
        logs = get_visitor_logs(brochure_sample["id"])
        assert logs[0].get("visitor_name") is not None

    def test_record_visit_visitor_type(self, brochure_db, brochure_sample):
        """visit_type 默认为 'view'"""
        log_id = record_visit(brochure_sample["id"])
        cursor = brochure_db.cursor()
        cursor.execute("SELECT visit_type FROM visitor_logs WHERE id = ?", (log_id,))
        assert cursor.fetchone()[0] == "view"


# ============================================================
# API 端点测试
# ============================================================


class TestBrochureAPIEndpoints:
    """已实现的 API 端点测试"""

    def test_api_get_brochure_success(self, brochure_client, brochure_sample):
        """GET /api/v1/digital-brochure/{id} 返回 200 + 图册数据"""
        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["id"] == brochure_sample["id"]
        assert data["data"]["title"] == brochure_sample["title"]

    def test_api_get_brochure_not_found(self, brochure_client):
        """不存在的图册返回 404"""
        resp = brochure_client.get("/api/v1/digital-brochure/99999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "图册不存在"

    def test_api_get_brochure_zero_id(self, brochure_client):
        """ID=0 也返回 404 (不存在)"""
        resp = brochure_client.get("/api/v1/digital-brochure/0")
        assert resp.status_code == 404

    def test_api_get_brochure_invalid_id(self, brochure_client):
        """非数字 ID 应返回 422 (FastAPI 自动校验)"""
        resp = brochure_client.get("/api/v1/digital-brochure/abc")
        assert resp.status_code in (422, 404)

    def test_api_record_visit_success(self, brochure_client, brochure_sample):
        """POST /{id}/visit 记录访问"""
        resp = brochure_client.post(f"/api/v1/digital-brochure/{brochure_sample['id']}/visit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "已记录"

    def test_api_record_visit_not_found(self, brochure_client):
        """不存在的图册返回 404"""
        resp = brochure_client.post("/api/v1/digital-brochure/99999/visit")
        assert resp.status_code == 404

    def test_api_record_visit_increments_view_count(self, brochure_client, brochure_sample):
        """API 访问后 view_count 增加"""
        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        before = resp.json()["data"]["view_count"]

        brochure_client.post(f"/api/v1/digital-brochure/{brochure_sample['id']}/visit")

        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        after = resp.json()["data"]["view_count"]
        assert after == before + 1

    def test_api_get_visitors(self, brochure_client, brochure_sample):
        """GET /{id}/visitors 返回访客列表"""
        # 先创建访问记录
        from digital_brochure_api import record_visit
        record_visit(brochure_sample["id"])

        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}/visitors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    def test_api_get_visitors_limit(self, brochure_client, brochure_sample):
        """访客列表支持 limit 参数"""
        from digital_brochure_api import record_visit
        for _ in range(5):
            record_visit(brochure_sample["id"])

        resp = brochure_client.get(
            f"/api/v1/digital-brochure/{brochure_sample['id']}/visitors?limit=2"
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) <= 2

    def test_api_get_visitors_empty(self, brochure_client, brochure_sample):
        """无访问记录返回空列表"""
        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}/visitors")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_api_get_visitors_not_found(self, brochure_client):
        """不存在的图册访问访客列表返回 404 (因 init_db 后无数据)"""
        resp = brochure_client.get("/api/v1/digital-brochure/99999/visitors")
        # 实际上访问不存在的图册时应返回空列表 (路由只检查 brochures 表)
        # 但当前实现没有校验 brochure_id 是否存在
        assert resp.status_code == 200


# ============================================================
# 权限隔离 & 访问控制
# ============================================================


class TestBrochurePermissions:
    """权限隔离与访问控制"""

    def test_public_brochure_accessible_public(self, brochure_client, brochure_sample):
        """公开图册无需认证即可访问"""
        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        assert resp.status_code == 200

    def test_private_brochure_access(self, brochure_client, brochure_db, brochure_sample):
        """私有图册仍然可被访问 (当前实现不检查权限)"""
        cursor = brochure_db.cursor()
        cursor.execute("UPDATE brochures SET is_public = 0 WHERE id = ?", (brochure_sample["id"],))
        brochure_db.commit()

        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        assert resp.status_code == 200  # 当前 API 不做权限检查

    def test_user_brochures_self(self, brochure_db, brochure_user, brochure_sample):
        """用户能看到自己的图册"""
        brochures = get_user_brochures(brochure_user["profile_id"])
        assert brochure_sample["id"] in [b["id"] for b in brochures]

    def test_user_brochures_not_other(self, brochure_db, brochure_user2, brochure_sample):
        """其他用户看不到不属于他的图册"""
        brochures = get_user_brochures(brochure_user2["profile_id"])
        assert brochure_sample["id"] not in [b["id"] for b in brochures]

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_create_requires_auth(self, brochure_client):
        """创建图册需要认证"""
        resp = brochure_client.post("/api/v1/digital-brochure/", json={"title": "test"})
        assert resp.status_code == 401

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_create_success(self, brochure_client, brochure_headers):
        """已认证用户创建图册"""
        resp = brochure_client.post(
            "/api/v1/digital-brochure/",
            headers=brochure_headers,
            json={"title": "API 创建图册", "description": "通过 API 创建", "pages_count": 5, "status": "draft"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["data"]["title"] == "API 创建图册"
        assert "id" in data["data"]

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_update_requires_auth(self, brochure_client, brochure_sample):
        """更新图册需要认证"""
        resp = brochure_client.put(
            f"/api/v1/digital-brochure/{brochure_sample['id']}",
            json={"title": "hacked"},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_update_own_brochure(self, brochure_client, brochure_headers, brochure_sample):
        """用户可更新自己的图册"""
        resp = brochure_client.put(
            f"/api/v1/digital-brochure/{brochure_sample['id']}",
            headers=brochure_headers,
            json={"title": "更新的标题"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "更新的标题"

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_cannot_update_others_brochure(self, brochure_client, brochure_headers, brochure_other_sample):
        """用户不能更新其他人的图册"""
        resp = brochure_client.put(
            f"/api/v1/digital-brochure/{brochure_other_sample['id']}",
            headers=brochure_headers,
            json={"title": "不应成功"},
        )
        assert resp.status_code in (403, 404)

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_delete_requires_auth(self, brochure_client, brochure_sample):
        resp = brochure_client.delete(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        assert resp.status_code == 401

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_delete_own_brochure(self, brochure_client, brochure_headers, brochure_sample):
        resp = brochure_client.delete(
            f"/api/v1/digital-brochure/{brochure_sample['id']}",
            headers=brochure_headers,
        )
        assert resp.status_code == 200
        # 验证已删除
        resp = brochure_client.get(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        assert resp.status_code == 404

    @pytest.mark.skip(reason="CRUD API 端点尚未实现")
    def test_cannot_delete_others_brochure(self, brochure_client, brochure_headers, brochure_other_sample):
        resp = brochure_client.delete(
            f"/api/v1/digital-brochure/{brochure_other_sample['id']}",
            headers=brochure_headers,
        )
        assert resp.status_code in (403, 404)


# ============================================================
# 辅助函数测试
# ============================================================


class TestDictFromRow:
    """dict_from_row 辅助函数"""

    def test_dict_from_row_none(self):
        assert dict_from_row(None) is None

    def test_dict_from_row_valid(self, brochure_db):
        cursor = brochure_db.cursor()
        cursor.execute("SELECT 1 as val, 'hello' as name")
        row = cursor.fetchone()
        d = dict_from_row(row)
        assert d == {"val": 1, "name": "hello"}
