"""
链客宝 - ABACC销售话术模板引擎
================================
ABACC五步说服逻辑 + 张力武器库 后端API

注入点：销售话术模板CRUD + ABACC框架 + 张力武器库数据服务
规则：纯新增，不修改现有业务逻辑
"""

from datetime import datetime

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class AbaccStep(BaseModel):
    """ABACC单步话术"""

    step_id: str  # attention / before / after / curiosity / call_action
    title: str
    template: str
    examples: list[str] = []
    tips: list[str] = []


class SalesScript(BaseModel):
    """完整话术模板"""

    id: int | None = None
    name: str
    scenario: str  # 适用场景 e.g. 面销/电销/展会
    target_role: str  # 目标角色 e.g. CEO/市场总监
    abacc: list[AbaccStep]  # 五步框架
    tension_score: int | None = None  # 张力评分 0-100
    tags: list[str] = []
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# ABACC五步预设模板库（内存存储，可替换为数据库）
# ---------------------------------------------------------------------------

ABACC_PRESETS: list[SalesScript] = [
    SalesScript(
        id=1,
        name="B2B企业获客-痛点唤醒型",
        scenario="电销/陌拜",
        target_role="市场总监",
        abacc=[
            AbaccStep(
                step_id="attention",
                title="吸引注意 - 破冰开场",
                template="[公司名]在[行业]领域深耕[X]年，最近我们帮助[同类客户]实现了[具体成果]。我只需要30秒介绍一下，您看方便吗？",
                examples=[
                    "张总，我注意到贵司最近在拓展华东市场，对吗？",
                    "李总，你们行业前三的XX公司正在用我们的方案做私域增长，您知道吗？",
                ],
                tips=["首句带出客户行业关键词", "用具体数据或竞品信息破冰", "控制语速给客户反应时间"],
            ),
            AbaccStep(
                step_id="before",
                title="痛点描述 - 痛苦具象化",
                template="目前很多[角色]面临[具体痛点1]、[具体痛点2]的问题，导致[量化损失]。您是否也有类似感受？",
                examples=[
                    "现在销售团队花30%的时间在录信息而不是成交，每月隐性损失超过5万，您团队有这种情况吗？",
                    "市场部线索到转化率不到3%，60%的线索直接浪费了，对吗？",
                ],
                tips=["痛点要具体到金额/时间占比", "用反问句让客户确认", "先认同再引导"],
            ),
            AbaccStep(
                step_id="after",
                title="改变后状态 - 解决方案可视化",
                template="想象一下，当您使用[产品名]之后，[痛点1]被解决，[痛点2]被优化——具体来说，[量化收益]。",
                examples=[
                    "使用链客宝后，销售自动完成信息录入和人脉匹配，团队效率提升40%，每周多出1天用于成交。",
                    "线索自动清洗+分级+跟进提醒，转化率从3%提升到12%，单月多签8单。",
                ],
                tips=["用'当您...之后'构建心理画面", "量化数据要可信附客户案例", "对比之前vs之后"],
            ),
            AbaccStep(
                step_id="curiosity",
                title="激发好奇 - 差异化卖点",
                template="和传统方案不同的是，我们的[独特能力]让您可以[独特价值]。最特别的一点是[杀手锏]。",
                examples=[
                    "链客宝不只是名片工具——它内置AI供需匹配引擎，自动推荐有真实需求的企业，这在行业里是唯一的。",
                    "别的工具只能管客户，链客宝能帮您'找'客户——AI每天扫描3000+企业需求信号，精准推送匹配。",
                ],
                tips=["突出唯一性（唯一/首创）", "用对比放大差异感", "制造信息差引起兴趣"],
            ),
            AbaccStep(
                step_id="call_action",
                title="号召行动 - 下一步引导",
                template="这样，我给您发一份[具体资料]，里面有[价值承诺]。您看是加个微信还是发邮箱？",
                examples=[
                    "我让技术团队给您开一个免费试用账号，您亲自体验一下AI匹配的效果，最快今天就能上线。",
                    "下周三我们有一场针对[行业]的线上分享，我给您留个名额？",
                ],
                tips=["二选一提问降低决策成本", "给出具体的下一步动作", "制造紧迫感（名额/时间限制）"],
            ),
        ],
        tension_score=85,
        tags=["B2B", "电销", "获客", "高客单价"],
        created_at="2026-06-01T08:00:00Z",
    ),
    SalesScript(
        id=2,
        name="展会快销-快速验证型",
        scenario="展会/沙龙",
        target_role="企业主/高管",
        abacc=[
            AbaccStep(
                step_id="attention",
                title="吸引注意 - 展位破冰",
                template="您好！我们正在做一个[行业]数字化转型的调研，能耽误您2分钟吗？作为感谢，送您一份[小礼品]。",
                examples=["嗨！可以帮我们填一份AI获客效率的问卷吗？2分钟，送您一杯咖啡~"],
            ),
            AbaccStep(
                step_id="before",
                title="痛点描述 - 场景唤醒",
                template="现在获客越来越难了对吧？地推成本涨了40%，线上广告ROI越来越低，您是不是也有同感？",
            ),
            AbaccStep(
                step_id="after",
                title="改变后状态 - 现场演示",
                template="如果有一个工具能让您现场扫码就生成电子名片、自动匹配展会上所有潜在客户，您想试试吗？",
            ),
            AbaccStep(
                step_id="curiosity",
                title="激发好奇 - 社交货币",
                template="刚刚有XX公司的VP也扫了我们的码，现场就匹配到了3个意向客户。您要不要也扫一个？",
            ),
            AbaccStep(
                step_id="call_action",
                title="号召行动 - 即刻体验",
                template="扫这个码，10秒生成您的AI数字名片，系统自动帮您找现场匹配客户。来，我教您操作。",
            ),
        ],
        tension_score=72,
        tags=["展会", "快销", "体验"],
        created_at="2026-06-05T10:00:00Z",
    ),
]

# 内存ID计数器
_next_id = 3


def _tension_checks(text: str, re_module) -> list[bool]:
    """构建张力检查规则列表"""
    return [
        _has_digit(text),
        _has_contrast(text),
        _has_pain_point(text),
        _has_call_to_action(text),
        _has_specific_data(text, re_module),
        _has_analogy(text),
        _has_urgency(text),
        _has_social_proof(text),
        _has_future_scene(text),
        _has_rhetorical_question(text),
    ]


def _has_digit(t: str) -> bool:
    return any(c.isdigit() for c in t)


def _has_contrast(t: str) -> bool:
    return any(w in t for w in ["对比", "传统", "而", "vs", "VS", "比"])


def _has_pain_point(t: str) -> bool:
    return any(w in t for w in ["痛点", "问题", "困难", "挑战", "浪费", "损失", "成本高", "效率低"])


def _has_call_to_action(t: str) -> bool:
    return any(w in t for w in ["立即", "现在", "扫码", "点击", "注册", "试试", "体验"])


def _has_specific_data(t: str, re_module) -> bool:
    return bool(re_module.search(r"\d+%|\d+倍|\d+元|\d+单|\d+家|\d+天|\d+小时|\d+分钟", t))


def _has_analogy(t: str) -> bool:
    return any(w in t for w in ["相当于", "等于", "好比", "就像", "如同"])


def _has_urgency(t: str) -> bool:
    return any(w in t for w in ["限时", "仅剩", "最后", "名额", "错过"])


def _has_social_proof(t: str) -> bool:
    return any(w in t for w in ["同行", "TOP", "标杆", "已经有", "增长"])


def _has_future_scene(t: str) -> bool:
    return any(w in t for w in ["想象", "当您", "半年后", "到那时"])


def _has_rhetorical_question(t: str) -> bool:
    return "?" in t or "？" in t or "对吗" in t or "是吧" in t


# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------


class DataAugmenter(BaseModel):
    """数据增强器"""

    mode: str  # analogy / unit_transform / comparison
    input_value: str
    output: str
    description: str


TENSION_WEAPONS = {
    "data_augmenter": {
        "analogy": {
            "description": "类比模式 - 将抽象数据变成直观感受",
            "examples": [
                {"input": "年节省500小时", "output": "相当于62个工作日，每年多出3个月做核心业务"},
                {"input": "转化率提升5%", "output": "5%意味着在1000个线索里多成交50单，按客单价2万算=100万营收"},
                {"input": "效率提升30%", "output": "同样是8小时，别人做5单，你做6.5单——每月多出33单"},
            ],
        },
        "unit_transform": {
            "description": "单位变换 - 换成更有冲击力的计价单位",
            "examples": [
                {"input": "月费999元", "output": "每天33元，少喝一杯奶茶就能获得AI获客能力"},
                {"input": "年费12000元", "output": "每客户成本1元，你一年只需要多签1个客户就回本"},
                {"input": "团队投入40小时/月", "output": "每天1.3小时，一台手机就能完成的工作量"},
            ],
        },
        "comparison": {
            "description": "对比模式 - 放大前后差距",
            "examples": [
                {"input": "传统方式3天匹配5家", "output": "链客宝3分钟推送50家——效率提升60倍"},
                {"input": "单个获客成本200元", "output": "链客宝单次匹配成本不到2元——省了99%"},
                {"input": "手动录入错误率15%", "output": "AI自动识别准确率99.7%——提升6.6倍"},
            ],
        },
    },
    "magic_words": {
        "urgency": {"name": "紧迫感引导词", "words": ["立即", "限时", "仅剩", "最后机会", "错过今天", "名额紧张"]},
        "social_proof": {
            "name": "社会认同引导词",
            "words": ["同行业TOP", "已有X家企业", "某总也在用", "行业标杆选择", "增长最快的"],
        },
        "specificity": {"name": "具象化引导词", "words": ["具体来说", "例如", "实际上", "数字上看", "换句话说"]},
        "contrast": {"name": "对比引导词", "words": ["相比之下", "传统方式", "而我们的", "别人还在", "我们已经"]},
        "future_pacing": {
            "name": "未来投射引导词",
            "words": ["想象一下", "当您使用后", "半年后的您", "到那时", "这意味着"],
        },
    },
    "tension_check": {
        "low": {
            "score_range": "0-40",
            "label": "低张力",
            "description": "话术平淡，缺乏记忆点和行动驱动力",
            "symptoms": ["没有具体数据", "痛点不明确", "没有对比", "号召行动模糊"],
            "fixes": ["加入量化数据", "使用数据增强器", "增加对比句式", "明确下一步动作"],
        },
        "medium": {
            "score_range": "41-70",
            "label": "中张力",
            "description": "有一定说服力，但冲击力不够",
            "symptoms": ["数据不够直观", "痛点描述有但不够痛", "差异化不够突出"],
            "fixes": ["用类比模式增强数据", "加入紧迫感引导词", "强化唯一性表述"],
        },
        "high": {
            "score_range": "71-100",
            "label": "高张力",
            "description": "话术有力，具象且有行动驱动",
            "symptoms": [],
            "fixes": ["保持迭代", "收集客户反馈做A/B测试"],
        },
    },
}

# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/api/sales-script", tags=["销售话术模板"])

    # === ABACC话术CRUD ===

    @router.get("/presets", summary="获取ABACC预设模板列表")
    async def list_presets():
        """返回所有预设话术模板"""
        return {"presets": ABACC_PRESETS, "total": len(ABACC_PRESETS)}

    @router.get("/presets/{script_id}", summary="获取单个话术模板详情")
    async def get_preset(script_id: int):
        for s in ABACC_PRESETS:
            if s.id == script_id:
                return s
        raise HTTPException(status_code=404, detail="话术模板不存在")

    @router.post("/scripts", summary="创建自定义话术模板")
    async def create_script(script: SalesScript):
        global _next_id
        script.id = _next_id
        _next_id += 1
        script.created_at = datetime.utcnow().isoformat() + "Z"
        script.updated_at = script.created_at
        ABACC_PRESETS.append(script)
        return {"id": script.id, "message": "话术模板创建成功"}

    @router.put("/scripts/{script_id}", summary="更新话术模板")
    async def update_script(script_id: int, script: SalesScript):
        for i, s in enumerate(ABACC_PRESETS):
            if s.id == script_id:
                script.id = script_id
                script.updated_at = datetime.utcnow().isoformat() + "Z"
                ABACC_PRESETS[i] = script
                return {"message": "更新成功"}
        raise HTTPException(status_code=404, detail="话术模板不存在")

    @router.delete("/scripts/{script_id}", summary="删除话术模板")
    async def delete_script(script_id: int):
        for i, s in enumerate(ABACC_PRESETS):
            if s.id == script_id:
                ABACC_PRESETS.pop(i)
                return {"message": "删除成功"}
        raise HTTPException(status_code=404, detail="话术模板不存在")

    # === 张力武器库 ===

    @router.get("/weapons/data-augmenter", summary="获取数据增强器示例")
    async def get_data_augmenter(mode: str | None = None):
        """数据增强器：类比/单位变换/对比三种模式"""
        if mode and mode in TENSION_WEAPONS["data_augmenter"]:
            return {"mode": mode, "data": TENSION_WEAPONS["data_augmenter"][mode]}
        return TENSION_WEAPONS["data_augmenter"]

    @router.get("/weapons/magic-words", summary="获取话术引导词推荐")
    async def get_magic_words(category: str | None = None):
        """话术引导词推荐：按分类筛选"""
        if category and category in TENSION_WEAPONS["magic_words"]:
            return {"category": category, "data": TENSION_WEAPONS["magic_words"][category]}
        return TENSION_WEAPONS["magic_words"]

    @router.get("/weapons/tension-check", summary="获取张力自检评分标准")
    async def get_tension_check(score: int | None = None):
        """张力自检评分：给定分数返回对应等级建议"""
        if score is not None:
            if score <= 40:
                level = "low"
            elif score <= 70:
                level = "medium"
            else:
                level = "high"
            return {"score": score, "level": level, "detail": TENSION_WEAPONS["tension_check"][level]}
        return TENSION_WEAPONS["tension_check"]

    @router.post("/weapons/analyze", summary="分析话术张力并评分")
    async def analyze_tension(text: str):
        """
        分析给定话术文本的张力评分（基于规则匹配）
        返回评分、等级和改进建议
        """
        score = _calculate_tension_score(text)
        if score <= 40:
            level = "low"
        elif score <= 70:
            level = "medium"
        else:
            level = "high"
        return {
            "score": score,
            "level": level,
            "label": TENSION_WEAPONS["tension_check"][level]["label"],
            "description": TENSION_WEAPONS["tension_check"][level]["description"],
            "symptoms": TENSION_WEAPONS["tension_check"][level]["symptoms"],
            "fixes": TENSION_WEAPONS["tension_check"][level]["fixes"],
        }

    def _calculate_tension_score(text: str) -> int:
        """简单的规则评分引擎"""
        import re

        score = 50  # 基准分
        checks = _tension_checks(text, re)
        for check_passed in checks:
            if check_passed:
                score += 5
        return min(score, 100)

    print("[ABACC] 销售话术模板路由已加载 ✓")
    print(f"[ABACC] 预设模板: {len(ABACC_PRESETS)} 套")
    print("[ABACC] 张力武器库: 数据增强器3模式 + 引导词5分类 + 自检3阶")

except ImportError:
    print("[ABACC] FastAPI未安装，跳过路由注册（数据层已就绪）")
    router = None
