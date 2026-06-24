"""
推荐质量评估体系 (NDCG/MRR/Recall@K/Precision@K)

纯 numpy 实现，无外部评估框架依赖。
提供:
  - calculate_ndcg: NDCG@K
  - calculate_mrr: MRR
  - calculate_recall_at_k: Recall@K
  - calculate_precision_at_k: Precision@K
  - evaluate_matching_engine: 批量评估
  - generate_test_cases: 从DB自动生成评估数据集
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models import BusinessNeed, Product, UserEvent

logger = logging.getLogger(__name__)


# ============================================================
# 核心指标函数
# ============================================================


def calculate_ndcg(relevance_scores: list[float], k: int = 10) -> float:
    """
    计算 NDCG@K (Normalized Discounted Cumulative Gain)

    NDCG 衡量推荐排序质量，考虑相关性分数的位置衰减。
    值域 [0.0, 1.0]，越接近 1.0 表示排序越优。

    Args:
        relevance_scores: 推荐结果的相关性分数列表（按推荐顺序）
        k: 截断位置

    Returns:
        NDCG@K 值
    """
    if not relevance_scores:
        return 0.0

    actual_k = min(k, len(relevance_scores))
    scores = relevance_scores[:actual_k]

    # DCG: 折损累计增益
    dcg = sum((2**rel - 1) / math.log2(i + 2) for i, rel in enumerate(scores))

    # IDCG: 理想折损累计增益（相关性分数降序排列）
    ideal = sorted(scores, reverse=True)
    idcg = sum((2**rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal))

    if idcg == 0:
        return 0.0
    return dcg / idcg


def calculate_mrr(relevance_scores: list[float]) -> float:
    """
    计算 MRR (Mean Reciprocal Rank)

    第一个相关结果的排名的倒数。值域 [0.0, 1.0]。
    相关性分数 > 0 表示相关。

    Args:
        relevance_scores: 推荐结果的相关性分数列表（按推荐顺序）

    Returns:
        MRR 值
    """
    for i, score in enumerate(relevance_scores):
        if score > 0:
            return 1.0 / (i + 1)
    return 0.0


def calculate_recall_at_k(
    relevant_items: set[Any],
    recommended_items: list[Any],
    k: int = 10,
) -> float:
    """
    计算 Recall@K (召回率)

    在 top-K 推荐结果中，覆盖了多少比例的相关项。
    值域 [0.0, 1.0]。

    Args:
        relevant_items: 所有相关项的 ID 集合
        recommended_items: 推荐结果的 ID 列表（按推荐顺序）
        k: 截断位置

    Returns:
        Recall@K 值
    """
    if not relevant_items:
        return 0.0

    top_k = recommended_items[:k]
    if not top_k:
        return 0.0

    relevant_count = sum(1 for item in top_k if item in relevant_items)
    return relevant_count / len(relevant_items)


def calculate_precision_at_k(
    relevant_items: set[Any],
    recommended_items: list[Any],
    k: int = 10,
) -> float:
    """
    计算 Precision@K (精确率)

    在 top-K 推荐结果中，有多大比例是相关的。
    值域 [0.0, 1.0]。

    Args:
        relevant_items: 所有相关项的 ID 集合
        recommended_items: 推荐结果的 ID 列表（按推荐顺序）
        k: 截断位置

    Returns:
        Precision@K 值
    """
    if not recommended_items:
        return 0.0

    actual_k = min(k, len(recommended_items))
    if actual_k == 0:
        return 0.0

    top_k = recommended_items[:actual_k]
    relevant_count = sum(1 for item in top_k if item in relevant_items)
    return relevant_count / actual_k


def calculate_f1_at_k(
    relevant_items: set[Any],
    recommended_items: list[Any],
    k: int = 10,
) -> float:
    """
    计算 F1@K (F1 分数)

    Precision@K 和 Recall@K 的调和平均数。
    值域 [0.0, 1.0]。

    Args:
        relevant_items: 所有相关项的 ID 集合
        recommended_items: 推荐结果的 ID 列表（按推荐顺序）
        k: 截断位置

    Returns:
        F1@K 值
    """
    precision = calculate_precision_at_k(relevant_items, recommended_items, k)
    recall = calculate_recall_at_k(relevant_items, recommended_items, k)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


# ============================================================
# 批量评估函数
# ============================================================


def evaluate_matching_engine(
    db: Session,
    test_cases: list[dict],
    engine_cls: type = None,
    top_k: int = 20,
) -> dict:
    """
    对匹配引擎进行批量评估。

    每个 test_case 格式:
        {
            "need_id": int,           # 需求 ID（供需匹配用）
            "product_id": int,        # 或产品 ID
            "direction": str,         # "need_to_product" 或 "product_to_need"
            "relevant_item_ids": list[int],  # 预期的相关项 ID 列表
            "relevance_scores": list[float], # 可选，每项的相关性分数 (0~1)
            "label": str,             # 可选，测试案例名称
        }

    Args:
        db: 数据库会话
        test_cases: 测试用例列表
        engine_cls: 引擎类（默认使用 matching_engine.MatchEngine）
        top_k: 每个案例返回 top-K 结果

    Returns:
        评估报告 dict:
        {
            "summary": {
                "total_cases": int,
                "avg_ndcg@5": float,
                "avg_ndcg@10": float,
                "avg_mrr": float,
                "avg_recall@5": float,
                "avg_recall@10": float,
                "avg_precision@5": float,
                "avg_precision@10": float,
                "avg_f1@10": float,
            },
            "details": [
                {
                    "label": str,
                    "need_id": int,
                    "direction": str,
                    "ndcg@5": float,
                    "ndcg@10": float,
                    "mrr": float,
                    "recall@5": float,
                    "recall@10": float,
                    "precision@5": float,
                    "precision@10": float,
                    "f1@10": float,
                    "recommended_ids": list[int],
                    "relevant_ids": list[int],
                    "num_relevant": int,
                },
                ...
            ],
            "config": {
                "top_k": int,
                "strategy": str,
            },
        }
    """
    # 惰性导入避免循环依赖
    if engine_cls is None:
        from matching_engine import MatchEngine

        engine_cls = MatchEngine

    results = []
    ndcg5_list, ndcg10_list = [], []
    mrr_list = []
    recall5_list, recall10_list = [], []
    precision5_list, precision10_list = [], []
    f1_10_list = []

    for tc in test_cases:
        direction = tc.get("direction", "need_to_product")
        relevant_ids = set(tc.get("relevant_item_ids", []))
        relevance_scores = tc.get("relevance_scores", None)
        label = tc.get("label", f"case_{tc.get('need_id', tc.get('product_id', '?'))}")

        recommended_ids = []
        try:
            engine = engine_cls(db, strategy=tc.get("strategy", "v2"))

            if direction == "need_to_product":
                need_id = tc.get("need_id")
                if not need_id:
                    logger.warning(f"跳过 test_case '{label}': 缺少 need_id")
                    continue
                match_results = engine.match_needs_to_products(need_id, top_k=top_k)
                recommended_ids = [r.id for r in match_results]
            elif direction == "product_to_need":
                product_id = tc.get("product_id")
                if not product_id:
                    logger.warning(f"跳过 test_case '{label}': 缺少 product_id")
                    continue
                match_results = engine.match_products_to_needs(product_id, top_k=top_k)
                recommended_ids = [r.id for r in match_results]
            else:
                logger.warning(f"跳过 test_case '{label}': 未知 direction '{direction}'")
                continue
        except Exception as e:
            logger.error(f"test_case '{label}' 执行失败: {e}")
            recommended_ids = []

        # 构建 relevance_scores 序列（用于 NDCG/MRR）
        if relevance_scores is not None:
            # 使用传进来的相关性分数
            rel_scores = []
            score_map = dict(zip(tc.get("relevant_item_ids", []), relevance_scores))
            for rid in recommended_ids:
                rel_scores.append(score_map.get(rid, 0.0))
        else:
            # 二元相关：在 relevant_ids 中为 1.0，否则 0.0
            rel_scores = [1.0 if rid in relevant_ids else 0.0 for rid in recommended_ids]

        # 计算各项指标
        ndcg5 = calculate_ndcg(rel_scores, k=5)
        ndcg10 = calculate_ndcg(rel_scores, k=10)
        mrr = calculate_mrr(rel_scores)
        recall5 = calculate_recall_at_k(relevant_ids, recommended_ids, k=5)
        recall10 = calculate_recall_at_k(relevant_ids, recommended_ids, k=10)
        precision5 = calculate_precision_at_k(relevant_ids, recommended_ids, k=5)
        precision10 = calculate_precision_at_k(relevant_ids, recommended_ids, k=10)
        f1_10 = calculate_f1_at_k(relevant_ids, recommended_ids, k=10)

        ndcg5_list.append(ndcg5)
        ndcg10_list.append(ndcg10)
        mrr_list.append(mrr)
        recall5_list.append(recall5)
        recall10_list.append(recall10)
        precision5_list.append(precision5)
        precision10_list.append(precision10)
        f1_10_list.append(f1_10)

        results.append(
            {
                "label": label,
                "need_id": tc.get("need_id"),
                "product_id": tc.get("product_id"),
                "direction": direction,
                "ndcg@5": round(ndcg5, 4),
                "ndcg@10": round(ndcg10, 4),
                "mrr": round(mrr, 4),
                "recall@5": round(recall5, 4),
                "recall@10": round(recall10, 4),
                "precision@5": round(precision5, 4),
                "precision@10": round(precision10, 4),
                "f1@10": round(f1_10, 4),
                "recommended_ids": recommended_ids[:top_k],
                "relevant_ids": list(relevant_ids),
                "num_relevant": len(relevant_ids),
            }
        )

    n = len(results)
    report = {
        "summary": {
            "total_cases": n,
            "avg_ndcg@5": round(np.mean(ndcg5_list).item(), 4) if ndcg5_list else 0.0,
            "avg_ndcg@10": round(np.mean(ndcg10_list).item(), 4) if ndcg10_list else 0.0,
            "avg_mrr": round(np.mean(mrr_list).item(), 4) if mrr_list else 0.0,
            "avg_recall@5": round(np.mean(recall5_list).item(), 4) if recall5_list else 0.0,
            "avg_recall@10": round(np.mean(recall10_list).item(), 4) if recall10_list else 0.0,
            "avg_precision@5": round(np.mean(precision5_list).item(), 4) if precision5_list else 0.0,
            "avg_precision@10": round(np.mean(precision10_list).item(), 4) if precision10_list else 0.0,
            "avg_f1@10": round(np.mean(f1_10_list).item(), 4) if f1_10_list else 0.0,
        },
        "details": results,
        "config": {
            "top_k": top_k,
        },
    }
    return report


# ============================================================
# 测试数据生成
# ============================================================


def _extract_feedback_signals(db: Session, days_back: int = 90) -> dict[tuple[int, int], float]:
    """
    从数据库中提取用户反馈信号作为 relevance ground truth。

    信号来源（按优先级）:
      1. UserEvent: event_type in ('product_click', 'need_view', 'add_cart')
         对应 (target_type=product, target_id) 或 (target_type=need, target_id)
      2. OnlineMatchingFeedback: rating >= 4 的评分

    Returns:
        dict mapping (need_id_or_product_id, related_item_id) -> relevance_score
        relevance_score 计算方式: 点击=0.3, 收藏=0.6, 评分>=4=0.8, 评分=5=1.0
    """
    signals: dict[tuple[int, int], float] = {}
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    try:
        # 1. 从 UserEvent 提取
        events = db.query(UserEvent).filter(UserEvent.created_at >= cutoff).all()
        for evt in events:
            if evt.event_type == "product_click" and evt.target_type == "product" and evt.target_id:
                # user_id 看到 product_id 的关联 need (从 need_view 事件推断)
                key = (evt.target_id, evt.user_id)
                signals[key] = max(signals.get(key, 0.0), 0.3)
            elif evt.event_type == "need_view" and evt.target_type == "need" and evt.target_id:
                key = (evt.target_id, evt.user_id)
                signals[key] = max(signals.get(key, 0.0), 0.3)
            elif evt.event_type == "add_cart" and evt.target_type == "product" and evt.target_id:
                key = (evt.target_id, evt.user_id)
                signals[key] = max(signals.get(key, 0.0), 0.6)
    except Exception as e:
        logger.warning(f"UserEvent 反馈信号提取失败: {e}")

    try:
        # 2. 从 OnlineMatchingFeedback 提取
        from app.models import OnlineMatchingFeedback

        feedbacks = (
            db.query(OnlineMatchingFeedback)
            .filter(OnlineMatchingFeedback.rating >= 4)
            .filter(OnlineMatchingFeedback.created_at >= cutoff)
            .all()
        )
        for fb in feedbacks:
            # event_id 是 feedback 关联的对接会，user_id 是反馈者
            # 这里将 event_id 作为关联信号
            key = (fb.event_id, fb.user_id)
            score = 0.8 if fb.rating == 4 else 1.0
            signals[key] = max(signals.get(key, 0.0), score)
    except Exception as e:
        logger.debug(f"OnlineMatchingFeedback 反馈信号提取跳过: {e}")

    return signals


def generate_test_cases(
    db: Session,
    max_cases: int = 50,
    min_products_per_need: int = 2,
    days_back: int = 90,
) -> list[dict]:
    """
    从数据库中自动生成评估测试数据集。

    策略:
      1. 提取最近 days_back 天内创建的 BusinessNeed
      2. 对于每个 Need，找到同类目下的 approved Products
      3. 用用户反馈信号标记 relevance
      4. 构造 test_case dict

    Args:
        db: 数据库会话
        max_cases: 最大生成数量
        min_products_per_need: 每个 need 至少匹配多少个产品才纳入
        days_back: 回溯天数

    Returns:
        test_cases 列表，可直接传入 evaluate_matching_engine
    """
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    test_cases: list[dict] = []

    try:
        # 获取所有 open 状态的需求（或最近创建的）
        needs = (
            db.query(BusinessNeed)
            .filter(BusinessNeed.status == "open")
            .filter(BusinessNeed.created_at >= cutoff)
            .order_by(BusinessNeed.created_at.desc())
            .limit(max_cases * 3)  # 多取一些用于过滤
            .all()
        )

        if not needs:
            # 回退：取所有 open 需求
            needs = db.query(BusinessNeed).filter(BusinessNeed.status == "open").limit(max_cases * 3).all()

        # 获取所有 approved 产品
        products = db.query(Product).filter(Product.status == "approved").all()
        product_map = {p.id: p for p in products}

        # 提取反馈信号
        signals = _extract_feedback_signals(db, days_back)

        for need in needs:
            if len(test_cases) >= max_cases:
                break

            # 找到同类目产品作为候选相关项
            candidate_products = []
            for p in products:
                # 类目匹配或相似
                if need.category and p.category:
                    if need.category.lower() == p.category.lower():
                        candidate_products.append(p)
                    elif (
                        need.category
                        and p.category
                        and (need.category.lower() in p.category.lower() or p.category.lower() in need.category.lower())
                    ):
                        candidate_products.append(p)

            if not candidate_products:
                continue

            # 给候选产品分配相关性分数
            relevant_ids = []
            relevance_scores = []

            for cp in candidate_products:
                # 从反馈信号中查找
                signal_key = (need.id, cp.id)
                alt_key = (cp.id, need.id)
                score = signals.get(signal_key, signals.get(alt_key, 0.0))

                # 如果没有直接反馈信号，根据类目匹配度给予基础分
                if score == 0.0:
                    # 类目相同给一个弱相关基线
                    if need.category and cp.category and need.category.lower() == cp.category.lower():
                        score = 0.3  # 弱相关

                if score > 0:
                    relevant_ids.append(cp.id)
                    relevance_scores.append(score)

            # 必须有足够的相关项才有评估意义
            if len(relevant_ids) < min_products_per_need:
                continue

            test_cases.append(
                {
                    "need_id": need.id,
                    "direction": "need_to_product",
                    "relevant_item_ids": relevant_ids,
                    "relevance_scores": relevance_scores,
                    "label": f"need_{need.id}_{need.title[:20]}",
                    "strategy": "v2",
                }
            )

        logger.info(
            "评估测试数据集生成完成",
            extra={
                "total_cases": len(test_cases),
                "total_needs_scanned": len(needs),
                "total_products": len(products),
                "signals_found": len(signals),
            },
        )

    except Exception as e:
        logger.error(f"测试数据集生成失败: {e}")

    return test_cases


def generate_test_cases_from_feedback(
    db: Session,
    max_cases: int = 30,
    min_interactions: int = 1,
    days_back: int = 90,
) -> list[dict]:
    """
    从用户交互反馈数据生成更精准的评估测试集。

    利用 UserEvent 中的 product_click 事件，找到用户同时浏览过的
    need-product 对，构建 ground truth。

    Args:
        db: 数据库会话
        max_cases: 最大生成数量
        min_interactions: 最小交互数阈值
        days_back: 回溯天数

    Returns:
        test_cases 列表
    """
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    test_cases: list[dict] = []

    try:
        # 获取有交互行为的 need_id 列表
        need_view_events = (
            db.query(UserEvent)
            .filter(UserEvent.event_type == "need_view")
            .filter(UserEvent.target_type == "need")
            .filter(UserEvent.created_at >= cutoff)
            .all()
        )

        # 统计每个 need 的交互用户
        need_user_map: dict[int, set[int]] = {}
        for evt in need_view_events:
            if evt.target_id and evt.user_id:
                need_user_map.setdefault(evt.target_id, set()).add(evt.user_id)

        # 获取有交互行为的产品
        product_click_events = (
            db.query(UserEvent)
            .filter(UserEvent.event_type.in_(["product_click", "add_cart"]))
            .filter(UserEvent.target_type == "product")
            .filter(UserEvent.created_at >= cutoff)
            .all()
        )

        product_user_map: dict[int, set[int]] = {}
        product_score_map: dict[int, float] = {}
        for evt in product_click_events:
            if evt.target_id and evt.user_id:
                product_user_map.setdefault(evt.target_id, set()).add(evt.user_id)
                # click=0.3, add_cart=0.6
                score = 0.6 if evt.event_type == "add_cart" else 0.3
                product_score_map[evt.target_id] = max(product_score_map.get(evt.target_id, 0.0), score)

        # 为每个 need 找到共同用户交互过的产品
        for need_id, users in need_user_map.items():
            if len(test_cases) >= max_cases:
                break

            relevant_ids = []
            relevance_scores = []

            for product_id, product_users in product_user_map.items():
                # 如果有共同用户交互过，认为相关
                common_users = users & product_users
                if len(common_users) >= min_interactions:
                    relevant_ids.append(product_id)
                    relevance_scores.append(max(product_score_map.get(product_id, 0.3), 0.3))

            if len(relevant_ids) >= 2:
                need = db.query(BusinessNeed).filter(BusinessNeed.id == need_id).first()
                label = f"need_{need_id}"
                if need:
                    label = f"need_{need_id}_{need.title[:20]}"

                test_cases.append(
                    {
                        "need_id": need_id,
                        "direction": "need_to_product",
                        "relevant_item_ids": relevant_ids,
                        "relevance_scores": relevance_scores,
                        "label": label,
                        "strategy": "v2",
                    }
                )

        logger.info(
            "基于反馈的评估数据集生成完成",
            extra={
                "total_cases": len(test_cases),
                "needs_with_interactions": len(need_user_map),
                "products_with_interactions": len(product_user_map),
            },
        )

    except Exception as e:
        logger.error(f"基于反馈的测试数据集生成失败: {e}")

    return test_cases


# ============================================================
# 快捷评估入口
# ============================================================


def quick_evaluate(
    db: Session,
    engine_cls: type = None,
    max_cases: int = 20,
    top_k: int = 20,
) -> dict:
    """
    一键评估：自动生成测试集 → 运行评估 → 返回报告。

    这是最常用的入口函数，适合日常开发中快速验证匹配质量。

    Args:
        db: 数据库会话
        engine_cls: 引擎类（默认使用 matching_engine.MatchEngine）
        max_cases: 最大测试案例数
        top_k: 每个案例返回 top-K 结果

    Returns:
        评估报告 dict
    """
    logger.info("=== 开始快速评估 ===")

    # 先用反馈数据生成测试集
    test_cases = generate_test_cases_from_feedback(db, max_cases=max_cases)
    if len(test_cases) < 3:
        logger.info(f"反馈数据不足 ({len(test_cases)} 条)，回退到基于类目的测试集")
        test_cases = generate_test_cases(db, max_cases=max_cases)

    if not test_cases:
        logger.warning("无法生成测试数据集，返回空报告")
        return {
            "summary": {
                "total_cases": 0,
                "avg_ndcg@5": 0.0,
                "avg_ndcg@10": 0.0,
                "avg_mrr": 0.0,
                "avg_recall@5": 0.0,
                "avg_recall@10": 0.0,
                "avg_precision@5": 0.0,
                "avg_precision@10": 0.0,
                "avg_f1@10": 0.0,
            },
            "details": [],
            "config": {"top_k": top_k},
            "note": "无法生成测试数据集，请确保数据库中有 BusinessNeed 和 Product 数据",
        }

    report = evaluate_matching_engine(db, test_cases, engine_cls=engine_cls, top_k=top_k)

    logger.info(
        "=== 快速评估完成 ===",
        extra={
            "total_cases": report["summary"]["total_cases"],
            "avg_ndcg@10": report["summary"]["avg_ndcg@10"],
            "avg_mrr": report["summary"]["avg_mrr"],
            "avg_recall@10": report["summary"]["avg_recall@10"],
        },
    )

    return report
