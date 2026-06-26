"""链客宝 — 跨境匹配引擎 (中/韩/英多语言匹配)

利用 BGE-M3 的多向量能力实现跨语言匹配:
  - 中/韩/英 共同语义空间
  - dense + sparse 混合检索
  - 先翻译再匹配 (精度优先) vs 直接跨语言匹配 (效率优先)

架构:
  CrossBorderMatcher      核心匹配器, 作为 MatchingAPI 的插件
  CrossBorderPipeline     高层管线 (自动语言检测 + 跨语言映射)
  BgeM3Embedder           BGE-M3 模型封装 (带模拟降级)

依赖: P3-1-C ✅ (i18n已完成)

Author: 䑏疏 (P8, 跨境部, 跨境匹配/Korean市场)
"""

from __future__ import annotations

import logging
import re
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BGE-M3 可用性检测 (延迟导入, 避免模块加载时卡住)
# ---------------------------------------------------------------------------
BGE_M3_AVAILABLE: bool = False


def _check_bge_m3() -> bool:
    """惰性检测 BGE-M3 是否可用"""
    global BGE_M3_AVAILABLE
    if BGE_M3_AVAILABLE:
        return True
    try:
        # 先检查是否安装了 FlagEmbedding 包
        import importlib.util
        spec = importlib.util.find_spec("FlagEmbedding")
        if spec is None:
            logger.info("FlagEmbedding 未安装, 使用 BGE-M3 模拟模式(仅用于测试)")
            return False
        from FlagEmbedding import BGEM3FlagModel  # noqa: F401
        BGE_M3_AVAILABLE = True
        return True
    except Exception:
        logger.info("FlagEmbedding 加载失败, 使用 BGE-M3 模拟模式")
        return False

# ---------------------------------------------------------------------------
# 语言检测 — 支持中/韩/英
# ---------------------------------------------------------------------------
# Unicode 范围
_CJK_UNIFIED_IDEOGRAPHS = range(0x4E00, 0x9FFF)
_HANGUL_SYLLABLES = range(0xAC00, 0xD7AF)
_HANGUL_JAMO = range(0x1100, 0x11FF)
_HANGUL_COMPAT_JAMO = range(0x3130, 0x318F)

LANG_CODES = {"zh": "zh", "ko": "ko", "en": "en"}


def detect_language(text: str) -> str:
    """检测文本语言: 中文(zh) / 韩语(ko) / 英语(en)

    逻辑:
      1. 统计各语种字符数量
      2. 占比最高的判定为对应语言
      3. 若无明显特征 => 英语
    """
    if not text or not text.strip():
        return "en"

    chars_zh = 0
    chars_ko = 0
    chars_en = 0
    total_letters = 0

    for ch in text.strip():
        cp = ord(ch)
        # 中文
        if cp in _CJK_UNIFIED_IDEOGRAPHS:
            chars_zh += 1
            total_letters += 1
        # 韩文
        elif (
            cp in _HANGUL_SYLLABLES
            or cp in _HANGUL_JAMO
            or cp in _HANGUL_COMPAT_JAMO
        ):
            chars_ko += 1
            total_letters += 1
        # 英文 / 数字
        elif ch.isalpha() and cp < 0x1100:
            chars_en += 1
            total_letters += 1
        else:
            # 标点/空格 — 跳过
            pass

    if total_letters == 0:
        return "en"

    ratio_zh = chars_zh / total_letters
    ratio_ko = chars_ko / total_letters
    ratio_en = chars_en / total_letters

    # 阈值: 超过 30% 即判定为该语言
    if ratio_zh >= 0.3:
        return "zh"
    if ratio_ko >= 0.3:
        return "ko"
    return "en"


# ---------------------------------------------------------------------------
# 跨境企业评分因子
# ---------------------------------------------------------------------------
@dataclass
class CrossBorderFactors:
    """影响跨境匹配倾向的关键因子"""
    has_export_license: bool = False        # 有出口许可证
    has_foreign_business: bool = False      # 有涉外业务
    target_markets: List[str] = field(default_factory=list)  # 目标市场
    language_capabilities: List[str] = field(default_factory=list)  # 语言能力
    cross_border_years: float = 0.0         # 跨境经验年限
    international_certifications: int = 0   # 国际认证数量
    overseas_office: bool = False           # 有海外办事处


# ---------------------------------------------------------------------------
# BGE-M3 嵌入器
# ---------------------------------------------------------------------------
class BgeM3Embedder:
    """BGE-M3 多语言嵌入器封装

    支持:
      - dense 嵌入 (768维)
      - sparse 词权重 (词汇权重字典)
      - 多语言共同语义空间 (zh/ko/en)

    当 FlagEmbedding 不可用时, 使用模拟嵌入 (仅供测试/开发).
    """

    def __init__(self, model_name: str = "BAAI/bge-m3", use_fp16: bool = False):
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self._model = None
        self._simulated = not _check_bge_m3()

        if not self._simulated:
            try:
                from FlagEmbedding import BGEM3FlagModel

                self._model = BGEM3FlagModel(
                    model_name,
                    use_fp16=use_fp16,
                    device="cpu",  # 生产环境可改为 "cuda"
                )
                logger.info(f"BGE-M3 加载完成: {model_name}")
            except Exception as e:
                logger.warning(f"BGE-M3 加载失败 ({e}), 使用模拟模式")
                self._simulated = True
        else:
            logger.info("BGE-M3 模拟模式 (安装 FlagEmbedding 以启用真实模型)")

    # ------------------------------------------------------------------
    # 嵌入计算
    # ------------------------------------------------------------------
    def encode(
        self,
        texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
        normalize_embeddings: bool = True,
    ) -> Dict[str, Any]:
        """计算文本的多向量表示

        Args:
            texts: 文本列表
            return_dense: 是否返回 dense 嵌入
            return_sparse: 是否返回 sparse 权重
            normalize_embeddings: 是否归一化

        Returns:
            {
                "dense_vecs": np.ndarray (N, 768) or None,
                "lexical_weights": List[Dict[str, float]] or None,
            }
        """
        if self._simulated:
            return self._simulate_encode(texts, return_dense, return_sparse)

        result = self._model.encode(
            texts,
            return_dense=return_dense,
            return_sparse=return_sparse,
            return_colbert_vecs=False,
        )

        out: Dict[str, Any] = {}
        if return_dense:
            dense = result.get("dense_vecs", None)
            if dense is not None and normalize_embeddings:
                norms = np.linalg.norm(dense, axis=1, keepdims=True)
                norms = np.where(norms == 0, 1.0, norms)
                dense = dense / norms
            out["dense_vecs"] = dense

        if return_sparse:
            out["lexical_weights"] = result.get("lexical_weights", None)

        return out

    def _simulate_encode(
        self,
        texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> Dict[str, Any]:
        """模拟 BGE-M3 嵌入 (确定性随机, 基于文本 hash)"""
        out: Dict[str, Any] = {}
        n = len(texts)
        rng = np.random.RandomState(42)

        if return_dense:
            # 768维模拟嵌入 — 用文本hash产生确定性表示
            dense = np.zeros((n, 768), dtype=np.float32)
            for i, txt in enumerate(texts):
                seed = hash(txt) & 0xFFFFFFFF
                local_rng = np.random.RandomState(seed)
                vec = local_rng.randn(768).astype(np.float32)
                # 归一化
                vec /= max(np.linalg.norm(vec), 1e-10)
                dense[i] = vec
            out["dense_vecs"] = dense

        if return_sparse:
            weights: List[Dict[str, float]] = []
            for txt in texts:
                tokens = re.findall(r"\w+|[^\w\s]", txt.strip())
                n_tok = len(tokens) if tokens else 1
                w = {f"tok_{j}": 1.0 / n_tok for j in range(min(n_tok, 50))}
                weights.append(w)
            out["lexical_weights"] = weights

        return out

    def compute_similarity(
        self,
        query_emb: Dict[str, Any],
        doc_emb: Dict[str, Any],
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
    ) -> np.ndarray:
        """计算混合相似度: dense 余弦 + sparse 词重叠

        Args:
            query_emb: query 嵌入 (含 dense_vecs, lexical_weights)
            doc_emb:   doc 嵌入
            dense_weight:  dense 相似度权重
            sparse_weight: sparse 相似度权重

        Returns:
            (N_doc,) 相似度数组
        """
        q_dense = query_emb.get("dense_vecs")  # (1, D)
        d_dense = doc_emb.get("dense_vecs")  # (N, D)

        scores = np.zeros(len(d_dense), dtype=np.float32)

        if q_dense is not None and d_dense is not None:
            # 余弦相似度
            dot = np.dot(d_dense, q_dense.T).flatten()  # (N,)
            scores += dense_weight * dot

        if sparse_weight > 0:
            q_lex = query_emb.get("lexical_weights")
            d_lex = doc_emb.get("lexical_weights")
            if q_lex and d_lex:
                q_tokens = q_lex[0] if isinstance(q_lex, list) else q_lex
                for i, d_tok in enumerate(d_lex):
                    overlap = 0.0
                    for tok, qw in q_tokens.items():
                        if tok in d_tok:
                            overlap += qw * d_tok[tok]
                    scores[i] += sparse_weight * overlap

        return scores

    @property
    def is_simulated(self) -> bool:
        return self._simulated


# ---------------------------------------------------------------------------
# 跨境匹配结果
# ---------------------------------------------------------------------------
@dataclass
class CrossBorderMatchResult:
    """跨境匹配结果"""
    enterprise_id: Union[str, int]
    score: float                    # 综合匹配分 (0~1)
    cross_border_score: float = 0.0  # 跨境倾向分 (0~1)
    match_score: float = 0.0        # 语义匹配分 (0~1)
    source_lang: str = ""           # 查询语言
    target_lang: str = ""           # 企业语言
    translated_query: str = ""      # 翻译后的查询 (仅翻译模式)
    details: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "CrossBorderMatchResult") -> bool:
        return self.score < other.score


# ===================================================================
# 跨境匹配器
# ===================================================================
class CrossBorderMatcher:
    """跨境匹配引擎核心。

    支持两种匹配路径:
      1. match_across_languages  — 直接跨语言语义匹配 (BGE-M3 多向量)
      2. match_with_translation  — 先翻译再匹配 (精度优先)

    Args:
        matching_api:     MatchingAPI 实例 (用于三塔评分)
        i18n_translator:  Translator 实例 (用于翻译)
        embedder:         BgeM3Embedder 实例 (可选, 默认新建)
        dense_weight:     dense 相似度权重 (默认 0.6)
        sparse_weight:    sparse 相似度权重 (默认 0.4)
        cross_border_weight: 跨境因子权重 (默认 0.3)
    """

    def __init__(
        self,
        matching_api: Any = None,
        i18n_translator: Any = None,
        embedder: Optional[BgeM3Embedder] = None,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        cross_border_weight: float = 0.3,
    ):
        self.matching_api = matching_api
        self.translator = i18n_translator
        self.embedder = embedder or BgeM3Embedder()
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.cross_border_weight = cross_border_weight

        # ── 翻译函数映射: source -> target -> 翻译函数 ──
        # 实际项目中接入外部翻译 API; 这里用 i18n 字典 + 模拟
        self._translation_fns: Dict[str, Dict[str, Callable]] = {}

    # ------------------------------------------------------------------
    # match_across_languages: 直接跨语言匹配
    # ------------------------------------------------------------------
    def match_across_languages(
        self,
        query_text: str,
        lang: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10,
    ) -> List[CrossBorderMatchResult]:
        """跨语言语义匹配 — 无视语言障碍

        利用 BGE-M3 的共同语义空间:
          - 中文 query → 匹配韩语/英语企业
          - 韩语 query → 匹配中文/英语企业
          - 英语 query → 匹配中文/韩语企业

        Args:
            query_text:  查询文本
            lang:        查询语言代码 (zh/ko/en)
            candidates:  候选企业列表, 每项含 enterprise_id, name, description, lang 等
            top_k:       返回 top-K

        Returns:
            按分数降序的匹配结果列表
        """
        lang = lang if lang in LANG_CODES else detect_language(query_text)

        # ── 编码查询 ──
        query_emb = self.embedder.encode([query_text])

        # ── 收集所有候选文本 ──
        candidate_texts = []
        valid_indices = []
        for i, ent in enumerate(candidates):
            text = self._get_enterprise_text(ent)
            if text and text.strip():
                candidate_texts.append(text)
                valid_indices.append(i)

        if not candidate_texts:
            return []

        # ── 批量编码候选 ──
        doc_emb = self.embedder.encode(candidate_texts)

        # ── 计算语义相似度 ──
        semantic_scores = self.embedder.compute_similarity(
            query_emb, doc_emb,
            dense_weight=self.dense_weight,
            sparse_weight=self.sparse_weight,
        )

        # ── 构建结果 ──
        results: List[CrossBorderMatchResult] = []
        for idx_in_batch, idx_in_candidates in enumerate(valid_indices):
            ent = candidates[idx_in_candidates]
            ent_lang = ent.get("lang", detect_language(
                ent.get("name", "") + " " + ent.get("description", "")
            ))

            match_score = float(semantic_scores[idx_in_batch])
            # 跨语言惩罚: 相同语言略微加分, 不同语言不惩罚
            lang_bonus = 0.05 if ent_lang == lang else 0.0

            cb_score = self.get_cross_border_score(ent)
            final_score = (
                0.6 * match_score
                + self.cross_border_weight * cb_score
                + lang_bonus
            )
            final_score = max(0.0, min(1.0, final_score))

            results.append(CrossBorderMatchResult(
                enterprise_id=ent.get("enterprise_id", ent.get("id", f"ent_{idx_in_candidates}")),
                score=final_score,
                cross_border_score=cb_score,
                match_score=match_score,
                source_lang=lang,
                target_lang=ent_lang,
                details={
                    "query": query_text,
                    "enterprise_name": ent.get("name", ""),
                },
            ))

        # ── 排序 ──
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # match_with_translation: 先翻译再匹配
    # ------------------------------------------------------------------
    def match_with_translation(
        self,
        query_text: str,
        source_lang: str,
        target_lang: str,
        candidates: List[Dict[str, Any]],
    ) -> List[CrossBorderMatchResult]:
        """先翻译查询再进行匹配 — 精度优先

        流程:
          1. 将 query 从 source_lang 翻译为 target_lang
          2. 在 target_lang 的候选企业中进行语义匹配
          3. 返回结果 (含翻译后的查询)

        Args:
            query_text:   源语言查询
            source_lang:  源语言 (zh/ko/en)
            target_lang:  目标语言 (zh/ko/en)
            candidates:   候选企业列表

        Returns:
            匹配结果列表 (按分数降序)
        """
        # ── 翻译 ──
        translated = self._translate(query_text, source_lang, target_lang)
        if not translated or translated == query_text:
            # 翻译失败, 回退到跨语言匹配
            logger.warning(
                f"翻译失败 ({source_lang}→{target_lang}), 回退到跨语言匹配"
            )
            return self.match_across_languages(query_text, source_lang, candidates)

        # ── 用翻译后的文本匹配 ──
        query_emb = self.embedder.encode([translated])

        # ── 过滤 candidates 中目标语言的企业 ──
        target_candidates = []
        for ent in candidates:
            ent_lang = ent.get("lang", detect_language(
                ent.get("name", "") + " " + ent.get("description", "")
            ))
            if ent_lang == target_lang:
                target_candidates.append(ent)

        if not target_candidates:
            # 没有目标语言企业, 回退
            return self.match_across_languages(query_text, source_lang, candidates)

        # ── 编码并匹配 ──
        candidate_texts = [self._get_enterprise_text(e) for e in target_candidates]
        doc_emb = self.embedder.encode(candidate_texts)
        semantic_scores = self.embedder.compute_similarity(
            query_emb, doc_emb,
            dense_weight=self.dense_weight,
            sparse_weight=self.sparse_weight,
        )

        results: List[CrossBorderMatchResult] = []
        for i, ent in enumerate(target_candidates):
            match_score = float(semantic_scores[i])
            cb_score = self.get_cross_border_score(ent)
            final_score = 0.7 * match_score + self.cross_border_weight * cb_score
            final_score = max(0.0, min(1.0, final_score))

            results.append(CrossBorderMatchResult(
                enterprise_id=ent.get("enterprise_id", ent.get("id", f"ent_{i}")),
                score=final_score,
                cross_border_score=cb_score,
                match_score=match_score,
                source_lang=source_lang,
                target_lang=target_lang,
                translated_query=translated,
                details={
                    "query": query_text,
                    "translated": translated,
                    "enterprise_name": ent.get("name", ""),
                },
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # get_cross_border_score: 跨境倾向评分
    # ------------------------------------------------------------------
    def get_cross_border_score(self, enterprise: Dict[str, Any]) -> float:
        """计算企业的跨境匹配倾向分 (0~1)

        基于因子:
          - 出口许可证 / 涉外业务
          - 目标海外市场
          - 语言能力
          - 跨境经验年限
          - 国际认证
          - 海外办事处

        若企业字典中不包含这些字段, 返回 0.3 (中等倾向)
        """
        factors = self._extract_cross_border_factors(enterprise)
        score = 0.0
        total_weight = 0.0

        # 各因子权重
        rules = [
            (factors.has_export_license, 0.20),
            (factors.has_foreign_business, 0.20),
            (len(factors.target_markets) > 0, 0.15),
            (len(factors.language_capabilities) > 0, 0.10),
            (factors.cross_border_years >= 1.0, 0.10),
            (factors.cross_border_years >= 3.0, 0.10),
            (factors.international_certifications >= 1, 0.05),
            (factors.international_certifications >= 3, 0.05),
            (factors.overseas_office, 0.10),
        ]

        for condition, weight in rules:
            if condition:
                score += weight
            total_weight += weight

        if total_weight > 0:
            score /= total_weight  # 归一化到 0~1

        # 硬性限制
        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # 三塔集成评分
    # ------------------------------------------------------------------
    def score_with_towers(
        self,
        user_features: Any,
        enterprise_features: Any,
        behavior_sequence: Any = None,
        behavior_mask: Any = None,
    ) -> float:
        """使用三塔 MatchingAPI 评分 (如果可用)"""
        if self.matching_api is None:
            return 0.5  # 默认中等分数
        try:
            return self.matching_api.scorer.score(
                user_features, enterprise_features,
                behavior_sequence, behavior_mask,
            )
        except Exception as e:
            logger.warning(f"三塔评分失败: {e}")
            return 0.5

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _get_enterprise_text(self, ent: Dict[str, Any]) -> str:
        """从企业字典提取用于语义匹配的文本"""
        parts = [
            ent.get("name", ""),
            ent.get("description", ""),
            ent.get("industry", ""),
            ent.get("business_scope", ""),  # 经营范围
            ent.get("introduction", ""),
        ]
        return " ".join(p for p in parts if p)

    def _extract_cross_border_factors(
        self, enterprise: Dict[str, Any]
    ) -> CrossBorderFactors:
        """从企业字典提取跨境因子"""
        return CrossBorderFactors(
            has_export_license=bool(enterprise.get("export_license", False)),
            has_foreign_business=bool(enterprise.get("foreign_business", False)),
            target_markets=enterprise.get("target_markets", []),
            language_capabilities=enterprise.get("languages", []),
            cross_border_years=float(enterprise.get("cross_border_years", 0.0)),
            international_certifications=int(
                enterprise.get("international_certifications", 0)
            ),
            overseas_office=bool(enterprise.get("overseas_office", False)),
        )

    def _translate(
        self, text: str, source: str, target: str
    ) -> str:
        """翻译文本 (source → target)

        优先使用 Translator 字典; 无翻译时模拟返回.
        生产环境应接入外部翻译 API (Google / Papago / DeepL).
        """
        if source == target:
            return text

        # 使用 i18n Translator 的字典翻译
        if self.translator is not None and hasattr(self.translator, "t"):
            # Translator.t 是按 key 查表, 不适合长文本翻译
            # 这里仅演示集成; 实际需要外部翻译 API
            pass

        # 模拟翻译 (仅测试用)
        simulated_translations = {
            ("zh", "ko"): f"[번역] {text}",
            ("zh", "en"): f"[Trans] {text}",
            ("ko", "zh"): f"[翻译] {text}",
            ("ko", "en"): f"[Trans] {text}",
            ("en", "zh"): f"[翻译] {text}",
            ("en", "ko"): f"[번역] {text}",
        }
        return simulated_translations.get((source, target), text)


# ===================================================================
# 跨境匹配管线
# ===================================================================
class CrossBorderPipeline:
    """跨境匹配高层管线

    自动语言检测 + 跨语言映射:

      输入: 中方企业需求(中文)   → 输出: 韩国/海外候选企业(韩/英)
      输入: 韩方企业需求(韩语)   → 输出: 中国候选企业(中文)
      输入: 英文企业需求(英语)   → 输出: 中/韩候选企业

    Args:
        matcher: CrossBorderMatcher 实例
    """

    # 语言映射: 源语言 → 目标语言(候选企业语言)
    LANGUAGE_MAP: Dict[str, List[str]] = {
        "zh": ["ko", "en"],      # 中国需求 → 韩国/英语企业
        "ko": ["zh", "en"],      # 韩国需求 → 中国/英语企业
        "en": ["zh", "ko"],      # 英语需求 → 中国/韩国企业
    }

    def __init__(self, matcher: CrossBorderMatcher):
        self.matcher = matcher

    # ------------------------------------------------------------------
    # run: 主入口
    # ------------------------------------------------------------------
    def run(
        self,
        query_text: str,
        candidates: List[Dict[str, Any]],
        lang: Optional[str] = None,
        mode: str = "auto",
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """执行跨境匹配管线

        Args:
            query_text:  查询文本
            candidates:  候选企业列表
            lang:        查询语言 (None=自动检测)
            mode:        匹配模式
                         "auto"      — 自动选择最佳模式
                         "direct"    — 直接跨语言匹配 (效率优先)
                         "translate" — 先翻译再匹配 (精度优先)
            top_k:       返回 top-K

        Returns:
            {
                "query": query_text,
                "detected_lang": detected_lang,
                "mode": mode_used,
                "results": [CrossBorderMatchResult, ...],
                "target_languages": [...],
            }
        """
        # 语言检测
        detected_lang = lang or detect_language(query_text)
        target_langs = self.LANGUAGE_MAP.get(detected_lang, ["zh", "ko", "en"])

        # 按语言分组候选
        candidates_by_lang: Dict[str, List[Dict]] = {l: [] for l in target_langs}
        for ent in candidates:
            ent_lang = ent.get("lang", detect_language(
                self.matcher._get_enterprise_text(ent)
            ))
            # 匹配到目标语言
            for tl in target_langs:
                if ent_lang == tl:
                    candidates_by_lang[tl].append(ent)
                    break
            else:
                # 非目标语言企业加入所有组
                for tl in target_langs:
                    candidates_by_lang[tl].append(ent)

        all_results: List[CrossBorderMatchResult] = []
        mode_used = mode

        for target_lang in target_langs:
            lang_candidates = candidates_by_lang.get(target_lang, [])
            if not lang_candidates:
                continue

            if mode == "translate":
                # 精度优先: 先翻译再匹配
                results = self.matcher.match_with_translation(
                    query_text, detected_lang, target_lang, lang_candidates,
                )
            elif mode == "direct":
                # 效率优先: 直接跨语言匹配
                results = self.matcher.match_across_languages(
                    query_text, detected_lang, lang_candidates, top_k,
                )
            else:
                # auto: 自动选择
                # 如果查询和目标语言相同, 用翻译模式; 否则用直接匹配
                if detected_lang == target_lang:
                    results = self.matcher.match_across_languages(
                        query_text, detected_lang, lang_candidates, top_k,
                    )
                else:
                    # 不同语言: 尝试先翻译
                    trans_results = self.matcher.match_with_translation(
                        query_text, detected_lang, target_lang, lang_candidates,
                    )
                    direct_results = self.matcher.match_across_languages(
                        query_text, detected_lang, lang_candidates, top_k,
                    )
                    # 合并 & 去重
                    seen_ids = set()
                    results = []
                    for r in trans_results + direct_results:
                        if r.enterprise_id not in seen_ids:
                            seen_ids.add(r.enterprise_id)
                            results.append(r)
                    mode_used = "hybrid"

            all_results.extend(results)

        # 全局排序
        all_results.sort(key=lambda r: r.score, reverse=True)

        return {
            "query": query_text,
            "detected_lang": detected_lang,
            "mode": mode_used,
            "results": all_results[:top_k],
            "target_languages": target_langs,
        }


# ===================================================================
# MatchingAPI 集成插件
# ===================================================================
def patch_matching_api(api_class: Any) -> None:
    """为 MatchingAPI 添加跨境匹配能力

    用法:
        from ml.models.cross_border import patch_matching_api
        from ml.models.tower_ensemble import MatchingAPI

        patch_matching_api(MatchingAPI)
        api = MatchingAPI(...)
        results = api.predict(
            user_info, candidates,
            cross_border=True,
            source_lang="zh",
        )
    """
    original_predict = api_class.predict

    def patched_predict(
        self,
        user_info,
        candidates,
        behavior_sequences=None,
        top_k=None,
        cross_border=False,
        source_lang=None,
        **kwargs,
    ):
        if not cross_border:
            return original_predict(
                self, user_info, candidates, behavior_sequences, top_k, **kwargs
            )

        # 构建跨境匹配器
        from ml.models.cross_border import CrossBorderMatcher

        # 尝试获取 i18n translator
        translator = getattr(self, "_i18n_translator", None)
        matcher = CrossBorderMatcher(
            matching_api=self,
            i18n_translator=translator,
        )

        # 从 user_info 提取 query 文本
        query_text = (
            user_info.get("query", "") or
            user_info.get("description", "") or
            user_info.get("需求描述", "") or
            user_info.get("需求", "") or
            ""
        )

        lang = source_lang or detect_language(query_text) or "zh"
        if not query_text:
            # 回退: 用 user_info 全文做 query
            query_text = " ".join(str(v) for v in user_info.values())

        # 执行跨境匹配
        pipe = CrossBorderPipeline(matcher)
        result = pipe.run(query_text, candidates, lang=lang, top_k=top_k or 20)

        # 转换为 MatchResult 格式
        from ml.models.tower_ensemble import MatchResult

        match_results = []
        for cr in result["results"]:
            match_results.append(MatchResult(
                enterprise_id=cr.enterprise_id,
                score=cr.score,
            ))

        return match_results

    api_class.predict = patched_predict
    logger.info("MatchingAPI 已打补丁: 支持 cross_border=True 参数")
