"""
链客宝 - 意图信号分析器 单元测试
====================================
覆盖 IntentSignalAnalyzer 的核心方法，包括正常路径、边界条件、异常处理。

运行时需要先添加项目根目录到 sys.path。

运行:
    pytest tests/test_intent_analyzer.py -v
    # 或
    python -m pytest tests/test_intent_analyzer.py -v
"""

import os
import sys
from unittest.mock import MagicMock, PropertyMock

import pytest

# 添加项目根目录（D:\chainke-full）到 path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.features.intent_signals.analyzer import (
    IntentSignalAnalyzer,
    IntentSignal,
    IntentSignalType,
    create_analyzer,
)
from backend.features.enterprise_data.tianyancha_adapter import EnterpriseInfo


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_qcc():
    """返回一个完全 mock 的 QichachaAdapter 实例，所有方法返回 None"""
    return MagicMock()


@pytest.fixture
def mock_merger():
    """返回一个完全 mock 的 EnterpriseDataMerger 实例"""
    merger = MagicMock()
    merger.merge.return_value = None
    return merger


def _make_credit_info(
    company_name: str = "测试科技",
    risk_count: int = 2,
    reg_status: str = "存续",
    biz_detail: str = "信用评级: A1",
    reg_capital: str = "5000万元",
) -> EnterpriseInfo:
    """构建一个带信用信息的 EnterpriseInfo"""
    return EnterpriseInfo(
        company_name=company_name,
        credit_code="91123456MA7890ABCD",
        legal_person="张三",
        reg_capital=reg_capital,
        reg_status=reg_status,
        business_status_detail=biz_detail,
        risk_count=risk_count,
        raw_data={
            "company_name": company_name,
            "risk_count": risk_count,
            "reg_status": reg_status,
            "creditRating": biz_detail,
        },
    )


def _make_ip_info(
    company_name: str = "测试科技",
    patents: int = 0,
    trademarks: int = 0,
    soft_copyrights: int = 0,
) -> EnterpriseInfo:
    """构建带知识产权数据的 EnterpriseInfo"""
    ip_list = []
    for i in range(patents):
        ip_list.append({
            "type": "patent",
            "name": f"专利-{i+1}",
            "reg_number": f"CN2023{i:04d}.X",
            "status": "授权",
            "apply_date": "2023-01-15",
            "type_detail": "发明专利",
        })
    for i in range(trademarks):
        ip_list.append({
            "type": "trademark",
            "name": f"{company_name}®-{i+1}",
            "reg_number": f"第{i+1:06d}号",
            "status": "已注册",
            "apply_date": "2022-05-10",
            "category": f"第{(i % 10 + 35)}类",
        })
    for i in range(soft_copyrights):
        ip_list.append({
            "type": "software_copyright",
            "name": f"{company_name}平台V{i+1}.0",
            "reg_number": f"软著{i:06d}号",
            "status": "原始取得",
            "apply_date": "2023-06-01",
        })
    return EnterpriseInfo(
        company_name=company_name,
        raw_data={"ip_list": ip_list},
    )


def _make_abnormal_info(
    company_name: str = "测试科技",
    records: object = None,
) -> object:
    """构建经营异常信息"""
    if records is None:
        return EnterpriseInfo(
            company_name=company_name,
            raw_data={"abnormal_records": []},
        )
    return EnterpriseInfo(
        company_name=company_name,
        raw_data={"abnormal_records": records},
    )


# =========================================================================
# 测试用例
# =========================================================================


class TestIntentSignal:
    """IntentSignal 数据模型基础功能测试"""

    def test_strength_clamping(self):
        """边界测试：strength / confidence 自动钳制到 [0.0, 1.0]"""
        s = IntentSignal(
            signal_type=IntentSignalType.GROWTH,
            sub_type="test",
            label="测试",
            strength=999.0,
            timestamp="2024-01-01T00:00:00",
            source="test",
            detail="测试超上限",
            confidence=-0.5,
        )
        assert s.strength == 1.0, f"期望 1.0，实际 {s.strength}"
        assert s.confidence == 0.0, f"期望 0.0，实际 {s.confidence}"

        s2 = IntentSignal(
            signal_type=IntentSignalType.GROWTH,
            sub_type="test",
            label="测试",
            strength=-1.0,
            timestamp="2024-01-01T00:00:00",
            source="test",
            detail="测试超下限",
            confidence=1.5,
        )
        assert s2.strength == 0.0, f"期望 0.0，实际 {s2.strength}"
        assert s2.confidence == 1.0, f"期望 1.0，实际 {s2.confidence}"

    def test_to_dict(self):
        """正常路径：序列化输出关键字段"""
        s = IntentSignal(
            signal_type=IntentSignalType.TECH,
            sub_type="patent_activity",
            label="专利活跃",
            strength=0.8,
            timestamp="2024-06-01T12:00:00+00:00",
            source="qichacha_ip",
            detail="测试详情",
            confidence=0.75,
        )
        d = s.to_dict()
        assert d["signal_type"] == "tech"
        assert d["signal_type_emoji"] == "🟡"
        assert d["sub_type"] == "patent_activity"
        assert d["strength"] == 0.8
        assert d["confidence"] == 0.75
        assert d["timestamp"] == "2024-06-01T12:00:00+00:00"
        # to_dict 不应包含 raw 字段（避免序列化污染）
        assert "raw" not in d


class TestIntentSignalAnalyzer:
    """IntentSignalAnalyzer 核心逻辑测试"""

    # ------------------------------------------------------------------
    # 正常路径：全量分析
    # ------------------------------------------------------------------

    def test_analyze_full_signals(self, mock_qcc, mock_merger):
        """正常路径：analyze() 正确汇总三类信号并按强度降序排列"""
        # 模拟增长信号：健康企业，风险较少
        mock_qcc.get_credit_info.return_value = _make_credit_info(
            risk_count=2, reg_capital="5000万元"
        )
        mock_merger.merge.return_value = _make_credit_info(
            risk_count=2, reg_capital="5000万元"
        )

        # 模拟技术信号：1专利+2商标
        mock_qcc.get_intellectual_property.return_value = _make_ip_info(
            patents=1, trademarks=2
        )

        # 模拟风险信号：有风险计数+有异常记录
        mock_qcc.get_abnormal_list.return_value = _make_abnormal_info(
            records=[
                {
                    "put_date": "2023-03-15",
                    "put_reason": "经营场所无法联系",
                    "put_department": "北京市监局",
                    "remove_date": "2023-06-20",
                    "remove_reason": "已变更",
                },
            ]
        )

        analyzer = IntentSignalAnalyzer(qcc_adapter=mock_qcc, merger=mock_merger)
        signals = analyzer.analyze("测试科技")

        # 断言：三类信号都应该存在
        assert len(signals) > 0, "应返回信号列表"

        # 验证三类信号类型都存在
        types_found = {s.signal_type for s in signals}
        assert IntentSignalType.GROWTH in types_found, "应包含增长信号"
        assert IntentSignalType.TECH in types_found, "应包含技术信号"
        assert IntentSignalType.RISK in types_found, "应包含风险信号"

        # 验证按强度降序排列
        for i in range(len(signals) - 1):
            assert (
                signals[i].strength >= signals[i + 1].strength
            ), f"信号未按强度降序: idx={i}"

        # 验证所有信号的基本字段完整性
        for s in signals:
            assert s.sub_type, "sub_type 不应为空"
            assert s.label, "label 不应为空"
            assert s.source, "source 不应为空"
            assert s.detail, "detail 不应为空"

    # ------------------------------------------------------------------
    # 正常路径：增长信号分析
    # ------------------------------------------------------------------

    def test_analyze_growth_healthy_company(self, mock_qcc, mock_merger):
        """正常路径：健康企业生成全部3个增长子信号"""
        mock_qcc.get_credit_info.return_value = _make_credit_info(
            risk_count=1,          # 低风险
            reg_status="存续",     # 经营状态正常
            biz_detail="信用评级: AAA",
            reg_capital="1亿元",   # 高注册资本
        )
        mock_merger.merge.return_value = _make_credit_info(
            risk_count=1,
            reg_status="存续",
            reg_capital="1亿元",
        )

        analyzer = IntentSignalAnalyzer(qcc_adapter=mock_qcc, merger=mock_merger)
        signals = analyzer.analyze_growth("测试科技")

        sub_types = {s.sub_type for s in signals}
        assert "stable_operation" in sub_types, "应包含稳定经营信号"
        assert "capital_scale" in sub_types, "应包含资本扩张信号"
        assert "credit_positive" in sub_types, "应包含信用正向信号"

        # 验证强度计算：risk_count=1 → health=(10-1)/10=0.9, capped at 0.9
        stable = [s for s in signals if s.sub_type == "stable_operation"][0]
        assert stable.strength == 0.9, f"稳定经营强度应为 0.9，实际 {stable.strength}"

    # ------------------------------------------------------------------
    # 正常路径：风险信号分析
    # ------------------------------------------------------------------

    def test_analyze_risk_with_abnormal_records(self, mock_qcc, mock_merger):
        """正常路径：风险信号包含风险积累+经营异常+综合风险"""
        mock_qcc.get_credit_info.return_value = _make_credit_info(
            risk_count=5,
        )
        mock_qcc.get_abnormal_list.return_value = _make_abnormal_info(
            records=[
                {
                    "put_date": "2023-03-15",
                    "put_reason": "经营场所无法联系",
                    "put_department": "北京市监局",
                    "remove_date": "",           # 未移出 → is_resolved=False
                    "remove_reason": "",
                },
                {
                    "put_date": "2022-01-10",
                    "put_reason": "未按期公示年报",
                    "put_department": "上海市监局",
                    "remove_date": "2022-04-15",  # 已移出 → is_resolved=True
                    "remove_reason": "补报完成",
                },
            ]
        )
        mock_merger.merge.return_value = None

        analyzer = IntentSignalAnalyzer(qcc_adapter=mock_qcc, merger=mock_merger)
        signals = analyzer.analyze_risk("测试科技")

        # 应生成: risk_accumulation (risk_count>0) + 2×abnormal_operation + composite_risk (total>1)
        sub_types = {s.sub_type for s in signals}
        assert "risk_accumulation" in sub_types, "应包含风险积累信号"
        assert "abnormal_operation" in sub_types, "应包含经营异常信号"
        assert "composite_risk" in sub_types, "应包含综合风险信号"

        # 验证异常信号数
        abnormal_signals = [s for s in signals if s.sub_type == "abnormal_operation"]
        assert len(abnormal_signals) == 2, f"应有2条异常信号，实际 {len(abnormal_signals)}"

        # 验证未移出 (remove_date="") 的记录强度为 0.85，已移出的强度为 0.5
        for s in abnormal_signals:
            if s.raw.get("remove_date") == "":
                assert s.strength == 0.85, f"未移出信号强度应为 0.85，实际 {s.strength}"
            else:
                assert s.strength == 0.5, f"已移出信号强度应为 0.5，实际 {s.strength}"

    # ------------------------------------------------------------------
    # 边界条件：所有适配器返回空
    # ------------------------------------------------------------------

    def test_analyze_all_empty(self, mock_qcc, mock_merger):
        """边界条件：所有 adapter 返回 None，analyze() 应返回空列表"""
        mock_qcc.get_credit_info.return_value = None
        mock_qcc.get_intellectual_property.return_value = None
        mock_qcc.get_abnormal_list.return_value = None
        mock_merger.merge.return_value = None

        analyzer = IntentSignalAnalyzer(qcc_adapter=mock_qcc, merger=mock_merger)
        signals = analyzer.analyze("不存在的企业")

        # 所有 try 块捕获异常后返回空列表；或者正常返回空列表
        assert signals == [], f"无数据时应返回空列表，实际 {signals}"

    # ------------------------------------------------------------------
    # 边界条件+异常路径：单个信号维度抛出异常
    # ------------------------------------------------------------------

    def test_analyze_single_dimension_exception(self, mock_qcc, mock_merger):
        """异常路径：analyze_growth 抛出异常时不影响其他维度"""
        # 增长信号 → get_credit_info 抛出异常
        # 注意：analyze_risk 也调用 get_credit_info，所以这里只让第一次调用异常
        mock_qcc.get_credit_info.side_effect = [
            RuntimeError("增长分析 API 超时"),   # analyze_growth 调用 → 抛异常
            _make_credit_info(risk_count=3),     # analyze_risk 调用 → 正常返回
        ]
        # 技术信号 → 正常返回
        mock_qcc.get_intellectual_property.return_value = _make_ip_info(
            patents=2, trademarks=1
        )
        # 风险信号 → 正常返回
        mock_qcc.get_abnormal_list.return_value = _make_abnormal_info(
            records=[
                {
                    "put_date": "2023-05-01",
                    "put_reason": "未年报",
                    "put_department": "市监局",
                    "remove_date": "",
                    "remove_reason": "",
                },
            ]
        )
        mock_merger.merge.return_value = None

        analyzer = IntentSignalAnalyzer(qcc_adapter=mock_qcc, merger=mock_merger)
        signals = analyzer.analyze("测试科技")

        # 仍然有技术信号和风险信号
        types_found = {s.signal_type for s in signals}
        assert IntentSignalType.TECH in types_found, (
            "技术信号应正常返回"
        )
        assert IntentSignalType.RISK in types_found, (
            "风险信号应正常返回"
        )
        assert IntentSignalType.GROWTH not in types_found, (
            "增长信号因异常应被跳过"
        )

        # 验证技术信号具体内容
        tech_signals = [s for s in signals if s.signal_type == IntentSignalType.TECH]
        assert len(tech_signals) >= 1

        # 验证风险信号具体内容
        risk_signals = [s for s in signals if s.signal_type == IntentSignalType.RISK]
        assert len(risk_signals) >= 1
