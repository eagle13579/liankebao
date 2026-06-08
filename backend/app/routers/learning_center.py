"""
X1-X10 心智模型注入 — 科学学习模型
=====================================
链客宝学习中心：用户侧加入知识推送/学习路径功能。
将一堂「科学学习」模型产品化为用户可消费的知识推送和学习路径系统。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, desc, func
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import User
from app.auth import get_current_user
from app.rbac import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["X1-X10心智模型-科学学习"])


# ============================================================
# X1-X10 科学学习框架
# ============================================================
LEARNING_MODULES = {
    "X1": {"name": "问题驱动", "description": "以真实问题驱动学习，而非被动吸收"},
    "X2": {"name": "间隔重复", "description": "按照遗忘曲线安排复习节奏"},
    "X3": {"name": "主动回忆", "description": "不看资料，强制自己回忆知识点"},
    "X4": {"name": "费曼技巧", "description": "用最简单的语言向别人解释复杂概念"},
    "X5": {"name": "知识树构建", "description": "将新知识挂接到已有知识树上"},
    "X6": {"name": "反馈循环", "description": "快速获取反馈，修正理解偏差"},
    "X7": {"name": "刻意练习", "description": "在最近发展区内进行有针对性的练习"},
    "X8": {"name": "思维模型", "description": "将知识抽象为可迁移的思维模型"},
    "X9": {"name": "关联迁移", "description": "在不同领域之间建立连接和类比"},
    "X10": {"name": "教授他人", "description": "通过教别人来巩固和深化理解"},
}

# 知识分类
KNOWLEDGE_CATEGORIES = [
    "商业认知", "产品思维", "增长策略", "管理方法",
    "市场营销", "技术趋势", "行业洞察", "思维模型",
    "融资认知", "领导力",
]


# ============================================================
# 数据模型
# ============================================================

class KnowledgeArticle(Base):
    """知识文章 — 推送给用户的学习内容"""
    __tablename__ = "learning_articles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="文章标题")
    summary = Column(String(500), nullable=True, comment="文章摘要（<100字）")
    content = Column(Text, nullable=False, comment="文章内容（Markdown）")
    category = Column(String(50), nullable=False, index=True, comment="知识分类")
    tags = Column(String(500), nullable=True, comment="标签（逗号分隔）")
    source = Column(String(100), nullable=True, comment="来源（一堂/自研/转载）")
    difficulty = Column(String(10), nullable=False, default="beginner", comment="难度: beginner/intermediate/advanced")
    read_time_minutes = Column(Integer, default=5, comment="预计阅读时间(分钟)")
    related_module = Column(String(5), nullable=True, comment="关联X模块: X1-X10")
    is_published = Column(Integer, default=0, comment="是否发布: 0草稿/1发布")
    author_name = Column(String(100), nullable=True, comment="作者")
    view_count = Column(Integer, default=0, comment="阅读次数")
    like_count = Column(Integer, default=0, comment="点赞数")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserLearningProgress(Base):
    """用户学习进度 — 跟踪每个用户的学习路径"""
    __tablename__ = "user_learning_progress"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    article_id = Column(Integer, nullable=False, comment="文章ID")
    status = Column(String(20), nullable=False, default="assigned", comment="状态: assigned/in_progress/completed/bookmarked")
    comprehension_score = Column(Integer, nullable=True, comment="理解度评分(1-5)")
    note = Column(Text, nullable=True, comment="用户笔记")
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningPath(Base):
    """学习路径 — 为用户推荐的学习路线"""
    __tablename__ = "learning_paths"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="路径名称")
    description = Column(Text, nullable=True, comment="路径描述")
    category = Column(String(50), nullable=False, comment="分类")
    difficulty = Column(String(10), nullable=False, default="beginner")
    article_ids = Column(Text, nullable=True, comment="关联文章ID列表(逗号分隔，有序)")
    estimated_hours = Column(Float, default=0, comment="预计学习时长(小时)")
    is_active = Column(Integer, default=1, comment="是否启用")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# Pydantic Schemas
# ============================================================

class ArticleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    summary: Optional[str] = None
    content: str = Field(..., min_length=1)
    category: str
    tags: Optional[str] = None
    source: Optional[str] = "自研"
    difficulty: str = "beginner"
    read_time_minutes: int = 5
    related_module: Optional[str] = None
    author_name: Optional[str] = None

class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    difficulty: Optional[str] = None
    is_published: Optional[int] = None

class PathCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    difficulty: str = "beginner"
    article_ids: str = ""
    estimated_hours: float = 0

class ProgressUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(assigned|in_progress|completed|bookmarked)$")
    comprehension_score: Optional[int] = Field(None, ge=1, le=5)
    note: Optional[str] = None


# ============================================================
# API 路由
# ============================================================

@router.get("/modules", summary="获取X1-X10学习框架", description="返回X1-X10科学学习模型框架定义")
def get_learning_framework(
    user: User = Depends(get_current_user),
):
    """返回X1-X10框架"""
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_modules": len(LEARNING_MODULES),
            "modules": [{"key": k, "name": v["name"], "description": v["description"]} for k, v in LEARNING_MODULES.items()],
        },
    }


@router.get("/categories", summary="获取知识分类", description="返回所有知识分类列表")
def get_categories():
    """返回知识分类"""
    return {"code": 200, "message": "success", "data": KNOWLEDGE_CATEGORIES}


# --- 文章管理（管理员） ---

@router.post("/articles", summary="创建知识文章", description="管理员创建新的知识文章")
def create_article(
    body: ArticleCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(["admin"])),
):
    """创建文章"""
    article = KnowledgeArticle(
        title=body.title,
        summary=body.summary,
        content=body.content,
        category=body.category,
        tags=body.tags,
        source=body.source,
        difficulty=body.difficulty,
        read_time_minutes=body.read_time_minutes,
        related_module=body.related_module,
        author_name=body.author_name or admin.name,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    logger.info(f"[X科学学习] 创建文章: {article.title}")
    return {"code": 200, "message": "文章已创建", "data": {"id": article.id, "title": article.title}}


@router.get("/articles", summary="获取文章列表", description="分页获取知识文章列表（支持分类/难度筛选）")
def list_articles(
    category: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None, pattern=r"^(beginner|intermediate|advanced)$"),
    related_module: Optional[str] = Query(None, pattern=r"^X(1[0]|[1-9])$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """分页列出文章"""
    q = db.query(KnowledgeArticle).filter(KnowledgeArticle.is_published == 1)
    if category:
        q = q.filter(KnowledgeArticle.category == category)
    if difficulty:
        q = q.filter(KnowledgeArticle.difficulty == difficulty)
    if related_module:
        q = q.filter(KnowledgeArticle.related_module == related_module)

    total = q.count()
    articles = q.order_by(desc(KnowledgeArticle.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": a.id,
                    "title": a.title,
                    "summary": a.summary,
                    "category": a.category,
                    "tags": a.tags,
                    "difficulty": a.difficulty,
                    "read_time_minutes": a.read_time_minutes,
                    "related_module": a.related_module,
                    "view_count": a.view_count,
                    "like_count": a.like_count,
                    "created_at": a.created_at.isoformat(),
                }
                for a in articles
            ],
        },
    }


@router.get("/articles/{article_id}", summary="获取文章详情", description="获取知识文章完整内容")
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看文章详情（自动增加阅读计数）"""
    article = db.query(KnowledgeArticle).filter(
        KnowledgeArticle.id == article_id,
        KnowledgeArticle.is_published == 1,
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 增加阅读计数
    article.view_count = (article.view_count or 0) + 1
    db.commit()

    # 记录用户阅读进度
    existing = db.query(UserLearningProgress).filter(
        UserLearningProgress.user_id == user.id,
        UserLearningProgress.article_id == article_id,
    ).first()
    if not existing:
        progress = UserLearningProgress(
            user_id=user.id,
            article_id=article_id,
            status="in_progress",
        )
        db.add(progress)
        db.commit()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": article.id,
            "title": article.title,
            "summary": article.summary,
            "content": article.content,
            "category": article.category,
            "tags": article.tags,
            "source": article.source,
            "difficulty": article.difficulty,
            "read_time_minutes": article.read_time_minutes,
            "related_module": article.related_module,
            "author_name": article.author_name,
            "view_count": article.view_count,
            "like_count": article.like_count,
            "created_at": article.created_at.isoformat(),
        },
    }


@router.post("/articles/{article_id}/like", summary="点赞文章", description="为知识文章点赞")
def like_article(
    article_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """点赞"""
    article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    article.like_count = (article.like_count or 0) + 1
    db.commit()
    return {"code": 200, "message": "点赞成功", "data": {"like_count": article.like_count}}


# --- 学习路径 ---

@router.post("/paths", summary="创建学习路径", description="管理员创建学习路径")
def create_learning_path(
    body: PathCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(["admin"])),
):
    """创建学习路径"""
    path = LearningPath(
        name=body.name,
        description=body.description,
        category=body.category,
        difficulty=body.difficulty,
        article_ids=body.article_ids,
        estimated_hours=body.estimated_hours,
    )
    db.add(path)
    db.commit()
    db.refresh(path)
    return {"code": 200, "message": "学习路径已创建", "data": {"id": path.id, "name": path.name}}


@router.get("/paths", summary="获取学习路径", description="获取所有学习路径")
def list_learning_paths(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出学习路径"""
    q = db.query(LearningPath).filter(LearningPath.is_active == 1)
    if category:
        q = q.filter(LearningPath.category == category)
    paths = q.all()
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "difficulty": p.difficulty,
                "article_count": len(p.article_ids.split(",")) if p.article_ids else 0,
                "estimated_hours": p.estimated_hours,
            }
            for p in paths
        ],
    }


# --- 用户学习进度 ---

@router.get("/progress", summary="获取学习进度", description="获取当前用户的学习进度概览")
def get_my_progress(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户的个人学习进度"""
    total_assigned = db.query(UserLearningProgress).filter(
        UserLearningProgress.user_id == user.id,
    ).count()

    completed = db.query(UserLearningProgress).filter(
        UserLearningProgress.user_id == user.id,
        UserLearningProgress.status == "completed",
    ).count()

    in_progress = db.query(UserLearningProgress).filter(
        UserLearningProgress.user_id == user.id,
        UserLearningProgress.status == "in_progress",
    ).count()

    bookmarked = db.query(UserLearningProgress).filter(
        UserLearningProgress.user_id == user.id,
        UserLearningProgress.status == "bookmarked",
    ).count()

    # 最近学习
    recent = db.query(UserLearningProgress).filter(
        UserLearningProgress.user_id == user.id,
    ).order_by(desc(UserLearningProgress.updated_at)).limit(5).all()

    recent_articles = []
    for r in recent:
        article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == r.article_id).first()
        if article:
            recent_articles.append({
                "article_id": article.id,
                "title": article.title,
                "category": article.category,
                "status": r.status,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_assigned": total_assigned,
            "completed": completed,
            "in_progress": in_progress,
            "bookmarked": bookmarked,
            "completion_rate": round(completed / max(total_assigned, 1) * 100, 1),
            "recent_articles": recent_articles,
        },
    }


@router.put("/progress/{article_id}", summary="更新学习进度", description="更新某篇文章的学习状态")
def update_progress(
    article_id: int,
    body: ProgressUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新学习进度"""
    progress = db.query(UserLearningProgress).filter(
        UserLearningProgress.user_id == user.id,
        UserLearningProgress.article_id == article_id,
    ).first()

    if not progress:
        progress = UserLearningProgress(
            user_id=user.id,
            article_id=article_id,
            status=body.status,
        )
        db.add(progress)
    else:
        progress.status = body.status
        if body.comprehension_score is not None:
            progress.comprehension_score = body.comprehension_score
        if body.note is not None:
            progress.note = body.note
        if body.status == "completed":
            progress.completed_at = datetime.utcnow()

    db.commit()
    return {"code": 200, "message": "进度已更新"}


# --- 每日推荐（知识推送） ---

@router.get("/daily-recommend", summary="每日推荐", description="根据用户学习历史和偏好推荐知识文章")
def daily_recommend(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """智能推荐未读文章"""
    # 已读文章ID
    read_ids = [
        r.article_id for r in db.query(UserLearningProgress).filter(
            UserLearningProgress.user_id == user.id,
        ).all()
    ]

    # 推荐未读文章（按新发布时间排序）
    q = db.query(KnowledgeArticle).filter(
        KnowledgeArticle.is_published == 1,
    )
    if read_ids:
        q = q.filter(~KnowledgeArticle.id.in_(read_ids))

    articles = q.order_by(desc(KnowledgeArticle.created_at)).limit(5).all()

    # 如果全部已读，推荐已读中评分高的
    if not articles:
        articles = db.query(KnowledgeArticle).filter(
            KnowledgeArticle.is_published == 1,
        ).order_by(desc(KnowledgeArticle.like_count)).limit(5).all()

    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": a.id,
                "title": a.title,
                "summary": a.summary,
                "category": a.category,
                "difficulty": a.difficulty,
                "read_time_minutes": a.read_time_minutes,
                "related_module": a.related_module,
            }
            for a in articles
        ],
    }
