"""
学习中心 (learning_center.py) 测试
====================================
覆盖：X1-X10 学习路径、课程 CRUD、模块管理、课时管理、
学习进度、AI 导师、认证管理、仪表盘
"""

import pytest


class TestLearningPath:
    """X1-X10 学习路径"""

    def test_get_learning_path(self, client):
        """获取学习路径定义 — 10 个阶段"""
        resp = client.get("/api/learning/path")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        codes = [p["code"] for p in data["path"]]
        assert codes == [f"X{i}" for i in range(1, 11)]


class TestCourseCRUD:
    """课程 CRUD"""

    BASE = "/api/learning/courses"

    def test_list_courses(self, client, reset_learning_center):
        """获取课程列表 — 预设 3 门"""
        resp = client.get(self.BASE)
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_list_courses_filter_category(self, client, reset_learning_center):
        """按分类筛选"""
        resp = client.get(self.BASE, params={"category": "销售技巧"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["courses"][0]["title"] == "B2B销售实战：从陌拜到成交"

    def test_list_courses_filter_level(self, client, reset_learning_center):
        """按级别筛选"""
        resp = client.get(self.BASE, params={"level": "初级"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_get_course_ok(self, client, reset_learning_center):
        """获取课程详情"""
        resp = client.get(f"{self.BASE}/1")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1
        assert resp.json()["title"] == "B2B销售实战：从陌拜到成交"

    def test_get_course_not_found(self, client, reset_learning_center):
        """获取不存在的课程 — 404"""
        resp = client.get(f"{self.BASE}/999")
        assert resp.status_code == 404

    def test_create_course(self, client, reset_learning_center):
        """创建课程"""
        payload = {
            "title": "测试课程",
            "description": "测试描述",
            "category": "数据分析",
            "level": "中级",
        }
        resp = client.post(self.BASE, json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 4


class TestModuleManagement:
    """模块管理"""

    def test_list_modules(self, client, reset_learning_center):
        """获取课程的所有模块 — 课程 1 有 5 个模块"""
        resp = client.get("/api/learning/courses/1/modules")
        assert resp.status_code == 200
        assert resp.json()["total"] == 5

    def test_list_modules_empty(self, client, reset_learning_center):
        """获取不存在课程的模块 — 空列表"""
        resp = client.get("/api/learning/courses/999/modules")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_create_module(self, client, reset_learning_center):
        """创建模块"""
        payload = {
            "course_id": 1,
            "module_code": "X6",
            "title": "实战任务",
            "description": "真实场景任务",
        }
        resp = client.post("/api/learning/modules", json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 9

        # 验证课程的模块计数已更新
        course = client.get("/api/learning/courses/1").json()
        assert course["modules_count"] >= 6


class TestLessonManagement:
    """课时管理"""

    def test_list_lessons(self, client, reset_learning_center):
        """获取模块的所有课时 — 模块 3 有 5 个课时"""
        resp = client.get("/api/learning/modules/3/lessons")
        assert resp.status_code == 200
        assert resp.json()["total"] == 5

    def test_create_lesson(self, client, reset_learning_center):
        """创建课时"""
        payload = {
            "module_id": 3,
            "title": "测试课时",
            "content": "课时内容",
            "content_type": "text",
            "order": 6,
        }
        resp = client.post("/api/learning/lessons", json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == 6


class TestLearningProgress:
    """学习进度"""

    PROGRESS_URL = "/api/learning/progress"

    def test_get_user_progress(self, client, reset_learning_center):
        """获取用户学习进度"""
        resp = client.get(f"{self.PROGRESS_URL}/U001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_get_user_progress_filter_course(self, client, reset_learning_center):
        """按课程筛选用户进度"""
        resp = client.get(f"{self.PROGRESS_URL}/U001", params={"course_id": 1})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["progresses"][0]["course_id"] == 1

    def test_update_progress_create_new(self, client, reset_learning_center):
        """创建新学习进度"""
        payload = {
            "user_id": "U999",
            "course_id": 1,
            "progress_pct": 10.0,
            "completed_lessons": 2,
            "total_lessons": 20,
        }
        resp = client.post(self.PROGRESS_URL, json=payload)
        assert resp.status_code == 200
        assert "创建" in resp.json()["message"]
        assert resp.json()["id"] == 4

    def test_update_progress_existing(self, client, reset_learning_center):
        """更新已有进度"""
        payload = {
            "user_id": "U001",
            "course_id": 1,
            "progress_pct": 80.0,
            "completed_lessons": 16,
            "total_lessons": 20,
        }
        resp = client.post(self.PROGRESS_URL, json=payload)
        assert resp.status_code == 200
        assert "更新" in resp.json()["message"]

    def test_update_progress_complete(self, client, reset_learning_center):
        """进度 100% 时自动标记为已完成"""
        payload = {
            "user_id": "U999",
            "course_id": 1,
            "progress_pct": 100.0,
            "completed_lessons": 20,
            "total_lessons": 20,
        }
        resp = client.post(self.PROGRESS_URL, json=payload)
        assert resp.status_code == 200

        # 验证状态
        progress = client.get(f"{self.PROGRESS_URL}/U999").json()["progresses"][0]
        assert progress["status"] == "已完成"


class TestAiTutor:
    """AI 导师"""

    TUTOR_URL = "/api/learning/tutor"

    def test_get_tutor_history_empty(self, client, reset_learning_center):
        """获取 AI 导师对话历史 — 新用户应返回空列表"""
        resp = client.get(f"{self.TUTOR_URL}/U999/1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_ask_tutor(self, client, reset_learning_center):
        """向 AI 导师提问 — 返回模拟回复"""
        payload = {
            "user_id": "U001",
            "course_id": 1,
            "role": "user",
            "content": "请问ABACC框架怎么用？",
        }
        resp = client.post(f"{self.TUTOR_URL}/ask", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "user_message" in data
        assert "ai_reply" in data
        assert data["ai_reply"]["role"] == "assistant"
        assert len(data["ai_reply"]["content"]) > 0

    def test_ask_tutor_stores_message(self, client, reset_learning_center):
        """提问后对话历史应增加"""
        client.post(
            f"{self.TUTOR_URL}/ask",
            json={"user_id": "U001", "course_id": 1, "role": "user", "content": "你好"},
        )
        resp = client.get(f"{self.TUTOR_URL}/U001/1")
        assert resp.json()["total"] == 2  # user + assistant


class TestCertification:
    """认证管理"""

    CERT_URL = "/api/learning/certifications"

    def test_get_user_certifications(self, client, reset_learning_center):
        """获取用户认证记录"""
        resp = client.get(f"{self.CERT_URL}/U001")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_issue_certification_passed(self, client, reset_learning_center):
        """颁发认证 — 通过"""
        payload = {
            "user_id": "U003",
            "user_name": "测试用户",
            "course_id": 1,
            "course_title": "B2B销售实战",
            "score": 85.0,
            "passed": True,
        }
        resp = client.post(self.CERT_URL, json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is True
        assert "认证成功" in data["message"]

        # 验证学习进度状态更新
        progress = client.get("/api/learning/progress/U003").json()["progresses"][0]
        assert progress["status"] == "已认证"

    def test_issue_certification_failed(self, client, reset_learning_center):
        """颁发认证 — 未通过（分数 < 70）"""
        payload = {
            "user_id": "U003",
            "user_name": "测试用户",
            "course_id": 1,
            "course_title": "B2B销售实战",
            "score": 50.0,
            "passed": False,
        }
        resp = client.post(self.CERT_URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["passed"] is False
        assert "未通过" in resp.json()["message"]


class TestDashboard:
    """学习仪表盘"""

    def test_dashboard_stats(self, client, reset_learning_center):
        """获取用户学习仪表盘"""
        resp = client.get("/api/learning/dashboard/U001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "U001"
        assert data["total_courses"] == 2
        assert data["completed_courses"] == 1
        assert data["in_progress"] == 1
        assert data["total_learning_time_minutes"] >= 0
        assert "next_stage" in data
        assert len(data["recommended_courses"]) >= 0

    def test_dashboard_new_user(self, client, reset_learning_center):
        """新用户仪表盘 — 无课程"""
        resp = client.get("/api/learning/dashboard/U999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_courses"] == 0
        assert data["avg_completion_rate"] == 0.0
        assert len(data["recommended_courses"]) == 3
