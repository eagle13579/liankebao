"""链客宝 — 跨境匹配引擎测试

至少 15 个测试覆盖:
  - 语言检测 (中/韩/英)
  - CrossBorderMatcher 跨语言匹配
  - 翻译匹配
  - 跨境倾向评分
  - CrossBorderPipeline 管线
  - MatchingAPI 集成
"""

import sys
import os

# 确保能从项目根目录导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import numpy as np

# ---------------------------------------------------------------------------
# 被测试模块
# ---------------------------------------------------------------------------
from ml.models.cross_border import (
    detect_language,
    BgeM3Embedder,
    CrossBorderMatcher,
    CrossBorderPipeline,
    CrossBorderMatchResult,
    CrossBorderFactors,
    patch_matching_api,
)


def _make_candidates(count: int = 5, lang: str = "ko") -> list:
    """生成测试用候选企业列表"""
    candidates = []
    names_map = {
        "ko": {
            "names": ["삼성전자", "현대중공업", "LG전자", "SK하이닉스", "카카오"],
            "desc": "첨단 기술 기업으로 글로벌 시장에서 경쟁력 있는 제품을 공급합니다",
        },
        "zh": {
            "names": ["阿里巴巴", "腾讯科技", "华为技术", "字节跳动", "比亚迪"],
            "desc": "全球领先的科技企业, 提供创新产品与服务",
        },
        "en": {
            "names": ["Google LLC", "Microsoft Corp", "Apple Inc", "Amazon", "Meta"],
            "desc": "Leading global technology company providing innovative solutions",
        },
    }
    data = names_map.get(lang, names_map["ko"])
    for i in range(count):
        candidates.append({
            "enterprise_id": i + 1,
            "name": data["names"][i % len(data["names"])],
            "description": data["desc"],
            "lang": lang,
            "export_license": i % 2 == 0,
            "foreign_business": True,
            "target_markets": ["中国", "韩国", "USA", "Japan"][: (i % 4) + 1],
            "languages": ["zh", "ko", "en"][: (i % 3) + 1],
            "cross_border_years": float(i * 2),
            "international_certifications": i,
            "overseas_office": i > 2,
        })
    return candidates


# ===================================================================
# 测试用例
# ===================================================================

def test_detect_language_zh():
    """TC1: 中文检测"""
    assert detect_language("你好世界") == "zh"
    assert detect_language("我们需要跨境合作") == "zh"
    assert detect_language("阿里巴巴是一家中国公司") == "zh"
    print("  ✓ test_detect_language_zh")


def test_detect_language_ko():
    """TC2: 韩语检测"""
    assert detect_language("안녕하세요") == "ko"
    assert detect_language("한국 기업과 협력하고 싶습니다") == "ko"
    assert detect_language("삼성전자는 글로벌 기업입니다") == "ko"
    print("  ✓ test_detect_language_ko")


def test_detect_language_en():
    """TC3: 英语检测"""
    assert detect_language("Hello world") == "en"
    assert detect_language("We want to cooperate with Korean companies") == "en"
    assert detect_language("Global trade and business") == "en"
    print("  ✓ test_detect_language_en")


def test_detect_language_mixed():
    """TC4: 混合文本检测"""
    # 中文为主
    assert detect_language("你好韩国 company") == "zh"
    # 韩语为主
    assert detect_language("안녕하세요 nice to meet") == "ko"
    # 空文本
    assert detect_language("") == "en"
    assert detect_language("   ") == "en"
    print("  ✓ test_detect_language_mixed")


def test_bge_m3_embedder_simulated():
    """TC5: BGE-M3 模拟嵌入"""
    embedder = BgeM3Embedder()
    assert embedder.is_simulated, "应处于模拟模式"

    texts = ["你好世界", "안녕하세요", "Hello world"]
    result = embedder.encode(texts)

    assert "dense_vecs" in result
    assert result["dense_vecs"].shape == (3, 768)
    assert isinstance(result["dense_vecs"], np.ndarray)

    assert "lexical_weights" in result
    assert len(result["lexical_weights"]) == 3
    print(f"  ✓ test_bge_m3_embedder_simulated (shape={result['dense_vecs'].shape})")


def test_bge_m3_similarity():
    """TC6: BGE-M3 相似度计算"""
    embedder = BgeM3Embedder()
    query_emb = embedder.encode(["첨단 기술 기업"])
    doc_emb = embedder.encode([
        "삼성전자는 글로벌 기업입니다",
        "중국 전통 차 산업",
        "Global tech company",
    ])

    scores = embedder.compute_similarity(query_emb, doc_emb)
    assert scores.shape == (3,)
    assert all(-1.0 <= s <= 1.0 for s in scores)
    # 韩语 query 应与韩语 doc 相似度最高
    assert scores[0] >= scores[1], "韩语-韩语应高于韩语-中文"
    print(f"  ✓ test_bge_m3_similarity (scores={scores.round(4).tolist()})")


def test_cross_border_score():
    """TC7: 跨境倾向评分"""
    matcher = CrossBorderMatcher()

    # 高跨境倾向企业
    high_cb = {
        "enterprise_id": 1,
        "export_license": True,
        "foreign_business": True,
        "target_markets": ["韩国", "日本"],
        "languages": ["ko", "en"],
        "cross_border_years": 5.0,
        "international_certifications": 3,
        "overseas_office": True,
    }
    score_high = matcher.get_cross_border_score(high_cb)
    assert 0.8 <= score_high <= 1.0, f"高跨境分应在 0.8~1.0, 收到 {score_high}"

    # 低跨境倾向企业
    low_cb = {
        "enterprise_id": 2,
        "export_license": False,
        "foreign_business": False,
        "target_markets": [],
        "languages": [],
        "cross_border_years": 0.0,
        "international_certifications": 0,
        "overseas_office": False,
    }
    score_low = matcher.get_cross_border_score(low_cb)
    assert 0.0 <= score_low <= 0.3, f"低跨境分应在 0~0.3, 收到 {score_low}"

    # 默认企业 (无跨境字段)
    default_ent = {"enterprise_id": 3}
    score_default = matcher.get_cross_border_score(default_ent)
    assert 0.0 <= score_default <= 1.0
    print(f"  ✓ test_cross_border_score (high={score_high:.3f}, low={score_low:.3f})")


def test_match_across_languages_zh_to_ko():
    """TC8: 中文 query → 匹配韩语企业"""
    matcher = CrossBorderMatcher()
    candidates = _make_candidates(count=5, lang="ko")

    results = matcher.match_across_languages(
        query_text="我们需要与韩国高科技企业合作",
        lang="zh",
        candidates=candidates,
        top_k=3,
    )

    assert len(results) <= 3
    assert all(isinstance(r, CrossBorderMatchResult) for r in results)
    assert all(0.0 <= r.score <= 1.0 for r in results)
    if results:
        assert results[0].source_lang == "zh"
        assert results[0].target_lang == "ko"
        # 按分数降序
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score
    print(f"  ✓ test_match_across_languages_zh_to_ko (n={len(results)})")


def test_match_across_languages_ko_to_zh():
    """TC9: 韩语 query → 匹配中文企业"""
    matcher = CrossBorderMatcher()
    candidates = _make_candidates(count=4, lang="zh")

    results = matcher.match_across_languages(
        query_text="중국 시장에 진출하려는 한국 기업입니다",
        lang="ko",
        candidates=candidates,
        top_k=3,
    )

    assert len(results) <= 3
    assert all(r.source_lang == "ko" for r in results)
    assert all(r.target_lang == "zh" for r in results)
    print(f"  ✓ test_match_across_languages_ko_to_zh (n={len(results)})")


def test_match_across_languages_en_to_mixed():
    """TC10: 英语 query → 匹配中/韩企业"""
    matcher = CrossBorderMatcher()
    candidates = _make_candidates(count=3, lang="zh") + _make_candidates(count=3, lang="ko")

    results = matcher.match_across_languages(
        query_text="Looking for innovative technology partners in Asia",
        lang="en",
        candidates=candidates,
        top_k=4,
    )

    assert len(results) <= 4
    # 可能匹配到 zh 或 ko
    target_langs = set(r.target_lang for r in results)
    assert target_langs.issubset({"zh", "ko"})
    print(f"  ✓ test_match_across_languages_en_to_mixed (n={len(results)}, langs={target_langs})")


def test_match_with_translation():
    """TC11: 先翻译再匹配"""
    matcher = CrossBorderMatcher()
    candidates = _make_candidates(count=3, lang="ko")

    results = matcher.match_with_translation(
        query_text="我需要韩国电子产品供应商",
        source_lang="zh",
        target_lang="ko",
        candidates=candidates,
    )

    assert all(r.source_lang == "zh" for r in results)
    assert all(r.target_lang == "ko" for r in results)
    if results:
        assert results[0].translated_query != ""
        assert results[0].source_lang == "zh"
    print(f"  ✓ test_match_with_translation (n={len(results)})")


def test_match_empty_candidates():
    """TC12: 空候选集"""
    matcher = CrossBorderMatcher()

    results = matcher.match_across_languages("测试", "zh", [], top_k=5)
    assert results == []

    results2 = matcher.match_with_translation("test", "en", "ko", [])
    assert results2 == []
    print("  ✓ test_match_empty_candidates")


def test_pipeline_zh_to_ko():
    """TC13: Pipeline 中文需求 → 韩语企业"""
    matcher = CrossBorderMatcher()
    pipe = CrossBorderPipeline(matcher)
    candidates = _make_candidates(count=5, lang="ko")

    result = pipe.run(
        query_text="我们需要高品质韩国电子产品",
        candidates=candidates,
        mode="direct",
        top_k=3,
    )

    assert result["detected_lang"] == "zh"
    assert "ko" in result["target_languages"]
    assert len(result["results"]) <= 3
    print(f"  ✓ test_pipeline_zh_to_ko (lang={result['detected_lang']}, n={len(result['results'])})")


def test_pipeline_ko_to_zh():
    """TC14: Pipeline 韩语需求 → 中文企业"""
    matcher = CrossBorderMatcher()
    pipe = CrossBorderPipeline(matcher)
    candidates = _make_candidates(count=4, lang="zh")

    result = pipe.run(
        query_text="중국 시장 진출을 위한 파트너를 찾고 있습니다",
        candidates=candidates,
        mode="direct",
        top_k=3,
    )

    assert result["detected_lang"] == "ko"
    assert "zh" in result["target_languages"]
    print(f"  ✓ test_pipeline_ko_to_zh (lang={result['detected_lang']}, n={len(result['results'])})")


def test_pipeline_auto_mode():
    """TC15: Pipeline 自动模式"""
    matcher = CrossBorderMatcher()
    pipe = CrossBorderPipeline(matcher)
    candidates = _make_candidates(count=3, lang="ko") + _make_candidates(count=3, lang="zh")

    result = pipe.run(
        query_text="글로벌 파트너십을 원합니다",
        candidates=candidates,
        mode="auto",
        top_k=5,
    )

    assert result["detected_lang"] == "ko"
    assert len(result["results"]) <= 5
    # auto 模式应使用 hybrid
    assert result["mode"] in ("auto", "hybrid", "direct")
    print(f"  ✓ test_pipeline_auto_mode (mode={result['mode']}, n={len(result['results'])})")


def test_pipeline_translate_mode():
    """TC16: Pipeline 翻译模式"""
    matcher = CrossBorderMatcher()
    pipe = CrossBorderPipeline(matcher)
    candidates = _make_candidates(count=3, lang="ko")

    result = pipe.run(
        query_text="韩国芯片供应商",
        candidates=candidates,
        mode="translate",
        top_k=3,
    )

    assert result["detected_lang"] == "zh"
    assert result["mode"] == "translate"
    print(f"  ✓ test_pipeline_translate_mode (n={len(result['results'])})")


def test_cross_border_factors_default():
    """TC17: CrossBorderFactors 默认值"""
    factors = CrossBorderFactors()
    assert factors.has_export_license is False
    assert factors.has_foreign_business is False
    assert factors.target_markets == []
    assert factors.cross_border_years == 0.0
    assert factors.international_certifications == 0
    print("  ✓ test_cross_border_factors_default")


def test_patch_matching_api():
    """TC18: MatchingAPI 集成补丁"""
    # 验证 patch 函数存在且可调用
    assert callable(patch_matching_api)
    print("  ✓ test_patch_matching_api (patch function is callable)")


def test_cross_border_match_result_sort():
    """TC19: CrossBorderMatchResult 排序"""
    r1 = CrossBorderMatchResult(enterprise_id=1, score=0.9)
    r2 = CrossBorderMatchResult(enterprise_id=2, score=0.5)
    r3 = CrossBorderMatchResult(enterprise_id=3, score=0.7)

    sorted_results = sorted([r1, r2, r3], reverse=True)
    assert sorted_results[0].score == 0.9
    assert sorted_results[1].score == 0.7
    assert sorted_results[2].score == 0.5
    print("  ✓ test_cross_border_match_result_sort")


def test_mixed_lang_candidates():
    """TC20: 混合语言候选集"""
    matcher = CrossBorderMatcher()
    candidates = (
        _make_candidates(count=2, lang="zh")
        + _make_candidates(count=2, lang="ko")
        + _make_candidates(count=2, lang="en")
    )

    results = matcher.match_across_languages(
        query_text="全球科技合作伙伴",
        lang="zh",
        candidates=candidates,
        top_k=5,
    )

    assert len(results) <= 5
    # 应包含多种语言的企业
    langs_found = set(r.target_lang for r in results)
    assert len(langs_found) >= 2, f"应匹配到至少2种语言, 收到 {langs_found}"
    print(f"  ✓ test_mixed_lang_candidates (langs={langs_found}, n={len(results)})")


# ===================================================================
# 主入口
# ===================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  跨境匹配引擎 — 单元测试")
    print("  CrossBorderMatcher / CrossBorderPipeline")
    print("=" * 60)
    print()

    tests = [
        ("语言检测 - 中文", test_detect_language_zh),
        ("语言检测 - 韩语", test_detect_language_ko),
        ("语言检测 - 英语", test_detect_language_en),
        ("语言检测 - 混合", test_detect_language_mixed),
        ("BGE-M3 模拟嵌入", test_bge_m3_embedder_simulated),
        ("BGE-M3 相似度", test_bge_m3_similarity),
        ("跨境倾向评分", test_cross_border_score),
        ("跨语言匹配 zh→ko", test_match_across_languages_zh_to_ko),
        ("跨语言匹配 ko→zh", test_match_across_languages_ko_to_zh),
        ("跨语言匹配 en→mixed", test_match_across_languages_en_to_mixed),
        ("翻译匹配", test_match_with_translation),
        ("空候选集", test_match_empty_candidates),
        ("Pipeline zh→ko", test_pipeline_zh_to_ko),
        ("Pipeline ko→zh", test_pipeline_ko_to_zh),
        ("Pipeline auto 模式", test_pipeline_auto_mode),
        ("Pipeline translate 模式", test_pipeline_translate_mode),
        ("CrossBorderFactors 默认值", test_cross_border_factors_default),
        ("MatchingAPI 补丁", test_patch_matching_api),
        ("CrossBorderMatchResult 排序", test_cross_border_match_result_sort),
        ("混合语言候选集", test_mixed_lang_candidates),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("-" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")
    if failed == 0:
        print("  ✓ 全部通过!")
    else:
        print("  ✗ 存在失败的测试!")
    print("=" * 60)
