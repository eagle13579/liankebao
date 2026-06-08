#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gaia_digest_pipeline.py — 外部知识消化管道 (MF-01)

核心功能:
  1. digest_text(text)    → 调用LLM提取实体类型+关系类型，输出结构化JSON ontology
  2. build_knowledge_graph(ontology, text) → 从文本中识别具体实体+关系，注入到五池
  3. integrate_into_cortex() → 返回hook函数，可插入gaia_cortex.py L1层

设计继承:
  - MiroFish ontology_generator.py: 10实体类型(8具体+2兜底Person/Organization)
  - 注入五池: 实体→模型池, 关系→决策验证池
  - 增量更新: 仅新增不覆盖

用法:
  python gaia_digest_pipeline.py --digest "文本字符串"
  python gaia_digest_pipeline.py --file 文档路径.md
  python gaia_digest_pipeline.py --hook   # 测试集成模式
"""

import os
import sys
import json
import re
import uuid
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import urllib.request
import urllib.error

# ── 路径 ──────────────────────────────────────────────────────
HERMES_HOME = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
SCRIPTS_DIR = os.path.join(HERMES_HOME, "scripts")
POOLS_DIR = os.path.join(HERMES_HOME, "五池")
MODEL_POOL_DIR = os.path.join(POOLS_DIR, "模型池")
DECISION_POOL_DIR = os.path.join(POOLS_DIR, "决策验证池")
CORTEX_PATH = os.path.join(SCRIPTS_DIR, "gaia_cortex.py")

# ── 日志 ──────────────────────────────────────────────────────
logger = logging.getLogger("gaia_digest_pipeline")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)

# ════════════════════════════════════════════════════════════════
#  1. LLM 客户端 — 复用 MiroFish 模式 (urllib → DeepSeek / 兼容)
# ════════════════════════════════════════════════════════════════

class _DigestLLMClient:
    """轻量 LLM 客户端，复用 gaia 生态已有的 API 调用模式。
    
    支持两种模式:
      A. 直接API调用 (urllib → DeepSeek / OpenAI 兼容接口)
      B. 委托模式 (subprocess → Hermes delegate_task)
    默认使用模式A，性能更高；模式B作为fallback。
    """

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.api_url = os.environ.get(
            "LLM_API_URL",
            "https://api.deepseek.com/chat/completions",
        )
        self.model = os.environ.get("LLM_MODEL", "deepseek-chat")
        self._use_direct = bool(self.api_key)

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """调用LLM并解析JSON响应。先尝试直接API，失败则fallback到委托模式。"""
        if self._use_direct:
            try:
                return self._call_direct(system_prompt, user_prompt, temperature, max_tokens)
            except Exception as e:
                logger.warning(f"直接API调用失败，尝试委托模式: {e}")
        return self._call_delegate(system_prompt, user_prompt, temperature, max_tokens)

    # ── 模式A: 直接API ──────────────────────────────────────────

    def _call_direct(self, system_prompt, user_prompt, temperature, max_tokens) -> Dict[str, Any]:
        """通过 urllib 直接调用 LLM API (与 MiroFish LLMClient 一致)"""
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")

        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]

        # 清理 JSON 包裹
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        return json.loads(content)

    # ── 模式B: 委托模式 ────────────────────────────────────────

    def _call_delegate(self, system_prompt, user_prompt, temperature, max_tokens) -> Dict[str, Any]:
        """通过 subprocess → delegate_task 调用 LLM (Hermes Agent 模式)"""
        import subprocess
        # 构造一个临时的 agent 指令脚本，委托给 hermes
        script_content = (
            f'你是一个JSON生成器。请严格按照以下system prompt分析文本，只输出JSON。\n\n'
            f'System: {system_prompt}\n\n'
            f'User: {user_prompt[:3000]}'
        )
        # 用 delegate_task 的 shell 调用模式
        result = subprocess.run(
            [sys.executable, "-c", json.dumps({
                "task": "llm_json",
                "system": system_prompt,
                "user": user_prompt[:2000],
            })],
            capture_output=True, text=True, timeout=120,
        )
        out = result.stdout.strip()
        if not out:
            raise RuntimeError(f"委托模式返回空: {result.stderr}")
        # 尝试从输出中提取 JSON
        json_match = re.search(r'\{.*\}', out, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise RuntimeError(f"委托模式无法解析JSON: {out[:200]}")


# ════════════════════════════════════════════════════════════════
#  2. 本体 (Ontology) 提取 — 消化文本，生成结构化类型定义
# ════════════════════════════════════════════════════════════════

ONTOLOGY_SYSTEM_PROMPT = """你是一个专业的知识图谱本体设计专家。你的任务是分析给定的文本内容，设计适合**知识消化与心智模型萃取**的实体类型和关系类型。

**你必须输出有效的JSON格式数据，不要输出任何其他内容。**

## 核心原则

实体必须是文本中真实出现的主体，可以是：
- 个人（专家、创始人、学者、从业者等具体人物）
- 组织（公司、机构、团队、平台等）
- 概念资源（方法、框架、理论、工具、产品等抽象但重要的知识实体）
- 事件与项目（战役、里程碑、项目、活动等）

## 输出格式

```json
{
    "entity_types": [
        {
            "name": "实体类型名称（英文PascalCase）",
            "description": "简短描述（中文，不超过100字）",
            "attributes": [
                {"name": "属性名（snake_case）", "type": "text", "description": "描述"}
            ],
            "examples": ["示例1", "示例2"]
        }
    ],
    "edge_types": [
        {
            "name": "关系类型名称（英文UPPER_SNAKE_CASE）",
            "description": "简短描述（中文，不超过100字）",
            "source_targets": [
                {"source": "源实体类型", "target": "目标实体类型"}
            ]
        }
    ],
    "analysis_summary": "对文本内容的本体分析摘要（中文）"
}
```

## 实体类型设计规则

**数量：必须正好10个实体类型**

**层次结构：**
A. 兜底类型（放在列表最后2个）：
   - Person: 任何自然人个体的兜底类型
   - Organization: 任何组织机构的兜底类型

B. 具体类型（8个，根据文本内容设计）：
   - 针对文本中出现的主要角色设计更具体的类型
   - 例如：Concept(概念/方法), Product(产品), Event(事件), Tool(工具), Role(角色), Standard(标准/规范), Method(方法论), Project(项目)

**属性注意事项：** 属性名不能使用 name、uuid、id、created_at、summary（系统保留字）

## 关系类型设计

- 数量：6-10个
- 关系应该反映知识实体间的真实联系
- 例如：BELONGS_TO(属于/隶属), CREATED_BY(创建者), USES(使用), RELATES_TO(关联), LEADS_TO(导致/引发), PART_OF(组成部分), INSPIRED_BY(启发自), APPLIES_TO(适用于)"""


def digest_text(text: str, llm_client: Optional[_DigestLLMClient] = None) -> Dict[str, Any]:
    """核心函数1: 消化文本 → 提取实体类型+关系类型 ontology
    
    Args:
        text: 待消化的文本内容
        llm_client: LLM客户端（可选，自动创建默认）
    
    Returns:
        ontology dict: {entity_types: [...], edge_types: [...], analysis_summary: str}
    """
    client = llm_client or _DigestLLMClient()

    # 文本截断保护（最多5万字）
    max_len = 50000
    if len(text) > max_len:
        text = text[:max_len] + f"\n\n...(原文共{len(text)}字，已截取前{max_len}字)"

    user_prompt = f"""请分析以下文本，提取适合知识消化与心智模型萃取的本体定义。

## 文本内容

{text}

## 要求

1. 必须正好输出10个实体类型
2. 最后2个必须是兜底类型：Person（个人兜底）和 Organization（组织兜底）
3. 前8个是根据文本内容设计的具体类型
4. 所有实体类型必须有明确的描述和属性定义
5. 关系类型需覆盖实体之间的主要关联"""

    logger.info("调用LLM进行本体提取...")
    ontology = client.chat_json(ONTOLOGY_SYSTEM_PROMPT, user_prompt)

    # 后处理：确保必要字段，强制兜底类型
    ontology = _ensure_ontology_structure(ontology)

    # 保存本体到文件（增量，不覆盖）
    _save_ontology_snapshot(ontology, text)

    logger.info(f"本体提取完成: {len(ontology.get('entity_types', []))}实体类型, "
                f"{len(ontology.get('edge_types', []))}关系类型")
    return ontology


def _ensure_ontology_structure(ontology: Dict[str, Any]) -> Dict[str, Any]:
    """确保 ontology 包含必要字段，强制兜底类型"""
    ontology.setdefault("entity_types", [])
    ontology.setdefault("edge_types", [])
    ontology.setdefault("analysis_summary", "")

    # 验证实体类型完整性
    for et in ontology["entity_types"]:
        et.setdefault("attributes", [])
        et.setdefault("examples", [])
        if len(et.get("description", "")) > 100:
            et["description"] = et["description"][:97] + "..."

    # 验证关系类型完整性
    for et in ontology["edge_types"]:
        et.setdefault("source_targets", [])
        if len(et.get("description", "")) > 100:
            et["description"] = et["description"][:97] + "..."

    # 兜底类型定义
    person_fallback = {
        "name": "Person",
        "description": "任何自然人个体的兜底类型。当一个人不属于其他更具体的人物类型时归入此类。",
        "attributes": [
            {"name": "full_name", "type": "text", "description": "人物全名"},
            {"name": "role", "type": "text", "description": "角色或职位"},
        ],
        "examples": ["普通个体", "匿名网友"],
    }
    org_fallback = {
        "name": "Organization",
        "description": "任何组织机构的兜底类型。当一个组织不属于其他更具体的组织类型时归入此类。",
        "attributes": [
            {"name": "org_name", "type": "text", "description": "组织名称"},
            {"name": "org_type", "type": "text", "description": "组织类型"},
        ],
        "examples": ["小型企业", "社区团体"],
    }

    entity_names = {e["name"] for e in ontology["entity_types"]}
    has_person = "Person" in entity_names
    has_org = "Organization" in entity_names

    # 如果已满10个但缺少兜底，替换末尾
    if len(ontology["entity_types"]) >= 10:
        if not has_person:
            ontology["entity_types"][-1] = person_fallback
        if not has_org:
            ontology["entity_types"][-2] = org_fallback
    else:
        if not has_person:
            ontology["entity_types"].append(person_fallback)
        if not has_org:
            ontology["entity_types"].append(org_fallback)

    # 最终数量限制
    MAX_ENTITY = 10
    MAX_EDGE = 10
    if len(ontology["entity_types"]) > MAX_ENTITY:
        ontology["entity_types"] = ontology["entity_types"][:MAX_ENTITY]
    if len(ontology["edge_types"]) > MAX_EDGE:
        ontology["edge_types"] = ontology["edge_types"][:MAX_EDGE]

    return ontology


def _save_ontology_snapshot(ontology: Dict[str, Any], source_text: str) -> str:
    """保存 ontology 快照到 模型池/_ontology/ 目录（增量不覆盖）"""
    snapshot_dir = os.path.join(MODEL_POOL_DIR, "_ontology")
    os.makedirs(snapshot_dir, exist_ok=True)

    # 用文本hash作为文件名标识，避免重复
    text_hash = hashlib.md5(source_text.encode("utf-8")).hexdigest()[:12]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"digest_{ts}_{text_hash}.json"
    filepath = os.path.join(snapshot_dir, filename)

    # 检查是否已有相同hash的快照
    for existing in os.listdir(snapshot_dir):
        if text_hash in existing and existing.endswith(".json"):
            logger.info(f"本体快照已存在，跳过写入: {existing}")
            return os.path.join(snapshot_dir, existing)

    snapshot = {
        "meta": {
            "created_at": datetime.now().isoformat(),
            "source_length": len(source_text),
            "text_hash": text_hash,
        },
        "ontology": ontology,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"本体快照已保存: {filepath}")
    return filepath


# ════════════════════════════════════════════════════════════════
#  3. 知识图谱构建 — 从文本识别具体实体+关系，注入五池
# ════════════════════════════════════════════════════════════════

GRAPH_EXTRACTION_PROMPT = """你是一个知识图谱抽取专家。根据给定的本体定义(ontology)和文本，抽取具体的实体和关系。

**你必须输出有效的JSON格式数据，不要输出任何其他内容。**

## 输出格式

```json
{
    "entities": [
        {
            "name": "实体名称",
            "type": "实体类型（需匹配ontology中的entity_types）",
            "attributes": {"属性名": "属性值"},
            "description": "实体描述（中文）",
            "source_text": "原文证据（截取关键句子）"
        }
    ],
    "relations": [
        {
            "source": "源实体名称",
            "target": "目标实体名称",
            "type": "关系类型（需匹配ontology中的edge_types）",
            "description": "关系描述",
            "source_text": "原文证据"
        }
    ]
}
```

## 抽取规则

1. 实体必须是文本中明确出现或可合理推断的主体
2. 每个实体必须有清晰的原文本证据
3. 关系必须连接已抽取的实体
4. 优先抽取高价值实体（核心人物、关键组织、重要概念）
5. 如果文本中没有匹配的实体，可以留空列表
6. 属性值应从文本中提取，不要虚构"""


def build_knowledge_graph(
    ontology: Dict[str, Any],
    text: str,
    llm_client: Optional[_DigestLLMClient] = None,
) -> Dict[str, Any]:
    """核心函数2: 根据ontology从文本中识别实体+关系，注入五池
    
    Args:
        ontology: digest_text() 返回的 ontology 定义
        text: 待分析的文本
        llm_client: LLM客户端（可选）
    
    Returns:
        result: {entities_found, relations_found, injected_to_pools}
    """
    client = llm_client or _DigestLLMClient()

    # 构建提取prompt — 包含ontology定义
    ontology_json = json.dumps(ontology, ensure_ascii=False, indent=2)
    max_text_len = 30000
    if len(text) > max_text_len:
        text = text[:max_text_len] + f"\n\n...(截断，原文共{len(text)}字)"

    user_prompt = f"""## 本体定义（Ontology）

{ontology_json}

## 待分析文本

{text}

请根据以上ontology从文本中抽取具体实体和关系。"""

    logger.info("调用LLM提取实体和关系...")
    graph_data = client.chat_json(GRAPH_EXTRACTION_PROMPT, user_prompt)

    entities = graph_data.get("entities", [])
    relations = graph_data.get("relations", [])

    logger.info(f"LLM提取完成: {len(entities)}个实体, {len(relations)}条关系")

    # ── 注入五池 ────────────────────────────────────────────────
    injection_result = {
        "entities_found": len(entities),
        "relations_found": len(relations),
        "entities_injected": 0,
        "relations_injected": 0,
        "entities_skipped_dup": 0,
        "relations_skipped_dup": 0,
        "entity_files": [],
        "relation_files": [],
    }

    # 注入实体 → 模型池（每个实体一个原子文件）
    for entity in entities:
        name = entity.get("name", "").strip()
        etype = entity.get("type", "Person")
        if not name:
            continue

        # 生成原子文件名
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)[:60]
        entity_filename = f"extern_{safe_name}_{etype}.md"
        entity_path = os.path.join(MODEL_POOL_DIR, entity_filename)

        # 增量更新：检查是否已存在
        if os.path.isfile(entity_path):
            injection_result["entities_skipped_dup"] += 1
            continue

        # 构建markdown原子内容
        desc = entity.get("description", "")
        attrs = entity.get("attributes", {})
        source_text = entity.get("source_text", "")
        attr_lines = "\n".join(
            f"- **{k}**: {v}" for k, v in attrs.items() if v
        )

        content = (
            f"# 外部知识实体: {name}\n\n"
            f"**类型**: {etype}\n\n"
            f"**描述**: {desc}\n\n"
            f"## 属性\n{attr_lines if attr_lines else '（无额外属性）'}\n\n"
            f"## 来源\n> {source_text}\n\n"
            f"---\n"
            f"*由 gaia_digest_pipeline.py 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} 注入*\n"
            f"*实体类型定义: {etype}*\n"
        )
        with open(entity_path, "w", encoding="utf-8") as f:
            f.write(content)
        injection_result["entities_injected"] += 1
        injection_result["entity_files"].append(entity_path)
        logger.info(f"  实体注入 → {entity_path}")

    # 注入关系 → 决策验证池（每个关系一条记录）
    for rel in relations:
        src = rel.get("source", "").strip()
        tgt = rel.get("target", "").strip()
        rtype = rel.get("type", "").strip()
        if not src or not tgt or not rtype:
            continue

        # 生成关系记录文件名
        rel_desc = rel.get("description", "")[:40]
        safe_src = re.sub(r'[\\/:*?"<>|]', "_", src)[:20]
        safe_tgt = re.sub(r'[\\/:*?"<>|]', "_", tgt)[:20]
        rel_filename = f"rel_{safe_src}_{rtype}_{safe_tgt}.md"
        rel_path = os.path.join(DECISION_POOL_DIR, rel_filename)

        # 增量更新
        if os.path.isfile(rel_path):
            injection_result["relations_skipped_dup"] += 1
            continue

        rel_desc_full = rel.get("description", "")
        source_evidence = rel.get("source_text", "")

        content = (
            f"# 知识关系: {src} → {tgt}\n\n"
            f"**关系类型**: {rtype}\n\n"
            f"**描述**: {rel_desc_full}\n\n"
            f"**源实体**: {src}\n"
            f"**目标实体**: {tgt}\n\n"
            f"## 原文证据\n> {source_evidence}\n\n"
            f"## 决策验证\n"
            f"- [ ] 验证此关系是否准确\n"
            f"- [ ] 关系强度评估（1-5）:\n"
            f"- [ ] 是否支持已有决策:\n\n"
            f"---\n"
            f"*由 gaia_digest_pipeline.py 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} 注入*\n"
            f"*待验证*"
        )
        with open(rel_path, "w", encoding="utf-8") as f:
            f.write(content)
        injection_result["relations_injected"] += 1
        injection_result["relation_files"].append(rel_path)
        logger.info(f"  关系注入 → {rel_path}")

    # 写入汇总报告
    _write_injection_report(injection_result, ontology)

    logger.info(f"注入完成: {injection_result['entities_injected']}实体新增, "
                f"{injection_result['entities_skipped_dup']}跳过(重复), "
                f"{injection_result['relations_injected']}关系新增, "
                f"{injection_result['relations_skipped_dup']}跳过(重复)")
    return injection_result


def _write_injection_report(result: Dict[str, Any], ontology: Dict[str, Any]) -> str:
    """写入注入报告到决策验证池"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(DECISION_POOL_DIR, f"digest_report_{ts}.md")

    entity_types_summary = "\n".join(
        f"  - {e['name']}: {e.get('description', '')[:50]}"
        for e in ontology.get("entity_types", [])
    )
    edge_types_summary = "\n".join(
        f"  - {e['name']}: {e.get('description', '')[:50]}"
        for e in ontology.get("edge_types", [])
    )

    content = (
        f"# 外部知识消化报告\n\n"
        f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"## 本体定义\n\n"
        f"### 实体类型 ({len(ontology.get('entity_types', []))}个)\n{entity_types_summary}\n\n"
        f"### 关系类型 ({len(ontology.get('edge_types', []))}个)\n{edge_types_summary}\n\n"
        f"## 抽取结果\n\n"
        f"- **实体**: 发现{result['entities_found']}个, "
        f"新增{result['entities_injected']}个, "
        f"跳过重复{result['entities_skipped_dup']}个\n"
        f"- **关系**: 发现{result['relations_found']}条, "
        f"新增{result['relations_injected']}条, "
        f"跳过重复{result['relations_skipped_dup']}条\n\n"
        f"## 注入路径\n"
        f"- 实体 → 模型池: {MODEL_POOL_DIR}\n"
        f"- 关系 → 决策验证池: {DECISION_POOL_DIR}\n\n"
        f"## 待验证\n"
        f"以上注入的知识需要经过决策验证池的校验确认。\n"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"注入报告已写入: {report_path}")
    return report_path


# ════════════════════════════════════════════════════════════════
#  4. 集成到 Cortex — L1层 Hook 点
# ════════════════════════════════════════════════════════════════

def integrate_into_cortex() -> dict:
    """核心函数3: 返回集成hook，可插入 gaia_cortex.py L1 分析层
    
    返回的hook字典包含:
      - hook_name: 钩子标识
      - layer: 挂载层 ('L1')
      - priority: 执行优先级
      - description: 描述
      - run: 可调用函数，接收l0_output参数，返回分析结果
    
    gaia_cortex.py L1层调用方式:
    
        from gaia_digest_pipeline import integrate_into_cortex
        digest_hook = integrate_into_cortex()
        digest_result = digest_hook['run'](l0)
    
    或者在 run_full_cycle() 中 L1 之后注入:
    
        if digest_hook['enabled']:
            digest_hook['run'](l0)
    """
    hook = {
        "hook_name": "gaia_digest_pipeline",
        "layer": "L1",
        "priority": 3,  # 在标准缺口分析之后执行
        "enabled": True,
        "description": "外部知识消化管道: 扫描新文件→提取Ontology→构建知识图谱→注入五池",
        "last_run": None,
        "total_digested": 0,
        "total_entities": 0,
        "total_relations": 0,
    }

    def _run(l0_output=None):
        """实际的hook函数 — 扫描外部文件并消化
        
        Args:
            l0_output: L0Output 对象（可选，用于上下文感知）
        
        Returns:
            消化结果统计
        """
        logger.info("=" * 50)
        logger.info("  盖娅消化管道 L1 Hook 启动")
        logger.info("=" * 50)

        # 扫描 现象池 中的新文件作为待消化文本来源
        phenomenon_dir = os.path.join(POOLS_DIR, "现象池")
        digest_dir = os.path.join(POOLS_DIR, "现象池", "_待消化")
        os.makedirs(digest_dir, exist_ok=True)

        candidates = []
        if os.path.isdir(phenomenon_dir):
            for fname in os.listdir(phenomenon_dir):
                fpath = os.path.join(phenomenon_dir, fname)
                if fname.endswith(".md") and os.path.isfile(fpath):
                    # 跳过已处理文件（以 _digested 为标记）
                    if fname.startswith("_digested"):
                        continue
                    candidates.append(fpath)

        logger.info(f"发现 {len(candidates)} 个待消化文件")

        if not candidates:
            return {
                "status": "idle",
                "message": "没有新的待消化文件",
                "digested": 0,
                "entities_added": 0,
                "relations_added": 0,
            }

        total_digested = 0
        total_entities = 0
        total_relations = 0

        for fpath in candidates[:5]:  # 每次最多处理5个
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()

                basename = os.path.basename(fpath)
                logger.info(f"消化文件: {basename} ({len(text)}字)")

                # Step 1: 提取 ontology
                ontology = digest_text(text)

                # Step 2: 构建知识图谱并注入
                result = build_knowledge_graph(ontology, text)

                # Step 3: 标记为已消化
                digested_path = os.path.join(
                    digest_dir,
                    f"_digested_{basename}",
                )
                # 写入消化摘要
                summary = {
                    "source_file": fpath,
                    "digested_at": datetime.now().isoformat(),
                    "entities": result["entities_found"],
                    "relations": result["relations_found"],
                    "entities_injected": result["entities_injected"],
                    "relations_injected": result["relations_injected"],
                    "ontology_types": len(ontology.get("entity_types", [])),
                    "edge_types": len(ontology.get("edge_types", [])),
                }
                with open(digested_path, "w", encoding="utf-8") as f:
                    json.dump(summary, f, ensure_ascii=False, indent=2)

                total_digested += 1
                total_entities += result["entities_injected"]
                total_relations += result["relations_injected"]

            except Exception as e:
                logger.error(f"消化文件失败 {fpath}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # 更新hook状态
        hook["last_run"] = datetime.now().isoformat()
        hook["total_digested"] += total_digested
        hook["total_entities"] += total_entities
        hook["total_relations"] += total_relations

        result = {
            "status": "ok",
            "digested": total_digested,
            "entities_added": total_entities,
            "relations_added": total_relations,
            "total_digested_ever": hook["total_digested"],
            "total_entities_ever": hook["total_entities"],
            "total_relations_ever": hook["total_relations"],
        }
        logger.info(f"消化管道完成: {result}")
        return result

    hook["run"] = _run
    return hook


# ════════════════════════════════════════════════════════════════
#  5. 自检与验证
# ════════════════════════════════════════════════════════════════

def self_check() -> List[str]:
    """运行自检，返回所有问题列表"""
    issues = []

    # 检查路径
    for name, path in [
        ("五池根目录", POOLS_DIR),
        ("模型池", MODEL_POOL_DIR),
        ("决策验证池", DECISION_POOL_DIR),
    ]:
        if not os.path.isdir(path):
            issues.append(f"路径不存在: {name} = {path}")

    # 检查gaia_cortex.py是否存在
    if not os.path.isfile(CORTEX_PATH):
        issues.append(f"gaia_cortex.py 未找到: {CORTEX_PATH}")
    else:
        # 检查L1层函数是否存在
        with open(CORTEX_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        if "def layer1_analyze" not in content:
            issues.append("gaia_cortex.py 中未找到 layer1_analyze 函数")

    # 检查LLM配置
    if not os.environ.get("DEEPSEEK_API_KEY"):
        issues.append("DEEPSEEK_API_KEY 环境变量未设置，LLM调用将使用委托模式")

    # 检查可写权限
    for dir_path in [POOLS_DIR, MODEL_POOL_DIR, DECISION_POOL_DIR]:
        if os.path.isdir(dir_path):
            test_file = os.path.join(dir_path, ".digest_write_test")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
            except (OSError, PermissionError):
                issues.append(f"目录不可写: {dir_path}")

    if not issues:
        logger.info("自检通过 ✓")
    else:
        logger.warning(f"自检发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            logger.warning(f"  {i}. {issue}")

    return issues


# ════════════════════════════════════════════════════════════════
#  6. CLI入口
# ════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="盖娅外部知识消化管道 (MF-01)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python gaia_digest_pipeline.py --digest \"量子计算是...\"\n"
            "  python gaia_digest_pipeline.py --file 文档.md\n"
            "  python gaia_digest_pipeline.py --hook\n"
            "  python gaia_digest_pipeline.py --status\n"
        ),
    )
    parser.add_argument(
        "--digest", type=str, default=None,
        help="直接传入文本字符串进行消化",
    )
    parser.add_argument(
        "--file", type=str, default=None,
        help="从文件读取文本进行消化",
    )
    parser.add_argument(
        "--hook", action="store_true",
        help="测试集成模式：运行一次L1 hook扫描",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="显示消化管道状态",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="运行自检",
    )

    args = parser.parse_args()

    if args.check:
        issues = self_check()
        sys.exit(0 if not issues else 1)

    if args.status:
        # 显示状态：统计已注入的实体和关系
        entity_count = 0
        relation_count = 0
        if os.path.isdir(MODEL_POOL_DIR):
            for f in os.listdir(MODEL_POOL_DIR):
                if f.startswith("extern_") and f.endswith(".md"):
                    entity_count += 1
        if os.path.isdir(DECISION_POOL_DIR):
            for f in os.listdir(DECISION_POOL_DIR):
                if f.startswith("rel_") and f.endswith(".md"):
                    relation_count += 1

        print("=" * 50)
        print("  盖娅消化管道 · 状态")
        print("=" * 50)
        print(f"  模型池路径: {MODEL_POOL_DIR}")
        print(f"  决策验证池路径: {DECISION_POOL_DIR}")
        print(f"  已注入外部实体: {entity_count} 个")
        print(f"  已注入知识关系: {relation_count} 条")
        print(f"  LLM模式: {'直接API' if os.environ.get('DEEPSEEK_API_KEY') else '委托模式'}")
        print(f"  自检: {'通过' if not self_check() else '有警告'}")
        print("=" * 50)
        return

    if args.hook:
        hook = integrate_into_cortex()
        logger.info("L1 Hook 测试运行...")
        result = hook["run"]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 获取待消化文本
    text = None
    source_desc = ""
    if args.file:
        filepath = args.file
        if not os.path.isfile(filepath):
            print(f"错误: 文件不存在 {filepath}")
            sys.exit(1)
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        source_desc = f"文件: {filepath}"
    elif args.digest:
        text = args.digest
        source_desc = "命令行输入"

    if not text:
        parser.print_help()
        sys.exit(1)

    print(f"开始消化: {source_desc} ({len(text)}字)")
    print("=" * 50)

    # 运行完整消化流程
    try:
        # Step 1: 提取本体
        ontology = digest_text(text)
        print(f"\n✅ 本体提取完成:")
        for et in ontology.get("entity_types", []):
            print(f"  - {et['name']}: {et.get('description', '')[:60]}")
        for et in ontology.get("edge_types", []):
            print(f"  - {et['name']}: {et.get('description', '')[:60]}")

        # Step 2: 构建知识图谱
        result = build_knowledge_graph(ontology, text)
        print(f"\n✅ 知识图谱构建完成:")
        print(f"  实体: 发现{result['entities_found']}个 → "
              f"新增{result['entities_injected']}个 (跳过{result['entities_skipped_dup']}个重复)")
        print(f"  关系: 发现{result['relations_found']}条 → "
              f"新增{result['relations_injected']}条 (跳过{result['relations_skipped_dup']}条重复)")

        print(f"\n✅ 消化完成")
    except Exception as e:
        print(f"\n❌ 消化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
