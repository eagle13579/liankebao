"""
链客宝 — BGE-M3 跨境匹配管线 (模拟/真实双模回退)
================================================

从 backend/ml/models/cross_border.py 升级封装：
  - attempt_import() 惰性检测 FlagEmbedding 可用性
  - 可用 → 真实 BGE-M3 推理 (BAAI/bge-m3)
  - 不可用 → 模拟模式 (带确定性随机嵌入), 打印警告
  - search_cross_border(query, k=5) → list[dict] 快速调用入口

约束: 不修改 cross_border.py, 仅在其基础上包装。
"""

from __future__ import annotations

import logging
import sys
import os
import warnings
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径: 确保能从项目根目录导入 ml.models.cross_border
# ---------------------------------------------------------------------------
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_BGE_M3_REAL: bool = False  # attempt_import() 后设置
_EMBEDDER_CACHE: Any = None  # 延迟加载的 BgeM3Embedder 实例


# ---------------------------------------------------------------------------
# attempt_import: 惰性检测 FlagEmbedding 并设置全局标志
# ---------------------------------------------------------------------------
def attempt_import() -> bool:
    """检测 FlagEmbedding 是否可用, 返回 True=真实推理, False=模拟回退.

    结果缓存到全局 _BGE_M3_REAL, 多次调用只检测一次.
    """
    global _BGE_M3_REAL
    if _BGE_M3_REAL:
        return True

    try:
        import importlib.util
        spec = importlib.util.find_spec("FlagEmbedding")
        if spec is None:
            warnings.warn(
                "FlagEmbedding 未安装 — 使用 BGE-M3 模拟模式回退。"
                " 运行: pip install FlagEmbedding",
                RuntimeWarning,
                stacklevel=2,
            )
            _BGE_M3_REAL = False
            return False

        # 尝试加载实际模型类, 确认可用
        from FlagEmbedding import BGEM3FlagModel  # noqa: F401

        _BGE_M3_REAL = True
        logger.info("✅ BGE-M3 真实推理可用 (FlagEmbedding 已安装)")
        return True

    except ImportError:
        warnings.warn(
            "FlagEmbedding 导入失败 — 使用 BGE-M3 模拟模式回退。"
            " 运行: pip install FlagEmbedding",
            RuntimeWarning,
            stacklevel=2,
        )
        _BGE_M3_REAL = False
        return False
    except Exception as exc:
        warnings.warn(
            f"FlagEmbedding 加载异常 ({exc}) — 使用 BGE-M3 模拟模式回退",
            RuntimeWarning,
            stacklevel=2,
        )
        _BGE_M3_REAL = False
        return False


# ---------------------------------------------------------------------------
# get_embedder: 获取 (缓存的) BgeM3Embedder 实例
# ---------------------------------------------------------------------------
def get_embedder() -> Any:
    """获取 BgeM3Embedder 单例实例.

    如果 FlagEmbedding 可用则使用真实模型, 否则使用模拟降级.
    """
    global _EMBEDDER_CACHE
    if _EMBEDDER_CACHE is not None:
        return _EMBEDDER_CACHE

    # 先检测 FlagEmbedding 可用性 (惰性)
    is_real = attempt_import()

    # 延迟导入 BgeM3Embedder (确保 sys.path 已配置)
    from ml.models.cross_border import BgeM3Embedder

    embedder = BgeM3Embedder(model_name="BAAI/bge-m3", use_fp16=False)

    if embedder.is_simulated:
        logger.warning(
            "BgeM3Embedder 运行在模拟模式 — 返回的向量为确定性随机值, "
            "仅适用于开发/测试。安装 FlagEmbedding 以启用真实推理。"
        )
    else:
        logger.info("BgeM3Embedder 运行在真实推理模式 — BAAI/bge-m3")

    _EMBEDDER_CACHE = embedder
    return embedder


# ---------------------------------------------------------------------------
# search_cross_border: 高层快速调用入口
# ---------------------------------------------------------------------------
def search_cross_border(
    query: str,
    k: int = 5,
    candidates: Optional[List[Dict[str, Any]]] = None,
    mode: str = "auto",
    lang: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """执行跨境语义匹配搜索.

    Args:
        query:  查询文本 (中文/韩语/英语)
        k:      返回 top-K 结果 (默认 5)
        candidates: 候选企业列表.
                    每项含 enterprise_id, name, description, lang 等.
                    若为 None, 返回空结果.
        mode:   匹配模式 — "auto" (默认), "direct", "translate"
        lang:   查询语言代码 — None 则自动检测 (zh/ko/en)

    Returns:
        按分数降序的匹配结果列表, 每项:
            enterprise_id  (str|int)
            score          (float)  综合匹配分 0~1
            cross_border_score (float)
            match_score    (float)
            source_lang    (str)
            target_lang    (str)
            enterprise_name (str)
            translated_query (str, 仅 translate 模式)

    用法:
        >>> results = search_cross_border("韩国芯片供应商", k=3)
        >>> for r in results:
        ...     print(r["enterprise_id"], r["score"])
    """
    if not candidates:
        return []

    # 确保检测过 FlagEmbedding
    attempt_import()

    # 延迟导入 (确保 sys.path 已设置)
    from ml.models.cross_border import (
        CrossBorderMatcher,
        CrossBorderPipeline,
        CrossBorderMatchResult,
    )

    embedder = get_embedder()
    matcher = CrossBorderMatcher(embedder=embedder)
    pipe = CrossBorderPipeline(matcher)

    result = pipe.run(
        query_text=query,
        candidates=candidates,
        lang=lang,
        mode=mode,
        top_k=k,
    )

    # 序列化为纯 dict 列表
    serialized: List[Dict[str, Any]] = []
    for r in result.get("results", []):
        if isinstance(r, CrossBorderMatchResult):
            serialized.append({
                "enterprise_id": r.enterprise_id,
                "score": r.score,
                "cross_border_score": r.cross_border_score,
                "match_score": r.match_score,
                "source_lang": r.source_lang,
                "target_lang": r.target_lang,
                "enterprise_name": r.details.get("enterprise_name", ""),
                "translated_query": r.translated_query,
            })
        elif isinstance(r, dict):
            # 兜底: 已序列化
            serialized.append(r)

    logger.info(
        "search_cross_border: query=%r lang=%s mode=%s results=%d",
        query[:60],
        result.get("detected_lang", "?"),
        result.get("mode", "?"),
        len(serialized),
    )
    return serialized


# ---------------------------------------------------------------------------
# 便捷变量: 暴露 real/simulated 状态
# ---------------------------------------------------------------------------
def is_real() -> bool:
    """返回当前 BGE-M3 是否为真实推理模式."""
    attempt_import()
    return _BGE_M3_REAL


# ---------------------------------------------------------------------------
# __init__-style 快速自检
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("=" * 60)
    print("  BGE-M3 跨境匹配管线 — 自检")
    print("=" * 60)

    real = attempt_import()
    if real:
        print("  ✅ FlagEmbedding 已安装 — 将使用真实 BGE-M3 推理")
    else:
        print("  ⚠️  FlagEmbedding 未安装 — 使用模拟模式 (确定性随机向量)")
        print("     运行: pip install FlagEmbedding")

    embedder = get_embedder()
    print(f"  嵌入器模拟模式: {embedder.is_simulated}")

    # 快速验证: 编码一段文本
    test_result = embedder.encode(["链客宝跨境匹配测试"])
    dense = test_result.get("dense_vecs")
    if dense is not None:
        print(f"  向量维度: {dense.shape}")
        print(f"  向量范数: {float((dense ** 2).sum() ** 0.5):.4f}")

    print("  ✅ 自检完成")
    print("=" * 60)
