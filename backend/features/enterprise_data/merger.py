"""
链客宝 - 企业数据合并引擎
==========================
合并天眼查 + 企查查数据为统一企业画像。

合并策略：
┌──────────────────┬──────────────────────┬──────────────────────┐
│ 字段              │ 来源优先级           │ 补充来源             │
├──────────────────┼──────────────────────┼──────────────────────┤
│ 工商信息          │ 天眼查 (主)          │ 企查查 (备)          │
│ 信用/风险         │ 企查查 (主)          │ 天眼查 (备)          │
│ 知识产权          │ 企查查 (唯一)        │ —                    │
│ 财务/经营异常     │ 企查查 (唯一)        │ —                    │
└──────────────────┴──────────────────────┴──────────────────────┘

设计原则：
1. 同名企业去重（严格匹配企业名称）
2. 天眼查优先填充工商字段，企查查补充信用/知产字段
3. 所有合并均不抛出异常，失败返回 None
4. 保留原始数据快照（raw_data_tyc / raw_data_qcc）

快速开始:
    from backend.features.enterprise_data import EnterpriseDataMerger

    merger = EnterpriseDataMerger()
    profile = merger.merge("阿里巴巴")
    if profile:
        print(profile.legal_person, profile.risk_count)
"""

import logging
from typing import Any, Optional

from .tianyancha_adapter import EnterpriseInfo, TianyanchaAdapter
from .qichacha_adapter import QichachaAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 字段合并优先级配置
# ---------------------------------------------------------------------------

# 天眼查优先字段（工商核心数据）
_TYC_PRIORITY_FIELDS = [
    "company_name",
    "credit_code",
    "legal_person",
    "reg_capital",
    "reg_status",
    "established_date",
    "company_type",
    "address",
    "business_scope",
    "phone",
    "email",
]

# 企查查优先字段（信用/风险/知产）
_QCC_PRIORITY_FIELDS = [
    "business_status_detail",
    "risk_count",
]

# 只从企查查提取的字段（天眼查不提供）
_QCC_ONLY_FIELDS = [
    "abnormal_records",
    "ip_list",
]


def _safe_str(value: Any) -> str:
    """安全转为非空字符串，None / 空字符串返回空串"""
    if value is None:
        return ""
    s = str(value).strip()
    return s


# ---------------------------------------------------------------------------
# 企业数据合并器
# ---------------------------------------------------------------------------


class EnterpriseDataMerger:
    """企业数据合并引擎

    整合天眼查与企查查两家数据源，根据字段优先级策略，
    生成统一的、尽可能完整的企业画像。

    Usage:
        merger = EnterpriseDataMerger()
        profile = merger.merge("阿里巴巴")

        # 可自定义适配器实例
        merger = EnterpriseDataMerger(
            tyc_adapter=my_tyc_adapter,
            qcc_adapter=my_qcc_adapter,
        )
    """

    def __init__(
        self,
        tyc_adapter: Optional[TianyanchaAdapter] = None,
        qcc_adapter: Optional[QichachaAdapter] = None,
    ) -> None:
        """初始化合并引擎

        Args:
            tyc_adapter: 天眼查适配器实例，不传则创建默认实例
            qcc_adapter: 企查查适配器实例，不传则创建默认实例
        """
        self._tyc = tyc_adapter or TianyanchaAdapter()
        self._qcc = qcc_adapter or QichachaAdapter()

        if self._tyc.is_mock_mode and self._qcc.is_mock_mode:
            logger.info(
                "企业数据合并引擎: 双模拟模式 "
                "(天眼查+企查查均未配置 API Key)"
            )
        elif self._tyc.is_mock_mode:
            logger.info(
                "企业数据合并引擎: 天眼查模拟模式 + 企查查 API 模式"
            )
        elif self._qcc.is_mock_mode:
            logger.info(
                "企业数据合并引擎: 天眼查 API 模式 + 企查查模拟模式"
            )
        else:
            logger.info("企业数据合并引擎: 双 API 模式")

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def merge(self, company_name: str) -> Optional[EnterpriseInfo]:
        """合并双源数据为统一企业画像

        同时调用天眼查和企查查，按字段优先级合并为一个 EnterpriseInfo。

        Args:
            company_name: 企业全称

        Returns:
            合并后的 EnterpriseInfo 对象（含全部可用字段），
            两家均无数据时返回 None
        """
        if not company_name or not company_name.strip():
            logger.warning("合并引擎: 企业名称为空")
            return None

        company_name = company_name.strip()

        # 并行采集
        tyc_basic = self._tyc.get_basic_info(company_name)
        qcc_credit = self._qcc.get_credit_info(company_name)
        qcc_abnormal = self._qcc.get_abnormal_list(company_name)
        qcc_ip = self._qcc.get_intellectual_property(company_name)

        # 两家都无数据
        if not tyc_basic and not qcc_credit and not qcc_abnormal and not qcc_ip:
            logger.warning("合并引擎: %s 双源均无数据", company_name)
            return None

        # 执行合并
        merged = self._do_merge(
            company_name=company_name,
            tyc=tyc_basic,
            qcc_credit=qcc_credit,
            qcc_abnormal=qcc_abnormal,
            qcc_ip=qcc_ip,
        )

        # 标记合并来源
        merged.source = "merged(tyc+qcc)"
        logger.info(
            "合并引擎: %s -> 工商=%s, 风险=%s, 异常=%s, 知产=%s",
            company_name,
            "✓" if tyc_basic else "✗",
            "✓" if qcc_credit else "✗",
            "✓" if qcc_abnormal else "✗",
            "✓" if qcc_ip else "✗",
        )

        return merged

    def merge_batch(
        self, company_names: list[str]
    ) -> dict[str, Optional[EnterpriseInfo]]:
        """批量合并查询

        Args:
            company_names: 企业名称列表

        Returns:
            dict {企业名称: 合并后 EnterpriseInfo 或 None}
        """
        results: dict[str, Optional[EnterpriseInfo]] = {}
        for name in company_names:
            results[name] = self.merge(name)
        return results

    def get_summary(self, company_name: str) -> dict[str, Any]:
        """获取企业画像摘要（轻量级，仅关键字段）

        Args:
            company_name: 企业全称

        Returns:
            包含关键字段的字典，无数据返回空字典
        """
        merged = self.merge(company_name)
        if not merged:
            return {}

        return {
            "company_name": merged.company_name,
            "credit_code": merged.credit_code,
            "legal_person": merged.legal_person,
            "reg_capital": merged.reg_capital,
            "reg_status": merged.reg_status,
            "established_date": merged.established_date,
            "business_status_detail": merged.business_status_detail,
            "risk_count": merged.risk_count,
            "source": merged.source,
        }

    # ------------------------------------------------------------------
    # 内部合并逻辑
    # ------------------------------------------------------------------

    def _do_merge(
        self,
        company_name: str,
        tyc: Optional[EnterpriseInfo],
        qcc_credit: Optional[EnterpriseInfo],
        qcc_abnormal: Optional[EnterpriseInfo],
        qcc_ip: Optional[EnterpriseInfo],
    ) -> EnterpriseInfo:
        """执行实际合并

        策略：
        1. 从天眼查基础信息优先填充工商字段
        2. 从企查查信用信息填充信用/风险字段
        3. 从企查查异常/知产接口提取结构化数据
        4. 保留双方原始数据快照
        """
        merged = EnterpriseInfo(company_name=company_name)

        # --- 第一步: 天眼查优先（工商信息） ---
        if tyc:
            for field in _TYC_PRIORITY_FIELDS:
                val = getattr(tyc, field, None)
                if val is not None and val != "":
                    setattr(merged, field, val)

            # 股东信息（天眼查特有）
            if tyc.shareholders:
                merged.shareholders = tyc.shareholders

        # --- 第二步: 企查查补充（信用/风险） ---
        if qcc_credit:
            for field in _QCC_PRIORITY_FIELDS:
                qcc_val = getattr(qcc_credit, field, None)
                if qcc_val is not None and qcc_val != "":
                    setattr(merged, field, qcc_val)

            # 补充工商字段（天眼查缺失时）
            for field in _TYC_PRIORITY_FIELDS:
                cur_val = getattr(merged, field, None)
                if not cur_val:
                    qcc_val = getattr(qcc_credit, field, None)
                    if qcc_val is not None and qcc_val != "":
                        setattr(merged, field, qcc_val)

        # --- 第三步: 企查查经营异常 ---
        if qcc_abnormal:
            abnormal_records = qcc_abnormal.raw_data.get("abnormal_records", [])
            if abnormal_records:
                # 存入 merged.raw_data 下
                existing_raw = merged.raw_data
                existing_raw["abnormal_records"] = abnormal_records
                merged.raw_data = existing_raw

        # --- 第四步: 企查查知识产权 ---
        if qcc_ip:
            ip_list = qcc_ip.raw_data.get("ip_list", [])
            if ip_list:
                existing_raw = merged.raw_data
                existing_raw["ip_list"] = ip_list
                merged.raw_data = existing_raw

        # --- 第五步: 保留原始数据快照 ---
        merged.raw_data["raw_data_tyc"] = tyc.raw_data if tyc else {}
        merged.raw_data["raw_data_qcc"] = qcc_credit.raw_data if qcc_credit else {}

        return merged

    # ------------------------------------------------------------------
    # 去重逻辑
    # ------------------------------------------------------------------

    @staticmethod
    def dedup(
        profiles: list[EnterpriseInfo],
    ) -> list[EnterpriseInfo]:
        """同名企业去重

        对传入的企业画像列表按企业名称去重，
        保留第一个出现的同名企业（较早获取的优先保留）。

        Args:
            profiles: 企业画像列表

        Returns:
            去重后的企业画像列表
        """
        seen: set[str] = set()
        result: list[EnterpriseInfo] = []

        for profile in profiles:
            name = (profile.company_name or "").strip()
            if not name:
                continue
            if name not in seen:
                seen.add(name)
                result.append(profile)

        duplicates = len(profiles) - len(result)
        if duplicates > 0:
            logger.info("去重引擎: 移除 %s 条重复企业条目", duplicates)

        return result


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_merger(
    tyc_api_key: Optional[str] = None,
    qcc_api_key: Optional[str] = None,
) -> EnterpriseDataMerger:
    """创建企业数据合并引擎实例（便利函数）

    Args:
        tyc_api_key: 天眼查 API Key（可选，不传则从环境变量读取）
        qcc_api_key: 企查查 API Key（可选，不传则从环境变量读取）

    Returns:
        EnterpriseDataMerger 实例
    """
    tyc = TianyanchaAdapter(api_key=tyc_api_key)
    qcc = QichachaAdapter(api_key=qcc_api_key)
    return EnterpriseDataMerger(tyc_adapter=tyc, qcc_adapter=qcc)


__all__ = [
    "EnterpriseInfo",
    "EnterpriseDataMerger",
    "create_merger",
]
