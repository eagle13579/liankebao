"""
链客宝 — 知识图谱冷启动匹配模块
=================================
为新用户（无行为数据）提供基于企业属性 + 知识图谱图遍历的冷启动推荐。

能力:
  - ColdStartMatcher: 基于用户注册企业信息，在知识图谱中查找同类企业
  - 多维度图遍历: 同行业、同规模、同地区以及图路径推荐
  - 兼容 Neo4j 和 NetworkX 双模式（自动降级）

用法:
    from features.kg_coldstart import ColdStartMatcher

    matcher = ColdStartMatcher()
    recommendations = matcher.match(
        user_info={"industry": "人工智能", "scale": "中型", "region": "北京"},
        top_k=10,
    )

依赖:
  - features.knowledge_graph (GraphQueryEngine)
  - ml.knowledge_graph.schema (可选, 用于实体类型常量)
"""

from .coldstart_matcher import ColdStartMatcher, ColdStartResult

__all__ = [
    "ColdStartMatcher",
    "ColdStartResult",
]
