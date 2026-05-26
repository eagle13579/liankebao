"""
链客宝 AI 供需匹配引擎模块
=============================

功能:
  1. MatchEngine 类 — 纯规则引擎（不调用外部API）
     - match_needs_to_products(need_id) → 返回匹配的产品列表和匹配分数
     - match_products_to_needs(product_id) → 返回匹配的需求列表和匹配分数
  2. 匹配规则：关键词匹配 / 类目匹配 / 价格区间匹配
  3. API:
     - GET /api/matching/needs/{id}/products → 需求匹配产品
     - GET /api/matching/products/{id}/needs → 产品匹配需求
     - POST /api/matching/refresh → 重建索引

注册方式（在 main.py 中）:
    import matching_engine as matching_engine_module
    app.include_router(matching_engine_module.router)
"""
import json
import logging
import re
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models import User, Product, BusinessNeed
from app.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matching", tags=["AI供需匹配"])


# ===== Pydantic 响应模型 =====

class MatchResult(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    match_score: float  # 0.0 ~ 1.0
    match_reasons: List[str]


class MatchResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[MatchResult]


# ===== 匹配引擎 =====

class MatchEngine:
    """
    纯规则匹配引擎（不调用外部 API）
    
    匹配规则（权重累加）:
      1. 类目匹配 (0~40分): 类目完全相同得40分，部分匹配得10~30分
      2. 关键词匹配 (0~40分): 标题/描述中匹配到关键词
      3. 价格区间匹配 (0~20分): 需求预算与产品价格重叠度
    """

    # 类目映射关系（用于相似类目匹配）
    CATEGORY_SYNONYMS = {
        "大健康": ["健康", "保健品", "养生", "医疗", "大健康"],
        "食品": ["零食", "特产", "农产品", "有机", "食品/大健康"],
        "企业服务": ["企业", "商务", "法律", "财税", "咨询", "企业服务"],
        "企业家服务": ["企业", "商务", "企业家服务", "企业服务"],
        "教育培训": ["培训", "课程", "教育", "训练营", "学习", "教育培训"],
        "科技产品": ["AI", "智能", "软件", "SaaS", "科技", "SaaS硬件"],
        "SaaS硬件": ["SaaS", "硬件", "智能", "科技产品"],
        "消费品": ["日用品", "快消品", "生活", "消费品"],
        "企业家服务": ["名片", "社交", "商务"],
    }

    def __init__(self, db: Session):
        self.db = db

    def _normalize_text(self, text_str: Optional[str]) -> str:
        """规范化文本：转小写、去标点"""
        if not text_str:
            return ""
        text_str = text_str.lower().strip()
        text_str = re.sub(r'[^\w\u4e00-\u9fff\s]', ' ', text_str)
        return text_str

    def _extract_keywords(self, text_str: Optional[str]) -> List[str]:
        """从文本中提取关键词（中文分词简化版）"""
        if not text_str:
            return []
        normalized = self._normalize_text(text_str)
        # 按空格和常见分隔符分割
        tokens = re.split(r'[\s,，、/／;；]+', normalized)
        # 过滤短词（单字或无意义词）
        stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
                      "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
                      "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "为", "与",
                      "及", "等", "或", "之", "以", "被", "让", "给", "对", "从", "把",
                      "向", "能", "做", "用", "买", "卖", "找", "寻", "求", "供", "需"}
        keywords = [t for t in tokens if len(t) >= 2 and t not in stop_words]
        return list(set(keywords))

    def _match_category(self, product_category: Optional[str], need_category: Optional[str]) -> Tuple[float, List[str]]:
        """类目匹配打分 (0~40分)"""
        reasons = []
        if not product_category or not need_category:
            return 0.0, reasons

        pc = self._normalize_text(product_category)
        nc = self._normalize_text(need_category)

        # 完全相同
        if pc == nc:
            return 40.0, ["类目完全匹配"]

        # 检查是否是同类目（通过同义词映射）
        for cat_name, synonyms in self.CATEGORY_SYNONYMS.items():
            cat_lower = cat_name.lower()
            syn_lower = [s.lower() for s in synonyms]
            pc_match = any(s in pc or pc in s for s in [cat_lower] + syn_lower)
            nc_match = any(s in nc or nc in s for s in [cat_lower] + syn_lower)
            if pc_match and nc_match:
                return 30.0, [f"类目匹配: 均属于「{cat_name}」类"]

        # 部分匹配（类目名称有共同字符）
        similarity = SequenceMatcher(None, pc, nc).ratio()
        if similarity > 0.3:
            score = round(10 + similarity * 20, 1)  # 10~30分
            return min(score, 30.0), [f"类目部分匹配 (相似度{int(similarity*100)}%)"]

        return 0.0, reasons

    def _match_keywords(self, product: Product, need: BusinessNeed) -> Tuple[float, List[str]]:
        """关键词匹配打分 (0~40分)"""
        reasons = []

        # 提取双方的文本内容
        prod_texts = [
            product.name or "",
            product.description or "",
            product.tags or "",
            product.brand or "",
            product.category or "",
        ]
        need_texts = [
            need.title or "",
            need.description or "",
            need.category or "",
        ]

        prod_keywords = self._extract_keywords(" ".join(prod_texts))
        need_keywords = self._extract_keywords(" ".join(need_texts))

        if not prod_keywords or not need_keywords:
            return 0.0, reasons

        # 计算关键词匹配
        prod_set = set(prod_keywords)
        need_set = set(need_keywords)

        matched = prod_set & need_set
        if not matched:
            return 0.0, reasons

        match_count = len(matched)
        total_possible = min(len(prod_set), len(need_set))
        if total_possible == 0:
            return 0.0, reasons

        # 评分: 匹配越多分数越高
        ratio = match_count / total_possible
        score = min(ratio * 40.0, 40.0)

        matched_str = ", ".join(list(matched)[:5])
        reasons.append(f"关键词匹配 ({match_count}个): {matched_str}")

        return round(score, 1), reasons

    def _parse_budget(self, budget_str: Optional[str]) -> Optional[Tuple[float, float]]:
        """解析预算字符串，返回 (min, max)"""
        if not budget_str:
            return None
        budget_str = budget_str.strip()
        # 匹配 "10万-50万" 或 "10万~50万" 或 "10-50万"
        pattern = r'(\d+(?:\.\d+)?)\s*(?:万|w)?\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*(?:万|w)?'
        m = re.search(pattern, budget_str)
        if m:
            min_val = float(m.group(1))
            max_val = float(m.group(2))
            # 如果是万为单位，转换为元
            if '万' in budget_str or 'w' in budget_str.lower():
                min_val *= 10000
                max_val *= 10000
            return (min_val, max_val)

        # 匹配 "10万以上" 或 ">5000"
        pattern2 = r'(?:>|大于|不低于|以上)\s*(\d+(?:\.\d+)?)\s*(?:万|w)?'
        m = re.search(pattern2, budget_str)
        if m:
            val = float(m.group(1))
            if '万' in budget_str or 'w' in budget_str.lower():
                val *= 10000
            return (val, float('inf'))

        # 匹配 "5万以内" 或 "<10000"
        pattern3 = r'(?:<|小于|不超过|以内)\s*(\d+(?:\.\d+)?)\s*(?:万|w)?'
        m = re.search(pattern3, budget_str)
        if m:
            val = float(m.group(1))
            if '万' in budget_str or 'w' in budget_str.lower():
                val *= 10000
            return (0, val)

        return None

    def _match_price_range(self, product: Product, need: BusinessNeed) -> Tuple[float, List[str]]:
        """价格区间匹配打分 (0~20分)"""
        reasons = []

        # 产品价格
        product_price = getattr(product, 'sale_price', None) or product.price

        # 需求预算
        budget_range = self._parse_budget(need.budget)
        if not budget_range:
            return 0.0, reasons

        min_budget, max_budget = budget_range

        # 检查产品价格是否在预算范围内
        if min_budget <= product_price <= max_budget:
            # 在范围内，计算匹配度（越靠近中间分数越高）
            span = max_budget - min_budget
            if span > 0:
                center = (min_budget + max_budget) / 2
                distance = abs(product_price - center) / span
                score = 20.0 * (1 - distance)
                reasons.append(f"价格匹配: ¥{product_price:.0f} 在预算 ¥{min_budget:.0f}~¥{max_budget:.0f} 内")
                return round(max(score, 10.0), 1), reasons
            else:
                return 20.0, [f"价格匹配: ¥{product_price:.0f} 符合预算"]

        # 价格偏高或偏低，给少量分
        if max_budget != float('inf') and product_price > max_budget:
            ratio = max_budget / max(product_price, 1)
            if ratio >= 0.5:
                return round(ratio * 10, 1), [f"价格略高于预算 (¥{product_price:.0f} > ¥{max_budget:.0f})"]
        elif min_budget > 0 and product_price < min_budget:
            ratio = product_price / min_budget
            if ratio >= 0.5:
                return round(ratio * 10, 1), [f"价格低于预算 (¥{product_price:.0f} < ¥{min_budget:.0f})"]

        return 0.0, reasons

    def _calculate_match(self, product: Product, need: BusinessNeed) -> MatchResult:
        """计算单个产品-需求对的匹配分数和原因"""
        total_score = 0.0
        all_reasons = []

        # 1. 类目匹配 (0~40)
        cat_score, cat_reasons = self._match_category(product.category, need.category)
        total_score += cat_score
        all_reasons.extend(cat_reasons)

        # 2. 关键词匹配 (0~40)
        kw_score, kw_reasons = self._match_keywords(product, need)
        total_score += kw_score
        all_reasons.extend(kw_reasons)

        # 3. 价格区间匹配 (0~20)
        price_score, price_reasons = self._match_price_range(product, need)
        total_score += price_score
        all_reasons.extend(price_reasons)

        # 总分归一化到 0~1
        final_score = round(total_score / 100.0, 2)
        final_score = min(max(final_score, 0.0), 1.0)

        return MatchResult(
            id=product.id,
            title=product.name,
            description=product.description[:200] if product.description else None,
            category=product.category,
            match_score=final_score,
            match_reasons=all_reasons if all_reasons else ["基础匹配"],
        )

    def _need_to_product_result(self, need: BusinessNeed, product: Product) -> MatchResult:
        """计算需求对产品的匹配（结果中显示需求信息）"""
        result = self._calculate_match(product, need)
        # 交换信息：这里显示的是需求信息
        return MatchResult(
            id=need.id,
            title=need.title,
            description=need.description[:200] if need.description else None,
            category=need.category,
            match_score=result.match_score,
            match_reasons=result.match_reasons,
        )

    def match_needs_to_products(self, need_id: int, top_k: int = 20) -> List[MatchResult]:
        """根据需求匹配产品"""
        need = self.db.query(BusinessNeed).filter(BusinessNeed.id == need_id).first()
        if not need:
            return []

        # 获取所有已上架的产品
        products = self.db.query(Product).filter(Product.status == "approved").all()

        results = []
        for product in products:
            result = self._calculate_match(product, need)
            if result.match_score > 0:
                results.append(result)

        # 按匹配分数降序排列
        results.sort(key=lambda r: r.match_score, reverse=True)
        return results[:top_k]

    def match_products_to_needs(self, product_id: int, top_k: int = 20) -> List[MatchResult]:
        """根据产品匹配需求"""
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return []

        # 获取所有 open 状态的需求
        needs = self.db.query(BusinessNeed).filter(BusinessNeed.status == "open").all()

        results = []
        for need in needs:
            result = self._need_to_product_result(need, product)
            if result.match_score > 0:
                results.append(result)

        # 按匹配分数降序排列
        results.sort(key=lambda r: r.match_score, reverse=True)
        return results[:top_k]


# ===== API Endpoints =====

def get_engine(db: Session = Depends(get_db)) -> MatchEngine:
    """依赖注入：创建匹配引擎实例"""
    return MatchEngine(db)


@router.get("/needs/{need_id}/products")
def match_needs_to_products(
    need_id: int,
    top_k: int = Query(20, ge=1, le=100, description="返回结果数量上限"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据需求ID匹配相关产品"""
    engine = MatchEngine(db)
    results = engine.match_needs_to_products(need_id, top_k=top_k)
    return {
        "code": 200,
        "message": "success",
        "data": [r.model_dump() for r in results],
    }


@router.get("/products/{product_id}/needs")
def match_products_to_needs(
    product_id: int,
    top_k: int = Query(20, ge=1, le=100, description="返回结果数量上限"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据产品ID匹配相关需求"""
    engine = MatchEngine(db)
    results = engine.match_products_to_needs(product_id, top_k=top_k)
    return {
        "code": 200,
        "message": "success",
        "data": [r.model_dump() for r in results],
    }


@router.post("/refresh")
def refresh_index(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    重建匹配索引（当前为无状态引擎，刷新即预热缓存）
    """
    # 预加载数据预热
    products = db.query(Product).filter(Product.status == "approved").count()
    needs = db.query(BusinessNeed).filter(BusinessNeed.status == "open").count()
    logger.info(
        "匹配索引已刷新",
        extra={"products": products, "needs": needs, "user": current_user.username},
    )
    return {
        "code": 200,
        "message": "匹配索引已刷新",
        "data": {
            "products_count": products,
            "needs_count": needs,
            "status": "ready",
        },
    }
