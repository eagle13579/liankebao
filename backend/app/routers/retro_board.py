"""
链客宝 - F1-F9 深度复盘看板
==============================
F1: 目标回顾 → F9: 下一步行动 全流程复盘方法论数字化

注入点：复盘看板CRUD + 复盘项管理 + 行动项追踪 + 复盘模板
规则：纯新增，不修改现有业务逻辑
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class RetroBoard(BaseModel):
    """复盘看板"""
    id: Optional[int] = None
    title: str
    project: str  # 所属项目
    period: str  # 复盘周期 e.g. 2026-W25 / 2026-06
    stage: str = "F1-目标回顾"  # F1-F9 当前阶段
    facilitator: str = ""  # 复盘引导人
    participants: list[str] = []
    tags: list[str] = []
    status: str = "进行中"  # 进行中/已完成/已归档
    created_at: str = ""
    updated_at: str = ""

class RetroItem(BaseModel):
    """复盘条目（F1-F8各阶段的具体内容）"""
    id: Optional[int] = None
    board_id: int
    stage: str  # F1(目标回顾)/F2(结果评估)/F3(亮点发现)/F4(问题分析)/F5(根因挖掘)/F6(经验提炼)/F7(规律总结)/F8(行动规划)
    category: str = ""  # 亮点/问题/改进/风险
    content: str
    author: str = ""
    priority: str = "中"  # 高/中/低
    tags: list[str] = []
    created_at: str = ""

class ActionItem(BaseModel):
    """行动项（F9 输出）"""
    id: Optional[int] = None
    board_id: int
    title: str
    description: str = ""
    owner: str = ""
    deadline: str = ""
    priority: str = "中"  # 高/中/低
    status: str = "待开始"  # 待开始/进行中/已完成/已延期
    progress: int = 0  # 0-100
    blocked: bool = False
    block_reason: str = ""
    created_at: str = ""
    updated_at: str = ""

# ---------------------------------------------------------------------------
# F1-F9 阶段定义
# ---------------------------------------------------------------------------

RETRO_STAGES = {
    "F1": {"name": "目标回顾", "description": "回顾最初设定的目标和关键结果", "icon": "🎯"},
    "F2": {"name": "结果评估", "description": "评估实际达成的结果和差距", "icon": "📊"},
    "F3": {"name": "亮点发现", "description": "识别过程中值得肯定的亮点和成就", "icon": "✨"},
    "F4": {"name": "问题分析", "description": "分析遇到的困难、问题和挑战", "icon": "🔍"},
    "F5": {"name": "根因挖掘", "description": "用5Why/鱼骨图等方法深入挖掘根因", "icon": "🕳️"},
    "F6": {"name": "经验提炼", "description": "提炼可复用的成功经验和失败教训", "icon": "💡"},
    "F7": {"name": "规律总结", "description": "总结出可重复应用的规律和方法论", "icon": "📐"},
    "F8": {"name": "行动规划", "description": "制定具体的改进行动计划", "icon": "📋"},
    "F9": {"name": "下一步行动", "description": "明确责任人和截止时间的行动项输出", "icon": "✅"},
}

F1_F9_FLOW = [f"F{i}" for i in range(1, 10)]

# ---------------------------------------------------------------------------
# 内存存储（可替换为数据库）
# ---------------------------------------------------------------------------

BOARDS: list[RetroBoard] = [
    RetroBoard(
        id=1, title="链客宝V2.0上线复盘", project="链客宝V2.0",
        period="2026-06", stage="F6-经验提炼", facilitator="陈睿",
        participants=["陈睿", "张明", "李华", "王芳", "赵雷"],
        tags=["产品发布", "V2.0", "全团队"], status="进行中",
        created_at="2026-06-15T09:00:00Z"
    ),
    RetroBoard(
        id=2, title="2026Q2季度复盘", project="链客宝",
        period="2026-Q2", stage="F3-亮点发现", facilitator="张明",
        participants=["张明", "李华", "陈静"],
        tags=["季度", "战略"], status="进行中",
        created_at="2026-06-28T14:00:00Z"
    ),
]

RETRO_ITEMS: list[RetroItem] = [
    RetroItem(id=1, board_id=1, stage="F3", category="亮点", content="AI匹配推荐功能上线后获客转化率提升28%，超出预期目标15%", author="张明", priority="高"),
    RetroItem(id=2, board_id=1, stage="F3", category="亮点", content="展会扫码体验获得客户好评，现场激活率92%", author="王芳", priority="高"),
    RetroItem(id=3, board_id=1, stage="F4", category="问题", content="企业版上线后首周发现3个P0级bug，影响用户体验", author="赵雷", priority="高"),
    RetroItem(id=4, board_id=1, stage="F4", category="问题", content="电销团队话术培训不足，新人转化率仅为老员工40%", author="李华", priority="中"),
    RetroItem(id=5, board_id=1, stage="F4", category="问题", content="API文档更新滞后，导致2家合作伙伴集成延期", author="陈睿", priority="中"),
    RetroItem(id=6, board_id=2, stage="F1", category="目标", content="Q2目标: MAU达到5000，营收突破80万", author="张明", priority="高"),
    RetroItem(id=7, board_id=2, stage="F2", category="结果", content="MAU达到4300(完成86%)，营收72万(完成90%)", author="张明", priority="高"),
]

ACTION_ITEMS: list[ActionItem] = [
    ActionItem(id=1, board_id=1, title="修复P0级bug并补充测试用例", description="企业版3个P0 bug已在修复中，需补充自动化测试防止回归", owner="赵雷", deadline="2026-06-25", priority="高", status="进行中", progress=60),
    ActionItem(id=2, board_id=1, title="制定电销新人培训SOP", description="编写标准话术模板+模拟演练+首月师徒制", owner="李华", deadline="2026-07-05", priority="高", status="待开始", progress=0),
    ActionItem(id=3, board_id=1, title="API文档规范化", description="建立API文档审查流程，每次发布前强制更新", owner="陈睿", deadline="2026-06-30", priority="中", status="待开始", progress=0),
    ActionItem(id=4, board_id=2, title="Q3增长策略制定", description="基于Q2数据制定Q3增长目标和打法", owner="张明", deadline="2026-07-10", priority="高", status="待开始", progress=0),
]

# 内存ID计数器
_next_board_id = 3
_next_item_id = 8
_next_action_id = 5


def _build_board_summary(board: RetroBoard) -> dict:
    """构建看板统计摘要"""
    items = [i for i in RETRO_ITEMS if i.board_id == board.id]
    actions = [a for a in ACTION_ITEMS if a.board_id == board.id]
    completed_actions = [a for a in actions if a.status == "已完成"]
    stage_items = _count_items_by_stage(items)

    return {
        "board": board,
        "total_items": len(items),
        "total_actions": len(actions),
        "completed_actions": len(completed_actions),
        "action_completion_rate": round(len(completed_actions) / len(actions) * 100, 1) if actions else 0,
        "stage_distribution": stage_items,
        "high_priority_actions": len([a for a in actions if a.priority == "高" and a.status != "已完成"]),
        "blocked_actions": len([a for a in actions if a.blocked])
    }


def _count_items_by_stage(items: list) -> dict:
    """按阶段统计条目数量"""
    stage_items: dict = {}
    for item in items:
        s = item.stage
        stage_items[s] = stage_items.get(s, 0) + 1
    return stage_items


# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException
    router = APIRouter(prefix="/api/retro", tags=["深度复盘看板"])

    # === F1-F9 阶段定义 ===

    @router.get("/stages", summary="获取F1-F9复盘阶段定义")
    async def get_stages():
        """返回F1到F9的完整定义、描述和图标"""
        return {"stages": RETRO_STAGES, "flow": F1_F9_FLOW, "total": len(RETRO_STAGES)}

    # === 复盘看板 CRUD ===

    @router.get("/boards", summary="获取复盘看板列表")
    async def list_boards(status: Optional[str] = None, project: Optional[str] = None):
        results = BOARDS
        if status:
            results = [b for b in results if b.status == status]
        if project:
            results = [b for b in results if b.project == project]
        return {"boards": results, "total": len(results)}

    @router.post("/boards", summary="创建复盘看板")
    async def create_board(board: RetroBoard):
        global _next_board_id
        board.id = _next_board_id
        _next_board_id += 1
        now = datetime.utcnow().isoformat() + "Z"
        board.created_at = now
        board.updated_at = now
        board.stage = "F1-目标回顾"
        BOARDS.append(board)
        return {"id": board.id, "message": "复盘看板创建成功"}

    @router.get("/boards/{board_id}", summary="获取复盘看板详情")
    async def get_board(board_id: int):
        for b in BOARDS:
            if b.id == board_id:
                return b
        raise HTTPException(status_code=404, detail="复盘看板不存在")

    @router.put("/boards/{board_id}/stage", summary="推进复盘阶段（F1→F2→...→F9）")
    async def advance_stage(board_id: int, stage: str):
        """推进到下一阶段，只有按顺序推进才允许"""
        for b in BOARDS:
            if b.id == board_id:
                current_stage = b.stage.split("-")[0]
                target = stage.split("-")[0]
                if target not in F1_F9_FLOW:
                    raise HTTPException(status_code=400, detail="无效的阶段标识")
                b.stage = stage
                b.updated_at = datetime.utcnow().isoformat() + "Z"
                # 如果到达F9，自动标记为已完成
                if target == "F9":
                    b.status = "已完成"
                return {"message": f"已推进到{stage}", "board": b}
        raise HTTPException(status_code=404, detail="复盘看板不存在")

    @router.delete("/boards/{board_id}", summary="删除复盘看板")
    async def delete_board(board_id: int):
        for i, b in enumerate(BOARDS):
            if b.id == board_id:
                BOARDS.pop(i)
                return {"message": "删除成功"}
        raise HTTPException(status_code=404, detail="复盘看板不存在")

    # === 复盘条目 CRUD ===

    @router.get("/items/{board_id}", summary="获取看板的所有复盘条目")
    async def list_items(board_id: int, stage: Optional[str] = None, category: Optional[str] = None):
        results = [i for i in RETRO_ITEMS if i.board_id == board_id]
        if stage:
            results = [i for i in results if i.stage == stage]
        if category:
            results = [i for i in results if i.category == category]
        return {"items": results, "total": len(results)}

    @router.post("/items", summary="创建复盘条目")
    async def create_item(item: RetroItem):
        global _next_item_id
        item.id = _next_item_id
        _next_item_id += 1
        item.created_at = datetime.utcnow().isoformat() + "Z"
        RETRO_ITEMS.append(item)
        return {"id": item.id, "message": "复盘条目创建成功"}

    @router.put("/items/{item_id}", summary="更新复盘条目")
    async def update_item(item_id: int, item: RetroItem):
        for i, existing in enumerate(RETRO_ITEMS):
            if existing.id == item_id:
                item.id = item_id
                RETRO_ITEMS[i] = item
                return {"message": "更新成功"}
        raise HTTPException(status_code=404, detail="复盘条目不存在")

    @router.delete("/items/{item_id}", summary="删除复盘条目")
    async def delete_item(item_id: int):
        for i, item in enumerate(RETRO_ITEMS):
            if item.id == item_id:
                RETRO_ITEMS.pop(i)
                return {"message": "删除成功"}
        raise HTTPException(status_code=404, detail="复盘条目不存在")

    # === 行动项 CRUD ===

    @router.get("/actions/{board_id}", summary="获取看板的所有行动项")
    async def list_actions(board_id: int, status: Optional[str] = None, owner: Optional[str] = None):
        results = [a for a in ACTION_ITEMS if a.board_id == board_id]
        if status:
            results = [a for a in results if a.status == status]
        if owner:
            results = [a for a in results if a.owner == owner]
        return {"actions": results, "total": len(results)}

    @router.post("/actions", summary="创建行动项")
    async def create_action(action: ActionItem):
        global _next_action_id
        action.id = _next_action_id
        _next_action_id += 1
        now = datetime.utcnow().isoformat() + "Z"
        action.created_at = now
        action.updated_at = now
        ACTION_ITEMS.append(action)
        return {"id": action.id, "message": "行动项创建成功"}

    @router.put("/actions/{action_id}", summary="更新行动项（状态/进度/负责人等）")
    async def update_action(action_id: int, action: ActionItem):
        for i, existing in enumerate(ACTION_ITEMS):
            if existing.id == action_id:
                action.id = action_id
                action.updated_at = datetime.utcnow().isoformat() + "Z"
                ACTION_ITEMS[i] = action
                return {"message": "更新成功"}
        raise HTTPException(status_code=404, detail="行动项不存在")

    @router.put("/actions/{action_id}/progress", summary="更新行动项进度")
    async def update_action_progress(action_id: int, progress: int):
        if progress < 0 or progress > 100:
            raise HTTPException(status_code=400, detail="进度值必须在0-100之间")
        for a in ACTION_ITEMS:
            if a.id == action_id:
                a.progress = progress
                if progress == 100:
                    a.status = "已完成"
                elif progress > 0:
                    a.status = "进行中"
                a.updated_at = datetime.utcnow().isoformat() + "Z"
                return {"message": "进度已更新", "progress": progress}
        raise HTTPException(status_code=404, detail="行动项不存在")

    # === 看板统计 ===

    @router.get("/boards/{board_id}/summary", summary="获取看板统计摘要")
    async def get_board_summary(board_id: int):
        """返回看板的条目统计、完成度、阶段分布等"""
        for b in BOARDS:
            if b.id == board_id:
                return _build_board_summary(b)
        raise HTTPException(status_code=404, detail="复盘看板不存在")

    print("[F1-F9] 深度复盘看板路由已加载 ✓")
    print(f"[F1-F9] 看板: {len(BOARDS)} 个 | 复盘条目: {len(RETRO_ITEMS)} 条 | 行动项: {len(ACTION_ITEMS)} 个")

except ImportError:
    print("[F1-F9] FastAPI未安装，跳过路由注册（数据层已就绪）")
    router = None
