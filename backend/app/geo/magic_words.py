#!/usr/bin/env python3
"""
MagicWords推荐器 · magic_words.py
==================================
科学表达·张力武器库(E5)关键词推荐模块

功能:
  1. 张力关键词分类 (强调词/规律词/疑问词/稀缺词)
  2. 根据文案类型自动推荐张力词
  3. 张力词组合建议
  4. 张力词使用评分

用法:
  from app.geo.magic_words import (
      recommend_magic_words,
      get_word_category,
      score_magic_word_usage,
      get_tension_combos,
  )
"""

import re
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════
#  张力关键词分类库
# ═══════════════════════════════════════════════════════════════

MAGIC_WORDS: Dict[str, List[Dict]] = {
    "强调词 — 制造确定性与权威感": [
        {"word": "必须", "power": 4, "usage": "强调必要性", "example": "你必须掌握的3个获客工具"},
        {"word": "绝对", "power": 4, "usage": "强调确定性", "example": "这绝对是2026年最值得关注的趋势"},
        {"word": "完全", "power": 3, "usage": "强调完整性", "example": "完全改变了我对B2B获客的认知"},
        {"word": "真正", "power": 4, "usage": "强调真实性", "example": "真正懂AI的人都在用这个工具"},
        {"word": "唯一", "power": 5, "usage": "强调稀缺", "example": "唯一一个让我主动推荐的获客平台"},
        {"word": "核心", "power": 3, "usage": "强调重要性", "example": "核心问题只有一个：你能不能找到客户"},
        {"word": "关键", "power": 3, "usage": "强调决定性", "example": "关键不在于工具，而在于你怎么用"},
        {"word": "根本", "power": 4, "usage": "强调本质", "example": "根本问题不是流量贵，而是流量不精准"},
        {"word": "本质", "power": 3, "usage": "强调深层", "example": "B2B获客的本质是信任的建立"},
        {"word": "永远", "power": 4, "usage": "强调时间性", "example": "永远不要低估口碑传播的力量"},
    ],
    "规律词 — 制造专业感与趋势感": [
        {"word": "趋势", "power": 3, "usage": "强调方向", "example": "2026年B2B获客的5大趋势"},
        {"word": "正在", "power": 3, "usage": "强调进行时", "example": "AI正在重新定义企业供需匹配"},
        {"word": "已经", "power": 3, "usage": "强调现状", "example": "你的竞争对手已经在用AI获客了"},
        {"word": "即将", "power": 4, "usage": "强调紧迫", "example": "传统获客方式即将被淘汰"},
        {"word": "越来越", "power": 3, "usage": "强调递增", "example": "企业信任越来越成为核心竞争力"},
        {"word": "爆发", "power": 5, "usage": "强调增长", "example": "AI数字名片市场正在爆发"},
        {"word": "加速", "power": 4, "usage": "强调速度", "example": "数字化转型正在加速重构行业格局"},
        {"word": "变革", "power": 4, "usage": "强调改变", "example": "B2B营销正在经历一场静悄悄的变革"},
        {"word": "浪潮", "power": 4, "usage": "强调规模", "example": "谁能在这波AI浪潮中抓住机会"},
        {"word": "门槛", "power": 3, "usage": "强调壁垒", "example": "AI降低了企业数字化获客的门槛"},
    ],
    "疑问词 — 制造互动与好奇心": [
        {"word": "你知道吗", "power": 4, "usage": "制造悬念", "example": "你知道吗？70%的B2B企业还在用Excel"},
        {"word": "为什么", "power": 5, "usage": "引发思考", "example": "为什么你的同行获客效率比你高3倍？"},
        {"word": "怎么", "power": 4, "usage": "引导方法", "example": "中小企业怎么做才能低成本获客？"},
        {"word": "如何", "power": 4, "usage": "引导方法", "example": "如何用AI把获客成本降低50%？"},
        {"word": "是不是", "power": 3, "usage": "引导共鸣", "example": "你是不是也觉得传统获客越来越难？"},
        {"word": "有没有", "power": 3, "usage": "引导共鸣", "example": "有没有一种可能，你根本不需要那么多客户"},
        {"word": "要不要", "power": 3, "usage": "引导决策", "example": "要不要试试这个让获客效率翻倍的方法"},
        {"word": "你敢信吗", "power": 5, "usage": "制造冲击", "example": "你敢信吗？一个AI工具让获客效率提升300%"},
        {"word": "什么", "power": 3, "usage": "引发好奇", "example": "真正高效的企业家都在用什么工具？"},
        {"word": "到底", "power": 4, "usage": "强调追问", "example": "B2B获客到底难在哪里？"},
    ],
    "稀缺词 — 制造紧迫与独占感": [
        {"word": "限时", "power": 5, "usage": "制造时间紧迫", "example": "限时免费体验AI获客工具"},
        {"word": "独家", "power": 5, "usage": "制造独占感", "example": "独家揭秘：头部企业都在用的获客策略"},
        {"word": "首发", "power": 4, "usage": "制造新鲜感", "example": "全网首发的企业供需匹配白皮书"},
        {"word": "最后", "power": 5, "usage": "制造紧迫感", "example": "最后3天，错过等一年"},
        {"word": "仅限", "power": 4, "usage": "制造限制感", "example": "仅限前100名企业免费体验"},
        {"word": "错过", "power": 5, "usage": "制造损失厌恶", "example": "错过这波AI红利，你可能要多花3年"},
        {"word": "先到先得", "power": 4, "usage": "制造竞争", "example": "名额有限，先到先得"},
        {"word": "限量", "power": 5, "usage": "制造稀缺", "example": "限量开放100个内测名额"},
        {"word": "首期", "power": 3, "usage": "制造首发感", "example": "首期AI获客训练营正式开启"},
        {"word": "免费", "power": 4, "usage": "制造利益感", "example": "免费获取2026年B2B获客趋势报告"},
    ],
}

# 展平列表 (用于快速检索)
_ALL_WORDS: List[Dict] = []
for _cat, _words in MAGIC_WORDS.items():
    for _w in _words:
        _w["category"] = _cat
        _ALL_WORDS.append(_w)


# ═══════════════════════════════════════════════════════════════
#  文案类型 → 推荐张力词映射
# ═══════════════════════════════════════════════════════════════

COPY_TYPE_PROFILES: Dict[str, Dict] = {
    "知乎问答": {
        "description": "知识型深度分享",
        "recommended_categories": ["疑问词", "规律词", "强调词"],
        "taboo_categories": ["稀缺词"],  # 知乎不太适合过度稀缺营销
        "tone": "专业但不装，有料但不吹",
    },
    "36氪": {
        "description": "行业分析/商业报道",
        "recommended_categories": ["规律词", "强调词", "疑问词"],
        "taboo_categories": [],
        "tone": "有数据有观点，理性中带态度",
    },
    "CSDN/掘金": {
        "description": "技术向内容",
        "recommended_categories": ["强调词", "疑问词", "规律词"],
        "taboo_categories": ["稀缺词"],
        "tone": "技术深度+实战经验",
    },
    "百家号": {
        "description": "大众资讯",
        "recommended_categories": ["稀缺词", "强调词", "疑问词"],
        "taboo_categories": [],
        "tone": "通俗易懂，抓眼球但不夸张",
    },
    "产品介绍页": {
        "description": "官网/落地页文案",
        "recommended_categories": ["强调词", "稀缺词", "疑问词"],
        "taboo_categories": [],
        "tone": "价值清晰，行动导向",
    },
    "朋友圈/社群": {
        "description": "短文案传播",
        "recommended_categories": ["疑问词", "稀缺词", "强调词"],
        "taboo_categories": ["规律词"],
        "tone": "接地气，有情绪，勾起互动",
    },
    "SEO/GEO文章": {
        "description": "搜索引擎/生成式引擎优化",
        "recommended_categories": ["疑问词", "规律词", "强调词"],
        "taboo_categories": [],
        "tone": "关键词自然融入，有信息增量",
    },
    "公众号": {
        "description": "品牌公众号推送",
        "recommended_categories": ["疑问词", "强调词", "规律词"],
        "taboo_categories": ["稀缺词"],
        "tone": "有深度有温度，像朋友在聊天",
    },
    "通用推荐": {
        "description": "不确定类型时的默认推荐",
        "recommended_categories": ["疑问词", "强调词", "规律词", "稀缺词"],
        "taboo_categories": [],
        "tone": "有张力有数据有情绪",
    },
}


# ═══════════════════════════════════════════════════════════════
#  核心推荐接口
# ═══════════════════════════════════════════════════════════════

def recommend_magic_words(
    copy_type: str = "通用推荐",
    topic: str = "",
    count: int = 5,
    min_power: int = 3,
) -> Dict:
    """
    根据文案类型和主题推荐张力关键词

    参数:
      copy_type: 文案类型 (知乎问答/36氪/CSDN掘金/百家号/产品介绍页/朋友圈社群/SEO文章/公众号/通用推荐)
      topic: 主题关键词 (如"企业供需匹配"), 用于优先推荐相关内容
      count: 推荐数量
      min_power: 最低张力强度 (1-5)

    返回:
      {
        "type_profile": {...},    # 当前文案类型画像
        "recommendations": [...],  # 推荐词列表
        "taboo_words": [...],     # 避免使用的词
        "usage_tips": [...],      # 使用建议
      }
    """
    # 获取类型画像
    profile = COPY_TYPE_PROFILES.get(
        copy_type, COPY_TYPE_PROFILES["通用推荐"]
    )
    recommended_cats = profile["recommended_categories"]
    taboo_cats = profile.get("taboo_categories", [])

    # 筛选: 按推荐类别 + 最小强度
    candidates = [
        w for w in _ALL_WORDS
        if any(cat in w["category"] for cat in recommended_cats)
        and w["power"] >= min_power
    ]

    # 如果提供了主题，给主题相关词加权
    if topic:
        def topic_weight(word_dict: Dict) -> int:
            w = word_dict["word"]
            ex = word_dict.get("example", "")
            # 主题词出现在示例中 +2 优先级
            bonus = 0
            if topic in ex or any(kw in ex for kw in topic.split()):
                bonus = 2
            return word_dict["power"] + bonus

        candidates.sort(key=topic_weight, reverse=True)
    else:
        candidates.sort(key=lambda x: x["power"], reverse=True)

    # 确保多样性: 尽量从不同类别取
    recommendations = []
    seen_categories = set()

    # 先每类取一个
    for cat in recommended_cats:
        for w in candidates:
            if w["word"] not in [r["word"] for r in recommendations]:
                if cat in w["category"]:
                    recommendations.append(w)
                    seen_categories.add(cat)
                    break

    # 补足数量
    for w in candidates:
        if len(recommendations) >= count:
            break
        if w["word"] not in [r["word"] for r in recommendations]:
            recommendations.append(w)

    # 禁忌词
    taboo_words = [
        w for w in _ALL_WORDS
        if any(cat in w["category"] for cat in taboo_cats)
    ]

    # 使用建议
    usage_tips = _generate_usage_tips(copy_type, recommendations)

    return {
        "type_profile": {
            "name": copy_type,
            "description": profile["description"],
            "tone": profile["tone"],
        },
        "recommendations": recommendations[:count],
        "taboo_words": taboo_words[:5],
        "usage_tips": usage_tips,
    }


def _generate_usage_tips(
    copy_type: str, words: List[Dict]
) -> List[str]:
    """生成张力词使用建议"""
    tips = []

    if copy_type == "知乎问答":
        tips.append("知乎用户爱看干货，张力词用在开头和转折处效果最好")
        tips.append("用疑问词开头('你知道吗'/'为什么')最适合知乎风格")
        tips.append("建议在文章前1/3处埋一个张力钩子")
    elif copy_type == "36氪":
        tips.append("36氪用户理性，规律词('趋势'/'正在'/'变革')比情绪词效果好")
        tips.append("用数据支撑张力词，不要只喊口号")
    elif copy_type == "CSDN/掘金":
        tips.append("技术社区对浮夸词敏感，强调词要配上真技术细节")
        tips.append("疑问词('怎么'/'如何')引导最佳，配合代码/架构图更佳")
    elif copy_type == "百家号":
        tips.append("大众用户喜欢强烈情绪，稀缺词和强调词可以大胆用")
        tips.append("标题一定要有张力词，点击率能提升30%+")
    elif copy_type == "产品介绍页":
        tips.append("产品页张力词要精准：直击痛点+给出方案")
        tips.append("CTA按钮周围用稀缺词效果最好")
    elif copy_type == "朋友圈/社群":
        tips.append("朋友圈张力要克制，一个张力词就够了，太多显营销")
        tips.append("疑问词+稀缺词组合最易引发互动")
    elif copy_type in ("SEO/GEO文章", "SEO文章"):
        tips.append("标题和H1/H2标签里放张力词，提升AI搜索引擎抓取权重")
        tips.append("规律词('趋势'/'正在')有助于GEO引擎判断内容时效性")
    elif copy_type == "公众号":
        tips.append("公众号适合开头用疑问词制造悬念，中间用规律词建立信任")
        tips.append("避免过度稀缺词，保持品牌调性一致")

    tips.append("张力词使用频率建议：每300-500字使用1个高强度(4-5分)张力词")
    return tips


def get_word_category() -> Dict[str, List[str]]:
    """获取所有张力词分类"""
    return {
        cat: [w["word"] for w in words]
        for cat, words in MAGIC_WORDS.items()
    }


def get_all_magic_words(min_power: int = 1) -> List[Dict]:
    """
    获取所有张力词

    参数:
      min_power: 最小张力强度 (1-5)
    """
    return [w for w in _ALL_WORDS if w["power"] >= min_power]


# ═══════════════════════════════════════════════════════════════
#  张力词使用评分器
# ═══════════════════════════════════════════════════════════════

def score_magic_word_usage(text: str) -> Dict:
    """
    评估文案的张力词使用情况

    返回:
      {
        "total_words_found": 5,      # 找到的张力词数量
        "unique_words": 3,           # 不重复的张力词数
        "word_density": 1.2,         # 每100字的张力词数
        "avg_power": 3.8,            # 平均张力强度
        "top_words": [...],          # 使用最多的张力词
        "category_coverage": {...},  # 各类覆盖率
        "score": 3.5,                # 张力词使用综合评分
        "suggestion": "...",         # 改进建议
      }
    """
    found = []
    category_hits = {}

    for w in _ALL_WORDS:
        word = w["word"]
        count = len(re.findall(re.escape(word), text))
        if count > 0:
            found.append({
                "word": word,
                "category": w["category"],
                "power": w["power"],
                "count": count,
            })
            cat = w["category"]
            category_hits[cat] = category_hits.get(cat, 0) + count

    word_count = len(text)
    unique_count = len(set(f["word"] for f in found))
    total_hits = sum(f["count"] for f in found)

    # 密度
    density = round(total_hits / (word_count / 100), 2) if word_count > 0 else 0

    # 平均张力强度
    if found:
        avg_power = round(
            sum(f["power"] * f["count"] for f in found) / total_hits, 1
        )
    else:
        avg_power = 0

    # 评分
    score = 3.0  # 基础分
    if density >= 2.0:
        score += 1.0
    elif density >= 1.0:
        score += 0.5
    elif density <= 0.3:
        score -= 0.5

    if avg_power >= 4.0:
        score += 0.5
    elif avg_power >= 3.0:
        score += 0.2

    # 多样性加分
    cat_count = len(category_hits)
    if cat_count >= 3:
        score += 0.5
    elif cat_count >= 2:
        score += 0.2

    score = max(1.0, min(5.0, round(score, 1)))

    # 建议
    suggestions = []
    if density < 0.5:
        suggestions.append("张力词使用不足，建议每100字至少使用1个张力词")
    if cat_count < 2:
        suggestions.append("张力词类型单一，建议混合使用强调词+疑问词+规律词")
    if avg_power < 3.0:
        suggestions.append("使用的张力词偏弱，建议替换为更高强度的词")
    if density > 5.0:
        suggestions.append("张力词使用过密，建议适当控制频率")

    if not suggestions:
        suggestions.append("张力词使用得当，继续保持")

    return {
        "total_words_found": total_hits,
        "unique_words": unique_count,
        "word_density": density,
        "avg_power": avg_power,
        "category_coverage": category_hits,
        "top_words": sorted(found, key=lambda x: -x["count"])[:5],
        "score": score,
        "suggestion": "; ".join(suggestions),
    }


# ═══════════════════════════════════════════════════════════════
#  张力词组合建议
# ═══════════════════════════════════════════════════════════════

TENSION_COMBOS: List[Dict] = [
    {
        "name": "悬念·揭秘组合",
        "pattern": "疑问词 + 强调词 + 规律词",
        "example": "你知道吗？AI正在彻底改变B2B获客的方式",
        "effect": "勾起好奇心→强调重要性→给出趋势判断",
        "best_for": ["知乎问答", "公众号", "36氪"],
    },
    {
        "name": "痛点·解决方案组合",
        "pattern": "强调词 + 疑问词 + 强调词",
        "example": "你的获客方式真的过时了？核心问题在这里",
        "effect": "指出问题→引发反思→给出答案",
        "best_for": ["产品介绍页", "SEO/GEO文章", "百家号"],
    },
    {
        "name": "紧迫感组合",
        "pattern": "稀缺词 + 规律词 + 强调词",
        "example": "限时免费！AI获客工具正在改变行业规则",
        "effect": "制造稀缺→趋势加持→强化价值",
        "best_for": ["朋友圈/社群", "百家号", "产品介绍页"],
    },
    {
        "name": "权威·专业组合",
        "pattern": "规律词 + 强调词 + 疑问词",
        "example": "2026年B2B获客的5大趋势，你抓住了几个？",
        "effect": "趋势感→重要性→引发互动",
        "best_for": ["36氪", "CSDN/掘金", "知乎问答"],
    },
    {
        "name": "好奇·反差组合",
        "pattern": "疑问词 + 稀缺词 + 强调词",
        "example": "你敢信吗？99%的企业家都在用错误的方式获客",
        "effect": "冲击认知→制造稀缺→强化反差",
        "best_for": ["百家号", "朋友圈/社群", "公众号"],
    },
]


def get_tension_combos(
    copy_type: Optional[str] = None,
) -> List[Dict]:
    """
    获取张力词组合建议

    参数:
      copy_type: 可选，筛选适合特定文案类型的组合
    """
    if copy_type:
        return [
            c for c in TENSION_COMBOS
            if copy_type in c["best_for"]
        ]
    return list(TENSION_COMBOS)


# ═══════════════════════════════════════════════════════════════
#  报告打印
# ═══════════════════════════════════════════════════════════════

def print_recommendations(result: Dict) -> None:
    """打印张力词推荐报告"""
    print("\n" + "=" * 55)
    print("🔮 MagicWords 张力关键词推荐")
    print("=" * 55)

    profile = result["type_profile"]
    print(f"\n📋 文案类型: {profile['name']}")
    print(f"📝 风格建议: {profile['tone']}")

    print(f"\n🔥 推荐张力词 (Top {len(result['recommendations'])}):")
    for i, w in enumerate(result["recommendations"], 1):
        power_bar = "💪" * w["power"] + "🤏" * (5 - w["power"])
        print(f"\n  {i}. 「{w['word']}」{power_bar}")
        print(f"     类别: {w['category']}")
        print(f"     用法: {w['usage']}")
        print(f"     示例: {w['example']}")

    if result["taboo_words"]:
        print(f"\n⛔ 本类型避免使用:")
        for w in result["taboo_words"][:3]:
            print(f"    「{w['word']}」({w['category']})")

    if result["usage_tips"]:
        print(f"\n💡 使用建议:")
        for tip in result["usage_tips"]:
            print(f"    • {tip}")

    print("\n" + "=" * 55 + "\n")


def print_score_report(result: Dict) -> None:
    """打印张力词使用评分报告"""
    print("\n" + "=" * 55)
    print("📊 张力词使用评分")
    print("=" * 55)
    print(f"\n📍 综合评分: {result['score']}/5.0")
    print(f"🔢 发现张力词: {result['total_words_found']} 个 ({result['unique_words']} 种)")
    print(f"📈 使用密度: {result['word_density']} 个/百字")
    print(f"⭐ 平均强度: {result['avg_power']}/5.0")

    if result["category_coverage"]:
        print("\n📂 类别覆盖:")
        for cat, count in sorted(
            result["category_coverage"].items(),
            key=lambda x: -x[1],
        ):
            print(f"    {cat}: {count}次")

    if result["top_words"]:
        print("\n🏆 使用最多的张力词:")
        for w in result["top_words"]:
            print(f"    「{w['word']}」({w['category']}) × {w['count']}次")

    print(f"\n💡 建议: {result['suggestion']}")
    print("=" * 55 + "\n")


# ═══════════════════════════════════════════════════════════════
#  CLI入口
# ═══════════════════════════════════════════════════════════════

def main():
    """命令行入口"""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("\n用法:")
        print("  python magic_words.py                                # 交互式推荐")
        print("  python magic_words.py --type 知乎问答                # 指定类型推荐")
        print("  python magic_words.py --type 知乎问答 --topic 供需匹配  # 带主题")
        print("  python magic_words.py --list                         # 列出所有词")
        print("  python magic_words.py --score <file>                # 评分文件中的张力词")
        print("  python magic_words.py --combos                      # 查看组合建议")
        return

    if "--list" in sys.argv:
        print("\n📚 张力关键词完整词库:")
        for cat, words in MAGIC_WORDS.items():
            print(f"\n  {cat}:")
            for w in words:
                print(f"    「{w['word']}」(强度{w['power']}) — {w['usage']}")
        return

    if "--combos" in sys.argv:
        combos = get_tension_combos()
        print("\n🔗 张力词组合推荐:")
        for c in combos:
            print(f"\n  [{c['name']}]")
            print(f"  模式: {c['pattern']}")
            print(f"  示例: \"{c['example']}\"")
            print(f"  效果: {c['effect']}")
            print(f"  适用: {', '.join(c['best_for'])}")
        return

    if "--score" in sys.argv:
        idx = sys.argv.index("--score")
        if idx + 1 < len(sys.argv):
            filepath = sys.argv[idx + 1]
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    text = f.read()
                result = score_magic_word_usage(text)
                print_score_report(result)
            except FileNotFoundError:
                print(f"❌ 文件不存在: {filepath}")
            return

    # 提取类型参数
    copy_type = "通用推荐"
    topic = ""
    if "--type" in sys.argv:
        idx = sys.argv.index("--type")
        if idx + 1 < len(sys.argv):
            copy_type = sys.argv[idx + 1]
    if "--topic" in sys.argv:
        idx = sys.argv.index("--topic")
        if idx + 1 < len(sys.argv):
            topic = sys.argv[idx + 1]

    result = recommend_magic_words(copy_type=copy_type, topic=topic)
    print_recommendations(result)


if __name__ == "__main__":
    main()
