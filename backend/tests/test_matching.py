"""
匹配引擎测试 (digital_brochure_api)
=====================================
测试信任网络和匹配记录功能。

数据库表:
- trust_network: 信任网络 (用户间的信任关系)
- match_records: 匹配记录 (供需匹配结果)

注意: 匹配引擎的高层 API 尚未实现。
      本文件测试数据库层的信任网络和匹配记录功能，
      并用 skip 标记待实现的匹配引擎高级功能。
"""
import pytest


class TestTrustNetwork:
    """信任网络功能测试 (数据库层)"""

    def test_create_trust_relation(self, test_db, sample_user_data, second_user):
        """应能创建信任关系"""
        conn = test_db
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO trust_network
               (user_id, target_user_id, trust_level, tags, notes, is_mutual, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                sample_user_data["profile_id"],
                second_user["profile_id"],
                2,  # trust_level: 2 = 中等信任
                '["合作", "推荐"]',
                "通过项目合作建立信任",
                0,
                "manual",
            ),
        )
        conn.commit()
        assert cursor.lastrowid > 0

        # 验证可查询
        cursor.execute(
            "SELECT * FROM trust_network WHERE user_id = ? AND target_user_id = ?",
            (sample_user_data["profile_id"], second_user["profile_id"]),
        )
        row = dict(zip([d[0] for d in cursor.description], cursor.fetchone()))
        assert row["trust_level"] == 2
        assert row["is_mutual"] == 0
        assert row["source"] == "manual"

    def test_trust_relation_unique(self, test_db, sample_user_data, second_user):
        """同一对用户只能有一条信任关系 (UNIQUE 约束)"""
        conn = test_db
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO trust_network (user_id, target_user_id, trust_level)
               VALUES (?, ?, ?)""",
            (sample_user_data["profile_id"], second_user["profile_id"], 1),
        )
        conn.commit()

        # 重复插入应报错
        with pytest.raises(Exception):
            cursor.execute(
                """INSERT INTO trust_network (user_id, target_user_id, trust_level)
                   VALUES (?, ?, ?)""",
                (sample_user_data["profile_id"], second_user["profile_id"], 2),
            )
            conn.commit()

    def test_mutual_trust(self, test_db, sample_user_data, second_user):
        """应支持双向信任"""
        conn = test_db
        cursor = conn.cursor()

        # A -> B
        cursor.execute(
            """INSERT INTO trust_network (user_id, target_user_id, trust_level, is_mutual)
               VALUES (?, ?, 3, 1)""",
            (sample_user_data["profile_id"], second_user["profile_id"]),
        )
        # B -> A
        cursor.execute(
            """INSERT INTO trust_network (user_id, target_user_id, trust_level, is_mutual)
               VALUES (?, ?, 3, 1)""",
            (second_user["profile_id"], sample_user_data["profile_id"]),
        )
        conn.commit()

        # 验证双向
        cursor.execute(
            "SELECT COUNT(*) FROM trust_network WHERE is_mutual = 1"
        )
        assert cursor.fetchone()[0] >= 2

    def test_trust_network_query(self, test_db, sample_user_data, second_user):
        """应能查询用户的信任网络"""
        conn = test_db
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO trust_network (user_id, target_user_id, trust_level)
               VALUES (?, ?, ?)""",
            (sample_user_data["profile_id"], second_user["profile_id"], 2),
        )
        conn.commit()

        cursor.execute(
            "SELECT * FROM trust_network WHERE user_id = ?",
            (sample_user_data["profile_id"],),
        )
        rows = cursor.fetchall()
        assert len(rows) >= 1
        assert rows[0][2] == second_user["profile_id"]  # target_user_id


class TestMatchRecords:
    """匹配记录功能测试 (数据库层)"""

    def test_create_match_record(self, test_db, sample_user_data, second_user):
        """应能创建匹配记录"""
        conn = test_db
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, match_score, match_reason, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                sample_user_data["profile_id"],
                second_user["profile_id"],
                "supply_demand",
                0.85,
                "供应与需求高度匹配 (建材类目)",
                "pending",
            ),
        )
        conn.commit()
        assert cursor.lastrowid > 0

        # 验证
        cursor.execute("SELECT * FROM match_records WHERE id = ?", (cursor.lastrowid,))
        row = dict(zip([d[0] for d in cursor.description], cursor.fetchone()))
        assert row["match_type"] == "supply_demand"
        assert abs(row["match_score"] - 0.85) < 0.001
        assert row["status"] == "pending"
        assert row["contact_made"] == 0

    def test_match_record_status_transitions(self, test_db, sample_user_data, second_user):
        """匹配记录应支持状态流转"""
        conn = test_db
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO match_records
               (user_id, matched_user_id, match_type, status)
               VALUES (?, ?, 'supply_demand', 'pending')""",
            (sample_user_data["profile_id"], second_user["profile_id"]),
        )
        record_id = cursor.lastrowid

        # pending -> contacted
        cursor.execute(
            "UPDATE match_records SET status = 'contacted', contact_made = 1 WHERE id = ?",
            (record_id,),
        )
        conn.commit()

        cursor.execute("SELECT status, contact_made FROM match_records WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        assert row[0] == "contacted"
        assert row[1] == 1

        # contacted -> closed
        cursor.execute(
            "UPDATE match_records SET status = 'closed' WHERE id = ?",
            (record_id,),
        )
        conn.commit()

        cursor.execute("SELECT status FROM match_records WHERE id = ?", (record_id,))
        assert cursor.fetchone()[0] == "closed"

    def test_multi_type_matches(self, test_db, sample_user_data, second_user):
        """应支持多种匹配类型"""
        conn = test_db
        cursor = conn.cursor()

        match_types = ["supply_demand", "trust_recommend", "geo_proximity", "industry_match"]
        for mt in match_types:
            cursor.execute(
                """INSERT INTO match_records
                   (user_id, matched_user_id, match_type, match_score)
                   VALUES (?, ?, ?, ?)""",
                (sample_user_data["profile_id"], second_user["profile_id"], mt, 0.7),
            )
        conn.commit()

        cursor.execute(
            "SELECT match_type FROM match_records WHERE user_id = ?",
            (sample_user_data["profile_id"],),
        )
        types = [row[0] for row in cursor.fetchall()]
        assert len(types) == len(match_types)
        for mt in match_types:
            assert mt in types


# ============================================================
# 匹配引擎 API (待实现)
# ============================================================


class TestMatchingEngine:
    """匹配引擎高级功能测试 (待实现)"""

    @pytest.mark.skip(reason="匹配引擎功能尚未实现")
    def test_find_matches(self):
        """应能基于信任网络和供需信息找到匹配

        匹配逻辑预期:
        1. 从 trust_network 中找到信任用户
        2. 根据用户标签/行业信息计算匹配分数
        3. 返回按分数降序排列的匹配结果
        """
        from digital_brochure_api import find_matches

        matches = find_matches(user_id=1, limit=10)
        assert isinstance(matches, list)
        if matches:
            assert "matched_user_id" in matches[0]
            assert "match_score" in matches[0]
            assert "match_reason" in matches[0]
            # 应按分数降序
            scores = [m["match_score"] for m in matches]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.skip(reason="匹配引擎功能尚未实现")
    def test_recommend_connections(self, test_db, sample_user_data, second_user):
        """应能基于信任网络推荐新连接"""
        from digital_brochure_api import recommend_connections

        # 先创建信任网络
        conn = test_db
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO trust_network (user_id, target_user_id, trust_level)
               VALUES (?, ?, 3)""",
            (sample_user_data["profile_id"], second_user["profile_id"]),
        )
        # 创建第三用户
        cursor.execute(
            """INSERT INTO auth_users (username, password_hash, is_active)
               VALUES ('third', '$2b$12$dummy', 1)"""
        )
        third_auth_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO users (auth_user_id, name, company)
               VALUES (?, '第三用户', '第三公司')""",
            (third_auth_id,),
        )
        third_profile_id = cursor.lastrowid

        # second_user 信任 third_user
        cursor.execute(
            """INSERT INTO trust_network (user_id, target_user_id, trust_level)
               VALUES (?, ?, 3)""",
            (second_user["profile_id"], third_profile_id),
        )
        conn.commit()

        # 推荐应为 sample_user 推荐 third_user (通过 second_user 的二度连接)
        recommendations = recommend_connections(sample_user_data["profile_id"])
        recommended_ids = [r["user_id"] for r in recommendations]
        assert third_profile_id in recommended_ids

    @pytest.mark.skip(reason="匹配引擎功能尚未实现")
    def test_match_score_calculation(self):
        """匹配分数应基于多维因素计算

        分数计算应考虑:
        - 信任等级 (权重高)
        - 行业相关度
        - 供需匹配度
        - 地理位置接近度
        """
        from digital_brochure_api import calculate_match_score

        score = calculate_match_score(
            user_id=1,
            target_user_id=2,
            trust_level=3,
            industry_overlap=0.8,
            supply_demand_match=True,
        )
        assert 0 <= score <= 1.0
        assert score > 0.5  # 高信任 + 高相关度应给高分

        # 低信任 + 低相关度应给低分
        low_score = calculate_match_score(
            user_id=1,
            target_user_id=2,
            trust_level=0,
            industry_overlap=0.1,
            supply_demand_match=False,
        )
        assert low_score < 0.3

    @pytest.mark.skip(reason="匹配引擎功能尚未实现")
    def test_confirm_match(self, client, auth_headers):
        """应能确认匹配并建立联系"""
        resp = client.post(
            "/api/v1/digital-brochure/matches/1/confirm",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "匹配已确认"

    @pytest.mark.skip(reason="匹配引擎功能尚未实现")
    def test_get_match_history(self, client, auth_headers):
        """应能查询匹配历史"""
        resp = client.get("/api/v1/digital-brochure/matches", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["data"], list)
