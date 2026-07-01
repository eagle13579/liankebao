#!/usr/bin/env python
"""
AI数字名片 — 自动翻译管道 (Auto Translation Pipeline)
=========================================================

从主语言(zh)翻译文件读取所有 key，调用翻译 API 生成目标语言翻译。
支持增量更新：只翻译缺失的 key，不覆盖已有的翻译。

支持的翻译引擎（通过环境变量配置）:
  - deepseek  (默认)  需要 DEEPSEEK_API_KEY
  - baidu              需要 BAIDU_APP_ID + BAIDU_APP_KEY
  - youdao             需要 YOUDAO_APP_KEY + YOUDAO_APP_SECRET

使用方式:
  # 后端翻译（更新 backend/app/i18n.py 中的 TRANSLATIONS 字典）
  python auto_translate.py

  # 前端翻译（更新 frontend/src/i18n/ 下的 .ts 文件）
  python auto_translate.py --mode frontend

  # 指定目标语言（默认更新所有非 zh 语言）
  python auto_translate.py --langs en,ja,ko

  # 仅翻译缺失的 key（增量更新）
  python auto_translate.py --incremental-only

  # 指定翻译引擎
  python auto_translate.py --engine deepseek
"""

import ast
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ════════════════════════════════════════════════════════════
# 配置常量
# ════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # D:/AI数智名片

# 后端翻译文件路径
BACKEND_I18N_FILE = PROJECT_ROOT / "backend" / "app" / "i18n.py"
BACKEND_I18N_DIR = PROJECT_ROOT / "backend" / "app" / "i18n"
BACKEND_TRANSLATIONS_DIR = BACKEND_I18N_DIR / "translations"

# 前端翻译文件路径
FRONTEND_I18N_DIR = PROJECT_ROOT / "frontend" / "src" / "i18n"

# 所有支持的语言（按语言族排序）
ALL_LANGS = ["zh", "en", "ja", "ko", "es", "fr", "de", "pt", "ru", "ar", "th", "vi"]

# RTL 语言列表
RTL_LANGS = {"ar", "he", "fa", "ur"}

# 语言 → 语言名（用于翻译 prompt）
LANG_NAMES = {
    "zh": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "ru": "Русский",
    "ar": "العربية",
    "th": "ไทย",
    "vi": "Tiếng Việt",
}

# 默认翻译引擎
DEFAULT_ENGINE = "deepseek"

# 批量翻译每批大小
BATCH_SIZE = 20

# API 重试配置
MAX_RETRIES = 3
RETRY_DELAY_SEC = 5


# ════════════════════════════════════════════════════════════
# 数据结构
# ════════════════════════════════════════════════════════════

@dataclass
class TranslationEntry:
    """单个翻译条目"""
    key: str
    zh: str                # 源语言（中文）文本
    en: Optional[str] = None   # 英文文本（如果已有）
    context: str = ""          # 注释上下文（如 '卡片', '分析' 等）


@dataclass
class TranslationResult:
    """翻译结果统计"""
    total_keys: int = 0
    existing_keys: int = 0
    translated_keys: int = 0
    failed_keys: int = 0
    failed_details: list[str] = field(default_factory=list)
    elapsed: float = 0.0


# ════════════════════════════════════════════════════════════
# 解析器：从源文件提取翻译条目
# ════════════════════════════════════════════════════════════

class BackendI18nParser:
    """解析 backend/app/i18n.py 中的 TRANSLATIONS 字典，提取所有 key 和 zh 翻译"""

    SECTION_PATTERN = re.compile(r'# ── (.+?) ─')

    @classmethod
    def parse(cls, filepath: Path) -> dict[str, TranslationEntry]:
        """解析 i18n.py 返回 {key: TranslationEntry}"""
        if not filepath.exists():
            print(f"[ERROR] 后端翻译文件不存在: {filepath}")
            return {}

        content = filepath.read_text(encoding="utf-8")
        entries: dict[str, TranslationEntry] = {}
        current_section = ""

        for line in content.splitlines():
            # 检测 section 注释
            m = cls.SECTION_PATTERN.search(line)
            if m:
                current_section = m.group(1).strip()

            # 匹配形如: "key_str": _fill_langs({"zh": "...", "en": "...", ...}),
            # 或:  'key_str': _fill_langs({"zh": "...", "en": "...", ...}),
            match = re.match(
                r'\s*["\']([^"\']+)["\']\s*:\s*_fill_langs\(\{([^}]+)\}\).*,?\s*',
                line,
            )
            if not match:
                continue

            key = match.group(1)
            dict_body = match.group(2)

            # 从 dict_body 中提取 zh 和 en
            zh_val = cls._extract_lang_value(dict_body, "zh")
            en_val = cls._extract_lang_value(dict_body, "en")

            if zh_val:
                entries[key] = TranslationEntry(
                    key=key,
                    zh=zh_val,
                    en=en_val,
                    context=current_section,
                )

        return entries

    @staticmethod
    def _extract_lang_value(dict_body: str, lang: str) -> Optional[str]:
        """从 'zh': 'value', 'en': 'value' 字符串中提取指定语言的值"""
        # 匹配 "lang": "value" 或 'lang': 'value'
        m = re.search(
            rf'["\']{lang}["\']\s*:\s*["\']([^"\']*)["\']',
            dict_body,
        )
        return m.group(1) if m else None


class FrontendI18nParser:
    """解析 frontend/src/i18n/zh.ts 前端翻译文件"""

    @classmethod
    def parse(cls, filepath: Path) -> dict[str, TranslationEntry]:
        """解析 zh.ts 返回 {key: TranslationEntry}"""
        if not filepath.exists():
            print(f"[ERROR] 前端翻译文件不存在: {filepath}")
            return {}

        content = filepath.read_text(encoding="utf-8")
        entries: dict[str, TranslationEntry] = {}
        current_section = ""

        for line in content.splitlines():
            # 检测 section 注释
            m = re.search(r'// ===== (.+?) =====', line)
            if m:
                current_section = m.group(1).strip()

            # 匹配形如: 'key': 'value',
            match = re.match(
                r"\s*['\"](\S[^'\"]*\S)['\"]\s*:\s*['\"]([^'\"]*)['\"],?\s*",
                line,
            )
            if not match:
                continue

            key = match.group(1)
            val = match.group(2)
            entries[key] = TranslationEntry(
                key=key,
                zh=val,
                context=current_section,
            )

        return entries


# ════════════════════════════════════════════════════════════
# 加载器：加载目标语言已有翻译
# ════════════════════════════════════════════════════════════

class BackendTranslationLoader:
    """从 backend/app/i18n.py 加载指定语言的已有翻译"""

    @classmethod
    def load_existing(cls, filepath: Path, lang: str) -> dict[str, str]:
        """从 TRANSLATIONS 字典中提取指定语言的所有已有翻译，返回 {key: translation}"""
        if not filepath.exists():
            return {}

        content = filepath.read_text(encoding="utf-8")
        existing: dict[str, str] = {}

        for line in content.splitlines():
            match = re.match(
                r'\s*["\']([^"\']+)["\']\s*:\s*_fill_langs\(\{([^}]+)\}\).*,?\s*',
                line,
            )
            if not match:
                continue

            key = match.group(1)
            dict_body = match.group(2)
            val = BackendI18nParser._extract_lang_value(dict_body, lang)
            if val:
                existing[key] = val

        return existing

    @classmethod
    def load_existing_from_file(cls, filepath: Path, lang: str) -> dict[str, str]:
        """从 translations_{lang}.py 文件中加载已有翻译"""
        if not filepath.exists():
            return {}
        # 支持简单的 Python dict 格式: TRANSLATIONS = { 'key': 'value', ... }
        # 或者导出 const LANG = { 'key': 'value', ... }
        content = filepath.read_text(encoding="utf-8")
        existing: dict[str, str] = {}

        for line in content.splitlines():
            match = re.match(
                r"\s*['\"](\S[^'\"]*\S)['\"]\s*:\s*['\"]([^'\"]*)['\"],?\s*",
                line,
            )
            if match:
                existing[match.group(1)] = match.group(2)

        return existing


class FrontendTranslationLoader:
    """从前端 .ts 文件加载指定语言的已有翻译"""

    @classmethod
    def load_existing(cls, filepath: Path) -> dict[str, str]:
        """加载前端 .ts 文件中的翻译，返回 {key: translation}"""
        if not filepath.exists():
            return {}

        content = filepath.read_text(encoding="utf-8")
        existing: dict[str, str] = {}

        for line in content.splitlines():
            match = re.match(
                r"\s*['\"](\S[^'\"]*\S)['\"]\s*:\s*['\"]([^'\"]*)['\"],?\s*",
                line,
            )
            if match:
                existing[match.group(1)] = match.group(2)

        return existing


# ════════════════════════════════════════════════════════════
# 翻译引擎
# ════════════════════════════════════════════════════════════

class DeepSeekTranslator:
    """DeepSeek API 翻译引擎"""

    API_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = None

    def _get_session(self):
        if self._session is None:
            import urllib.request
            self._session = urllib.request
        return self._session

    def translate_batch(
        self,
        entries: list[TranslationEntry],
        target_lang: str,
    ) -> list[tuple[str, str]]:
        """
        批量翻译一批条目
        返回: [(key, translated_text), ...]
        """
        if not entries:
            return []

        target_name = LANG_NAMES.get(target_lang, target_lang)
        source_lang_name = LANG_NAMES.get("zh", "简体中文")

        # 构建翻译 prompt
        texts = [f"[{e.key}] {e.zh}" for e in entries]
        texts_str = "\n".join(texts)

        system_prompt = (
            f"你是一个专业的翻译专家。请将以下从 {source_lang_name} 到 {target_name} 的翻译任务完成。\n"
            f"要求：\n"
            f"1. 保持专业、自然的语气\n"
            f"2. 保持占位符 {{variable}} 不变，不要翻译它们\n"
            f"3. 保持原有的标点符号风格\n"
            f"4. 返回 JSON 格式: {{\"translations\": [{{\"key\": \"...\", \"translation\": \"...\"}}, ...]}}\n"
            f"5. 不要改变 key 值，只翻译翻译文本部分\n"
            f"6. 每行格式为 [key] 原文，请在翻译结果中保持 key 不变"
        )

        user_prompt = f"请将以下内容翻译成 {target_name}：\n\n{texts_str}"

        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }

        result = self._call_api(payload)
        return self._parse_result(result, entries)

    def _call_api(self, payload: dict) -> Optional[dict]:
        """调用 DeepSeek API"""
        import urllib.request as request_lib

        data = json.dumps(payload).encode("utf-8")
        req = request_lib.Request(
            self.API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        for attempt in range(MAX_RETRIES):
            try:
                with request_lib.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"  [WARN] API 调用失败 (第 {attempt + 1}/{MAX_RETRIES} 次): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SEC)
                else:
                    print(f"  [ERROR] API 调用最终失败")
                    return None

    def _parse_result(
        self, api_result: Optional[dict], entries: list[TranslationEntry]
    ) -> list[tuple[str, str]]:
        """解析 API 返回结果"""
        if not api_result:
            return [(e.key, "") for e in entries]

        try:
            content = api_result["choices"][0]["message"]["content"]
            data = json.loads(content)
            translations = data.get("translations", [])

            result_map = {}
            for item in translations:
                result_map[item["key"]] = item["translation"]

            return [(e.key, result_map.get(e.key, "")) for e in entries]
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            print(f"  [WARN] 解析 API 返回结果失败: {e}")
            # 尝试从原始文本中提取
            return self._fallback_parse(api_result, entries)

    def _fallback_parse(
        self, api_result: dict, entries: list[TranslationEntry]
    ) -> list[tuple[str, str]]:
        """备用解析：直接从 content 文本中读取"""
        try:
            content = api_result.get("choices", [{}])[0].get("message", {}).get("content", "")
            results = []
            for entry in entries:
                # 查找 [entry.key] 后面的文本
                m = re.search(rf'\[{re.escape(entry.key)}\].*?["\']?([^"\'\n]+)', content)
                results.append((entry.key, m.group(1).strip() if m else ""))
            return results
        except Exception:
            return [(e.key, "") for e in entries]


class BaiduTranslator:
    """百度翻译 API (需要 app_id + app_key)"""

    API_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"

    def __init__(self, app_id: str, app_key: str):
        self.app_id = app_id
        self.app_key = app_key

    def translate_batch(
        self,
        entries: list[TranslationEntry],
        target_lang: str,
    ) -> list[tuple[str, str]]:
        """百度翻译不支持真正的批量 key 映射，逐条翻译"""
        import hashlib
        import random
        import urllib.request as request_lib
        import urllib.parse

        lang_map = {
            "en": "en", "ja": "jp", "ko": "kor",
            "es": "spa", "fr": "fra", "de": "de",
            "pt": "pt", "ru": "ru", "ar": "ara",
            "th": "th", "vi": "vie",
        }
        to = lang_map.get(target_lang, target_lang)

        results: list[tuple[str, str]] = []
        for entry in entries:
            text = entry.zh
            if not text:
                results.append((entry.key, ""))
                continue

            salt = str(random.randint(32768, 65536))
            sign_str = self.app_id + text + salt + self.app_key
            sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()

            params = urllib.parse.urlencode({
                "q": text,
                "from": "zh",
                "to": to,
                "appid": self.app_id,
                "salt": salt,
                "sign": sign,
            })
            url = f"{self.API_URL}?{params}"

            for attempt in range(MAX_RETRIES):
                try:
                    with request_lib.urlopen(url, timeout=15) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if "trans_result" in data:
                            translated = data["trans_result"][0]["dst"]
                            results.append((entry.key, translated))
                        else:
                            print(f"  [WARN] 百度翻译失败 {entry.key}: {data}")
                            results.append((entry.key, ""))
                        break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_SEC)
                    else:
                        print(f"  [ERROR] 百度翻译失败 {entry.key}: {e}")
                        results.append((entry.key, ""))

        return results


class YoudaoTranslator:
    """有道翻译 API"""

    API_URL = "https://openapi.youdao.com/api"

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret

    def translate_batch(
        self,
        entries: list[TranslationEntry],
        target_lang: str,
    ) -> list[tuple[str, str]]:
        """有道翻译，逐条翻译"""
        import hashlib
        import random
        import urllib.request as request_lib
        import urllib.parse

        lang_map = {
            "en": "EN", "ja": "JA", "ko": "KR",
            "es": "ES", "fr": "FR", "de": "DE",
            "pt": "PT", "ru": "RU", "ar": "AR",
            "th": "TH", "vi": "VI",
        }
        to = lang_map.get(target_lang, target_lang.upper())

        results: list[tuple[str, str]] = []
        for entry in entries:
            text = entry.zh
            if not text:
                results.append((entry.key, ""))
                continue

            salt = str(random.randint(32768, 65536))
            curtime = str(int(time.time()))
            sign_str = self.app_key + text + salt + curtime + self.app_secret
            sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest()

            params = urllib.parse.urlencode({
                "q": text,
                "from": "zh-CHS",
                "to": to,
                "appKey": self.app_key,
                "salt": salt,
                "sign": sign,
                "signType": "v3",
                "curtime": curtime,
            })
            url = f"{self.API_URL}?{params}"

            for attempt in range(MAX_RETRIES):
                try:
                    with request_lib.urlopen(url, timeout=15) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if "translation" in data and data["translation"]:
                            results.append((entry.key, data["translation"][0]))
                        else:
                            print(f"  [WARN] 有道翻译失败 {entry.key}: {data.get('errorCode', '')}")
                            results.append((entry.key, ""))
                        break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_SEC)
                    else:
                        print(f"  [ERROR] 有道翻译失败 {entry.key}: {e}")
                        results.append((entry.key, ""))

        return results


# ════════════════════════════════════════════════════════════
# 写入器：将翻译结果写入目标文件
# ════════════════════════════════════════════════════════════

class BackendTranslationWriter:
    """更新 backend/app/i18n.py 中的 TRANSLATIONS 字典"""

    @classmethod
    def write(
        cls,
        filepath: Path,
        source_entries: dict[str, TranslationEntry],
        target_lang: str,
        translations: dict[str, str],
        incremental: bool = True,
    ) -> int:
        """
        将翻译合并到 i18n.py 文件中
        返回更新的行数
        """
        if not filepath.exists():
            print(f"[ERROR] 目标文件不存在: {filepath}")
            return 0

        content = filepath.read_text(encoding="utf-8")
        lines = content.splitlines()
        updated_count = 0

        new_lines = []
        for line in lines:
            # 检测哪些行包含需要更新的 key
            match = re.match(
                r'\s*["\']([^"\']+)["\']\s*:\s*_fill_langs\(\{([^}]*)\}\).*,?\s*',
                line,
            )
            if match:
                key = match.group(1)
                if key in translations:
                    dict_body = match.group(2)
                    old_val = BackendI18nParser._extract_lang_value(dict_body, target_lang)

                    # 如果已有翻译且 incremental=True，跳过
                    if incremental and old_val:
                        new_lines.append(line)
                        continue

                    new_val = translations[key]
                    if not new_val:
                        new_lines.append(line)
                        continue

                    # 如果该语言已存在，替换值
                    if target_lang in dict_body:
                        new_dict = re.sub(
                            rf'["\']{target_lang}["\']\s*:\s*["\'][^"\']*["\']',
                            f'"{target_lang}": "{new_val}"',
                            dict_body,
                        )
                    else:
                        # 在 dict 末尾添加新语言
                        new_dict = dict_body.rstrip().rstrip(",")
                        new_dict += f', "{target_lang}": "{new_val}"'

                    # 重建行
                    indent = re.match(r'(\s*)', line).group(1)
                    new_line = f'{indent}"{key}": _fill_langs({{{new_dict}}}),'
                    new_lines.append(new_line)
                    updated_count += 1
                    continue

            new_lines.append(line)

        filepath.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return updated_count


class FrontendTranslationWriter:
    """更新前端 .ts 翻译文件"""

    @classmethod
    def write(
        cls,
        filepath: Path,
        source_entries: dict[str, TranslationEntry],
        translations: dict[str, str],
        target_lang: str,
        incremental: bool = True,
    ) -> int:
        """
        写入前端 .ts 翻译文件
        如果文件不存在，基于 zh.ts 模板创建
        返回更新的行数
        """
        lang_name = LANG_NAMES.get(target_lang, target_lang)
        header_comment = f"// AI数智名片 {lang_name} language pack"
        if target_lang in RTL_LANGS:
            header_comment = f"// AI数智名片 حزمة اللغة {lang_name}"

        if not filepath.exists():
            # 基于 zh.ts 创建模板
            return cls._create_from_template(filepath, source_entries, translations, target_lang, lang_name)

        # 更新已有文件
        content = filepath.read_text(encoding="utf-8")
        lines = content.splitlines()
        updated_count = 0
        key_order = list(source_entries.keys())

        # 构建现有翻译映射
        existing = FrontendTranslationLoader.load_existing(filepath)

        new_lines = []
        for line in lines:
            match = re.match(
                r"\s*['\"](\S[^'\"]*\S)['\"]\s*:\s*['\"]([^'\"]*)['\"],?\s*",
                line,
            )
            if match:
                key = match.group(1)
                if key in translations:
                    old_val = existing.get(key)
                    if incremental and old_val:
                        new_lines.append(line)
                        continue

                    new_val = translations[key]
                    if not new_val:
                        new_lines.append(line)
                        continue

                    indent = re.match(r'(\s*)', line).group(1)
                    escaped_val = new_val.replace("\\", "\\\\").replace("'", "\\'")
                    new_lines.append(f"{indent}'{key}': '{escaped_val}',")
                    updated_count += 1
                    continue

            new_lines.append(line)

        filepath.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return updated_count

    @classmethod
    def _create_from_template(
        cls,
        filepath: Path,
        source_entries: dict[str, TranslationEntry],
        translations: dict[str, str],
        target_lang: str,
        lang_name: str,
    ) -> int:
        """基于 zh.ts 模板创建新语言文件"""
        zh_file = FRONTEND_I18N_DIR / "zh.ts"
        if not zh_file.exists():
            print(f"[ERROR] 源模板文件不存在: {zh_file}")
            return 0

        zh_content = zh_file.read_text(encoding="utf-8")
        lines = zh_content.splitlines()
        new_lines = []
        count = 0

        for line in lines:
            # 替换文件头注释
            if line.startswith("// AI数智名片"):
                if target_lang in RTL_LANGS:
                    new_lines.append(f"// AI数智名片 حزمة اللغة {lang_name}")
                else:
                    new_lines.append(f"// AI数智名片 {lang_name} language pack")
                continue

            # 替换 const 声明
            if line.startswith("const zh:"):
                new_lines.append(f"const {target_lang}: Record<string, string> = {{")
                continue

            # 替换翻译值
            match = re.match(
                r"\s*['\"](\S[^'\"]*\S)['\"]\s*:\s*['\"]([^'\"]*)['\"],?\s*",
                line,
            )
            if match:
                key = match.group(1)
                if key in translations and translations[key]:
                    escaped_val = translations[key].replace("\\", "\\\\").replace("'", "\\'")
                    indent = re.match(r'(\s*)', line).group(1)
                    new_lines.append(f"{indent}'{key}': '{escaped_val}',")
                    count += 1
                else:
                    new_lines.append(line)
                continue

            new_lines.append(line)

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return count


# ════════════════════════════════════════════════════════════
# 主管道
# ════════════════════════════════════════════════════════════

class TranslationPipeline:
    """自动翻译管道"""

    def __init__(
        self,
        engine: str = "deepseek",
        mode: str = "backend",
        target_langs: Optional[list[str]] = None,
        incremental_only: bool = True,
        dry_run: bool = False,
    ):
        self.engine_name = engine
        self.mode = mode
        self.target_langs = target_langs or [l for l in ALL_LANGS if l != "zh"]
        self.incremental_only = incremental_only
        self.dry_run = dry_run
        self.translator = self._init_translator()

    def _init_translator(self):
        """初始化翻译引擎"""
        if self.engine_name == "deepseek":
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                print("[ERROR] 环境变量 DEEPSEEK_API_KEY 未设置")
                print("       请设置: export DEEPSEEK_API_KEY='your-api-key'")
                sys.exit(1)
            return DeepSeekTranslator(api_key)

        elif self.engine_name == "baidu":
            app_id = os.environ.get("BAIDU_APP_ID", "")
            app_key = os.environ.get("BAIDU_APP_KEY", "")
            if not app_id or not app_key:
                print("[ERROR] 环境变量 BAIDU_APP_ID 和 BAIDU_APP_KEY 未设置")
                sys.exit(1)
            return BaiduTranslator(app_id, app_key)

        elif self.engine_name == "youdao":
            app_key = os.environ.get("YOUDAO_APP_KEY", "")
            app_secret = os.environ.get("YOUDAO_APP_SECRET", "")
            if not app_key or not app_secret:
                print("[ERROR] 环境变量 YOUDAO_APP_KEY 和 YOUDAO_APP_SECRET 未设置")
                sys.exit(1)
            return YoudaoTranslator(app_key, app_secret)

        else:
            print(f"[ERROR] 不支持的翻译引擎: {self.engine_name}")
            print(f"       支持: deepseek, baidu, youdao")
            sys.exit(1)

    def run(self) -> dict[str, TranslationResult]:
        """运行翻译管道"""
        if self.mode == "backend":
            return self._run_backend()
        elif self.mode == "frontend":
            return self._run_frontend()
        else:
            print(f"[ERROR] 不支持的翻译模式: {self.mode}")
            print(f"       支持: backend, frontend")
            return {}

    def _run_backend(self) -> dict[str, TranslationResult]:
        """后端翻译"""
        print("=" * 60)
        print("  自动翻译管道 — 后端模式")
        print(f"  源文件: {BACKEND_I18N_FILE}")
        print(f"  翻译引擎: {self.engine_name}")
        print(f"  目标语言: {', '.join(self.target_langs)}")
        print(f"  增量模式: {'是' if self.incremental_only else '否'}")
        print(f"  预览模式: {'是' if self.dry_run else '否'}")
        print("=" * 60)

        # 1. 解析源文件
        print("\n[1/4] 解析源翻译文件...")
        source_entries = BackendI18nParser.parse(BACKEND_I18N_FILE)
        if not source_entries:
            print("[ERROR] 未能从源文件中提取任何翻译条目")
            return {}
        print(f"  ✓ 提取到 {len(source_entries)} 个翻译条目")

        results: dict[str, TranslationResult] = {}

        for lang in self.target_langs:
            print(f"\n{'─' * 50}")
            print(f"  语言: {LANG_NAMES.get(lang, lang).upper()} ({lang})")
            print(f"{'─' * 50}")

            result = TranslationResult(total_keys=len(source_entries))

            # 2. 加载已有翻译
            existing = BackendTranslationLoader.load_existing(BACKEND_I18N_FILE, lang)
            result.existing_keys = len(existing)
            print(f"  [2/4] 已有翻译: {len(existing)}/{len(source_entries)} 条")

            # 3. 找出缺失的 key
            missing_entries = []
            for key, entry in source_entries.items():
                if key not in existing or not existing[key]:
                    missing_entries.append(entry)
                elif not self.incremental_only:
                    # 非增量模式也翻译已有的
                    missing_entries.append(entry)

            if not missing_entries:
                print(f"  [3/4] ✗ 无需翻译，所有 key 已有翻译")
                result.translated_keys = 0
                results[lang] = result
                continue

            print(f"  [3/4] 待翻译: {len(missing_entries)} 条 (共 {len(source_entries)} 条)")

            # 4. 批量翻译
            translations: dict[str, str] = {}
            start_time = time.time()

            # 分批翻译
            for i in range(0, len(missing_entries), BATCH_SIZE):
                batch = missing_entries[i : i + BATCH_SIZE]
                batch_results = self.translator.translate_batch(batch, lang)
                for key, val in batch_results:
                    if val:
                        translations[key] = val
                        result.translated_keys += 1
                    else:
                        result.failed_keys += 1
                        result.failed_details.append(key)

                # 进度
                pct = min(100, int((i + len(batch)) / len(missing_entries) * 100))
                print(f"    进度: {pct}% ({i + len(batch)}/{len(missing_entries)})")

                # 避免 API 限流
                if i + BATCH_SIZE < len(missing_entries):
                    time.sleep(1)

            result.elapsed = time.time() - start_time
            print(f"  [4/4] 翻译完成: {result.translated_keys} 成功, {result.failed_keys} 失败, 耗时 {result.elapsed:.1f}s")

            # 5. 写入文件
            if not self.dry_run and translations:
                updated = BackendTranslationWriter.write(
                    BACKEND_I18N_FILE,
                    source_entries,
                    lang,
                    translations,
                    incremental=self.incremental_only,
                )
                print(f"  ✓ 已更新 {updated} 条到 {BACKEND_I18N_FILE}")

            results[lang] = result

        return results

    def _run_frontend(self) -> dict[str, TranslationResult]:
        """前端翻译"""
        print("=" * 60)
        print("  自动翻译管道 — 前端模式")
        print(f"  源文件: {FRONTEND_I18N_DIR / 'zh.ts'}")
        print(f"  翻译引擎: {self.engine_name}")
        print(f"  目标语言: {', '.join(self.target_langs)}")
        print(f"  增量模式: {'是' if self.incremental_only else '否'}")
        print(f"  预览模式: {'是' if self.dry_run else '否'}")
        print("=" * 60)

        # 1. 解析源文件
        print("\n[1/4] 解析源翻译文件...")
        zh_file = FRONTEND_I18N_DIR / "zh.ts"
        source_entries = FrontendI18nParser.parse(zh_file)
        if not source_entries:
            print("[ERROR] 未能从源文件中提取任何翻译条目")
            return {}
        print(f"  ✓ 提取到 {len(source_entries)} 个翻译条目")

        results: dict[str, TranslationResult] = {}

        for lang in self.target_langs:
            print(f"\n{'─' * 50}")
            print(f"  语言: {LANG_NAMES.get(lang, lang).upper()} ({lang})")
            print(f"{'─' * 50}")

            result = TranslationResult(total_keys=len(source_entries))
            target_file = FRONTEND_I18N_DIR / f"{lang}.ts"

            # 2. 加载已有翻译
            existing = FrontendTranslationLoader.load_existing(target_file) if target_file.exists() else {}
            result.existing_keys = len(existing)
            print(f"  [2/4] 已有翻译: {len(existing)}/{len(source_entries)} 条")

            # 3. 找出缺失的 key
            missing_entries = []
            for key, entry in source_entries.items():
                if key not in existing or not existing[key]:
                    missing_entries.append(entry)
                elif not self.incremental_only:
                    missing_entries.append(entry)

            if not missing_entries:
                print(f"  [3/4] ✗ 无需翻译，所有 key 已有翻译")
                result.translated_keys = 0
                results[lang] = result
                continue

            print(f"  [3/4] 待翻译: {len(missing_entries)} 条 (共 {len(source_entries)} 条)")

            # 4. 批量翻译
            translations: dict[str, str] = {}
            start_time = time.time()

            for i in range(0, len(missing_entries), BATCH_SIZE):
                batch = missing_entries[i : i + BATCH_SIZE]
                batch_results = self.translator.translate_batch(batch, lang)
                for key, val in batch_results:
                    if val:
                        translations[key] = val
                        result.translated_keys += 1
                    else:
                        result.failed_keys += 1
                        result.failed_details.append(key)

                pct = min(100, int((i + len(batch)) / len(missing_entries) * 100))
                print(f"    进度: {pct}% ({i + len(batch)}/{len(missing_entries)})")

                if i + BATCH_SIZE < len(missing_entries):
                    time.sleep(1)

            result.elapsed = time.time() - start_time
            print(f"  [4/4] 翻译完成: {result.translated_keys} 成功, {result.failed_keys} 失败, 耗时 {result.elapsed:.1f}s")

            # 5. 写入文件
            if not self.dry_run and translations:
                updated = FrontendTranslationWriter.write(
                    target_file,
                    source_entries,
                    translations,
                    lang,
                    incremental=self.incremental_only,
                )
                print(f"  ✓ 已更新 {updated} 条到 {target_file}")

            results[lang] = result

        return results


# ════════════════════════════════════════════════════════════
# 报告输出
# ════════════════════════════════════════════════════════════

def print_summary(results: dict[str, TranslationResult]):
    """打印翻译结果摘要"""
    print("\n" + "=" * 60)
    print("  翻译结果摘要")
    print("=" * 60)

    total_translated = 0
    total_failed = 0
    total_existing = 0

    print(f"\n  {'语言':<12} {'总计':>6} {'已有':>6} {'翻译':>6} {'失败':>6} {'耗时':>8}")
    print(f"  {'─' * 50}")

    for lang, result in results.items():
        name = LANG_NAMES.get(lang, lang)
        total_translated += result.translated_keys
        total_failed += result.failed_keys
        total_existing += result.existing_keys
        elapsed_str = f"{result.elapsed:.1f}s" if result.elapsed else "-"
        print(
            f"  {name:<12} {result.total_keys:>6} {result.existing_keys:>6} "
            f"{result.translated_keys:>6} {result.failed_keys:>6} {elapsed_str:>8}"
        )

    print(f"  {'─' * 50}")
    print(f"  {'合计':<12} {'':>6} {total_existing:>6} {total_translated:>6} {total_failed:>6}")

    if any(r.failed_details for r in results.values()):
        print(f"\n  [WARN] 以下 key 翻译失败:")
        for lang, result in results.items():
            if result.failed_details:
                for key in result.failed_details:
                    print(f"    [{lang}] {key}")

    print(f"\n  {'=' * 50}")


# ════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="AI数字名片 — 自动翻译管道",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 后端翻译（默认）
  python auto_translate.py

  # 前端翻译
  python auto_translate.py --mode frontend

  # 指定目标语言
  python auto_translate.py --langs en,ja,ko

  # 使用百度翻译
  python auto_translate.py --engine baidu

  # 预览模式（不写入）
  python auto_translate.py --dry-run

  # 强制重新翻译所有 key（非增量）
  python auto_translate.py --no-incremental
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["backend", "frontend"],
        default="backend",
        help="翻译模式: backend(后端i18n.py) / frontend(前端.ts文件) (默认: backend)",
    )
    parser.add_argument(
        "--engine",
        choices=["deepseek", "baidu", "youdao"],
        default=DEFAULT_ENGINE,
        help=f"翻译引擎 (默认: {DEFAULT_ENGINE})",
    )
    parser.add_argument(
        "--langs",
        type=str,
        default="",
        help="目标语言代码，逗号分隔 (默认: 所有非zh语言)",
    )
    parser.add_argument(
        "--incremental-only",
        action="store_true",
        default=True,
        help="仅翻译缺失的 key，不覆盖已有翻译 (默认启用)",
    )
    parser.add_argument(
        "--no-incremental",
        action="store_false",
        dest="incremental_only",
        help="强制重新翻译所有 key，覆盖已有翻译",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="预览模式：仅显示将要翻译的内容，不写入文件",
    )

    args = parser.parse_args()

    # 解析目标语言
    target_langs = None
    if args.langs:
        target_langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    # 运行管道
    pipeline = TranslationPipeline(
        engine=args.engine,
        mode=args.mode,
        target_langs=target_langs,
        incremental_only=args.incremental_only,
        dry_run=args.dry_run,
    )

    results = pipeline.run()

    if results:
        print_summary(results)

    # 返回非零退出码如果有失败
    if any(r.failed_keys > 0 for r in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
