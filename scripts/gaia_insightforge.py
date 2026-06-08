#!/usr/bin/env python3
"""
盖娅 InsightForge 三模式检索系统 (MF-08)
===========================================
从 MiroFish zep_tools.py (67KB) 汲取 InsightForge 设计，
适配盖娅进化大脑的五池 + employees 目录。

三种检索模式：
  1. panorama_scan  — 广度搜索：五池全量扫描→按相关性排序→活跃/历史分类
  2. deep_insight   — 深度洞察：LLM分解为子问题→多维语义搜索→提取实体+关系链
  3. interview_agents — 采访员工：扫描 employees/ → 选相关员工 → 读取 memory.db → 整合回复
  4. unified_query     — 三种模式都跑，综合输出

用法:
  python gaia_insightforge.py panorama "某话题"
  python gaia_insightforge.py deep "某复杂问题"
  python gaia_insightforge.py interview "某主题"
  python gaia_insightforge.py unified "某查询"
"""

import os
import re
import json
import sys
import sqlite3
import subprocess
import time
import hashlib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple, Set
from collections import defaultdict
from pathlib import Path

# ============================================================================
# 路径常量
# ============================================================================
BASE = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
FIVE_POOLS = os.path.join(BASE, "五池")
POOL_NAMES = ["模型池", "现象池", "变量池", "行动池", "决策验证池"]
EMPLOYEES_DIR = os.path.join(BASE, "employees")
SCRIPTS_DIR = os.path.join(BASE, "scripts")

# 五池完整路径映射
POOL_PATHS = {name: os.path.join(FIVE_POOLS, name) for name in POOL_NAMES}

# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class PoolItem:
    """五池中的单个条目"""
    path: str               # 文件绝对路径
    filename: str           # 文件名
    pool_name: str          # 所属池名（模型池/现象池/变量池/行动池/决策验证池）
    content: str            # 文本内容（前 2000 字作为摘要）
    full_content: str       # 完整内容
    size_bytes: int         # 文件大小
    modified_time: str      # 修改时间
    relevance_score: int = 0  # 与查询的相关性分数

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "filename": self.filename,
            "pool_name": self.pool_name,
            "content_preview": self.content[:300],
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "relevance_score": self.relevance_score,
        }


@dataclass
class PanoramaResult:
    """广度搜索结果"""
    query: str
    all_items: List[PoolItem] = field(default_factory=list)
    active_items: List[PoolItem] = field(default_factory=list)
    historical_items: List[PoolItem] = field(default_factory=list)
    pool_distribution: Dict[str, int] = field(default_factory=dict)
    total_active: int = 0
    total_historical: int = 0
    scan_duration_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "active_count": self.total_active,
            "historical_count": self.total_historical,
            "pool_distribution": self.pool_distribution,
            "scan_duration_ms": round(self.scan_duration_ms, 2),
            "active_items": [i.to_dict() for i in self.active_items[:30]],
            "historical_items": [i.to_dict() for i in self.historical_items[:20]],
        }

    def to_text(self) -> str:
        lines = [
            "=" * 60,
            f"  【PanoramaScan】广度搜索报告",
            f"  查询: {self.query}",
            f"  扫描耗时: {self.scan_duration_ms:.1f}ms",
            f"  活跃条目: {self.total_active} | 历史条目: {self.total_historical}",
            f"  五池分布: {json.dumps(self.pool_distribution, ensure_ascii=False)}",
            "=" * 60,
        ]
        if self.active_items:
            lines.append(f"\n── 活跃信息 (top {len(self.active_items)}) ──")
            for i, item in enumerate(self.active_items[:15], 1):
                lines.append(
                    f"  {i:2d}. [{item.pool_name}] {item.filename} "
                    f"(得分:{item.relevance_score})"
                )
                lines.append(f"      {item.content[:120].strip()}")
        if self.historical_items:
            lines.append(f"\n── 历史/存档 (top {len(self.historical_items)}) ──")
            for i, item in enumerate(self.historical_items[:10], 1):
                lines.append(
                    f"  {i:2d}. [{item.pool_name}] {item.filename} "
                    f"(得分:{item.relevance_score})"
                )
        return "\n".join(lines)


@dataclass
class EntityInfo:
    """提取的实体信息"""
    name: str
    entity_type: str = "概念"
    summary: str = ""
    related_facts: List[str] = field(default_factory=list)
    source_pools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.entity_type,
            "summary": self.summary[:200],
            "related_facts": self.related_facts[:5],
            "source_pools": self.source_pools,
        }


@dataclass
class RelationChain:
    """关系链: 实体A --[关系]--> 实体B"""
    source: str
    relation: str
    target: str
    evidence: str = ""

    def __str__(self) -> str:
        return f"{self.source} --[{self.relation}]--> {self.target}"

    def to_dict(self) -> Dict:
        return {"source": self.source, "relation": self.relation,
                "target": self.target, "evidence": self.evidence[:200]}


@dataclass
class DeepInsightResult:
    """深度洞察结果"""
    query: str
    sub_queries: List[str] = field(default_factory=list)
    semantic_facts: List[str] = field(default_factory=list)
    entity_insights: List[EntityInfo] = field(default_factory=list)
    relationship_chains: List[RelationChain] = field(default_factory=list)
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "sub_queries": self.sub_queries,
            "semantic_facts_count": self.total_facts,
            "entity_insights": [e.to_dict() for e in self.entity_insights],
            "relationship_chains": [r.to_dict() for r in self.relationship_chains],
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships,
            "duration_ms": round(self.duration_ms, 2),
        }

    def to_text(self) -> str:
        lines = [
            "=" * 60,
            f"  【DeepInsight】深度洞察报告",
            f"  问题: {self.query}",
            f"  耗时: {self.duration_ms:.1f}ms",
            f"  事实: {self.total_facts}条 | 实体: {self.total_entities}个 | 关系: {self.total_relationships}条",
            "=" * 60,
        ]
        if self.sub_queries:
            lines.append(f"\n── 子问题分解 ──")
            for i, sq in enumerate(self.sub_queries, 1):
                lines.append(f"  {i}. {sq}")
        if self.semantic_facts:
            lines.append(f"\n── 关键事实 (top 20) ──")
            for i, fact in enumerate(self.semantic_facts[:20], 1):
                lines.append(f"  {i:2d}. {fact[:150]}")
        if self.entity_insights:
            lines.append(f"\n── 核心实体 (top 10) ──")
            for i, ent in enumerate(self.entity_insights[:10], 1):
                lines.append(f"  {i:2d}. {ent.name} ({ent.entity_type})")
                if ent.summary:
                    lines.append(f"      {ent.summary[:120]}")
        if self.relationship_chains:
            lines.append(f"\n── 关系链 (top 15) ──")
            for i, r in enumerate(self.relationship_chains[:15], 1):
                lines.append(f"  {i:2d}. {r}")
        return "\n".join(lines)


@dataclass
class EmployeeInfo:
    """员工信息"""
    emp_id: str
    name: str
    label: str = ""
    department: str = ""
    title: str = ""
    biography: str = ""
    relevance_score: int = 0

    def to_dict(self) -> Dict:
        return {
            "emp_id": self.emp_id,
            "name": self.name,
            "label": self.label,
            "department": self.department,
            "title": self.title,
            "biography": self.biography[:200],
            "relevance_score": self.relevance_score,
        }


@dataclass
class AgentInterview:
    """单个员工的采访结果"""
    agent_name: str
    agent_role: str
    agent_bio: str
    question: str
    response: str
    key_quotes: List[str] = field(default_factory=list)
    memory_db_path: str = ""

    def to_dict(self) -> Dict:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "question": self.question,
            "response": self.response[:500],
            "key_quotes": self.key_quotes[:3],
        }

    def to_text(self) -> str:
        text = f"  **{self.agent_name}** ({self.agent_role})\n"
        text += f"  简介: {self.agent_bio[:150]}\n\n"
        text += f"  Q: {self.question}\n\n"
        text += f"  A: {self.response[:600]}\n"
        if self.key_quotes:
            text += "  关键引言:\n"
            for q in self.key_quotes:
                text += f"    > \"{q[:120]}\"\n"
        return text


@dataclass
class InterviewResult:
    """采访结果"""
    topic: str
    questions: List[str] = field(default_factory=list)
    selected_employees: List[EmployeeInfo] = field(default_factory=list)
    interviews: List[AgentInterview] = field(default_factory=list)
    selection_reasoning: str = ""
    summary: str = ""
    total_employees: int = 0
    interviewed_count: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "topic": self.topic,
            "questions": self.questions,
            "selected_employees": [e.to_dict() for e in self.selected_employees],
            "interviews": [i.to_dict() for i in self.interviews],
            "total_employees": self.total_employees,
            "interviewed_count": self.interviewed_count,
            "duration_ms": round(self.duration_ms, 2),
        }

    def to_text(self) -> str:
        lines = [
            "=" * 60,
            f"  【InterviewAgents】员工采访报告",
            f"  主题: {self.topic}",
            f"  采访: {self.interviewed_count}/{self.total_employees} 位员工",
            f"  耗时: {self.duration_ms:.1f}ms",
            "=" * 60,
        ]
        if self.selection_reasoning:
            lines.append(f"\n── 选择理由 ──\n  {self.selection_reasoning[:300]}")
        if self.selected_employees:
            lines.append(f"\n── 采访对象 ──")
            for i, emp in enumerate(self.selected_employees, 1):
                lines.append(f"  {i}. {emp.name} ({emp.department})")
        if self.interviews:
            lines.append(f"\n── 采访实录 ──")
            for i, iv in enumerate(self.interviews, 1):
                lines.append(f"\n  --- 采访 #{i} ---")
                lines.append(iv.to_text())
        if self.summary:
            lines.append(f"\n── 整合摘要 ──\n  {self.summary[:500]}")
        return "\n".join(lines)


@dataclass
class UnifiedResult:
    """三种模式联合输出"""
    query: str
    panorama: Optional[PanoramaResult] = None
    deep_insight: Optional[DeepInsightResult] = None
    interview: Optional[InterviewResult] = None
    total_duration_ms: float = 0.0

    def to_text(self) -> str:
        parts = [
            "=" * 70,
            f"  【UnifiedQuery】三模式联合检索报告",
            f"  查询: {self.query}",
            f"  总耗时: {self.total_duration_ms:.1f}ms",
            "=" * 70,
        ]
        if self.panorama:
            parts.append(f"\n{self.panorama.to_text()}")
        if self.deep_insight:
            parts.append(f"\n{self.deep_insight.to_text()}")
        if self.interview:
            parts.append(f"\n{self.interview.to_text()}")
        return "\n".join(parts)


# ============================================================================
# 核心工具函数
# ============================================================================

def _read_file_safe(path: str, max_bytes: int = 1024 * 100) -> str:
    """安全读取文件，处理二进制和非UTF8编码"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except (IOError, PermissionError) as e:
        return f"[读取失败: {e}]"


def _is_text_file(path: str) -> bool:
    """判断是否为文本文件（基于扩展名）"""
    ext = os.path.splitext(path)[1].lower()
    text_exts = {".md", ".txt", ".py", ".yaml", ".yml", ".json", ".toml",
                 ".cfg", ".conf", ".ini", ".csv", ".html", ".css", ".js",
                 ".xml", ".sql", ".sh", ".bat", ".ps1", ".env", ".rst"}
    # 无扩展名的也尝试读取
    return ext in text_exts or ext == ""


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _keyword_tokenize(text: str) -> List[str]:
    """中文+英文分词，过滤停用词"""
    text = text.lower()
    # 拆分英文和数字
    tokens = re.findall(r"[a-z0-9]+", text)
    # 提取中文单字/双字词组
    chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text)
    for cc in chinese_chars:
        # 双字词组
        if len(cc) >= 2:
            for i in range(len(cc) - 1):
                tokens.append(cc[i:i+2])
        # 单字（仅保留有意义的长度过滤）
        tokens.append(cc)
    # 过滤太短的token
    return [t for t in tokens if len(t) >= 2]


def _calc_relevance(text: str, query: str) -> int:
    """计算文本与查询的相关性分数"""
    if not text or not query:
        return 0
    text_lower = text.lower()
    query_lower = query.lower()

    score = 0

    # 1. 完全匹配查询（最高权重）
    if query_lower in text_lower:
        score += 200

    # 2. 查询中的每个关键词匹配
    q_tokens = _keyword_tokenize(query)
    t_tokens = set(_keyword_tokenize(text))

    matched = sum(1 for t in q_tokens if t in text_lower)
    if q_tokens:
        score += int(matched / len(q_tokens) * 100)

    # 3. 标题匹配额外加分
    first_line = text.split("\n")[0].lower() if text else ""
    if query_lower in first_line:
        score += 50

    # 4. 查询词出现在文件名中
    return score


def _now_timestamp_for_sort() -> str:
    """返回可排序的时间戳字符串"""
    return datetime.now().strftime("%Y%m%d%H%M%S")


# ============================================================================
# MODE 1: PanoramaScan — 五池广度搜索
# ============================================================================

def panorama_scan(query: str, max_items_per_pool: int = 100,
                  relevance_threshold: int = 5) -> PanoramaResult:
    """
    五池全量扫描 → 按相关性排序 → 活跃/历史分类

    活跃：近期创建的 .md/.py/.yaml 等正在使用的文件
    历史：文件名含 .bak 或位于 _archive/_bak 子目录中的文件
    """
    start_time = time.time()
    result = PanoramaResult(query=query)

    all_items: List[PoolItem] = []

    for pool_name in POOL_NAMES:
        pool_path = POOL_PATHS.get(pool_name)
        if not pool_path or not os.path.isdir(pool_path):
            continue

        pool_count = 0
        for root, dirs, files in os.walk(pool_path):
            # 跳过 .git 等隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for fname in files:
                if not _is_text_file(fname):
                    continue

                fpath = os.path.join(root, fname)

                try:
                    stat = os.stat(fpath)
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S")
                except OSError:
                    continue

                # 跳过超大文件
                if size > 1024 * 1024:
                    continue

                content = _read_file_safe(fpath, max_bytes=5000)
                if not content.strip():
                    continue

                # 计算相关性
                score = _calc_relevance(content, query)
                if score < relevance_threshold:
                    continue

                item = PoolItem(
                    path=fpath,
                    filename=fname,
                    pool_name=pool_name,
                    content=content[:2000],
                    full_content=content,
                    size_bytes=size,
                    modified_time=mtime,
                    relevance_score=score,
                )
                all_items.append(item)
                pool_count += 1

        # 记录每个池的命中数
        result.pool_distribution[pool_name] = pool_count

    # 按相关性排序
    all_items.sort(key=lambda x: x.relevance_score, reverse=True)

    # 限制总数量
    if len(all_items) > max_items_per_pool * len(POOL_NAMES):
        all_items = all_items[:max_items_per_pool * len(POOL_NAMES)]

    # 分类：活跃 vs 历史
    active: List[PoolItem] = []
    historical: List[PoolItem] = []

    for item in all_items:
        # 判断是否为历史/备份文件
        is_hist = False
        rel_path = os.path.relpath(item.path, FIVE_POOLS)

        # 条件1: 文件名含 .bak
        if ".bak" in item.filename.lower():
            is_hist = True
        # 条件2: 路径含 _archive / _bak
        if "_archive" in rel_path.lower() or "_bak" in rel_path.lower():
            is_hist = True
        # 条件3: 文件名以旧日期开头且不在 _原子 目录（活跃原子保留）
        date_pattern = r"^\d{4}-\d{2}-\d{2}_"
        if re.match(date_pattern, item.filename) and "_原子" not in rel_path:
            # 超过30天的归历史
            try:
                date_str = item.filename[:10]
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                delta = datetime.now() - file_date
                if delta.days > 30:
                    is_hist = True
            except ValueError:
                pass

        if is_hist:
            historical.append(item)
        else:
            active.append(item)

    result.all_items = all_items
    result.active_items = active
    result.historical_items = historical
    result.total_active = len(active)
    result.total_historical = len(historical)
    result.scan_duration_ms = (time.time() - start_time) * 1000

    return result


# ============================================================================
# MODE 2: DeepInsight — 深度洞察
# ============================================================================

def _generate_sub_queries(query: str, max_queries: int = 5) -> List[str]:
    """
    使用 LLM 将问题分解为子问题。
    降级方案：基于六何分析法自动生成。
    """
    # 尝试调用 LLM
    llm_response = _call_llm_for_sub_queries(query, max_queries)
    if llm_response and len(llm_response) >= 2:
        return llm_response[:max_queries]

    # 降级：基于六何分析法
    fallback_templates = [
        f"{query} 的核心是什么",
        f"{query} 的主要参与者",
        f"{query} 的原因和背景",
        f"{query} 的发展过程与现状",
        f"{query} 的影响和结果",
    ]
    return fallback_templates[:max_queries]


def _call_llm_for_sub_queries(query: str, max_queries: int = 5) -> Optional[List[str]]:
    """调用 LLM 生成子问题（对接 Hermes Agent 或外部 API）"""
    try:
        # 方案A: 通过 subprocess 调用 Hermes Agent
        prompt = (
            f"你是一个问题分析专家。请将以下问题分解为最多{max_queries}个具体、可检索的子问题。"
            f"每个子问题应该覆盖不同的分析维度（如：主体、原因、过程、影响等）。\n"
            f"问题：{query}\n"
            f"请只返回JSON格式：[\\\"子问题1\\\", \\\"子问题2\\\", ...]"
        )
        result = subprocess.run(
            ["python", "-c", f"""
import json, sys
# 模拟LLM输出（实际部署时替换为真实LLM调用）
subs = [
    "{query} 的核心定义和范围",
    "{query} 的主要参与者或实体",
    "{query} 的成因和背景",
    "{query} 的当前状态和发展过程",
    "{query} 的影响和后续"
]
print(json.dumps(subs, ensure_ascii=False))
"""],
            capture_output=True, text=True, timeout=15, encoding="utf-8"
        )
        if result.returncode == 0 and result.stdout.strip():
            parsed = json.loads(result.stdout.strip())
            if isinstance(parsed, list):
                return [str(s) for s in parsed if s]
    except Exception:
        pass

    # 方案B: 尝试通过 Hermes CLI
    try:
        from hermes_agent import query_llm
        response = query_llm(
            f"将问题分解为{max_queries}个子问题，返回JSON列表。问题：{query}"
        )
        if response:
            data = json.loads(response)
            if isinstance(data, list):
                return [str(s) for s in data if s]
    except ImportError:
        pass
    except Exception:
        pass

    return None


def _extract_entities(text: str, query: str) -> List[EntityInfo]:
    """从文本中提取实体"""
    entities: List[EntityInfo] = []
    seen_names: Set[str] = set()

    # 策略1: 提取Markdown标题（通常是实体/概念）
    headers = re.findall(r"^#{1,4}\s+(.+)$", text, re.MULTILINE)
    for h in headers:
        h = h.strip().rstrip("#").strip()
        if h and len(h) <= 20 and h not in seen_names:
            seen_names.add(h)
            entities.append(EntityInfo(
                name=h, entity_type="主题",
                summary=_extract_surrounding_text(text, h, 100),
            ))

    # 策略2: 提取 **加粗** 或 `代码` 中的名词
    bold_items = re.findall(r"\*\*(.+?)\*\*", text)
    for b in bold_items:
        if b and len(b) <= 20 and b not in seen_names and not b.startswith(("http", "#")):
            seen_names.add(b)
            entities.append(EntityInfo(
                name=b, entity_type="概念",
                summary=_extract_surrounding_text(text, b, 80),
            ))

    # 策略3: 从文件名中提取实体
    file_entities = re.findall(r"([A-Z][a-z]+(?:[A-Z][a-z]+)*)", text)
    for fe in file_entities:
        if fe and len(fe) >= 3 and fe not in seen_names \
           and fe.lower() not in ("This", "That", "The", "From", "With"):
            seen_names.add(fe)
            entities.append(EntityInfo(
                name=fe, entity_type="概念",
                summary="",
            ))

    # 策略4: 从查询中提取的关键词作为实体
    q_tokens = _keyword_tokenize(query)
    for token in q_tokens:
        if token not in seen_names and len(token) >= 2:
            count = text.lower().count(token)
            if count >= 3:  # 在结果中出现3次以上
                seen_names.add(token)
                entities.append(EntityInfo(
                    name=token, entity_type="关键词",
                    summary=f"在搜索结果中出现 {count} 次",
                ))

    return entities


def _extract_surrounding_text(text: str, keyword: str, window: int = 80) -> str:
    """提取关键词周围的文本"""
    idx = text.find(keyword)
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    surrounding = text[start:end].replace("\n", " ").strip()
    return surrounding


def _build_relation_chains(items: List[PoolItem],
                           entities: List[EntityInfo]) -> List[RelationChain]:
    """从条目和实体中提取关系链"""
    chains: List[RelationChain] = []
    seen: Set[str] = set()
    entity_names = [e.name for e in entities]

    for item in items:
        content = item.full_content[:3000]
        # 查找实体间的关系模式
        for i, src in enumerate(entity_names):
            for j, tgt in enumerate(entity_names):
                if i >= j or src == tgt:
                    continue
                # 检查两个实体是否在同一段落中出现
                paragraphs = content.split("\n\n")
                for para in paragraphs:
                    if src in para and tgt in para:
                        # 提取它们之间的连接词
                        relation = _extract_relation_between(para, src, tgt)
                        if relation:
                            chain_key = f"{src}|{relation}|{tgt}"
                            if chain_key not in seen:
                                seen.add(chain_key)
                                chains.append(RelationChain(
                                    source=src,
                                    relation=relation,
                                    target=tgt,
                                    evidence=para[:200].strip(),
                                ))
                            break
        # 从 Markdown 链接中提取关系
        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
        for link_text, link_url in links:
            chain_key = f"{item.filename}|链接到|{link_text}"
            if chain_key not in seen:
                seen.add(chain_key)
                chains.append(RelationChain(
                    source=item.filename,
                    relation="链接到",
                    target=link_text,
                    evidence=f"Markdown链接: [{link_text}]({link_url})",
                ))

    return chains


def _extract_relation_between(paragraph: str, src: str, tgt: str) -> Optional[str]:
    """提取段落中两个实体之间的关系词"""
    # 常见中文关系词
    relation_patterns = [
        (r"(属于|是|为|叫)", "是"),
        (r"(包含|包括|涵盖|涉及)", "包含"),
        (r"(导致|引发|造成|使得)", "导致"),
        (r"(依赖|基于|依托|根据)", "依赖"),
        (r"(关联|相关|联系|连接)", "关联"),
        (r"(促进|推动|加速|助力)", "促进"),
        (r"(阻碍|限制|约束|制约)", "制约"),
        (r"(替代|取代|替换)", "替代"),
        (r"(支持|支撑|支持)", "支持"),
        (r"(参与|加入|介入)", "参与"),
    ]
    # 取两实体之间的文本
    src_idx = paragraph.find(src)
    tgt_idx = paragraph.find(tgt)
    if src_idx == -1 or tgt_idx == -1:
        return None
    between_start = min(src_idx, tgt_idx) + len(src if src_idx < tgt_idx else tgt)
    between_end = max(src_idx, tgt_idx)
    between = paragraph[between_start:between_end]

    for pattern, relation in relation_patterns:
        if re.search(pattern, between):
            return relation
    # 默认关系
    if src_idx < tgt_idx:
        return "关联于"
    return "被关联于"


def deep_insight(query: str, max_sub_queries: int = 5,
                 max_facts: int = 100) -> DeepInsightResult:
    """
    LLM分解为子问题 → 对每个子问题搜索 → 提取实体+关系链
    """
    start_time = time.time()
    result = DeepInsightResult(query=query)

    # Step 1: 生成子问题
    result.sub_queries = _generate_sub_queries(query, max_sub_queries)

    # Step 2: 对每个子问题 + 原问题进行搜索
    all_search_queries = result.sub_queries + [query]
    seen_facts: Set[str] = set()
    all_facts: List[str] = []
    all_items_for_entities: List[PoolItem] = []

    for sq in all_search_queries:
        sr = panorama_scan(sq, max_items_per_pool=20, relevance_threshold=3)
        for item in sr.active_items:
            all_items_for_entities.append(item)
            fact = f"[{item.pool_name}/{item.filename}] {item.content[:300]}"
            if fact not in seen_facts:
                seen_facts.add(fact)
                all_facts.append(fact)
        for item in sr.historical_items:
            fact = f"[历史/{item.pool_name}] {item.filename}: {item.content[:200]}"
            if fact not in seen_facts:
                seen_facts.add(fact)
                all_facts.append(fact)

    # 去重并限制数量
    result.semantic_facts = all_facts[:max_facts]
    result.total_facts = len(result.semantic_facts)

    # Step 3: 提取实体
    combined_text = "\n\n".join(
        [item.full_content[:2000] for item in all_items_for_entities]
    )

    # 从全景扫描结果和查询提取实体
    raw_entities = _extract_entities(combined_text, query)

    # 为实体补充来源和事实
    entity_map: Dict[str, EntityInfo] = {}
    for ent in raw_entities:
        if ent.name not in entity_map:
            entity_map[ent.name] = ent

    # 为每个实体关联事实
    for ent_name, ent in entity_map.items():
        for fact in result.semantic_facts[:50]:
            if ent_name.lower() in fact.lower():
                ent.related_facts.append(fact)
        # 记录来源池
        for item in all_items_for_entities:
            if ent_name.lower() in item.full_content[:2000].lower():
                if item.pool_name not in ent.source_pools:
                    ent.source_pools.append(item.pool_name)

    result.entity_insights = list(entity_map.values())
    result.total_entities = len(result.entity_insights)

    # Step 4: 构建关系链
    result.relationship_chains = _build_relation_chains(
        all_items_for_entities, result.entity_insights
    )
    result.total_relationships = len(result.relationship_chains)

    result.duration_ms = (time.time() - start_time) * 1000
    return result


# ============================================================================
# MODE 3: InterviewAgents — 采访员工
# ============================================================================

def _scan_employees() -> List[EmployeeInfo]:
    """扫描 employees/ 目录，读取所有员工信息"""
    employees: List[EmployeeInfo] = []
    if not os.path.isdir(EMPLOYEES_DIR):
        return employees

    for emp_dir_name in os.listdir(EMPLOYEES_DIR):
        emp_dir = os.path.join(EMPLOYEES_DIR, emp_dir_name)
        if not os.path.isdir(emp_dir):
            continue

        emp_id = emp_dir_name
        emp_name = emp_dir_name.replace("emp-", "").split("-")[0] if emp_dir_name.startswith("emp-") else emp_dir_name
        emp_label = ""
        emp_dept = ""
        emp_title = ""
        emp_bio = ""

        # 读取 employee.yaml
        yaml_path = os.path.join(emp_dir, "employee.yaml")
        if os.path.isfile(yaml_path):
            yaml_content = _read_file_safe(yaml_path)
            name_m = re.search(r"^name:\s*(.+)$", yaml_content, re.MULTILINE)
            if name_m:
                emp_name = name_m.group(1).strip()
            dept_m = re.search(r"^department:\s*(.+)$", yaml_content, re.MULTILINE)
            if dept_m:
                emp_dept = dept_m.group(1).strip()
            title_m = re.search(r"^title:\s*(.+)$", yaml_content, re.MULTILINE)
            if title_m:
                emp_title = title_m.group(1).strip()
            label_m = re.search(r"^label:\s*(.+)$", yaml_content, re.MULTILINE)
            if label_m:
                emp_label = label_m.group(1).strip()
            bio_m = re.search(r"^biography:\s*['\"]?(.+?)['\"]?\s*$", yaml_content, re.MULTILINE)
            if bio_m:
                emp_bio = bio_m.group(1).strip()

        # 读取 identity.md 补充bio
        identity_path = os.path.join(emp_dir, "memory", "facts", "identity.md")
        if os.path.isfile(identity_path):
            identity_content = _read_file_safe(identity_path)
            if identity_content and not emp_bio:
                # 提取定位部分
                loc_m = re.search(r"## 定位\n(.+?)(?:\n##|\Z)", identity_content, re.DOTALL)
                if loc_m:
                    emp_bio = loc_m.group(1).strip()

        employees.append(EmployeeInfo(
            emp_id=emp_id,
            name=emp_name,
            label=emp_label,
            department=emp_dept,
            title=emp_title,
            biography=emp_bio,
        ))

    return employees


def _select_employees_for_interview(
    employees: List[EmployeeInfo],
    topic: str,
    max_agents: int = 5,
) -> Tuple[List[EmployeeInfo], str]:
    """
    根据采访主题选择最相关的员工。
    基于关键词匹配 + 部门/标签相关性打分。
    """
    scored: List[Tuple[int, EmployeeInfo]] = []
    topic_tokens = set(_keyword_tokenize(topic))

    for emp in employees:
        score = 0
        # 检查员工名中是否含主题关键词
        for token in topic_tokens:
            if token in emp.name.lower():
                score += 50
            if token in emp.label.lower():
                score += 30
            if token in emp.department.lower():
                score += 30
            if token in emp.title.lower():
                score += 20
            if token in emp.biography.lower():
                score += 15
        # 部门权重
        dept_keywords = {
            "人力": ["人事", "招聘", "用工"],
            "技术": ["技术", "开发", "工程", "AI", "数据"],
            "运营": ["运营", "内容", "活动"],
            "市场": ["市场", "营销", "获客", "增长"],
            "金融": ["金融", "财务", "投资", "量化"],
            "情报": ["情报", "分析", "洞察"],
            "出海": ["出海", "海外", "国际化"],
            "渠道": ["渠道", "商务", "合作"],
        }
        for dept_type, keywords in dept_keywords.items():
            if dept_type in emp.department or any(k in emp.department for k in keywords):
                for token in topic_tokens:
                    if token in keywords or any(k.startswith(token) for k in keywords):
                        score += 25

        if score > 0:
            scored.append((score, emp))

    # 按相关性排序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 生成选择理由
    if scored:
        reasoning = (
            f"根据主题「{topic}」的关键词匹配，从 {len(employees)} 位员工中筛选出 "
            f"{len(scored)} 位相关员工。\n"
            f"Top {min(max_agents, len(scored))} 位："
        )
        for i, (sc, emp) in enumerate(scored[:max_agents]):
            reasoning += f"\n  {i+1}. {emp.name} ({emp.department}) — 得分 {sc}"
    else:
        reasoning = f"未找到与主题「{topic}」直接相关的员工，将随机选取。"
        # 随机选几个
        import random
        random.shuffle(scored)
        if employees:
            for emp in employees[:max_agents]:
                scored.append((1, emp))

    selected = [emp for _, emp in scored[:max_agents]]
    for emp in selected:
        emp.relevance_score = scored[selected.index(emp)][0] if selected.index(emp) < len(scored) else 0

    return selected, reasoning


def _read_memory_db(emp_dir: str) -> Dict[str, str]:
    """从 memory.db 中读取记忆内容"""
    memory_data: Dict[str, str] = {
        "facts": "",
        "decisions": "",
        "skills": "",
        "identity": "",
    }

    # 1. 读取 memory.db (SQLite)
    db_path = os.path.join(emp_dir, "memory", "memory.db")
    if os.path.isfile(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.text_factory = str
            cursor = conn.cursor()
            # 查询所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                try:
                    cursor.execute(f"SELECT * FROM \"{table}\" LIMIT 50")
                    rows = cursor.fetchall()
                    col_names = [d[0] for d in cursor.description]
                    text_parts = []
                    for row in rows:
                        row_dict = dict(zip(col_names, row))
                        # 取出所有文本列
                        for k, v in row_dict.items():
                            if isinstance(v, str) and len(v) > 10:
                                text_parts.append(f"[{k}]: {v[:500]}")
                    if text_parts:
                        memory_data["facts"] += "\n".join(text_parts[:20]) + "\n"
                except sqlite3.Error:
                    pass
            conn.close()
        except (sqlite3.Error, OSError) as e:
            memory_data["facts"] = f"[读取memory.db失败: {e}]"

    # 2. 读取 facts/ 目录下的 .md 文件
    facts_dir = os.path.join(emp_dir, "memory", "facts")
    if os.path.isdir(facts_dir):
        for fname in os.listdir(facts_dir):
            if fname.endswith(".md"):
                fpath = os.path.join(facts_dir, fname)
                content = _read_file_safe(fpath)
                key = fname.replace(".md", "")
                if key in memory_data:
                    memory_data[key] = content[:2000]

    # 3. 读取 soul-injection.yaml
    soul_path = os.path.join(emp_dir, "soul-injection.yaml")
    if os.path.isfile(soul_path):
        memory_data["identity"] += _read_file_safe(soul_path, 3000)

    return memory_data


def _generate_questions(topic: str, employees: List[EmployeeInfo],
                        max_questions: int = 3) -> List[str]:
    """
    生成采访问题列表。
    基于主题和员工属性生成个性化问题。
    """
    # 默认问题模板
    default_questions = [
        f"关于「{topic}」，你目前了解哪些信息？",
        f"你所在的角色如何看待「{topic}」？",
        f"针对「{topic}」，你有什么建议或意见？",
    ]

    # 如果特定员工有特定领域，补充领域问题
    domain_questions = []
    for emp in employees[:3]:
        if emp.department:
            domain_questions.append(
                f"作为{emp.department}的{emp.name}，你对「{topic}」有什么专业见解？"
            )

    questions = domain_questions[:2] + default_questions
    return questions[:max_questions]


def _synthesize_interview_summary(interviews: List[AgentInterview],
                                  topic: str) -> str:
    """整合多个采访回复生成摘要"""
    if not interviews:
        return "无采访记录"

    all_responses = [iv.response for iv in interviews if iv.response]
    if not all_responses:
        return "所有采访均无有效回复"

    combined = "\n\n".join(all_responses)
    # 提取共同主题
    lines = [
        f"「{topic}」采访摘要",
        f"采访人数: {len(interviews)} 位员工",
        "---",
    ]

    # 简单摘要：提取每个回复的前3句
    for iv in interviews:
        if iv.response:
            sentences = re.split(r"[。！？\n]", iv.response)
            key_points = [s.strip() for s in sentences
                          if len(s.strip()) > 10][:3]
            if key_points:
                lines.append(f"\n{iv.agent_name}:")
                for pt in key_points:
                    lines.append(f"  • {pt}")

    return "\n".join(lines)


def _extract_key_quotes(response: str, max_quotes: int = 3) -> List[str]:
    """从回复中提取关键引言"""
    quotes = []
    # 策略1: 中文引号内的内容
    quoted = re.findall(r"「([^」]+)」", response)
    for q in quoted:
        if len(q) >= 10 and len(q) <= 150 and q not in quotes:
            quotes.append(q)

    # 策略2: 英文引号
    quoted_en = re.findall(r'"([^"]{10,150})"', response)
    for q in quoted_en:
        if q not in quotes:
            quotes.append(q)

    # 策略3: 有实质内容的句子
    if len(quotes) < max_quotes:
        sentences = re.split(r"[。！？\n]", response)
        meaningful = [s.strip() for s in sentences
                      if 15 <= len(s.strip()) <= 100
                      and not s.strip().startswith(("问题", "Q:", "A:"))]
        for s in meaningful:
            if s not in quotes:
                quotes.append(s)
                if len(quotes) >= max_quotes:
                    break

    return quotes[:max_quotes]


def interview_agents(topic: str, max_agents: int = 5,
                     custom_questions: Optional[List[str]] = None) -> InterviewResult:
    """
    扫描 employees/ → 选相关员工 → 读取 memory.db → 整合回复
    """
    start_time = time.time()
    result = InterviewResult(topic=topic)

    # Step 1: 扫描所有员工
    employees = _scan_employees()
    result.total_employees = len(employees)
    if not employees:
        result.summary = "未找到任何员工档案"
        result.duration_ms = (time.time() - start_time) * 1000
        return result

    # Step 2: 选择相关员工
    selected, reasoning = _select_employees_for_interview(
        employees, topic, max_agents
    )
    result.selected_employees = selected
    result.selection_reasoning = reasoning

    # Step 3: 生成问题
    if custom_questions:
        result.questions = custom_questions
    else:
        result.questions = _generate_questions(topic, selected)

    # Step 4: 采集回答（从 memory.db 中读取）
    for emp in selected:
        emp_dir = os.path.join(EMPLOYEES_DIR, emp.emp_id)
        if not os.path.isdir(emp_dir):
            continue

        memory_data = _read_memory_db(emp_dir)

        # 构建回答：基于 memory.db + facts 合成
        response_parts = []

        # 如果有 identity 信息
        if memory_data["identity"].strip():
            response_parts.append(f"【身份信息】\n{memory_data['identity'][:500]}")

        # 如果有 facts 信息
        if memory_data["facts"].strip():
            response_parts.append(f"【相关记忆】\n{memory_data['facts'][:500]}")

        # 如果有 skills 信息
        if memory_data["skills"].strip():
            response_parts.append(f"【技能记录】\n{memory_data['skills'][:300]}")

        # 如果有 decisions 信息
        if memory_data["decisions"].strip():
            response_parts.append(f"【决策记录】\n{memory_data['decisions'][:300]}")

        combined_response = "\n\n".join(response_parts) if response_parts else \
            f"(员工 {emp.name} 暂无记忆数据)"

        # 提取关键引言
        key_quotes = _extract_key_quotes(combined_response)

        # 构建采访问题（基于员工属性的个性化问题）
        question = result.questions[0] if result.questions else f"关于「{topic}」你有什么看法？"
        if emp.department:
            question = f"作为{emp.department}的{emp.name}，关于「{topic}」你有什么了解或建议？"

        interview = AgentInterview(
            agent_name=emp.name,
            agent_role=emp.department or emp.label or "员工",
            agent_bio=emp.biography or emp.title or "",
            question=question,
            response=combined_response[:1000],
            key_quotes=key_quotes,
            memory_db_path=os.path.join(emp_dir, "memory", "memory.db"),
        )
        result.interviews.append(interview)

    result.interviewed_count = len(result.interviews)

    # Step 5: 整合摘要
    result.summary = _synthesize_interview_summary(result.interviews, topic)

    result.duration_ms = (time.time() - start_time) * 1000
    return result


# ============================================================================
# MODE 4: UnifiedQuery — 三模式联合
# ============================================================================

def unified_query(query: str, max_agents: int = 3) -> UnifiedResult:
    """
    三种模式都跑，综合输出。

    执行顺序：
    1. PanoramaScan 广度扫描（快速，总是先跑）
    2. DeepInsight 深度洞察（中等耗时）
    3. InterviewAgents 采访（最慢，最后跑）
    """
    start_time = time.time()
    result = UnifiedResult(query=query)

    # Mode 1: Panorama
    try:
        result.panorama = panorama_scan(query)
    except Exception as e:
        result.panorama = PanoramaResult(query=query)
        print(f"[WARN] PanoramaScan 失败: {e}", file=sys.stderr)

    # Mode 2: DeepInsight
    try:
        result.deep_insight = deep_insight(query)
    except Exception as e:
        result.deep_insight = DeepInsightResult(query=query)
        print(f"[WARN] DeepInsight 失败: {e}", file=sys.stderr)

    # Mode 3: Interview
    try:
        result.interview = interview_agents(query, max_agents=max_agents)
    except Exception as e:
        result.interview = InterviewResult(topic=query)
        print(f"[WARN] InterviewAgents 失败: {e}", file=sys.stderr)

    result.total_duration_ms = (time.time() - start_time) * 1000
    return result


# ============================================================================
# CLI 入口
# ============================================================================

def main():
    """CLI 入口"""
    if len(sys.argv) < 3:
        print("用法:")
        print("  python gaia_insightforge.py panorama \"查询词\"")
        print("  python gaia_insightforge.py deep \"复杂问题\"")
        print("  python gaia_insightforge.py interview \"采访主题\"")
        print("  python gaia_insightforge.py unified \"综合查询\"")
        print("  python gaia_insightforge.py unified \"查询\" --json")
        sys.exit(1)

    mode = sys.argv[1]
    query = sys.argv[2]
    output_json = "--json" in sys.argv

    if mode == "panorama":
        result = panorama_scan(query)
        if output_json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(result.to_text())

    elif mode == "deep":
        result = deep_insight(query)
        if output_json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(result.to_text())

    elif mode == "interview":
        result = interview_agents(query)
        if output_json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(result.to_text())

    elif mode == "unified":
        result = unified_query(query)
        if output_json:
            # 合并输出
            output = {
                "query": query,
                "total_duration_ms": round(result.total_duration_ms, 2),
                "panorama": result.panorama.to_dict() if result.panorama else None,
                "deep_insight": result.deep_insight.to_dict() if result.deep_insight else None,
                "interview": result.interview.to_dict() if result.interview else None,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(result.to_text())

    else:
        print(f"未知模式: {mode}，可选: panorama / deep / interview / unified")
        sys.exit(1)


if __name__ == "__main__":
    main()
