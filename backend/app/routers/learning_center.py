"""
链客宝 - X1-X10 学习中心
==============================
X1: AI导师 → X10: 认证考核 全链路学习平台

注入点：课程CRUD + 模块管理 + 学习进度追踪 + AI导师问答 + 考核认证
规则：纯新增，不修改现有业务逻辑
"""

from datetime import datetime

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class Course(BaseModel):
    """课程"""

    id: int | None = None
    title: str
    description: str
    category: str  # 销售技巧/产品使用/行业知识/管理能力/数据分析
    level: str = "初级"  # 初级/中级/高级
    duration_minutes: int = 0  # 总时长（分钟）
    modules_count: int = 0
    instructor: str = ""
    thumbnail: str = ""
    tags: list[str] = []
    rating: float = 0.0
    enrolled_count: int = 0
    completion_rate: float = 0.0
    status: str = "上架"  # 上架/下架/草稿
    created_at: str = ""
    updated_at: str = ""


class Module(BaseModel):
    """课程模块（X1-X10中的某个阶段）"""

    id: int | None = None
    course_id: int
    module_code: str  # X1, X2, ..., X10
    title: str
    description: str
    content_type: str = "video"  # video / article / quiz / interactive / case
    content_url: str = ""
    duration_minutes: int = 0
    order: int = 0
    is_required: bool = True
    created_at: str = ""


class Lesson(BaseModel):
    """课时（模块下的最小学习单元）"""

    id: int | None = None
    module_id: int
    title: str
    content: str = ""
    content_type: str = "text"  # text / video / quiz / exercise
    content_url: str = ""
    duration_minutes: int = 0
    order: int = 0
    quiz_questions: list[dict] = []  # 如果是测验类型
    created_at: str = ""


class LearningProgress(BaseModel):
    """学习进度"""

    id: int | None = None
    user_id: str
    course_id: int
    module_id: int | None = None
    lesson_id: int | None = None
    progress_pct: float = 0.0  # 0-100
    completed_lessons: int = 0
    total_lessons: int = 0
    time_spent_minutes: int = 0
    quiz_score: float | None = None  # 测验得分 0-100
    status: str = "未开始"  # 未开始/学习中/已完成/已认证
    last_accessed_at: str = ""
    started_at: str = ""
    completed_at: str = ""


class AiTutorMessage(BaseModel):
    """AI导师对话记录"""

    id: int | None = None
    user_id: str
    course_id: int
    module_id: int | None = None
    role: str  # user / assistant
    content: str
    context: str = ""
    created_at: str = ""


class Certification(BaseModel):
    """认证记录"""

    id: int | None = None
    user_id: str
    user_name: str = ""
    course_id: int
    course_title: str = ""
    score: float
    passed: bool
    certificate_url: str = ""
    issued_at: str = ""
    expires_at: str = ""
    skills: list[str] = []


# ---------------------------------------------------------------------------
# X1-X10 学习路径定义
# ---------------------------------------------------------------------------

LEARNING_PATH = [
    {"code": "X1", "name": "AI导师引导", "description": "AI导师根据用户角色和目标推荐个性化学习路径", "icon": "🤖"},
    {"code": "X2", "name": "认知诊断", "description": "前置测评评估当前知识水平，定位能力缺口", "icon": "📋"},
    {"code": "X3", "name": "核心知识", "description": "系统学习核心知识点和理论框架", "icon": "📚"},
    {"code": "X4", "name": "案例教学", "description": "真实业务案例分析，理论与实际结合", "icon": "🔬"},
    {"code": "X5", "name": "模拟练习", "description": "沙盘模拟和角色扮演，在安全环境练习", "icon": "🎮"},
    {"code": "X6", "name": "实战任务", "description": "真实业务场景任务，产出可量化成果", "icon": "⚔️"},
    {"code": "X7", "name": "同伴互评", "description": "学习社区互评互学，获得多元化反馈", "icon": "👥"},
    {"code": "X8", "name": "导师反馈", "description": "资深导师1对1点评指导，针对性提升", "icon": "👨‍🏫"},
    {"code": "X9", "name": "复盘总结", "description": "学习成果复盘，知识体系梳理沉淀", "icon": "📝"},
    {"code": "X10", "name": "认证考核", "description": "综合考核评估，通过颁发链客宝认证", "icon": "🎓"},
]

# ---------------------------------------------------------------------------
# 内存存储（可替换为数据库）
# ---------------------------------------------------------------------------

COURSES: list[Course] = [
    Course(
        id=1,
        title="B2B销售实战：从陌拜到成交",
        description="系统化掌握B2B销售全流程，包含ABACC话术框架、客户心理学、谈判技巧等核心能力",
        category="销售技巧",
        level="中级",
        duration_minutes=480,
        modules_count=10,
        instructor="陈睿",
        tags=["B2B", "销售", "话术", "ABACC"],
        rating=4.7,
        enrolled_count=128,
        completion_rate=0.68,
        status="上架",
        created_at="2026-05-01T08:00:00Z",
    ),
    Course(
        id=2,
        title="链客宝产品专家认证",
        description="全面掌握链客宝所有功能模块，成为产品专家并获得官方认证",
        category="产品使用",
        level="初级",
        duration_minutes=360,
        modules_count=8,
        instructor="王芳",
        tags=["产品", "认证", "入门"],
        rating=4.5,
        enrolled_count=256,
        completion_rate=0.45,
        status="上架",
        created_at="2026-05-15T10:00:00Z",
    ),
    Course(
        id=3,
        title="AI获客引擎深度训练",
        description="深入理解AI供需匹配原理，掌握数据驱动获客方法",
        category="数据分析",
        level="高级",
        duration_minutes=600,
        modules_count=12,
        instructor="张明",
        tags=["AI", "获客", "数据分析", "高级"],
        rating=4.9,
        enrolled_count=67,
        completion_rate=0.32,
        status="上架",
        created_at="2026-06-01T09:00:00Z",
    ),
]

MODULES: list[Module] = [
    Module(
        id=1,
        course_id=1,
        module_code="X1",
        title="AI导师路径规划",
        description="AI根据您的销售经验和目标定制学习路径",
        content_type="interactive",
        order=1,
    ),
    Module(
        id=2,
        course_id=1,
        module_code="X2",
        title="销售能力诊断",
        description="30分钟前置测评，评估您的销售能力基线",
        content_type="quiz",
        order=2,
    ),
    Module(
        id=3,
        course_id=1,
        module_code="X3",
        title="ABACC五步说服框架",
        description="深入掌握注意→痛点→改变→好奇→行动的完整话术框架",
        content_type="video",
        order=3,
    ),
    Module(
        id=4,
        course_id=1,
        module_code="X4",
        title="B2B成交案例拆解",
        description="分析5个真实B2B成交案例，理解ABACC的实际应用",
        content_type="case",
        order=4,
    ),
    Module(
        id=5,
        course_id=1,
        module_code="X5",
        title="模拟客户对话",
        description="AI模拟客户角色，进行真实销售对话练习",
        content_type="interactive",
        order=5,
    ),
    Module(
        id=6,
        course_id=2,
        module_code="X1",
        title="产品全景认知",
        description="链客宝产品体系总览：获客→匹配→转化→服务全链路",
        content_type="video",
        order=1,
    ),
    Module(
        id=7,
        course_id=2,
        module_code="X3",
        title="核心功能实操",
        description="手把手教学：AI名片、供需匹配、人脉管理、数据看板",
        content_type="video",
        order=2,
    ),
    Module(
        id=8,
        course_id=3,
        module_code="X3",
        title="AI匹配算法原理",
        description="深入理解协同过滤+知识图谱的匹配机制",
        content_type="video",
        order=1,
    ),
]

LESSONS: list[Lesson] = [
    Lesson(
        id=1,
        module_id=3,
        title="Attention：3秒建立信任的开场",
        content="在B2B销售中，第一句话决定了客户是否愿意继续听下去。本课教你如何用'行业关键词+具体数据+价值承诺'的结构在3秒内抓住客户注意力。",
        content_type="video",
        order=1,
        duration_minutes=15,
    ),
    Lesson(
        id=2,
        module_id=3,
        title="Before：让客户自己说'痛'",
        content="不是告诉客户他们有问题，而是引导客户自己意识到问题的存在。学会用SCQA模型构建痛点对话。",
        content_type="video",
        order=2,
        duration_minutes=20,
    ),
    Lesson(
        id=3,
        module_id=3,
        title="After：制造购买后的画面感",
        content="人们买的不是产品，是更好的自己。学会用'当您使用...之后'句式帮客户构建购买后的理想画面。",
        content_type="video",
        order=3,
        duration_minutes=18,
    ),
    Lesson(
        id=4,
        module_id=3,
        title="Curiosity：唯一性才是成交开关",
        content="客户不关心你有多好，只关心你有多不同。掌握差异化卖点的3个提炼方法和话术转化技巧。",
        content_type="video",
        order=4,
        duration_minutes=22,
    ),
    Lesson(
        id=5,
        module_id=3,
        title="Call Action：让说'好'比说'不'更容易",
        content="好的行动号召是让客户的下一个动作变得极其简单。二选一法则+紧迫感构建+零风险承诺。",
        content_type="video",
        order=5,
        duration_minutes=15,
    ),
]

PROGRESSES: list[LearningProgress] = [
    LearningProgress(
        id=1,
        user_id="U001",
        course_id=1,
        progress_pct=65.0,
        completed_lessons=13,
        total_lessons=20,
        time_spent_minutes=320,
        status="学习中",
        started_at="2026-06-10T10:00:00Z",
    ),
    LearningProgress(
        id=2,
        user_id="U001",
        course_id=2,
        progress_pct=100.0,
        completed_lessons=16,
        total_lessons=16,
        time_spent_minutes=280,
        quiz_score=92.0,
        status="已完成",
        started_at="2026-05-20T09:00:00Z",
        completed_at="2026-06-05T16:00:00Z",
    ),
    LearningProgress(
        id=3,
        user_id="U003",
        course_id=1,
        progress_pct=25.0,
        completed_lessons=5,
        total_lessons=20,
        time_spent_minutes=90,
        status="学习中",
        started_at="2026-06-18T14:00:00Z",
    ),
]

AI_TUTOR_MESSAGES: list[AiTutorMessage] = []

CERTIFICATIONS: list[Certification] = [
    Certification(
        id=1,
        user_id="U001",
        user_name="张明",
        course_id=2,
        course_title="链客宝产品专家认证",
        score=92.0,
        passed=True,
        skills=["产品操作", "客户配置", "数据分析"],
    ),
]

# 内存ID计数器
_next_course_id = 4
_next_module_id = 9
_next_lesson_id = 6
_next_progress_id = 4
_next_tutor_id = 1
_next_cert_id = 2


def _recommend_courses(user_progresses: list) -> list:
    """推荐未开始的课程（按评分排序）"""
    enrolled_ids = {p.course_id for p in user_progresses}
    recommended = [c for c in COURSES if c.id not in enrolled_ids and c.status == "上架"]
    return sorted(recommended, key=lambda c: c.rating, reverse=True)


def _suggest_next_module(target) -> dict | None:
    """根据学习进度建议下一个模块"""
    course_modules = [m for m in MODULES if m.course_id == target.course_id and m.module_code != "X10"]
    total = target.total_lessons or 1
    done_ratio = target.completed_lessons / total
    done_count = max(1, int(len(course_modules) * done_ratio))
    completed = course_modules[:done_count]
    if not completed:
        return None
    completed_codes = {m.module_code for m in completed}
    next_modules = [m for m in course_modules if m.module_code not in completed_codes]
    if not next_modules:
        return None
    stage_info = next((p for p in LEARNING_PATH if p["code"] == next_modules[0].module_code), None)
    return {
        "course_id": target.course_id,
        "next_module": next_modules[0],
        "stage_info": stage_info,
        "message": f"建议继续学习「{next_modules[0].title}」模块",
    }


def _determine_progress_status(progress, now: str) -> str:
    if progress.progress_pct >= 100.0:
        progress.completed_at = now
        return "已完成"
    elif progress.progress_pct > 0:
        return "学习中"
    return "未开始"


def _set_progress_timestamps(progress, now: str) -> None:
    if not progress.last_accessed_at:
        progress.last_accessed_at = now


def _filter_courses(category: str | None, level: str | None, status: str | None) -> list:
    """按筛选条件过滤课程"""
    results = COURSES
    if category:
        results = [c for c in results if c.category == category]
    if level:
        results = [c for c in results if c.level == level]
    if status:
        results = [c for c in results if c.status == status]
    return results


# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/api/learning", tags=["学习中心"])

    # === X1-X10 学习路径 ===

    @router.get("/path", summary="获取X1-X10学习路径定义")
    async def get_learning_path():
        return {"path": LEARNING_PATH, "total": len(LEARNING_PATH)}

    # === 课程 CRUD ===

    @router.get("/courses", summary="获取课程列表")
    async def list_courses(category: str | None = None, level: str | None = None, status: str | None = None):
        results = _filter_courses(category, level, status)
        return {"courses": results, "total": len(results)}

    @router.get("/courses/{course_id}", summary="获取课程详情")
    async def get_course(course_id: int):
        for c in COURSES:
            if c.id == course_id:
                return c
        raise HTTPException(status_code=404, detail="课程不存在")

    @router.post("/courses", summary="创建课程")
    async def create_course(course: Course):
        global _next_course_id
        course.id = _next_course_id
        _next_course_id += 1
        now = datetime.utcnow().isoformat() + "Z"
        course.created_at = now
        course.updated_at = now
        COURSES.append(course)
        return {"id": course.id, "message": "课程创建成功"}

    # === 模块管理 ===

    @router.get("/courses/{course_id}/modules", summary="获取课程的所有模块")
    async def list_modules(course_id: int):
        results = [m for m in MODULES if m.course_id == course_id]
        # 按X1-X10顺序排序
        results = sorted(
            results,
            key=lambda m: LEARNING_PATH.index(next(p for p in LEARNING_PATH if p["code"] == m.module_code))
            if any(p["code"] == m.module_code for p in LEARNING_PATH)
            else 99,
        )
        return {"modules": results, "total": len(results)}

    @router.post("/modules", summary="创建课程模块")
    async def create_module(module: Module):
        global _next_module_id
        module.id = _next_module_id
        _next_module_id += 1
        module.created_at = datetime.utcnow().isoformat() + "Z"
        MODULES.append(module)
        # 更新课程的模块计数
        for c in COURSES:
            if c.id == module.course_id:
                c.modules_count = len([m for m in MODULES if m.course_id == c.id])
        return {"id": module.id, "message": "模块创建成功"}

    # === 课时管理 ===

    @router.get("/modules/{module_id}/lessons", summary="获取模块的所有课时")
    async def list_lessons(module_id: int):
        results = [l for l in LESSONS if l.module_id == module_id]
        results = sorted(results, key=lambda l: l.order)
        return {"lessons": results, "total": len(results)}

    @router.post("/lessons", summary="创建课时")
    async def create_lesson(lesson: Lesson):
        global _next_lesson_id
        lesson.id = _next_lesson_id
        _next_lesson_id += 1
        lesson.created_at = datetime.utcnow().isoformat() + "Z"
        LESSONS.append(lesson)
        return {"id": lesson.id, "message": "课时创建成功"}

    # === 学习进度 ===

    @router.get("/progress/{user_id}", summary="获取用户学习进度")
    async def get_user_progress(user_id: str, course_id: int | None = None):
        results = [p for p in PROGRESSES if p.user_id == user_id]
        if course_id:
            results = [p for p in results if p.course_id == course_id]
        return {"progresses": results, "total": len(results)}

    @router.post("/progress", summary="更新/创建学习进度")
    async def update_progress(progress: LearningProgress):
        global _next_progress_id
        now = datetime.utcnow().isoformat() + "Z"
        _set_progress_timestamps(progress, now)

        # 查找是否已有进度记录
        for i, p in enumerate(PROGRESSES):
            if p.user_id == progress.user_id and p.course_id == progress.course_id:
                progress.id = p.id
                progress.last_accessed_at = now
                progress.status = _determine_progress_status(progress, now)
                PROGRESSES[i] = progress
                return {"id": progress.id, "message": "学习进度已更新"}

        # 新建
        progress.id = _next_progress_id
        _next_progress_id += 1
        progress.started_at = now
        progress.last_accessed_at = now
        progress.status = _determine_progress_status(progress, now)
        PROGRESSES.append(progress)
        return {"id": progress.id, "message": "学习进度已创建"}

    # === AI导师 ===

    @router.get("/tutor/{user_id}/{course_id}", summary="获取AI导师对话历史")
    async def get_tutor_history(user_id: str, course_id: int):
        messages = [m for m in AI_TUTOR_MESSAGES if m.user_id == user_id and m.course_id == course_id]
        return {"messages": messages, "total": len(messages)}

    @router.post("/tutor/ask", summary="向AI导师提问")
    async def ask_tutor(message: AiTutorMessage):
        """用户提问，AI导师回复（模拟）"""
        global _next_tutor_id
        message.id = _next_tutor_id
        _next_tutor_id += 1
        message.role = "user"
        message.created_at = datetime.utcnow().isoformat() + "Z"
        AI_TUTOR_MESSAGES.append(message)

        # 模拟AI回复
        from random import choice

        responses = [
            "根据您的学习进度，我建议您先完成X3核心知识模块的打基础，再进入X4案例教学。",
            "这个问题很好！ABACC框架中的'Curiosity'环节最关键的技巧是制造信息差——让客户觉得'这个信息我不知道但我需要知道'。",
            "您现在处于B2B销售实战课程的第65%进度。我推荐您重点关注'Call Action'章节，这是转化率提升的关键。",
            "在链客宝的AI匹配场景中，您提到的这个问题可以通过调整匹配权重参数来解决。需要我详细讲解吗？",
        ]
        reply = AiTutorMessage(
            user_id=message.user_id,
            course_id=message.course_id,
            module_id=message.module_id,
            role="assistant",
            content=choice(responses),
            context=message.content,
        )
        reply.id = _next_tutor_id
        _next_tutor_id += 1
        reply.created_at = datetime.utcnow().isoformat() + "Z"
        AI_TUTOR_MESSAGES.append(reply)

        return {"user_message": message, "ai_reply": reply}

    # === 认证管理 ===

    @router.get("/certifications/{user_id}", summary="获取用户认证记录")
    async def get_user_certifications(user_id: str):
        results = [c for c in CERTIFICATIONS if c.user_id == user_id]
        return {"certifications": results, "total": len(results)}

    @router.post("/certifications", summary="颁发认证")
    async def issue_certification(cert: Certification):
        global _next_cert_id
        cert.id = _next_cert_id
        _next_cert_id += 1
        now = datetime.utcnow().isoformat() + "Z"
        cert.issued_at = now
        cert.passed = cert.score >= 70.0
        CERTIFICATIONS.append(cert)
        # 更新学习进度状态
        for p in PROGRESSES:
            if p.user_id == cert.user_id and p.course_id == cert.course_id:
                p.status = "已认证"
        return {"id": cert.id, "message": "认证成功" if cert.passed else "未通过考核", "passed": cert.passed}

    # === 仪表盘统计 ===

    @router.get("/dashboard/{user_id}", summary="获取用户学习仪表盘")
    async def get_learning_dashboard(user_id: str):
        """返回用户的学习总览统计数据"""
        user_progresses = [p for p in PROGRESSES if p.user_id == user_id]

        total_courses = len(user_progresses)
        completed_courses = len([p for p in user_progresses if p.status == "已完成" or p.status == "已认证"])
        certified_courses = len([p for p in user_progresses if p.status == "已认证"])
        in_progress = len([p for p in user_progresses if p.status == "学习中"])
        total_time = sum(p.time_spent_minutes for p in user_progresses)
        avg_completion = (
            round(sum(p.progress_pct for p in user_progresses) / total_courses, 1) if total_courses > 0 else 0.0
        )

        recommended = _recommend_courses(user_progresses)

        return {
            "user_id": user_id,
            "total_courses": total_courses,
            "completed_courses": completed_courses,
            "certified_courses": certified_courses,
            "in_progress": in_progress,
            "total_learning_time_minutes": total_time,
            "avg_completion_rate": avg_completion,
            "recommended_courses": recommended[:3],
            "next_stage": _get_next_learning_stage(user_id),
        }

    def _get_next_learning_stage(user_id: str) -> dict | None:
        """建议用户下一个学习阶段"""
        in_progress_courses = [p for p in PROGRESSES if p.user_id == user_id and p.status == "学习中"]
        if not in_progress_courses:
            return {"message": "暂无进行中的课程，建议开始一门新课程", "action": "browse_courses"}
        target = max(in_progress_courses, key=lambda p: p.progress_pct)
        return _suggest_next_module(target)

    print("[X1-X10] 学习中心路由已加载 ✓")
    print(f"[X1-X10] 课程: {len(COURSES)} 门 | 模块: {len(MODULES)} 个 | 课时: {len(LESSONS)} 个")

except ImportError:
    print("[X1-X10] FastAPI未安装，跳过路由注册（数据层已就绪）")
    router = None
