"""
深度复盘看板 (retro_board.py) 测试
====================================
覆盖：F1-F9 阶段定义、看板 CRUD、复盘条目 CRUD、行动项 CRUD、
阶段推进、进度更新、看板统计
"""

import pytest


class TestStages:
    """F1-F9 阶段定义"""

    def test_get_stages(self, client):
        """获取 F1-F9 阶段定义"""
        resp = client.get("/api/retro/stages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 9
        assert "F1" in data["stages"]
        assert "F9" in data["stages"]
        assert data["flow"] == ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"]


class TestBoardCRUD:
    """复盘看板 CRUD"""

    BOARDS_URL = "/api/retro/boards"

    def test_list_boards(self, client, reset_retro_board):
        """获取看板列表 — 2 个预设"""
        resp = client.get(self.BOARDS_URL)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_boards_filter_status(self, client, reset_retro_board):
        """按状态筛选"""
        resp = client.get(self.BOARDS_URL, params={"status": "进行中"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_boards_filter_project(self, client, reset_retro_board):
        """按项目筛选"""
        resp = client.get(self.BOARDS_URL, params={"project": "链客宝"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_create_board(self, client, reset_retro_board):
        """创建复盘看板 — 默认 F1 阶段"""
        payload = {
            "title": "测试复盘",
            "project": "测试项目",
            "period": "2026-W28",
            "facilitator": "测试员",
            "participants": ["A", "B"],
        }
        resp = client.post(self.BOARDS_URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 3

        # 验证默认阶段为 F1
        board = client.get(f"{self.BOARDS_URL}/3").json()
        assert board["stage"].startswith("F1")

    def test_get_board_ok(self, client, reset_retro_board):
        """获取看板详情"""
        resp = client.get(f"{self.BOARDS_URL}/1")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_get_board_not_found(self, client, reset_retro_board):
        """获取不存在的看板 — 404"""
        resp = client.get(f"{self.BOARDS_URL}/999")
        assert resp.status_code == 404

    def test_delete_board_ok(self, client, reset_retro_board):
        """删除看板"""
        resp = client.delete(f"{self.BOARDS_URL}/1")
        assert resp.status_code == 200
        assert "删除成功" in resp.json()["message"]

    def test_delete_board_not_found(self, client, reset_retro_board):
        """删除不存在的看板 — 404"""
        resp = client.delete(f"{self.BOARDS_URL}/999")
        assert resp.status_code == 404


class TestStageAdvancement:
    """阶段推进"""

    STAGE_URL = "/api/retro/boards"

    def test_advance_stage(self, client, reset_retro_board):
        """推进到 F2"""
        resp = client.put(f"{self.STAGE_URL}/1/stage", params={"stage": "F2-结果评估"})
        assert resp.status_code == 200
        data = resp.json()
        assert "已推进到" in data["message"]
        assert data["board"]["stage"].startswith("F2")

    def test_advance_to_invalid_stage(self, client, reset_retro_board):
        """推进到无效阶段 — 400"""
        resp = client.put(
            f"{self.STAGE_URL}/1/stage", params={"stage": "F99-不存在"}
        )
        assert resp.status_code == 400
        assert "无效" in resp.json()["detail"]

    def test_advance_to_f9_marks_complete(self, client, reset_retro_board):
        """推进到 F9 时自动标记为已完成"""
        resp = client.put(f"{self.STAGE_URL}/1/stage", params={"stage": "F9-下一步行动"})
        assert resp.status_code == 200
        board = resp.json()["board"]
        assert board["status"] == "已完成"

    def test_advance_on_nonexistent_board(self, client, reset_retro_board):
        """推进不存在的看板 — 404"""
        resp = client.put(
            f"{self.STAGE_URL}/999/stage", params={"stage": "F2-结果评估"}
        )
        assert resp.status_code == 404


class TestRetroItem:
    """复盘条目"""

    ITEMS_URL = "/api/retro/items"

    def test_list_items(self, client, reset_retro_board):
        """获取看板的复盘条目"""
        resp = client.get(f"{self.ITEMS_URL}/1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 5

    def test_list_items_filter_stage(self, client, reset_retro_board):
        """按阶段筛选"""
        resp = client.get("/api/retro/items/1", params={"stage": "F3"})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["stage"] == "F3"

    def test_create_item(self, client, reset_retro_board):
        """创建复盘条目"""
        payload = {
            "board_id": 1,
            "stage": "F5",
            "category": "根因",
            "content": "测试根因分析",
            "author": "测试员",
            "priority": "高",
        }
        resp = client.post(self.ITEMS_URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 8

    def test_update_item(self, client, reset_retro_board):
        """更新复盘条目"""
        payload = {
            "board_id": 1,
            "stage": "F3",
            "category": "亮点",
            "content": "已更新内容",
            "author": "测试员",
        }
        resp = client.put(f"{self.ITEMS_URL}/1", json=payload)
        assert resp.status_code == 200
        assert "更新成功" in resp.json()["message"]

    def test_update_item_not_found(self, client, reset_retro_board):
        """更新不存在的条目 — 404"""
        resp = client.put(
            f"{self.ITEMS_URL}/999",
            json={
                "board_id": 1,
                "stage": "F3",
                "category": "x",
                "content": "x",
            },
        )
        assert resp.status_code == 404

    def test_delete_item(self, client, reset_retro_board):
        """删除复盘条目"""
        resp = client.delete(f"{self.ITEMS_URL}/1")
        assert resp.status_code == 200

    def test_delete_item_not_found(self, client, reset_retro_board):
        """删除不存在的条目 — 404"""
        resp = client.delete(f"{self.ITEMS_URL}/999")
        assert resp.status_code == 404


class TestActionItem:
    """行动项"""

    ACTIONS_URL = "/api/retro/actions"

    def test_list_actions(self, client, reset_retro_board):
        """获取看板的行动项"""
        resp = client.get(f"{self.ACTIONS_URL}/1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_list_actions_filter_status(self, client, reset_retro_board):
        """按状态筛选"""
        resp = client.get("/api/retro/actions/1", params={"status": "待开始"})
        assert resp.status_code == 200
        for a in resp.json()["actions"]:
            assert a["status"] == "待开始"

    def test_create_action(self, client, reset_retro_board):
        """创建行动项"""
        payload = {
            "board_id": 1,
            "title": "测试行动",
            "description": "测试",
            "owner": "测试员",
            "priority": "高",
        }
        resp = client.post(self.ACTIONS_URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 5

    def test_update_action(self, client, reset_retro_board):
        """更新行动项"""
        payload = {
            "board_id": 1,
            "title": "已更新行动",
            "description": "更新测试",
            "owner": "测试员",
            "priority": "中",
            "status": "进行中",
        }
        resp = client.put(f"{self.ACTIONS_URL}/1", json=payload)
        assert resp.status_code == 200
        assert "更新成功" in resp.json()["message"]

    def test_update_action_progress(self, client, reset_retro_board):
        """更新行动项进度"""
        resp = client.put(f"{self.ACTIONS_URL}/1/progress", params={"progress": 80})
        assert resp.status_code == 200
        assert resp.json()["progress"] == 80

    def test_update_action_progress_complete(self, client, reset_retro_board):
        """进度 100 时自动完成"""
        resp = client.put(f"{self.ACTIONS_URL}/1/progress", params={"progress": 100})
        assert resp.status_code == 200

        # 验证状态
        actions = client.get(f"{self.ACTIONS_URL}/1").json()["actions"]
        target = [a for a in actions if a["id"] == 1][0]
        assert target["status"] == "已完成"

    def test_update_action_progress_invalid(self, client, reset_retro_board):
        """进度值越界 — 400"""
        resp = client.put(f"{self.ACTIONS_URL}/1/progress", params={"progress": -1})
        assert resp.status_code == 400

        resp2 = client.put(f"{self.ACTIONS_URL}/1/progress", params={"progress": 101})
        assert resp2.status_code == 400

    def test_update_action_not_found(self, client, reset_retro_board):
        """更新不存在的行动项 — 404"""
        resp = client.put(
            f"{self.ACTIONS_URL}/999",
            json={"board_id": 1, "title": "x", "owner": "x"},
        )
        assert resp.status_code == 404


class TestBoardSummary:
    """看板统计摘要"""

    def test_board_summary(self, client, reset_retro_board):
        """获取看板统计摘要"""
        resp = client.get("/api/retro/boards/1/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["board"]["id"] == 1
        assert data["total_items"] == 5
        assert data["total_actions"] == 3
        assert "stage_distribution" in data
        assert "action_completion_rate" in data

    def test_board_summary_not_found(self, client, reset_retro_board):
        """不存在的看板摘要 — 404"""
        resp = client.get("/api/retro/boards/999/summary")
        assert resp.status_code == 404
