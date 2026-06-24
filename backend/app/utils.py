"""
链客宝AI 共享工具函数
======================
从 matching_engine.py 和 feature_pipeline.py 提取的通用函数，
消除两模块间的重复代码。

函数:
  - normalize_text(text)  → str           文本规范化（小写、去标点）
  - parse_budget(budget_str) → (float,float)|None  预算字符串解析
"""

import logging
import re

logger = logging.getLogger(__name__)


def normalize_text(text: str | None) -> str:
    """规范化文本：转小写、去标点、合并空白

    从 matching_engine.MatchEngine._normalize_text 和
    feature_pipeline._normalize_text 提取的公共版本。
    """
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_budget(budget_str: str | None) -> tuple[float, float] | None:
    """解析预算字符串，返回 (min, max) 元组

    支持格式:
      - "10万-50万" / "10万~50万" / "10-50万" → (100000, 500000)
      - "10万以上" / "不低于10万" / ">10万"   → (100000, inf)
      - "5万以内" / "不超过10万" / "<10万"     → (0, 100000)

    无法解析时返回 None。
    """
    if not budget_str:
        return None
    budget_str = budget_str.strip()

    # 匹配 "10万-50万" / "10万~50万" / "10-50万" / "10至50万" / "10到50万"
    pattern = r"(\d+(?:\.\d+)?)\s*(?:万|w)?\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*(?:万|w)?"
    m = re.search(pattern, budget_str)
    if m:
        min_val = float(m.group(1))
        max_val = float(m.group(2))
        if "万" in budget_str or "w" in budget_str.lower():
            min_val *= 10000
            max_val *= 10000
        return (min_val, max_val)

    # 匹配 "10万以上" / "不低于10万" / ">10万" / "大于10万"
    pattern2 = r"(?:不低于|以上|>|大于)\s*(\d+(?:\.\d+)?)\s*(?:万|w)?"
    m = re.search(pattern2, budget_str)
    if m:
        val = float(m.group(1))
        if "万" in budget_str or "w" in budget_str.lower():
            val *= 10000
        return (val, float("inf"))

    # 匹配 "10万以上"（数字在前，关键词在后）
    pattern2b = r"(\d+(?:\.\d+)?)\s*(?:万|w)?\s*(?:以上|>|大于|不低于)"
    m = re.search(pattern2b, budget_str)
    if m:
        val = float(m.group(1))
        if "万" in budget_str or "w" in budget_str.lower():
            val *= 10000
        return (val, float("inf"))

    # 匹配 "5万以内" / "不超过10万" / "<10万" / "小于10万"
    pattern3 = r"(?:不超过|以内|<|小于)\s*(\d+(?:\.\d+)?)\s*(?:万|w)?"
    m = re.search(pattern3, budget_str)
    if m:
        val = float(m.group(1))
        if "万" in budget_str or "w" in budget_str.lower():
            val *= 10000
        return (0, val)

    # 匹配 "5万以内"（数字在前，关键词在后）
    pattern3b = r"(\d+(?:\.\d+)?)\s*(?:万|w)?\s*(?:以内|<|小于|不超过)"
    m = re.search(pattern3b, budget_str)
    if m:
        val = float(m.group(1))
        if "万" in budget_str or "w" in budget_str.lower():
            val *= 10000
        return (0, val)

    return None
