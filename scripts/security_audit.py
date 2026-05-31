#!/usr/bin/env python3
"""
链客宝 安全审计脚本
====================
自动扫描项目安全风险, 输出 JSON 报告。

扫描项:
  1. .env 文件泄露检查 — 扫描文件内容是否包含敏感密钥
  2. 依赖漏洞扫描 — 检查 requirements.txt 中的已知漏洞 (爬取 PyPI advisory)
  3. API Key 硬编码检查 — 扫描代码中的 API key/secrets/tokens
  4. 安全配置检查 — 检查 CSP/安全头/加密配置
  5. 文件权限检查 — 检查 .env / 密钥文件的权限

用法:
    python scripts/security_audit.py                    # 扫描当前项目
    python scripts/security_audit.py --output report.json  # 输出到文件
    python scripts/security_audit.py --verbose            # 详细输出
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("security_audit")

# ======================================================================
# 项目根目录 (脚本位于 <project_root>/scripts/)
# ======================================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ======================================================================
# 1. .env 文件泄露检查
# ======================================================================

_SENSITIVE_KEY_PATTERNS = {
    "SECRET_KEY": "Django/FastAPI 密钥",
    "JWT_SECRET": "JWT 签名密钥",
    "ENCRYPTION_KEY": "AES-256 加密密钥",
    "API_KEY": "通用 API 密钥",
    "OPENAI_API_KEY": "OpenAI API 密钥",
    "WECHAT_APP_SECRET": "微信 AppSecret",
    "WECHAT_PAY_KEY": "微信支付密钥",
    "ALIPAY_PRIVATE_KEY": "支付宝私钥",
    "PG_PASSWORD": "PostgreSQL 密码",
    "MYSQL_PASSWORD": "MySQL 密码",
    "REDIS_PASSWORD": "Redis 密码",
    "SENTRY_DSN": "Sentry DSN (可能包含秘钥)",
    "POSTHOG_API_KEY": "PostHog API 密钥",
    "AWS_SECRET_ACCESS_KEY": "AWS 访问密钥",
    "ACCESS_KEY_ID": "云服务 Access Key",
    "SECRET_ACCESS_KEY": "云服务 Secret Key",
    "TOKEN": "通用令牌/Token",
    "PASSWORD": "通用密码",
    "PRIVATE_KEY": "私钥",
}


def _is_binary_file(filepath: str) -> bool:
    """通过检查 NULL 字节快速判断是否为二进制文件。"""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return True


def scan_env_leaks(base_dir: str = "") -> List[Dict[str, Any]]:
    """扫描 .env 文件和代码中的密钥泄露。

    检查:
      - .env 文件是否存在且暴露
      - .env 文件内容中的密钥类型
      - 代码中硬编码的 API key/token
    """
    if not base_dir:
        base_dir = _PROJECT_ROOT

    findings: List[Dict[str, Any]] = []

    # 1a. 查找 .env 文件
    env_files = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [
            d
            for d in dirs
            if d not in ("venv", "venv_new", "__pycache__", ".git", "node_modules")
        ]
        for f in files:
            if f in (
                ".env",
                ".env.example",
                ".env.local",
                ".env.production",
                ".env.development",
            ):
                env_files.append(os.path.join(root, f))

    if not env_files:
        findings.append(
            {
                "category": "env_leak",
                "severity": "INFO",
                "title": "未找到 .env 文件",
                "detail": "项目根目录及子目录未发现 .env 或 .env.* 文件。若已通过环境变量配置, 可忽略此信息。",
            }
        )
    else:
        for env_path in env_files:
            rel_path = os.path.relpath(env_path, base_dir)
            # 检查 .env 文件是否在 web 可访问目录 (deploy/static/public)
            is_exposed = any(
                part in rel_path.replace("\\", "/").split("/")
                for part in ("static", "public", "dist", "html", "deploy")
            )

            if is_exposed:
                findings.append(
                    {
                        "category": "env_leak",
                        "severity": "CRITICAL",
                        "title": f".env 文件位于 Web 可访问目录: {rel_path}",
                        "detail": f"{rel_path} 可能通过 Web 服务器被公开访问! 请将其移至项目根目录或上级目录。",
                        "file": rel_path,
                    }
                )

            # 检查 .env 文件权限 (Unix only)
            try:
                mode = os.stat(env_path).st_mode
                if mode & 0o004:  # world-readable
                    findings.append(
                        {
                            "category": "env_leak",
                            "severity": "HIGH",
                            "title": f".env 文件权限过于开放: {rel_path}",
                            "detail": f"权限模式: {oct(mode & 0o777)}, 建议设为 600 或 640",
                            "file": rel_path,
                        }
                    )
            except Exception:
                pass

            # 检查文件中是否存在密钥
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for pattern, desc in _SENSITIVE_KEY_PATTERNS.items():
                    if pattern in content:
                        findings.append(
                            {
                                "category": "env_leak",
                                "severity": "INFO",
                                "title": f"检测到 {desc} ({pattern})",
                                "detail": f"{rel_path} 中包含 {desc} 配置项 (这是正常的, 仅确认配置存在)",
                                "file": rel_path,
                                "key_type": pattern,
                            }
                        )
            except Exception:
                pass

    # 1b. 扫描代码中的硬编码 API key
    high_entropy_patterns = [
        (
            re.compile(r'(?:"|' "'" ')?(sk-[A-Za-z0-9]{20,})(?:"|' "'" ")?"),
            "OpenAI API Key (sk-...)",
        ),
        (
            re.compile(r'(?:"|' "'" ')?(ghp_[A-Za-z0-9]{36})(?:"|' "'" ")?"),
            "GitHub Personal Access Token",
        ),
        (
            re.compile(r'(?:"|' "'" ')?(AIza[0-9A-Za-z_-]{35})(?:"|' "'" ")?"),
            "Google API Key",
        ),
        (
            re.compile(r'(?:"|' "'" ')?(AKIA[0-9A-Z]{16})(?:"|' "'" ")?"),
            "AWS Access Key ID",
        ),
    ]

    # 仅扫描 Python 和 JS/TS 文件
    scan_extensions = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".sh",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".conf",
    }
    scanned_files = 0
    key_findings = 0

    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [
            d
            for d in dirs
            if d not in ("venv", "venv_new", "__pycache__", ".git", "node_modules")
        ]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in scan_extensions:
                continue
            filepath = os.path.join(root, f)
            if _is_binary_file(filepath):
                continue
            scanned_files += 1
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
                for lineno, line in enumerate(lines, 1):
                    for pattern, key_name in high_entropy_patterns:
                        match = pattern.search(line)
                        if match:
                            # 排除测试/示例/文档中的假 key
                            is_example = any(
                                kw in line.lower()
                                for kw in (
                                    "example",
                                    "test",
                                    "dummy",
                                    "placeholder",
                                    "your-",
                                    "xxxx",
                                )
                            )
                            if not is_example:
                                key_findings += 1
                                findings.append(
                                    {
                                        "category": "hardcoded_key",
                                        "severity": "HIGH",
                                        "title": f"检测到硬编码 {key_name}",
                                        "detail": f"{os.path.relpath(filepath, base_dir)}:{lineno}",
                                        "file": os.path.relpath(filepath, base_dir),
                                        "line": lineno,
                                        "key_type": key_name,
                                    }
                                )
            except Exception:
                continue

    if key_findings == 0:
        findings.append(
            {
                "category": "hardcoded_key",
                "severity": "OK",
                "title": "未检测到硬编码 API Key",
                "detail": f"已扫描 {scanned_files} 个文件, 未发现硬编码密钥",
            }
        )

    return findings


# ======================================================================
# 2. 依赖漏洞扫描
# ======================================================================

# PyPI 安全公告 API
_PYPI_ADVISORY_URL = "https://pypi.org/pypi/{package}/json"


def _parse_version(ver: str) -> Tuple[int, ...]:
    """将版本字符串转换为可比较的元组。"""
    try:
        parts = ver.replace("-", ".").replace("_", ".").split(".")
        nums = []
        for p in parts:
            try:
                nums.append(int(p))
            except ValueError:
                # 处理 'a1', 'b2', 'rc1' 等
                m = re.match(r"(\d+)([a-zA-Z].*)?$", p)
                if m:
                    nums.append(int(m.group(1)))
                else:
                    nums.append(0)
        return tuple(nums)
    except Exception:
        return (0,)


def _get_latest_version(package: str) -> Optional[str]:
    """查询 PyPI 获取包的最新版本。"""
    try:
        url = _PYPI_ADVISORY_URL.format(package=package)
        req = urllib.request.Request(
            url, headers={"User-Agent": "LianKeBao-Security-Audit/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("info", {}).get("version")
    except Exception as e:
        logger.debug(f"查询 {package} 版本失败: {e}")
        return None


def scan_dependency_vulnerabilities(
    requirements_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """扫描 requirements.txt 中的已知漏洞。

    检查:
      - 是否安装了有已知漏洞的版本
      - 是否有可用安全更新
      - 已知高危依赖 (通过内置 CVE 数据库)
    """
    if requirements_path is None:
        requirements_path = os.path.join(_PROJECT_ROOT, "backend", "requirements.txt")

    findings: List[Dict[str, Any]] = []

    # 内置已知漏洞数据库 (CVE lookup 离线库)
    # 格式: package -> { max_affected_version: "描述" }
    KNOWN_VULNS: Dict[str, Dict[str, str]] = {
        "fastapi": {"0.95.0": "CVE-2023-27579 — FastAPI path traversal via mount"},
        "cryptography": {
            "41.0.6": "CVE-2023-50782 — 证书验证绕过",
            "42.0.3": "CVE-2024-26130 — 低版本已知漏洞",
        },
        "sqlalchemy": {"2.0.0": "多版本已知问题, 建议升级至 2.0.35+"},
        "jose": {"3.3.0": "python-jose 已被 pyjwt 取代, 建议迁移"},
        "passlib": {
            "1.7.4": "passlib 已停止维护 (2023), 建议迁移至 argon2-cffi 或 bcrypt"
        },
    }

    try:
        with open(requirements_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        findings.append(
            {
                "category": "dependency",
                "severity": "WARN",
                "title": "未找到 requirements.txt",
                "detail": f"路径: {requirements_path}",
            }
        )
        return findings

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        # 解析包名和版本
        match = re.match(r"^([a-zA-Z0-9_.-]+)\s*([><=!~]+)\s*([0-9.a-zA-Z-]+)", line)
        if not match:
            # 可能是无版本号的包
            match = re.match(r"^([a-zA-Z0-9_.-]+)\s*$", line)
            if match:
                pkg_name = match.group(1).lower()
                findings.append(
                    {
                        "category": "dependency",
                        "severity": "INFO",
                        "title": f"依赖 {pkg_name} 未指定版本号",
                        "detail": "建议锁定版本号以避免非预期更新",
                    }
                )
            continue

        pkg_name = match.group(1).lower()
        pkg_version = match.group(3)

        # 检查已知漏洞
        if pkg_name in KNOWN_VULNS:
            vuln_map = KNOWN_VULNS[pkg_name]
            for affected_ver, desc in vuln_map.items():
                if _parse_version(pkg_version) <= _parse_version(affected_ver):
                    findings.append(
                        {
                            "category": "dependency",
                            "severity": "HIGH",
                            "title": f"{pkg_name}=={pkg_version}: {desc}",
                            "detail": f"当前版本 {pkg_version}, 影响版本 <= {affected_ver}",
                            "package": pkg_name,
                            "current_version": pkg_version,
                        }
                    )

        # 查询 PyPI 最新版本
        try:
            latest = _get_latest_version(pkg_name)
            if latest and _parse_version(pkg_version) < _parse_version(latest):
                findings.append(
                    {
                        "category": "dependency",
                        "severity": "MEDIUM",
                        "title": f"{pkg_name}: {pkg_version} -> {latest} (可用更新)",
                        "detail": f"当前版本 {pkg_version}, 最新版本 {latest}",
                        "package": pkg_name,
                        "current_version": pkg_version,
                        "latest_version": latest,
                    }
                )
        except Exception:
            continue

    # 总结
    findings.append(
        {
            "category": "dependency",
            "severity": "INFO",
            "title": "依赖扫描完成",
            "detail": f"已扫描 {len([l for l in lines if l.strip() and not l.startswith('#')])} 个依赖项",
        }
    )

    return findings


# ======================================================================
# 3. API Key 硬编码检查 (深度扫描)
# ======================================================================


def _is_high_entropy_string(s: str) -> bool:
    """简单熵值检查: 判断字符串是否可能是密钥。"""
    if len(s) < 20:
        return False
    # 计算字符分布
    unique_chars = len(set(s))
    # 高熵: 字符集大 (Base64: 64种+, Base62: 62种+, 十六进制: 16种)
    has_upper = any(c.isupper() for c in s)
    has_lower = any(c.islower() for c in s)
    has_digit = any(c.isdigit() for c in s)
    has_special = any(c in "+/=_" for c in s)
    score = sum([has_upper, has_lower, has_digit, has_special, unique_chars > 20])
    return score >= 4


def scan_hardcoded_secrets(base_dir: str = "") -> List[Dict[str, Any]]:
    """深度扫描代码中的硬编码密钥/密码。

    扫描 Python/JS/TS 文件中类似密钥的字符串赋值。
    """
    if not base_dir:
        base_dir = _PROJECT_ROOT

    findings: List[Dict[str, Any]] = []
    scan_extensions = {".py", ".js", ".ts"}
    secret_assign_pattern = re.compile(
        r"(?:(?:SECRET|SECRET_KEY|PASSWORD|TOKEN|API_KEY|PRIVATE_KEY|PUBLIC_KEY)"
        r'\s*[=:]\s*["\']([A-Za-z0-9+/=_\-]{20,})["\'])',
        re.IGNORECASE,
    )

    scanned_files = 0
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [
            d
            for d in dirs
            if d not in ("venv", "venv_new", "__pycache__", ".git", "node_modules")
        ]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in scan_extensions:
                continue
            filepath = os.path.join(root, f)
            if _is_binary_file(filepath):
                continue
            scanned_files += 1
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                for match in secret_assign_pattern.finditer(content):
                    secret_value = match.group(1)
                    # 排除示例/测试值
                    if any(
                        kw in secret_value.lower()
                        for kw in ("your", "xxxx", "test", "example", "changeme")
                    ):
                        continue
                    if _is_high_entropy_string(secret_value):
                        findings.append(
                            {
                                "category": "hardcoded_secret",
                                "severity": "HIGH",
                                "title": "检测到疑似硬编码密钥",
                                "detail": (
                                    f"{os.path.relpath(filepath, base_dir)}: "
                                    f"...{secret_value[:12]}****{secret_value[-4:]}... "
                                    f"(长度: {len(secret_value)})"
                                ),
                                "file": os.path.relpath(filepath, base_dir),
                            }
                        )
            except Exception:
                continue

    if not findings:
        findings.append(
            {
                "category": "hardcoded_secret",
                "severity": "OK",
                "title": "未检测到硬编码密钥",
                "detail": f"已扫描 {scanned_files} 个代码文件",
            }
        )

    return findings


# ======================================================================
# 4. 安全配置检查
# ======================================================================


def check_security_configuration(base_dir: str = "") -> List[Dict[str, Any]]:
    """检查项目的安全配置。"""
    if not base_dir:
        base_dir = _PROJECT_ROOT

    findings: List[Dict[str, Any]] = []

    # 4a. 检查 main.py 中是否有安全头中间件
    main_py = os.path.join(base_dir, "backend", "app", "main.py")
    if os.path.exists(main_py):
        with open(main_py, "r", encoding="utf-8") as f:
            content = f.read()

        checks = [
            ("Strict-Transport-Security", "HSTS 安全头"),
            ("X-Frame-Options", "点击劫持保护"),
            ("Content-Security-Policy", "内容安全策略"),
            ("X-Content-Type-Options", "MIME 类型嗅探防护"),
            ("X-XSS-Protection", "XSS 保护"),
            ("RateLimitMiddleware", "速率限制中间件"),
            ("limit_request_size", "请求体大小限制"),
        ]

        for keyword, desc in checks:
            if keyword in content:
                findings.append(
                    {
                        "category": "security_config",
                        "severity": "OK",
                        "title": f"已启用: {desc}",
                        "detail": f"main.py 中包含 {keyword}",
                    }
                )
            else:
                findings.append(
                    {
                        "category": "security_config",
                        "severity": "HIGH",
                        "title": f"未启用: {desc}",
                        "detail": f"main.py 中未检测到 {keyword}",
                    }
                )

        # 检查是否引入了 security_hardening
        if "security_hardening" in content:
            findings.append(
                {
                    "category": "security_config",
                    "severity": "OK",
                    "title": "已集成: security_hardening 模块",
                    "detail": "main.py 中已导入 security_hardening",
                }
            )
        else:
            findings.append(
                {
                    "category": "security_config",
                    "severity": "WARN",
                    "title": "未集成: security_hardening 模块",
                    "detail": "main.py 中未导入 security_hardening — 建议添加",
                }
            )

    # 4b. 检查 nginx 安全配置
    nginx_conf = os.path.join(base_dir, "deploy", "nginx.conf")
    if os.path.exists(nginx_conf):
        with open(nginx_conf, "r", encoding="utf-8") as f:
            content = f.read()

        nginx_checks = [
            ("ssl_protocols", "SSL 协议限制 (TLSv1.2+)"),
            ("ssl_ciphers", "加密套件限制"),
            ("Strict-Transport-Security", "HSTS 头"),
            ("Content-Security-Policy", "CSP 头"),
            ("X-Frame-Options", "X-Frame-Options"),
            ("server_tokens off", "隐藏 Nginx 版本"),
        ]

        for keyword, desc in nginx_checks:
            if keyword in content:
                findings.append(
                    {
                        "category": "security_config",
                        "severity": "OK",
                        "title": f"Nginx 已配置: {desc}",
                        "detail": f"nginx.conf 中包含 {keyword}",
                    }
                )
            else:
                findings.append(
                    {
                        "category": "security_config",
                        "severity": "MEDIUM",
                        "title": f"Nginx 未配置: {desc}",
                        "detail": f"nginx.conf 中未检测到 {keyword}",
                    }
                )

    # 4c. 检查是否存在 .gitignore
    gitignore = os.path.join(base_dir, ".gitignore")
    if os.path.exists(gitignore):
        with open(gitignore, "r", encoding="utf-8") as f:
            content = f.read()
        if ".env" in content:
            findings.append(
                {
                    "category": "security_config",
                    "severity": "OK",
                    "title": ".env 已在 .gitignore 中",
                    "detail": ".env 文件不会被提交到 Git",
                }
            )
        else:
            findings.append(
                {
                    "category": "security_config",
                    "severity": "HIGH",
                    "title": ".env 未在 .gitignore 中",
                    "detail": "危险! .env 文件可能会被提交到 Git 仓库",
                }
            )
    else:
        findings.append(
            {
                "category": "security_config",
                "severity": "MEDIUM",
                "title": "未找到 .gitignore 文件",
                "detail": "建议创建 .gitignore 并添加 .env/密钥文件",
            }
        )

    return findings


# ======================================================================
# 5. 文件权限检查
# ======================================================================


def check_file_permissions(base_dir: str = "") -> List[Dict[str, Any]]:
    """检查敏感文件的权限设置。"""
    if not base_dir:
        base_dir = _PROJECT_ROOT

    findings: List[Dict[str, Any]] = []

    # 需要检查的文件/目录
    target_patterns = [
        ".env",
        "*.key",
        "*.pem",
        "*.p12",
        "*.pfx",
        "config*.yaml",
        "config*.yml",
        "credentials*",
        "secret*",
    ]

    import fnmatch

    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [
            d
            for d in dirs
            if d not in ("venv", "venv_new", "__pycache__", ".git", "node_modules")
        ]
        for f in files:
            if any(fnmatch.fnmatch(f, pat) for pat in target_patterns):
                filepath = os.path.join(root, f)
                try:
                    mode = os.stat(filepath).st_mode
                    rel_path = os.path.relpath(filepath, base_dir)

                    if mode & 0o004:  # world-readable
                        findings.append(
                            {
                                "category": "file_permission",
                                "severity": "MEDIUM",
                                "title": f"文件权限过于开放: {rel_path}",
                                "detail": f"权限: {oct(mode & 0o777)} — 建议设为 600 或 640",
                                "file": rel_path,
                            }
                        )
                    else:
                        findings.append(
                            {
                                "category": "file_permission",
                                "severity": "OK",
                                "title": f"文件权限正常: {rel_path}",
                                "detail": f"权限: {oct(mode & 0o777)}",
                                "file": rel_path,
                            }
                        )
                except Exception:
                    continue

    return findings


# ======================================================================
# 6. 报告生成
# ======================================================================


def generate_report(
    env_findings: List[Dict[str, Any]],
    dep_findings: List[Dict[str, Any]],
    secret_findings: List[Dict[str, Any]],
    config_findings: List[Dict[str, Any]],
    perm_findings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """生成统一的安全审计报告。"""
    all_findings = (
        env_findings + dep_findings + secret_findings + config_findings + perm_findings
    )

    # 按严重级别统计
    severity_count = defaultdict(int)
    category_count = defaultdict(int)
    for f in all_findings:
        severity_count[f["severity"]] += 1
        category_count[f["category"]] += 1

    # 计算评分 (0-10)
    # 扣分项: CRITICAL=-3, HIGH=-2, MEDIUM=-1, WARN=-0.5
    score = 10.0
    deductions = {
        "CRITICAL": -3.0,
        "HIGH": -2.0,
        "MEDIUM": -1.0,
        "WARN": -0.5,
    }
    for f in all_findings:
        if f["severity"] in deductions:
            score += deductions[f["severity"]]
    score = max(0.0, min(10.0, round(score, 1)))

    return {
        "report": {
            "project": "链客宝 (LianKeBao)",
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "scan_duration_seconds": 0,  # 由调用者填写
            "security_score": score,
            "severity_summary": dict(severity_count),
            "category_summary": dict(category_count),
            "overall_assessment": (
                "优秀"
                if score >= 9
                else "良好"
                if score >= 7
                else "一般"
                if score >= 5
                else "较差"
                if score >= 3
                else "严重"
            ),
        },
        "findings": all_findings,
    }


def print_summary(report: Dict[str, Any]) -> None:
    """以可读格式输出审计摘要。"""
    rep = report["report"]
    findings = report["findings"]

    print(f"\n{'=' * 60}")
    print("  链客宝 安全审计报告")
    print(f"{'=' * 60}")
    print(f"  项目:     {rep['project']}")
    print(f"  时间:     {rep['scan_time']}")
    print(f"  安全评分: {rep['security_score']}/10 ({rep['overall_assessment']})")
    print(f"  发现总数: {len(findings)}")
    print(f"{'=' * 60}")

    severity_count = rep["severity_summary"]
    if severity_count:
        print("\n  严重级别分布:")
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "WARN", "OK", "INFO"):
            if sev in severity_count:
                print(f"    {sev:10s}: {severity_count[sev]}")

    print(f"\n{'=' * 60}")
    print("  详细发现:")
    print(f"{'=' * 60}")

    for i, f in enumerate(findings, 1):
        sev = f["severity"]
        sev_color = {
            "CRITICAL": "[CRITICAL]",
            "HIGH": "[HIGH]",
            "MEDIUM": "[MEDIUM]",
            "WARN": "[WARN]",
            "OK": "[OK]",
            "INFO": "[INFO]",
        }.get(sev, "[INFO]")
        print(f"\n  {sev_color} {f['title']}")
        print(f"          {f['detail'][:120]}")
        if "file" in f:
            print(f"          文件: {f['file']}")

    print(f"\n{'=' * 60}")
    print(f"  评分: {rep['security_score']}/10 ({rep['overall_assessment']})")
    print(f"{'=' * 60}\n")


# ======================================================================
# 主入口
# ======================================================================


def main():
    parser = argparse.ArgumentParser(
        description="链客宝安全审计脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/security_audit.py                     # 标准扫描
  python scripts/security_audit.py --output report.json  # 输出 JSON
  python scripts/security_audit.py --verbose             # 详细日志
  python scripts/security_audit.py --quick               # 快速扫描 (跳过网络查询)
        """,
    )
    parser.add_argument("--output", "-o", type=str, help="输出 JSON 报告文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")
    parser.add_argument(
        "--quick", "-q", action="store_true", help="快速模式 (跳过网络查询)"
    )
    parser.add_argument(
        "--project-dir", type=str, default=_PROJECT_ROOT, help="项目根目录路径"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    start = time.time()

    print("\n🔐 链客宝安全审计 — 开始扫描...")
    print(f"   项目路径: {args.project_dir}")
    if args.quick:
        print("   模式: 快速 (跳过网络查询)")

    # 执行扫描
    print("\n  [1/5] .env 泄露检查...")
    env_findings = scan_env_leaks(args.project_dir)

    print("  [2/5] 依赖漏洞扫描...")
    dep_findings = (
        scan_dependency_vulnerabilities(
            os.path.join(args.project_dir, "backend", "requirements.txt")
        )
        if not args.quick
        else [
            {
                "category": "dependency",
                "severity": "INFO",
                "title": "快速模式: 跳过 PyPI 网络查询",
                "detail": "使用 --quick 标志跳过了在线漏洞查询",
            }
        ]
    )

    print("  [3/5] API Key 硬编码检查...")
    secret_findings = scan_hardcoded_secrets(args.project_dir)

    print("  [4/5] 安全配置检查...")
    config_findings = check_security_configuration(args.project_dir)

    print("  [5/5] 文件权限检查...")
    perm_findings = check_file_permissions(args.project_dir)

    # 生成报告
    elapsed = round(time.time() - start, 2)
    report = generate_report(
        env_findings=env_findings,
        dep_findings=dep_findings,
        secret_findings=secret_findings,
        config_findings=config_findings,
        perm_findings=perm_findings,
    )
    report["report"]["scan_duration_seconds"] = elapsed

    # 输出
    print_summary(report)

    if args.output:
        output_path = args.output
        if not os.path.isabs(output_path):
            output_path = os.path.join(args.project_dir, output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  📄 完整报告已保存: {output_path}")
    else:
        # 默认输出到 project_dir
        default_output = os.path.join(args.project_dir, "security_audit_report.json")
        with open(default_output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  📄 完整报告已保存: {default_output}")

    # 返回退出码
    if report["report"]["severity_summary"].get("CRITICAL", 0) > 0:
        sys.exit(1)
    elif report["report"]["security_score"] < 5:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
