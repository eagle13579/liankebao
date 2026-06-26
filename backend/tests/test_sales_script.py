"""
销售话术模板引擎 (sales_script.py) 测试
=========================================
覆盖：ABACC 预设模板 CRUD、张力武器库、张力评分分析
"""

import pytest


class TestPresets:
    """ABACC 预设模板"""

    BASE = "/api/sales-script/presets"

    def test_list_presets(self, client, reset_sales_script):
        """获取预设模板列表 — 2 套"""
        resp = client.get(self.BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["presets"]) == 2

    def test_get_preset_ok(self, client, reset_sales_script):
        """获取单个模板详情"""
        resp = client.get(f"{self.BASE}/1")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1
        assert "abacc" in resp.json()
        assert len(resp.json()["abacc"]) == 5  # ABACC 五步

    def test_get_preset_not_found(self, client, reset_sales_script):
        """获取不存在的模板 — 404"""
        resp = client.get(f"{self.BASE}/999")
        assert resp.status_code == 404


class TestScriptCRUD:
    """话术模板自定义 CRUD"""

    SCRIPTS = "/api/sales-script/scripts"

    def test_create_script(self, client, reset_sales_script):
        """创建自定义话术模板"""
        payload = {
            "name": "测试话术",
            "scenario": "电销",
            "target_role": "CEO",
            "abacc": [
                {
                    "step_id": "attention",
                    "title": "开场",
                    "template": "您好，我是链客宝的...",
                }
            ],
        }
        resp = client.post(self.SCRIPTS, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 3

        # 总数应增加
        assert client.get("/api/sales-script/presets").json()["total"] == 3

    def test_update_script_ok(self, client, reset_sales_script):
        """更新话术模板"""
        payload = {
            "name": "已更新",
            "scenario": "展会",
            "target_role": "市场总监",
            "abacc": [],
        }
        resp = client.put(f"{self.SCRIPTS}/1", json=payload)
        assert resp.status_code == 200
        assert "更新成功" in resp.json()["message"]

    def test_update_script_not_found(self, client, reset_sales_script):
        """更新不存在的模板 — 404"""
        resp = client.put(
            f"{self.SCRIPTS}/999",
            json={"name": "x", "scenario": "x", "target_role": "x", "abacc": []},
        )
        assert resp.status_code == 404

    def test_delete_script_ok(self, client, reset_sales_script):
        """删除话术模板"""
        resp = client.delete(f"{self.SCRIPTS}/1")
        assert resp.status_code == 200
        assert "删除成功" in resp.json()["message"]

    def test_delete_script_not_found(self, client, reset_sales_script):
        """删除不存在的模板 — 404"""
        resp = client.delete(f"{self.SCRIPTS}/999")
        assert resp.status_code == 404


class TestTensionWeapons:
    """张力武器库"""

    DATA_AUG = "/api/sales-script/weapons/data-augmenter"
    MAGIC_WORDS = "/api/sales-script/weapons/magic-words"
    TENSION_CHECK = "/api/sales-script/weapons/tension-check"
    ANALYZE = "/api/sales-script/weapons/analyze"

    def test_data_augmenter_all(self, client):
        """获取所有数据增强器模式"""
        resp = client.get(self.DATA_AUG)
        assert resp.status_code == 200
        data = resp.json()
        assert "analogy" in data
        assert "unit_transform" in data
        assert "comparison" in data

    def test_data_augmenter_by_mode(self, client):
        """按模式筛选数据增强器"""
        resp = client.get(self.DATA_AUG, params={"mode": "analogy"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "analogy"

    def test_magic_words_all(self, client):
        """获取所有话术引导词"""
        resp = client.get(self.MAGIC_WORDS)
        assert resp.status_code == 200
        data = resp.json()
        assert "urgency" in data
        assert "social_proof" in data

    def test_magic_words_by_category(self, client):
        """按分类筛选引导词"""
        resp = client.get(self.MAGIC_WORDS, params={"category": "urgency"})
        assert resp.status_code == 200
        assert resp.json()["category"] == "urgency"
        assert "words" in resp.json()["data"]

    def test_tension_check_all(self, client):
        """获取所有张力自检标准"""
        resp = client.get(self.TENSION_CHECK)
        assert resp.status_code == 200
        data = resp.json()
        assert "low" in data
        assert "medium" in data
        assert "high" in data

    def test_tension_check_by_score_low(self, client):
        """按分数查询 — 低张力"""
        resp = client.get(self.TENSION_CHECK, params={"score": 20})
        assert resp.status_code == 200
        assert resp.json()["level"] == "low"

    def test_tension_check_by_score_medium(self, client):
        """按分数查询 — 中张力"""
        resp = client.get(self.TENSION_CHECK, params={"score": 55})
        assert resp.status_code == 200
        assert resp.json()["level"] == "medium"

    def test_tension_check_by_score_high(self, client):
        """按分数查询 — 高张力"""
        resp = client.get(self.TENSION_CHECK, params={"score": 85})
        assert resp.status_code == 200
        assert resp.json()["level"] == "high"


class TestTensionAnalysis:
    """话术张力分析"""

    ANALYZE = "/api/sales-script/weapons/analyze"

    def test_analyze_high_tension(self, client):
        """分析高张力话术"""
        text = (
            "通过对比传统方式，我们实现了300%的效率提升，"
            "每年节省2000小时。立即扫码注册体验吧！"
        )
        resp = client.post(self.ANALYZE, params={"text": text})
        assert resp.status_code == 200
        data = resp.json()
        assert 0 <= data["score"] <= 100
        assert data["level"] in ("low", "medium", "high")
        assert "label" in data
        assert "fixes" in data

    def test_analyze_low_tension(self, client):
        """分析低张力话术 — 无数字无对比无行动号召"""
        text = "我们的产品很好，您要不要考虑一下。"
        resp = client.post(self.ANALYZE, params={"text": text})
        assert resp.status_code == 200
        data = resp.json()
        # 基准分50，不加分，应接近50
        assert data["score"] <= 60

    def test_analyze_empty_text(self, client):
        """分析空文本 — 应返回基准分"""
        resp = client.post(self.ANALYZE, params={"text": ""})
        assert resp.status_code == 200
        assert resp.json()["score"] == 50

    def test_analyze_full_score_text(self, client):
        """分析满分配置的话术 — 应接近 100"""
        text = (
            "对比传统方案，我们的产品效率提升300%，每年节省100万元成本。"
            "您是否也面临获客成本高的痛点？想象一下，使用我们的系统后，"
            "相当于每个月多赚10万元，同行TOP企业已经在用了。"
            "限时优惠，立即扫码注册体验吧！"
        )
        resp = client.post(self.ANALYZE, params={"text": text})
        assert resp.status_code == 200
        assert resp.json()["score"] >= 80
