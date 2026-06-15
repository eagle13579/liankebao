"""
AI数字名片 Brochure API — 国际化 (i18n) 测试套件
==================================================
覆盖:
  - Accept-Language 头处理
  - 中文/英文/日文等多语言切换
  - 响应头 X-Content-Language
  - 降级行为 (不支持的语言 → 默认语言)
  - gettext / 翻译函数 (如果实现)
  - 错误消息国际化

注意: 当前 digital_brochure_api.py 尚未实现 i18n 中间件。
      fix_i18n.py 描述了计划中的实现方案。
      本文件包含完整测试结构, 实现后移除 skip 标记即可运行。
"""

import pytest


# ============================================================
# 语言检测函数测试
# ============================================================


class TestLanguageDetection:
    """语言检测功能"""

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_detect_chinese(self):
        """Accept-Language: zh-CN → zh"""
        from digital_brochure_api import detect_lang
        assert detect_lang("zh-CN,zh;q=0.9") == "zh"

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_detect_english(self):
        """Accept-Language: en → en"""
        from digital_brochure_api import detect_lang
        assert detect_lang("en-US,en;q=0.9") == "en"

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_detect_japanese(self):
        """Accept-Language: ja → ja"""
        from digital_brochure_api import detect_lang
        assert detect_lang("ja-JP,ja;q=0.9") == "ja"

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_detect_korean(self):
        """Accept-Language: ko → ko"""
        from digital_brochure_api import detect_lang
        assert detect_lang("ko-KR,ko;q=0.9") == "ko"

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_unsupported_language_fallback(self):
        """不支持的语言应降级为默认 (zh)"""
        from digital_brochure_api import detect_lang
        for lang in ["fr-FR", "de-DE", "es", "pt-BR", "ar-SA"]:
            result = detect_lang(f"{lang};q=0.9")
            assert result == "zh", f"{lang} 应降级为 zh, 得到 {result}"

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_empty_accept_language(self):
        """无 Accept-Language 头应返回默认语言"""
        from digital_brochure_api import detect_lang
        assert detect_lang("") == "zh"
        assert detect_lang(None) == "zh"

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_quality_value_parsing(self):
        """q 值解析: 按优先级选择"""
        from digital_brochure_api import detect_lang
        # en 优先级高于 zh
        assert detect_lang("en;q=0.9, zh;q=0.5") == "en"
        # zh 优先级高于 en
        assert detect_lang("zh;q=0.9, en;q=0.5") == "zh"

    @pytest.mark.skip(reason="i18n 尚未在 digital_brochure_api.py 中实现")
    def test_malformed_header(self):
        """畸形 Accept-Language 头不应崩溃"""
        from digital_brochure_api import detect_lang
        for bad_header in [";;;", "invalid", "=", ";;;;", "*/*"]:
            result = detect_lang(bad_header)
            assert result == "zh", f"畸形头 '{bad_header}' 应返回默认语言"


# ============================================================
# API 响应头测试
# ============================================================


class TestI18nResponseHeaders:
    """国际化响应头"""

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_x_content_language_header(self, brochure_client):
        """响应应包含 X-Content-Language 头"""
        resp = brochure_client.get(
            "/api/v1/digital-brochure/1",
            headers={"Accept-Language": "zh-CN"},
        )
        assert "X-Content-Language" in resp.headers
        assert resp.headers["X-Content-Language"] == "zh"

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_english_response_header(self, brochure_client):
        resp = brochure_client.get(
            "/api/v1/digital-brochure/1",
            headers={"Accept-Language": "en-US"},
        )
        assert resp.headers["X-Content-Language"] == "en"

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_unsupported_language_header(self, brochure_client):
        """不支持的语言应返回默认 zh"""
        resp = brochure_client.get(
            "/api/v1/digital-brochure/1",
            headers={"Accept-Language": "fr-FR"},
        )
        assert resp.headers["X-Content-Language"] == "zh"

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_no_header_default_language(self, brochure_client):
        """无 Accept-Language 头应返回默认 zh"""
        resp = brochure_client.get("/api/v1/digital-brochure/1")
        assert resp.headers.get("X-Content-Language") == "zh"


# ============================================================
# 错误消息国际化
# ============================================================


class TestI18nErrorMessages:
    """错误消息国际化"""

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_404_in_chinese(self, brochure_client):
        """中文环境下 404 错误消息应为中文"""
        resp = brochure_client.get(
            "/api/v1/digital-brochure/99999",
            headers={"Accept-Language": "zh-CN"},
        )
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_404_in_english(self, brochure_client):
        """英文环境下 404 错误消息应为英文"""
        resp = brochure_client.get(
            "/api/v1/digital-brochure/99999",
            headers={"Accept-Language": "en-US"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_404_in_japanese(self, brochure_client):
        resp = brochure_client.get(
            "/api/v1/digital-brochure/99999",
            headers={"Accept-Language": "ja-JP"},
        )
        assert resp.status_code == 404
        # 期望日文消息
        detail = resp.json()["detail"]
        assert any(kw in detail for kw in ["存在し", "見つかり", "ない"])

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_success_message_in_chinese(self, brochure_client, brochure_sample):
        resp = brochure_client.post(
            f"/api/v1/digital-brochure/{brochure_sample['id']}/visit",
            headers={"Accept-Language": "zh-CN"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "已记录" or "访问" in data["message"]

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_success_message_in_english(self, brochure_client, brochure_sample):
        resp = brochure_client.post(
            f"/api/v1/digital-brochure/{brochure_sample['id']}/visit",
            headers={"Accept-Language": "en-US"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "recorded" in data["message"].lower() or "visit" in data["message"].lower()


# ============================================================
# 翻译函数测试 (如果实现了 gettext)
# ============================================================


class TestTranslationFunctions:
    """翻译函数"""

    @pytest.mark.skip(reason="翻译函数尚未实现")
    def test_gettext_zh(self):
        """中文翻译"""
        from digital_brochure_api import _
        assert _("Brochure not found", lang="zh") == "图册不存在"
        assert _("Visit recorded", lang="zh") == "已记录"

    @pytest.mark.skip(reason="翻译函数尚未实现")
    def test_gettext_en(self):
        """英文翻译"""
        from digital_brochure_api import _
        assert _("Brochure not found", lang="en") == "Brochure not found"
        assert _("Visit recorded", lang="en") == "Visit recorded"

    @pytest.mark.skip(reason="翻译函数尚未实现")
    def test_gettext_ja(self):
        """日文翻译"""
        from digital_brochure_api import _
        result = _("Brochure not found", lang="ja")
        assert result is not None
        assert result != "Brochure not found"

    @pytest.mark.skip(reason="翻译函数尚未实现")
    def test_gettext_fallback(self):
        """无翻译时返回原文"""
        from digital_brochure_api import _
        result = _("Some untranslated string", lang="fr")
        assert result == "Some untranslated string"

    @pytest.mark.skip(reason="翻译函数尚未实现")
    def test_gettext_parameterized(self):
        """带参数翻译"""
        from digital_brochure_api import _
        result = _("{} brochures found", lang="en", count=5)
        assert "5" in result


# ============================================================
# 国际化中间件 (模拟 fix_i18n.py 方案)
# ============================================================


class TestI18nMiddleware:
    """国际化中间件 (基于 fix_i18n.py 方案)

    fix_i18n.py 描述:
      - 使用 contextvars 存储语言 (ContextVar('lang', default='zh'))
      - 中间件从 Accept-Language 检测语言并设置 context var
      - 响应头 X-Content-Language
    """

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_lang_context_var(self):
        """验证 _lang_var ContextVar 存在且有默认值"""
        from digital_brochure_api import _lang_var
        assert _lang_var.get() == "zh"

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_lang_context_var_set(self, brochure_client):
        """中间件应设置 _lang_var"""
        from digital_brochure_api import _lang_var
        brochure_client.get(
            "/health",
            headers={"Accept-Language": "en-US"},
        )
        assert _lang_var.get() == "en"

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_request_state_lang(self, brochure_client):
        """request.state.lang 应正确设置"""
        resp = brochure_client.get(
            "/health",
            headers={"Accept-Language": "ja-JP"},
        )
        assert resp.headers.get("X-Content-Language") == "ja"

    @pytest.mark.skip(reason="i18n 中间件尚未实现")
    def test_lang_persistence_across_requests(self, brochure_client):
        """不同请求的语言应独立 (不相互影响)"""
        # 第一个请求设 en
        brochure_client.get("/health", headers={"Accept-Language": "en-US"})
        # 第二个请求默认 (无头)
        resp = brochure_client.get("/health")
        assert resp.headers.get("X-Content-Language") == "zh"


# ============================================================
# 多种语言场景
# ============================================================


class TestMultiLanguageScenarios:
    """多语言场景"""

    SUPPORTED_LANGUAGES = ["zh", "en", "ja", "ko"]

    @pytest.mark.skip(reason="i18n 尚未实现")
    def test_all_supported_languages(self, brochure_client):
        """所有支持的语言都能正确设置"""
        for lang in self.SUPPORTED_LANGUAGES:
            resp = brochure_client.get(
                "/health",
                headers={"Accept-Language": f"{lang};q=1.0"},
            )
            assert resp.headers.get("X-Content-Language") == lang

    @pytest.mark.skip(reason="i18n 尚未实现")
    def test_language_cookie(self, brochure_client):
        """应支持通过 Cookie 设置语言"""
        resp = brochure_client.get(
            "/health",
            cookies={"lang": "en"},
        )
        assert resp.headers.get("X-Content-Language") == "en"

    @pytest.mark.skip(reason="i18n 尚未实现")
    def test_language_query_param(self, brochure_client):
        """应支持通过查询参数设置语言"""
        resp = brochure_client.get("/health?lang=en")
        assert resp.headers.get("X-Content-Language") == "en"
