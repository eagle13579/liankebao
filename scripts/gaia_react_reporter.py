#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gaia_react_reporter.py — ReACT日报生成器 (MF-07)
================================================

三段式日报生成引擎：
  Phase 1: plan_report(context) → LLM规划报告目录结构
  Phase 2: generate_section(section, tools) → 每章独立ReACT: Reason→ToolCall→Analysis→Write
  Phase 3: integrate_report(sections) → 交叉引用 + 执行摘要

从 MiroFish report_agent.py (101KB) 吸取设计:
  - ReportLogger 结构化日志 (JSONL)
  - ReACT循环：Thought → <tool_call> → Observation → Final Answer
  - 每章独立LLM调用，注意力集中
  - 冲突处理：工具调用与Final Answer同时出现时的降级策略

工具列表:
  - scan_employees()   — 扫描军团雇员状态
  - check_services()   — 检查服务健康度
  - scan_pools()       — 扫描资源池水位
  - scan_features()    — 扫描产品特性进展

输出: Markdown格式日报报告

位置: D:\\向海容的知识库\\wiki\\wiki\\记忆宫殿\\scripts\\gaia_react_reporter.py
"""

import os
import re
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ═══════════════════════════════════════════════════════════════
# 路径常量 — 所有路径基于记忆宫殿
# ═══════════════════════════════════════════════════════════════

PALACE_BASE = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
REPORTS_DIR = os.path.join(PALACE_BASE, "reports")
LOGS_DIR = os.path.join(PALACE_BASE, "logs", "react_reporter")
DEFAULT_OUTPUT = os.path.join(REPORTS_DIR, "daily_react_report.md")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 日志系统
# ═══════════════════════════════════════════════════════════════

logger = logging.getLogger("gaia.react_reporter")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setLevel(logging.DEBUG)
    _fmtr = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    _ch.setFormatter(_fmtr)
    logger.addHandler(_ch)


class ReportLogger:
    """ReACT日报结构化日志记录器 — 每步action/stage/section写入JSONL"""

    def __init__(self, report_id: str):
        self.report_id = report_id
        self.log_file = os.path.join(LOGS_DIR, f"{report_id}_agent_log.jsonl")
        self.start_time = datetime.now()
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write("")

    def _elapsed(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def _write(self, action: str, stage: str, details: Dict[str, Any],
               section_title: str = None, section_index: int = None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._elapsed(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_start(self, context: str):
        self._write("report_start", "pending", {"context": context, "message": "日报生成任务开始"})

    def log_planning_start(self):
        self._write("planning_start", "planning", {"message": "开始规划日报目录结构"})

    def log_planning_complete(self, outline: Dict[str, Any]):
        self._write("planning_complete", "planning", {"outline": outline, "message": "目录结构规划完成"})

    def log_section_start(self, title: str, idx: int):
        self._write("section_start", "generating", {"message": f"开始生成章节: {title}"},
                     section_title=title, section_index=idx)

    def log_react_thought(self, title: str, idx: int, iteration: int, thought: str):
        self._write("react_thought", "generating", {"iteration": iteration, "thought": thought},
                     section_title=title, section_index=idx)

    def log_tool_call(self, title: str, idx: int, tool: str, params: Dict[str, Any], iteration: int):
        self._write("tool_call", "generating", {"iteration": iteration, "tool": tool, "params": params},
                     section_title=title, section_index=idx)

    def log_tool_result(self, title: str, idx: int, tool: str, result: str, iteration: int):
        self._write("tool_result", "generating",
                     {"iteration": iteration, "tool": tool, "result": result, "result_len": len(result)},
                     section_title=title, section_index=idx)

    def log_llm_response(self, title: str, idx: int, response: str, iteration: int,
                         has_tool: bool, has_final: bool):
        self._write("llm_response", "generating",
                     {"iteration": iteration, "response": response, "response_len": len(response),
                      "has_tool_call": has_tool, "has_final_answer": has_final},
                     section_title=title, section_index=idx)

    def log_section_complete(self, title: str, idx: int, content: str, tool_count: int):
        self._write("section_complete", "generating",
                     {"content": content, "content_len": len(content), "tool_calls": tool_count},
                     section_title=title, section_index=idx)

    def log_report_complete(self, total_sections: int, total_seconds: float):
        self._write("report_complete", "completed",
                     {"total_sections": total_sections, "total_seconds": round(total_seconds, 2),
                      "message": "日报生成完成"})

    def log_error(self, error: str, stage: str, section_title: str = None):
        self._write("error", stage, {"error": error, "message": f"错误: {error}"},
                     section_title=section_title)


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

class ReportStage(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    INTEGRATING = "integrating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """日报章节"""
    title: str
    description: str = ""
    content: str = ""

    def to_md(self, level: int = 2) -> str:
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "description": self.description, "content": self.content}


@dataclass
class ReportOutline:
    """日报大纲"""
    title: str
    summary: str
    sections: List[ReportSection]

    def to_md(self) -> str:
        md = f"# {self.title}\n\n> {self.summary}\n\n"
        for s in self.sections:
            md += s.to_md()
        return md

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "summary": self.summary, "sections": [s.to_dict() for s in self.sections]}


@dataclass
class DailyReport:
    """完整日报"""
    report_id: str
    context: str
    status: ReportStage = ReportStage.PENDING
    outline: Optional[ReportOutline] = None
    markdown: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "context": self.context,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown": self.markdown,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


# ═══════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════

TOOL_DESCRIPTIONS = """\
可用工具：

1. **scan_employees(query: str)**
   - 扫描军团雇员状态，包括在线率、任务完成率、情绪指数
   - 参数: query — 搜索/过滤条件（如 "all", "online", "offline", "legion"）
   - 返回: 雇员列表及其健康指标

2. **check_services(service_names: List[str])**
   - 检查服务健康度，包括响应时间、错误率、资源占用
   - 参数: service_names — 要检查的服务名称列表（如 ["api_gateway", "matrix", "polaris"]）
   - 返回: 各服务的健康状态详情

3. **scan_pools(pool_name: str = "")**
   - 扫描资源池水位，包括CPU/内存/磁盘/连接池使用率
   - 参数: pool_name — 指定池名称（为空则扫描全部）
   - 返回: 各资源池的水位和趋势

4. **scan_features(feature_tags: List[str] = [])**
   - 扫描产品特性进展，包括完成度、质量分、最近更新
   - 参数: feature_tags — 特性标签过滤（为空则扫描全部）
   - 返回: 各特性的状态和演进数据
"""

PLAN_SYSTEM_PROMPT = """\
你是一个Gaia军团「ReACT日报」的总编辑，负责规划每日报告的目录结构。

【核心理念】
Gaia军团是一个由AI雇员、微服务、资源池和持续进化产品组成的智能体组织。
每日报告需要从全局视角审视军团运行状态，发现信号，追踪进化，预警风险。

【你的任务】
分析当前上下文，规划一份精炼的日报目录结构。报告应包含4个核心维度：
1. 军团健康度 — 雇员状态、服务可用性、资源水位
2. 信号发现 — 异常信号、趋势变化、值得关注的事件
3. 产品进化 — 特性进展、质量变化、演进方向
4. 风险预警 — 潜在风险、瓶颈识别、建议行动

【格式要求】
输出JSON格式:
{
    "title": "日报标题（含日期）",
    "summary": "一句话总览",
    "sections": [
        {"title": "章节标题", "description": "本章聚焦什么"},
        ...
    ]
}
sections数量: 4-8个。每个章节必须对应一个核心维度标记: HEALTH/SIGNAL/EVOLVE/RISK。
"""

PLAN_USER_PROMPT_TEMPLATE = """\
【今日上下文】
{context}

请根据上述上下文，规划一份精炼的Gaia军团ReACT日报目录结构。
日报日期: {date}

注意:
- 覆盖军团健康度、信号发现、产品进化、风险预警四大维度
- 每个章节标注其维度标记
- 输出JSON格式，不要额外解释
"""

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
你是一个Gaia军团「ReACT日报」的特约撰稿人，正在撰写日报中的一个章节。

═══════════════════════════════════════════════════════════════
报告标题: {report_title}
报告摘要: {report_summary}
当前章节: {section_title}
章节维度: {section_dimension}
═══════════════════════════════════════════════════════════════

【工作模式 - ReACT】
你必须通过 Reason → ToolCall → Analysis → Write 的循环来完成本章节。

每次回复只能做以下两件事之一（不可同时）:
1. **调用工具**: 输出思考后，用 <tool_call>{{"name": "工具名", "parameters": {{...}}}}</tool_call> 调用一个工具
2. **输出最终内容**: 以 `Final Answer:` 开头输出章节的Markdown正文

【规则】
- 每个章节至少调用3次工具，最多5次
- 工具结果必须被分析和引用，不能忽略
- 禁止自己编造工具返回结果
- 最终内容必须基于工具返回的真实数据
- 使用Markdown格式: **粗体**、列表、引用、表格
- 在最终内容末尾标注本章参考的工具列表

【可用工具】
{tools_description}
"""

SECTION_USER_PROMPT_TEMPLATE = """\
已完成的章节内容（请仔细阅读，避免重复）:
{previous_content}

═══════════════════════════════════════════════════════════════
【当前任务】撰写章节: {section_title}
═══════════════════════════════════════════════════════════════

请开始:
1. 思考(Thought)本章需要什么数据
2. 调用工具(Action)获取数据
3. 分析结果(Observation)
4. 信息充分后输出 Final Answer: 及Markdown正文
"""

REACT_OBSERVATION_TEMPLATE = """\
Observation（工具返回）:

═══ 工具 "{tool_name}" 返回 ═══
{result}

═══════════════════════════════════════════════════════════════
已调用 {tool_calls_count}/{max_tool_calls} 次工具
已使用: {used_tools}
{unused_hint}
- 信息充分 → 以 "Final Answer:" 开头输出章节内容
- 需要更多 → 调用工具继续检索
═══════════════════════════════════════════════════════════════
"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "【注意】你只调用了 {tool_calls_count} 次工具，至少需要 {min_tool_calls} 次。"
    "请继续调用工具获取更多数据，然后再输出 Final Answer。{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "工具调用次数已达上限 ({tool_calls_count}/{max_tool_calls})，不能再调用工具。"
    "请立即基于已获取的信息，以 'Final Answer:' 开头输出章节内容。"
)

REACT_UNUSED_HINT = "\n💡 还未使用: {unused_list}，建议尝试不同工具获取多角度信息"

REACT_FORCE_FINAL_MSG = "已达到工具调用限制，请直接输出 Final Answer: 并生成章节内容。"

INTEGRATE_SYSTEM_PROMPT = """\
你是一个Gaia军团「ReACT日报」的终审主编，负责整合所有章节并生成执行摘要。

【你的任务】
1. 为整份日报撰写「执行摘要」— 提炼最关键的3-5个发现
2. 在章节之间添加交叉引用 — 发现不同章节间的关联信号
3. 确保整体叙事流畅，逻辑连贯

【输出格式】
输出包含两部分:
1. exec_summary: 执行摘要Markdown文本
2. cross_refs: 交叉引用列表 [{"from": "章节A", "to": "章节B", "insight": "关联发现"}]
"""

INTEGRATE_USER_PROMPT_TEMPLATE = """\
请为以下日报进行整合和精炼。

报告标题: {report_title}
报告日期: {date}

各章节内容:
{sections_text}

请输出JSON:
{{
    "exec_summary": "执行摘要Markdown...",
    "cross_refs": [
        {{"from": "章节A", "to": "章节B", "insight": "关联发现"}}
    ]
}}
"""


# ═══════════════════════════════════════════════════════════════
# 工具函数（模拟 / 实际调用）
# ═══════════════════════════════════════════════════════════════

def scan_employees(query: str = "all") -> str:
    """扫描军团雇员状态"""
    # 模拟实现 — 生产环境应替换为实际API调用
    now = datetime.now().strftime("%H:%M")
    return json.dumps({
        "status": "ok",
        "timestamp": now,
        "query": query,
        "summary": {
            "total_employees": 24,
            "online": 19,
            "offline": 3,
            "idle": 2,
            "avg_completion_rate": 87.3,
            "avg_morale_index": 72.5,
        },
        "details": [
            {"name": "Athena", "role": "orchestrator", "status": "online", "completion": 94, "morale": 81},
            {"name": "Hermes", "role": "messenger", "status": "online", "completion": 91, "morale": 78},
            {"name": "Polaris", "role": "scheduler", "status": "online", "completion": 88, "morale": 75},
            {"name": "Matrix", "role": "sync", "status": "online", "completion": 85, "morale": 70},
            {"name": "Hephaestus", "role": "builder", "status": "offline", "completion": 62, "morale": 45},
        ]
    }, ensure_ascii=False, indent=2)


def check_services(service_names: List[str] = None) -> str:
    """检查服务健康度"""
    if service_names is None:
        service_names = ["api_gateway", "matrix", "polaris", "evolution", "watchdog"]
    return json.dumps({
        "status": "ok",
        "timestamp": datetime.now().strftime("%H:%M"),
        "services": [
            {"name": "api_gateway", "health": "healthy", "response_ms": 42, "error_rate": 0.3, "cpu": 34,
             "memory": 58},
            {"name": "matrix", "health": "healthy", "response_ms": 128, "error_rate": 1.2, "cpu": 52, "memory": 71},
            {"name": "polaris", "health": "degraded", "response_ms": 345, "error_rate": 3.8, "cpu": 78, "memory": 89,
             "note": "连接池水位过高，建议扩容"},
            {"name": "evolution", "health": "healthy", "response_ms": 67, "error_rate": 0.1, "cpu": 28, "memory": 44},
            {"name": "watchdog", "health": "healthy", "response_ms": 15, "error_rate": 0.0, "cpu": 12, "memory": 33},
        ]
    }, ensure_ascii=False, indent=2)


def scan_pools(pool_name: str = "") -> str:
    """扫描资源池水位"""
    return json.dumps({
        "status": "ok",
        "timestamp": datetime.now().strftime("%H:%M"),
        "pools": [
            {"name": "cpu_pool", "usage_pct": 47, "capacity": 100, "trend": "stable", "alert": False},
            {"name": "memory_pool", "usage_pct": 63, "capacity": 100, "trend": "rising", "alert": False},
            {"name": "disk_pool", "usage_pct": 72, "capacity": 100, "trend": "rising", "alert": True,
             "note": "磁盘使用率超过70%阈值"},
            {"name": "connection_pool", "usage_pct": 81, "capacity": 100, "trend": "rising", "alert": True,
             "note": "连接池即将耗尽，建议立即扩容"},
            {"name": "gpu_pool", "usage_pct": 38, "capacity": 100, "trend": "stable", "alert": False},
        ]
    }, ensure_ascii=False, indent=2)


def scan_features(feature_tags: List[str] = None) -> str:
    """扫描产品特性进展"""
    if feature_tags is None:
        feature_tags = []
    return json.dumps({
        "status": "ok",
        "timestamp": datetime.now().strftime("%H:%M"),
        "features": [
            {"name": "ReACT日报引擎", "tag": "core", "completion": 92, "quality_score": 88, "last_update": "2026-06-07",
             "status": "active"},
            {"name": "军团自愈系统", "tag": "reliability", "completion": 78, "quality_score": 72, "last_update": "2026-06-06",
             "status": "active"},
            {"name": "多模态感知层", "tag": "perception", "completion": 45, "quality_score": 60, "last_update": "2026-06-05",
             "status": "dev"},
            {"name": "自动扩缩容", "tag": "scaling", "completion": 63, "quality_score": 55, "last_update": "2026-06-04",
             "status": "active"},
            {"name": "知识蒸馏管道", "tag": "learning", "completion": 81, "quality_score": 79, "last_update": "2026-06-07",
             "status": "active"},
        ]
    }, ensure_ascii=False, indent=2)


TOOL_REGISTRY = {
    "scan_employees": scan_employees,
    "check_services": check_services,
    "scan_pools": scan_pools,
    "scan_features": scan_features,
}

VALID_TOOL_NAMES = set(TOOL_REGISTRY.keys())

# 维度标记 -> 建议优先使用的工具
DIMENSION_TOOLS = {
    "HEALTH": ["scan_employees", "check_services", "scan_pools"],
    "SIGNAL": ["scan_employees", "scan_pools", "scan_features"],
    "EVOLVE": ["scan_features", "scan_employees"],
    "RISK": ["check_services", "scan_pools", "scan_employees"],
}


# ═══════════════════════════════════════════════════════════════
# ReACT日报生成器主类
# ═══════════════════════════════════════════════════════════════

class GaiaReactReporter:
    """Gaia ReACT日报生成器 — 三段式引擎"""

    MAX_TOOL_CALLS_PER_SECTION = 5
    MIN_TOOL_CALLS_PER_SECTION = 3

    def __init__(self, llm_call: Optional[Callable] = None):
        """
        初始化ReACT日报生成器

        Args:
            llm_call: LLM调用函数，接收 (system_prompt, messages) 返回文本。
                      如果为None，使用内置的模拟LLM用于测试。
        """
        self.llm_call = llm_call or self._simulated_llm
        self.report_logger: Optional[ReportLogger] = None

    # ── 模拟LLM（用于开发测试，生产环境替换为真实LLM） ──

    def _simulated_llm(self, system: str, messages: List[Dict[str, str]]) -> str:
        """模拟LLM调用 — 用于开发测试"""
        last_msg = messages[-1]["content"] if messages else ""
        if "plan" in system.lower() and "outline" in system.lower():
            date_str = datetime.now().strftime("%Y-%m-%d")
            return json.dumps({
                "title": f"Gaia军团ReACT日报 — {date_str}",
                "summary": f"第{datetime.now().day}期日报：军团整体健康，Polaris服务出现连接池瓶颈，磁盘使用率触发预警。",
                "sections": [
                    {"title": "军团健康全景", "description": "HEALTH: 雇员在线率、服务SLA、资源池水位",
                     "dimension": "HEALTH"},
                    {"title": "信号与趋势发现", "description": "SIGNAL: 异常信号、趋势变化、值得关注的事件",
                     "dimension": "SIGNAL"},
                    {"title": "产品演进追踪", "description": "EVOLVE: 特性进展、质量变化、演进方向",
                     "dimension": "EVOLVE"},
                    {"title": "风险识别与建议", "description": "RISK: 潜在风险、瓶颈定位、行动建议",
                     "dimension": "RISK"},
                ]
            })
        if "integrate" in system.lower():
            return json.dumps({
                "exec_summary": "## 执行摘要\n\n本日报覆盖四大维度...\n",
                "cross_refs": [
                    {"from": "军团健康全景", "to": "风险识别与建议",
                     "insight": "Polaris服务降级与连接池高水位形成直接因果关系"},
                ]
            })
        return (
            "Final Answer: 本章节基于工具扫描数据进行分析。\n\n"
            "**核心发现**\n\n"
            "- 在线率79.2%，较昨日下降3个百分点\n"
            "- 平均任务完成率87.3%，处于健康区间\n\n"
            "_数据来源: scan_employees, check_services_"
        )

    # ── 工具执行 ──

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """执行一个工具调用"""
        tool_fn = TOOL_REGISTRY.get(tool_name)
        if not tool_fn:
            return json.dumps({"error": f"未知工具: {tool_name}", "valid_tools": list(VALID_TOOL_NAMES)})
        try:
            return tool_fn(**parameters)
        except TypeError as e:
            # 尝试无参数调用
            try:
                return tool_fn()
            except Exception:
                return json.dumps({"error": f"工具调用参数错误: {e}"})
        except Exception as e:
            return json.dumps({"error": f"工具执行失败: {e}"})

    def _get_tools_description(self) -> str:
        return TOOL_DESCRIPTIONS

    # ── 工具调用解析 ──

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """从LLM响应中解析工具调用，支持 <tool_call> 标签和裸JSON"""
        calls = []

        # 格式1: <tool_call>{"name": "...", "parameters": {...}}</tool_call>
        for match in re.finditer(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', response, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                calls.append(data)
            except json.JSONDecodeError:
                pass

        if calls:
            return calls

        # 格式2: 裸JSON兜底
        stripped = response.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
                if self._validate_tool_call(data):
                    calls.append(data)
                    return calls
            except json.JSONDecodeError:
                pass

        # 格式3: 从文本中提取末尾JSON
        json_match = re.search(r'(\{"(?:name|tool)"\s*:.*?\})\s*$', stripped, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if self._validate_tool_call(data):
                    calls.append(data)
            except json.JSONDecodeError:
                pass

        return calls

    def _validate_tool_call(self, data: dict) -> bool:
        """校验工具调用合法性"""
        name = data.get("name") or data.get("tool")
        if name and name in VALID_TOOL_NAMES:
            # 统一键名
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            if "parameters" not in data:
                data["parameters"] = {}
            return True
        return False

    # ══════════════════════════════════════════════════════════
    # Phase 1: 规划报告目录
    # ══════════════════════════════════════════════════════════

    def plan_report(self, context: str, progress_cb: Optional[Callable] = None) -> ReportOutline:
        """
        Phase 1 — LLM规划报告目录结构

        Args:
            context: 日报上下文（今日事件、关注重点等）
            progress_cb: 进度回调 (stage, progress, message)

        Returns:
            ReportOutline: 包含标题、摘要和章节列表
        """
        logger.info("[Phase 1] 开始规划日报目录结构...")
        if self.report_logger:
            self.report_logger.log_planning_start()
        if progress_cb:
            progress_cb("planning", 10, "正在分析上下文...")

        date_str = datetime.now().strftime("%Y-%m-%d %A")
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(context=context, date=date_str)

        if progress_cb:
            progress_cb("planning", 40, "正在调用LLM规划目录...")

        raw = self.llm_call(PLAN_SYSTEM_PROMPT, [
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        if progress_cb:
            progress_cb("planning", 70, "正在解析大纲结构...")

        # 尝试解析JSON
        outline_data = self._try_parse_json(raw)
        if not outline_data or "sections" not in outline_data:
            logger.warning("LLM返回非标准格式，使用默认大纲")
            outline_data = self._default_outline(context)

        sections = []
        for i, sec_data in enumerate(outline_data.get("sections", [])):
            title = sec_data.get("title", f"章节{i + 1}")
            desc = sec_data.get("description", "")
            sections.append(ReportSection(title=title, description=desc))

        outline = ReportOutline(
            title=outline_data.get("title", f"Gaia军团ReACT日报 — {date_str}"),
            summary=outline_data.get("summary", "军团日常运行报告"),
            sections=sections,
        )

        if self.report_logger:
            self.report_logger.log_planning_complete(outline.to_dict())
        if progress_cb:
            progress_cb("planning", 100, f"目录规划完成，共{len(sections)}个章节")

        logger.info(f"[Phase 1] 规划完成: {len(sections)} 个章节")
        return outline

    def _default_outline(self, context: str) -> Dict[str, Any]:
        """默认大纲（LLM异常时的fallback）"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return {
            "title": f"Gaia军团ReACT日报 — {date_str}",
            "summary": "军团运行状态总览与关键发现",
            "sections": [
                {"title": "军团健康全景", "description": "HEALTH: 雇员状态、服务可用性、资源消耗"},
                {"title": "信号与趋势发现", "description": "SIGNAL: 异常模式、变化趋势、关注事件"},
                {"title": "产品演进追踪", "description": "EVOLVE: 特性进展、质量变化、演进方向"},
                {"title": "风险识别与行动建议", "description": "RISK: 风险定位、瓶颈分析、建议措施"},
            ],
        }

    # ══════════════════════════════════════════════════════════
    # Phase 2: 逐章ReACT生成
    # ══════════════════════════════════════════════════════════

    def _get_section_dimension(self, section: ReportSection) -> str:
        """从章节描述中提取维度标记"""
        for dim in ["HEALTH", "SIGNAL", "EVOLVE", "RISK"]:
            if dim in section.description.upper():
                return dim
        # 关键词推断
        kw_map = {
            "健康": "HEALTH", "雇员": "HEALTH", "服务": "HEALTH",
            "信号": "SIGNAL", "趋势": "SIGNAL", "发现": "SIGNAL",
            "产品": "EVOLVE", "进化": "EVOLVE", "演进": "EVOLVE", "特性": "EVOLVE",
            "风险": "RISK", "预警": "RISK", "建议": "RISK", "瓶颈": "RISK",
        }
        for kw, dim in kw_map.items():
            if kw in section.title or kw in section.description:
                return dim
        return "GENERAL"

    def generate_section(self, section: ReportSection, outline: ReportOutline,
                         previous_sections: List[str],
                         section_index: int = 1,
                         progress_cb: Optional[Callable] = None) -> str:
        """
        Phase 2 — 每章独立ReACT: Reason → ToolCall → Analysis → Write

        Args:
            section: 要生成的章节
            outline: 完整报告大纲
            previous_sections: 已完成章节的Markdown列表
            section_index: 章节序号
            progress_cb: 进度回调

        Returns:
            str: 章节内容的Markdown文本
        """
        dimension = self._get_section_dimension(section)
        logger.info(f"[Phase 2] 生成章节 #{section_index}: {section.title} (维度: {dimension})")

        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)

        if progress_cb:
            progress_cb("generating", 0, f"开始生成: {section.title}")

        # 构建system prompt
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            section_title=section.title,
            section_dimension=dimension,
            tools_description=self._get_tools_description(),
        )

        # 构建user prompt
        prev_text = "（这是第一个章节）"
        if previous_sections:
            prev_parts = []
            for sec in previous_sections:
                truncated = sec[:3000] + "..." if len(sec) > 3000 else sec
                prev_parts.append(truncated)
            prev_text = "\n\n---\n\n".join(prev_parts)

        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=prev_text,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # ReACT循环
        tool_calls_count = 0
        max_iterations = 8
        used_tools = set()
        conflict_retries = 0

        for iteration in range(max_iterations):
            if progress_cb:
                progress_cb("generating",
                             int((iteration / max_iterations) * 80),
                             f"ReACT迭代 {iteration + 1}/{max_iterations} (已调用{tool_calls_count}次工具)")

            response = self.llm_call(system_prompt, messages)

            if not response:
                logger.warning(f"章节 {section.title} 迭代 {iteration + 1}: LLM返回空")
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "（响应为空）"})
                    messages.append({"role": "user", "content": "请继续生成内容。"})
                    continue
                break

            tool_calls = self._parse_tool_calls(response)
            has_tool = bool(tool_calls)
            has_final = "Final Answer:" in response or "final answer:" in response.lower()

            # ── 冲突处理 ──
            if has_tool and has_final:
                conflict_retries += 1
                logger.warning(f"章节 {section.title} 第{iteration + 1}轮: 同时包含工具调用和Final Answer (第{conflict_retries}次)")
                if conflict_retries <= 2:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "【格式错误】一次回复中不能同时包含工具调用和Final Answer。\n"
                            "请只做一件事：要么调用一个工具，要么以 'Final Answer:' 开头输出最终内容。"
                        ),
                    })
                    continue
                else:
                    # 第三次冲突 → 截断到工具调用
                    end_tag = response.find("</tool_call>")
                    if end_tag != -1:
                        response = response[:end_tag + len("</tool_call>")]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool = bool(tool_calls)
                    has_final = False
                    conflict_retries = 0

            # 记录LLM响应
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section.title, section_index, response,
                    iteration + 1, has_tool, has_final,
                )

            # ── Final Answer ──
            if has_final and not has_tool:
                if tool_calls_count < self.MIN_TOOL_CALLS_PER_SECTION:
                    unused = list(VALID_TOOL_NAMES - used_tools)
                    hint = REACT_UNUSED_HINT.format(unused_list="、".join(unused)) if unused else ""
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=self.MIN_TOOL_CALLS_PER_SECTION,
                            unused_hint=hint,
                        ),
                    })
                    continue

                # ✅ 正常结束
                final_answer = response.split("Final Answer:", 1)[-1].strip()
                if not final_answer:
                    final_answer = response.split("final answer:", 1)[-1].strip()
                if not final_answer:
                    final_answer = response

                # 添加工具引用脚注
                tool_ref = "\n\n---\n_本章数据来源: " + ", ".join(sorted(used_tools)) + "_"
                final_answer += tool_ref

                logger.info(f"章节 {section.title} 生成完成 ({tool_calls_count}次工具调用)")
                if self.report_logger:
                    self.report_logger.log_section_complete(
                        section.title, section_index, final_answer, tool_calls_count,
                    )
                if progress_cb:
                    progress_cb("generating", 100, f"章节完成: {section.title}")
                return final_answer

            # ── 工具调用 ──
            if has_tool:
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                call = tool_calls[0]
                tool_name = call.get("name", "")
                params = call.get("parameters", {})

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section.title, section_index, tool_name, params, iteration + 1,
                    )

                # 执行工具
                result = self._execute_tool(tool_name, params)

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section.title, section_index, tool_name, result, iteration + 1,
                    )

                tool_calls_count += 1
                used_tools.add(tool_name)

                # 构建未使用工具提示
                unused_tools = VALID_TOOL_NAMES - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_HINT.format(unused_list="、".join(sorted(unused_tools)))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=tool_name,
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools="、".join(sorted(used_tools)),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── 既无工具也无Final Answer ──
            messages.append({"role": "assistant", "content": response})
            if tool_calls_count < self.MIN_TOOL_CALLS_PER_SECTION:
                unused = list(VALID_TOOL_NAMES - used_tools)
                hint = REACT_UNUSED_HINT.format(unused_list="、".join(unused)) if unused else ""
                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=self.MIN_TOOL_CALLS_PER_SECTION,
                        unused_hint=hint,
                    ),
                })
                continue

            # 工具调用已足够，直接采纳
            final_answer = response.strip()
            tool_ref = "\n\n---\n_本章数据来源: " + ", ".join(sorted(used_tools)) + "_"
            final_answer += tool_ref

            logger.info(f"章节 {section.title} 直接采纳LLM输出 ({tool_calls_count}次工具)")
            if self.report_logger:
                self.report_logger.log_section_complete(
                    section.title, section_index, final_answer, tool_calls_count,
                )
            return final_answer

        # 达到最大迭代次数 → 强制生成
        logger.warning(f"章节 {section.title} 达到最大迭代次数，强制收尾")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        response = self.llm_call(system_prompt, messages)

        if response and "Final Answer:" in response:
            final_answer = response.split("Final Answer:", 1)[-1].strip()
        elif response and "final answer:" in response.lower():
            final_answer = response.split("final answer:", 1)[-1].strip()
        else:
            final_answer = response or "（本章节生成失败）"

        tool_ref = "\n\n---\n_本章数据来源: " + ", ".join(sorted(used_tools)) + "_"
        final_answer += tool_ref

        if self.report_logger:
            self.report_logger.log_section_complete(
                section.title, section_index, final_answer, tool_calls_count,
            )
        return final_answer

    # ══════════════════════════════════════════════════════════
    # Phase 3: 整合报告
    # ══════════════════════════════════════════════════════════

    def integrate_report(self, sections: List[Tuple[str, str]],
                         outline: ReportOutline,
                         progress_cb: Optional[Callable] = None) -> str:
        """
        Phase 3 — 交叉引用 + 执行摘要

        Args:
            sections: [(title, content_md), ...] 已完成的所有章节
            outline: 报告大纲
            progress_cb: 进度回调

        Returns:
            str: 完整报告的Markdown文本
        """
        logger.info("[Phase 3] 开始整合报告...")
        if progress_cb:
            progress_cb("integrating", 10, "正在生成执行摘要和交叉引用...")

        # 构建章节文本
        sections_text = ""
        for i, (title, content) in enumerate(sections):
            sections_text += f"## {title}\n\n{content}\n\n---\n\n"

        # 调用LLM进行整合
        date_str = datetime.now().strftime("%Y-%m-%d")
        user_prompt = INTEGRATE_USER_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            date=date_str,
            sections_text=sections_text,
        )

        if progress_cb:
            progress_cb("integrating", 40, "正在调用LLM整合报告...")

        raw = self.llm_call(INTEGRATE_SYSTEM_PROMPT, [
            {"role": "system", "content": INTEGRATE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        if progress_cb:
            progress_cb("integrating", 70, "正在组装完整报告...")

        integ_data = self._try_parse_json(raw)
        exec_summary = ""
        cross_refs = []

        if integ_data:
            exec_summary = integ_data.get("exec_summary", "")
            cross_refs = integ_data.get("cross_refs", [])
        else:
            exec_summary = "## 执行摘要\n\n（自动生成摘要失败，请参考各章节内容。）"

        # 组装完整报告
        full_md = f"# {outline.title}\n\n> {outline.summary}\n\n"

        # 执行摘要
        if exec_summary:
            full_md += f"{exec_summary}\n\n---\n\n"

        # 交叉引用
        if cross_refs:
            full_md += "## 交叉引用\n\n"
            for ref in cross_refs:
                full_md += f"- **{ref.get('from', '?')}** ↔ **{ref.get('to', '?')}**: {ref.get('insight', '')}\n"
            full_md += "\n---\n\n"

        # 各章节
        for title, content in sections:
            full_md += f"## {title}\n\n{content}\n\n---\n\n"

        # 页脚
        full_md += (
            f"\n---\n"
            f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
            f"*生成引擎: Gaia ReACT日报生成器 v1.0 (MF-07)*\n"
            f"*生成方式: 三段式ReACT (规划→逐章生成→整合)*\n"
        )

        if progress_cb:
            progress_cb("integrating", 100, "报告整合完成")

        logger.info(f"[Phase 3] 整合完成: {len(sections)} 个章节, {len(cross_refs)} 个交叉引用")
        return full_md

    # ══════════════════════════════════════════════════════════
    # 完整日报生成流程
    # ══════════════════════════════════════════════════════════

    def generate_daily_report(self, context: str,
                              output_path: str = DEFAULT_OUTPUT,
                              progress_cb: Optional[Callable] = None) -> DailyReport:
        """
        三段式ReACT日报生成

        Args:
            context: 日报上下文
            output_path: 输出文件路径
            progress_cb: 进度回调 (stage, progress, message)

        Returns:
            DailyReport: 完整报告对象
        """
        report_id = f"react_daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.report_logger = ReportLogger(report_id)
        start_time = datetime.now()

        report = DailyReport(
            report_id=report_id,
            context=context,
            status=ReportStage.PENDING,
            created_at=datetime.now().isoformat(),
        )

        try:
            # 记录开始
            self.report_logger.log_start(context)
            if progress_cb:
                progress_cb("pending", 0, "初始化日报生成器...")

            # ── Phase 1: 规划 ──
            report.status = ReportStage.PLANNING
            if progress_cb:
                progress_cb("planning", 5, "开始规划日报目录...")

            outline = self.plan_report(context, progress_cb=progress_cb)
            report.outline = outline

            if progress_cb:
                progress_cb("planning", 100, f"目录规划完成")

            # ── Phase 2: 逐章ReACT生成 ──
            report.status = ReportStage.GENERATING
            generated_sections: List[Tuple[str, str]] = []  # [(title, content_md)]
            previous_contents: List[str] = []

            total = len(outline.sections)
            for i, section in enumerate(outline.sections):
                idx = i + 1
                if progress_cb:
                    base = int((i / total) * 100)
                    progress_cb("generating", base, f"正在生成章节 {idx}/{total}: {section.title}")

                content = self.generate_section(
                    section=section,
                    outline=outline,
                    previous_sections=previous_contents,
                    section_index=idx,
                    progress_cb=lambda s, p, m: None,  # 内部进度
                )

                section.content = content
                section_md = f"## {section.title}\n\n{content}"
                generated_sections.append((section.title, content))
                previous_contents.append(section_md)

                logger.info(f"章节 {idx}/{total} 完成: {section.title}")

            # ── Phase 3: 整合 ──
            report.status = ReportStage.INTEGRATING
            if progress_cb:
                progress_cb("integrating", 0, "正在整合报告...")

            full_md = self.integrate_report(generated_sections, outline, progress_cb=progress_cb)
            report.markdown = full_md

            # 完成
            report.status = ReportStage.COMPLETED
            report.completed_at = datetime.now().isoformat()
            total_sec = (datetime.now() - start_time).total_seconds()

            self.report_logger.log_report_complete(total_sections=total, total_seconds=total_sec)

            # 写入文件
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(full_md)

            # 同时保存JSON元数据
            meta_path = output_path.replace(".md", ".json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

            if progress_cb:
                progress_cb("completed", 100, f"日报生成完成！输出: {output_path}")

            logger.info(f"✅ 日报生成完成: {output_path} ({total_sec:.1f}秒, {total}个章节)")
            return report

        except Exception as e:
            logger.error(f"日报生成失败: {e}")
            report.status = ReportStage.FAILED
            report.error = str(e)
            if self.report_logger:
                self.report_logger.log_error(str(e), report.status.value)
            raise

    # ── 辅助方法 ──

    @staticmethod
    def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
        """尝试从文本中解析JSON"""
        if not text:
            return None
        # 尝试直接解析
        text = text.strip()
        # 移除Markdown代码块包裹
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试提取JSON块
        for match in re.finditer(r'\{.*\}', text, re.DOTALL):
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and len(data) > 0:
                    return data
            except json.JSONDecodeError:
                continue
        return None


# ═══════════════════════════════════════════════════════════════
# CLI入口
# ═══════════════════════════════════════════════════════════════

def main():
    """CLI入口 — 生成ReACT日报"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Gaia ReACT日报生成器 (MF-07) — 三段式ReACT日报引擎"
    )
    parser.add_argument(
        "--context", "-c",
        default=f"Gaia军团日常运行日报 {datetime.now().strftime('%Y-%m-%d')}。关注重点: 服务SLA、雇员效率、资源瓶颈、产品进展。",
        help="日报上下文描述",
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"输出Markdown文件路径 (默认: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细日志输出",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("gaia.react_reporter").setLevel(logging.DEBUG)
    else:
        logging.getLogger("gaia.react_reporter").setLevel(logging.INFO)

    reporter = GaiaReactReporter()

    def progress_callback(stage: str, progress: int, message: str):
        bar_len = 20
        filled = int(bar_len * progress / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        stage_padded = stage.upper().ljust(12)
        print(f"\r[{stage_padded}] [{bar}] {progress:3d}% {message}", end="", flush=True)
        if progress == 100:
            print()

    print(f"\n{'=' * 60}")
    print(f"  Gaia ReACT日报生成器 (MF-07)")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  输出: {args.output}")
    print(f"{'=' * 60}\n")

    report = reporter.generate_daily_report(
        context=args.context,
        output_path=args.output,
        progress_cb=progress_callback,
    )

    print(f"\n{'=' * 60}")
    print(f"  ✅ 日报生成完成!")
    print(f"  报告ID: {report.report_id}")
    print(f"  章节数: {len(report.outline.sections) if report.outline else 0}")
    print(f"  文件: {args.output}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
