"""链客宝 — AI对话匹配模块

提供自然语言意图识别与智能匹配功能。

模块:
  - intent_parser: NLU意图识别与实体提取
  - matcher:      基于意图+实体的匹配查询构建与执行

用法:
    from features.ai_matching.intent_parser import IntentParser
    from features.ai_matching.matcher import AIMatcher
"""

from features.ai_matching.intent_parser import (
    IntentParser,
    IntentResult,
    IntentType,
    ExtractedEntity,
)
from features.ai_matching.matcher import (
    AIMatcher,
    MatchQuery,
    MatchResult,
)

__all__ = [
    "IntentParser",
    "IntentResult",
    "IntentType",
    "ExtractedEntity",
    "AIMatcher",
    "MatchQuery",
    "MatchResult",
]

__version__ = "1.0.0"
