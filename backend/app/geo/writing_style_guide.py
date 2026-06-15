#!/usr/bin/env python3
"""
口语化写作标准化 · writing_style_guide.py
========================================
科学表达·口语化写作方法论(E8)核心规范模块

功能:
  1. 书面语→口语对照表 (完整映射)
  2. 自动检测文案中的书面语并建议替换
  3. 提供口语化改写建议
  4. 常用句式模板库

用法:
  from app.geo.writing_style_guide import (
      detect_formal_writing,
      suggest_colloquial_replacements,
      rewrite_to_colloquial,
      get_style_templates,
  )
"""

import re
from typing import Dict, List, Tuple, Optional


# ═══════════════════════════════════════════════════════════════
#  书面语 → 口语对照表
#  来源: 科学表达口语化写作方法论(E8)
# ═══════════════════════════════════════════════════════════════

# 按类别组织的对照表
FORMAL_TO_COLLOQUIAL_MAP: Dict[str, List[Dict[str, str]]] = {
    "连词替换": [
        {"formal": "然而", "colloquial": "但是/不过"},
        {"formal": "此外", "colloquial": "另外/还有"},
        {"formal": "以及", "colloquial": "和/还有"},
        {"formal": "并且", "colloquial": "而且/还"},
        {"formal": "因而", "colloquial": "所以/因此"},
        {"formal": "鉴于", "colloquial": "因为/考虑到"},
        {"formal": "倘若", "colloquial": "如果/要是"},
        {"formal": "乃至", "colloquial": "甚至/连"},
        {"formal": "抑或", "colloquial": "或者/还是"},
        {"formal": "故而", "colloquial": "所以"},
    ],
    "总结词替换": [
        {"formal": "综上所述", "colloquial": "总的来说/一句话"},
        {"formal": "由此可见", "colloquial": "所以/你看"},
        {"formal": "换言之", "colloquial": "换句话说/说白了"},
        {"formal": "归结起来", "colloquial": "说到底/归根结底"},
        {"formal": "总体而言", "colloquial": "总的来说"},
        {"formal": "从某种意义上说", "colloquial": "某种意义上"},
    ],
    "程度词替换": [
        {"formal": "较为", "colloquial": "比较/挺"},
        {"formal": "颇为", "colloquial": "挺/很"},
        {"formal": "极其", "colloquial": "特别/超级"},
        {"formal": "极其重要", "colloquial": "特别重要/真的很重要"},
        {"formal": "显著", "colloquial": "明显/很大"},
        {"formal": "具有一定", "colloquial": "有"},
        {"formal": "相当", "colloquial": "挺/特别"},
        {"formal": "十分", "colloquial": "特别/非常"},
        {"formal": "略微", "colloquial": "有点/稍微"},
    ],
    "动词替换": [
        {"formal": "进行", "colloquial": "做/搞"},
        {"formal": "予以", "colloquial": "给/做"},
        {"formal": "实施", "colloquial": "做/执行"},
        {"formal": "执行", "colloquial": "做/干"},
        {"formal": "获取", "colloquial": "拿到/得到"},
        {"formal": "在...方面", "colloquial": "在...上/在...这块"},
        {"formal": "利用", "colloquial": "用/借助"},
        {"formal": "具备", "colloquial": "有"},
        {"formal": "构建", "colloquial": "搭建/建立"},
        {"formal": "促使", "colloquial": "让/推动"},
    ],
    "抽象名词替换": [
        {"formal": "相关事宜", "colloquial": "相关的事"},
        {"formal": "后续工作", "colloquial": "后面的事"},
        {"formal": "解决方案", "colloquial": "解决办法/方案"},
        {"formal": "方法论", "colloquial": "方法/套路"},
        {"formal": "维度", "colloquial": "方面/角度"},
        {"formal": "层面", "colloquial": "层面/角度"},
        {"formal": "抓手", "colloquial": "切入点/突破口"},
        {"formal": "赋能", "colloquial": "帮助/支持/助力"},
        {"formal": "闭环", "colloquial": "完整流程/走通"},
        {"formal": "痛点", "colloquial": "问题/难处"},
        {"formal": "场景", "colloquial": "情况/场景"},
        {"formal": "颗粒度", "colloquial": "细致程度/细节"},
    ],
    "句子结构替换": [
        {"formal": "我们需要...", "colloquial": "你得.../你要..."},
        {"formal": "值得我们关注的是", "colloquial": "值得注意"},
        {"formal": "从...角度来看", "colloquial": "从...来看"},
        {"formal": "基于...考虑", "colloquial": "考虑到..."},
        {"formal": "对...进行优化", "colloquial": "优化..."},
        {"formal": "对...展开讨论", "colloquial": "聊聊/说说..."},
        {"formal": "给出...的建议", "colloquial": "建议你..."},
    ],
}

# 平铺映射表 (用于快速查找)
_FLAT_MAP: List[Dict[str, str]] = []
for _category, _items in FORMAL_TO_COLLOQUIAL_MAP.items():
    for _item in _items:
        _item["category"] = _category
        _FLAT_MAP.append(_item)


# ═══════════════════════════════════════════════════════════════
#  口语化句式模板库
# ═══════════════════════════════════════════════════════════════

COLLOQUIAL_TEMPLATES: Dict[str, List[str]] = {
    "开头句式": [
        "跟你说个事儿，{topic}这事最近火了。",
        "你有没有发现，{topic}已经悄悄变了。",
        "说实话，{topic}真没你想的那么复杂。",
        "今天咱们聊聊{topic}，一个你可能忽略的问题。",
        "我跟你讲，{topic}这事儿真的得重视。",
        "你知道{topic}意味着什么吗？",
        "先问个问题：{topic}，你真的了解吗？",
        "老实说，我之前也不信，直到看到这些数据。",
    ],
    "转折句式": [
        "但问题是，{issue}。",
        "不过话说回来，{point}。",
        "然而事实恰恰相反——{reality}。",
        "但你别急着下定论，{reversal}。",
        "等等，先别走，关键的在后面：{key_point}。",
    ],
    "解释句式": [
        "说白了就是，{simple_explain}。",
        "打个比方，{analogy}。",
        "换句话说，{rephrase}。",
        "简单来说就一句话：{one_liner}。",
        "我给你算笔账：{calculation}。",
    ],
    "数据呈现句式": [
        "给你看组数据：{data}。",
        "数据不会骗人——{data_fact}。",
        "你可能不信，但这是真的：{data_fact}。",
        "我问你，{rhetorical_question}？答案是{answer}。",
        "做个对比你就懂了：{comparison}。",
    ],
    "结尾句式": [
        "所以，你还在犹豫什么？",
        "说到底，{takeaway}，就是这么简单。",
        "现在行动还来得及，别等错过了再后悔。",
        "如果你有{topic}的问题，现在就是解决的最好时机。",
        "我说完了，你怎么看？",
        "最后送你一句话：{quote}。",
    ],
    "互动句式": [
        "你觉得呢？",
        "你是怎么看的？",
        "你有没有类似的经历？",
        "评论区说说你的看法。",
        "如果觉得有用，转发给需要的朋友。",
    ],
}


# ═══════════════════════════════════════════════════════════════
#  检测引擎
# ═══════════════════════════════════════════════════════════════

def detect_formal_writing(
    text: str,
    threshold: int = 1,
) -> List[Dict]:
    """
    检测文案中的书面语表达

    参数:
      text: 文案内容
      threshold: 匹配阈值(每个书面词只报告1次)

    返回:
      [{"formal": "然而", "colloquial": "但是/不过",
        "category": "连词替换", "position": 12, "context": "...然而..."}, ...]
    """
    results = []
    seen = set()

    for item in _FLAT_MAP:
        formal = item["formal"]
        # 跳过太短的可能误匹配的词
        if len(formal) < 2:
            continue

        pattern = re.escape(formal)
        for match in re.finditer(pattern, text):
            pos = match.start()

            # 去重: 同一个词在同一篇文章只报告一次
            if formal in seen:
                continue
            seen.add(formal)

            # 提取上下文
            start = max(0, pos - 10)
            end = min(len(text), pos + len(formal) + 10)
            context = text[start:end].replace("\n", " ")

            results.append({
                "formal": formal,
                "colloquial": item["colloquial"],
                "category": item.get("category", "其他"),
                "position": pos,
                "context": f"...{context}...",
            })
            break  # 只报告第一个出现位置

    # 按类别分组排序
    results.sort(key=lambda x: x["category"])
    return results


def suggest_colloquial_replacements(
    text: str,
    context_window: int = 30,
) -> List[Dict]:
    """
    对检测到的书面语给出替换建议

    返回:
      [{
        "original": "然而",
        "suggested": "但是/不过",
        "category": "连词替换",
        "context": "...然而...",
        "replacement_sentence": "改进后的句子示例"
      }, ...]
    """
    detections = detect_formal_writing(text)
    suggestions = []

    for det in detections:
        # 尝试生成替换后的句子
        formal = det["formal"]
        colloq_options = det["colloquial"].split("/")
        best_colloq = colloq_options[0]  # 默认选第一个

        # 看上下文中是否适合特定口语词
        context = det["context"]
        replaced = context.replace(formal, best_colloq)

        suggestions.append({
            "original": formal,
            "suggested": det["colloquial"],
            "category": det["category"],
            "context": det["context"],
            "replacement_example": replaced,
        })

    return suggestions


def rewrite_to_colloquial(text: str) -> Dict:
    """
    全自动口语化改写 (返回原文·改写文·改动列表)

    这是一个启发式改写，会替换所有匹配的书面语。
    注意: 改写后建议人工复核。
    """
    replacements_made = []
    rewritten = text

    # 按formal长度降序替换 (避免短词被长词的部分匹配)
    sorted_items = sorted(_FLAT_MAP, key=lambda x: -len(x["formal"]))

    for item in sorted_items:
        formal = item["formal"]
        colloq_options = item["colloquial"].split("/")
        best = colloq_options[0]

        count_before = rewritten.count(formal)
        if count_before > 0:
            rewritten = rewritten.replace(formal, best)
            replacements_made.append({
                "formal": formal,
                "colloquial": best,
                "count": count_before,
            })

    return {
        "original": text,
        "rewritten": rewritten,
        "replacements": replacements_made,
        "total_replacements": len(replacements_made),
        "chars_saved": len(text) - len(rewritten),
    }


# ═══════════════════════════════════════════════════════════════
#  模板 & 风格建议
# ═══════════════════════════════════════════════════════════════

def get_style_templates(style_type: Optional[str] = None) -> Dict:
    """
    获取口语化句式模板

    参数:
      style_type: 模板类型 (开头句式/转折句式/解释句式/数据呈现句式/结尾句式/互动句式)
                  不传则返回全部
    """
    if style_type:
        return {style_type: COLLOQUIAL_TEMPLATES.get(style_type, [])}
    return dict(COLLOQUIAL_TEMPLATES)


def get_writing_rules() -> List[Dict]:
    """
    获取口语化写作黄金法则
    """
    return [
        {
            "rule": "黄金法则一: 说人话",
            "detail": "写完后大声读一遍，读着不顺的地方就是需要改的地方",
            "example": "❌ '我们对系统进行了全面的优化升级' → ✅ '我们把系统彻底优化了一遍'",
        },
        {
            "rule": "黄金法则二: 短句 > 长句",
            "detail": "一句话不超过30个字，超过就拆成两句",
            "example": "❌ '在当前的商业环境中企业供需匹配已成为企业关注的焦点' → ✅ '企业供需匹配这事，最近特别火。大家都在关注。'",
        },
        {
            "rule": "黄金法则三: 一个'你'字值千金",
            "detail": "多使用'你'、'你的'，把读者拉到对话场景中",
            "example": "❌ '企业家需要关注获客效率' → ✅ '你的获客效率，真的够用吗？'",
        },
        {
            "rule": "黄金法则四: 用动词不用名词",
            "detail": "动词有画面感，名词是冷冰冰的概念",
            "example": "❌ '进行供需资源的匹配对接' → ✅ '帮供需双方牵线搭桥'",
        },
        {
            "rule": "黄金法则五: 用具体不用抽象",
            "detail": "给具体数字、具体场景、具体案例",
            "example": "❌ '很多企业存在效率低下的问题' → ✅ '10个老板里7个在抱怨：找客户太难了'",
        },
        {
            "rule": "黄金法则六: 用疑问句引导思考",
            "detail": "疑问句让读者从被动接收变成主动思考",
            "example": "❌ '企业供需匹配很重要' → ✅ '你的企业还在靠人脉找客户吗？'",
        },
        {
            "rule": "黄金法则七: 每段只说一件事",
            "detail": "一段一个核心观点，不要贪多",
            "example": "把三个观点塞进一段 → 拆成三段，每段配一个小标题或问句开头",
        },
        {
            "rule": "黄金法则八: 开头3秒定生死",
            "detail": "开头必须有钩子——反问/惊人数据/冲突场景/反常识观点",
            "example": "❌ '随着数字化转型的深入推进' → ✅ '你知道吗？70%的B2B企业还在用Excel找客户。'",
        },
    ]


def get_formal_colloquial_map(category: Optional[str] = None) -> Dict:
    """获取书面语→口语对照表"""
    if category and category in FORMAL_TO_COLLOQUIAL_MAP:
        return {category: FORMAL_TO_COLLOQUIAL_MAP[category]}
    return dict(FORMAL_TO_COLLOQUIAL_MAP)


# ═══════════════════════════════════════════════════════════════
#  完整风格检查报告
# ═══════════════════════════════════════════════════════════════

def full_style_check(text: str) -> Dict:
    """
    完整的口语化风格检查报告

    返回包含:
      - 书面语检测结果
      - 替换建议
      - 风格评分
      - 黄金法则遵守情况
      - 改进建议列表
    """
    detections = detect_formal_writing(text)
    suggestions = suggest_colloquial_replacements(text)

    # 计算口语化得分 (基于书面语密度)
    word_count = len(text)
    formal_count = len(detections)
    if word_count > 0:
        formal_density = formal_count / (word_count / 100)  # 每100字
    else:
        formal_density = 0

    if formal_density <= 1.0:
        style_score = 4.5
        style_level = "✅ 口语化程度优秀"
    elif formal_density <= 2.0:
        style_score = 3.5
        style_level = "✅ 口语化程度良好"
    elif formal_density <= 3.0:
        style_score = 2.5
        style_level = "⚠️ 偏书面化，建议优化"
    else:
        style_score = 1.5
        style_level = "⚠️ 书面腔太重，建议重写"

    # 分类统计
    category_counts = {}
    for d in detections:
        cat = d["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # 改进建议
    improvement_tips = []
    if category_counts.get("连词替换", 0) >= 2:
        improvement_tips.append("减少书面连词，多用'但是/不过/所以'替代'然而/此外/因而'")
    if category_counts.get("总结词替换", 0) >= 1:
        improvement_tips.append("避免'综上所述/由此可见'，用'总的来说/说白了'替代")
    if category_counts.get("动词替换", 0) >= 2:
        improvement_tips.append("减少'进行/予以/实施'等僵尸动词，直接用动词")
    if category_counts.get("抽象名词替换", 0) >= 2:
        improvement_tips.append("少用'赋能/闭环/抓手'等黑话，说大白话")
    if category_counts.get("程度词替换", 0) >= 2:
        improvement_tips.append("用'挺/特别/超级'替代'较为/颇为/极其'")
    if not detections:
        improvement_tips.append("整体口语化程度不错，继续保持")

    return {
        "style_score": style_score,
        "style_level": style_level,
        "formal_count": formal_count,
        "formal_density": round(formal_density, 2),
        "detections": detections,
        "suggestions": suggestions,
        "category_breakdown": category_counts,
        "improvement_tips": improvement_tips,
        "rules": get_writing_rules(),
    }


def print_style_report(result: Dict) -> None:
    """打印口语化风格检查报告"""
    print("\n" + "=" * 55)
    print("🗣️  口语化风格检查报告")
    print("=" * 55)
    print(f"\n📊 风格评分: {result['style_score']}/5.0 | {result['style_level']}")
    print(f"🔍 书面语检出: {result['formal_count']} 处 (密度: {result['formal_density']}/百字)")

    if result["category_breakdown"]:
        print("\n📂 按类别分布:")
        for cat, count in sorted(result["category_breakdown"].items()):
            print(f"    {cat}: {count}处")

    if result["detections"]:
        print("\n🔎 检测到的书面语:")
        for d in result["detections"][:15]:  # 最多显示15条
            print(f"    [{d['category']}] '{d['formal']}' → 建议: {d['colloquial']}")
            print(f"      上下文: {d['context'][:50]}")

        if len(result["detections"]) > 15:
            print(f"    ... 还有 {len(result['detections']) - 15} 处")

    if result["improvement_tips"]:
        print("\n💡 改进建议:")
        for tip in result["improvement_tips"][:5]:
            print(f"    • {tip}")

    if result["rules"]:
        print("\n📖 口语化黄金法则:")
        for rule in result["rules"]:
            print(f"    📌 {rule['rule']}")
            print(f"       {rule['detail']}")

    print("\n" + "=" * 55 + "\n")


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
        filepath = sys.argv[1]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"❌ 文件不存在: {filepath}")
            sys.exit(1)

        # 可选: --rewrite 参数触发自动改写
        if "--rewrite" in sys.argv:
            result = rewrite_to_colloquial(text)
            print("\n" + "=" * 55)
            print("🔄 口语化改写结果")
            print("=" * 55)
            print(f"\n替换了 {result['total_replacements']} 处书面语")
            print(f"节省 {result['chars_saved']} 字符")
            print("\n--- 改写后 ---")
            print(result["rewritten"])
            return

        report = full_style_check(text)
        print_style_report(report)
    else:
        # 交互模式
        print("📝 粘贴你的文案 (输入EOF或Ctrl+D结束):")
        text = sys.stdin.read().strip()
        if text:
            report = full_style_check(text)
            print_style_report(report)
        else:
            print("❌ 没有输入内容")
            # 显示个示例
            print("\n📖 书面语→口语对照表示例:")
            for cat, items in list(FORMAL_TO_COLLOQUIAL_MAP.items())[:3]:
                print(f"\n  [{cat}]")
                for item in items[:3]:
                    print(f"    '{item['formal']}' → '{item['colloquial']}'")


if __name__ == "__main__":
    main()
