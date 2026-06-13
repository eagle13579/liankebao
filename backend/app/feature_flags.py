"""
链客宝AI Feature Flags 灰度发布系统

功能:
  1. 基于 JSON 配置热加载的 Feature Flags 管理
  2. 按用户百分比灰度、按 org_id 灰度、按环境(dev/staging/prod) 控制
  3. 内置 flags: new_ai_pipeline, vector_search_v2, new_checkout, dark_mode
  4. FastAPI 路由: GET /api/flags, POST /api/flags/admin
  5. FastAPI 中间件: inject_feature_flags(request)
  6. flags_config.json 热加载（带缓存和 mtime 检查）
"""

import hashlib
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ============================================================
# 配置路径
# ============================================================

FLAGS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "flags_config.json",
)

# ============================================================
# 灰度策略枚举
# ============================================================


class RolloutStrategy(str, Enum):
    """灰度发布策略"""

    PERCENTAGE = "percentage"  # 按用户百分比
    ORG_ID = "org_id"  # 按组织 ID 白名单
    ENVIRONMENT = "environment"  # 按环境
    ALWAYS = "always"  # 全部开启
    NEVER = "never"  # 全部关闭


# ============================================================
# Flag 定义
# ============================================================


@dataclass
class FeatureFlag:
    """单个 Feature Flag 定义"""

    key: str
    description: str
    default: bool = False
    strategy: RolloutStrategy = RolloutStrategy.NEVER
    rollout_percentage: int = 0  # 0-100
    org_whitelist: list[int] = field(default_factory=list)
    environments: list[str] = field(default_factory=lambda: ["dev", "staging"])
    enabled: bool = False
    owner: str = ""
    created_at: str = ""
    updated_at: str = ""


# ============================================================
# 内置默认 Flag 定义
# ============================================================

BUILTIN_FLAGS: dict[str, dict[str, Any]] = {
    "new_ai_pipeline": {
        "key": "new_ai_pipeline",
        "description": "新AI名片智能处理管线（替代旧pipeline）",
        "default": False,
        "strategy": "percentage",
        "rollout_percentage": 10,
        "org_whitelist": [],
        "environments": ["dev", "staging"],
        "enabled": False,
        "owner": "AI团队",
        "created_at": "2025-05-01T00:00:00Z",
        "updated_at": "2025-05-01T00:00:00Z",
    },
    "vector_search_v2": {
        "key": "vector_search_v2",
        "description": "向量搜索v2（改进版语义匹配+重排序）",
        "default": False,
        "strategy": "percentage",
        "rollout_percentage": 5,
        "org_whitelist": [],
        "environments": ["dev", "staging"],
        "enabled": False,
        "owner": "搜索团队",
        "created_at": "2025-05-01T00:00:00Z",
        "updated_at": "2025-05-01T00:00:00Z",
    },
    "new_checkout": {
        "key": "new_checkout",
        "description": "新版结算页面（优化支付流程）",
        "default": False,
        "strategy": "percentage",
        "rollout_percentage": 20,
        "org_whitelist": [1, 5, 10],
        "environments": ["dev", "staging", "prod"],
        "enabled": False,
        "owner": "支付团队",
        "created_at": "2025-05-01T00:00:00Z",
        "updated_at": "2025-05-01T00:00:00Z",
    },
    "dark_mode": {
        "key": "dark_mode",
        "description": "暗色模式UI（仅前端样式切换）",
        "default": True,
        "strategy": "environment",
        "rollout_percentage": 0,
        "org_whitelist": [],
        "environments": ["dev"],
        "enabled": True,
        "owner": "前端团队",
        "created_at": "2025-05-01T00:00:00Z",
        "updated_at": "2025-05-01T00:00:00Z",
    },
    "F-CHAINKE-CHATBOT-01": {
        "key": "F-CHAINKE-CHATBOT-01",
        "description": "AI客服机器人系统 - 意图识别+FAQ知识库+聊天API+WebUI+上下文管理+转人工",
        "default": True,
        "strategy": "always",
        "rollout_percentage": 100,
        "org_whitelist": [],
        "environments": ["dev", "staging", "prod"],
        "enabled": True,
        "owner": "AI团队",
        "created_at": "2026-06-13T00:00:00Z",
        "updated_at": "2026-06-13T00:00:00Z",
    },
}


# ============================================================
# 配置管理器（带热加载）
# ============================================================


class FlagsConfigManager:
    """Feature Flags 配置管理器

    支持从 JSON 文件热加载配置，定期检查文件 mtime 变化。
    提供线程安全的配置读取和写入。
    """

    def __init__(self, config_path: str = FLAGS_CONFIG_PATH):
        self._config_path = config_path
        self._lock = threading.RLock()
        self._flags: dict[str, FeatureFlag] = {}
        self._last_mtime: float = 0
        self._last_reload: float = 0
        self._reload_interval: float = 10.0  # 最小重新加载间隔（秒）
        self._load_or_init()

    # ---- 配置加载 ----

    def _load_or_init(self) -> None:
        """加载配置文件，如果不存在则使用内置默认值初始化"""
        if os.path.exists(self._config_path):
            try:
                self._load_from_file()
                logger.info(f"Feature Flags 配置已加载: {self._config_path} ({len(self._flags)} flags)")
                return
            except Exception as e:
                logger.warning(f"Feature Flags 配置加载失败，使用默认值: {e}")

        # 初始化默认配置
        self._flags = {}
        for key, cfg in BUILTIN_FLAGS.items():
            self._flags[key] = FeatureFlag(**cfg)
        self._save_to_file()
        logger.info(f"Feature Flags 默认配置已初始化 ({len(self._flags)} flags)")

    def _load_from_file(self) -> None:
        """从 JSON 文件加载配置"""
        with open(self._config_path, encoding="utf-8") as f:
            raw = json.load(f)

        flags = {}
        for key, cfg in raw.items():
            # 合并内置默认值，确保新字段存在
            builtin = BUILTIN_FLAGS.get(key, {})
            merged = {**builtin, **cfg}
            merged["key"] = key
            # 处理 strategy 枚举
            if isinstance(merged.get("strategy"), str):
                try:
                    merged["strategy"] = RolloutStrategy(merged["strategy"])
                except ValueError:
                    merged["strategy"] = RolloutStrategy.NEVER
            flags[key] = FeatureFlag(**merged)

        self._flags = flags
        self._last_mtime = os.path.getmtime(self._config_path)
        self._last_reload = time.time()

    def _save_to_file(self) -> None:
        """将当前配置保存到 JSON 文件"""
        data = {}
        for key, flag in self._flags.items():
            data[key] = {
                "key": flag.key,
                "description": flag.description,
                "default": flag.default,
                "strategy": flag.strategy.value,
                "rollout_percentage": flag.rollout_percentage,
                "org_whitelist": flag.org_whitelist,
                "environments": flag.environments,
                "enabled": flag.enabled,
                "owner": flag.owner,
                "created_at": flag.created_at,
                "updated_at": flag.updated_at,
            }
        dir_path = os.path.dirname(self._config_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._last_mtime = os.path.getmtime(self._config_path)

    def reload_if_needed(self) -> bool:
        """如果配置文件已变更则热加载，返回是否重新加载"""
        with self._lock:
            now = time.time()
            if now - self._last_reload < self._reload_interval:
                return False
            try:
                current_mtime = os.path.getmtime(self._config_path)
                if current_mtime != self._last_mtime:
                    self._load_from_file()
                    logger.info("Feature Flags 配置已热加载")
                    return True
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Feature Flags 热加载失败: {e}")
            return False

    # ---- 查询 ----

    def get_flag(self, key: str) -> FeatureFlag | None:
        """获取指定 flag 的配置"""
        self.reload_if_needed()
        with self._lock:
            return self._flags.get(key)

    def get_all_flags(self) -> dict[str, FeatureFlag]:
        """获取所有 flags"""
        self.reload_if_needed()
        with self._lock:
            return dict(self._flags)

    def is_enabled(
        self,
        key: str,
        user_id: int | None = None,
        org_id: int | None = None,
        env: str | None = None,
    ) -> bool:
        """判断指定 flag 对某个用户是否启用

        灰度逻辑：
          1. 如果 flag 全局禁用 → False
          2. 如果 strategy=always → True
          3. 如果 strategy=never → False
          4. 如果 strategy=environment → 检查当前环境是否在允许列表中
          5. 如果 strategy=org_id → 检查 org_id 是否在白名单中
          6. 如果 strategy=percentage → 对 user_id 做一致性哈希取模
        """
        flag = self.get_flag(key)
        if flag is None:
            # 未知 flag 返回内置默认值
            builtin = BUILTIN_FLAGS.get(key)
            return builtin["default"] if builtin else False

        # 全局开关
        if not flag.enabled:
            return False

        # 获取当前环境
        current_env = env or os.environ.get("ENV", os.environ.get("APP_ENV", "dev")).lower()

        # 环境检查：如果当前环境不在支持列表中，返回 False
        if flag.environments and current_env not in [e.lower() for e in flag.environments]:
            return False

        # 策略判断
        if flag.strategy == RolloutStrategy.ALWAYS:
            return True
        elif flag.strategy == RolloutStrategy.NEVER:
            return False
        elif flag.strategy == RolloutStrategy.ENVIRONMENT:
            # 环境策略已经在上面检查过了
            return True
        elif flag.strategy == RolloutStrategy.ORG_ID:
            if org_id is not None and org_id in flag.org_whitelist:
                return True
            return False
        elif flag.strategy == RolloutStrategy.PERCENTAGE:
            if user_id is not None:
                # 使用一致性哈希确保同一用户始终命中相同灰度组
                hash_input = f"{key}:{user_id}"
                hash_val = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)
                return (hash_val % 100) < flag.rollout_percentage
            else:
                # 无 user_id 时使用随机
                return random.randint(0, 99) < flag.rollout_percentage

        return flag.default

    def get_user_flags(
        self,
        user_id: int | None = None,
        org_id: int | None = None,
        env: str | None = None,
    ) -> dict[str, bool]:
        """获取用户可用的所有 flags（key → enabled 布尔值）"""
        result = {}
        with self._lock:
            keys = list(self._flags.keys())
        for key in keys:
            result[key] = self.is_enabled(key, user_id=user_id, org_id=org_id, env=env)
        # 包含未在 JSON 中但内置定义的 flags
        for key in BUILTIN_FLAGS:
            if key not in result:
                result[key] = self.is_enabled(key, user_id=user_id, org_id=org_id, env=env)
        return result

    # ---- 管理 ----

    def set_flag(self, key: str, updates: dict[str, Any]) -> FeatureFlag | None:
        """更新 flag 配置（线程安全）"""
        with self._lock:
            flag = self._flags.get(key)
            if flag is None:
                # 如果是内置 flag 但未加载，先创建
                builtin = BUILTIN_FLAGS.get(key)
                if builtin:
                    flag = FeatureFlag(**builtin)
                    self._flags[key] = flag
                else:
                    return None

            # 更新字段
            for field, value in updates.items():
                if hasattr(flag, field) and field != "key":
                    if field == "strategy" and isinstance(value, str):
                        try:
                            value = RolloutStrategy(value)
                        except ValueError:
                            continue
                    setattr(flag, field, value)

            flag.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._save_to_file()
            return flag

    def delete_flag(self, key: str) -> bool:
        """删除 flag（不删除内置 flags，仅恢复到默认）"""
        with self._lock:
            if key in BUILTIN_FLAGS:
                # 内置 flag 恢复到默认
                builtin = BUILTIN_FLAGS[key]
                self._flags[key] = FeatureFlag(**builtin)
                self._save_to_file()
                return True
            if key in self._flags:
                del self._flags[key]
                self._save_to_file()
                return True
            return False

    def to_dict(self) -> dict[str, Any]:
        """导出所有 flags 为可序列化字典"""
        result = {}
        with self._lock:
            for key, flag in self._flags.items():
                result[key] = {
                    "key": flag.key,
                    "description": flag.description,
                    "default": flag.default,
                    "strategy": flag.strategy.value
                    if isinstance(flag.strategy, RolloutStrategy)
                    else str(flag.strategy),
                    "rollout_percentage": flag.rollout_percentage,
                    "org_whitelist": flag.org_whitelist,
                    "environments": flag.environments,
                    "enabled": flag.enabled,
                    "owner": flag.owner,
                    "created_at": flag.created_at,
                    "updated_at": flag.updated_at,
                }
        # 添加未在 JSON 中但内置定义的 flags
        for key, cfg in BUILTIN_FLAGS.items():
            if key not in result:
                result[key] = dict(cfg)
        return result


# ============================================================
# 全局单例
# ============================================================

_flags_manager: FlagsConfigManager | None = None


def get_flags_manager() -> FlagsConfigManager:
    """获取全局 FlagsConfigManager 单例"""
    global _flags_manager
    if _flags_manager is None:
        _flags_manager = FlagsConfigManager()
    return _flags_manager


# ============================================================
# FastAPI 路由
# ============================================================

from fastapi import APIRouter

flags_router = APIRouter(tags=["feature_flags"])


@flags_router.get(
    "/api/flags",
    summary="获取用户可用的 Feature Flags",
    description="返回当前用户可用的所有 Feature Flags（根据灰度策略计算）",
)
async def get_user_flags(request: Request):
    """返回当前请求用户可用的 Feature Flags

    从请求中提取 user_id 和 org_id，计算每个 flag 是否启用。
    """
    manager = get_flags_manager()

    # 从请求状态中提取用户信息（由中间件或认证模块注入）
    user_id = getattr(request.state, "user_id", None)
    org_id = getattr(request.state, "org_id", None)

    # 尝试从请求头中获取
    if user_id is None:
        user_id_str = request.headers.get("X-User-ID")
        if user_id_str and user_id_str.isdigit():
            user_id = int(user_id_str)

    if org_id is None:
        org_id_str = request.headers.get("X-Org-ID")
        if org_id_str and org_id_str.isdigit():
            org_id = int(org_id_str)

    env = os.environ.get("ENV", os.environ.get("APP_ENV", "dev")).lower()

    flags = manager.get_user_flags(user_id=user_id, org_id=org_id, env=env)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "flags": flags,
            "user_id": user_id,
            "org_id": org_id,
            "environment": env,
        },
    }


@flags_router.post(
    "/api/flags/admin",
    summary="管理员开关 Feature Flag",
    description="管理员动态开启/关闭或修改 Feature Flag 配置",
)
async def admin_set_flag(request: Request):
    """管理员动态修改 Feature Flag 配置

    请求体:
    {
        "key": "new_ai_pipeline",
        "enabled": true,
        "rollout_percentage": 50,
        "strategy": "percentage",
        "org_whitelist": [1, 2, 3],
        "environments": ["dev", "staging", "prod"]
    }
    """
    # 管理员权限检查
    user_role = getattr(request.state, "user_role", None)
    if user_role != "admin":
        # 尝试从请求头获取
        role_str = request.headers.get("X-User-Role", "")
        if role_str != "admin":
            return JSONResponse(
                status_code=403,
                content={"code": 403, "message": "需要管理员权限"},
            )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "请求体必须是有效 JSON"},
        )

    key = body.get("key", "").strip()
    if not key:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "缺少 'key' 字段"},
        )

    # 提取可更新的字段
    updatable_fields = [
        "enabled",
        "description",
        "strategy",
        "rollout_percentage",
        "org_whitelist",
        "environments",
        "default",
        "owner",
    ]
    updates = {}
    for field in updatable_fields:
        if field in body:
            updates[field] = body[field]

    if not updates:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "没有可更新的字段"},
        )

    manager = get_flags_manager()
    flag = manager.set_flag(key, updates)

    if flag is None:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": f"Flag '{key}' 不存在"},
        )

    logger.info(
        f"管理员更新 Feature Flag: {key}",
        extra={"updates": updates, "admin_role": user_role},
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "key": flag.key,
            "enabled": flag.enabled,
            "strategy": flag.strategy.value if isinstance(flag.strategy, RolloutStrategy) else str(flag.strategy),
            "rollout_percentage": flag.rollout_percentage,
        },
    }


@flags_router.get(
    "/api/flags/admin",
    summary="查看所有 Feature Flags 配置",
    description="管理员查看所有 Feature Flags 的详细配置",
)
async def admin_list_flags(request: Request):
    """查看所有 Feature Flags 的完整配置（管理员）"""
    user_role = getattr(request.state, "user_role", None)
    if user_role != "admin":
        role_str = request.headers.get("X-User-Role", "")
        if role_str != "admin":
            return JSONResponse(
                status_code=403,
                content={"code": 403, "message": "需要管理员权限"},
            )

    manager = get_flags_manager()
    return {
        "code": 200,
        "message": "success",
        "data": manager.to_dict(),
    }


# ============================================================
# FastAPI 中间件
# ============================================================


class FeatureFlagsMiddleware:
    """Feature Flags 中间件

    将当前用户的 Feature Flags 注入到 request.state 中，
    后续路由可以直接通过 request.state.feature_flags 获取。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from fastapi import Request

        request = Request(scope, receive)

        # 提取用户信息
        user_id = getattr(request.state, "user_id", None)
        org_id = getattr(request.state, "org_id", None)

        if user_id is None:
            uid_str = request.headers.get("X-User-ID", "")
            user_id = int(uid_str) if uid_str.isdigit() else None

        if org_id is None:
            oid_str = request.headers.get("X-Org-ID", "")
            org_id = int(oid_str) if oid_str.isdigit() else None

        # 获取 flags
        manager = get_flags_manager()
        try:
            flags = manager.get_user_flags(user_id=user_id, org_id=org_id)
            request.state.feature_flags = flags
        except Exception as e:
            logger.warning(f"Feature Flags 中间件获取 flags 失败: {e}")
            request.state.feature_flags = {}

        await self.app(scope, receive, send)


def register_feature_flags(app: FastAPI) -> None:
    """注册 Feature Flags 路由和中间件到 FastAPI 应用"""
    app.add_middleware(FeatureFlagsMiddleware)
    app.include_router(flags_router)
    logger.info("Feature Flags 系统已注册（路由 + 中间件）")
