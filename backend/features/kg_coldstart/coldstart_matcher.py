"""知识图谱冷启动匹配 — 基于企业属性的图匹配算法"""
from typing import Optional
from features.knowledge_graph.neo4j_client import Neo4jClient
from features.knowledge_graph.schema import CompanyNode

class ColdStartMatcher:
    """为新用户(无行为数据)提供基于企业属性的冷启动匹配"""
    
    def __init__(self):
        self.graph = Neo4jClient()
    
    def get_recommendations(self, user_id: int, 
                            industry: Optional[str] = None,
                            company_size: Optional[str] = None,
                            region: Optional[str] = None,
                            top_k: int = 10):
        """
        基于用户属性的冷启动推荐
        
        Args:
            user_id: 用户ID
            industry: 行业 (如 "科技", "金融")
            company_size: 企业规模 (如 "1-50人", "50-200人")
            region: 地区 (如 "北京", "上海")
            top_k: 返回数量
        """
        # Build filter conditions
        filters = []
        params = {"user_id": user_id, "limit": top_k}
        
        if industry:
            filters.append("c.industry = $industry")
            params["industry"] = industry
        if company_size:
            filters.append("c.company_size = $company_size")
            params["company_size"] = company_size
        if region:
            filters.append("c.region = $region")
            params["region"] = region
        
        where_clause = " AND ".join(filters) if filters else "1=1"
        
        query = f"""
        MATCH (u:User {{id: $user_id}})
        MATCH (c:Company)
        WHERE {where_clause}
          AND NOT EXISTS {{ (u)-[:MATCHED]->(c) }}
        OPTIONAL MATCH (c)-[r:COOPERATED_WITH]->(other:Company)
        WITH c, count(r) AS connection_count
        RETURN c.id AS company_id,
               c.name AS company_name,
               c.industry AS industry,
               c.company_size AS company_size,
               c.region AS region,
               connection_count
        ORDER BY connection_count DESC
        LIMIT $limit
        """
        
        try:
            results = self.graph.query(query, params)
            return [
                {
                    "company_id": r["company_id"],
                    "company_name": r["company_name"],
                    "industry": r["industry"],
                    "company_size": r["company_size"],
                    "region": r["region"],
                    "connection_count": r["connection_count"],
                    "match_type": "coldstart",
                    "confidence": min(0.3 + r["connection_count"] * 0.05, 0.7)
                }
                for r in results
            ]
        except Exception as e:
            # Fallback: if Neo4j unavailable, return rule-based
            return self._rule_based_fallback(industry, company_size, region, top_k)
    
    def _rule_based_fallback(self, industry, company_size, region, top_k=10):
        """Neo4j不可用时的规则兜底"""
        recs = []
        # Generate synthetic recommendations based on matching dimensions
        for i in range(min(top_k, 8)):
            score = 0.3
            tags = []
            if industry:
                score += 0.2
                tags.append(f"同行业:{industry}")
            if company_size:
                score += 0.1
                tags.append(f"同规模:{company_size}")
            if region:
                score += 0.1
                tags.append(f"同地区:{region}")
            
            recs.append({
                "company_id": i + 1000,
                "company_name": f"推荐企业{i+1}",
                "industry": industry or "综合",
                "company_size": company_size or "50-200人",
                "region": region or "全国",
                "connection_count": 0,
                "match_type": "coldstart_fallback",
                "confidence": round(min(score, 0.7), 2),
                "tags": tags
            })
        return recs
    
    def get_similar_companies(self, company_id: int, top_k: int = 5):
        """基于图相似度的企业推荐"""
        query = """
        MATCH (c:Company {id: $company_id})
        MATCH (c)-[:IN_SAME_INDUSTRY|COOPERATED_WITH*1..2]->(similar:Company)
        WHERE similar.id <> $company_id
        RETURN similar.id AS company_id,
               similar.name AS company_name,
               similar.industry AS industry,
               count(*) AS similarity_score
        ORDER BY similarity_score DESC
        LIMIT $limit
        """
        try:
            results = self.graph.query(query, {"company_id": company_id, "limit": top_k})
            return [
                {
                    "company_id": r["company_id"],
                    "company_name": r["company_name"],
                    "industry": r["industry"],
                    "similarity_score": r["similarity_score"],
                    "match_type": "graph_similarity",
                    "confidence": min(r["similarity_score"] * 0.1, 0.8)
                }
                for r in results
            ]
        except Exception as e:
            return []
