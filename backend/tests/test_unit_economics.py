"""
单位经济仪表盘 (unit_economics.py) 测试
==========================================
覆盖：成本管理、收入管理、计算引擎、仪表盘、渠道分析
"""

import pytest


class TestCostManagement:
    """成本条目管理"""

    BASE = "/api/unit-economics/costs"

    def test_list_costs_default(self, client, reset_unit_economics):
        """获取默认成本列表 — 5 条预设"""
        resp = client.get(self.BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert "total_amount" in data
        assert data["total_amount"] > 0

    def test_list_costs_filter_period(self, client, reset_unit_economics):
        """按月份筛选成本"""
        resp = client.get(self.BASE, params={"period": "2026-06"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 5

        resp2 = client.get(self.BASE, params={"period": "2026-07"})
        assert resp2.status_code == 200
        assert resp2.json()["total"] == 0

    def test_list_costs_filter_category(self, client, reset_unit_economics):
        """按分类筛选成本"""
        resp = client.get(self.BASE, params={"category": "市场推广"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_create_cost(self, client, reset_unit_economics):
        """录入成本条目"""
        payload = {
            "name": "测试成本",
            "category": "其他",
            "amount": 1000.0,
            "period": "2026-07",
        }
        resp = client.post(self.BASE, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 6

        # 总数增加
        assert client.get(self.BASE).json()["total"] == 6

    def test_create_cost_missing_field(self, client, reset_unit_economics):
        """录入成本 — 缺少必填字段"""
        resp = client.post(self.BASE, json={"category": "x"})
        assert resp.status_code == 422

    def test_delete_cost_ok(self, client, reset_unit_economics):
        """删除成本条目"""
        resp = client.delete(f"{self.BASE}/1")
        assert resp.status_code == 200
        assert "删除成功" in resp.json()["message"]
        assert client.get(self.BASE).json()["total"] == 4

    def test_delete_cost_not_found(self, client, reset_unit_economics):
        """删除不存在的成本"""
        resp = client.delete(f"{self.BASE}/999")
        assert resp.status_code == 404


class TestRevenueManagement:
    """收入条目管理"""

    BASE = "/api/unit-economics/revenues"

    def test_list_revenues_default(self, client, reset_unit_economics):
        """获取默认收入列表 — 8 条"""
        resp = client.get(self.BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 8
        assert "total_revenue" in data

    def test_list_revenues_filter_channel(self, client, reset_unit_economics):
        """按渠道筛选收入"""
        resp = client.get(self.BASE, params={"channel": "线上"})
        assert resp.status_code == 200
        assert resp.json()["total"] >= 3

    def test_create_revenue(self, client, reset_unit_economics):
        """录入收入条目"""
        payload = {
            "customer_id": "C009",
            "customer_name": "测试客户",
            "plan": "专业版",
            "revenue": 5000.0,
            "period": "2026-07",
        }
        resp = client.post(self.BASE, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 9


class TestEconomicsCalculation:
    """单位经济计算"""

    BASE = "/api/unit-economics"

    def test_calculate_period(self, client, reset_unit_economics):
        """计算指定月份的单位经济指标"""
        resp = client.get(f"{self.BASE}/calculate/2026-06")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "2026-06"
        assert data["cac"] > 0
        assert data["ltv"] > 0
        assert data["ltv_cac_ratio"] > 0
        assert data["new_customers"] == 8

    def test_calculate_empty_period(self, client, reset_unit_economics):
        """计算无数据的月份 — 应返回零值指标"""
        resp = client.get(f"{self.BASE}/calculate/2026-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cac"] == 0.0
        assert data["new_customers"] == 0

    def test_dashboard_default(self, client, reset_unit_economics):
        """获取仪表盘 — 使用默认月份"""
        resp = client.get(f"{self.BASE}/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "2026-06"
        assert "snapshot" in data
        assert "health_score" in data
        assert "warnings" in data
        assert "recommendations" in data

    def test_dashboard_with_period(self, client, reset_unit_economics):
        """获取指定月份仪表盘"""
        resp = client.get(f"{self.BASE}/dashboard", params={"period": "2026-06"})
        assert resp.status_code == 200
        assert resp.json()["period"] == "2026-06"

    def test_dashboard_calculates_on_the_fly(self, client, reset_unit_economics):
        """当请求的月份无快照时，动态计算"""
        resp = client.get(f"{self.BASE}/dashboard", params={"period": "2026-05"})
        assert resp.status_code == 200
        assert resp.json()["period"] == "2026-05"

    def test_channel_economics(self, client, reset_unit_economics):
        """获取渠道经济分析 — 按 ROI 降序"""
        resp = client.get(f"{self.BASE}/channels")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        # 验证按 ROI 降序排列
        rois = [c["roi"] for c in data["channels"]]
        assert rois == sorted(rois, reverse=True)

    def test_channel_economics_filter(self, client, reset_unit_economics):
        """按月份筛选渠道经济"""
        resp = client.get(f"{self.BASE}/channels", params={"period": "2026-06"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 4

    def test_trend(self, client, reset_unit_economics):
        """获取单位经济趋势"""
        resp = client.get(f"{self.BASE}/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert "snapshots" in data
        assert "periods" in data

    def test_health_score_calculation(self, client, reset_unit_economics):
        """验证健康评分 — 预设数据应产生 良好 级别"""
        resp = client.get(f"{self.BASE}/dashboard")
        hs = resp.json()["health_score"]
        assert 0 <= hs["score"] <= 100
        assert hs["level"] in ("优秀", "良好", "警告", "危险")
