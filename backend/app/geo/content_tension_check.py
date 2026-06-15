#!/usr/bin/env python3
"""
文案张力门禁 · content_tension_check.py
======================================
科学表达·张力武器库(E5)核心评分模块

功能:
  1. 对文案进行多维张力评分
  2. 评分维度: 卖点清晰度·张力强度·口语化程度·数据支撑度·情感感染力
  3. 总张力分 = 加权平均，低于3分标注⚠️
  4. 提供详细的评分报告和改进建议

评分维度说明 (1-5分制):
  - 卖点清晰度 (weight=0.25): 核心卖点是否突出一句话就能说清
  - 张力强度   (weight=0.25): 用词是否有冲击力、有冲突、有反差
  - 口语化程度 (weight=0.20): 是否像人话，避免书面腔/公文腔
  - 数据支撑度 (weight=0.15): 是否有具体数据/案例/对比
  - 情感感染力 (weight=0.15): 能否调动读者情绪(好奇/焦虑/渴望)

用法:
  from app.geo.content_tension_check import check_copy_tension
  result = check_copy_tension("你的文案内容...")
  print(result["summary"])
"""

import re
import json
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════
#  评分权重配置
# ═══════════════════════════════════════════════════════════════

SCORE_WEIGHTS = {
    "卖点清晰度": 0.25,
    "张力强度": 0.25,
    "口语化程度": 0.20,
    "数据支撑度": 0.15,
    "情感感染力": 0.15,
}

# 确保权重之和为1
assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 0.001, "权重之和必须为1"


# ═══════════════════════════════════════════════════════════════
#  信号词库 — 用于自动检测各维度特征
# ═══════════════════════════════════════════════════════════════

# 卖点信号词 (正面: 有明确卖点表达)
CLARITY_POSITIVE_SIGNALS = [
    "核心", "关键", "本质", "根本", "首要", "第一",
    "解决方案", "一站式", "全方位", "全覆盖",
    "只需", "仅需", "一步到位", "一键",
    "效率提升", "成本降低", "转化率", "增长",
    "区别于", "不同于", "相比", "对比传统",
]

# 卖点模糊信号词 (负面: 泛泛而谈)
CLARITY_NEGATIVE_SIGNALS = [
    "各种", "多种", "一些", "某些", "若干",
    "相关", "有关", "等等", "等",
    "一般来说", "某种程度", "一定程度上",
    "众所周知", "毫无疑问",
]

# 张力信号词 (冲击力/冲突/反差)
TENSION_POSITIVE_SIGNALS = [
    "颠覆", "革命", "重塑", "重构", "重新定义",
    "致命", "危机", "痛点", "焦虑", "焦虑",
    "惊人", "不可思议", "震撼", "不得不",
    "正在消亡", "正在消失", "即将被取代",
    "不转型就", "不做就", "错过", "淘汰",
    "真相", "谎言", "误区", "骗局",
    "飙升", "暴跌", "爆发", "崩盘",
    "独家", "首次", "首度", "史无前例",
    "你必须", "千万别", "不要再",
]

# 口语化信号词 (正面: 像人话)
COLLOQUIAL_POSITIVE_SIGNALS = [
    "说白了", "讲真", "说实话", "坦白说",
    "你想想", "你想", "比如", "打个比方",
    "对吧", "是不是", "有没有", "能不能",
    "真的", "确实", "其实", "说白了",
    "我跟你讲", "我跟你说", "你知道吗",
    "就是这个", "说白了就是", "简单来说",
    "啥", "怎么", "什么", "为啥", "咋",
    "大家", "朋友们", "兄弟们",
]

# 书面语信号词 (负面: 需要替换)
COLLOQUIAL_NEGATIVE_SIGNALS = [
    "然而", "此外", "以及", "并且", "因而",
    "综上所述", "由此可见", "换言之",
    "较为", "较为明显", "较为突出",
    "具有一定", "具有一定程度",
    "值得我们", "需要我们",
    "其", "该", "本", "上述",
    "尚未", "是否", "可否",
    "于", "为", "以", "与",
]

# 数据信号词
DATA_POSITIVE_SIGNALS = [
    "%", "百分比", "倍",
    "增长", "提升", "降低", "减少",
    "超过", "达到", "突破",
    "调查显示", "数据显示", "研究表明",
    "统计", "调研", "报告",
    "第1", "第2", "第3", "排名",
    "万", "亿", "千",
]

# 情感信号词
EMOTION_POSITIVE_SIGNALS = [
    "焦虑", "恐慌", "害怕", "担心", "担忧",
    "兴奋", "激动", "期待", "渴望",
    "后悔", "遗憾", "错过",
    "安全感", "信任", "放心", "省心",
    "痛苦", "煎熬", "折磨",
    "轻松", "简单", "爽", "嗨",
    "浪费时间", "浪费钱", "白忙活",
]


def _count_signals(text: str, signals: List[str]) -> int:
    """统计文本中信号词出现的总次数"""
    count = 0
    for signal in signals:
        count += len(re.findall(re.escape(signal), text))
    return count


def _detect_question_ratio(text: str) -> float:
    """检测疑问句比例 — 问答感越强越口语化/有张力"""
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    question_count = sum(1 for s in sentences if '?' in s or '？' in s)
    return question_count / len(sentences)


def _detect_exclamation_ratio(text: str) -> float:
    """检测感叹句比例 — 情感感染力的一个指标"""
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    exclamation_count = sum(1 for s in sentences if '!' in s or '！' in s)
    return exclamation_count / len(sentences)


def _detect_short_sentence_ratio(text: str) -> float:
    """检测短句比例 — 口语化的重要特征"""
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    # 短句: <= 20个字
    short_count = sum(1 for s in sentences if len(s) <= 20)
    return short_count / len(sentences)


def _detect_first_person_ratio(text: str) -> float:
    """检测第一人称使用 — 增强口语感和亲和力"""
    first_person = len(re.findall(r'我|我们|咱', text))
    total_chars = len(text)
    if total_chars == 0:
        return 0.0
    return first_person / total_chars * 100  # 千分比


def _has_numbers(text: str) -> int:
    """检测数字出现次数"""
    return len(re.findall(r'\d+', text))


def _has_comparison(text: str) -> int:
    """检测对比结构出现次数"""
    patterns = [
        r'比.*(好|差|多|少|高|低|快|慢)',
        r'从.*到',
        r'vs\.|VS\.|versus',
        r'相比于|相较于|相对于',
        r'以前.*现在|过去.*如今',
        r'传统.*现代|传统.*AI|传统.*智能',
    ]
    count = 0
    for p in patterns:
        count += len(re.findall(p, text))
    return count


# ═══════════════════════════════════════════════════════════════
#  各维度评分函数 (1-5分)
# ═══════════════════════════════════════════════════════════════

def score_clarity(text: str) -> Tuple[float, str]:
    """
    评分维度1: 卖点清晰度
    评估文案核心卖点是否突出、是否一句话就能说清
    """
    pos = _count_signals(text, CLARITY_POSITIVE_SIGNALS)
    neg = _count_signals(text, CLARITY_NEGATIVE_SIGNALS)
    word_count = len(text)

    # 基础分 3.0
    base = 3.0

    # 正面信号加成: 每3个正面信号 +0.2，上限+1.5
    bonus = min(pos / 3 * 0.2, 1.5)

    # 负面信号扣分: 每个负面信号 -0.2，上限-1.0
    penalty = min(neg * 0.2, 1.0)

    # 长度惩罚: 太短的文案(<50字)卖点可能说不清
    if word_count < 50:
        penalty += 0.3
    # 太长且正面信号少: 可能是啰嗦
    if word_count > 500 and pos < 3:
        penalty += 0.3

    score = base + bonus - penalty
    score = max(1.0, min(5.0, round(score, 1)))

    # 诊断说明
    details = []
    if pos >= 6:
        details.append("卖点表达充分")
    elif pos >= 3:
        details.append("有卖点意识，建议更突出")
    else:
        details.append("缺乏明确的卖点表达")

    if neg >= 3:
        details.append("存在模糊用语，建议删减")

    return score, "; ".join(details) if details else "一般"


def score_tension(text: str) -> Tuple[float, str]:
    """
    评分维度2: 张力强度
    评估用词是否有冲击力、有冲突感、有反差
    """
    pos = _count_signals(text, TENSION_POSITIVE_SIGNALS)
    question_ratio = _detect_question_ratio(text)
    comparison_count = _has_comparison(text)
    word_count = len(text)

    base = 3.0
    bonus = 0.0

    # 张力词加成
    if word_count > 0:
        tension_density = pos / (word_count / 100)  # 每100字的张力词数
        bonus += min(tension_density * 0.3, 1.5)

    # 疑问句加成 (引发读者思考 = 张力)
    bonus += min(question_ratio * 2.0, 0.8)

    # 对比结构加成
    bonus += min(comparison_count * 0.3, 0.5)

    score = base + bonus
    score = max(1.0, min(5.0, round(score, 1)))

    details = []
    if pos >= 8:
        details.append("张力词使用充分")
    elif pos >= 4:
        details.append("有张力意识，可加强")
    else:
        details.append("张力不足，建议加入冲突/反差/危机词")

    if question_ratio > 0.15:
        details.append("疑问句运用良好")
    if comparison_count > 0:
        details.append(f"含{comparison_count}处对比结构")

    return score, "; ".join(details) if details else "一般"


def score_colloquial(text: str) -> Tuple[float, str]:
    """
    评分维度3: 口语化程度
    评估是否像人话，避免书面腔/公文腔
    """
    pos = _count_signals(text, COLLOQUIAL_POSITIVE_SIGNALS)
    neg = _count_signals(text, COLLOQUIAL_NEGATIVE_SIGNALS)
    short_ratio = _detect_short_sentence_ratio(text)
    first_person = _detect_first_person_ratio(text)
    word_count = len(text)

    base = 3.0
    bonus = 0.0
    penalty = 0.0

    # 正面口语信号
    if word_count > 0:
        colloquial_density = pos / (word_count / 100)
        bonus += min(colloquial_density * 0.3, 1.2)

    # 短句比例加成
    bonus += min(short_ratio * 1.0, 0.8)

    # 第一人称加成
    if first_person > 0.5:
        bonus += 0.3

    # 书面语扣分
    if word_count > 0:
        formal_density = neg / (word_count / 100)
        penalty = min(formal_density * 0.3, 1.5)

    score = base + bonus - penalty
    score = max(1.0, min(5.0, round(score, 1)))

    details = []
    if pos >= 4:
        details.append("口语化表达好")
    elif pos >= 2:
        details.append("有一定口语感")
    else:
        details.append("偏书面化，建议加入口语词")

    if neg >= 4:
        details.append(f"含{neg}处书面用语建议替换")
    if short_ratio > 0.5:
        details.append("短句使用得当")
    elif short_ratio < 0.2:
        details.append("长句偏多，建议切短")

    return score, "; ".join(details) if details else "一般"


def score_data_support(text: str) -> Tuple[float, str]:
    """
    评分维度4: 数据支撑度
    是否有具体数据/案例/对比来支撑观点
    """
    data_signals = _count_signals(text, DATA_POSITIVE_SIGNALS)
    number_count = _has_numbers(text)
    comparison_count = _has_comparison(text)

    base = 2.5  # 多数文案数据支撑不足，基础分偏低
    bonus = 0.0

    # 数据信号加成
    bonus += min(data_signals * 0.25, 1.5)

    # 数字加成
    bonus += min(number_count * 0.15, 0.8)

    # 对比结构加成
    bonus += min(comparison_count * 0.2, 0.5)

    score = base + bonus
    score = max(1.0, min(5.0, round(score, 1)))

    details = []
    if data_signals >= 5:
        details.append("数据充分")
    elif data_signals >= 2:
        details.append("有数据支撑")
    else:
        details.append("缺乏数据支撑")

    if number_count >= 3:
        details.append(f"含{number_count}个具体数字")
    if comparison_count > 0:
        details.append(f"含{comparison_count}处对比")

    return score, "; ".join(details) if details else "无数据支撑"


def score_emotion(text: str) -> Tuple[float, str]:
    """
    评分维度5: 情感感染力
    能否调动读者情绪 (好奇/焦虑/渴望/共鸣)
    """
    pos = _count_signals(text, EMOTION_POSITIVE_SIGNALS)
    exclamation_ratio = _detect_exclamation_ratio(text)
    question_ratio = _detect_question_ratio(text)
    word_count = len(text)

    base = 2.5
    bonus = 0.0

    # 情感词加成
    if word_count > 0:
        emotion_density = pos / (word_count / 100)
        bonus += min(emotion_density * 0.4, 1.5)

    # 感叹句加成 (情绪表达)
    bonus += min(exclamation_ratio * 2.0, 0.8)

    # 疑问句加成 (引发情感共鸣)
    bonus += min(question_ratio * 1.0, 0.5)

    # 第一人称加成 (共情)
    first_person = _detect_first_person_ratio(text)
    if first_person > 1.0:
        bonus += 0.3

    score = base + bonus
    score = max(1.0, min(5.0, round(score, 1)))

    details = []
    if pos >= 5:
        details.append("情感词丰富")
    elif pos >= 2:
        details.append("有一定情感表达")
    else:
        details.append("缺乏情感词，建议增加情绪触发")

    if exclamation_ratio > 0.1:
        details.append("感叹运用好")
    if question_ratio > 0.1:
        details.append("疑问句引发共鸣")

    return score, "; ".join(details) if details else "情感平淡"


# ═══════════════════════════════════════════════════════════════
#  主评分接口
# ═══════════════════════════════════════════════════════════════

def check_copy_tension(
    text: str,
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    文案张力全方位评分

    参数:
      text: 待评估的文案内容
      weights: 自定义权重 (默认使用 SCORE_WEIGHTS)

    返回:
      {
        "scores": {...},        # 各维度分数字典
        "weighted_total": 3.8,  # 加权总分
        "summary": "...",       # 一句话总结
        "details": {...},       # 各维度详情
        "level": "⚠️ 需要改进"  # 评级
      }
    """
    if not text or not text.strip():
        return {
            "scores": {k: 0.0 for k in SCORE_WEIGHTS},
            "weighted_total": 0.0,
            "summary": "❌ 文案为空，无法评分",
            "details": {},
            "level": "❌ 空文案",
        }

    if weights is None:
        weights = SCORE_WEIGHTS.copy()

    # 逐项评分
    score_funcs = {
        "卖点清晰度": score_clarity,
        "张力强度": score_tension,
        "口语化程度": score_colloquial,
        "数据支撑度": score_data_support,
        "情感感染力": score_emotion,
    }

    scores = {}
    details = {}
    for dim, func in score_funcs.items():
        s, d = func(text)
        scores[dim] = s
        details[dim] = d

    # 加权总分
    weighted_total = sum(
        scores[dim] * weights.get(dim, 0.2)
        for dim in scores
    )
    weighted_total = round(weighted_total, 2)

    # 评级
    if weighted_total >= 4.5:
        level = "🌟 张力大师级"
    elif weighted_total >= 4.0:
        level = "✅ 优质文案"
    elif weighted_total >= 3.5:
        level = "✅ 合格文案"
    elif weighted_total >= 3.0:
        level = "⚠️ 及格边缘，需改进"
    else:
        level = "⚠️ 需要重写"

    # 总结
    low_dims = [dim for dim, s in scores.items() if s < 3.0]
    summary_parts = [f"总分: {weighted_total}/5.0 | {level}"]
    if low_dims:
        summary_parts.append(
            f"薄弱维度: {', '.join(low_dims)}"
        )
    else:
        summary_parts.append("各维度均达标")

    summary = " | ".join(summary_parts)

    return {
        "scores": scores,
        "weighted_total": weighted_total,
        "summary": summary,
        "details": details,
        "level": level,
        "word_count": len(text),
    }


def batch_check(copies: List[Dict[str, str]]) -> List[Dict]:
    """
    批量检查多篇文案

    参数:
      copies: [{"title": "xxx", "content": "xxx"}, ...]

    返回: 每篇的评分结果列表
    """
    results = []
    for item in copies:
        title = item.get("title", "未命名")
        content = item.get("content", "")
        result = check_copy_tension(content)
        result["title"] = title
        results.append(result)
    return results


def print_report(result: Dict) -> None:
    """将评分结果打印为可读报告"""
    print("\n" + "=" * 50)
    print("📊 文案张力评分报告")
    print("=" * 50)

    print(f"\n📝 字数: {result.get('word_count', 0)}")
    print(f"📈 总分: {result['weighted_total']}/5.0")
    print(f"🏷️  评级: {result['level']}")
    print()

    for dim, score in result["scores"].items():
        bar = "█" * int(score) + "░" * (5 - int(score))
        print(f"  {dim}: {score}/5.0 {bar}")
        det = result["details"].get(dim, "")
        if det:
            print(f"       └─ {det}")

    print(f"\n📋 总结: {result['summary']}")
    print("=" * 50 + "\n")


# ═══════════════════════════════════════════════════════════════
#  CLI入口
# ═══════════════════════════════════════════════════════════════

def main():
    """命令行入口"""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return

    if len(sys.argv) > 1:
        # 从文件读取
        filepath = sys.argv[1]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"❌ 文件不存在: {filepath}")
            sys.exit(1)
    else:
        # 交互模式
        print("📝 粘贴你的文案 (输入EOF或Ctrl+D结束):")
        text = sys.stdin.read().strip()

    if not text:
        print("❌ 没有输入内容")
        sys.exit(1)

    result = check_copy_tension(text)
    print_report(result)


if __name__ == "__main__":
    main()
