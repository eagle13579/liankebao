"""
AI数字名片 Brochure API — 匹配引擎测试套件
============================================
覆盖 match_records 表的完整功能:

匹配记录 (match_records) 字段:
  - id, user_id, matched_user_id, match_type, match_score
  - match_reason, status, contact_made, created_at, updated_at

match_type 枚举: supply_demand, trust_recommend, geo_proximity, industry_match
status 枚举: pending, contacted, closed

测试重点:
  - 创建匹配记录 (各种类型)
  - 查询匹配列表/历史
  - 状态流转 (pending → contacted → closed)
  - 分数计算与排序
  - 匹配原因文本
  - contact_made 标记
  - 重复匹配
  - 数据完整性
"""

import pytest

from digital_brochure_api import dict_from_row


# ============================================================
# 创建匹配记录
# ============================================================


class TestCreateMatch:
    """创建匹配记录"""

    MATCH_TYPES = ["supply_demand", "trust_recommend", "geo_proximity", "industry_match"]
    STATUSES = ["pending", "contacted", "closed"]

    def test_create_minimal(self, brochure_db, brochure_user, brochure_user2):
        """仅必填字段"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, status)
               VALUES (?, ?, ?, ?)""",
            (brochure_user["profile_id"], brochure_user2["profile_id"], "supply_demand", "pending"),
        )
        conn.commit()
        assert cursor.lastrowid > 0

    def test_create_all_fields(self, brochure_db, brochure_user, brochure_user2):
        """所有字段"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, match_score, match_reason, status, contact_made)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (brochure_user["profile_id"], brochure_user2["profile_id"],
             "supply_demand", 0.95, "高度匹配: 供需互补", "pending", 0),
        )
        conn.commit()
        assert cursor.lastrowid > 0

        row = dict_from_row(cursor.execute(
            "SELECT * FROM match_records WHERE id = ?", (cursor.lastrowid,)
        ).fetchone())
        assert row["match_score"] == 0.95
        assert row["match_reason"] == "高度匹配: 供需互补"
        assert row["contact_made"] == 0

    def test_create_all_match_types(self, brochure_db, brochure_user, brochure_user2):
        """所有匹配类型都可创建"""
        conn = brochure_db
        cursor = conn.cursor()
        for mt in self.MATCH_TYPES:
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, match_score, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (brochure_user["profile_id"], brochure_user2["profile_id"], mt, 0.7),
            )
        conn.commit()

        cursor.execute(
            "SELECT match_type FROM match_records WHERE user_id = ?",
            (brochure_user["profile_id"],),
        )
        types = {r[0] for r in cursor.fetchall()}
        assert types == set(self.MATCH_TYPES)

    def test_create_all_statuses(self, brochure_db, brochure_user, brochure_user2):
        """所有状态都可设置"""
        conn = brochure_db
        cursor = conn.cursor()
        for status in self.STATUSES:
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, status)
                   VALUES (?, ?, 'supply_demand', ?)""",
                (brochure_user["profile_id"], brochure_user2["profile_id"], status),
            )
        conn.commit()

        cursor.execute(
            "SELECT status FROM match_records WHERE user_id = ?",
            (brochure_user["profile_id"],),
        )
        statuses = {r[0] for r in cursor.fetchall()}
        assert statuses == set(self.STATUSES)

    def test_create_with_high_score(self, brochure_db, brochure_user, brochure_user2):
        """高分匹配 (1.0)"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, match_score, match_reason)
               VALUES (?, ?, 'supply_demand', 1.0, '完美匹配')""",
            (brochure_user["profile_id"], brochure_user2["profile_id"]),
        )
        conn.commit()
        row = dict_from_row(cursor.execute(
            "SELECT * FROM match_records WHERE id = ?", (cursor.lastrowid,)
        ).fetchone())
        assert row["match_score"] == 1.0

    def test_create_with_zero_score(self, brochure_db, brochure_user, brochure_user2):
        """零分匹配"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, match_score)
               VALUES (?, ?, 'supply_demand', 0.0)""",
            (brochure_user["profile_id"], brochure_user2["profile_id"]),
        )
        conn.commit()
        assert cursor.lastrowid > 0

    def test_create_multiple_matches_same_user(self, brochure_db, brochure_user, brochure_user2):
        """同一用户可以有多个匹配记录 (不同 target)"""
        conn = brochure_db
        cursor = conn.cursor()
        for i in range(3):
            extra_auth = cursor.execute(
                "INSERT INTO auth_users (username, password_hash, is_active) VALUES (?, ?, 1)",
                (f"match_target_{i}", "hash"),
            ).lastrowid
            extra_profile = cursor.execute(
                "INSERT INTO users (auth_user_id, name) VALUES (?, ?)",
                (extra_auth, f"Match Target {i}"),
            ).lastrowid

            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, match_score)
                   VALUES (?, ?, 'supply_demand', ?)""",
                (brochure_user["profile_id"], extra_profile, 0.5 + i * 0.15),
            )
        conn.commit()

        cursor.execute(
            "SELECT COUNT(*) FROM match_records WHERE user_id = ?",
            (brochure_user["profile_id"],),
        )
        assert cursor.fetchone()[0] == 3


# ============================================================
# 查询匹配记录
# ============================================================


class TestQueryMatch:
    """查询匹配记录"""

    def test_query_by_user(self, brochure_db, brochure_user, brochure_user2, brochure_match_record):
        """按 user_id 查询"""
        cursor = brochure_db.cursor()
        cursor.execute(
            "SELECT * FROM match_records WHERE user_id = ?",
            (brochure_user["profile_id"],),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        assert len(rows) >= 1
        assert rows[0]["matched_user_id"] == brochure_user2["profile_id"]

    def test_query_by_matched_user(self, brochure_db, brochure_user, brochure_user2, brochure_match_record):
        """按 matched_user_id 查询"""
        cursor = brochure_db.cursor()
        cursor.execute(
            "SELECT * FROM match_records WHERE matched_user_id = ?",
            (brochure_user2["profile_id"],),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        assert len(rows) >= 1

    def test_query_empty(self, brochure_db):
        """无匹配记录返回空列表"""
        cursor = brochure_db.cursor()
        cursor.execute(
            "SELECT * FROM match_records WHERE user_id = ?", (99999,)
        )
        assert cursor.fetchall() == []

    def test_query_by_type(self, brochure_db, brochure_user, brochure_user2, brochure_match_record):
        """按 match_type 过滤"""
        cursor = brochure_db.cursor()
        cursor.execute(
            "SELECT * FROM match_records WHERE user_id = ? AND match_type = ?",
            (brochure_user["profile_id"], "supply_demand"),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        assert len(rows) >= 1

    def test_query_by_status(self, brochure_db, brochure_user, brochure_user2, brochure_match_record):
        """按 status 过滤"""
        cursor = brochure_db.cursor()
        cursor.execute(
            "SELECT * FROM match_records WHERE user_id = ? AND status = ?",
            (brochure_user["profile_id"], "pending"),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        assert len(rows) >= 1

    def test_query_by_score_range(self, brochure_db, brochure_user, brochure_user2, brochure_match_record):
        """按分数范围查询"""
        cursor = brochure_db.cursor()
        cursor.execute(
            """SELECT * FROM match_records
               WHERE user_id = ? AND match_score >= ? AND match_score <= ?""",
            (brochure_user["profile_id"], 0.5, 1.0),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        assert len(rows) >= 1


# ============================================================
# 匹配状态流转
# ============================================================


class TestMatchStatusTransitions:
    """匹配状态流转"""

    def test_pending_to_contacted(self, brochure_db, brochure_match_record):
        """pending → contacted"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE match_records SET status = 'contacted', contact_made = 1 WHERE id = ?",
            (brochure_match_record["id"],),
        )
        conn.commit()

        row = dict_from_row(cursor.execute(
            "SELECT status, contact_made FROM match_records WHERE id = ?",
            (brochure_match_record["id"],),
        ).fetchone())
        assert row["status"] == "contacted"
        assert row["contact_made"] == 1

    def test_contacted_to_closed(self, brochure_db, brochure_match_record):
        """contacted → closed"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE match_records SET status = 'contacted', contact_made = 1 WHERE id = ?",
            (brochure_match_record["id"],),
        )
        cursor.execute(
            "UPDATE match_records SET status = 'closed' WHERE id = ?",
            (brochure_match_record["id"],),
        )
        conn.commit()

        row = dict_from_row(cursor.execute(
            "SELECT status FROM match_records WHERE id = ?",
            (brochure_match_record["id"],),
        ).fetchone())
        assert row["status"] == "closed"

    def test_pending_to_closed_direct(self, brochure_db, brochure_match_record):
        """pending → closed (跳过 contacted)"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE match_records SET status = 'closed' WHERE id = ?",
            (brochure_match_record["id"],),
        )
        conn.commit()

        row = dict_from_row(cursor.execute(
            "SELECT status FROM match_records WHERE id = ?",
            (brochure_match_record["id"],),
        ).fetchone())
        assert row["status"] == "closed"

    def test_contact_made_flag(self, brochure_db, brochure_match_record):
        """contact_made 标记"""
        conn = brochure_db
        cursor = conn.cursor()

        # 初始: contact_made = 0
        row = dict_from_row(cursor.execute(
            "SELECT contact_made FROM match_records WHERE id = ?",
            (brochure_match_record["id"],),
        ).fetchone())
        assert row["contact_made"] == 0

        # 更新为 contacted
        cursor.execute(
            "UPDATE match_records SET status = 'contacted', contact_made = 1 WHERE id = ?",
            (brochure_match_record["id"],),
        )
        conn.commit()

        row = dict_from_row(cursor.execute(
            "SELECT contact_made FROM match_records WHERE id = ?",
            (brochure_match_record["id"],),
        ).fetchone())
        assert row["contact_made"] == 1

    def test_status_transition_timestamps(self, brochure_db, brochure_match_record):
        """状态更新应更新 updated_at"""
        conn = brochure_db
        cursor = conn.cursor()

        row_before = dict_from_row(cursor.execute(
            "SELECT updated_at FROM match_records WHERE id = ?",
            (brochure_match_record["id"],),
        ).fetchone())

        cursor.execute(
            "UPDATE match_records SET status = 'contacted' WHERE id = ?",
            (brochure_match_record["id"],),
        )
        conn.commit()

        row_after = dict_from_row(cursor.execute(
            "SELECT updated_at FROM match_records WHERE id = ?",
            (brochure_match_record["id"],),
        ).fetchone())

        assert row_after["updated_at"] >= row_before["updated_at"]


# ============================================================
# 匹配排序 & 分数
# ============================================================


class TestMatchSorting:
    """匹配分数排序"""

    def test_multiple_matches_ordered(self, brochure_db, brochure_user, brochure_user2):
        """多个匹配按分数降序"""
        conn = brochure_db
        cursor = conn.cursor()

        users = []
        for i in range(3):
            extra_auth = cursor.execute(
                "INSERT INTO auth_users (username, password_hash, is_active) VALUES (?, ?, 1)",
                (f"sort_target_{i}", "hash"),
            ).lastrowid
            extra_profile = cursor.execute(
                "INSERT INTO users (auth_user_id, name) VALUES (?, ?)",
                (extra_auth, f"Sort Target {i}"),
            ).lastrowid
            users.append(extra_profile)

        scores = [0.3, 0.9, 0.6]
        for uid, score in zip(users, scores):
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, match_score)
                   VALUES (?, ?, 'supply_demand', ?)""",
                (brochure_user["profile_id"], uid, score),
            )
        conn.commit()

        cursor.execute(
            "SELECT match_score FROM match_records WHERE user_id = ? ORDER BY match_score DESC",
            (brochure_user["profile_id"],),
        )
        fetched_scores = [r[0] for r in cursor.fetchall()]
        assert fetched_scores == sorted(fetched_scores, reverse=True)

    def test_score_null(self, brochure_db, brochure_user, brochure_user2):
        """match_score 可为 NULL"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, status)
               VALUES (?, ?, 'supply_demand', 'pending')""",
            (brochure_user["profile_id"], brochure_user2["profile_id"]),
        )
        conn.commit()

        row = dict_from_row(cursor.execute(
            "SELECT match_score FROM match_records WHERE id = ?", (cursor.lastrowid,)
        ).fetchone())
        assert row["match_score"] is None

    def test_score_boundaries(self, brochure_db, brochure_user, brochure_user2):
        """分数边界值"""
        conn = brochure_db
        cursor = conn.cursor()

        for score in [0.0, 0.001, 0.5, 0.999, 1.0]:
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, match_score)
                   VALUES (?, ?, 'supply_demand', ?)""",
                (brochure_user["profile_id"], brochure_user2["profile_id"], score),
            )
        conn.commit()

        cursor.execute(
            "SELECT COUNT(*) FROM match_records WHERE user_id = ?",
            (brochure_user["profile_id"],),
        )
        assert cursor.fetchone()[0] == 5


# ============================================================
# 数据完整性
# ============================================================


class TestMatchIntegrity:
    """FK 约束和数据完整性"""

    def test_invalid_user_id(self, brochure_db, brochure_user2):
        cursor = brochure_db.cursor()
        with pytest.raises(Exception):
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, status)
                   VALUES (?, ?, 'supply_demand', 'pending')""",
                (99999, brochure_user2["profile_id"]),
            )
            brochure_db.commit()

    def test_invalid_matched_user_id(self, brochure_db, brochure_user):
        cursor = brochure_db.cursor()
        with pytest.raises(Exception):
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, status)
                   VALUES (?, ?, 'supply_demand', 'pending')""",
                (brochure_user["profile_id"], 99999),
            )
            brochure_db.commit()

    def test_self_match_allowed(self, brochure_db, brochure_user):
        """可匹配自己 (无 CHECK 约束)"""
        cursor = brochure_db.cursor()
        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, match_score, status)
               VALUES (?, ?, 'supply_demand', 1.0, 'pending')""",
            (brochure_user["profile_id"], brochure_user["profile_id"]),
        )
        brochure_db.commit()
        assert cursor.lastrowid > 0

    def test_duplicate_match_allowed(self, brochure_db, brochure_user, brochure_user2):
        """同一对 user, matched_user 可有多条匹配记录 (无 UNIQUE 约束)"""
        conn = brochure_db
        cursor = conn.cursor()
        for i in range(3):
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, match_score, status)
                   VALUES (?, ?, 'supply_demand', ?, 'pending')""",
                (brochure_user["profile_id"], brochure_user2["profile_id"], 0.5 + i * 0.1),
            )
        conn.commit()

        cursor.execute(
            "SELECT COUNT(*) FROM match_records WHERE user_id = ? AND matched_user_id = ?",
            (brochure_user["profile_id"], brochure_user2["profile_id"]),
        )
        assert cursor.fetchone()[0] == 3


# ============================================================
# 匹配推荐逻辑 (待实现)
# ============================================================


class TestMatchEngineSkipped:
    """匹配引擎高级功能 (标记 skip 直到实现)"""

    @pytest.mark.skip(reason="匹配引擎 find_matches 尚未实现")
    def test_find_matches(self, brochure_db, brochure_user, brochure_user2):
        from digital_brochure_api import find_matches
        matches = find_matches(user_id=brochure_user["profile_id"], limit=10)
        assert isinstance(matches, list)

    @pytest.mark.skip(reason="匹配引擎 recommend_connections 尚未实现")
    def test_recommend_connections(self, brochure_db, brochure_user, brochure_user2):
        from digital_brochure_api import recommend_connections
        recommendations = recommend_connections(brochure_user["profile_id"])
        assert isinstance(recommendations, list)

    @pytest.mark.skip(reason="匹配引擎 calculate_match_score 尚未实现")
    def test_calculate_match_score(self):
        from digital_brochure_api import calculate_match_score
        score = calculate_match_score(
            user_id=1, target_user_id=2,
            trust_level=3, industry_overlap=0.8, supply_demand_match=True,
        )
        assert 0 <= score <= 1.0

    @pytest.mark.skip(reason="匹配 API 端点尚未实现")
    def test_get_matches_api(self, brochure_client, brochure_headers):
        resp = brochure_client.get(
            "/api/v1/digital-brochure/matches",
            headers=brochure_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    @pytest.mark.skip(reason="匹配 API 端点尚未实现")
    def test_confirm_match_api(self, brochure_client, brochure_headers, brochure_match_record):
        resp = brochure_client.post(
            f"/api/v1/digital-brochure/matches/{brochure_match_record['id']}/confirm",
            headers=brochure_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "匹配已确认"
