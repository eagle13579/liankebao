"""
Webhook 接收器 (WebhookReceiver)

提供统一的 Webhook 事件接收端点，负责：
  1. 接收外部系统推送的 JSON 事件
  2. 验证事件签名（HMAC-SHA256）
  3. 根据事件类型或模块映射路由到对应的 ExternalModuleAdapter

典型用法（在 FastAPI 路由中）:
    receiver = WebhookReceiver()
    receiver.register_module("payment_gateway", payment_adapter_instance)

    @router.post("/webhook/{module_name}")
    async def webhook_endpoint(module_name: str, payload: dict, request: Request):
        return await receiver.dispatch(module_name, payload, request)

迁移自旧版链客宝 backend/modules/external/webhook.py
适配 chainke-full: 更新 import 路径指向 features.external。
"""

import hashlib
import hmac
import logging
from typing import Any

from features.external.models.external_module import ExternalModule

logger = logging.getLogger(__name__)


class WebhookVerificationError(Exception):
    """Webhook 签名验证失败"""


class WebhookReceiver:
    """统一 Webhook 事件接收与路由

    管理模块适配器注册表，并提供事件分发入口。
    支持可选的 HMAC-SHA256 签名验证。
    """

    def __init__(self):
        # module_name -> ExternalModuleAdapter 实例
        self._adapters: dict[str, "ExternalModuleAdapter"] = {}  # noqa: F821

    # ── 注册 / 注销 ─────────────────────────────────────────

    def register_module(self, module_name: str, adapter: "ExternalModuleAdapter") -> None:  # noqa: F821
        """注册外部模块适配器

        Args:
            module_name: 模块名称（应与 module.yaml 一致）
            adapter:     ExternalModuleAdapter 实例
        """
        if module_name in self._adapters:
            logger.warning("模块 '%s' 已被注册，将被覆盖", module_name)
        self._adapters[module_name] = adapter
        logger.info("外部模块 '%s' 已注册到 WebhookReceiver", module_name)

    def unregister_module(self, module_name: str) -> None:
        """注销外部模块适配器"""
        self._adapters.pop(module_name, None)
        logger.info("外部模块 '%s' 已从 WebhookReceiver 注销", module_name)

    def get_module(self, module_name: str) -> Any | None:
        """获取已注册的模块适配器"""
        return self._adapters.get(module_name)

    # ── 签名验证 ─────────────────────────────────────────────

    @staticmethod
    def verify_signature(
        payload: bytes,
        signature: str,
        secret: str,
        algo: str = "hmac-sha256",
    ) -> bool:
        """验证 Webhook 请求签名

        支持以下算法:
          - hmac-sha256 (默认)
          - hmac-sha1

        Args:
            payload:   原始请求体 (bytes)
            signature: 请求头中携带的签名值
            secret:    预设的签名密钥
            algo:      签名算法标识

        Returns:
            True 通过验证, False 失败

        Raises:
            ValueError: 不支持的算法
        """
        if algo == "hmac-sha256":
            hash_func = hashlib.sha256
        elif algo == "hmac-sha1":
            hash_func = hashlib.sha1
        else:
            raise ValueError(f"不支持的签名算法: {algo}")

        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hash_func,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    # ── 事件分发 ─────────────────────────────────────────────

    async def dispatch_from_db(
        self,
        module_name: str,
        event: str,
        data: dict,
    ) -> dict:
        """基于数据库注册信息分发事件

        优先使用内存中已注册的适配器，否则尝试从数据库查询并动态加载。

        Args:
            module_name: 目标外部模块名称
            event:       事件类型
            data:        事件载荷

        Returns:
            处理结果字典
        """
        adapter = self._adapters.get(module_name)
        if adapter is not None:
            return await adapter.handle_webhook(event, data)

        # 尝试从数据库加载模块配置并动态初始化
        db_module = await self._load_module_from_db(module_name)
        if db_module is None:
            return {
                "status": "error",
                "message": f"外部模块 '{module_name}' 未注册",
            }

        # 这里需要框架层面的模块动态加载逻辑
        # 当前占位 — 子类或调用方应事先 register_module
        return {
            "status": "error",
            "message": (
                f"外部模块 '{module_name}' 已注册但未加载适配器实例。"
                "请先调用 register_module() 注册适配器实例。"
            ),
        }

    async def dispatch(
        self,
        module_name: str,
        event: str,
        data: dict,
        raw_body: bytes | None = None,
        signature: str | None = None,
        secret: str | None = None,
        algo: str = "hmac-sha256",
        verify: bool = True,
    ) -> dict:
        """完整的 Webhook 事件分发流程

        包含签名验证（可选）和事件路由。

        Args:
            module_name: 目标模块名称
            event:       事件类型
            data:        事件数据字典
            raw_body:    原始请求体（签名验证需要）
            signature:   请求签名值
            secret:      签名密钥
            algo:        签名算法
            verify:      是否执行签名验证

        Returns:
            处理结果字典
        """
        # 1. 签名验证
        if verify:
            if not raw_body or not signature or not secret:
                return {
                    "status": "error",
                    "message": "签名验证失败: 缺少签名参数 (raw_body/signature/secret)",
                }
            valid = self.verify_signature(raw_body, signature, secret, algo)
            if not valid:
                return {
                    "status": "error",
                    "message": "签名验证失败: 签名不匹配",
                }

        # 2. 路由到适配器
        return await self.dispatch_from_db(module_name, event, data)

    # ── 数据库查询（辅助） ──────────────────────────────────

    @staticmethod
    async def _load_module_from_db(module_name: str) -> ExternalModule | None:
        """从数据库查询外部模块注册信息

        此方法为异步占位，实际实现需在 FastAPI 依赖注入环境中
        通过数据库会话查询 ExternalModule 表。
        """
        # TODO: 集成实际数据库查询逻辑
        # async with get_db() as db:
        #     return await db.query(ExternalModule).filter(
        #         ExternalModule.name == module_name,
        #         ExternalModule.is_active == True,
        #     ).first()
        logger.debug("从数据库加载外部模块配置: %s (当前为占位实现)", module_name)
        return None

    def __repr__(self) -> str:
        return f"<WebhookReceiver(modules={list(self._adapters.keys())})>"
