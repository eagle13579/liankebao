"""
链客宝 — Feature Flags 功能开关 + 灰度发布系统
===============================================
提供功能开关管理、灰度发布规则评估（白名单/百分比/地域）以及 REST API。

类:
    FeatureFlag         单个功能开关定义
    FeatureFlagManager  全局管理器（含 JSON 文件持久化）
    UserContext         用户上下文（用于灰度规则评估）

API 端点:
    GET    /api/v1/flags        查询所有 flags
    GET    /api/v1/flags/{name}  查询单个 flag
    PUT    /api/v1/flags/{name}  修改 flag enabled 状态
"""

import json
import os
import hashlib
import copy
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


# ===================================================================
# 数据模型
# ===================================================================


class UserContext(BaseModel):
    """用户上下文 — 用于灰度发布规则评估"""
    user_id: str = ""
    region: str = ""


class FeatureFlag(BaseModel):
    """功能开关定义"""
    name: str
    description: str = ""
    enabled: bool = False
    rules: dict[str, Any] = {}
    owner: str = ""
    created_at: str = ""

    def model_post_init(self, __context: Any) -> None:
        """自动填充 created_at（如果为空）"""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ===================================================================
# 规则评估器
# ===================================================================


def _evaluate_rules(flag: FeatureFlag, user: UserContext) -> bool:
    """
    评估灰度发布规则。

    规则语义:
        - whitelist: 白名单用户直接放行（override）
        - percentage: 基于 user_id hash 的灰度百分比 (AND)
        - regions:    地域白名单 (AND)
        - 叠加: percentage 和 regions 共同满足（AND）,
          但 whitelist 命中时无视其他规则直接放行。
    """
    rules = flag.rules
    if not rules:
        return True  # 无规则 = 全局生效（仅受 enabled 控制）

    # ── 白名单规则（override）────────────────────────────────────
    if "whitelist" in rules and user.user_id:
        if user.user_id in rules["whitelist"]:
            return True  # 白名单用户直接放行，无视其他规则

    # ── 其他规则: 百分比 + 地域 (AND 叠加) ──────────────────────
    total_checks = 0
    passed_checks = 0

    if "percentage" in rules:
        total_checks += 1
        if user.user_id:
            h = int(hashlib.md5(user.user_id.encode()).hexdigest(), 16)
            bucket = h % 100
            if bucket < rules["percentage"]:
                passed_checks += 1

    if "regions" in rules:
        total_checks += 1
        if user.region and user.region in rules["regions"]:
            passed_checks += 1

    # 只有 whitelist 规则存在且用户不在白名单中
    if total_checks == 0:
        return False

    # AND: 所有非白名单规则必须全部通过
    return passed_checks == total_checks


# ===================================================================
# 预设默认 Flags
# ===================================================================

DEFAULT_FLAGS: list[FeatureFlag] = [
    FeatureFlag(
        name="new_matching_engine",
        description="新DNN匹配引擎开关",
        enabled=False,
        owner="匹配引擎团队",
        rules={"percentage": 10},
    ),
    FeatureFlag(
        name="cross_border",
        description="跨境匹配",
        enabled=False,
        owner="跨境业务组",
        rules={"regions": ["HK", "SG"]},
    ),
    FeatureFlag(
        name="multi_language",
        description="多语言UI",
        enabled=False,
        owner="前端团队",
        rules={"whitelist": ["tester_001", "tester_002"]},
    ),
    FeatureFlag(
        name="beta_feature",
        description="测试中功能",
        enabled=False,
        owner="产品部",
        rules={"whitelist": ["alpha_user_01", "alpha_user_02"], "percentage": 5},
    ),
]


# ===================================================================
# FeatureFlagManager
# ===================================================================


class FeatureFlagManager:
    """Feature Flags 管理器 — 基于内存 + JSON 文件持久化"""

    def __init__(self, flags_file: str = "feature_flags.json"):
        self.flags_file = flags_file
        self._flags: dict[str, FeatureFlag] = {}
        self._load()

    # ── 持久化 ──────────────────────────────────────────────────

    def _flags_path(self) -> str:
        """返回 flags 文件的绝对路径（相对于项目根目录或 CWD）"""
        if os.path.isabs(self.flags_file):
            return self.flags_file
        # 尝试相对于项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, self.flags_file)

    def _load(self) -> None:
        """从 JSON 文件加载 flags"""
        path = self._flags_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    flag = FeatureFlag(**item)
                    self._flags[flag.name] = flag
            except (json.JSONDecodeError, Exception):
                self._flags = {}
        else:
            # 首次使用：写入预设 flags（深拷贝避免外部修改）
            self._flags = {f.name: copy.deepcopy(f) for f in DEFAULT_FLAGS}
            self._save()

    def _save(self) -> None:
        """将 flags 持久化到 JSON 文件"""
        path = self._flags_path()
        data = [f.model_dump() for f in self._flags.values()]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 查询 ────────────────────────────────────────────────────

    def is_enabled(self, flag_name: str, user_context: Optional[UserContext] = None) -> bool:
        """
        判断功能开关是否开启（含灰度规则评估）。

        流程:
            1. 全局 enabled == False → 直接返回 False
            2. 评估 rules（白名单/百分比/地域 AND 叠加）
            3. 无 user_context 且存在 rules → 返回 False（安全默认）
            4. 无 user_context 且无 rules → 返回 enabled
        """
        flag = self._flags.get(flag_name)
        if flag is None:
            return False

        if not flag.enabled:
            return False

        user = user_context or UserContext()

        # 若存在规则但没有用户上下文 → 不开
        if flag.rules and not user.user_id and not user.region:
            return False

        return _evaluate_rules(flag, user)

    # ── 管理 ────────────────────────────────────────────────────

    def enable(self, flag_name: str) -> bool:
        """启用一个 flag"""
        flag = self._flags.get(flag_name)
        if flag is None:
            return False
        flag.enabled = True
        self._save()
        return True

    def disable(self, flag_name: str) -> bool:
        """禁用一个 flag"""
        flag = self._flags.get(flag_name)
        if flag is None:
            return False
        flag.enabled = False
        self._save()
        return True

    def add_flag(self, flag: FeatureFlag) -> bool:
        """添加新 flag（如果已存在则返回 False）"""
        if flag.name in self._flags:
            return False
        # 深拷贝避免外部修改泄漏到管理器中
        self._flags[flag.name] = copy.deepcopy(flag)
        self._save()
        return True

    def remove_flag(self, flag_name: str) -> bool:
        """删除一个 flag"""
        if flag_name not in self._flags:
            return False
        del self._flags[flag_name]
        self._save()
        return True

    def list_flags(self) -> list[dict[str, Any]]:
        """返回所有 flags 及状态（含简化的 enabled 标记 + rules 摘要）"""
        result = []
        for flag in self._flags.values():
            d = flag.model_dump()
            result.append(d)
        return result

    def get_flag(self, flag_name: str) -> Optional[FeatureFlag]:
        """获取单个 flag"""
        return self._flags.get(flag_name)

    def set_rule(self, flag_name: str, rule_name: str, rule_value: Any) -> bool:
        """
        设置（或覆盖）某个 flag 的一条规则。

        例如:
            manager.set_rule("new_matching_engine", "percentage", 30)
            manager.set_rule("beta_feature", "whitelist", ["u1", "u2"])
        """
        flag = self._flags.get(flag_name)
        if flag is None:
            return False
        flag.rules[rule_name] = rule_value
        self._save()
        return True


# ===================================================================
# 全局单例 + API Router
# ===================================================================

# 全局管理器实例（应用生命周期内共享）
manager = FeatureFlagManager()

# FastAPI Router
feature_flags_bp = APIRouter(prefix="/api/v1/flags", tags=["功能开关"])


# ── PUT /api/v1/flags/{name} — 请求体 ─────────────────────────────


class UpdateFlagRequest(BaseModel):
    enabled: bool


# ── GET /api/v1/flags — 查询所有 flags ─────────────────────────


@feature_flags_bp.get("")
async def list_all_flags():
    """返回所有 Feature Flags 及当前状态"""
    return {"flags": manager.list_flags(), "total": len(manager.list_flags())}


# ── GET /api/v1/flags/{name} — 查询单个 flag ─────────────────────


@feature_flags_bp.get("/{name}")
async def get_flag(name: str):
    """查询单个 Flag 详情"""
    flag = manager.get_flag(name)
    if flag is None:
        raise HTTPException(status_code=404, detail=f"Flag '{name}' not found")
    return {"flag": flag.model_dump()}


# ── PUT /api/v1/flags/{name} — 修改 flag 状态 ────────────────────


@feature_flags_bp.put("/{name}")
async def update_flag(name: str, body: UpdateFlagRequest):
    """启用或禁用一个 Flag"""
    if name not in manager._flags:
        raise HTTPException(status_code=404, detail=f"Flag '{name}' not found")
    if body.enabled:
        manager.enable(name)
    else:
        manager.disable(name)
    flag = manager.get_flag(name)
    return {"flag": flag.model_dump() if flag else None, "message": "ok"}
