"""
AI数字名片 检索增强生成(RAG)管道
=================================
从向量搜索升级为完整的RAG管道，包含：
  1. 上下文构建（向量搜索结果 + 用户画像 + 关系图谱）
  2. DeepSeek API 调用（流式/非流式）
  3. 源引用追踪（每个回复片段关联原始数据源）
  4. 支持多轮对话上下文

依赖:
  - vector_search.py 提供向量搜索
  - knowledge_graph.py 提供关系图谱上下文
  - config.py 中 DEEPSEEK_API_KEY / DEEPSEEK_API_URL
"""

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.vector_search import VectorSearchEngine
from app.config import settings
from app.models.brochure import Brochure, Page
from app.models.tag import MatchRecord, UserTag
from app.models.user import User

logger = logging.getLogger(__name__)


# ======================================================================
# 数据模型
# ======================================================================


@dataclass
class RAGContext:
    """RAG 上下文 - 包含检索结果和用户画像"""

    query: str
    user_id: int
    vector_results: list[dict] = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)
    related_brochures: list[dict] = field(default_factory=list)
    match_suggestions: list[dict] = field(default_factory=list)
    knowledge_graph_context: dict = field(default_factory=dict)
    source_refs: list[dict] = field(default_factory=list)
    conversation_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "user_id": self.user_id,
            "vector_results": self.vector_results[:5],
            "user_profile": self.user_profile,
            "related_brochures": self.related_brochures[:3],
            "match_suggestions": self.match_suggestions[:3],
            "knowledge_graph_context": self.knowledge_graph_context,
            "source_refs": self.source_refs,
            "conversation_history": self.conversation_history[-5:],
        }


@dataclass
class RAGResponse:
    """RAG 响应 - 包含生成的回答和源引用"""

    answer: str
    sources: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    model_used: str = "deepseek-chat"
    tokens_used: int = 0

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "confidence": self.confidence,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
        }


# ======================================================================
# DeepSeek API 调用
# ======================================================================


class DeepSeekClient:
    """DeepSeek API 客户端 - 支持非流式和流式调用"""

    BASE_URL: str = settings.DEEPSEEK_API_URL or "https://api.deepseek.com/v1/chat/completions"
    API_KEY: str = settings.DEEPSEEK_API_KEY or ""

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key or self.API_KEY
        self.base_url = base_url or self.BASE_URL
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def chat(
        self,
        messages: list[dict],
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
    ) -> dict | AsyncGenerator[str, None]:
        """调用 DeepSeek Chat API

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            model: 模型名
            temperature: 温度
            max_tokens: 最大输出 token 数
            stream: 是否流式返回

        Returns:
            非流式: 完整响应 dict
            流式: AsyncGenerator[str, None] 逐块产出文本
        """
        from app.middleware.metrics import track_ai_inference

        with track_ai_inference(model_name=model):
            session = await self._get_session()
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream,
            }

            try:
                async with session.post(self.base_url, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"DeepSeek API error (status={resp.status}): {error_text}")
                        return {"error": f"API调用失败: {resp.status}", "detail": error_text}

                    if stream:
                        return self._stream_response(resp)

                    data = await resp.json()
                    return self._parse_response(data)
            except aiohttp.ClientError as e:
                logger.error(f"DeepSeek API network error: {e}")
                return {"error": f"网络错误: {str(e)}"}
            except Exception as e:
                logger.error(f"DeepSeek API unexpected error: {e}")
                return {"error": f"未知错误: {str(e)}"}

    async def _stream_response(self, resp: aiohttp.ClientResponse) -> AsyncGenerator[str, None]:
        """解析流式响应"""
        async for line in resp.content:
            if line.startswith(b"data: "):
                chunk = line[6:].strip()
                if chunk == b"[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    def _parse_response(self, data: dict) -> dict:
        """解析非流式响应为统一格式"""
        try:
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            usage = data.get("usage", {})
            return {
                "content": message.get("content", ""),
                "role": message.get("role", "assistant"),
                "finish_reason": choice.get("finish_reason", ""),
                "tokens_used": usage.get("total_tokens", 0),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            }
        except (IndexError, KeyError, TypeError) as e:
            logger.error(f"Parse DeepSeek response error: {e}, raw: {data}")
            return {"content": "", "error": f"解析响应失败: {str(e)}"}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ======================================================================
# 上下文构建器
# ======================================================================


class ContextBuilder:
    """构建 RAG 上下文的工具类"""

    @staticmethod
    async def build_user_profile(db: AsyncSession, user_id: int) -> dict:
        """构建用户画像"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            return {}

        # 获取标签
        result = await db.execute(select(UserTag).where(UserTag.user_id == user_id))
        tags = result.scalars().all()
        provide_tags = [t.tag for t in tags if t.tag_type == "provide"]
        need_tags = [t.tag for t in tags if t.tag_type == "need"]

        return {
            "user_id": user.id,
            "name": user.name,
            "company": user.company,
            "title": user.title,
            "intro": user.intro,
            "provide_tags": provide_tags,
            "need_tags": need_tags,
            "membership_tier": user.membership_tier,
        }

    @staticmethod
    async def build_brochure_context(db: AsyncSession, user_id: int) -> list[dict]:
        """构建用户画册内容摘要"""
        result = await db.execute(
            select(Brochure).where(
                Brochure.user_id == user_id,
                Brochure.status == "published",
            )
        )
        brochures = result.scalars().all()
        contexts = []
        for b in brochures:
            pages_result = await db.execute(select(Page).where(Page.brochure_id == b.id).order_by(Page.sort_order))
            pages = pages_result.scalars().all()
            page_summaries = []
            for p in pages:
                summary = p.ai_summary or p.content[:200] if p.content else ""
                if summary:
                    page_summaries.append(summary)
            contexts.append(
                {
                    "brochure_id": b.id,
                    "title": b.title,
                    "purpose": b.purpose,
                    "page_count": b.pages_count,
                    "content_summary": page_summaries[:5],
                }
            )
        return contexts

    @staticmethod
    async def build_vector_context(
        db: AsyncSession,
        query: str,
        user_id: int,
        top_k: int = 10,
    ) -> list[dict]:
        """构建向量搜索结果上下文"""
        vse = VectorSearchEngine(db)
        try:
            results = await vse.search(query=query, top_k=top_k, min_score=0.3)
            return results
        except Exception as e:
            logger.warning(f"Vector search failed (fallback: empty): {e}")
            return []

    @staticmethod
    async def build_match_context(
        db: AsyncSession,
        user_id: int,
        top_k: int = 5,
    ) -> list[dict]:
        """构建匹配建议上下文"""
        result = await db.execute(
            select(MatchRecord)
            .where(
                (MatchRecord.user_a_id == user_id) | (MatchRecord.user_b_id == user_id),
                MatchRecord.match_score >= 0.5,
            )
            .order_by(MatchRecord.match_score.desc())
            .limit(top_k)
        )
        records = result.scalars().all()
        suggestions = []
        for r in records:
            target_id = r.user_b_id if r.user_a_id == user_id else r.user_a_id
            user_result = await db.execute(select(User).where(User.id == target_id))
            target_user = user_result.scalars().first()
            if target_user:
                suggestions.append(
                    {
                        "user_id": target_user.id,
                        "name": target_user.name,
                        "company": target_user.company,
                        "title": target_user.title,
                        "match_score": r.match_score,
                        "status": r.status,
                    }
                )
        return suggestions

    @staticmethod
    def build_system_prompt(context: RAGContext) -> str:
        """构建系统提示词"""
        prompt_parts = [
            "你是一个AI数字名片的智能助手，帮助用户分析商业匹配、提供推荐建议。",
            "请使用以下检索到的信息来回答问题。如果信息不足，请如实说明。",
            "回答时请附上信息来源引用，格式为 [来源: 类型/名称]。",
            "",
            "=== 用户画像 ===",
        ]

        profile = context.user_profile
        if profile:
            prompt_parts.append(f"用户: {profile.get('name', '未知')}")
            prompt_parts.append(f"公司: {profile.get('company', '未设置')}")
            prompt_parts.append(f"职位: {profile.get('title', '未设置')}")
            prompt_parts.append(f"简介: {profile.get('intro', '无')}")
            provide = profile.get("provide_tags", [])
            need = profile.get("need_tags", [])
            if provide:
                prompt_parts.append(f"能提供: {'、'.join(provide)}")
            if need:
                prompt_parts.append(f"需要: {'、'.join(need)}")

        prompt_parts.append("")
        prompt_parts.append("=== 向量搜索结果 ===")
        for i, vr in enumerate(context.vector_results[:5], 1):
            name = vr.get("user_name", vr.get("name", f"用户{vr.get('user_id', '?')}"))
            company = vr.get("company", "")
            intro = vr.get("intro", "")
            score = vr.get("score", 0)
            prompt_parts.append(f"{i}. {name} ({company}) - 相似度: {score:.2f}")
            if intro:
                prompt_parts.append(f"   简介: {intro[:300]}")

        prompt_parts.append("")
        prompt_parts.append("=== 匹配建议 ===")
        for j, ms in enumerate(context.match_suggestions, 1):
            prompt_parts.append(
                f"{j}. {ms.get('name', '?')} - {ms.get('company', '?')} - 匹配度: {ms.get('match_score', 0):.2f}"
            )

        if context.knowledge_graph_context:
            prompt_parts.append("")
            prompt_parts.append("=== 关系图谱 ===")
            kg = context.knowledge_graph_context
            if kg.get("trusted_connections"):
                prompt_parts.append(f"信任连接: {len(kg['trusted_connections'])} 个")
            if kg.get("common_tags_with_others"):
                prompt_parts.append(f"共同标签关联: {len(kg['common_tags_with_others'])} 个")
            if kg.get("industry_peers"):
                prompt_parts.append(f"行业同行: {len(kg['industry_peers'])} 个")

        prompt_parts.append("")
        prompt_parts.append("回答要求:")
        prompt_parts.append("1. 基于上述检索信息回答问题")
        prompt_parts.append("2. 对每个事实标注来源引用")
        prompt_parts.append("3. 如果信息不足，明确告知用户")
        prompt_parts.append("4. 使用中文回答")
        prompt_parts.append("5. 可以给出进一步的行动建议")

        return "\n".join(prompt_parts)


# ======================================================================
# RAG 管道主类
# ======================================================================


class RAGPipeline:
    """检索增强生成管道 - 整合搜索 + 上下文 + LLM 生成"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.deepseek = DeepSeekClient()
        self.context_builder = ContextBuilder()

    async def query(
        self,
        user_id: int,
        query_text: str,
        top_k: int = 10,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        include_sources: bool = True,
        conversation_history: list[dict] | None = None,
    ) -> RAGResponse:
        """执行 RAG 查询

        Args:
            user_id: 当前用户 ID
            query_text: 查询文本
            top_k: 向量搜索返回数量
            temperature: LLM 温度
            max_tokens: 最大 token 数
            include_sources: 是否包含源引用
            conversation_history: 多轮对话历史

        Returns:
            RAGResponse 包含答案和源引用
        """
        # 1. 构建上下文
        context = RAGContext(
            query=query_text,
            user_id=user_id,
            conversation_history=conversation_history or [],
        )

        # 并行构建各层上下文
        import asyncio

        (
            context.user_profile,
            context.related_brochures,
            context.vector_results,
            context.match_suggestions,
        ) = await asyncio.gather(
            self.context_builder.build_user_profile(self.db, user_id),
            self.context_builder.build_brochure_context(self.db, user_id),
            self.context_builder.build_vector_context(self.db, query_text, user_id, top_k),
            self.context_builder.build_match_context(self.db, user_id),
        )

        # 2. 构建系统提示词
        system_prompt = self.context_builder.build_system_prompt(context)

        # 3. 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]

        # 添加对话历史
        for msg in context.conversation_history:
            messages.append(msg)

        # 添加用户当前问题
        messages.append({"role": "user", "content": query_text})

        # 4. 调用 DeepSeek API
        response = await self.deepseek.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        # 5. 构建源引用
        sources = []
        if include_sources:
            for vr in context.vector_results[:5]:
                sources.append(
                    {
                        "type": "vector_search",
                        "user_id": vr.get("user_id"),
                        "user_name": vr.get("user_name", vr.get("name", "")),
                        "company": vr.get("company", ""),
                        "score": vr.get("score", 0),
                    }
                )
            for ms in context.match_suggestions[:3]:
                sources.append(
                    {
                        "type": "match_record",
                        "user_id": ms.get("user_id"),
                        "user_name": ms.get("name", ""),
                        "company": ms.get("company", ""),
                        "match_score": ms.get("match_score", 0),
                    }
                )

        # 6. 生成 RAG 响应
        answer = response.get("content", "") if isinstance(response, dict) else str(response)
        error = response.get("error", "") if isinstance(response, dict) else ""

        if error:
            logger.warning(f"RAG pipeline LLM error: {error}")
            # 降级: 直接返回向量搜索结果
            answer = self._fallback_answer(context)

        return RAGResponse(
            answer=answer,
            sources=sources,
            confidence=0.9 if not error else 0.5,
            model_used="deepseek-chat",
            tokens_used=response.get("tokens_used", 0) if isinstance(response, dict) else 0,
        )

    def _fallback_answer(self, context: RAGContext) -> str:
        """降级方案：当 LLM 不可用时，基于检索结果生成结构化回复"""
        parts = ["我暂时无法使用 AI 生成能力，以下是基于检索结果的信息：\n"]

        if context.vector_results:
            parts.append("**相关用户推荐：**")
            for i, vr in enumerate(context.vector_results[:5], 1):
                name = vr.get("user_name", vr.get("name", f"用户{vr.get('user_id', '?')}"))
                company = vr.get("company", "")
                score = vr.get("score", 0)
                parts.append(f"  {i}. {name} ({company}) - 匹配度 {score:.2f}")
            parts.append("")

        if context.match_suggestions:
            parts.append("**匹配建议：**")
            for j, ms in enumerate(context.match_suggestions, 1):
                parts.append(
                    f"  {j}. {ms.get('name', '?')} - {ms.get('company', '?')} - 分数: {ms.get('match_score', 0):.2f}"
                )

        return "\n".join(parts)

    async def query_stream(
        self,
        user_id: int,
        query_text: str,
        top_k: int = 10,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        conversation_history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式 RAG 查询"""
        # 构建上下文（同上）
        context = RAGContext(
            query=query_text,
            user_id=user_id,
            conversation_history=conversation_history or [],
        )

        import asyncio

        (
            context.user_profile,
            context.related_brochures,
            context.vector_results,
            context.match_suggestions,
        ) = await asyncio.gather(
            self.context_builder.build_user_profile(self.db, user_id),
            self.context_builder.build_brochure_context(self.db, user_id),
            self.context_builder.build_vector_context(self.db, query_text, user_id, top_k),
            self.context_builder.build_match_context(self.db, user_id),
        )

        system_prompt = self.context_builder.build_system_prompt(context)
        messages = [{"role": "system", "content": system_prompt}]

        for msg in conversation_history or []:
            messages.append(msg)
        messages.append({"role": "user", "content": query_text})

        result = await self.deepseek.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        if isinstance(result, AsyncGenerator):
            async for chunk in result:
                yield chunk
        else:
            yield result.get("content", "") if isinstance(result, dict) else str(result)

    async def close(self):
        await self.deepseek.close()
