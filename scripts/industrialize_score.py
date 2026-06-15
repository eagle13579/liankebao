#!/usr/bin/env python3
"""
链客宝AI 工业化全景扫描与评分工具
===============================
自动扫描项目代码并输出10维度工业化评分。
用法: python scripts/industrialize_score.py

评分维度:
  1. 架构成熟度 (Architecture)
  2. 代码质量 (Code Quality)
  3. 安全合规 (Security)
  4. AI能力 (AI Capability)
  5. 部署运维 (DevOps)
  6. 数据架构 (Data Architecture)
  7. 前端工程 (Frontend)
  8. 文档完备 (Documentation)
  9. 团队协作 (Collaboration)
  10. 商业成熟度 (Business Maturity)
"""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))


def sh(cmd: str, capture: bool = True) -> str:
    """Run shell command and return output."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True, timeout=30
        )
        return r.stdout.strip() + ("\n" + r.stderr.strip() if r.stderr else "")
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"


def _find_count(pattern: str, path: str = ".", exclude_patterns: list = None) -> int:
    """Cross-platform file counting excluding venv/node_modules etc."""
    if exclude_patterns is None:
        exclude_patterns = [
            "venv",
            "venv_new",
            "node_modules",
            "dist",
            "dist-ssr",
            ".git",
            ".ruff_cache",
            "__pycache__",
        ]
    cmd = f'find "{path}" -type f -name "{pattern}"'
    for ep in exclude_patterns:
        cmd += f' -not -path "*/{ep}/*"'
    cmd += " | wc -l"
    result = sh(cmd)
    try:
        return int(result.strip().split()[0])
    except (ValueError, IndexError):
        return 0


def scan_file_counts() -> dict:
    """Count project files excluding venv/node_modules/dist."""
    return {
        "py_files": _find_count("*.py"),
        "ts_files": _find_count("*.ts") + _find_count("*.tsx"),
        "css_files": _find_count("*.css"),
        "test_files_py": int(
            sh("find backend/tests -type f -name '*.py' | wc -l") or 0
        ),
        "test_files_ts": int(sh("find src/__tests__ -type f | wc -l") or 0),
    }


def scan_loc() -> dict:
    """Count lines of code excluding generated/vendor code."""
    exclude_dirs = [
        "venv",
        "venv_new",
        "node_modules",
        "dist",
        "dist-ssr",
        ".git",
        ".ruff_cache",
        "__pycache__",
    ]
    py_loc = 0
    for f in Path(".").rglob("*.py"):
        skip = False
        for ed in exclude_dirs:
            if ed in str(f):
                skip = True
                break
        if not skip:
            try:
                py_loc += len(
                    f.read_text(encoding="utf-8", errors="ignore").splitlines()
                )
            except Exception:
                pass
    ts_loc = 0
    for ext in ["*.ts", "*.tsx", "*.jsx"]:
        for f in Path("src").rglob(ext):
            try:
                ts_loc += len(
                    f.read_text(encoding="utf-8", errors="ignore").splitlines()
                )
            except Exception:
                pass
    return {"py_loc": py_loc, "ts_loc": ts_loc}


def scan_api_endpoints() -> list:
    """Count API endpoints."""
    counts = {}
    for rf in sorted(Path("backend/app/routers").glob("*.py")):
        if rf.name == "__init__.py":
            continue
        text = rf.read_text(encoding="utf-8")
        n = sum(
            1
            for line in text.splitlines()
            if any(
                f".{method}(" in line
                for method in ["get", "post", "put", "delete", "patch"]
            )
        )
        if n > 0:
            counts[rf.stem] = n
    return counts


def scan_security() -> dict:
    """Security scan results."""
    issues = {
        "env_perms": sh("stat -c '%a' .env 2>/dev/null").strip(),
        "env_in_gitignore": ".env" in sh("grep -E '^\\.env$' .gitignore 2>/dev/null"),
        "csp_configured": "Content-Security-Policy"
        in sh("grep -rl 'Content-Security-Policy' backend/app/ 2>/dev/null"),
        "rate_limiting": Path("backend/app/middleware/rate_limit.py").exists(),
        "rbac": Path("backend/app/rbac.py").exists(),
        "sentry": "sentry_sdk"
        in sh("grep -r 'sentry_sdk' backend/app/sentry_config.py 2>/dev/null"),
    }
    return issues


def scan_test_coverage() -> float:
    """Get test coverage from pytest-cov if available, otherwise estimate."""
    if Path("backend/.coverage").exists():
        out = sh("cd backend && python -m coverage report --format=total 2>/dev/null")
        try:
            return float(out.strip().replace("%", ""))
        except ValueError:
            pass
    # Estimate from test vs source LOC
    py_loc = scan_loc()["py_loc"]
    test_loc = sum(
        p.stat().st_size for p in Path("backend/tests").rglob("*.py") if p.is_file()
    )
    # Rough heuristic: assume each source file has ~20% test coverage by LOC ratio
    src_loc = sum(
        p.stat().st_size for p in Path("backend/app").rglob("*.py") if p.is_file()
    )
    if src_loc == 0:
        return 0.0
    return min(round(test_loc / src_loc * 100, 1), 100.0)


def score_architecture(endpoints: dict, has_gateway: bool, has_alembic: bool) -> dict:
    """Score dimension 1: Architecture Maturity."""
    n_routers = len(endpoints)
    n_endpoints = sum(endpoints.values())
    score = 60  # baseline

    # + for good structure
    if n_routers >= 15:
        score += 5
    if n_endpoints >= 200:
        score += 5
    if has_gateway:
        score += 3
    if has_alembic:
        score += 3
    if Path("backend/app/services").exists():
        score += 2
    if Path("backend/app/middleware").exists():
        score += 2

    return {
        "score": min(score, 100),
        "routers": n_routers,
        "endpoints": n_endpoints,
        "has_gateway": has_gateway,
        "has_migrations": has_alembic,
    }


def score_code_quality(
    n_tests: int, coverage: float, has_lint: bool, has_precommit: bool
) -> dict:
    """Score dimension 2: Code Quality."""
    score = 55
    # Test quantity
    if n_tests >= 30:
        score += 5
    if n_tests >= 50:
        score += 5
    # Coverage
    if coverage >= 20:
        score += 3
    if coverage >= 35:
        score += 3
    if coverage >= 50:
        score += 4
    if has_lint:
        score += 3
    if has_precommit:
        score += 2

    return {
        "score": min(score, 100),
        "test_files": n_tests,
        "coverage_pct": coverage,
        "has_linter": has_lint,
        "has_precommit": has_precommit,
    }


def score_security(sec: dict) -> dict:
    """Score dimension 3: Security."""
    score = 50
    checks_passed = 0
    total_checks = 6

    if sec["env_in_gitignore"]:
        score += 5
        checks_passed += 1
    if sec["csp_configured"]:
        score += 5
        checks_passed += 1
    if sec["rate_limiting"]:
        score += 5
        checks_passed += 1
    if sec["rbac"]:
        score += 5
        checks_passed += 1
    if sec["sentry"]:
        score += 3
        checks_passed += 1
    if Path("backend/app/security_hardening.py").exists():
        score += 7
        checks_passed += 1

    # Check security audit report
    if Path("security_audit_report.json").exists():
        score += 5

    return {
        "score": min(score, 100),
        "checks_passed": f"{checks_passed}/{total_checks}",
        "details": sec,
    }


def score_ai() -> dict:
    """Score dimension 4: AI Capability."""
    score = 40
    details = []

    if Path("backend/app/business_card_ai.py").exists():
        score += 10
        details.append("business_card_ai")
    if Path("backend/matching_engine.py").exists():
        score += 10
        details.append("matching_engine")
    if Path("backend/app/vector_search.py").exists():
        score += 10
        details.append("vector_search")
    if Path("backend/app/services/llm_service.py").exists():
        score += 8
        details.append("llm_service")
    if Path("backend/app/enterprise_crawler.py").exists():
        score += 5
        details.append("enterprise_crawler")
    if Path("backend/app/services/enrichment_providers.py").exists():
        score += 5
        details.append("enrichment_providers")
    if Path("backend/app/search_index.py").exists():
        score += 5
        details.append("search_index")
    if Path("backend/llm_cost_controller.py").exists():
        score += 2
        details.append("llm_cost_controller")

    return {
        "score": min(score, 100),
        "modules_found": details,
        "n_modules": len(details),
    }


def score_devops() -> dict:
    """Score dimension 5: DevOps/Deployment."""
    score = 50
    items = []

    if Path("docker-compose.yml").exists():
        score += 5
        items.append("docker-compose")
    if Path("Dockerfile").exists():
        score += 5
        items.append("Dockerfile")
    if Path(".github/workflows/ci.yml").exists():
        score += 5
        items.append("ci_workflow")
    if Path(".github/workflows/deploy.yml").exists():
        score += 5
        items.append("deploy_workflow")
    if Path("deploy/").exists() and list(Path("deploy/").iterdir()):
        score += 5
        items.append("deploy_scripts")
    if Path("Makefile").exists():
        score += 3
        items.append("Makefile")
    if Path("backend/app/observability.py").exists():
        score += 3
        items.append("observability")
    if Path("backend/app/telemetry.py").exists():
        score += 3
        items.append("telemetry")
    if Path("backend/health_dashboard.py").exists():
        score += 3
        items.append("health_dashboard")
    if Path("scripts/security-check.sh").exists():
        score += 3
        items.append("security_check")

    return {
        "score": min(score, 100),
        "items_found": items,
        "n_items": len(items),
    }


def score_data_architecture() -> dict:
    """Score dimension 6: Data Architecture."""
    score = 40
    items = []

    if Path("backend/app/database.py").exists():
        score += 5
        items.append("database_module")
    if Path("backend/app/database_postgres.py").exists():
        score += 5
        items.append("pg_support")
    if Path("backend/alembic/").exists() and list(
        Path("backend/alembic/versions/").iterdir()
    ):
        score += 8
        items.append("alembic_migrations")
    if Path("backend/app/models.py").exists():
        score += 5
        items.append("orm_models")
    if Path("backend/app/optimistic_lock.py").exists():
        score += 5
        items.append("optimistic_lock")
    if Path("backend/reconciliation.py").exists():
        score += 5
        items.append("reconciliation")
    if Path("backend/app/tenant.py").exists():
        score += 5
        items.append("multi_tenant")
    if Path("backend/app/tenant_middleware.py").exists():
        score += 4
        items.append("tenant_middleware")

    # Check for soft delete
    grep_out = sh(
        "grep -rn is_deleted backend/app/models.py 2>/dev/null; grep -rn deleted_at backend/app/models.py 2>/dev/null"
    )
    if grep_out.strip():
        score += 3
        items.append("soft_delete")

    return {
        "score": min(score, 100),
        "items_found": items,
        "n_items": len(items),
    }


def score_frontend() -> dict:
    """Score dimension 7: Frontend Engineering."""
    score = 50
    items = []

    if Path("vite.config.ts").exists():
        score += 5
        items.append("vite")
    if Path("tsconfig.json").exists():
        score += 5
        items.append("typescript")
    if Path("src/__tests__/").exists() and list(Path("src/__tests__/").iterdir()):
        score += 8
        items.append("frontend_tests")
    if Path("src/api/client.ts").exists():
        score += 5
        items.append("api_client")
    if Path("src/components/").exists():
        score += 5
        items.append("components")
    if Path("server/ssr.ts").exists():
        score += 5
        items.append("ssr")
    if Path("src/pwa.tsx").exists():
        score += 3
        items.append("pwa")
    if Path("src/i18n/").exists():
        score += 3
        items.append("i18n")
    if Path("src/main.tsx").exists():
        score += 3
        items.append("main_tsx")
    if Path("tailwind.config.js").exists() or "tailwindcss" in sh(
        "grep -o 'tailwindcss' package.json 2>/dev/null"
    ):
        score += 3
        items.append("tailwind")

    return {
        "score": min(score, 100),
        "items_found": items,
        "n_items": len(items),
    }


def score_documentation() -> dict:
    """Score dimension 8: Documentation."""
    score = 50
    items = []

    docs = [
        "ARCHITECTURE.md",
        "AI_MODULE_ARCHITECTURE.md",
        "L5_API_CONTRACT.md",
        "DEVELOPMENT_BEST_PRACTICE.md",
        "README.md",
        "README-小程序.md",
        "PRICING.md",
        "GO_TO_MARKET.md",
        "GITHUB_SECRETS_SOP.md",
        "docker-compose.yml",
        "security_audit_report.json",
    ]

    for d in docs:
        if Path(d).exists():
            score += 3
            items.append(d)

    if Path("docs/").exists():
        score += 3
        items.append("docs_dir")
    if (
        Path("backend/app/main.py").exists()
        and "docs_url" in Path("backend/app/main.py").read_text()
    ):
        score += 5
        items.append("openapi_docs")
    if Path("backend/app/schemas.py").exists():
        score += 3
        items.append("pydantic_schemas")

    return {
        "score": min(score, 100),
        "items_found": items,
        "n_items": len(items),
    }


def score_collaboration() -> dict:
    """Score dimension 9: Team Collaboration."""
    score = 50
    items = []

    if Path(".pre-commit-config.yaml").exists():
        score += 5
        items.append("pre_commit")
    if Path(".github/workflows/ci.yml").exists():
        score += 5
        items.append("ci")
    if Path(".github/workflows/lint.yml").exists():
        score += 3
        items.append("lint_workflow")
    if Path("Makefile").exists():
        score += 5
        items.append("makefile")
    if Path(".flake8").exists():
        score += 3
        items.append("flake8")
    if Path(".gitignore").exists():
        score += 3
        items.append("gitignore")
    if Path("pyproject.toml").exists():
        score += 3
        items.append("pyproject")
    if Path("CONTRIBUTING.md").exists():
        score += 3
        items.append("contributing")
    if Path("CODE_OF_CONDUCT.md").exists():
        score += 2
        items.append("code_of_conduct")
    if Path("LICENSE").exists():
        score += 3
        items.append("license")
    if Path("CHANGELOG.md").exists():
        score += 5
        items.append("changelog")

    return {
        "score": min(score, 100),
        "items_found": items,
        "n_items": len(items),
    }


def score_business() -> dict:
    """Score dimension 10: Business Maturity."""
    score = 30
    items = []

    # Pricing & market docs
    if Path("PRICING.md").exists():
        score += 5
        items.append("pricing_doc")
    if Path("GO_TO_MARKET.md").exists():
        score += 5
        items.append("gtm_doc")
    if Path("payment_sdk/").exists():
        score += 5
        items.append("payment_sdk")

    # Payment config
    env_text = Path(".env").read_text() if Path(".env").exists() else ""
    if "WXPAY_MCHID" in env_text:
        score += 5
        items.append("wxpay_config")
    if "WECHAT_PAYMENT_PLAN.md" in sh("ls *.md 2>/dev/null"):
        score += 5
        items.append("payment_plan")

    # Check for wechat mini program
    if Path("liankebao-weapp/").exists() or Path("liankebao-miniapp/").exists():
        score += 5
        items.append("miniapp")

    # Domain/deployment
    if Path("docker-compose.yml").exists():
        score += 3
        items.append("docker_deploy")
    if Path("deploy/").exists():
        score += 3
        items.append("deploy_dir")

    return {
        "score": min(score, 100),
        "items_found": items,
        "n_items": len(items),
    }


def main():
    print("=" * 60)
    print("  链客宝AI 工业化全景扫描与评分 v2.0")
    print("=" * 60)
    print()

    # Phase 1: Scan
    print("📡 Phase 1: 全景扫描...")
    files = scan_file_counts()
    loc = scan_loc()
    endpoints = scan_api_endpoints()
    security = scan_security()
    coverage = scan_test_coverage()

    print(f"   Python 文件: {files['py_files']}")
    print(f"   TypeScript 文件: {files['ts_files']}")
    print(f"   Python LOC: {loc['py_loc']}")
    print(f"   TypeScript LOC: {loc['ts_loc']}")
    print(f"   API 端点: {sum(endpoints.values())} (分布在 {len(endpoints)} 个路由)")
    print(
        f"   测试文件: {files['test_files_py']} pytest + {files['test_files_ts']} vitest"
    )
    print(f"   估算覆盖率: {coverage}%")
    print()

    # Phase 2: Score
    print("📊 Phase 2: 10维度评分...")
    results = {
        "① 架构成熟度": score_architecture(
            endpoints,
            Path("gateway.py").exists(),
            Path("backend/alembic/versions").exists(),
        ),
        "② 代码质量": score_code_quality(
            files["test_files_py"] + files["test_files_ts"],
            coverage,
            Path(".flake8").exists(),
            Path(".pre-commit-config.yaml").exists(),
        ),
        "③ 安全合规": score_security(security),
        "④ AI能力": score_ai(),
        "⑤ 部署运维": score_devops(),
        "⑥ 数据架构": score_data_architecture(),
        "⑦ 前端工程": score_frontend(),
        "⑧ 文档完备": score_documentation(),
        "⑨ 团队协作": score_collaboration(),
        "⑩ 商业成熟度": score_business(),
    }

    # Phase 3: Report
    total = 0
    print()
    print(f"{'维度':<20} {'评分':>6}  {'说明'}")
    print("-" * 60)
    for dim, data in results.items():
        s = data["score"]
        total += s
        print(f"  {dim:<18} {s:>3}/100  ({data.get('n_items', 0)} items)")

    avg = round(total / len(results), 1)
    overall = round(avg / 10, 1)
    print("-" * 60)
    print(f"  {'总分':<18} {total:>3}/1000")
    print(f"  {'平均分':<18} {avg:>3}/100")
    print(f"  {'工业化评分':<18} {overall}/10")

    # Phase 4: Gap Analysis
    print()
    print("📋 Phase 3: P0 缺口识别")
    gaps = [(dim, data) for dim, data in results.items() if data["score"] < 70]
    gaps.sort(key=lambda x: x[1]["score"])
    for dim, data in gaps[:5]:
        print(f"   ⚠️  {dim}: {data['score']}/100 — 需修复")

    # Save report
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "scores": {dim: data["score"] for dim, data in results.items()},
        "overall": overall,
        "average": avg,
        "total": total,
        "files": files,
        "loc": loc,
        "endpoints": endpoints,
        "gaps": [dim for dim, _ in gaps],
    }
    report_path = "industrialization_report.json"
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n📝 报告已保存: {report_path}")
    print()

    return overall


if __name__ == "__main__":
    sys.exit(0 if main() >= 7.0 else 1)
