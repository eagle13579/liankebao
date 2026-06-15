#!/usr/bin/env python3
"""
安全消毒引擎 (Security Sanitization Engine)
===========================================
全量安全消毒引擎，支持递归消毒嵌套字典/列表结构。
包含：基础消毒、Unicode攻击防护、SSRF防护、深度嵌套保护。

模块：向海容知識庫 · 記憶宮殿 · 数据安全层
"""

import ipaddress
import re
import unicodedata
import urllib.parse
from typing import Any

__version__ = "2.1.0"

# =====================================================================
#  配置常量
# =====================================================================

# ---- 深度嵌套保护 ----
MAX_NESTING_DEPTH: int = 10
MAX_KEYS_PER_OBJECT: int = 500
MAX_STRING_LENGTH: int = 100_000
MAX_LIST_LENGTH: int = 10_000

# ---- 控制字符 ----
CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# ---- Unicode 零宽字符 ----
ZERO_WIDTH_CHARS = re.compile(
    "[\u200b\u200c\u200d\ufeff\u200e\u200f\u2060\u2061\u2062"
    "\u2063\u2064\u2066\u2067\u2068\u2069\u202a\u202b\u202c"
    "\u202d\u202e\u206a\u206b\u206c\u206d\u206e\u206f]"
)

# ---- RTL / LTR 覆盖字符 ----
BIDI_OVERRIDE_CHARS = re.compile("[\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069]")

# ---- 同形异义字检测（西里尔字母伪装拉丁字母） ----
HOMOGLYPH_CYRILLIC = {
    "\u0430",  # а (Cyrillic a) -> a
    "\u0435",  # е (Cyrillic ie) -> e
    "\u043e",  # о (Cyrillic o) -> o
    "\u0440",  # р (Cyrillic er) -> p
    "\u0441",  # с (Cyrillic es) -> c
    "\u0445",  # х (Cyrillic ha) -> x
    "\u0456",  # і (Cyrillic i) -> i
    "\u04bb",  # һ (Cyrillic shha) -> h
    "\u04cf",  # ӏ (Cyrillic palochka) -> I
    "\u0432",  # в (Cyrillic ve) -> b
    "\u043d",  # н (Cyrillic en) -> h
    "\u043a",  # к (Cyrillic ka) -> k
    "\u043c",  # м (Cyrillic em) -> m
    "\u0442",  # т (Cyrillic te) -> t
    "\u0443",  # у (Cyrillic u) -> y
    "\u0438",  # и (Cyrillic i) -> u?
}

# ---- SQL注入检测模式（15+ patterns） ----
SQL_INJECTION_PATTERNS: list[re.Pattern] = [
    # 1) 经典 OR 1=1 / OR '1'='1'
    re.compile(
        r"\bOR\s*[+%\s]*['\"]?\s*\d+\s*['\"]?\s*=\s*['\"]?\s*\d+",
        re.IGNORECASE | re.DOTALL,
    ),
    # 2) AND 1=1
    re.compile(
        r"\bAND\s*[+%\s]*['\"]?\s*\d+\s*['\"]?\s*=\s*['\"]?\s*\d+",
        re.IGNORECASE | re.DOTALL,
    ),
    # 3) UNION SELECT
    re.compile(r"\bUNION\s+(ALL\s+)?SELECT\b", re.IGNORECASE | re.DOTALL),
    # 4) 注释绕过 --
    re.compile(r"['\"]\s*--\s*", re.IGNORECASE | re.DOTALL),
    # 5) 注释绕过 # 或 --
    re.compile(r"['\"]\s*(?:#|--)\s*", re.IGNORECASE | re.DOTALL),
    # 6) 注释绕过 /* */
    re.compile(r"['\"]\s*/\*.*?\*/", re.IGNORECASE | re.DOTALL),
    # 7) 时间盲注 SLEEP/BENCHMARK
    re.compile(
        r"\b(?:SLEEP|BENCHMARK|WAITFOR\s+DELAY|PG_SLEEP)\s*\(",
        re.IGNORECASE | re.DOTALL,
    ),
    # 8) 报错注入 - ExtractValue / UpdateXML
    re.compile(
        r"\b(?:EXTRACTVALUE|UPDATEXML|GTID_SUBSET|CONVERT|CAST)\s*\(",
        re.IGNORECASE | re.DOTALL,
    ),
    # 9) 堆叠查询 ; DROP/TRUNCATE/INSERT/UPDATE/DELETE
    re.compile(
        r";\s*\b(?:DROP|TRUNCATE|INSERT|UPDATE|DELETE|ALTER|CREATE|EXEC)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # 10) 信息收集 information_schema
    re.compile(
        r"\bINFORMATION_SCHEMA\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # 11) INTO OUTFILE / INTO DUMPFILE
    re.compile(
        r"\bINTO\s+(?:OUTFILE|DUMPFILE)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # 12) LOAD_FILE / LOAD DATA
    re.compile(
        r"\b(?:LOAD_FILE|LOAD\s+DATA)\s*\(",
        re.IGNORECASE | re.DOTALL,
    ),
    # 13) 十六进制/二进制编码注入 0x...
    re.compile(
        r"['\"]?\s*0x[0-9a-fA-F]{4,}",
        re.IGNORECASE | re.DOTALL,
    ),
    # 14) 条件语句 IF/CASE 注入
    re.compile(
        r"\bIF\s*\(.*?=.*?,\s*.*?,.*?\)",
        re.IGNORECASE | re.DOTALL,
    ),
    # 15) 系统命令/存储过程 xp_cmdshell
    re.compile(
        r"\b(?:xp_cmdshell|sp_executesql|sp_makewebtask)\b",
        re.IGNORECASE | re.DOTALL,
    ),
]

# ---- XSS检测模式（15+ patterns） ----
XSS_PATTERNS: list[re.Pattern] = [
    # 1) <script> 标签
    re.compile(r"<script[\s>]", re.IGNORECASE | re.DOTALL),
    # 2) javascript: URL
    re.compile(r"\bjavascript\s*:\s*", re.IGNORECASE | re.DOTALL),
    # 3) data: URL (base64 或 text/html)
    re.compile(
        r"\bdata\s*:\s*(?:text/html|application/x-javascript|image/svg\+xml)",
        re.IGNORECASE,
    ),
    # 4) onerror=
    re.compile(r"\bonerror\s*=", re.IGNORECASE),
    # 5) onload=
    re.compile(r"\bonload\s*=", re.IGNORECASE),
    # 6) 通用事件处理器 onclick= / onmouseover= / onfocus= 等
    re.compile(
        r"\bon(?:click|mouseover|mouseout|focus|blur|change|submit|reset|"
        r"keydown|keypress|keyup|dblclick|mousedown|mouseup|select|load|"
        r"unload|abort|error|resize|scroll|input|toggle|drag|drop|"
        r"dragstart|dragend|dragenter|dragexit|dragover|dragleave)"
        r"\s*=",
        re.IGNORECASE,
    ),
    # 7) <svg ...>
    re.compile(r"<svg[\s>/]", re.IGNORECASE | re.DOTALL),
    # 8) <img ... src=...>
    re.compile(
        r"<img[\s>].*?src\s*=",
        re.IGNORECASE | re.DOTALL,
    ),
    # 9) <iframe ...>
    re.compile(r"<iframe[\s>]", re.IGNORECASE | re.DOTALL),
    # 10) <embed ...>
    re.compile(r"<embed[\s>]", re.IGNORECASE | re.DOTALL),
    # 11) <object ...>
    re.compile(r"<object[\s>]", re.IGNORECASE | re.DOTALL),
    # 12) <style ...>
    re.compile(r"<style[\s>]", re.IGNORECASE | re.DOTALL),
    # 13) eval() / setTimeout / setInterval
    re.compile(
        r"\b(?:eval|setTimeout|setInterval|Function)\s*\(",
        re.IGNORECASE | re.DOTALL,
    ),
    # 14) document.write / document.location / window.location
    re.compile(
        r"\b(?:document\.write|document\.location|window\.location)\s*\(",
        re.IGNORECASE | re.DOTALL,
    ),
    # 15) HTML事件属性（泛型）<tag ... onXX=>
    re.compile(
        r"<[a-zA-Z][a-zA-Z0-9]*[\s>][^>]*?\s+on\w+\s*=",
        re.IGNORECASE | re.DOTALL,
    ),
    # 16) base64 html data URL
    re.compile(
        r"data\s*:\s*text/html\s*;\s*base64",
        re.IGNORECASE,
    ),
]

# ---- JSON注入检测 ----
JSON_INJECTION_PATTERNS: list[re.Pattern] = [
    # JSON 结构闭合
    re.compile(r"['\"]\s*\}\s*['\"]?.*?\{", re.DOTALL),
    # 原型污染关键词
    re.compile(r"\b__proto__\b"),
    re.compile(r"\bconstructor\b"),
    re.compile(r"\bprototype\b"),
    # 原型污染 __proto__: ...
    re.compile(r"['\"]__proto__['\"]\s*:", re.DOTALL),
]

# ---- SSRF检测 ----
SSRF_PRIVATE_IPV4_RANGES = [
    ("10.0.0.0", "10.255.255.255"),
    ("172.16.0.0", "172.31.255.255"),
    ("192.168.0.0", "192.168.255.255"),
    ("127.0.0.0", "127.255.255.255"),
    ("169.254.0.0", "169.254.255.255"),
    ("0.0.0.0", "0.255.255.255"),
    ("100.64.0.0", "100.127.255.255"),  # CGNAT
    ("198.18.0.0", "198.19.255.255"),  # Benchmark
]

SSRF_PRIVATE_IPV6_RANGES = [
    ("::1", "::1"),
    ("fc00::", "fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"),
    ("fe80::", "febf:ffff:ffff:ffff:ffff:ffff:ffff:ffff"),
]

METADATA_ENDPOINT_PATTERNS = re.compile(
    r"(?:169\.254\.169\.254|metadata\.google\.internal|"
    r"metadata\.google\.com|metadata\.azure\.com|"
    r"100\.100\.100\.200|instance-data)",
    re.IGNORECASE,
)

SSRF_DANGEROUS_PROTOCOLS = re.compile(
    r"^(?:file|gopher|dict|ldap|tftp|ftp)://",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(
    r"(?:https?|ftp|file|gopher|dict|ldap|tftp)://[^\s<>\"']+",
    re.IGNORECASE,
)

# =====================================================================
#  辅助函数
# =====================================================================


def _normalize_nfkc(text: str) -> str:
    """NFKC归一化（Unicode规范化）"""
    return unicodedata.normalize("NFKC", text)


def _strip_control_chars(text: str) -> str:
    """移除控制字符"""
    return CONTROL_CHARS_PATTERN.sub("", text)


def _strip_zero_width_chars(text: str) -> str:
    """移除零宽字符"""
    return ZERO_WIDTH_CHARS.sub("", text)


def _strip_bidi_overrides(text: str) -> str:
    """移除双向文本覆盖字符"""
    return BIDI_OVERRIDE_CHARS.sub("", text)


def _has_cyrillic_homoglyphs(text: str) -> list[str]:
    """检测字符串中的西里尔同形字母"""
    found: list[str] = []
    for i, ch in enumerate(text):
        if ch in HOMOGLYPH_CYRILLIC:
            found.append(f"U+{ord(ch):04X} '{ch}' at pos {i}")
    return found


def _detect_sql_injection(text: str) -> str | None:
    """检测SQL注入，返回匹配的pattern编号"""
    for i, pattern in enumerate(SQL_INJECTION_PATTERNS, 1):
        if pattern.search(text):
            return f"sql_injection_pattern_{i}"
    return None


def _detect_xss(text: str) -> str | None:
    """检测XSS，返回匹配的pattern编号"""
    for i, pattern in enumerate(XSS_PATTERNS, 1):
        if pattern.search(text):
            return f"xss_pattern_{i}"
    return None


def _detect_json_injection(text: str) -> str | None:
    """检测JSON注入/原型污染"""
    for i, pattern in enumerate(JSON_INJECTION_PATTERNS, 1):
        if pattern.search(text):
            return f"json_injection_pattern_{i}"
    return None


def _extract_urls(text: str) -> list[str]:
    """从文本中提取所有URL（完整匹配）"""
    return [m.group(0) for m in URL_PATTERN.finditer(text)]


def _is_private_ip(ip_str: str) -> bool:
    """判断IP地址是否为内网/私有地址"""
    try:
        ip = ipaddress.ip_address(ip_str.strip())
        if ip.version == 4:
            for start, end in SSRF_PRIVATE_IPV4_RANGES:
                if ipaddress.IPv4Address(start) <= ip <= ipaddress.IPv4Address(end):
                    return True
        elif ip.version == 6:
            for start, end in SSRF_PRIVATE_IPV6_RANGES:
                if ipaddress.IPv6Address(start) <= ip <= ipaddress.IPv6Address(end):
                    return True
        return False
    except ValueError:
        return False


def _extract_ips_from_url(url: str) -> list[str]:
    """从URL中提取主机名/IP"""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if hostname:
        return [hostname]
    return []


def _detect_ssrf(text: str) -> str | None:
    """检测SSRF攻击向量"""
    # 1) 检测 metadata endpoint
    if METADATA_ENDPOINT_PATTERNS.search(text):
        return "ssrf_metadata_endpoint"

    # 2) 检测 file:// 等危险协议
    if SSRF_DANGEROUS_PROTOCOLS.match(text.strip()):
        proto = text.strip().split("://")[0]
        return f"ssrf_dangerous_protocol_{proto}"

    # 3) 直接检测文本中的内网IP
    for token in text.strip().split():
        token = token.strip("'\",;()[]{}<>")
        if _is_private_ip(token):
            return f"ssrf_private_ip_{token}"
        if token.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"):
            return f"ssrf_private_ip_{token}"

    # 4) 提取URL检测
    for url in _extract_urls(text):
        for ip_str in _extract_ips_from_url(url):
            if _is_private_ip(ip_str):
                return f"ssrf_private_ip_{ip_str}"
            if ip_str in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"):
                return f"ssrf_private_ip_{ip_str}"

    return None


# =====================================================================
#  异常类
# =====================================================================


class SanitizerError(Exception):
    """消毒器异常基类"""

    pass


class InjectionDetectedError(SanitizerError):
    """检测到注入攻击"""

    def __init__(self, pattern: str, field: str, value: str):
        self.pattern = pattern
        self.field = field
        self.value = value
        super().__init__(f"Injection detected: {pattern} at field '{field}'")


class MaxDepthExceededError(SanitizerError):
    """超过最大嵌套深度"""

    pass


# =====================================================================
#  主要消毒类
# =====================================================================


class Sanitizer:
    """
    安全消毒引擎主类

    提供递归消毒、Unicode防护、SSRF防护、深度嵌套保护。
    """

    def __init__(
        self,
        max_depth: int = MAX_NESTING_DEPTH,
        max_keys: int = MAX_KEYS_PER_OBJECT,
        max_string_length: int = MAX_STRING_LENGTH,
        max_list_length: int = MAX_LIST_LENGTH,
        raise_on_injection: bool = False,
    ):
        """
        初始化消毒器

        Args:
            max_depth: 最大递归深度
            max_keys: 字典最大键数
            max_string_length: 字符串最大长度
            max_list_length: 列表最大元素数
            raise_on_injection: 检测到注入时是否抛出异常
        """
        self.max_depth = max_depth
        self.max_keys = max_keys
        self.max_string_length = max_string_length
        self.max_list_length = max_list_length
        self.raise_on_injection = raise_on_injection

    # ----------------------------------------------------------------
    #  字符串级消毒（工序1-9）
    # ----------------------------------------------------------------

    def sanitize_string(
        self,
        text: str,
        field_name: str = "<unknown>",
    ) -> tuple[str, list[str]]:
        """
        对单个字符串执行全量消毒工序

        工序:
          1. NFKC归一化
          2. 控制字符清洗
          3. 零宽字符检测+清除
          4. RTL覆盖字符检测+清除
          5. SQL注入检测
          6. XSS检测
          7. JSON注入检测
          8. SSRF检测
          9. 同形异义字警告

        Returns:
            (cleaned_text, warnings_list)
        """
        warnings: list[str] = []
        original = text

        # 工序1: NFKC归一化
        text = _normalize_nfkc(text)

        # 工序2: 控制字符清洗
        before = len(text)
        text = _strip_control_chars(text)
        if len(text) < before:
            warnings.append(f"[{field_name}] 移除了 {before - len(text)} 个控制字符")

        # 工序3: 零宽字符检测+清除
        before = len(text)
        text = _strip_zero_width_chars(text)
        if len(text) < before:
            warnings.append(f"[{field_name}] 移除了 {before - len(text)} 个零宽字符")

        # 工序4: RTL覆盖字符清除
        before = len(text)
        text = _strip_bidi_overrides(text)
        if len(text) < before:
            warnings.append(f"[{field_name}] 移除了 {before - len(text)} 个双向文本覆盖字符")

        # 工序5: SQL注入检测
        sql_match = _detect_sql_injection(text)
        if sql_match:
            msg = f"[{field_name}] SQL注入检测: {sql_match}"
            warnings.append(msg)
            if self.raise_on_injection:
                raise InjectionDetectedError(sql_match, field_name, original)

        # 工序6: XSS检测
        xss_match = _detect_xss(text)
        if xss_match:
            msg = f"[{field_name}] XSS检测: {xss_match}"
            warnings.append(msg)
            if self.raise_on_injection:
                raise InjectionDetectedError(xss_match, field_name, original)

        # 工序7: JSON注入检测
        json_match = _detect_json_injection(text)
        if json_match:
            msg = f"[{field_name}] JSON注入检测: {json_match}"
            warnings.append(msg)
            if self.raise_on_injection:
                raise InjectionDetectedError(json_match, field_name, original)

        # 工序8: SSRF检测
        ssrf_match = _detect_ssrf(text)
        if ssrf_match:
            msg = f"[{field_name}] SSRF检测: {ssrf_match}"
            warnings.append(msg)
            if self.raise_on_injection:
                raise InjectionDetectedError(ssrf_match, field_name, original)

        # 工序9: 同形异义字警告
        homoglyphs = _has_cyrillic_homoglyphs(text)
        if homoglyphs:
            warnings.append(f"[{field_name}] 检测到 {len(homoglyphs)} 个西里尔同形字母: {'; '.join(homoglyphs[:5])}")

        # 字符串长度截断保护
        if len(text) > self.max_string_length:
            warnings.append(f"[{field_name}] 字符串长度 {len(text)} 超过限制 {self.max_string_length}，截断处理")
            text = text[: self.max_string_length]

        return text, warnings

    # ----------------------------------------------------------------
    #  深度嵌套检测
    # ----------------------------------------------------------------

    def _check_depth(self, depth: int) -> None:
        """检查递归深度"""
        if depth > self.max_depth:
            raise MaxDepthExceededError(f"超过最大嵌套深度 {self.max_depth} (当前深度 {depth})")

    def _check_keys(self, obj: dict[str, Any], field_name: str) -> list[str]:
        """检查字典键数量"""
        if len(obj) > self.max_keys:
            return [f"[{field_name}] 键数量 {len(obj)} 超过限制 {self.max_keys}"]
        return []

    def _check_list_length(self, lst: list[Any], field_name: str) -> list[str]:
        """检查列表长度"""
        if len(lst) > self.max_list_length:
            return [f"[{field_name}] 列表长度 {len(lst)} 超过限制 {self.max_list_length}"]
        return []

    # ----------------------------------------------------------------
    #  递归消毒入口（返回纯净数据）
    # ----------------------------------------------------------------

    def sanitize(
        self,
        data: Any,
        field_name: str = "<root>",
        _depth: int = 0,
    ) -> Any:
        """
        递归消毒入口，返回消毒后的纯净数据。

        支持: dict, list, str, int, float, bool, None
        """
        self._check_depth(_depth)

        if isinstance(data, dict):
            self._check_keys(data, field_name)
            result: dict[str, Any] = {}
            for key, value in data.items():
                safe_key, _ = self.sanitize_string(str(key), field_name=f"{field_name}.key")
                result[safe_key] = self.sanitize(
                    value,
                    field_name=f"{field_name}.{safe_key}",
                    _depth=_depth + 1,
                )
            return result

        if isinstance(data, list):
            self._check_list_length(data, field_name)
            return [
                self.sanitize(
                    item,
                    field_name=f"{field_name}[{i}]",
                    _depth=_depth + 1,
                )
                for i, item in enumerate(data)
            ]

        if isinstance(data, str):
            cleaned, _ = self.sanitize_string(data, field_name=field_name)
            return cleaned

        # 基本类型: int, float, bool, None
        return data

    # ----------------------------------------------------------------
    #  带警告收集的消毒入口
    # ----------------------------------------------------------------

    def sanitize_with_warnings(
        self,
        data: Any,
        field_name: str = "<root>",
    ) -> dict[str, Any]:
        """
        全量消毒，带警告/攻击检测结果。

        Returns:
            成功: {'cleaned': data, 'warnings': [...]}
            攻击: {'injection_detected': True, 'pattern': '...',
                    'field': '...', 'value': '...'}
        """
        warnings: list[str] = []

        try:
            cleaned = self._sanitize_recursive(data, field_name, 0, warnings)
            return {
                "cleaned": cleaned,
                "warnings": warnings,
            }
        except InjectionDetectedError as e:
            return {
                "injection_detected": True,
                "pattern": e.pattern,
                "field": e.field,
                "value": e.value,
            }
        except MaxDepthExceededError:
            return {
                "injection_detected": True,
                "pattern": "max_depth_exceeded",
                "field": field_name,
                "value": str(data)[:200],
            }

    def _sanitize_recursive(
        self,
        data: Any,
        field_name: str,
        _depth: int,
        warnings: list[str],
    ) -> Any:
        """内部递归消毒，同时收集warnings"""
        self._check_depth(_depth)

        if isinstance(data, dict):
            warnings.extend(self._check_keys(data, field_name))
            result: dict[str, Any] = {}
            for key, value in data.items():
                safe_key, key_warns = self.sanitize_string(str(key), field_name=f"{field_name}.key")
                warnings.extend(key_warns)
                result[safe_key] = self._sanitize_recursive(
                    value,
                    f"{field_name}.{safe_key}",
                    _depth + 1,
                    warnings,
                )
            return result

        if isinstance(data, list):
            warnings.extend(self._check_list_length(data, field_name))
            return [
                self._sanitize_recursive(
                    item,
                    f"{field_name}[{i}]",
                    _depth + 1,
                    warnings,
                )
                for i, item in enumerate(data)
            ]

        if isinstance(data, str):
            cleaned, str_warns = self.sanitize_string(
                data,
                field_name=field_name,
            )
            warnings.extend(str_warns)
            return cleaned

        return data

    # ----------------------------------------------------------------
    #  便捷方法：直接获取warnings列表
    # ----------------------------------------------------------------

    def get_warnings(
        self,
        data: Any,
        field_name: str = "<root>",
    ) -> list[str]:
        """仅获取消毒过程中的所有warnings"""
        result = self.sanitize_with_warnings(data, field_name)
        return result.get("warnings", [])


# =====================================================================
#  便利函数（单次调用）
# =====================================================================


def sanitize(
    data: Any,
    raise_on_injection: bool = False,
    max_depth: int = MAX_NESTING_DEPTH,
) -> Any:
    """
    便利函数：创建消毒器并执行消毒。

    Args:
        data: 待消毒数据
        raise_on_injection: 检测到注入时抛出异常
        max_depth: 最大递归深度

    Returns:
        raise_on_injection=False: {'cleaned': ..., 'warnings': [...]}
        raise_on_injection=True: 纯净数据（注入时抛异常）
    """
    s = Sanitizer(max_depth=max_depth, raise_on_injection=raise_on_injection)
    if raise_on_injection:
        return s.sanitize(data)
    return s.sanitize_with_warnings(data)


# =====================================================================
#  测试/演示
# =====================================================================


def _demo():
    """快速演示消毒引擎功能"""
    print("=" * 60)
    print("  安全消毒引擎 v" + __version__ + "  演示")
    print("=" * 60)

    test_cases = [
        ("正常文本", "Hello, 世界！这是一个正常文本。"),
        ("控制字符", "Hello\x00World\x1f\x7fTest"),
        ("零宽字符", "Hello\u200bWorld\ufeffTest"),
        ("SQL注入_OR", "username=' OR 1=1 --"),
        ("SQL注入_联合查询", "id=1 UNION SELECT * FROM users"),
        ("SQL注入_时间盲注", "id=1 AND SLEEP(5)"),
        ("SQL注入_堆叠查询", "1; DROP TABLE users"),
        ("SQL注入_注释绕过", "admin'/*comment*/"),
        ("XSS_script", "<script>alert('xss')</script>"),
        ("XSS_onerror", "<img src=x onerror=alert(1)>"),
        ("XSS_javascript", "javascript:alert(document.cookie)"),
        ("XSS_data_url", "data:text/html;base64,PHNjcmlwdD4="),
        ("XSS_svg", "<svg onload=alert(1)>"),
        ("SSRF_metadata", "http://169.254.169.254/latest/meta-data/"),
        ("SSRF_file协议", "file:///etc/passwd"),
        ("SSRF_内网IP_http", "http://192.168.1.1/admin"),
        ("SSRF_内网IP_10段", "http://10.0.0.1/config"),
        ("SSRF_localhost", "http://localhost:8080/admin"),
        ("JSON注入_原型污染", '{"__proto__": {"admin": true}}'),
        ("JSON注入_constructor", "constructor.prototype"),
        ("西里尔同形", "арара test"),
        ("嵌套字典注入", {"user": {"name": "admin' OR 1=1 --", "age": 25}}),
        ("深层嵌套列表", [[[[["deep"]]]]]),
    ]

    s = Sanitizer()

    for name, value in test_cases:
        label = f"{name}: {str(value)[:55]}"
        print(f"\n>>> {label}")
        result = s.sanitize_with_warnings(value)
        if result.get("injection_detected"):
            print(f"  !! 检测到攻击: pattern={result['pattern']}, field={result['field']}")
        else:
            cleaned = result.get("cleaned", "")
            print(f"  清理后: {str(cleaned)[:60]}")
            warnings = result.get("warnings", [])
            if warnings:
                for w in warnings:
                    print(f"  警告: {w}")
            else:
                print("  无警告")

    # 深度嵌套测试
    print("\n" + "-" * 60)
    print("  深度嵌套保护测试")
    deep_data = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": {"k": "too deep"}}}}}}}}}}}
    result = s.sanitize_with_warnings(deep_data)
    if result.get("injection_detected"):
        print(f"  检测到: {result['pattern']}")
    else:
        print(f"  深度 {_max_depth(deep_data)} 层，无异常")

    # raise_on_injection 测试
    print("\n" + "-" * 60)
    print("  raise_on_injection=True 测试")
    s2 = Sanitizer(raise_on_injection=True)
    try:
        s2.sanitize("username=' OR 1=1 --")
        print("  (未抛出异常)")
    except InjectionDetectedError as e:
        print(f"  正确抛出 InjectionDetectedError: {e}")

    print("\n" + "=" * 60)
    print("  演示完毕")
    print("=" * 60)


def _max_depth(data: Any) -> int:
    """计算数据的最大嵌套深度"""
    if isinstance(data, dict):
        if not data:
            return 1
        return 1 + max(_max_depth(v) for v in data.values())
    if isinstance(data, list):
        if not data:
            return 1
        return 1 + max(_max_depth(i) for i in data)
    return 0


if __name__ == "__main__":
    _demo()
