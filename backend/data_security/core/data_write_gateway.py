#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据写入验证网关 (Data Write Gateway Core)
============================================
DWGC —— 5步验证流水线 + 异步降级 + 熔断 + 迁移白名单。

设计原则:
  1. 所有写入 core schema 的数据必须经过 DWG
  2. 5步验证流水线一旦失败，数据不得直接写入
  3. 熔断机制修复乘黄提出的 SPOF 质疑
  4. 迁移白名单修复墨子提出的致命缺陷#1
  5. 异常评分留 stub API 供后续集成

五步验证流水线:
  Step 1: 验证数据契约 (ContractValidator)
  Step 2: 类型清洗 + 约束检查 (强转类型、正则/enum/min/max)
  Step 3: 安全消毒 (Sanitizer: Unicode/SSRF/深度嵌套保护)
  Step 4: 异常评分 (AnomalyScorer stub — 后续集成)
  Step 5: 路由决策 (通过→write / 可疑→quarantine / 拒绝→reject)

核心接口:
    validate_and_write(module, table, data, context) -> dict

模块：向海容知識庫 · 記憶宮殿 · 数据安全层
"""

import copy
import io
import json
import os
import time
import threading
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# -----------------------------------------------------------------------
# 导入依赖模块
# -----------------------------------------------------------------------
from data_contract import (
    ContractValidator,
    ContractYAML,
    DataContractError,
    ContractValidationError,
    ContractNotFoundError,
    ContractSchemaError,
)
from sanitizer import (
    Sanitizer,
    SanitizerError,
    InjectionDetectedError,
    MaxDepthExceededError,
)

__version__ = "1.0.0"

# =======================================================================
# 配置常量
# =======================================================================

# ---- 熔断配置 ----
CIRCUIT_BREAKER_THRESHOLD: int = 10       # 连续失败次数触发熔断
CIRCUIT_BREAKER_RECOVERY: int = 300        # 熔断后尝试恢复的秒数 (5分钟)
CIRCUIT_HALF_OPEN_MAX: int = 3             # 半开状态下最多尝试次数

# ---- 降级模式 ----
DEGRADE_MODE_NORMAL: str = "normal"        # 正常模式 (走5步流水线)
DEGRADE_MODE_AUDIT_ONLY: str = "audit_only"  # 仅审计 (旁路DWG但记录)
DEGRADE_MODE_DIRECT: str = "direct"        # 直接写入 (紧急降级)

# ---- 异常评分阈值 ----
ANOMALY_SCORE_LOW: float = 30.0            # 0-30: 正常
ANOMALY_SCORE_MEDIUM: float = 60.0         # 30-60: 可疑
ANOMALY_SCORE_HIGH: float = 90.0           # 60-90: 高危
# 90-100: 拒绝

# ---- 迁移白名单前缀 ----
MIGRATION_FLAG: str = "migration"
MIGRATION_CONTEXT_KEY: str = "_dwg_mode"

# ---- 默认契约路径 ----
DEFAULT_CONTRACTS_DIR: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "contracts",
)

# =======================================================================
# 异常定义
# =======================================================================


class DataWriteGatewayError(Exception):
    """DWG 基础异常"""
    pass


class ValidationPipelineError(DataWriteGatewayError):
    """验证流水线失败"""
    def __init__(self, message: str, step: int, detail: Any = None):
        self.step = step
        self.detail = detail
        super().__init__(f"[Step {step}] {message}")


class CircuitBreakerOpenError(DataWriteGatewayError):
    """熔断器打开，写入被阻止"""
    pass


class DegradeModeError(DataWriteGatewayError):
    """降级模式错误"""
    pass


# =======================================================================
# 内部数据写入器 (DataWriter)
# =======================================================================


class _DataWriter:
    """
    内部数据写入器 —— 模拟写入目标存储。

    生产环境中应替换为真正的数据库写入器。
    当前实现仅模拟写入并根据配置决定成功/失败。
    """

    def __init__(self, fail_rate: float = 0.0):
        """
        Args:
            fail_rate: 模拟写入失败率 (0.0-1.0)
        """
        self.fail_rate = fail_rate
        self._written: List[Dict] = []
        self._lock = threading.Lock()

    def write(self, module: str, table: str, data: dict) -> Dict:
        """
        写入数据到目标存储。

        Returns:
            {"success": True, "written_at": timestamp, "id": uuid}
            或 {"success": False, "error": "..."}
        """
        import random
        if self.fail_rate > 0 and random.random() < self.fail_rate:
            return {
                "success": False,
                "error": "模拟写入失败 (fail_rate 触发)",
            }

        record = {
            "module": module,
            "table": table,
            "data": copy.deepcopy(data),
            "written_at": datetime.now(timezone.utc).isoformat(),
            "write_id": str(uuid.uuid4()),
        }
        with self._lock:
            self._written.append(record)
        return {
            "success": True,
            "written_at": record["written_at"],
            "write_id": record["write_id"],
        }

    def get_written_count(self) -> int:
        with self._lock:
            return len(self._written)


# =======================================================================
# 异常评分器 (AnomalyScorer) — Stub
# =======================================================================


class AnomalyScorer:
    """
    异常评分器 (Stub API)

    当前实现为占位版本，返回基础评分 0.0。
    后续集成计划:
      - 统计异常检测 (标准差、z-score)
      - 行为基线 (用户历史写入模式)
      - ML 模型推理 (TensorFlow / ONNX)
      - 时序异常检测 (Prophet / LSTM)
    """

    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}
        self._enabled = self._config.get("enabled", False)

    def score(
        self,
        module: str,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        计算数据的异常评分。

        Args:
            module: 模块名
            table: 表名
            data: 待评分数据 (已通过前3步清洗)
            context: 上下文信息

        Returns:
            {
                "score": float,        # 0.0-100.0
                "reasons": [str],      # 扣分原因
                "features": dict,      # 特征值 (调试用)
            }
        """
        # ---- Stub 实现 ----
        reasons: List[str] = []
        score = 0.0

        if not self._enabled:
            return {
                "score": 0.0,
                "reasons": ["scorer_disabled"],
                "features": {},
            }

        # 基础规则: 字段数量异常
        field_count = len(data)
        if field_count > 50:
            score += 20
            reasons.append(f"field_count:{field_count}>50")

        # 基础规则: 字符串长度异常
        for key, value in data.items():
            if isinstance(value, str) and len(value) > 10000:
                score = min(100, score + 10)
                reasons.append(f"long_string:{key}({len(value)})")

        # 基础规则: 深层嵌套
        depth = self._compute_depth(data)
        if depth > 6:
            score = min(100, score + 15)
            reasons.append(f"deep_nesting:{depth}>6")

        return {
            "score": min(100.0, score),
            "reasons": reasons,
            "features": {"field_count": field_count, "depth": depth},
        }

    @staticmethod
    def _compute_depth(data: Any, current: int = 0) -> int:
        """递归计算嵌套深度"""
        if isinstance(data, dict):
            if not data:
                return current + 1
            return max(
                AnomalyScorer._compute_depth(v, current + 1)
                for v in data.values()
            )
        if isinstance(data, list):
            if not data:
                return current + 1
            return max(
                AnomalyScorer._compute_depth(i, current + 1)
                for i in data
            )
        return current


# =======================================================================
# 步骤引擎 (StepEngine)
# =======================================================================


class _StepEngine:
    """
    5步验证流水线引擎。

    每步独立可执行，结果传递给下一步。
    """

    def __init__(
        self,
        contract_validator: ContractValidator,
        sanitizer: Sanitizer,
        anomaly_scorer: AnomalyScorer,
        data_writer: _DataWriter,
    ):
        self._validator = contract_validator
        self._sanitizer = sanitizer
        self._scorer = anomaly_scorer
        self._writer = data_writer

    # ------------------------------------------------------------------
    # Step 1: 验证数据契约
    # ------------------------------------------------------------------

    def step1_validate_contract(
        self,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        调用 ContractValidator 进行契约校验。

        Returns:
            {"passed": True, "cleaned": dict} or {"passed": False, "errors": [...]}
        """
        try:
            cleaned = self._validator.validate(table, data, context)
            return {"passed": True, "cleaned": cleaned}
        except ContractValidationError as e:
            return {"passed": False, "errors": e.errors, "message": str(e)}
        except (ContractNotFoundError, ContractSchemaError) as e:
            return {
                "passed": False,
                "errors": [{"field": "_contract", "message": str(e)}],
                "message": str(e),
            }

    # ------------------------------------------------------------------
    # Step 2: 类型清洗 + 约束检查
    # ------------------------------------------------------------------

    def step2_type_coerce_and_constraints(
        self,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        类型强转 + 约束二次验证。

        处理:
          - 字符串数字 → int/float 强转
          - 布尔值标准化
          - None/null 处理
          - 约束规则验证 (enum, regex, min/max 等)

        Returns:
            {"passed": True, "coerced": dict} or {"passed": False, "errors": [...]}
        """
        errors: List[Dict] = []
        coerced = {}

        # 获取契约中该表的约束定义
        try:
            contract = self._validator._contract
            table_config = contract.get_table(table)
        except Exception:
            table_config = None

        constraints = {}
        allowed_fields = []
        if table_config:
            constraints = table_config.get("constraints", {})
            allowed_fields = table_config.get("allowed_fields", [])

        for field, value in data.items():
            # 跳过内部字段
            if field.startswith("_"):
                coerced[field] = value
                continue

            # 获取该字段的约束规则
            field_rules = constraints.get(field, {})

            try:
                coerced_value = self._coerce_value(field, value, field_rules, errors)
                coerced[field] = coerced_value
            except Exception as e:
                errors.append({
                    "field": field,
                    "value": value,
                    "rule": "coerce",
                    "message": f"类型强转失败: {e}",
                })

        if errors:
            return {"passed": False, "errors": errors, "coerced": coerced}

        return {"passed": True, "coerced": coerced}

    @staticmethod
    def _coerce_value(
        field: str,
        value: Any,
        rules: Dict,
        errors: List[Dict],
    ) -> Any:
        """对单个值进行类型强转"""
        expected_type = rules.get("type", None)

        # None 值处理
        if value is None:
            if rules.get("default") is not None:
                return rules["default"]
            return None

        # 字符串 → 数字强转
        if expected_type in ("int", "integer", "float", "number"):
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    if rules.get("default") is not None:
                        return rules["default"]
                    return None
                try:
                    if expected_type in ("int", "integer"):
                        value = int(value)
                    elif expected_type == "float":
                        value = float(value)
                    else:  # number
                        value = float(value) if "." in value else int(value)
                except (ValueError, TypeError):
                    errors.append({
                        "field": field,
                        "value": value,
                        "rule": "type_coerce",
                        "message": f"无法将 '{value}' 强转为 {expected_type}",
                    })
                    return value

        # 字符串 → bool 强转
        if expected_type in ("bool", "boolean"):
            if isinstance(value, str):
                v_lower = value.strip().lower()
                if v_lower in ("true", "1", "yes", "on"):
                    value = True
                elif v_lower in ("false", "0", "no", "off"):
                    value = False

        # 数字 → 字符串强转 (约束要求regex时)
        if not isinstance(value, str) and "regex" in rules:
            value = str(value)

        # 整数 → 字符串 (当类型为string但值是int时自动转换)
        if expected_type in ("string", "str") and isinstance(value, (int, float)):
            value = str(value)

        return value

    # ------------------------------------------------------------------
    # Step 3: 安全消毒
    # ------------------------------------------------------------------

    _INJECTION_KEYWORDS = (
        "sql_injection", "xss", "json_injection",
        "ssrf_metadata", "ssrf_dangerous", "ssrf_private_ip",
    )

    def step3_sanitize(
        self,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        调用 Sanitizer 进行安全消毒。

        Returns:
            {"passed": True, "cleaned": dict, "warnings": [...]}
            or {"passed": False, "errors": [...]}
        """
        try:
            result = self._sanitizer.sanitize_with_warnings(data)
            if result.get("injection_detected"):
                return {
                    "passed": False,
                    "errors": [{
                        "field": result.get("field", "<unknown>"),
                        "rule": "injection",
                        "pattern": result.get("pattern", "unknown"),
                        "message": f"安全消毒检测到注入: {result.get('pattern', '')}",
                    }],
                }
            warnings = result.get("warnings", [])
            # 检查 warnings 中是否包含注入相关关键词
            # (sanitize_with_warnings 在 raise_on_injection=False 时
            #  不会抛异常，但 warnings 中会记录注入检测)
            critical_warnings = [
                w for w in warnings
                if any(kw in w.lower() for kw in self._INJECTION_KEYWORDS)
            ]
            if critical_warnings:
                return {
                    "passed": False,
                    "errors": [{
                        "field": "<sanitizer>",
                        "rule": "injection_detected_in_warning",
                        "message": f"消毒检测到注入: {'; '.join(critical_warnings[:3])}",
                        "warnings": critical_warnings,
                    }],
                }
            return {
                "passed": True,
                "cleaned": result.get("cleaned", data),
                "warnings": warnings,
            }
        except (InjectionDetectedError, MaxDepthExceededError) as e:
            return {
                "passed": False,
                "errors": [{
                    "field": getattr(e, "field", "<unknown>"),
                    "rule": "injection",
                    "message": str(e),
                }],
            }
        except SanitizerError as e:
            return {
                "passed": False,
                "errors": [{
                    "field": "<sanitizer>",
                    "rule": "sanitizer_error",
                    "message": str(e),
                }],
            }

    # ------------------------------------------------------------------
    # Step 4: 异常评分
    # ------------------------------------------------------------------

    def step4_anomaly_score(
        self,
        module: str,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        调用 AnomalyScorer 进行异常评分。

        Returns:
            {"passed": True, "score": float, "reasons": [...], "features": {...}}
        """
        result = self._scorer.score(module, table, data, context)
        return {
            "passed": True,
            "score": result["score"],
            "reasons": result["reasons"],
            "features": result.get("features", {}),
        }

    # ------------------------------------------------------------------
    # Step 5: 路由决策
    # ------------------------------------------------------------------

    @staticmethod
    def step5_route(
        step1_result: Dict,
        step2_result: Dict,
        step3_result: Dict,
        step4_result: Dict,
        migration_mode: bool = False,
    ) -> Dict:
        """
        根据前4步的结果做路由决策。

        决策逻辑:
          - 任何一步 failed → REJECTED
          - Step4 score >= 90 → REJECTED
          - Step4 score >= 60 → QUARANTINED
          - Step4 score >= 30 + warnings → QUARANTINED
          - 其余 → PASSED

        Returns:
            {"decision": "passed"|"quarantined"|"rejected",
             "reason": str,
             "data": dict}
        """
        # 收集所有步骤的数据
        data = step1_result.get("cleaned", {})
        if not data:
            data = step2_result.get("coerced", {})

        # Step 1-3 检查
        for step_name, step_res in [
            ("step1_contract", step1_result),
            ("step2_coerce",   step2_result),
            ("step3_sanitize", step3_result),
        ]:
            if not step_res.get("passed", False):
                errors = step_res.get("errors", [])
                error_msgs = "; ".join(
                    e.get("message", str(e)) for e in errors
                )
                return {
                    "decision": "rejected",
                    "reason": f"{step_name} 验证失败: {error_msgs}",
                    "data": data,
                }

        # Step 4 评分决策
        score = step4_result.get("score", 0.0)
        reasons = step4_result.get("reasons", [])
        warnings = step3_result.get("warnings", [])

        if score >= ANOMALY_SCORE_HIGH:
            return {
                "decision": "rejected",
                "reason": f"异常评分过高: {score:.1f}/100. {'; '.join(reasons)}",
                "data": data,
                "score": score,
            }

        if score >= ANOMALY_SCORE_MEDIUM:
            return {
                "decision": "quarantined",
                "reason": f"异常评分中等: {score:.1f}/100. {'; '.join(reasons)}",
                "data": data,
                "score": score,
            }

        if score >= ANOMALY_SCORE_LOW and warnings:
            return {
                "decision": "quarantined",
                "reason": (
                    f"异常评分偏低但含消毒警告: {score:.1f}/100. "
                    f"warnings: {len(warnings)}"
                ),
                "data": data,
                "score": score,
            }

        return {
            "decision": "passed",
            "reason": "全部验证通过",
            "data": data,
            "score": score,
        }


# =======================================================================
# 熔断器 (CircuitBreaker)
# =======================================================================


class _CircuitBreakerState:
    """熔断器的状态枚举"""
    CLOSED = "closed"         # 正常状态，请求通过
    OPEN = "open"             # 熔断打开，请求被拒绝
    HALF_OPEN = "half_open"   # 半开状态，尝试恢复


class CircuitBreaker:
    """
    熔断器 —— 连续失败达到阈值后自动降级。

    状态机:
      CLOSED → (连续失败 >= threshold) → OPEN
      OPEN → (经过 recovery_timeout) → HALF_OPEN
      HALF_OPEN → (尝试成功) → CLOSED
      HALF_OPEN → (尝试失败) → OPEN
    """

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        recovery_timeout: int = CIRCUIT_BREAKER_RECOVERY,
        half_open_max: int = CIRCUIT_HALF_OPEN_MAX,
    ):
        self._threshold = threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max

        self._state = _CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_attempts = 0
        self._lock = threading.Lock()

        # 统计
        self._total_success = 0
        self._total_failure = 0
        self._total_rejected = 0

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def is_open(self) -> bool:
        return self._state == _CircuitBreakerState.OPEN

    @property
    def can_attempt(self) -> bool:
        """检查是否允许尝试请求"""
        with self._lock:
            if self._state == _CircuitBreakerState.CLOSED:
                return True

            if self._state == _CircuitBreakerState.OPEN:
                # 检查是否达到恢复时间
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    return True  # 允许进入半开状态
                return False

            # HALF_OPEN 状态：限制尝试次数
            return self._half_open_attempts < self._half_open_max

    @property
    def stats(self) -> Dict:
        with self._lock:
            return {
                "state": self._state,
                "failure_count": self._failure_count,
                "threshold": self._threshold,
                "recovery_timeout": self._recovery_timeout,
                "total_success": self._total_success,
                "total_failure": self._total_failure,
                "total_rejected": self._total_rejected,
            }

    # ------------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------------

    def before_request(self) -> bool:
        """
        请求前调用。如果熔断器不允许请求，返回 False。
        """
        with self._lock:
            if self._state == _CircuitBreakerState.CLOSED:
                return True

            if self._state == _CircuitBreakerState.OPEN:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    # 切换到半开状态
                    self._state = _CircuitBreakerState.HALF_OPEN
                    self._half_open_attempts = 0
                    return True
                self._total_rejected += 1
                return False

            # HALF_OPEN
            if self._half_open_attempts < self._half_open_max:
                self._half_open_attempts += 1
                return True
            # 半开尝试次数用完 → 回到 OPEN
            self._state = _CircuitBreakerState.OPEN
            self._total_rejected += 1
            return False

    def on_success(self):
        """请求成功后调用"""
        with self._lock:
            self._total_success += 1
            if self._state == _CircuitBreakerState.HALF_OPEN:
                # 半开状态成功 → 关闭熔断器
                self._state = _CircuitBreakerState.CLOSED
                self._failure_count = 0
                self._half_open_attempts = 0
            elif self._state == _CircuitBreakerState.CLOSED:
                self._failure_count = 0  # 重置失败计数

    def on_failure(self):
        """请求失败后调用"""
        with self._lock:
            self._total_failure += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == _CircuitBreakerState.HALF_OPEN:
                # 半开状态失败 → 回到 OPEN
                self._state = _CircuitBreakerState.OPEN
            elif (
                self._state == _CircuitBreakerState.CLOSED
                and self._failure_count >= self._threshold
            ):
                # 达到阈值 → 打开熔断器
                self._state = _CircuitBreakerState.OPEN

    def reset(self):
        """手动重置熔断器"""
        with self._lock:
            self._state = _CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._half_open_attempts = 0


# =======================================================================
# 审计日志器 (AuditLogger)
# =======================================================================


class _AuditLogger:
    """
    审计日志器 —— 记录所有通过DWG的数据操作。

    支持内存缓冲和文件持久化两种模式。
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        buffer_size: int = 100,
    ):
        self._log_dir = log_dir
        self._buffer_size = buffer_size
        self._buffer: List[Dict] = []
        self._lock = threading.Lock()
        self._total_logged = 0

        if log_dir and not os.path.isdir(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except (IOError, OSError):
                self._log_dir = None

    def log(self, entry: Dict):
        """记录一条审计日志"""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "_seq": self._total_logged,
        }
        record.update(entry)

        with self._lock:
            self._buffer.append(record)
            self._total_logged += 1

            if len(self._buffer) >= self._buffer_size:
                self._flush()

    def _flush(self):
        """将缓冲区写入磁盘"""
        if not self._log_dir or not self._buffer:
            return

        try:
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
            log_file = os.path.join(
                self._log_dir, f"dwg_audit_{date_str}.jsonl"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._buffer.clear()
        except (IOError, OSError):
            pass  # 静默处理写入失败

    def flush(self):
        """显式刷新缓冲区到磁盘"""
        with self._lock:
            self._flush()

    def get_recent(self, limit: int = 50) -> List[Dict]:
        """获取最近的审计记录"""
        with self._lock:
            return list(self._buffer[-limit:])

    @property
    def count(self) -> int:
        return self._total_logged


# =======================================================================
# DWGC 主类
# =======================================================================


class DataWriteGateway:
    """
    数据写入验证网关 (DWGC) 主类

    5步验证流水线 + 异步降级 + 熔断 + 迁移白名单。

    使用示例:
        dwg = DataWriteGateway()
        result = dwg.validate_and_write(
            module="user_service",
            table="users",
            data={"name": "alice", "email": "alice@example.com"},
            context={"request_id": "req-123"},
        )
        if result["status"] == "passed":
            print("写入成功:", result["data"])
        elif result["status"] == "quarantined":
            print("隔离:", result["quarantine_id"])
        else:
            print("拒绝:", result["reason"])
    """

    def __init__(
        self,
        contracts_dir: Optional[str] = None,
        strict_mode: bool = True,
        sanitizer_config: Optional[Dict] = None,
        scorer_config: Optional[Dict] = None,
        circuit_breaker_config: Optional[Dict] = None,
        audit_log_dir: Optional[str] = None,
        writer_fail_rate: float = 0.0,
        migration_modes: Optional[List[str]] = None,
    ):
        """
        初始化 DWG。

        Args:
            contracts_dir: 契约文件目录 (默认: ./contracts/)
            strict_mode: 契约校验严格模式 (默认: True)
            sanitizer_config: 消毒器配置
            scorer_config: 异常评分器配置
            circuit_breaker_config: 熔断器配置
            audit_log_dir: 审计日志目录 (None=仅内存缓冲)
            writer_fail_rate: 模拟写入失败率 (用于测试熔断)
            migration_modes: 迁移模式标识列表 (默认: ["migration"])
        """
        # ---- 契约系统 ----
        self._contracts_dir = contracts_dir or DEFAULT_CONTRACTS_DIR
        self._strict_mode = strict_mode
        self._contracts_cache: Dict[str, ContractYAML] = {}

        # ---- 核心组件 ----
        self._sanitizer = Sanitizer(
            **(sanitizer_config or {}),
        )
        self._scorer = AnomalyScorer(config=scorer_config)
        self._writer = _DataWriter(fail_rate=writer_fail_rate)
        self._circuit_breaker = CircuitBreaker(
            **(circuit_breaker_config or {}),
        )
        self._audit_logger = _AuditLogger(log_dir=audit_log_dir)

        # ---- 降级模式 ----
        self._degrade_mode = DEGRADE_MODE_NORMAL
        self._degrade_mode_lock = threading.Lock()

        # ---- 迁移白名单 ----
        self._migration_modes = migration_modes or [MIGRATION_FLAG]

        # ---- 统计 ----
        self._stats_lock = threading.Lock()
        self._stats = {
            "total_requests": 0,
            "passed": 0,
            "quarantined": 0,
            "rejected": 0,
            "degraded": 0,
            "circuit_broken": 0,
            "migration_passed": 0,
        }

        # ---- 内部流水线引擎 ----
        self._step_engine: Optional[_StepEngine] = None

    # ------------------------------------------------------------------
    # 契约加载
    # ------------------------------------------------------------------

    def _get_contract(self, module: str) -> ContractYAML:
        """获取模块的契约（带缓存）"""
        if module in self._contracts_cache:
            return self._contracts_cache[module]

        # 尝试多个路径加载契约
        search_paths = [
            os.path.join(self._contracts_dir, f"{module}.yaml"),
            os.path.join(self._contracts_dir, f"{module}.yml"),
            os.path.join(self._contracts_dir, module, "contract.yaml"),
            os.path.join(self._contracts_dir, module, "contract.yml"),
        ]

        for path in search_paths:
            if os.path.isfile(path):
                contract = ContractYAML(path)
                self._contracts_cache[module] = contract
                return contract

        raise ContractNotFoundError(
            f"模块 '{module}' 的契约文件未找到"
            f" (搜索路径: {self._contracts_dir})"
        )

    def _get_validator(self, module: str) -> ContractValidator:
        """获取模块的契约校验器"""
        contract = self._get_contract(module)
        return ContractValidator(contract, strict_mode=self._strict_mode)

    def _ensure_step_engine(self, module: str) -> _StepEngine:
        """确保步骤引擎已初始化"""
        if self._step_engine is None:
            validator = self._get_validator(module)
            self._step_engine = _StepEngine(
                contract_validator=validator,
                sanitizer=self._sanitizer,
                anomaly_scorer=self._scorer,
                data_writer=self._writer,
            )
        return self._step_engine

    # ------------------------------------------------------------------
    # 降解模式管理
    # ------------------------------------------------------------------

    @property
    def degrade_mode(self) -> str:
        return self._degrade_mode

    def set_degrade_mode(self, mode: str):
        """
        设置降级模式。

        Args:
            mode: "normal" | "audit_only" | "direct"
        """
        if mode not in (DEGRADE_MODE_NORMAL, DEGRADE_MODE_AUDIT_ONLY, DEGRADE_MODE_DIRECT):
            raise DegradeModeError(f"不支持的降级模式: {mode}")
        with self._degrade_mode_lock:
            old = self._degrade_mode
            self._degrade_mode = mode

    def _check_degrade_mode(self) -> str:
        """检查当前降级模式"""
        with self._degrade_mode_lock:
            return self._degrade_mode

    # ------------------------------------------------------------------
    # 迁移白名单检查
    # ------------------------------------------------------------------

    def _is_migration(self, context: Optional[Dict]) -> bool:
        """检查请求是否来自迁移脚本"""
        if not context:
            return False
        mode = context.get(MIGRATION_CONTEXT_KEY, "")
        return mode in self._migration_modes

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def validate_and_write(
        self,
        module: str,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        5步验证流水线主入口。

        Args:
            module: 模块名 (用于加载契约)
            table: 表名
            data: 待写入的数据字典
            context: 上下文信息。
                    迁移脚本需传入 {"_dwg_mode": "migration"}。
                    支持字段: request_id, user_id, source_ip 等。

        Returns:
            {
                "status": "passed" | "quarantined" | "rejected",
                "data": ...,         # 通过时返回清洗后的数据
                "reason": ...,       # 拒绝或隔离原因
                "quarantine_id": ..., # 隔离时的ID
                "score": float,      # 异常评分
                "degraded": bool,    # 是否走降级通路
            }
        """
        context = context or {}
        is_migration = self._is_migration(context)
        request_id = context.get("request_id", str(uuid.uuid4()))

        # ---- 更新统计 ----
        with self._stats_lock:
            self._stats["total_requests"] += 1

        # ---- 检查降级模式 ----
        degrade_mode = self._check_degrade_mode()
        if degrade_mode != DEGRADE_MODE_NORMAL:
            return self._degraded_write(
                module=module,
                table=table,
                data=data,
                context=context,
                degrade_mode=degrade_mode,
                is_migration=is_migration,
                request_id=request_id,
            )

        # ---- 检查熔断器 ----
        if not self._circuit_breaker.before_request():
            with self._stats_lock:
                self._stats["circuit_broken"] += 1
            # 熔断器打开 → 自动降级为 audit_only
            return self._degraded_write(
                module=module,
                table=table,
                data=data,
                context=context,
                degrade_mode=DEGRADE_MODE_AUDIT_ONLY,
                is_migration=is_migration,
                request_id=request_id,
                circuit_broken=True,
            )

        # ---- 执行5步流水线 ----
        try:
            result = self._run_pipeline(
                module=module,
                table=table,
                data=data,
                context=context,
                is_migration=is_migration,
                request_id=request_id,
            )
        except Exception as e:
            # 流水线内部异常 → 记录失败
            self._circuit_breaker.on_failure()
            self._audit_logger.log({
                "event": "pipeline_error",
                "module": module,
                "table": table,
                "request_id": request_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "migration": is_migration,
            })
            return {
                "status": "rejected",
                "reason": f"流水线内部错误: {e}",
                "data": data,
                "score": 0.0,
                "degraded": False,
            }

        # ---- 路由决策后的处理 ----
        decision = result.get("decision", "rejected")
        pipeline_data = result.get("data", data)
        score = result.get("score", 0.0)
        reason = result.get("reason", "")

        if decision == "passed":
            # 写入目标存储
            write_result = self._writer.write(module, table, pipeline_data)
            if write_result.get("success"):
                self._circuit_breaker.on_success()
                with self._stats_lock:
                    self._stats["passed"] += 1
                    if is_migration:
                        self._stats["migration_passed"] += 1
                self._audit_logger.log({
                    "event": "write_success",
                    "module": module,
                    "table": table,
                    "request_id": request_id,
                    "score": score,
                    "write_id": write_result.get("write_id"),
                    "migration": is_migration,
                    "degraded": False,
                })
                return {
                    "status": "passed",
                    "data": pipeline_data,
                    "reason": reason,
                    "score": score,
                    "quarantine_id": None,
                    "degraded": False,
                    "write_id": write_result.get("write_id"),
                }
            else:
                # 写入失败
                self._circuit_breaker.on_failure()
                with self._stats_lock:
                    self._stats["rejected"] += 1
                self._audit_logger.log({
                    "event": "write_failed",
                    "module": module,
                    "table": table,
                    "request_id": request_id,
                    "error": write_result.get("error", "unknown"),
                    "migration": is_migration,
                })
                return {
                    "status": "rejected",
                    "reason": f"写入失败: {write_result.get('error', 'unknown')}",
                    "data": pipeline_data,
                    "score": score,
                    "degraded": False,
                }

        elif decision == "quarantined":
            quarantine_id = str(uuid.uuid4())
            self._circuit_breaker.on_success()  # 隔离不算写入失败
            with self._stats_lock:
                self._stats["quarantined"] += 1
            self._audit_logger.log({
                "event": "quarantined",
                "module": module,
                "table": table,
                "request_id": request_id,
                "quarantine_id": quarantine_id,
                "score": score,
                "reason": reason,
                "migration": is_migration,
            })
            return {
                "status": "quarantined",
                "data": pipeline_data,
                "reason": reason,
                "score": score,
                "quarantine_id": quarantine_id,
                "degraded": False,
            }

        else:  # rejected
            self._circuit_breaker.on_success()  # 验证拒绝不算写入失败
            with self._stats_lock:
                self._stats["rejected"] += 1
            self._audit_logger.log({
                "event": "rejected",
                "module": module,
                "table": table,
                "request_id": request_id,
                "score": score,
                "reason": reason,
                "migration": is_migration,
            })
            return {
                "status": "rejected",
                "data": pipeline_data,
                "reason": reason,
                "score": score,
                "quarantine_id": None,
                "degraded": False,
            }

    # ------------------------------------------------------------------
    # 降级写入通路
    # ------------------------------------------------------------------

    def _degraded_write(
        self,
        module: str,
        table: str,
        data: dict,
        context: Dict,
        degrade_mode: str,
        is_migration: bool,
        request_id: str,
        circuit_broken: bool = False,
    ) -> Dict:
        """
        降级写入通路。

        audit_only: 跳过验证直接写入，但记录完整审计日志
        direct: 跳过所有验证和审计，仅写入
        """
        with self._stats_lock:
            self._stats["degraded"] += 1

        if degrade_mode == DEGRADE_MODE_DIRECT:
            # 极速降级: 直接写入，不审计
            write_result = self._writer.write(module, table, data)
            if write_result.get("success"):
                return {
                    "status": "passed",
                    "data": data,
                    "reason": "DIRECT degrade mode: 旁路所有验证",
                    "score": 0.0,
                    "quarantine_id": None,
                    "degraded": True,
                    "write_id": write_result.get("write_id"),
                }
            return {
                "status": "rejected",
                "data": data,
                "reason": f"降级写入失败: {write_result.get('error', 'unknown')}",
                "score": 0.0,
                "degraded": True,
            }

        # audit_only: 跳过验证但写审计
        audit_entry = {
            "event": "degraded_write",
            "module": module,
            "table": table,
            "request_id": request_id,
            "degrade_mode": degrade_mode,
            "circuit_broken": circuit_broken,
            "migration": is_migration,
            "data_snapshot": json.dumps(data, ensure_ascii=False, default=str)[:2000],
        }

        # 尝试执行最小验证 (仅contract check)
        try:
            validator = self._get_validator(module)
            cleaned = validator.validate(table, copy.deepcopy(data), context)
            audit_entry["contract_passed"] = True
        except ContractValidationError as e:
            audit_entry["contract_passed"] = False
            audit_entry["contract_errors"] = str(e)
            cleaned = data  # 降级模式下仍然写入，但标注
        except Exception as e:
            audit_entry["contract_passed"] = False
            audit_entry["contract_errors"] = str(e)
            cleaned = data

        # 写入
        write_result = self._writer.write(module, table, cleaned)
        audit_entry["write_success"] = write_result.get("success", False)
        audit_entry["write_id"] = write_result.get("write_id")
        self._audit_logger.log(audit_entry)

        if write_result.get("success"):
            with self._stats_lock:
                self._stats["passed"] += 1
            return {
                "status": "passed",
                "data": cleaned,
                "reason": f"{degrade_mode} degrade mode: 跳过完整流水线",
                "score": 0.0,
                "quarantine_id": None,
                "degraded": True,
                "write_id": write_result.get("write_id"),
            }

        self._circuit_breaker.on_failure()
        return {
            "status": "rejected",
            "data": cleaned,
            "reason": f"降级写入失败: {write_result.get('error', 'unknown')}",
            "score": 0.0,
            "degraded": True,
        }

    # ------------------------------------------------------------------
    # 内部流水线执行
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        module: str,
        table: str,
        data: dict,
        context: Dict,
        is_migration: bool,
        request_id: str,
    ) -> Dict:
        """
        执行5步验证流水线。

        Returns:
            {"decision": ..., "data": ..., "score": ..., "reason": ...}
        """
        data_copy = copy.deepcopy(data)
        engine = self._ensure_step_engine(module)

        # ---- Step 1: 验证数据契约 ----
        step1_result = engine.step1_validate_contract(table, data_copy, context)
        if not step1_result.get("passed", False):
            return _StepEngine.step5_route(
                step1_result, {}, {}, {}, migration_mode=is_migration,
            )

        step1_data = step1_result.get("cleaned", data_copy)

        # ---- Step 2: 类型清洗 + 约束检查 ----
        step2_result = engine.step2_type_coerce_and_constraints(
            table, step1_data, context,
        )
        if not step2_result.get("passed", False):
            return _StepEngine.step5_route(
                step1_result, step2_result, {}, {}, migration_mode=is_migration,
            )

        step2_data = step2_result.get("coerced", step1_data)

        # ---- Step 3: 安全消毒 ----
        step3_result = engine.step3_sanitize(table, step2_data, context)
        if not step3_result.get("passed", False):
            return _StepEngine.step5_route(
                step1_result, step2_result, step3_result, {},
                migration_mode=is_migration,
            )

        step3_data = step3_result.get("cleaned", step2_data)

        # ---- Step 4: 异常评分 ----
        step4_result = engine.step4_anomaly_score(
            module, table, step3_data, context,
        )

        # ---- Step 5: 路由决策 ----
        return _StepEngine.step5_route(
            step1_result, step2_result, step3_result, step4_result,
            migration_mode=is_migration,
        )

    # ------------------------------------------------------------------
    # 统计接口
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """
        获取DWG运行统计。

        Returns:
            {
                "total_requests": int,
                "passed": int,        # 通过
                "quarantined": int,   # 隔离
                "rejected": int,      # 拒绝
                "degraded": int,      # 降级
                "circuit_broken": int, # 熔断触发次数
                "migration_passed": int, # 迁移通过数
                "circuit_breaker": {...},  # 熔断器状态
                "degrade_mode": str,
                "audit_log_count": int,
                "written_count": int,
            }
        """
        with self._stats_lock:
            stats = dict(self._stats)

        stats["circuit_breaker"] = self._circuit_breaker.stats
        stats["degrade_mode"] = self._degrade_mode
        stats["audit_log_count"] = self._audit_logger.count
        stats["written_count"] = self._writer.get_written_count()
        return stats

    def reset_stats(self):
        """重置统计计数器 (熔断器状态不受影响)"""
        with self._stats_lock:
            self._stats = {
                "total_requests": 0,
                "passed": 0,
                "quarantined": 0,
                "rejected": 0,
                "degraded": 0,
                "circuit_broken": 0,
                "migration_passed": 0,
            }

    # ------------------------------------------------------------------
    # 契约热加载
    # ------------------------------------------------------------------

    def reload_contract(self, module: str) -> bool:
        """
        热加载指定模块的契约。

        Returns:
            是否成功重新加载
        """
        try:
            contract = ContractYAML(
                os.path.join(self._contracts_dir, f"{module}.yaml")
            )
            self._contracts_cache[module] = contract
            # 重置步骤引擎 (下次请求时重新创建)
            self._step_engine = None
            return True
        except Exception:
            return False

    def clear_contract_cache(self):
        """清除所有契约缓存"""
        self._contracts_cache.clear()
        self._step_engine = None


# =======================================================================
# 便利函数
# =======================================================================

_DEFAULT_GATEWAY: Optional[DataWriteGateway] = None
_DEFAULT_GATEWAY_LOCK = threading.Lock()


def get_default_gateway() -> DataWriteGateway:
    """
    获取默认的全局 DWG 实例 (单例)。
    """
    global _DEFAULT_GATEWAY
    if _DEFAULT_GATEWAY is None:
        with _DEFAULT_GATEWAY_LOCK:
            if _DEFAULT_GATEWAY is None:
                _DEFAULT_GATEWAY = DataWriteGateway()
    return _DEFAULT_GATEWAY


def validate_and_write(
    module: str,
    table: str,
    data: dict,
    context: Optional[Dict] = None,
) -> Dict:
    """
    便利函数：使用默认 DWG 实例执行写入验证。

    等同于 DataWriteGateway().validate_and_write(module, table, data, context)
    """
    return get_default_gateway().validate_and_write(module, table, data, context)


# =======================================================================
# 自测
# =======================================================================


def _demo():
    """快速演示 DWG 功能"""
    print("=" * 70)
    print(f"  DWGC v{__version__} - 数据写入验证网关 演示")
    print("=" * 70)

    # 创建测试数据目录
    test_dir = os.path.join(os.path.dirname(__file__), "..", "tests")
    os.makedirs(test_dir, exist_ok=True)

    # 创建临时契约文件
    contract_yaml = """\
module: demo_module
version: "1.0"
description: "演示用契约"
tables:
  - name: users
    description: "用户表"
    allowed_fields:
      - name
      - email
      - age
      - role
      - status
    required:
      - name
      - email
    constraints:
      name:
        type: string
        max_length: 100
        min_length: 1
      email:
        type: string
        regex: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\\\.[a-zA-Z]{2,}$"
        max_length: 200
      age:
        type: integer
        min: 0
        max: 150
      role:
        type: string
        enum: ["admin", "user", "guest", "moderator"]
      status:
        type: string
        enum: ["active", "inactive", "banned"]
"""
    contract_path = os.path.join(test_dir, "demo_module.yaml")
    with open(contract_path, "w", encoding="utf-8") as f:
        f.write(contract_yaml)

    # 初始化 DWG
    dwg = DataWriteGateway(
        contracts_dir=test_dir,
        strict_mode=True,
    )

    # ---- 测试用例 ----
    test_cases = [
        ("PASS - 正常数据", "users", {
            "name": "Alice",
            "email": "alice@example.com",
            "age": 30,
            "role": "user",
            "status": "active",
        }),
        ("PASS - 迁移模式", "users", {
            "name": "Bob",
            "email": "bob@example.com",
            "age": 25,
            "role": "admin",
            "status": "active",
        }, {"_dwg_mode": "migration"}),
        ("QUARANTINE - SQL注入", "users", {
            "name": "admin' OR 1=1 --",
            "email": "evil@example.com",
            "role": "user",
            "status": "active",
        }),
        ("REJECT - 缺少必需字段", "users", {
            "email": "no-name@example.com",
            "role": "user",
        }),
        ("REJECT - 错误的email格式", "users", {
            "name": "Bad Email",
            "email": "not-an-email",
            "role": "user",
        }),
        ("REJECT - 枚举值无效", "users", {
            "name": "Hacker",
            "email": "hacker@example.com",
            "role": "superadmin",
            "status": "active",
        }),
        ("REJECT - 年龄超出范围", "users", {
            "name": "Old Man",
            "email": "old@example.com",
            "age": 200,
            "role": "user",
        }),
        ("QUARANTINE - SSRF尝试", "users", {
            "name": "SSRF Attack",
            "email": "http://169.254.169.254/latest/meta-data/",
            "role": "user",
        }),
    ]

    for case in test_cases:
        label = case[0]
        table = case[1]
        data = case[2]
        ctx = case[3] if len(case) > 3 else {}

        print(f"\n{'─' * 70}")
        print(f">>> {label}")
        print(f"    表: {table}")
        print(f"    数据: {json.dumps(data, ensure_ascii=False)[:80]}")

        result = dwg.validate_and_write("demo_module", table, data, ctx)
        status = result["status"]
        reason = result.get("reason", "")

        if status == "passed":
            print(f"  ✓ PASSED | score={result.get('score', 0):.1f}")
            if result.get("degraded"):
                print(f"    (降级模式: {dwg.degrade_mode})")
        elif status == "quarantined":
            print(f"  ⚠ QUARANTINED | id={result.get('quarantine_id', '')[:8]}...")
            print(f"    原因: {reason[:100]}")
        else:
            print(f"  ✗ REJECTED")
            print(f"    原因: {reason[:120]}")

    # ---- 测试统计 ----
    print(f"\n{'=' * 70}")
    print("  统计:")
    stats = dwg.get_stats()
    for key, value in stats.items():
        if key != "circuit_breaker":
            print(f"    {key}: {value}")

    print(f"\n  熔断器状态: {stats.get('circuit_breaker', {}).get('state')}")

    # ---- 测试熔断 ----
    print(f"\n{'=' * 70}")
    print("  熔断测试 (连续写入失败触发熔断):")
    fail_dwg = DataWriteGateway(
        contracts_dir=test_dir,
        writer_fail_rate=1.0,  # 100% 失败率
        circuit_breaker_config={"threshold": 3, "recovery_timeout": 60},
    )
    for i in range(5):
        res = fail_dwg.validate_and_write(
            "demo_module", "users", test_cases[0][2], {},
        )
        cb = fail_dwg.get_stats()["circuit_breaker"]
        print(f"    第{i+1}次: state={cb['state']}, failures={cb['failure_count']}")

    # ---- 测试降级 ----
    print(f"\n{'=' * 70}")
    print("  降级模式测试:")
    dwg.set_degrade_mode("audit_only")
    res = dwg.validate_and_write(
        "demo_module", "users", test_cases[0][2], {},
    )
    print(f"    audit_only 模式: status={res['status']}, degraded={res['degraded']}")

    dwg.set_degrade_mode("direct")
    res = dwg.validate_and_write(
        "demo_module", "users", test_cases[0][2], {},
    )
    print(f"    direct 模式: status={res['status']}, degraded={res['degraded']}")

    dwg.set_degrade_mode("normal")

    # 清理测试文件
    try:
        os.remove(contract_path)
    except (IOError, OSError):
        pass

    print(f"\n{'=' * 70}")
    print("  演示完毕")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    _demo()
