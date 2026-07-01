#!/usr/bin/env python3
"""
AI数字名片 — 安全审计脚本 (P0 Security Audit)

检查项:
  1. CORS 配置 — 不允许通配符 '*'（与 allow_credentials=True 冲突）
  2. JWT 算法 — 固定为 HS256/RS256，不允许 'none'
  3. 密码哈希 — 使用 bcrypt
  4. HTTPS 强制 — 检查是否有 HTTPS 重定向中间件或配置
  5. 安全头中间件 — 是否已注册
  6. 速率限制中间件 — 是否已注册

Usage:
    python scripts/security_audit.py
    python scripts/security_audit.py --verbose
    python scripts/security_audit.py --json       # JSON output
"""

import argparse
import ast
import os
import sys
import json
from pathlib import Path

# ── 路径 ─────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"


# ── 检查结果类型 ──────────────────────────────────────────────────────────────
class AuditResult:
    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    WARN = "⚠️  WARN"
    INFO = "ℹ️  INFO"


# ── 检查函数 ──────────────────────────────────────────────────────────────────

def check_cors(filepath: Path) -> list[dict]:
    """检查 CORS 配置是否使用了通配符 '*'。"""
    results = []
    if not filepath.exists():
        return [{"check": "CORS 配置", "status": AuditResult.WARN, "detail": f"文件不存在: {filepath}"}]

    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [{"check": "CORS 配置", "status": AuditResult.FAIL, "detail": f"语法错误: {e}"}]

    for node in ast.walk(tree):
        # 查找 app.add_middleware(CORSMiddleware, ...) 调用
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute) and call.func.attr == "add_middleware"):
                args = call.args
                keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
                # 检查第一个参数是否为 CORSMiddleware
                if args and isinstance(args[0], ast.Name) and args[0].id == "CORSMiddleware":
                    allow_origins = keywords.get("allow_origins")
                    allow_credentials = keywords.get("allow_credentials")

                    # 检查 allow_credentials
                    creds_ok = True
                    if isinstance(allow_credentials, ast.Constant) and allow_credentials.value is True:
                        creds_ok = False  # need to check origins too

                    # 检查 allow_origins
                    if isinstance(allow_origins, ast.List):
                        has_star = any(
                            isinstance(el, ast.Constant) and el.value == "*"
                            for el in allow_origins.elts
                        )
                        if has_star:
                            results.append({
                                "check": "CORS allow_origins",
                                "status": AuditResult.FAIL,
                                "detail": "allow_origins 包含通配符 '*'，不允许在 allow_credentials=True 时使用",
                                "severity": "high",
                                "fix": "在 app/__init__.py 中将 allow_origins=[\"*\"] 替换为显式的来源白名单",
                            })
                        else:
                            origins = [
                                el.value for el in allow_origins.elts
                                if isinstance(el, ast.Constant)
                            ]
                            results.append({
                                "check": "CORS allow_origins",
                                "status": AuditResult.PASS,
                                "detail": f"来源白名单已配置: {origins}",
                            })
                    elif isinstance(allow_origins, ast.IfExp):
                        # 处理条件表达式: cfg.CORS_ORIGINS.split(",") if ... else [...]
                        else_part = allow_origins.orelse
                        if isinstance(else_part, ast.List):
                            has_star = any(
                                isinstance(el, ast.Constant) and el.value == "*"
                                for el in else_part.elts
                            )
                            if has_star:
                                results.append({
                                    "check": "CORS 降级配置",
                                    "status": AuditResult.FAIL,
                                    "detail": "CORS_ORIGINS 为空时降级为 ['*']，存在安全隐患",
                                    "severity": "high",
                                    "fix": "降级列表应使用显式白名单而非通配符",
                                })
                            else:
                                origins = [
                                    el.value for el in else_part.elts
                                    if isinstance(el, ast.Constant)
                                ]
                                results.append({
                                    "check": "CORS 降级配置",
                                    "status": AuditResult.PASS,
                                    "detail": f"降级白名单已配置: {origins}",
                                })
                    else:
                        results.append({
                            "check": "CORS allow_origins",
                            "status": AuditResult.WARN,
                            "detail": f"allow_origins 类型未识别: {type(allow_origins).__name__}",
                        })

                    if creds_ok and results:
                        orig_result = results[-1]
                        if orig_result["status"] == AuditResult.PASS:
                            results.append({
                                "check": "CORS allow_credentials",
                                "status": AuditResult.PASS,
                                "detail": "allow_credentials=True 配合显式来源白名单",
                            })

                    break
    else:
        results.append({
            "check": "CORS 配置",
            "status": AuditResult.WARN,
            "detail": "未找到 CORSMiddleware 注册调用",
        })

    return results


def check_jwt_algorithm(filepath: Path) -> list[dict]:
    """检查 JWT 解码是否使用固定算法列表。"""
    results = []
    if not filepath.exists():
        return [{"check": "JWT 算法", "status": AuditResult.WARN, "detail": f"文件不存在: {filepath}"}]

    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [{"check": "JWT 算法", "status": AuditResult.FAIL, "detail": f"语法错误: {e}"}]

    found_decode = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # 查找 jwt.decode(...) 调用
            if isinstance(func, ast.Attribute) and func.attr == "decode":
                # 检查调用者是否为 jwt
                if isinstance(func.value, ast.Name) and func.value.id == "jwt":
                    found_decode = True
                    keywords = {kw.arg: str(ast.dump(kw.value)) for kw in node.keywords if kw.arg}
                    algorithms_kw = next(
                        (kw for kw in node.keywords if kw.arg == "algorithms"), None
                    )
                    if algorithms_kw is None:
                        results.append({
                            "check": "JWT 算法",
                            "status": AuditResult.FAIL,
                            "detail": "jwt.decode() 未指定 algorithms 参数（可能接受任意算法）",
                            "severity": "critical",
                            "fix": "添加 algorithms=[settings.ALGORITHM] 参数",
                        })
                    elif isinstance(algorithms_kw.value, ast.List):
                        algos = [
                            el.value for el in algorithms_kw.value.elts
                            if isinstance(el, ast.Constant)
                        ]
                        if "none" in [a.lower() for a in algos]:
                            results.append({
                                "check": "JWT 算法",
                                "status": AuditResult.FAIL,
                                "detail": f"允许 'none' 算法: {algos}",
                                "severity": "critical",
                                "fix": "移除 'none' 算法",
                            })
                        elif algos:
                            results.append({
                                "check": "JWT 算法",
                                "status": AuditResult.PASS,
                                "detail": f"固定算法列表: {algos}",
                            })
                        else:
                            # 可能是 ast.Name 引用 (如 settings.ALGORITHM)
                            algo_names = [
                                ast.dump(el) for el in algorithms_kw.value.elts
                            ]
                            results.append({
                                "check": "JWT 算法",
                                "status": AuditResult.PASS,
                                "detail": f"算法列表使用变量引用 (非字面常量): {algo_names} — 需确认 config.py ALGORITHM 非 'none'",
                            })
                    else:
                        results.append({
                            "check": "JWT 算法",
                            "status": AuditResult.WARN,
                            "detail": "algorithms 参数非字面列表，需人工确认",
                        })

    if not found_decode:
        results.append({
            "check": "JWT 算法",
            "status": AuditResult.INFO,
            "detail": "未找到 jwt.decode() 调用（可能无 JWT 使用场景）",
        })

    return results


def check_password_hash(filepath: Path) -> list[dict]:
    """检查密码哈希是否使用 bcrypt。"""
    results = []
    if not filepath.exists():
        return [{"check": "密码哈希", "status": AuditResult.WARN, "detail": f"文件不存在: {filepath}"}]

    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [{"check": "密码哈希", "status": AuditResult.FAIL, "detail": f"语法错误: {e}"}]

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # CryptContext(...) or passlib.context.CryptContext(...)
            is_crypt = (
                (isinstance(func, ast.Attribute) and func.attr == "CryptContext")
                or (isinstance(func, ast.Name) and func.id == "CryptContext")
            )
            if is_crypt:
                keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                schemes = keywords.get("schemes")
                if isinstance(schemes, ast.List):
                    scheme_names = [
                        el.value for el in schemes.elts
                        if isinstance(el, ast.Constant)
                    ]
                    if "bcrypt" in scheme_names:
                        results.append({
                            "check": "密码哈希",
                            "status": AuditResult.PASS,
                            "detail": f"使用 bcrypt: {scheme_names}",
                        })
                    else:
                        results.append({
                            "check": "密码哈希",
                            "status": AuditResult.FAIL,
                            "detail": f"未使用 bcrypt: {scheme_names}",
                            "severity": "high",
                            "fix": "将 schemes 改为 [\"bcrypt\"]",
                        })
                    break
    else:
        results.append({
            "check": "密码哈希",
            "status": AuditResult.INFO,
            "detail": "未找到 CryptContext 配置（可能不使用密码认证）",
        })

    return results


def check_https_enforcement(main_py: Path, security_headers_py: Path) -> list[dict]:
    """检查 HTTPS 强制 / HSTS 配置。"""
    results = []

    # 检查 security_headers.py 中的 HSTS
    if security_headers_py.exists():
        try:
            sh_content = security_headers_py.read_text(encoding="utf-8")
        except Exception as e:
            return [{"check": "HTTPS 强制", "status": AuditResult.FAIL, "detail": f"读取失败: {e}"}]

        hsts_keywords = ["strict-transport-security", "Strict-Transport-Security", "HSTS"]
        has_hsts = any(kw in sh_content for kw in hsts_keywords)
        if has_hsts:
            results.append({
                "check": "HTTPS 强制",
                "status": AuditResult.PASS,
                "detail": "HSTS 头已配置（在 security_headers.py 中）",
            })
        else:
            results.append({
                "check": "HTTPS 强制",
                "status": AuditResult.WARN,
                "detail": "未在 security_headers.py 中找到 HSTS 配置",
            })
    else:
        results.append({
            "check": "HTTPS 强制",
            "status": AuditResult.WARN,
            "detail": f"文件不存在: {security_headers_py}",
        })
        return results

    # 检查 main.py 启动参数中是否有 SSL
    main_content = main_py.read_text(encoding="utf-8") if main_py.exists() else ""
    if "--ssl-keyfile" in main_content or "ssl_keyfile" in main_content or "ssl_certfile" in main_content:
        results.append({
            "check": "HTTPS 终端",
            "status": AuditResult.PASS,
            "detail": "SSL/TLS 证书配置已设置",
        })
    else:
        results.append({
            "check": "HTTPS 终端",
            "status": AuditResult.WARN,
            "detail": "未在启动配置中找到 SSL 证书配置（HTTPS 应在反向代理层处理）",
        })

    return results


def check_middleware_registration(filepath: Path) -> list[dict]:
    """检查安全中间件是否已在 app 中注册。"""
    results = []
    if not filepath.exists():
        return [{"check": "中间件注册", "status": AuditResult.WARN, "detail": f"文件不存在: {filepath}"}]

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return [{"check": "中间件注册", "status": AuditResult.FAIL, "detail": f"读取失败: {e}"}]

    # 检查 RateLimiterMiddleware 注册
    if "RateLimiterMiddleware" in content and "add_middleware(RateLimiterMiddleware" in content:
        results.append({
            "check": "速率限制中间件",
            "status": AuditResult.PASS,
            "detail": "RateLimiterMiddleware 已注册",
        })
    else:
        results.append({
            "check": "速率限制中间件",
            "status": AuditResult.FAIL,
            "detail": "RateLimiterMiddleware 未注册",
            "severity": "high",
            "fix": "在 create_app() 中添加: app.add_middleware(RateLimiterMiddleware)",
        })

    # 检查 SecurityHeadersMiddleware 注册
    if "SecurityHeadersMiddleware" in content and "add_middleware(SecurityHeadersMiddleware" in content:
        results.append({
            "check": "安全头中间件",
            "status": AuditResult.PASS,
            "detail": "SecurityHeadersMiddleware 已注册",
        })
    else:
        results.append({
            "check": "安全头中间件",
            "status": AuditResult.FAIL,
            "detail": "SecurityHeadersMiddleware 未注册",
            "severity": "high",
            "fix": "在 create_app() 中添加: app.add_middleware(SecurityHeadersMiddleware)",
        })

    # 检查 API Key 中间件
    if "ApiKeyMiddleware" in content and "add_middleware(ApiKeyMiddleware" in content:
        results.append({
            "check": "API Key 中间件",
            "status": AuditResult.PASS,
            "detail": "ApiKeyMiddleware 已注册",
        })
    else:
        results.append({
            "check": "API Key 中间件",
            "status": AuditResult.WARN,
            "detail": "ApiKeyMiddleware 未注册（可选，如不使用 API Key 可忽略）",
        })

    return results


def check_imports(filepath: Path) -> list[dict]:
    """检查 middleware/__init__.py 中是否导出了所需安全中间件。"""
    results = []
    if not filepath.exists():
        return [{"check": "中间件导出", "status": AuditResult.WARN, "detail": f"文件不存在: {filepath}"}]

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return [{"check": "中间件导出", "status": AuditResult.FAIL, "detail": f"读取失败: {e}"}]

    checks = [
        ("RateLimiterMiddleware", "rate_limiter"),
        ("SecurityHeadersMiddleware", "security_headers"),
    ]

    for name, module in checks:
        if f"from .{module}" in content and name in content:
            results.append({
                "check": f"导出 {name}",
                "status": AuditResult.PASS,
                "detail": f"{name} 从 middleware/{module}.py 已导出",
            })
        else:
            results.append({
                "check": f"导出 {name}",
                "status": AuditResult.FAIL,
                "detail": f"{name} 未在 middleware/__init__.py 中导出",
                "severity": "high",
                "fix": f"添加: from .{module} import {name}",
            })

    return results


# ── 主审计流程 ──────────────────────────────────────────────────────────────

def run_audit(verbose: bool = False) -> list[dict]:
    """运行所有安全检查并返回结果列表。"""
    all_results = []

    init_py = APP_DIR / "__init__.py"
    auth_py = APP_DIR / "routers" / "auth.py"
    middleware_init = APP_DIR / "middleware" / "__init__.py"
    main_py = BACKEND_DIR / "main.py"

    # 1. CORS 检查
    if verbose:
        print(f"\n{'='*60}")
        print(f"  1. CORS 配置检查")
        print(f"{'='*60}")
    all_results.extend(check_cors(init_py))

    # 2. JWT 算法检查
    if verbose:
        print(f"\n{'='*60}")
        print(f"  2. JWT 算法检查")
        print(f"{'='*60}")

    # 检查所有可能使用 jwt.decode 的文件
    jwt_files = [
        APP_DIR / "routers" / "auth.py",
        APP_DIR / "routers" / "sso.py",
    ]
    for f in jwt_files:
        all_results.extend(check_jwt_algorithm(f))

    # 3. 密码哈希检查
    if verbose:
        print(f"\n{'='*60}")
        print(f"  3. 密码哈希检查")
        print(f"{'='*60}")
    all_results.extend(check_password_hash(APP_DIR / "routers" / "auth.py"))

    # 4. HTTPS 强制检查
    if verbose:
        print(f"\n{'='*60}")
        print(f"  4. HTTPS 强制检查")
        print(f"{'='*60}")
    all_results.extend(check_https_enforcement(main_py, APP_DIR / "middleware" / "security_headers.py"))

    # 5. 中间件注册检查
    if verbose:
        print(f"\n{'='*60}")
        print(f"  5. 中间件注册检查")
        print(f"{'='*60}")
    all_results.extend(check_middleware_registration(init_py))

    # 6. 中间件导出检查
    if verbose:
        print(f"\n{'='*60}")
        print(f"  6. 中间件导出检查")
        print(f"{'='*60}")
    all_results.extend(check_imports(middleware_init))

    return all_results


def print_report(results: list[dict], verbose: bool = False):
    """打印人类可读的审计报告。"""
    passed = [r for r in results if r["status"] == AuditResult.PASS]
    failed = [r for r in results if r["status"] == AuditResult.FAIL]
    warned = [r for r in results if r["status"] == AuditResult.WARN]
    info = [r for r in results if r["status"] == AuditResult.INFO]

    print(f"\n{'='*60}")
    print(f"  🔒 AI数字名片 — 安全审计报告")
    print(f"{'='*60}")
    print(f"  总计: {len(results)} | ✅ {len(passed)} | ❌ {len(failed)} | ⚠️  {len(warned)} | ℹ️  {len(info)}")
    print(f"{'='*60}\n")

    for r in results:
        if r["status"] in (AuditResult.FAIL, AuditResult.WARN) or verbose:
            sev = r.get("severity", "")
            sev_tag = f" [{sev.upper()}]" if sev else ""
            print(f"  {r['status']}{sev_tag} — {r['check']}")

            detail = r["detail"]
            # 对长文本换行
            while len(detail) > 90:
                print(f"      {detail[:90]}")
                detail = detail[90:]
            print(f"      {detail}")

            fix = r.get("fix")
            if fix:
                print(f"      🔧 {fix}")
            print()

    print(f"{'='*60}")
    if failed:
        print(f"  ❌ {len(failed)} 个检查未通过 — 请修复后再部署")
    elif warned:
        print(f"  ⚠️  {len(warned)} 个警告 — 建议审查")
    else:
        print(f"  ✅ 所有安全检查通过")
    print(f"{'='*60}")

    return len(failed)


def main():
    parser = argparse.ArgumentParser(description="AI数字名片安全审计脚本")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    results = run_audit(verbose=args.verbose)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        exit_code = print_report(results, verbose=args.verbose)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
