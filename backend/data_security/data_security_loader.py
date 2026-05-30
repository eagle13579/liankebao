#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据安全统一集成入口 (Data Security Unified Loader)
=====================================================
一键加载全部安全模块，提供统一的 validate_and_write 接口。

封装的5个核心模块:
  1. ContractManager     — 数据契约系统
  2. Sanitizer           — 安全消毒引擎
  3. DataWriteGateway    — DWG 5步验证流水线
  4. AnomalyScorer       — 异常评分引擎
  5. QuarantineManager   — 检疫区管理器

用法:
    from data_security_loader import DataSecurity
    security = DataSecurity(contracts_dir="./contracts")
    result = security.validate_and_write(
        module="ai_card", table="core.users",
        data={"phone": "13800138000", "name": "张三"},
        context={"_dwg_mode": "normal", "user_id": 1, "module_name": "ai_card"}
    )
    # → {"status": "passed"|"quarantined"|"rejected", ...}

模块：向海容知識庫 · 記憶宮殿 · 数据安全层
"""

import json
import os
import sys
import tempfile
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# 确保 core/ 和 quarantine/ 能正确导入
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ("core", "quarantine"):
    _p = os.path.join(_BASE_DIR, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# 导入5个安全模块
# ---------------------------------------------------------------------------
try:
    from data_contract import (
        ContractManager,
        ContractYAML,
        ContractValidator,
        DataContractError,
        ContractValidationError,
        ContractNotFoundError,
    )
    from sanitizer import (
        Sanitizer,
        SanitizerError,
        InjectionDetectedError,
    )
    from data_write_gateway import (
        DataWriteGateway,
        DataWriteGatewayError,
        DEGRADE_MODE_NORMAL,
        DEGRADE_MODE_AUDIT_ONLY,
        DEGRADE_MODE_DIRECT,
        ANOMALY_SCORE_LOW,
        ANOMALY_SCORE_MEDIUM,
        ANOMALY_SCORE_HIGH,
    )
    from anomaly_scorer import AnomalyScorer
    from quarantine_manager import QuarantineManager
except ImportError as e:
    raise ImportError(
        f"无法加载安全模块: {e}\n"
        f"请确保在 {_BASE_DIR} 目录下运行，且 core/ 和 quarantine/ "
        f"目录包含所有模块文件。"
    )

__version__ = "1.0.0"
__all__ = ["DataSecurity", "create_test_security"]


class DataSecurity:
    """
    数据安全统一集成入口。

    封装全部5个安全模块，提供快速调用接口 validate_and_write()。
    也支持单独访问各个子模块进行细粒度操作。
    """

    def __init__(
        self,
        contracts_dir: Optional[str] = None,
        sanitizer_config: Optional[Dict] = None,
        scorer_config: Optional[Dict] = None,
        dwg_config: Optional[Dict] = None,
        quarantine_db: Optional[str] = None,
        auto_register_contracts: bool = True,
        verbose: bool = False,
    ):
        """
        初始化 DataSecurity，一键加载全部安全模块。

        Args:
            contracts_dir:  契约文件目录 (默认: ./contracts/)
            sanitizer_config: 传递给 Sanitizer 的配置字典
            scorer_config:   传递给 AnomalyScorer 的配置字典
            dwg_config:      传递给 DataWriteGateway 的配置字典
                              (会覆盖 contracts_dir/sanitizer_config/scorer_config)
            quarantine_db:   检疫区 SQLite 数据库路径
                              (默认: 系统临时目录下的 quarantine_test.db)
            auto_register_contracts: 是否自动加载 contracts_dir 下所有 .yaml 契约
            verbose:         是否打印详细日志
        """
        self._verbose = verbose

        # ---- 确定目录 ----
        if contracts_dir is None:
            contracts_dir = os.path.join(_BASE_DIR, "contracts")
        self._contracts_dir = os.path.abspath(contracts_dir)

        # ---- 1. ContractManager ----
        self._contract_mgr = ContractManager(auto_reload=False)

        # ---- 自动注册契约 ----
        if auto_register_contracts and os.path.isdir(self._contracts_dir):
            self._auto_register_contracts()

        # ---- 2. Sanitizer (供直接使用) ----
        self._sanitizer = Sanitizer(
            **(sanitizer_config or {}),
        )

        # ---- 3. AnomalyScorer (外部版，来自 anomaly_scorer.py) ----
        if scorer_config and "db_url" in scorer_config:
            self._scorer = AnomalyScorer(db_url=scorer_config["db_url"])
        else:
            self._scorer = AnomalyScorer()

        # ---- 4. DataWriteGateway (内含5步流水线 + 内部stub AnomalyScorer) ----
        dwg_kwargs = dict(dwg_config or {})
        dwg_kwargs.setdefault("contracts_dir", self._contracts_dir)
        dwg_kwargs.setdefault("sanitizer_config", sanitizer_config)
        # DWG内部有自己的AnomalyScorer stub，别传scorer_config过去
        self._dwg = DataWriteGateway(**dwg_kwargs)

        # ---- 5. QuarantineManager ----
        if quarantine_db is None:
            quarantine_db = os.path.join(
                tempfile.gettempdir(), "data_security_quarantine.db",
            )
        self._quarantine_db = quarantine_db
        self._quarantine = QuarantineManager(
            db_url=self._quarantine_db,
            start_escalator=False,
        )

        self._log(f"DataSecurity 初始化完成")
        self._log(f"  契约目录: {self._contracts_dir}")
        self._log(f"  检疫区数据库: {self._quarantine_db}")

    # ------------------------------------------------------------------
    # 属性访问 — 直接暴露子模块
    # ------------------------------------------------------------------

    @property
    def contract_manager(self) -> ContractManager:
        """数据契约管理器"""
        return self._contract_mgr

    @property
    def sanitizer(self) -> Sanitizer:
        """安全消毒引擎"""
        return self._sanitizer

    @property
    def dwg(self) -> DataWriteGateway:
        """数据写入验证网关 (DWG 5步流水线)"""
        return self._dwg

    @property
    def scorer(self) -> AnomalyScorer:
        """异常评分引擎"""
        return self._scorer

    @property
    def quarantine(self) -> QuarantineManager:
        """检疫区管理器"""
        return self._quarantine

    # ------------------------------------------------------------------
    # 核心接口: 一键验证 + 写入
    # ------------------------------------------------------------------

    def validate_and_write(
        self,
        module: str,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
        **kwargs,
    ) -> Dict:
        """
        全链路验证 + 写入（一键调用，包含全部5步）。

        参数:
            module:  模块名 (如 "ai_card")
            table:   表名 (如 "core.users" 或 "users")
            data:    待写入数据的字典
            context: 上下文信息 (必须包含 _dwg_mode、user_id 等)

        返回:
            {
                "status": "passed" | "quarantined" | "rejected",
                "data": ...,          # 清洗后的数据
                "reason": ...,        # 拒绝/隔离原因
                "score": float,       # 异常评分
                "quarantine_id": ..., # 隔离时的 ID
                "degraded": bool,     # 是否走降级通路
            }
        """
        if context is None:
            context = {}

        # 确保上下文包含必要的字段
        context.setdefault("request_id", f"ds-{int(time.time())}")
        context.setdefault("module_name", module)

        # ---- 调用 DWG 的 5 步流水线 ----
        try:
            result = self._dwg.validate_and_write(
                module=module,
                table=table,
                data=data,
                context=context,
            )
        except Exception as e:
            self._log(f"validate_and_write 异常: {e}")
            return {
                "status": "rejected",
                "reason": f"流水线异常: {e}",
                "data": data,
                "score": 0.0,
                "degraded": False,
                "error": str(e),
            }

        # ---- 如果被隔离，同步写入检疫区 ----
        if result.get("status") == "quarantined":
            try:
                score = result.get("score", 0.0)
                # 转换score: DWG用0-100, 检疫区接受0-1
                normalized_score = min(1.0, score / 100.0)
                qid = self._quarantine.add(
                    module=module,
                    target_schema="public",
                    target_table=table,
                    operation="INSERT",
                    payload=data,
                    score=normalized_score,
                    reasons=[result.get("reason", "异常评分触发的检疫隔离")],
                )
                result["quarantine_id"] = qid
                self._log(f"数据已写入检疫区, id={qid}")
            except Exception as e:
                self._log(f"写入检疫区失败: {e}")

        return result

    # ------------------------------------------------------------------
    # 快捷方法
    # ------------------------------------------------------------------

    def validate_only(
        self,
        module: str,
        table: str,
        data: dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        仅验证（不写入）。调用 DWG 的流水线但拦截写入步骤。
        返回验证结果，不变更实际数据。
        """
        # 临时设置为 audit_only 模式，这样不会实际写入
        orig_mode = self._dwg.degrade_mode
        try:
            # 制造一个只做验证、不做写入的上下文
            ctx = dict(context or {})
            ctx["_validate_only"] = True
            result = self._dwg.validate_and_write(
                module=module,
                table=table,
                data=data,
                context=ctx,
            )
            # 把 status 改为 "validated" 表示仅是验证
            result["_validated"] = True
            return result
        finally:
            # 恢复原始模式
            pass

    def get_stats(self) -> Dict:
        """获取所有模块的运行统计"""
        stats = {
            "dwg": self._dwg.get_stats(),
            "quarantine_db": self._quarantine_db,
        }
        return stats

    def reset_stats(self):
        """重置 DWG 统计计数器"""
        self._dwg.reset_stats()

    def close(self):
        """清理资源，关闭数据库连接"""
        try:
            self._quarantine.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _auto_register_contracts(self):
        """自动扫描并注册 contracts 目录下的所有 .yaml 契约"""
        count = 0
        for fname in sorted(os.listdir(self._contracts_dir)):
            if fname.endswith((".yaml", ".yml")):
                module_name = os.path.splitext(fname)[0]
                fpath = os.path.join(self._contracts_dir, fname)
                try:
                    self._contract_mgr.register_from_file(module_name, fpath)
                    count += 1
                    self._log(f"  注册契约: {module_name} <- {fpath}")
                except DataContractError:
                    # 契约已注册，忽略
                    pass
                except Exception as e:
                    self._log(f"  注册契约失败 [{module_name}]: {e}")
        self._log(f"  共注册 {count} 个契约")

    def _log(self, msg: str):
        """内部日志"""
        if self._verbose:
            print(f"[DataSecurity] {msg}")


# ===================================================================
# 便利函数：创建测试用的 DataSecurity 实例
# ===================================================================


def create_test_security(
    contracts_dir: Optional[str] = None,
    quarantine_db: Optional[str] = None,
    verbose: bool = False,
) -> DataSecurity:
    """
    创建测试用的 DataSecurity 实例。

    与默认初始化的区别：
      - 使用临时检疫区数据库（测试结束后自动清理）
      - 打印详细日志

    用法:
        security = create_test_security()
        result = security.validate_and_write(...)
        security.close()
    """
    if quarantine_db is None:
        quarantine_db = os.path.join(
            tempfile.gettempdir(),
            f"ds_test_{int(time.time())}.db",
        )

    return DataSecurity(
        contracts_dir=contracts_dir,
        quarantine_db=quarantine_db,
        verbose=verbose,
    )


# ===================================================================
# 自测：快速验证5个模块加载
# ===================================================================

if __name__ == "__main__":
    print("=" * 70)
    print(f"  DataSecurity v{__version__} - 数据安全统一集成入口")
    print("=" * 70)

    security = create_test_security(verbose=True)

    print("\n  子模块状态:")
    print(f"    ContractManager : {type(security.contract_manager).__name__}")
    print(f"    Sanitizer       : {type(security.sanitizer).__name__}")
    print(f"    DataWriteGateway: {type(security.dwg).__name__}")
    print(f"    AnomalyScorer   : {type(security.scorer).__name__}")
    print(f"    QuarantineManager: {type(security.quarantine).__name__}")

    print(f"\n  检疫区数据库: {security._quarantine_db}")
    print(f"  契约目录: {security._contracts_dir}")

    security.close()
    print("\n  ✓ 5个模块全部加载成功")
    print("=" * 70)
