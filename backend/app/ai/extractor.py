import json
import os
import re
from typing import Optional

import pdfplumber

from app.config import settings


class AIExtractor:
    """AI 提取器 - PDF 文本提取、NLP 字段提取、DeepSeek 摘要与排版"""

    # 中文正则模式
    PHONE_PATTERN = re.compile(r'(?:\+86[-\s]?)?1[3-9]\d{9}')
    EMAIL_PATTERN = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
    WECHAT_PATTERN = re.compile(r'(?:微信|wechat|wx|VX)[：:\s]*([a-zA-Z0-9_]{4,})', re.IGNORECASE)
    TITLE_PATTERN = re.compile(r'(?:职位|职务|title|position)[：:\s]*(.{2,20})', re.IGNORECASE)
    COMPANY_PATTERN = re.compile(r'(?:公司|企业|单位|company|firm)[：:\s]*(.{2,30})', re.IGNORECASE)
    NAME_PATTERN = re.compile(r'(?:姓名|名字|name|称呼)[：:\s]*([\u4e00-\u9fa5]{2,4})', re.IGNORECASE)

    @staticmethod
    def extract_text_from_pdf(pdf_path: str) -> str:
        """从 PDF 文件中提取文本

        Args:
            pdf_path: PDF 文件路径

        Returns:
            提取出的纯文本内容
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text.strip())

        full_text = "\n".join(text_parts)
        if not full_text.strip():
            raise ValueError("未能从 PDF 中提取出文本，可能是扫描件，请使用 OCR 功能")

        return full_text

    @staticmethod
    def extract_fields_from_text(text: str) -> dict:
        """从文本中提取结构化字段（中文 NLP + 正则）

        Args:
            text: 原始文本内容

        Returns:
            {
                "name": str | None,
                "phone": str | None,
                "email": str | None,
                "wechat": str | None,
                "title": str | None,
                "company": str | None,
                "raw_text": str
            }
        """
        result = {
            "name": None,
            "phone": None,
            "email": None,
            "wechat": None,
            "title": None,
            "company": None,
            "raw_text": text.strip(),
        }

        # 手机号
        phones = AIExtractor.PHONE_PATTERN.findall(text)
        if phones:
            result["phone"] = phones[0]

        # 邮箱
        emails = AIExtractor.EMAIL_PATTERN.findall(text)
        if emails:
            result["email"] = emails[0]

        # 微信
        wechat_match = AIExtractor.WECHAT_PATTERN.search(text)
        if wechat_match:
            result["wechat"] = wechat_match.group(1)

        # 职位
        title_match = AIExtractor.TITLE_PATTERN.search(text)
        if title_match:
            result["title"] = title_match.group(1)

        # 公司
        company_match = AIExtractor.COMPANY_PATTERN.search(text)
        if company_match:
            result["company"] = company_match.group(1)

        # 姓名
        name_match = AIExtractor.NAME_PATTERN.search(text)
        if name_match:
            result["name"] = name_match.group(1)

        # 通用中文姓名启发式：在文本开头附近找2-4个中文字符
        if result["name"] is None:
            lines = text.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 跳过明显不是名字的行
                if re.search(r'(公司|企业|电话|手机|邮箱|地址|职位|微信|传真|网址|www\.|@)', line):
                    continue
                # 匹配2-4个中文字符
                chinese_names = re.findall(r'^[\u4e00-\u9fa5]{2,4}$', line)
                if chinese_names:
                    result["name"] = chinese_names[0]
                    break

        return result

    @staticmethod
    async def generate_summary(
        text: str,
        api_key: Optional[str] = None,
    ) -> str:
        """调用 DeepSeek API 生成摘要

        Args:
            text: 需要摘要的文本
            api_key: DeepSeek API Key（默认使用配置中的 key）

        Returns:
            生成的摘要文本
        """
        api_key = api_key or settings.DEEPSEEK_API_KEY
        if not api_key:
            return "【摘要生成需要配置 DEEPSEEK_API_KEY】"

        import httpx

        prompt = f"""请为以下名片信息生成一段简洁的中文摘要（50字以内），突出个人身份和业务特点：

{text[:1000]}

摘要："""

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    settings.DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": "你是一个名片信息摘要助手。请用简洁的语言提炼名片信息的核心内容。"},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 200,
                        "temperature": 0.3,
                    },
                )
                result = resp.json()
                return result["choices"][0]["message"]["content"].strip()
            except Exception as e:
                return f"【摘要生成失败: {str(e)}】"

    @staticmethod
    async def auto_layout(
        fields: dict,
        api_key: Optional[str] = None,
    ) -> list[dict]:
        """调用 DeepSeek API 智能排版，将字段分配到翻页图册的各页

        Args:
            fields: 提取的结构化字段
            api_key: DeepSeek API Key

        Returns:
            页面列表，每页含 content_type / content / sort_order
        """
        api_key = api_key or settings.DEEPSEEK_API_KEY
        if not api_key:
            # 默认布局
            return AIExtractor._default_layout(fields)

        import httpx

        prompt = f"""请根据以下名片信息，设计一个4页翻页图册的排版方案。

名片信息：
{json.dumps(fields, ensure_ascii=False, indent=2)}

要求：
- 第1页：封面（个人名称 + 标题）
- 第2页：联系方式（手机/邮箱/微信）
- 第3页：企业信息（公司 + 职位 + 简介）
- 第4页：二维码/其他

请以 JSON 数组返回，每项格式：{{"sort_order": int, "content_type": "cover|text|image", "content": "页面内容"}}

JSON："""

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    settings.DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": "你是一个名片排版助手，返回严格的 JSON 数组。"},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 500,
                        "temperature": 0.2,
                    },
                )
                result = resp.json()
                content = result["choices"][0]["message"]["content"].strip()
                # 尝试提取 JSON
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    pages = json.loads(json_match.group(0))
                    return pages
            except Exception:
                pass

        return AIExtractor._default_layout(fields)

    @staticmethod
    async def rag_match(
        user_query: str,
        user_tags: list[str],
        api_key: Optional[str] = None,
    ) -> dict:
        """DeepSeek RAG 匹配增强 — 用大模型做高级语义理解

        对用户的查询文本和标签做深度语义分析，
        返回结构化的匹配意图和关键词。

        Args:
            user_query: 用户输入的查询文本（如"找Python全栈开发者"）
            user_tags: 用户已有的标签列表
            api_key: DeepSeek API Key（默认使用配置中的 key）

        Returns:
            {
                "matched": bool,           # 是否匹配
                "intent": str,             # 匹配意图分析
                "suggested_tags": list,    # 建议补充的标签
                "confidence": float,       # 置信度 [0, 1]
                "fallback": bool,          # 是否回退到 TF-IDF
            }

        注意：
            - 有 API key 时用 DeepSeek
            - 无 API key 时回退到 TF-IDF 语义分析
        """
        api_key = api_key or settings.DEEPSEEK_API_KEY

        # 无 API key：回退到 TF-IDF 分析
        if not api_key:
            from app.ai.vector_search import VectorSearchEngine

            # 用 TF-IDF 做语义匹配度分析
            doc = " ".join(user_tags) if user_tags else ""
            if doc.strip() and user_query.strip():
                semantic_sim = VectorSearchEngine.compute_semantic_similarity(
                    tags_a=user_tags,
                    tags_b=[user_query],
                )
                return {
                    "matched": semantic_sim > 0.3,
                    "intent": f"TF-IDF语义匹配度: {semantic_sim:.2f}",
                    "suggested_tags": [],
                    "confidence": round(semantic_sim, 4),
                    "fallback": True,
                }

            return {
                "matched": False,
                "intent": "无法分析（缺少标签或查询文本）",
                "suggested_tags": [],
                "confidence": 0.0,
                "fallback": True,
            }

        # 有 API key：使用 DeepSeek
        import httpx

        prompt = f"""你是一个名片匹配分析助手。请分析以下用户的查询和标签，判断匹配意图。

用户查询：{user_query}

用户标签：{', '.join(user_tags) if user_tags else '无'}

请返回 JSON 格式分析结果：
{{
    "matched": true/false,           // 用户查询是否与标签匹配
    "intent": "匹配意图说明",         // 用一句话分析匹配逻辑
    "suggested_tags": ["标签1", "标签2"],  // 根据查询建议补充的标签
    "confidence": 0.0-1.0           // 匹配置信度
}}

仅返回 JSON，不要额外说明。
"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    settings.DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": "你是一个名片匹配分析助手，返回严格的 JSON。"},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 300,
                        "temperature": 0.1,
                    },
                )
                result = resp.json()
                content = result["choices"][0]["message"]["content"].strip()
                # 提取 JSON
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    parsed["fallback"] = False
                    return parsed
        except Exception:
            pass

        # 回退
        return {
            "matched": False,
            "intent": "DeepSeek 分析失败",
            "suggested_tags": [],
            "confidence": 0.0,
            "fallback": True,
        }

    @staticmethod
    def _default_layout(fields: dict) -> list[dict]:
        """默认排版方案"""
        name = fields.get("name") or "名片"
        title = fields.get("title") or ""
        company = fields.get("company") or ""
        phone = fields.get("phone") or ""
        email = fields.get("email") or ""
        wechat = fields.get("wechat") or ""

        title_line = f" {title}" if title else ""
        cover_content = f"{name}{title_line}"

        contact_lines = []
        if phone:
            contact_lines.append(f"📞 {phone}")
        if email:
            contact_lines.append(f"✉️ {email}")
        if wechat:
            contact_lines.append(f"💬 微信: {wechat}")
        contact_content = "\n".join(contact_lines) if contact_lines else "暂无联系方式"

        company_lines = []
        if company:
            company_lines.append(f"🏢 {company}")
        if title:
            company_lines.append(f"📌 {title}")
        company_content = "\n".join(company_lines) if company_lines else "暂无企业信息"

        return [
            {"sort_order": 0, "content_type": "cover", "content": cover_content},
            {"sort_order": 1, "content_type": "text", "content": contact_content},
            {"sort_order": 2, "content_type": "text", "content": company_content},
            {"sort_order": 3, "content_type": "image", "content": "扫码联系"},
        ]
