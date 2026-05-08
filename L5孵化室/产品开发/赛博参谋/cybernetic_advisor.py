#!/usr/bin/env python3
"""
赛博参谋 (Cybernetic Advisor) v0.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
输入创业想法 → 输出结构化6步沙盘推演报告
纯 Python 标准库 CLI 工具
"""

import sys
import json
import textwrap
import argparse
from pathlib import Path

# ─── 核心函数库 ───────────────────────────────────────────────

def box(text, title=None, width=72, style="─"):
    """用 ASCII 线框包裹文本"""
    lines = text.split("\n")
    inner_w = width - 4
    result = []
    if title:
        top = f"┌{style * 2} {title} {style * (inner_w - len(title) - 2)}┐"
    else:
        top = f"┌{style * (width - 2)}┐"
    result.append(top)
    for line in lines:
        # 手动换行处理
        while len(line) > inner_w:
            result.append(f"│ {line[:inner_w]} │")
            line = line[inner_w:]
        result.append(f"│ {line:<{inner_w}} │")
    result.append(f"└{style * (width - 2)}┘")
    return "\n".join(result)


def separator(title="", width=72):
    """打印分隔线"""
    if title:
        return f"├─ {title} " + "─" * (width - len(title) - 4) + "┤"
    return f"├{'─' * (width - 2)}┤"


def heading(text, level=1, width=72):
    """打印标题"""
    if level == 1:
        return f"\n┌{'═' * (width - 2)}┐\n│  {text:<{width-4}}│\n└{'═' * (width - 2)}┘"
    elif level == 2:
        return f"\n╞{'═' * (width - 2)}╡\n│  {text:<{width-4}}│\n╞{'═' * (width - 2)}╡"
    else:
        return f"\n── {text} " + "─" * (width - len(text) - 5)


def score_bar(score, max_score=10, width=20):
    """生成分数条"""
    filled = int(score / max_score * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score}/{max_score}"


# ─── 1. 市场检查 ─────────────────────────────────────────────

MARKET_KEYWORDS = {
    "saas": 2, "sass": 2, "订阅": 2, "订阅制": 2, "月费": 2, "年费": 2,
    "ai": 1.5, "人工智能": 1.5, "大模型": 1.5, "llm": 1.5, "gpt": 1.5,
    "平台": 1, "marketplace": 1.5, "双边市场": 1.5, "电商": 1,
    "跨境": 1.5, "出海": 1.5, "全球": 1, "海外": 1,
    "自动化": 1.5, "效率": 1, "提效": 1, "降本": 1,
    "内容": 1, "知识付费": 1, "课程": 0.5, "教育": 0.5,
    "私域": 1.5, "社群": 1, "社区": 1,
    "工具": 0.5, "应用": 0.5, "app": 0.5, "小程序": 0.5,
    "b2b": 1.5, "b端": 1.5, "企业服务": 1.5,
    "c端": 1, "消费者": 1, "toc": 1,
    "数据": 1, "分析": 1, "洞察": 1, "dashboard": 1,
    "无代码": 1.5, "低代码": 1.5, "nocode": 1.5,
    "咨询": 0.5, "服务": 0.5, "外包": -0.5,
    "区块链": -1, "nft": -1, "元宇宙": -0.5, "web3": -0.5,
    "社交": 0.5, "泛娱乐": 0, "游戏": 0.5,
}

MARKET_GREEN_FLAGS = [
    "付费", "订阅", "recurring", "复购", "留存的", "黏性",
    "规模化", "边际成本", "杠杆", "网络效应", "飞轮",
    "刚需", "痛点", "高频", "强需求",
]

MARKET_RED_FLAGS = [
    "补贴", "烧钱", "免费", "流量变现", "先做大再变现",
    "教育市场", "改变习惯", "等政策", "靠关系",
]


def market_check(idea_text: str) -> dict:
    """市场检查：关键词匹配 + 评分"""
    text_lower = idea_text.lower()
    score = 5.0  # 基础分

    # 关键词匹配加分/减分
    matched = {}
    for kw, val in MARKET_KEYWORDS.items():
        if kw in text_lower:
            score += val
            matched[kw] = val

    # 绿旗信号
    green_flags = []
    for flag in MARKET_GREEN_FLAGS:
        if flag in text_lower:
            green_flags.append(flag)
            score += 1.0

    # 红旗信号
    red_flags = []
    for flag in MARKET_RED_FLAGS:
        if flag in text_lower:
            red_flags.append(flag)
            score -= 1.5

    score = max(1, min(10, round(score, 1)))

    # 判断
    if score >= 7:
        verdict = "✅ 市场契合度良好，值得深入推演"
    elif score >= 5:
        verdict = "⚠️ 市场信号中性，建议调整定位或验证需求"
    else:
        verdict = "❌ 市场风险较高，建议重新构思"

    return {
        "score": score,
        "matched_keywords": matched,
        "green_flags": green_flags,
        "red_flags": red_flags,
        "verdict": verdict,
    }


# ─── 2. 需求验证 ─────────────────────────────────────────────

DTC_CHECKLIST = [
    ("用户画像", "是否清晰定义了目标用户是谁？（年龄、身份、场景）"),
    ("场景频率", "需求发生频率如何？日频 > 周频 > 月频"),
    ("付费意愿", "用户是否已经为类似方案付过费？"),
    ("替代方案", "用户目前用什么方法解决此问题？（竞品/手工/忍着）"),
    ("痛点强度", "这个问题不解决会怎样？痛 / 很痛 / 剧痛"),
    ("需求真伪", "是真需求还是伪需求？（用户嘴上说 vs 实际行为）"),
    ("规模验证", "目标用户群体规模是否足够大？（1000人真粉 vs 100万路人）"),
    ("第一批用户", "能否找到第一批 10 个愿意付费的用户？"),
    ("获客路径", "是否知道去哪找这些用户？渠道是否可复制？"),
    ("冷启动", "冷启动阶段如何验证需求？MVP 是什么？"),
]


def demand_validation(idea_text: str) -> dict:
    """需求验证：DTC checklist"""
    text_lower = idea_text.lower()
    idea_len = len(idea_text)
    passed = 0
    details = []

    # 每项检查的信号词
    CHECK_SIGNALS = [
        (["用户", "目标", "人群", "人群画像", "用户画像"], "用户画像"),
        (["高频", "频率", "日频", "周频", "每天", "每周", "反复", "频次"], "场景频率"),
        (["付费", "付费意愿", "花钱", "买单", "客单价", "arpu"], "付费意愿"),
        (["替代", "现有方案", "竞品", "目前", "怎么解决"], "替代方案"),
        (["痛点", "刚需", "痛", "焦虑", "烦恼", "困扰"], "痛点强度"),
        (["需求", "真需求", "伪需求", "真实", "嘴上", "行为"], "需求真伪"),
        (["规模", "市场大小", "tam", "sam", "目标用户数", "1000"], "规模验证"),
        (["第一批", "种子用户", "冷启动", "10个", "首100"], "第一批用户"),
        (["获客", "渠道", "推广", "流量", "用户获取", "增长"], "获客路径"),
        (["mvp", "原型", "验证", "冷启动", "最小产品", "demo"], "冷启动"),
    ]

    for i, ((title, question)) in enumerate(DTC_CHECKLIST, 1):
        signals = CHECK_SIGNALS[i-1][0]
        matched_any = any(sig in text_lower for sig in signals)

        # 想法越长、越具体，默认通过越多项
        auto_pass = idea_len > 60   # 长输入认为经过思考
        half_pass = idea_len > 25   # 中等长度部分通过

        if matched_any or auto_pass or (half_pass and i <= 4):
            passed += 1
            status = "✓"
        elif i <= 2 and idea_len > 15:
            # 前2项给基础通过
            passed += 1
            status = "✓"
        else:
            status = "?"
        details.append(f"  [{status}] {i}. {title}: {question}")
    return {
        "passed": passed,
        "total": len(DTC_CHECKLIST),
        "details": details,
        "pass_rate": round(passed / len(DTC_CHECKLIST) * 100),
    }


# ─── 3. 竞争分析 ─────────────────────────────────────────────

def competitive_analysis(idea_text: str) -> dict:
    """三种套利空间分析"""
    text_lower = idea_text.lower()

    analyses = []

    # 套利类型1：信息套利（我知道但别人不知道）
    info_signals = ["信息", "数据", "知识", "know-how", "knowhow", "专业",
                      "行业经验", "人脉", "独家", "信息差"]
    info_score = sum(1 for s in info_signals if s in text_lower)
    if info_score >= 2 or "出海" in text_lower or "跨境" in text_lower:
        info_level = "强"
        info_note = "存在明显的信息不对称机会，跨境/跨领域套利空间大"
    elif info_score >= 1:
        info_level = "中"
        info_note = "有一定信息优势，可进一步挖掘"
    else:
        info_level = "弱"
        info_note = "信息套利空间不明显，建议寻找其他差异化"
    analyses.append({
        "type": "信息套利",
        "level": info_level,
        "note": info_note,
    })

    # 套利类型2：技术套利（我能但别人不能）
    tech_signals = ["ai", "人工智能", "llm", "大模型", "自动化", "算法",
                     "技术", "模型", "pytorch", "tensorflow", "nlp",
                     "机器人", "rpa", "api", "sdk"]
    tech_score = sum(1 for s in tech_signals if s in text_lower)
    if tech_score >= 3:
        tech_level = "强"
        tech_note = "技术壁垒较高，有护城河潜力"
    elif tech_score >= 1:
        tech_level = "中"
        tech_note = "有一定技术优势，但需要持续投入保持"
    else:
        tech_level = "弱"
        tech_note = "技术套利空间有限，需结合其他优势"
    analyses.append({
        "type": "技术套利",
        "level": tech_level,
        "note": tech_note,
    })

    # 套利类型3：执行套利（我快但我还坚持）
    exec_signals = ["敏捷", "快速", "迭代", "执行", "运营", "服务", "响应",
                     "定制", "本地化", "线下", "服务好", "客户成功"]
    exec_score = sum(1 for s in exec_signals if s in text_lower)
    if exec_score >= 2:
        exec_level = "强"
        exec_note = "执行效率是核心优势，适合以快打慢"
    elif exec_score >= 1:
        exec_level = "中"
        exec_note = "执行层面有优化空间"
    else:
        exec_level = "弱"
        exec_note = "需建立执行层面的竞争优势"
    analyses.append({
        "type": "执行套利",
        "level": exec_level,
        "note": exec_note,
    })

    return {"analyses": analyses}


# ─── 4. 能力评估 ─────────────────────────────────────────────

CAPABILITY_TEMPLATES = {
    "技术": {
        "强": "已具备核心技术能力，可形成技术壁垒",
        "中": "技术能力可支撑 MVP，但需持续强化",
        "弱": "技术是短板，建议找技术合伙人或用无代码方案",
    },
    "产品": {
        "强": "产品思维成熟，能快速做出用户想要的东西",
        "中": "有基本产品能力，建议多做用户调研",
        "弱": "产品能力不足，建议先用原型验证",
    },
    "运营": {
        "强": "运营能力强，用户获取和留存有章法",
        "中": "运营能力一般，建议聚焦单一渠道",
        "弱": "运营经验不足，建议先学案例或找合伙人",
    },
    "行业": {
        "强": "行业认知深入，知道水下的坑和机会",
        "中": "有一定行业了解，但深度不够",
        "弱": "行业经验欠缺，建议先兼职调研3个月",
    },
    "资源": {
        "强": "资金/人脉/渠道资源充足，启动条件成熟",
        "中": "有一定资源但不够充裕，需精打细算",
        "弱": "资源有限，建议走轻资产路线",
    },
}


def capability_assessment(idea_text: str) -> dict:
    """降维能力碾压分析"""
    # 根据想法文本粗略评估能力等级
    text_lower = idea_text.lower()

    assessments = []
    for dim, levels in CAPABILITY_TEMPLATES.items():
        # heuristic 评分
        if dim == "技术":
            score = sum(1 for w in ["ai", "技术", "算法", "模型", "自动化", "代码"] if w in text_lower)
        elif dim == "产品":
            score = sum(1 for w in ["产品", "体验", "设计", "ux", "ui", "交互"] if w in text_lower)
        elif dim == "运营":
            score = sum(1 for w in ["运营", "增长", "流量", "私域", "社群", "内容"] if w in text_lower)
        elif dim == "行业":
            score = sum(1 for w in ["行业", "经验", "专业", "专家", "深耕", "多年"] if w in text_lower)
        elif dim == "资源":
            score = sum(1 for w in ["融资", "投资", "资源", "人脉", "资金", "团队"] if w in text_lower)
        else:
            score = 0

        if score >= 3:
            level = "强"
        elif score >= 1:
            level = "中"
        else:
            level = "弱"

        assessments.append({
            "dimension": dim,
            "level": level,
            "advice": levels[level],
            "score": score,
        })

    return {"assessments": assessments}


# ─── 5. 最小路径 ─────────────────────────────────────────────

def minimal_path(idea_text: str) -> dict:
    """小闭环三阶验证规划"""
    text_lower = idea_text.lower()

    # 根据想法内容推荐验证方式 - 优先级：内容/知识 > 电商/跨境 > AI > 工具 > 平台 > 通用
    if any(w in text_lower for w in ["内容", "知识付费", "课程", "社群", "社区", "订阅"]):
        phase1 = "写 1 篇深度文章/录制 1 个短视频，测阅读量和互动"
        phase2 = "做 1 期付费小课/社群，看付费转化率"
        phase3 = "跑通内容-引流-转化-交付的完整循环"
    elif any(w in text_lower for w in ["电商", "跨境", "出海", "卖货"]):
        phase1 = "用 Shopify / 独立站 上架第一个产品，测试转化率"
        phase2 = "找到 1-2 个爆款 SKU，验证复购率"
        phase3 = "跑通供应链+物流+售后全流程"
    elif any(w in text_lower for w in ["ai", "人工智能", "llm", "大模型", "模型"]):
        phase1 = "写 1 篇深度文章/录制 1 个短视频，测阅读量和互动"
        phase2 = "做 1 期付费小课/社群，看付费转化率"
        phase3 = "跑通内容-引流-转化-交付的完整循环"
    elif any(w in text_lower for w in ["工具", "saas", "sass", "订阅"]):
        phase1 = "做 1 个落地页+等待列表，测用户兴趣"
        phase2 = "手工服务 3-5 个用户（Wizard of Oz），验证价值"
        phase3 = "开发 MVP 并获取第一批付费用户"
    elif any(w in text_lower for w in ["平台", "marketplace", "双边"]):
        phase1 = "单边切入：先服务供给端或需求端的一方"
        phase2 = "跑通 5 笔最小交易，验证平台撮合效率"
        phase3 = "找到冷启动的原子网络（最小规模供需匹配）"
    else:
        phase1 = "找到 10 个目标用户做 30 分钟深度访谈"
        phase2 = "做出最简单的 MVP 让 5 个人试用"
        phase3 = "找到 1 个愿意付费的种子用户"

    return {
        "phase1": {
            "title": "验证需求真伪",
            "action": phase1,
            "duration": "1-2 周",
            "cost": "低 (< ¥1000)",
        },
        "phase2": {
            "title": "验证解决方案",
            "action": phase2,
            "duration": "2-4 周",
            "cost": "中 (¥1000-¥5000)",
        },
        "phase3": {
            "title": "验证商业模式",
            "action": phase3,
            "duration": "4-8 周",
            "cost": "中高 (¥5000-¥20000)",
        },
    }


# ─── 6. 终局思考 ─────────────────────────────────────────────

def endgame_thinking(idea_text: str) -> dict:
    """大闭环公式推演"""
    text_lower = idea_text.lower()

    # 推导北极星指标
    if any(w in text_lower for w in ["saas", "sass", "订阅", "工具"]):
        polaris = "月活跃付费用户数 (MAPU)"
        formula = "收入 = 活跃用户数 × ARPU × 留存率^时间"
        endgame = "成为该垂直领域的标准工具，年经常性收入 (ARR) 破亿"
    elif any(w in text_lower for w in ["平台", "marketplace", "双边"]):
        polaris = "月交易总额 (GMV)"
        formula = "价值 = 供需匹配效率 × 交易频次 × 佣金率"
        endgame = "网络效应形成后，成为品类第一的交易平台"
    elif any(w in text_lower for w in ["内容", "知识付费", "社群"]):
        polaris = "用户终身价值 (LTV)"
        formula = "收入 = 精准用户数 × 客单价 × 内容复购率"
        endgame = "建立 IP 资产 + 内容矩阵，形成持续收入流"
    elif any(w in text_lower for w in ["电商", "跨境", "出海", "卖货"]):
        polaris = "单用户购买频次 × 毛利率"
        formula = "利润 = (流量 × 转化率 × 客单价 - 成本) × 复购系数"
        endgame = "建立品牌护城河 + 供应链壁垒，实现品牌溢价"
    elif any(w in text_lower for w in ["ai", "人工智能", "llm", "模型"]):
        polaris = "模型使用频次 × 数据飞轮增速"
        formula = "壁垒 = 模型效果 × 数据规模 × 用户粘性"
        endgame = "数据飞轮驱动，模型越用越强，形成 AI Native 产品"
    else:
        polaris = "月活跃用户数 (MAU)"
        formula = "价值 = 用户规模 × 单用户价值 × 网络效应系数"
        endgame = "规模化后建立品牌认知和用户习惯壁垒"

    # 终局思考的三个问题
    questions = [
        "这个生意 5 年后还存在吗？市场是变大还是变小？",
        "如果巨头进场，你的护城河是什么？",
        "假设做成了，这是你想要的 lifestyle 还是 exit？",
    ]

    # 大闭环公式
    def calc_potential(formula_text, idea_len):
        """简单的潜力估算"""
        # 基础分来自想法长度（表示思考深度）
        base = min(5, idea_len * 0.08)
        # 关键词加分
        kw_bonus = sum(1.5 for w in ["规模化", "复购", "网络效应", "壁垒", "飞轮",
                                      "护城河", "高频", "刚需", "爆发", "增长"] if w in text_lower)
        # SaaS/AI/平台等模式加分
        model_bonus = 2 if any(w in text_lower for w in ["saas", "订阅", "平台", "marketplace"]) else 0
        model_bonus += 1 if any(w in text_lower for w in ["ai", "人工智能", "自动化"]) else 0
        return min(10, round(base + kw_bonus + model_bonus, 1))

    potential = calc_potential(formula, len(idea_text))

    return {
        "polaris": polaris,
        "formula": formula,
        "endgame_scenario": endgame,
        "potential_score": potential,
        "questions": questions,
    }


# ─── 主推演函数 ─────────────────────────────────────────────

def full_report(idea_text: str) -> dict:
    """执行完整的6步沙盘推演"""
    report = {
        "idea": idea_text,
        "market": market_check(idea_text),
        "demand": demand_validation(idea_text),
        "competition": competitive_analysis(idea_text),
        "capability": capability_assessment(idea_text),
        "path": minimal_path(idea_text),
        "endgame": endgame_thinking(idea_text),
    }

    # 综合评分 (每个子项都是 0-10 分制，加权平均)
    comp_score = sum(
        7 if a["level"] == "强" else 5 if a["level"] == "中" else 3
        for a in report["competition"]["analyses"]
    ) / 3
    cap_score = sum(
        8 if a["level"] == "强" else 5 if a["level"] == "中" else 3
        for a in report["capability"]["assessments"]
    ) / 5

    weights = [0.25, 0.15, 0.15, 0.15, 0.15, 0.15]
    scores = [
        report["market"]["score"],                        # 市场 0-10
        report["demand"]["pass_rate"] / 10,              # 需求 0-10
        comp_score,                                       # 竞争 0-10
        cap_score,                                        # 能力 0-10
        report["endgame"]["potential_score"],             # 终局 0-10
    ]
    # 最小路径不计入评分，但用于建议
    overall = round(sum(s * w for s, w in zip(scores, weights)), 1)
    overall = max(1, min(10, overall))

    report["overall_score"] = overall
    return report


# ─── 报告格式化 ─────────────────────────────────────────────

def format_report(report: dict) -> str:
    """格式化为美观的终端 ASCII 报告"""
    W = 72
    lines = []

    # ── 头部 ──
    lines.append("")
    lines.append(f"╔{'═' * (W-2)}╗")
    lines.append(f"║{' ' * (W-2)}║")
    lines.append(f"║  {'🧠 赛博参谋 Cybernetic Advisor v0.1':<{W-4}}║")
    lines.append(f"║  {'沙盘推演报告':<{W-4}}║")
    lines.append(f"║{' ' * (W-2)}║")
    lines.append(f"╠{'═' * (W-2)}╣")
    lines.append(f"║  输入想法: {textwrap.shorten(report['idea'], width=W-14)}{' ' * max(0, W-14-len(textwrap.shorten(report['idea'], width=W-14)))}║")
    lines.append(f"╚{'═' * (W-2)}╝")

    # ── 综合评分 ──
    score = report["overall_score"]
    lines.append("")
    lines.append(box(
        f"\n  可行性综合评分\n\n"
        f"  {score_bar(score, 10, 30)}\n\n"
        f"  {'✅ 强烈推荐，可以启动' if score >= 8 else '⚠️ 有潜力，建议优化' if score >= 5 else '❌ 风险较高，建议重新构思'}\n",
        title="📊 综合评估",
        width=W,
    ))

    # ── 1. 市场检查 ──
    m = report["market"]
    mk_str = ", ".join(f"{k}(+{v})" for k, v in m["matched_keywords"].items()) if m["matched_keywords"] else "无特定匹配"
    lines.append("")
    lines.append(heading("1. 市场检查 —— 想法是否契合市场", level=2, width=W))
    lines.append(f"  评分: {score_bar(m['score'], 10, 25)}")
    lines.append(f"  匹配关键词: {mk_str}")
    if m["green_flags"]:
        lines.append(f"  🟢 积极信号: {', '.join(m['green_flags'])}")
    if m["red_flags"]:
        lines.append(f"  🔴 风险信号: {', '.join(m['red_flags'])}")
    lines.append(f"  判断: {m['verdict']}")

    # ── 2. 需求验证 ──
    d = report["demand"]
    lines.append("")
    lines.append(heading("2. 需求验证 —— DTC Checklist", level=2, width=W))
    lines.append(f"  通过率: {d['passed']}/{d['total']} ({d['pass_rate']}%)")
    for detail in d["details"][:5]:  # 只显示前5条，保持简洁
        lines.append(detail)
    lines.append(f"  ...（共 {d['total']} 项，通过 {d['passed']} 项）")

    # ── 3. 竞争分析 ──
    c = report["competition"]
    lines.append("")
    lines.append(heading("3. 竞争分析 —— 三种套利空间", level=2, width=W))
    for a in c["analyses"]:
        level_icon = "🟢" if a["level"] == "强" else "🟡" if a["level"] == "中" else "🔴"
        lines.append(f"  {level_icon} {a['type']}: {a['level']} —— {a['note']}")

    # ── 4. 能力评估 ──
    ca = report["capability"]
    lines.append("")
    lines.append(heading("4. 能力评估 —— 降维能力碾压分析", level=2, width=W))
    for a in ca["assessments"]:
        level_icon = "🟢" if a["level"] == "强" else "🟡" if a["level"] == "中" else "🔴"
        lines.append(f"  {level_icon} {a['dimension']}: {a['level']} —— {a['advice']}")

    # ── 5. 最小路径 ──
    p = report["path"]
    lines.append("")
    lines.append(heading("5. 最小路径 —— 小闭环三阶验证规划", level=2, width=W))
    phases = [
        ("第1阶", p["phase1"]["title"], p["phase1"]["action"], p["phase1"]["duration"], p["phase1"]["cost"]),
        ("第2阶", p["phase2"]["title"], p["phase2"]["action"], p["phase2"]["duration"], p["phase2"]["cost"]),
        ("第3阶", p["phase3"]["title"], p["phase3"]["action"], p["phase3"]["duration"], p["phase3"]["cost"]),
    ]
    for i, (label, title, action, duration, cost) in enumerate(phases, 1):
        lines.append(f"  ┌{'─' * 40}┐")
        lines.append(f"  │ {label}: {title:<32}│")
        lines.append(f"  │ 行动: {textwrap.shorten(action, width=36):<36}│")
        lines.append(f"  │ 耗时: {duration:<8}  成本: {cost:<14}│")
        lines.append(f"  └{'─' * 40}┘")

    # ── 6. 终局思考 ──
    e = report["endgame"]
    lines.append("")
    lines.append(heading("6. 终局思考 —— 大闭环公式推演", level=2, width=W))
    lines.append(f"  北极星指标: {e['polaris']}")
    lines.append(f"  核心公式: {e['formula']}")
    lines.append(f"  终局场景: {e['endgame_scenario']}")
    lines.append(f"  潜力评分: {score_bar(e['potential_score'], 10, 20)}")
    lines.append(f"  自检三问:")
    for i, q in enumerate(e["questions"], 1):
        lines.append(f"    {i}. {q}")

    # ── 尾部 ──
    lines.append("")
    lines.append(f"╔{'═' * (W-2)}╗")
    lines.append(f"║  📋 推演完成  |  综合评分: {report['overall_score']}/10{' ' * (W-32)}║")
    lines.append(f"║  提醒: 沙盘推演仅作为决策参考，不构成投资建议{' ' * (W-42)}║")
    lines.append(f"╚{'═' * (W-2)}╝")
    lines.append("")

    return "\n".join(lines)


# ─── 命令行入口 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="赛博参谋 Cybernetic Advisor v0.1 — AI 沙盘推演工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python3 cybernetic_advisor.py "做一个 AI 驱动的跨境电商工具"
              python3 cybernetic_advisor.py "出海知识付费社群" --output report.md
              python3 cybernetic_advisor.py  # 交互模式
        """),
    )
    parser.add_argument("idea", nargs="?", help="创业想法（不提供则进入交互模式）")
    parser.add_argument("--output", "-o", help="输出到文件（如 report.md）")
    parser.add_argument("--json", "-j", action="store_true", help="以 JSON 格式输出结构化数据")

    args = parser.parse_args()

    # ── 获取想法 ──
    idea = args.idea
    if not idea:
        print("")
        print(f"╔{'═' * 60}╗")
        print(f"║  {'🧠 赛博参谋 Cybernetic Advisor v0.1':<58}║")
        print(f"║  {'交互模式':<58}║")
        print(f"╚{'═' * 60}╝")
        print("")
        try:
            idea = input("请输入你的创业想法: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n已退出。")
            sys.exit(0)
        if not idea:
            print("未输入想法，退出。")
            sys.exit(0)

    # ── 运行推演 ──
    report = full_report(idea)

    # ── 输出 ──
    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        output = format_report(report)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output, encoding="utf-8")
        print(f"\n📄 报告已写入: {out_path.resolve()}")
    else:
        print(output)


if __name__ == "__main__":
    main()
