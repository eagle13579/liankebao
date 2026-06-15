"""
LLM Service — DeepSeek API 智能服务层

提供:
- get_llm_client() → 返回 DeepSeek HTTP 客户端
- generate_matching_reason(product, need) → 生成 AI 匹配理由
- generate_enriched_description(company_data) → 生成企业描述
- summarize_lead(lead_data) → 线索智能摘要

降级策略: LLM 不可用时返回默认文本，不阻塞业务流
"""

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "15"))  # 15 秒超时

# ============================================================
# 客户端
# ============================================================


def get_llm_client() -> httpx.Client:
    """返回 DeepSeek HTTP 同步客户端"""
    return httpx.Client(
        base_url=DEEPSEEK_BASE_URL,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=LLM_TIMEOUT,
    )


def get_llm_client_async() -> httpx.AsyncClient:
    """返回 DeepSeek HTTP 异步客户端"""
    return httpx.AsyncClient(
        base_url=DEEPSEEK_BASE_URL,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=LLM_TIMEOUT,
    )


# ============================================================
# 底层调用
# ============================================================


def _call_deepseek(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> str | None:
    """调用 DeepSeek Chat API，返回生成的文本内容

    异常降级: 网络错误 / 认证错误 / 超时等均返回 None
    """
    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY 未配置，跳过 LLM 调用")
        return None

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        with get_llm_client() as client:
            resp = client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(
                "llm_call_success",
                extra={
                    "model": DEEPSEEK_MODEL,
                    "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                    "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                },
            )
            return content.strip()
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM HTTP 错误: {e.response.status_code} - {e.response.text[:200]}")
    except httpx.TimeoutException:
        logger.error(f"LLM 请求超时 ({LLM_TIMEOUT}s)")
    except httpx.RequestError as e:
        logger.error(f"LLM 请求失败: {e}")
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error(f"LLM 响应解析失败: {e}")
    return None


# ============================================================
# 业务函数
# ============================================================


def generate_matching_reason(
    product: dict[str, Any],
    need: dict[str, Any],
) -> str:
    """生成 AI 产品-需求匹配理由

    参数:
        product: 产品数据字典（含 name, description, category, tags, price 等）
        need:    需求数据字典（含 title, description, category 等）

    返回:
        匹配理由字符串，降级时返回默认理由
    """
    product_info = json.dumps(
        {
            "name": product.get("name", ""),
            "description": product.get("description", ""),
            "category": product.get("category", ""),
            "tags": product.get("tags", ""),
            "price": product.get("price", 0),
        },
        ensure_ascii=False,
    )
    need_info = json.dumps(
        {
            "title": need.get("title", ""),
            "description": need.get("description", ""),
            "category": need.get("category", ""),
        },
        ensure_ascii=False,
    )

    messages = [
        {
            "role": "system",
            "content": "你是一个商业供需匹配专家。请分析以下产品与需求之间的匹配程度，"
            "用一句话（不超过80字）说明为什么该产品适合满足此需求。返回简洁的中文理由。",
        },
        {
            "role": "user",
            "content": f"需求: {need_info}\n产品: {product_info}\n请给出匹配理由:",
        },
    ]

    result = _call_deepseek(messages, temperature=0.3, max_tokens=128)
    if result:
        return result

    # 降级: 基于标签/分类生成简单理由
    fallback_parts = []
    product_name = product.get("name", "")
    need_title = need.get("title", "")
    if product_name and need_title:
        fallback_parts.append(f"「{product_name}」与「{need_title}」高度匹配")
    else:
        fallback_parts.append("基于供需特征匹配推荐")
    return "；".join(fallback_parts)


def generate_enriched_description(company_data: dict[str, Any]) -> str:
    """生成企业智能描述

    参数:
        company_data: 企业信息字典（含 name, industry, scale, business_scope 等）

    返回:
        企业描述文本，降级时返回原始简介或默认描述
    """
    raw_description = company_data.get("description", "") or company_data.get("introduction", "")

    messages = [
        {
            "role": "system",
            "content": "你是一个企业信息分析师。请根据提供的企业信息，生成一段简洁专业的企业描述（不超过150字），"
            "涵盖主营业务、行业定位和核心优势。返回中文。",
        },
        {
            "role": "user",
            "content": f"企业信息: {json.dumps(company_data, ensure_ascii=False)}",
        },
    ]

    result = _call_deepseek(messages, temperature=0.4, max_tokens=256)
    if result:
        return result

    # 降级: 返回原始描述
    return raw_description or f"{company_data.get('name', '该企业')} — 暂无详细描述"


def summarize_lead(lead_data: dict[str, Any]) -> str:
    """生成线索智能摘要

    参数:
        lead_data: 线索数据字典（含 name, company, phone, source, notes, stage 等）

    返回:
        智能摘要文本，降级时返回基本信息摘要
    """
    stage_labels = {
        "new_lead": "新线索",
        "contacted": "已联系",
        "negotiating": "洽谈中",
        "quotation": "报价中",
        "closed_won": "已成交",
        "closed_lost": "已流失",
    }
    stage_cn = stage_labels.get(lead_data.get("stage", ""), lead_data.get("stage", "未知"))

    messages = [
        {
            "role": "system",
            "content": "你是一个 CRM 销售助理。请根据线索信息，生成一段不超过100字的智能摘要，"
            "包含线索关键要素和当前阶段建议。返回中文。",
        },
        {
            "role": "user",
            "content": f"线索信息: {json.dumps(lead_data, ensure_ascii=False)}",
        },
    ]

    result = _call_deepseek(messages, temperature=0.3, max_tokens=192)
    if result:
        return result

    # 降级: 基于字段拼接摘要
    name = lead_data.get("name", "未知联系人")
    company = lead_data.get("company", "")
    phone = lead_data.get("phone", "")
    source = lead_data.get("source", "手动录入")
    notes = lead_data.get("notes", "")

    parts = [f"{name}（{company or '无公司'}）| 阶段: {stage_cn} | 来源: {source}"]
    if phone:
        parts.append(f"电话: {phone}")
    if notes:
        parts.append(f"备注: {notes[:50]}")
    return " | ".join(parts)
