"""
留存分析引擎 (retention_insights.py) 测试
===========================================
覆盖：Cohort 管理、留存矩阵、用户活跃度、流失信号、留存策略、总览
"""

import pytest


class TestCohortManagement:
    """Cohort 管理"""

    COHORTS_URL = "/api/retention/cohorts"

    def test_list_cohorts(self, client, reset_retention_insights):
        """获取 Cohort 列表 — 4 个预设"""
        resp = client.get(self.COHORTS_URL)
        assert resp.status_code == 200
        assert resp.json()["total"] == 4

    def test_create_cohort(self, client, reset_retention_insights):
        """创建 Cohort"""
        payload = {
            "name": "2026年7月获客群",
            "period": "2026-07",
            "user_count": 50,
            "source": "线上",
        }
        resp = client.post(self.COHORTS_URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 5


class TestRetentionMatrix:
    """留存数据"""

    def test_get_cohort_retention_cached(self, client, reset_retention_insights):
        """获取已有缓存的 Cohort 留存数据"""
        resp = client.get("/api/retention/cohorts/1/retention")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cohort_id"] == 1
        assert len(data["retention"]) > 0

    def test_get_cohort_retention_not_found(self, client, reset_retention_insights):
        """获取不存在的 Cohort 留存数据 — 404"""
        resp = client.get("/api/retention/cohorts/999/retention")
        assert resp.status_code == 404

    def test_get_retention_matrix(self, client, reset_retention_insights):
        """获取完整留存矩阵"""
        resp = client.get("/api/retention/retention-matrix")
        assert resp.status_code == 200
        data = resp.json()
        assert "matrix" in data
        assert len(data["matrix"]) == 4
        for entry in data["matrix"]:
            assert "cohort" in entry
            assert "retention" in entry


class TestUserActivity:
    """用户活跃度"""

    ACTIVITIES_URL = "/api/retention/activities"

    def test_list_activities(self, client, reset_retention_insights):
        """获取用户活跃记录"""
        resp = client.get(self.ACTIVITIES_URL)
        assert resp.status_code == 200
        assert resp.json()["total"] == 5

    def test_list_activities_filter_cohort(self, client, reset_retention_insights):
        """按 Cohort 月份筛选"""
        resp = client.get(self.ACTIVITIES_URL, params={"cohort_period": "2026-03"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_activities_active_only(self, client, reset_retention_insights):
        """仅筛选活跃用户"""
        resp = client.get(self.ACTIVITIES_URL, params={"active_only": True})
        assert resp.status_code == 200
        for a in resp.json()["activities"]:
            assert a["is_active"] is True

    def test_record_activity(self, client, reset_retention_insights):
        """记录用户活跃"""
        payload = {
            "user_id": "U010",
            "username": "测试用户",
            "cohort_period": "2026-06",
            "activity_period": "2026-07",
            "actions": 10,
            "is_active": True,
        }
        resp = client.post(self.ACTIVITIES_URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 6


class TestChurnSignals:
    """流失信号"""

    SIGNALS_URL = "/api/retention/churn-signals"

    def test_list_churn_signals(self, client, reset_retention_insights):
        """获取流失信号列表 — 3 个预设"""
        resp = client.get(self.SIGNALS_URL)
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_list_churn_signals_filter_severity(self, client, reset_retention_insights):
        """按严重程度筛选"""
        resp = client.get(self.SIGNALS_URL, params={"severity": "高"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_create_churn_signal(self, client, reset_retention_insights):
        """创建流失信号"""
        payload = {
            "user_id": "U010",
            "username": "测试用户",
            "signal_type": "inactivity",
            "severity": "中",
            "description": "超过15天未活跃",
            "days_since_last_active": 18,
            "recommended_action": "推送召回通知",
        }
        resp = client.post(self.SIGNALS_URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 4

    def test_resolve_churn_signal(self, client, reset_retention_insights):
        """解决流失信号"""
        resp = client.put(f"{self.SIGNALS_URL}/1/resolve")
        assert resp.status_code == 200
        assert "已解决" in resp.json()["message"]

    def test_resolve_churn_signal_not_found(self, client, reset_retention_insights):
        """解决不存在的流失信号 — 404"""
        resp = client.put(f"{self.SIGNALS_URL}/999/resolve")
        assert resp.status_code == 404


class TestRetentionStrategies:
    """留存策略"""

    STRATEGIES_URL = "/api/retention/strategies"

    def test_list_strategies(self, client, reset_retention_insights):
        """获取留存策略列表 — 3 条"""
        resp = client.get(self.STRATEGIES_URL)
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_list_strategies_filter_status(self, client, reset_retention_insights):
        """按状态筛选"""
        resp = client.get(self.STRATEGIES_URL, params={"status": "待实施"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_strategies_filter_priority(self, client, reset_retention_insights):
        """按优先级筛选"""
        resp = client.get(self.STRATEGIES_URL, params={"priority": "高"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2


class TestRetentionOverview:
    """留存分析总览"""

    def test_overview(self, client, reset_retention_insights):
        """获取留存分析总览"""
        resp = client.get("/api/retention/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cohorts"] == 4
        assert 0 <= data["avg_month1_retention"] <= 1
        assert data["active_churn_signals"] >= 0
        assert data["trend"] in ("up", "stable", "declining")
