"""
外部模块适配器基类 (ExternalModuleAdapter)

所有外部模块必须继承 ExternalModuleAdapter 并实现其抽象方法。
框架通过该类统一管理外部模块的安装、健康检查和Webhook事件处理。
"""

from abc import ABC, abstractmethod
from typing import Any


class ExternalModuleAdapter(ABC):
    """外部模块适配器基类

    每个集成到链客宝的外部模块都应实现此适配器，
    框架通过它执行模块的生命周期管理：
      1. install()   — 首次部署时执行（注册路由、创建表、设置权限）
      2. healthcheck() — 周期性/按需检查模块可用性
      3. handle_webhook() — 接收并处理来自外部系统的回调事件

    Attributes:
        module_name: 外部模块的唯一名称（应与 module.yaml 中的 name 一致）
        config:      模块配置字典，由框架在初始化时注入
    """

    module_name: str
    config: dict

    def __init__(self, module_name: str, config: dict | None = None):
        self.module_name = module_name
        self.config = config or {}

    # ── 抽象方法 ──────────────────────────────────────────────

    @abstractmethod
    async def install(self) -> bool:
        """安装外部模块

        生命周期中的"安装"步骤，仅在模块首次注册时调用一次。
        典型职责：
          - 注册额外的 API 路由
          - 创建目标数据库表（如需独立存储）
          - 设置权限与角色

        Returns:
            True 表示安装成功，False 表示失败。
        """

    @abstractmethod
    async def healthcheck(self) -> bool:
        """健康检查

        框架定期或按需调用此方法，确认外部模块的后端服务可达且运行正常。
        实现应包含：
          - 连接外部服务的可达性检查
          - 内部状态自检

        Returns:
            True 表示模块健康，False 表示异常。
        """

    @abstractmethod
    async def handle_webhook(self, event: str, data: dict) -> dict:
        """处理外部模块的Webhook回调

        当外部系统通过 Webhook 推送事件时，框架将事件名和载荷数据
        路由到对应模块的此方法。

        Args:
            event: 事件类型名称（例如 "order.created", "payment.success"）
            data:  事件载荷（解析后的 JSON 字典）

        Returns:
            处理结果字典，至少包含 {"status": "ok" | "error", "message": "..."}
        """

    # ── 便捷方法（可选覆盖） ─────────────────────────────────

    async def uninstall(self) -> bool:
        """卸载外部模块

        默认实现不做任何操作，子类可覆盖以执行清理（如删除路由、表等）。

        Returns:
            True 表示卸载成功。
        """
        return True

    def get_config(self, key: str, default: Any = None) -> Any:
        """安全获取配置项"""
        return self.config.get(key, default)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(module_name='{self.module_name}')>"
