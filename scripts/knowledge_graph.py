#!/usr/bin/env python3
"""
knowledge_graph.py — 关键词匹配引擎（对标 Mem.ai 自动关联）

心智模型自动关联引擎 P0：
- 从五池/模型池/读取所有心智模型 .md 文件
- 提取：标题、标签/分类、核心关键词、引用关系
- 建立关键词→心智模型的倒排索引
- CLI 功能：--search, --related, --stats

零外部依赖，纯 Python 标准库。
"""

import os
import re
import sys
import json
import argparse
import textwrap
from collections import defaultdict, Counter
from datetime import datetime

# ── 全局路径 ──
HERMES = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
POOL_DIR = os.path.join(HERMES, "L5孵化室", "五池", "模型池")
INDEX_PATH = os.path.join(HERMES, "profiles", "_shared", "MENTAL_MODEL_INDEX.yaml")
# 模型池子目录（排除非心智模型目录）
POOL_SUBDIRS = [
    "_原子", "一堂",
    "attribution_compressor", "baize-ui-essence",
    "BM25SearchEngine", "CoreInfra", "cybernetic_advisor",
    "HybridSearchEngine", "KnowledgeBaseAPI", "meeting_analyzer",
    "mempalace", "MetaInjector", "so_switch",
    "从知识库提取的模型",
]

# ── 停用词（心智模型无关的通用词） ──
STOP_WORDS = {
    "一个", "可以", "这个", "那个", "什么", "怎么", "如何", "为什么",
    "就是", "不是", "但是", "而且", "或者", "如果", "因为", "所以",
    "没有", "已经", "这些", "那些", "这样", "那样", "非常", "还是",
    "需要", "能够", "应该", "可能", "必须", "不会", "不能", "不要",
    "用于", "通过", "包括", "并且", "其中", "以及", "或者", "他们",
    "我们", "你们", "它们", "自己", "这里", "那里", "每个", "所有",
    "一些", "很多", "部分", "其他", "之后", "之前", "以上", "以下",
    "使用", "进行", "提供", "实现", "完成", "支持", "基于", "相关",
    "一种", "两个", "三个", "第一", "第二", "第三", "最后", "主要",
    "属于", "对应", "分别", "直接", "同时", "一直", "一定", "一样",
    "成为", "进入", "产生", "发现", "开始", "出现", "形成", "影响",
    "更多", "更少", "更大", "更小", "更好", "更差", "更优", "更高效",
    "一下", "来看", "来看", "来看", "所示", "如下", "包含", "拥有",
    "到", "了", "的", "在", "是", "和", "有", "不", "就", "都",
    "而", "也", "上", "下", "中", "让", "做", "被", "把", "对",
    "为", "与", "用", "从", "到", "以", "将", "或", "但", "还",
    "这", "那", "很", "太", "更", "最", "已", "没", "又", "再",
    "只", "多", "少", "大", "小", "长", "短", "高", "低", "好",
    "坏", "新", "旧", "正", "反", "真", "假", "因", "果",
    # 心智模型无关的结构词
    "模型", "模式", "架构", "系统", "流程", "机制", "框架", "方法",
    "方案", "策略", "方式", "形式", "类型", "种类", "维度", "层面",
    "层面", "级别", "层次", "步骤", "阶段", "环节", "要素", "因素",
    "原则", "规则", "规律", "定律", "定理", "逻辑", "理念", "概念",
    "定义", "解释", "说明", "描述", "示例", "案例", "场景", "情况",
    "目标", "目的", "结果", "输出", "输入", "反馈", "循环", "闭环",
}

# ── 有用关键词模式（提取复合词/术语） ──
KEYWORD_PATTERNS = [
    # 中文术语：双字到六字
    re.compile(r'[\u4e00-\u9fff]{2,8}'),
    # 英文术语
    re.compile(r'[A-Za-z][A-Za-z0-9_-]{1,}'),
    # 中英混合术语
    re.compile(r'[\u4e00-\u9fff]+[A-Za-z0-9]+[\u4e00-\u9fff]*'),
]

# 标签提取模式
TAG_PATTERNS = [
    re.compile(r'\*\*分类\*\*\s*:\s*(.+)', re.IGNORECASE),
    re.compile(r'\*\*类型\*\*\s*:\s*(.+)', re.IGNORECASE),
    re.compile(r'\*\*类别\*\*\s*:\s*(.+)', re.IGNORECASE),
    re.compile(r'\*\*标签\*\*\s*:\s*(.+)', re.IGNORECASE),
    re.compile(r'\*\*标签\*\*[：:]\s*(.+)'),
    re.compile(r'标签\s*[：:]\s*(.+)'),
    re.compile(r'类别\s*[：:]\s*(.+)'),
    re.compile(r'分类\s*[：:]\s*(.+)'),
]

# 引用模式
CITATION_PATTERNS = [
    re.compile(r'\[\[(.+?)\]\]'),
    re.compile(r'【参见[：:]?\s*(.+?)】'),
    re.compile(r'（参见[：:]?\s*(.+?)）'),
    re.compile(r'\(参见[：:]?\s*(.+?)\)'),
    re.compile(r'参见[：:]\s*(.+?)(?:[。，；\n]|$)'),
]


# ══════════════════════════════════════════════
#  文件扫描与解析
# ══════════════════════════════════════════════

def scan_model_files() -> list[dict]:
    """扫描模型池所有 .md 文件，返回模型元数据列表"""
    models = []
    seen = set()

    # 收集所有 .md 文件路径
    md_files = []
    if os.path.isdir(POOL_DIR):
        for root, dirs, files in os.walk(POOL_DIR):
            # 跳过 __pycache__
            dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('_page')]
            for f in files:
                if f.endswith('.md') and not f.endswith('.bak'):
                    full = os.path.join(root, f)
                    md_files.append(full)

    # 读取 index 获取已知模型清单（用于优先命名）
    index_names = set()
    if os.path.isfile(INDEX_PATH):
        with open(INDEX_PATH, 'r', encoding='utf-8') as fh:
            content = fh.read()
        for m in re.finditer(r'name:\s*"(.+?)"', content):
            index_names.add(m.group(1))

    for path in sorted(md_files):
        rel_path = os.path.relpath(path, POOL_DIR)
        rel_unix = rel_path.replace('\\', '/')

        # 读取文件
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception:
            continue

        # 跳过空文件
        if len(text.strip()) < 20:
            continue

        # 提取标题
        title = extract_title(text, rel_path)

        # 唯一性去重
        dedup_key = title
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # 提取标签/分类
        tags = extract_tags(text, rel_path)

        # 提取关键词
        keywords = extract_keywords(text, title)

        # 提取引用
        citations = extract_citations(text)

        # 摘要（前200字非空）
        summary = extract_summary(text)

        models.append({
            "name": title,
            "file": rel_unix,
            "path": path,
            "tags": sorted(tags),
            "keywords": keywords,
            "citations": citations,
            "summary": summary,
            "char_count": len(text),
        })

    return models


def extract_title(text: str, rel_path: str) -> str:
    """从文本中提取心智模型标题"""
    # 优先：# 标题 或 ## 模型：xxx
    for pat in [
        re.compile(r'^#\s+(.+?)$', re.MULTILINE),
        re.compile(r'^##\s+(.+?)$', re.MULTILINE),
    ]:
        m = pat.search(text)
        if m:
            title = m.group(1).strip()
            if len(title) > 200:
                title = title[:200]
            # 清理标题格式
            title = re.sub(r'\*\*', '', title)
            title = re.sub(r'🔥', '', title)
            title = title.strip()
            if title:
                return title

    # 回退：使用文件名（去掉 .md 扩展名）
    name = rel_path.replace('\\', '/')
    name = name.replace('.md', '')
    return name


def extract_tags(text: str, rel_path: str) -> set:
    """从文件内容和路径提取标签"""
    tags = set()

    # 1. 从结构化字段提取
    for pat in TAG_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1).strip()
            # 分割逗号、顿号、空格分隔的多个标签
            parts = re.split(r'[，,、/\\·\s]+', raw)
            for p in parts:
                p = p.strip().strip('*').strip('#')
                if p and len(p) <= 30:
                    tags.add(p)

    # 2. 从文件路径提取（子目录名作为标签）
    parts = rel_path.replace('\\', '/').split('/')
    for p in parts[:-1]:  # 排除文件名
        if p and p not in POOL_SUBDIRS and not p.startswith('_'):
            # 清理路径名作为标签
            clean = p.replace('_', '-').replace('-', '·')
            if clean and len(clean) <= 30:
                tags.add(clean)

    # 3. 从内容中提取显式标签行（标签: xxx）
    for pat in [
        re.compile(r'^标签[：:]\s*(.+)$', re.MULTILINE),
        re.compile(r'^Tags[：:]\s*(.+)$', re.MULTILINE),
    ]:
        for m in pat.finditer(text):
            raw = m.group(1).strip()
            parts = re.split(r'[，,、/\\·\s]+', raw)
            for p in parts:
                p = p.strip().strip('*')
                if p and len(p) <= 30:
                    tags.add(p)

    # 4. 从文件名推断一些常见标签
    fname = parts[-1] if parts else ""
    if '原子' in fname:
        tags.add('原子心智模型')
    if '架构' in fname or '架构' in rel_path:
        tags.add('架构心智模型')
    if '交易' in fname or '投资' in fname or 'Vibe' in fname:
        tags.add('交易')
    if '安全' in fname or 'Security' in fname:
        tags.add('安全')
    if '铁律' in fname:
        tags.add('铁律')
    if '产品' in fname or '工业化' in fname:
        tags.add('产品化')
    if '链客宝' in fname:
        tags.add('链客宝')
    if '盖娅' in fname or 'Gaia' in fname:
        tags.add('盖娅之城')
    if 'Hermes' in fname or 'hermes' in fname:
        tags.add('Hermes')
    if '原子' in fname:
        tags.add('原子')

    return tags


def extract_keywords(text: str, title: str) -> list[str]:
    """从文本中提取核心关键词（含词频排序）"""
    # 只处理正文内容（跳过标题行）
    body = text

    # 移除代码块
    body = re.sub(r'```[\s\S]*?```', '', body)
    # 移除表格
    body = re.sub(r'\|[^\n]*\|', '', body)
    # 移除 Markdown 链接语法但保留文字
    body = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', body)

    # 提取所有中文词（双字到八字）
    chinese_words = KEYWORD_PATTERNS[0].findall(body)

    # 过滤停用词和短词
    filtered = []
    for w in chinese_words:
        w = w.strip()
        if len(w) < 2 or len(w) > 20:
            continue
        if w in STOP_WORDS:
            continue
        # 排除纯标点/数字
        if re.match(r'^[\d\s\.\-\+\*#_/\\\(\)\[\]]+$', w):
            continue
        # 排除标题本身（关键词不应与标题相同）
        if w == title or w in title:
            continue
        filtered.append(w)

    # 词频统计
    word_freq = Counter(filtered)

    # 提取英文术语（3 字母以上）
    for m in KEYWORD_PATTERNS[1].finditer(body):
        w = m.group(0)
        if len(w) >= 3 and w.lower() not in {'the', 'and', 'for', 'are', 'but', 'not', 'you',
                                               'all', 'can', 'had', 'her', 'was', 'one', 'our',
                                               'out', 'has', 'had', 'its', 'may', 'see', 'use',
                                               'any', 'way', 'new', 'now', 'old', 'how', 'why',
                                               'who', 'two', 'get', 'set', 'put', 'run', 'end'}:
            word_freq[w] += 1

    # 取前 50 个关键词
    top_words = [w for w, _ in word_freq.most_common(50)]
    return top_words


def extract_citations(text: str) -> list[str]:
    """提取文本中的引用关系"""
    citations = []
    for pat in CITATION_PATTERNS:
        for m in pat.finditer(text):
            ref = m.group(1).strip()
            if ref and len(ref) <= 100:
                # 清理
                ref = ref.strip('"').strip("'").strip('*')
                if ref not in citations:
                    citations.append(ref)
    return citations


def extract_summary(text: str) -> str:
    """提取简要摘要（前 200 非空字符）"""
    # 移除标题行
    body = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE)
    body = re.sub(r'\*\*', '', body)
    body = re.sub(r'\n+', ' ', body).strip()
    if len(body) > 200:
        body = body[:200] + '...'
    return body


# ══════════════════════════════════════════════
#  索引构建
# ══════════════════════════════════════════════

def build_inverted_index(models: list[dict]) -> dict[str, list[str]]:
    """构建关键词→心智模型名称的倒排索引"""
    index = defaultdict(set)

    for model in models:
        name = model["name"]
        # 加入标题本身的词
        for w in extract_title_words(name):
            index[w].add(name)
        # 加入标签
        for tag in model["tags"]:
            index[tag].add(name)
            # 标签的子词
            for w in extract_title_words(tag):
                index[w].add(name)
        # 加入关键词
        for kw in model["keywords"][:20]:  # 取前20关键词
            index[kw].add(name)
        # 加入引用名
        for cit in model["citations"]:
            index[cit].add(name)
            for w in extract_title_words(cit):
                index[w].add(name)
        # 加入文件名（不含扩展名）
        fname = model["file"].replace('.md', '')
        for seg in fname.replace('\\', '/').split('/'):
            index[seg].add(name)
            for w in extract_title_words(seg):
                index[w].add(name)

    # 转换为列表排序
    result = {}
    for k, v in index.items():
        result[k] = sorted(v)
    return result


def extract_title_words(title: str) -> list[str]:
    """从标题/名称中提取关键词片段"""
    words = []
    # 按常见分隔符分割
    parts = re.split(r'[_\s\-+·、，,./\\（）()（）\[\]【】:：]+', title)
    for p in parts:
        p = p.strip()
        if not p or len(p) < 2:
            continue
        if p in STOP_WORDS:
            continue
        words.append(p)

    # 提取中文双字+片段
    cjk = re.findall(r'[\u4e00-\u9fff]{2,6}', title)
    for w in cjk:
        if w not in STOP_WORDS and w not in words:
            words.append(w)

    return words


def compute_related_models(models: list[dict], inverted_index: dict[str, list[str]],
                           target_name: str, top_n: int = 10) -> list[dict]:
    """计算与指定模型最相关的其他模型（基于共享关键词/标签）"""
    # 找到目标模型
    target = None
    for m in models:
        if m["name"] == target_name:
            target = m
            break

    if not target:
        # 模糊匹配
        candidates = [m for m in models if target_name.lower() in m["name"].lower()]
        if candidates:
            target = candidates[0]
        else:
            return []

    # 收集目标模型的所有关键词/标签
    target_signals = set(target["keywords"][:30])
    target_signals.update(target["tags"])

    # 对每个其他模型计算关联分数
    scores = {}
    for m in models:
        if m["name"] == target["name"]:
            continue

        score = 0
        shared_keywords = set()

        # 标签匹配（高权重）
        for tag in target["tags"]:
            if tag in m["tags"]:
                score += 3
                shared_keywords.add(tag)

        # 关键词重叠
        for kw in target["keywords"][:30]:
            if kw in m["keywords"][:50]:
                score += 1
                shared_keywords.add(kw)

        # 引用匹配（目标引用此模型，或此模型引用目标）
        if target["name"] in m["citations"]:
            score += 5
            shared_keywords.add(f"引用: {target['name']}")
        if m["name"] in target["citations"]:
            score += 5
            shared_keywords.add(f"引用: {m['name']}")

        # 文件名/路径相似度
        target_dir = os.path.dirname(target["file"])
        m_dir = os.path.dirname(m["file"])
        if target_dir == m_dir and target_dir != '.':
            score += 2

        if score > 0:
            scores[m["name"]] = {
                "name": m["name"],
                "summary": m["summary"][:100],
                "weight": round(score / 10.0, 2),  # 归一化到 0-1+
                "shared_signals": list(shared_keywords)[:10],
                "tags": m["tags"],
            }

    # 按权重排序
    sorted_results = sorted(scores.values(), key=lambda x: x["weight"], reverse=True)
    return sorted_results[:top_n]


def search_models(inverted_index: dict[str, list[str]], models: list[dict],
                  query: str, top_n: int = 20) -> list[dict]:
    """搜索关键词匹配的心智模型"""
    query_lower = query.lower()
    query_words = extract_title_words(query)
    query_words.append(query)
    query_words.extend(re.findall(r'[\u4e00-\u9fff]{2,6}', query))

    # 收集匹配的模型名
    matched_names = set()
    match_detail = defaultdict(int)  # name -> score

    for qw in query_words:
        if not qw or len(qw) < 1:
            continue
        qw_lower = qw.lower()

        # 精确匹配
        if qw in inverted_index:
            for n in inverted_index[qw]:
                matched_names.add(n)
                match_detail[n] += 5

        # 子串匹配（关键词包含查询词）
        for key, names in inverted_index.items():
            if qw_lower in key.lower():
                for n in names:
                    matched_names.add(n)
                    match_detail[n] += 3

    # 额外：在模型名、标签、摘要中模糊搜索
    for m in models:
        mname = m["name"].lower()
        if query_lower in mname:
            matched_names.add(m["name"])
            match_detail[m["name"]] += 10

        for tag in m["tags"]:
            if query_lower in tag.lower():
                matched_names.add(m["name"])
                match_detail[m["name"]] += 4

        if query_lower in m["summary"].lower()[:200]:
            matched_names.add(m["name"])
            match_detail[m["name"]] += 2

        if query_lower in m["file"].lower():
            matched_names.add(m["name"])
            match_detail[m["name"]] += 2

    # 构建结果
    results = []
    for name in matched_names:
        for m in models:
            if m["name"] == name:
                results.append({
                    "name": name,
                    "summary": m["summary"][:120],
                    "tags": m["tags"],
                    "file": m["file"],
                    "score": match_detail.get(name, 0),
                })
                break

    # 按分数+标签丰富度排序
    results.sort(key=lambda x: (
        x["score"],
        len(x["tags"]),
    ), reverse=True)

    return results[:top_n]


def compute_stats(models: list[dict], inverted_index: dict[str, list[str]]) -> dict:
    """计算统计信息"""
    total_models = len(models)
    total_keywords = len(inverted_index)

    # 每个模型关联数
    if total_models == 0:
        return {
            "total_models": 0,
            "total_keywords": 0,
            "avg_relations": 0,
            "total_tags": 0,
            "total_citations": 0,
        }

    relations_count = []
    for m in models:
        related = compute_related_models(models, inverted_index, m["name"], top_n=20)
        relations_count.append(len(related))

    avg_relations = sum(relations_count) / total_models if total_models else 0

    # 统计标签
    all_tags = set()
    all_citations = 0
    for m in models:
        all_tags.update(m["tags"])
        all_citations += len(m["citations"])

    return {
        "total_models": total_models,
        "total_keywords": total_keywords,
        "avg_relations": round(avg_relations, 1),
        "total_tags": len(all_tags),
        "total_citations": all_citations,
        "unique_tags": sorted(all_tags),
    }


# ══════════════════════════════════════════════
#  关联持久化
# ══════════════════════════════════════════════

def build_links_yaml(models: list[dict], inverted_index: dict[str, list[str]]) -> str:
    """生成 KNOWLEDGE_GRAPH_LINKS.yaml 内容"""
    lines = [
        "# 自动知识图谱关联索引",
        f"# 生成时间: {datetime.now().isoformat()}",
        f"# 总模型数: {len(models)}",
        f"# 总关键词: {len(inverted_index)}",
        "---",
        "links:",
    ]

    for m in models:
        related = compute_related_models(models, inverted_index, m["name"], top_n=10)
        if related:
            lines.append(f"  - source: \"{m['name']}\"")
            lines.append(f"    targets:")
            for r in related:
                lines.append(f"      - {{ name: \"{r['name']}\", weight: {r['weight']} }}")

    return "\n".join(lines)


# ══════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════

def print_results(results: list[dict], title: str):
    """格式化打印结果"""
    if not results:
        print("(无匹配结果)")
        return

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    for i, r in enumerate(results, 1):
        score_str = f" [{r.get('score', '')}]" if 'score' in r else f" (w={r.get('weight', '')})"
        print(f"\n  {i}. {r['name']}{score_str}")
        if r.get('summary'):
            print(f"     📝 {r['summary'][:120]}")
        if r.get('tags'):
            print(f"     🏷️  {', '.join(r['tags'][:8])}")
        if r.get('shared_signals'):
            sigs = r['shared_signals'][:6]
            print(f"     🔗 共同信号: {', '.join(sigs)}")
        if r.get('file'):
            print(f"     📁 {r['file']}")


def main():
    parser = argparse.ArgumentParser(
        description="心智模型关键词匹配引擎 — 对标 Mem.ai 自动关联",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              %(prog)s --stats                    # 输出统计信息
              %(prog)s --search "架构"            # 搜索含"架构"的模型
              %(prog)s --search "安全 隔离"       # 多关键词搜索
              %(prog)s --related "母体-节点-管道架构"  # 查找相关模型
              %(prog)s --related "GP经济系统" --top 5
              %(prog)s --export-links             # 导出关联 YAML 文件
        """)
    )

    parser.add_argument("--stats", action="store_true", help="输出统计信息")
    parser.add_argument("--search", type=str, help="搜索关键词（返回匹配的心智模型列表）")
    parser.add_argument("--related", type=str, help="查找与指定模型相关的其他模型")
    parser.add_argument("--top", type=int, default=10, help="返回结果数量上限 (默认: 10)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--export-links", action="store_true", help="导出关联索引到 YAML 文件")

    args = parser.parse_args()

    # 没有参数时显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        return

    # 扫描并建立索引
    print("🔍 扫描模型池...", file=sys.stderr)
    models = scan_model_files()
    print(f"📊 发现 {len(models)} 个心智模型文件", file=sys.stderr)

    print("🏗️  构建倒排索引...", file=sys.stderr)
    inverted_index = build_inverted_index(models)
    print(f"📝 索引规模: {len(inverted_index)} 个关键词", file=sys.stderr)

    # ── --stats ──
    if args.stats:
        stats = compute_stats(models, inverted_index)
        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print(f"\n{'='*50}")
            print(f"  心智模型知识图谱 — 统计")
            print(f"{'='*50}")
            print(f"  总模型数:     {stats['total_models']}")
            print(f"  总关键词数:   {stats['total_keywords']}")
            print(f"  平均关联数:   {stats['avg_relations']}")
            print(f"  总标签数:     {stats['total_tags']}")
            print(f"  总引用数:     {stats['total_citations']}")
            print(f"\n  所有标签 ({len(stats['unique_tags'])}):")
            for tag in stats['unique_tags']:
                print(f"    • {tag}")

    # ── --search ──
    if args.search:
        results = search_models(inverted_index, models, args.search, top_n=args.top)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print_results(results, f"搜索 \"{args.search}\" — {len(results)} 个结果")

    # ── --related ──
    if args.related:
        results = compute_related_models(models, inverted_index, args.related, top_n=args.top)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print_results(results, f"与 \"{args.related}\" 相关的模型 — {len(results)} 个")

    # ── --export-links ──
    if args.export_links:
        links_yaml = build_links_yaml(models, inverted_index)
        out_path = os.path.join(HERMES, "profiles", "_shared", "KNOWLEDGE_GRAPH_LINKS.yaml")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(links_yaml)
        print(f"✅ 关联索引已导出: {out_path}")


if __name__ == "__main__":
    main()
