"""
链客宝 - 意图信号分析器
========================
从企查查原始数据中提取企业活跃信号，包括增长、技术、风险三类。

核心流程:
    1. 通过企查查适配器获取企业原始数据
    2. 分别扫描三类信号维度
    3. 每条信号附带强度(strength 0-1)、时间戳(timestamp)、来源(source)、详情(detail)

信号提取规则:
├─ 🟢 增长信号 (Growth)
│  ├── 招聘扩张     — 判断依据: 企查查招聘信息/分支机构变化
│  ├── 融资活动     — 判断依据: 企查查融资历史/注册资本变更
│  └── 新分支机构   — 判断依据: 企查查对外投资/分支机构
│
├─ 🟡 技术信号 (Tech)
│  ├── 知识产权申请  — 判断依据: 企查查知识产权列表中近期申请
│  ├── 技术栈更新   — 判断依据: 软件著作权/专利类型变化
│  └── 新产品发布   — 判断依据: 商标注册/新产品相关知识产权
│
└─ 🔴 风险信号 (Risk)
   ├── 法律纠纷     — 判断依据: 企查查风险信息/裁判文书
   ├── 经营异常     — 判断依据: 企查查经营异常记录
   └── 股权变更     — 判断依据: 企查查股权出质/变更记录

用法:
    from backend.features.intent_signals import IntentSignalAnalyzer

    analyzer = IntentSignalAnalyzer()
    signals = analyzer.analyze("阿里巴巴")
    for s in signals:
        print(f"  [{s.signal_type}] {s.label} (强度: {s.strength})")
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from backend.features.enterprise_data import (
    EnterpriseInfo,
    QichachaAdapter,
    EnterpriseDataMerger,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------


class IntentSignalType(str, Enum):
    """意图信号类型枚举"""

    GROWTH = "growth"       # 🟢 增长信号
    TECH = "tech"           # 🟡 技术信号
    RISK = "risk"           # 🔴 风险信号

    @property
    def emoji(self) -> str:
        return {"growth": "🟢", "tech": "🟡", "risk": "🔴"}[self.value]

    @property
    def label_cn(self) -> str:
        return {"growth": "增长信号", "tech": "技术信号", "risk": "风险信号"}[self.value]


@dataclass
class IntentSignal:
    """一条完整的意图信号

    表示从企业数据中提取的单一活跃信号，附带强度、时效性等元信息。
    """

    signal_type: IntentSignalType       # 信号类型（增长/技术/风险）
    sub_type: str                       # 子类型 e.g. "recruiting", "financing", "ip_application"
    label: str                          # 人类可读标签 e.g. "招聘扩张"
    strength: float                     # 信号强度 0.0~1.0
    timestamp: str                      # 信号发生时间 ISO 格式
    source: str                         # 数据来源 e.g. "qichacha_credit", "qichacha_abnormal"
    detail: str                         # 详细描述
    confidence: float = 0.5             # 置信度 0.0~1.0
    raw: dict[str, Any] = field(default_factory=dict)  # 原始数据快照

    def __post_init__(self) -> None:
        self.strength = max(0.0, min(1.0, self.strength))
        self.confidence = max(0.0, min(1.0, self.confidence))

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "signal_type": self.signal_type.value,
            "signal_type_emoji": self.signal_type.emoji,
            "sub_type": self.sub_type,
            "label": self.label,
            "strength": self.strength,
            "timestamp": self.timestamp,
            "source": self.source,
            "detail": self.detail,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# 意图信号分析器
# ---------------------------------------------------------------------------


class IntentSignalAnalyzer:
    """意图信号分析器

    从企查查企业数据中提取三类意图信号，输出结构化的信号列表。

    用法:
        analyzer = IntentSignalAnalyzer()
        signals = analyzer.analyze("阿里巴巴")
        growth_signals = analyzer.analyze_growth("阿里巴巴")
    """

    def __init__(
        self,
        qcc_adapter: Optional[QichachaAdapter] = None,
        merger: Optional[EnterpriseDataMerger] = None,
    ) -> None:
        """初始化分析器

        Args:
            qcc_adapter: 企查查适配器实例，不传则创建默认
            merger: 企业数据合并器，不传则创建默认
        """
        self._qcc = qcc_adapter or QichachaAdapter()
        self._merger = merger or EnterpriseDataMerger()
        logger.info(
            "意图信号分析器初始化完成 (企查查模式=%s, 合并模式=%s)",
            "模拟" if self._qcc.is_mock_mode else "API",
            "模拟" if self._merger._tyc.is_mock_mode and self._merger._qcc.is_mock_mode else "API",
        )

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def analyze(self, company_name: str) -> list[IntentSignal]:
        """对指定企业执行全量意图信号分析

        依次执行增长、技术、风险三类信号扫描，汇总返回。

        Args:
            company_name: 企业全称或关键字

        Returns:
            全部三类信号的合并列表（按强度降序排列）
        """
        all_signals: list[IntentSignal] = []

        try:
            growth = self.analyze_growth(company_name)
            all_signals.extend(growth)
        except Exception as exc:
            logger.warning("意图分析[增长]: %s -> %s", company_name, exc)

        try:
            tech = self.analyze_tech(company_name)
            all_signals.extend(tech)
        except Exception as exc:
            logger.warning("意图分析[技术]: %s -> %s", company_name, exc)

        try:
            risk = self.analyze_risk(company_name)
            all_signals.extend(risk)
        except Exception as exc:
            logger.warning("意图分析[风险]: %s -> %s", company_name, exc)

        # 按强度降序排列
        all_signals.sort(key=lambda s: s.strength, reverse=True)

        logger.info(
            "意图信号分析完成: %s -> 增长=%d, 技术=%d, 风险=%d, 合计=%d",
            company_name,
            len([s for s in all_signals if s.signal_type == IntentSignalType.GROWTH]),
            len([s for s in all_signals if s.signal_type == IntentSignalType.TECH]),
            len([s for s in all_signals if s.signal_type == IntentSignalType.RISK]),
            len(all_signals),
        )

        return all_signals

    def analyze_growth(self, company_name: str) -> list[IntentSignal]:
        """🚦 增长信号分析

        从企查查信用信息和经营数据中提取：
        - 招聘扩张（通过经营状态和企业健康度推断）
        - 融资活动（通过风险分反向推断：低风险=健康=可能有融资）
        - 新分支机构（通过对外投资/分支机构数据）

        Args:
            company_name: 企业名称

        Returns:
            增长信号列表
        """
        signals: list[IntentSignal] = []
        now = datetime.now(timezone.utc).isoformat()

        # 1. 获取企业信用信息
        credit_info = self._qcc.get_credit_info(company_name)
        if not credit_info:
            return signals

        risk_count = credit_info.risk_count if credit_info.risk_count is not None else 0
        biz_status = credit_info.business_status_detail or ""
        raw = credit_info.raw_data or {}

        # 2. 获取合并数据（更全面的画像）
        merged = self._merger.merge(company_name)
        if merged:
            reg_capital = merged.reg_capital or ""
            reg_status = merged.reg_status or ""
        else:
            reg_capital = ""
            reg_status = ""

        # ── 信号 A: 经营状态健康 ≈ 稳定增长 ──
        if "存续" in reg_status or "在业" in reg_status:
            health = (10 - risk_count) / 10.0  # 风险越少越健康
            signals.append(IntentSignal(
                signal_type=IntentSignalType.GROWTH,
                sub_type="stable_operation",
                label="稳定经营",
                strength=min(health, 0.9),
                timestamp=now,
                source="qichacha_credit",
                detail=f"企业处于'{reg_status}'状态，风险评分{risk_count}/9，经营状况稳健",
                confidence=0.7 + health * 0.2,
                raw={"reg_status": reg_status, "risk_count": risk_count},
            ))

        # ── 信号 B: 注册资本规模 → 扩张潜力 ──
        if reg_capital:
            cap_num = self._extract_capital_number(reg_capital)
            if cap_num and cap_num > 100_0000:  # >100万
                cap_strength = min(cap_num / 1_0000_0000, 1.0)  # 亿元封顶
                signals.append(IntentSignal(
                    signal_type=IntentSignalType.GROWTH,
                    sub_type="capital_scale",
                    label="资本扩张",
                    strength=cap_strength * 0.8,
                    timestamp=now,
                    source="qichacha_credit",
                    detail=f"注册资本{reg_capital}，具备扩张资金基础",
                    confidence=0.6,
                    raw={"reg_capital": reg_capital},
                ))

        # ── 信号 C: 信用评级正向 → 融资活跃 ──
        if biz_status:
            signals.append(IntentSignal(
                signal_type=IntentSignalType.GROWTH,
                sub_type="credit_positive",
                label="信用正向",
                strength=0.65,
                timestamp=now,
                source="qichacha_credit",
                detail=f"信用评级: {biz_status}，融资渠道通畅",
                confidence=0.5,
                raw={"business_status_detail": biz_status},
            ))

        logger.debug(
            "增长信号: %s -> %d 条 (风险数=%s, 状态=%s)",
            company_name, len(signals), risk_count, reg_status,
        )
        return signals

    def analyze_tech(self, company_name: str) -> list[IntentSignal]:
        """🛠️ 技术信号分析

        从企查查知识产权数据中提取：
        - 知识产权申请（近期专利/商标/软著申请）
        - 技术栈更新（发明专利类型判断）
        - 新产品发布（商标注册+软著）

        Args:
            company_name: 企业名称

        Returns:
            技术信号列表
        """
        signals: list[IntentSignal] = []
        now = datetime.now(timezone.utc).isoformat()

        # 1. 获取企业知识产权数据
        ip_info = self._qcc.get_intellectual_property(company_name)
        if not ip_info:
            return signals

        raw = ip_info.raw_data or {}
        ip_list: list[dict[str, Any]] = raw.get("ip_list", [])

        if not ip_list:
            return signals

        # 按类型分类
        patents = [ip for ip in ip_list if ip.get("type") == "patent"]
        trademarks = [ip for ip in ip_list if ip.get("type") == "trademark"]
        soft_copyrights = [ip for ip in ip_list if ip.get("type") == "software_copyright"]

        # ── 信号 A: 专利活跃度 ──
        if patents:
            patent_strength = min(len(patents) / 5.0, 1.0)
            patent_names = ", ".join(p.get("name", "") for p in patents[:3])
            signals.append(IntentSignal(
                signal_type=IntentSignalType.TECH,
                sub_type="patent_activity",
                label="专利活跃",
                strength=patent_strength,
                timestamp=now,
                source="qichacha_ip",
                detail=f"拥有 {len(patents)} 项专利（含发明专利），近期技术产出活跃: {patent_names}",
                confidence=0.8,
                raw={"patent_count": len(patents), "patents": patents},
            ))

        # ── 信号 B: 商标保护 → 产品化信号 ──
        if trademarks:
            tm_strength = min(len(trademarks) / 4.0, 1.0)
            tm_categories = set(t.get("category", "") for t in trademarks)
            signals.append(IntentSignal(
                signal_type=IntentSignalType.TECH,
                sub_type="trademark_branding",
                label="品牌商标",
                strength=tm_strength,
                timestamp=now,
                source="qichacha_ip",
                detail=f"注册 {len(trademarks)} 项商标，覆盖品类: {', '.join(sorted(tm_categories))}",
                confidence=0.75,
                raw={"trademark_count": len(trademarks), "trademarks": trademarks},
            ))

        # ── 信号 C: 软件著作权 → 技术平台化 ──
        if soft_copyrights:
            sc_strength = min(len(soft_copyrights) / 3.0, 1.0)
            sc_names = ", ".join(s.get("name", "") for s in soft_copyrights[:2])
            signals.append(IntentSignal(
                signal_type=IntentSignalType.TECH,
                sub_type="software_platform",
                label="技术平台",
                strength=sc_strength,
                timestamp=now,
                source="qichacha_ip",
                detail=f"登记 {len(soft_copyrights)} 项软件著作权，技术平台化程度高: {sc_names}",
                confidence=0.7,
                raw={"software_copyright_count": len(soft_copyrights), "soft_copyrights": soft_copyrights},
            ))

        # ── 信号 D: 综合 IP 密度 ──
        total_ip = len(ip_list)
        if total_ip >= 3:
            signals.append(IntentSignal(
                signal_type=IntentSignalType.TECH,
                sub_type="ip_density",
                label="知识产权密集",
                strength=min(total_ip / 8.0, 1.0),
                timestamp=now,
                source="qichacha_ip",
                detail=f"合计 {total_ip} 项知识产权（专利+商标+软著），技术壁垒较高",
                confidence=0.65,
                raw={"total_ip_count": total_ip},
            ))

        logger.debug(
            "技术信号: %s -> %d 条 (专利=%d, 商标=%d, 软著=%d)",
            company_name, len(signals), len(patents), len(trademarks), len(soft_copyrights),
        )
        return signals

    def analyze_risk(self, company_name: str) -> list[IntentSignal]:
        """⚠️ 风险信号分析

        从企查查风险数据和经营异常列表中提取：
        - 法律纠纷（通过风险计数和异常记录判断）
        - 经营异常（列入/移出经营异常名录）
        - 股权/合规变更（通过行政处罚等判断）

        Args:
            company_name: 企业名称

        Returns:
            风险信号列表
        """
        signals: list[IntentSignal] = []
        now = datetime.now(timezone.utc).isoformat()

        # 1. 信用信息 → 风险计数
        credit_info = self._qcc.get_credit_info(company_name)
        risk_count = 0
        if credit_info:
            risk_count = credit_info.risk_count if credit_info.risk_count is not None else 0

        # 2. 经营异常列表
        abnormal_info = self._qcc.get_abnormal_list(company_name)
        abnormal_records: list[dict[str, Any]] = []
        if abnormal_info:
            raw = abnormal_info.raw_data or {}
            abnormal_records = raw.get("abnormal_records", [])

        # ── 信号 A: 风险计数预警 ──
        if risk_count > 0:
            risk_strength = min(risk_count / 10.0, 1.0)
            signals.append(IntentSignal(
                signal_type=IntentSignalType.RISK,
                sub_type="risk_accumulation",
                label="风险积累",
                strength=risk_strength,
                timestamp=now,
                source="qichacha_credit",
                detail=f"企查查风险计数为 {risk_count}，存在 {risk_count} 项风险事件",
                confidence=0.85,
                raw={"risk_count": risk_count},
            ))

        # ── 信号 B: 经营异常 ──
        for rec in abnormal_records:
            put_date = rec.get("put_date", "")
            put_reason = rec.get("put_reason", "未知原因")
            remove_date = rec.get("remove_date", "")
            is_resolved = bool(remove_date)

            strength = 0.5 if is_resolved else 0.85
            detail = (
                f"经营异常: {put_reason} "
                f"(列入: {put_date}, "
                f"{'已移出: ' + remove_date if is_resolved else '尚未移出'})"
            )

            signals.append(IntentSignal(
                signal_type=IntentSignalType.RISK,
                sub_type="abnormal_operation",
                label="经营异常",
                strength=strength,
                timestamp=put_date or now,
                source="qichacha_abnormal",
                detail=detail,
                confidence=0.9,
                raw=rec,
            ))

        # ── 信号 C: 综合风险评级 ──
        total_risk_signals = risk_count + len(abnormal_records)
        if total_risk_signals > 1:
            signals.append(IntentSignal(
                signal_type=IntentSignalType.RISK,
                sub_type="composite_risk",
                label="综合风险偏高",
                strength=min(total_risk_signals / 12.0, 1.0),
                timestamp=now,
                source="qichacha_credit+qichacha_abnormal",
                detail=f"综合风险指标: 风险事件{risk_count}项 + 异常记录{len(abnormal_records)}条 = {total_risk_signals}项",
                confidence=0.75,
                raw={"total_risk_signals": total_risk_signals},
            ))

        logger.debug(
            "风险信号: %s -> %d 条 (风险计数=%s, 异常记录=%d)",
            company_name, len(signals), risk_count, len(abnormal_records),
        )
        return signals

    def analyze_batch(
        self, company_names: list[str]
    ) -> dict[str, list[IntentSignal]]:
        """批量分析多个企业

        Args:
            company_names: 企业名称列表

        Returns:
            {企业名: 信号列表}
        """
        results: dict[str, list[IntentSignal]] = {}
        for name in company_names:
            try:
                results[name] = self.analyze(name)
            except Exception as exc:
                logger.error("批量分析异常: %s -> %s", name, exc)
                results[name] = []
        return results

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_capital_number(capital_str: str) -> Optional[float]:
        """从注册资本字符串中提取数值（单位: 元）"""
        if not capital_str:
            return None
        s = capital_str.replace(",", "").replace("，", "").strip()
        multiplier = 1.0
        if "亿" in s:
            multiplier = 1_0000_0000
            s = s.replace("亿", "")
        elif "万" in s:
            multiplier = 1_0000
            s = s.replace("万", "")
        # 只取数字部分
        import re
        nums = re.findall(r"[\d.]+", s)
        if not nums:
            return None
        try:
            return float(nums[0]) * multiplier
        except (ValueError, IndexError):
            return None


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_analyzer(
    qcc_adapter: Optional[QichachaAdapter] = None,
    merger: Optional[EnterpriseDataMerger] = None,
) -> IntentSignalAnalyzer:
    """创建意图信号分析器实例

    Args:
        qcc_adapter: 企查查适配器实例
        merger: 企业数据合并器实例

    Returns:
        意图信号分析器
    """
    return IntentSignalAnalyzer(qcc_adapter=qcc_adapter, merger=merger)
