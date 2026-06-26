"""
链客宝 - 意图信号识别引擎
=========================
从企查查企业数据中提取企业活跃信号，分析企业意图。

信号体系:
┌──────────┬──────────────────────────────────────────────┐
│ 类型      │ 说明                                         │
├──────────┼──────────────────────────────────────────────┤
│ 🟢 增长   │ 招聘扩张、融资、新分支机构、注册资本变更      │
│ 🟡 技术   │ 技术栈更新、新产品发布、知识产权申请          │
│ 🔴 风险   │ 法律纠纷、经营异常、股权变更、行政处罚        │
└──────────┴──────────────────────────────────────────────┘

快速开始:
    from backend.features.intent_signals import (
        IntentSignal,
        IntentSignalAnalyzer,
        compute_intent_score,
        inject_into_pipeline,
    )

    analyzer = IntentSignalAnalyzer()
    signals = analyzer.analyze("阿里巴巴")
    for s in signals:
        print(f"[{s.signal_type}] {s.label} strength={s.strength}")

    score = compute_intent_score(signals)
    print(f"综合意图分: {score}/100")
"""

from .analyzer import (
    IntentSignal,
    IntentSignalType,
    IntentSignalAnalyzer,
    create_analyzer,
)
from .scorer import (
    compute_intent_score,
    get_signal_profile,
)
from .integration import (
    inject_into_pipeline,
    build_signal_features,
)

__all__ = [
    "IntentSignal",
    "IntentSignalType",
    "IntentSignalAnalyzer",
    "create_analyzer",
    "compute_intent_score",
    "get_signal_profile",
    "inject_into_pipeline",
    "build_signal_features",
]

__version__ = "1.0.0"
__author__ = "链客宝 AI 引擎组"
