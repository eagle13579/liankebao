"""
链客宝 - M2 假设验证门禁
==============================
商业假设 → 实验设计 → 数据验证 → 门禁判断 全流程

注入点：假设模板CRUD + 实验运行 + 验证结果管理
规则：纯新增，不修改现有业务逻辑
"""

from datetime import datetime

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class Hypothesis(BaseModel):
    """商业假设"""

    id: int | None = None
    title: str
    description: str
    category: str  # 增长/留存/转化/定价/产品
    assumptions: list[str] = []
    evidence_level: str = "低"  # 低/中/高 — 现有证据支撑程度
    risk_score: int | None = None  # 1-10 验证不通过的风险
    status: str = "待验证"  # 待验证/验证中/已验证/已关闭
    tags: list[str] = []
    created_at: str = ""
    updated_at: str = ""


class ExperimentDesign(BaseModel):
    """实验设计"""

    id: int | None = None
    hypothesis_id: int
    name: str
    method: str  # A/B测试/用户访谈/数据分析/问卷调研
    sample_size: int | None = None
    success_criteria: str  # 判定假设成立的标准
    duration_days: int | None = None
    variables: list[dict] = []  # [{"name": "自变量", "control": "对照组", "experiment": "实验组"}]
    created_at: str = ""


class ValidationResult(BaseModel):
    """验证结果"""

    id: int | None = None
    hypothesis_id: int
    experiment_id: int
    passed: bool
    confidence: float = 0.0  # 0.0-1.0 置信度
    data_summary: str = ""
    metrics: dict = {}  # {"对照组转化率": 0.12, "实验组转化率": 0.18, "提升": 0.5}
    conclusion: str = ""
    reviewer: str = ""
    validated_at: str = ""


# ---------------------------------------------------------------------------
# 内存存储（可替换为数据库）
# ---------------------------------------------------------------------------

HYPOTHESES: list[Hypothesis] = [
    Hypothesis(
        id=1,
        title="AI匹配推荐提升B2B获客转化率",
        description="在链客宝AI供需匹配结果页增加'一键约见'按钮和个性化推荐理由，可使B2B用户转化率提升30%",
        category="转化",
        assumptions=["用户对AI匹配结果有信任基础", "推荐理由是驱动点击的核心因素", "一键约见降低用户操作门槛"],
        evidence_level="中",
        risk_score=6,
        status="验证中",
        tags=["B2B", "AI匹配", "转化率"],
        created_at="2026-06-01T09:00:00Z",
    ),
    Hypothesis(
        id=2,
        title="展会场景扫码即用降低获客门槛",
        description="展会场景用户扫码后无需注册即可使用基础匹配功能，可提升线索获取量50%",
        category="增长",
        assumptions=["展会用户对快速体验有强烈需求", "注册流程是主要流失节点", "基础功能足以展示产品价值"],
        evidence_level="高",
        risk_score=4,
        status="待验证",
        tags=["展会", "获客", "用户体验"],
        created_at="2026-06-03T14:00:00Z",
    ),
    Hypothesis(
        id=3,
        title="社交人脉可视化增加付费转化",
        description="在个人主页增加人脉关系图谱可视化功能，可使免费用户升级为付费用户的比例提升20%",
        category="增长",
        assumptions=[
            "用户对自身人脉资产有可视化需求",
            "图谱功能是区别于竞品的差异化卖点",
            "付费解锁图谱的心理门槛低于工具功能",
        ],
        evidence_level="低",
        risk_score=7,
        status="待验证",
        tags=["社交", "人脉", "付费转化"],
        created_at="2026-06-05T10:30:00Z",
    ),
]

EXPERIMENTS: list[ExperimentDesign] = [
    ExperimentDesign(
        id=1,
        hypothesis_id=1,
        name="AI匹配推荐理由A/B测试",
        method="A/B测试",
        sample_size=2000,
        success_criteria="实验组转化率比对照组高15%以上，置信度>95%",
        duration_days=14,
        variables=[
            {
                "name": "推荐理由展示方式",
                "control": "仅显示匹配企业名称",
                "experiment": "企业名称+AI推荐理由+一键约见按钮",
            }
        ],
        created_at="2026-06-02T10:00:00Z",
    )
]

VALIDATION_RESULTS: list[ValidationResult] = []

# 内存ID计数器
_next_hypothesis_id = 4
_next_experiment_id = 2
_next_result_id = 1


def _find_hypothesis(hypothesis_id: int) -> Hypothesis | None:
    for h in HYPOTHESES:
        if h.id == hypothesis_id:
            return h
    return None


def _compute_gate_score(latest: ValidationResult, h: Hypothesis) -> int:
    score = 0
    if latest.passed:
        score += 40
    score += int(latest.confidence * 30)
    risk_penalty = (h.risk_score or 5) * 3
    return max(0, min(100, score - risk_penalty))


# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/api/hypothesis", tags=["假设验证门禁"])

    # === 假设 CRUD ===

    @router.get("/hypotheses", summary="获取假设列表")
    async def list_hypotheses(category: str | None = None, status: str | None = None):
        """按分类和状态筛选假设列表"""
        results = HYPOTHESES
        if category:
            results = [h for h in results if h.category == category]
        if status:
            results = [h for h in results if h.status == status]
        return {"hypotheses": results, "total": len(results)}

    @router.get("/hypotheses/{hypothesis_id}", summary="获取假设详情")
    async def get_hypothesis(hypothesis_id: int):
        for h in HYPOTHESES:
            if h.id == hypothesis_id:
                return h
        raise HTTPException(status_code=404, detail="假设不存在")

    @router.post("/hypotheses", summary="创建假设")
    async def create_hypothesis(h: Hypothesis):
        global _next_hypothesis_id
        h.id = _next_hypothesis_id
        _next_hypothesis_id += 1
        now = datetime.utcnow().isoformat() + "Z"
        h.created_at = now
        h.updated_at = now
        HYPOTHESES.append(h)
        return {"id": h.id, "message": "假设创建成功"}

    @router.put("/hypotheses/{hypothesis_id}", summary="更新假设")
    async def update_hypothesis(hypothesis_id: int, h: Hypothesis):
        for i, existing in enumerate(HYPOTHESES):
            if existing.id == hypothesis_id:
                h.id = hypothesis_id
                h.updated_at = datetime.utcnow().isoformat() + "Z"
                HYPOTHESES[i] = h
                return {"message": "假设更新成功"}
        raise HTTPException(status_code=404, detail="假设不存在")

    @router.delete("/hypotheses/{hypothesis_id}", summary="删除假设")
    async def delete_hypothesis(hypothesis_id: int):
        for i, h in enumerate(HYPOTHESES):
            if h.id == hypothesis_id:
                HYPOTHESES.pop(i)
                return {"message": "删除成功"}
        raise HTTPException(status_code=404, detail="假设不存在")

    # === 实验设计 ===

    @router.get("/experiments", summary="获取实验列表")
    async def list_experiments(hypothesis_id: int | None = None):
        if hypothesis_id:
            results = [e for e in EXPERIMENTS if e.hypothesis_id == hypothesis_id]
        else:
            results = EXPERIMENTS
        return {"experiments": results, "total": len(results)}

    @router.post("/experiments", summary="创建实验设计")
    async def create_experiment(e: ExperimentDesign):
        global _next_experiment_id
        e.id = _next_experiment_id
        _next_experiment_id += 1
        e.created_at = datetime.utcnow().isoformat() + "Z"
        EXPERIMENTS.append(e)
        # 更新假设状态为"验证中"
        for h in HYPOTHESES:
            if h.id == e.hypothesis_id and h.status == "待验证":
                h.status = "验证中"
        return {"id": e.id, "message": "实验创建成功"}

    # === 验证结果 ===

    @router.post("/validate", summary="提交验证结果")
    async def submit_validation(result: ValidationResult):
        global _next_result_id
        result.id = _next_result_id
        _next_result_id += 1
        result.validated_at = datetime.utcnow().isoformat() + "Z"
        VALIDATION_RESULTS.append(result)
        # 更新假设状态
        for h in HYPOTHESES:
            if h.id == result.hypothesis_id:
                h.status = "已验证"
                h.updated_at = datetime.utcnow().isoformat() + "Z"
        return {"id": result.id, "message": "验证结果已记录"}

    @router.get("/results/{hypothesis_id}", summary="获取假设的验证结果")
    async def get_results(hypothesis_id: int):
        results = [r for r in VALIDATION_RESULTS if r.hypothesis_id == hypothesis_id]
        return {"results": results, "total": len(results)}

    @router.get("/gate-check/{hypothesis_id}", summary="门禁检查 — 判断假设能否进入下一阶段")
    async def gate_check(hypothesis_id: int):
        """综合判断假设是否通过门禁：验证结果 + 置信度 + 风险评分"""
        h = _find_hypothesis(hypothesis_id)
        if not h:
            raise HTTPException(status_code=404, detail="假设不存在")

        results = [r for r in VALIDATION_RESULTS if r.hypothesis_id == hypothesis_id]
        if not results:
            return {"passed": False, "reason": "尚无验证结果", "hypothesis": h, "gate": "locked"}

        latest = results[-1]
        score = _compute_gate_score(latest, h)
        passed = score >= 60
        return {
            "passed": passed,
            "score": score,
            "threshold": 60,
            "hypothesis": h,
            "latest_result": latest,
            "gate": "open" if passed else "blocked",
            "recommendation": "假设验证通过，建议进入执行阶段" if passed else "建议重新设计实验或调整假设",
        }

    print("[M2] 假设验证门禁路由已加载 ✓")
    print(f"[M2] 预设假设: {len(HYPOTHESES)} 条 | 实验: {len(EXPERIMENTS)} 个")

except ImportError:
    print("[M2] FastAPI未安装，跳过路由注册（数据层已就绪）")
    router = None
