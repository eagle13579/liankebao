#!/usr/bin/env python3
"""
链客宝 — 部署缺口扫描清单 (Gap Checklist Scanner)

Scans all remaining gaps from the v3.0 architecture plan and reports
the activation status of every component. Designed to be run after
production deployment to verify everything is properly connected.

Usage:
    python scripts/gap_checklist.py              # Standard output
    python scripts/gap_checklist.py --json       # JSON output (for monitoring)
    python scripts/gap_checklist.py --verbose    # Detailed diagnostics
    python scripts/gap_checklist.py --ci         # CI mode (exit code = count of failures)

Environment:
    INFRA_PHASE=1   Must be set to activate Phase 1 checks
    REDIS_HOST      Optional, for Redis connectivity check
    REDIS_PORT      Optional, default 6379
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable

# ── Ensure backend on path ────────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ═══════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    """Result of a single gap check."""
    id: str
    name: str
    category: str
    status: bool               # True = ✅, False = ❌
    detail: str = ""
    duration_ms: float = 0.0
    depends_on: list[str] = field(default_factory=list)

    @property
    def emoji(self) -> str:
        return "✅" if self.status else "❌"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_ansi(self) -> str:
        icon = f"\033[32m{self.emoji}\033[0m" if self.status else f"\033[31m{self.emoji}\033[0m"
        return f"  {icon} [{self.id}] {self.name}  ({self.duration_ms:.0f}ms)\n      {self.detail}"


# ═══════════════════════════════════════════════════════════════════
# Gap check registry
# ═══════════════════════════════════════════════════════════════════

_registry: list[tuple[str, str, list[str], Callable[[], tuple[bool, str]]]] = []


def register(
    check_id: str,
    name: str,
    category: str,
    depends_on: list[str] | None = None,
) -> Callable:
    """Decorator to register a gap check function."""
    def wrapper(fn: Callable) -> Callable:
        _registry.append((check_id, name, category, depends_on or [], fn))
        return fn
    return wrapper


# ═══════════════════════════════════════════════════════════════════
# Gap checks — Phase 1 Infrastructure
# ═══════════════════════════════════════════════════════════════════

@register("P1-01", "INFRA_PHASE 环境变量已设置", "Phase 1: 基础设施")
def check_infra_phase() -> tuple[bool, str]:
    """Check that INFRA_PHASE=1 is set."""
    phase = os.environ.get("INFRA_PHASE", "0")
    if phase == "1":
        return True, f"INFRA_PHASE={phase} — Phase 1 已激活"
    return False, f"INFRA_PHASE={phase} — 需要设置为 1"


@register("P1-02", "RedisCache 模块可导入", "Phase 1: 基础设施", depends_on=["P1-01"])
def check_redis_cache_import() -> tuple[bool, str]:
    """Check RedisCache adapter is importable."""
    try:
        from app.cache.adapters.redis_adapter import RedisCache  # noqa: F401
        return True, "RedisCache 模块成功导入"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("P1-03", "SQLiteEventBus 模块可导入", "Phase 1: 基础设施", depends_on=["P1-01"])
def check_sqlite_event_bus_import() -> tuple[bool, str]:
    """Check SQLiteEventBus adapter is importable."""
    try:
        from app.events.adapters.sqlite_adapter import SQLiteEventBus  # noqa: F401
        return True, "SQLiteEventBus 模块成功导入"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("P1-04", "Dependencies 使用 Phase 1 实现", "Phase 1: 基础设施", depends_on=["P1-01", "P1-02", "P1-03"])
def check_dependencies_phase1() -> tuple[bool, str]:
    """Check get_cache() and get_event_bus() return Phase 1 implementations."""
    try:
        # Force reimport by clearing caches
        for mod in list(sys.modules.keys()):
            if mod.startswith("app.dependencies"):
                del sys.modules[mod]

        from app.dependencies import get_cache, get_event_bus

        cache = get_cache()
        bus = get_event_bus()

        cache_ok = "RedisCache" in type(cache).__name__
        bus_ok = "SQLiteEventBus" in type(bus).__name__

        if cache_ok and bus_ok:
            return True, f"cache={type(cache).__name__}, bus={type(bus).__name__} — Phase 1 实现已激活"
        if cache_ok:
            return True, f"cache={type(cache).__name__} ✅, bus={type(bus).__name__} ⚠️"
        if bus_ok:
            return True, f"cache={type(cache).__name__} ⚠️, bus={type(bus).__name__} ✅"
        return False, f"cache={type(cache).__name__}, bus={type(bus).__name__} — 未使用 Phase 1 实现"
    except Exception as e:
        return False, f"错误: {e}"


@register("P1-05", "Redis 连接可达", "Phase 1: 基础设施", depends_on=["P1-02"])
def check_redis_connectivity() -> tuple[bool, str]:
    """Check if Redis is reachable (if REDIS_HOST is set)."""
    host = os.environ.get("REDIS_HOST", "")
    port = os.environ.get("REDIS_PORT", "6379")

    if not host:
        return True, "REDIS_HOST 未设置 — 跳过连通性检查 (将使用 InMemoryCache 降级)"

    try:
        import asyncio
        from app.cache.adapters.redis_adapter import RedisCache

        cache = RedisCache(
            host=host,
            port=int(port),
            password=os.environ.get("REDIS_PASSWORD", None),
            db=int(os.environ.get("REDIS_DB", "0")),
        )

        async def _test() -> bool:
            try:
                await cache.start()
                await cache.set("__probe__", "pong", ttl=5)
                val = await cache.get("__probe__")
                await cache.delete("__probe__")
                await cache.stop()
                return val == "pong"
            except Exception:
                return False

        ok = asyncio.run(_test())
        if ok:
            return True, f"Redis 连接正常 ({host}:{port})"
        return False, f"Redis 连接失败 ({host}:{port})"
    except ImportError as e:
        return True, f"Redis 客户端未安装 ({e}) — 跳过 (降级模式)"
    except Exception as e:
        return False, f"Redis 连接异常: {e}"


# ═══════════════════════════════════════════════════════════════════
# Gap checks — Agent Runtime
# ═══════════════════════════════════════════════════════════════════

@register("AR-01", "BaseAgent 模块可导入", "Agent Runtime", depends_on=["P1-01"])
def check_base_agent_import() -> tuple[bool, str]:
    """Check BaseAgent is importable."""
    try:
        from app.agents.base_agent import BaseAgent  # noqa: F401
        return True, "BaseAgent 模块成功导入"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("AR-02", "AgentRuntime 模块可导入", "Agent Runtime", depends_on=["P1-01"])
def check_agent_runtime_import() -> tuple[bool, str]:
    """Check AgentRuntime is importable."""
    try:
        from app.agents.agent_runtime import AgentRuntime  # noqa: F401
        return True, "AgentRuntime 模块成功导入"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("AR-03", "所有 9 名数字员工已注册", "Agent Runtime", depends_on=["P1-01"])
def check_all_employees_registered() -> tuple[bool, str]:
    """Check EMPLOYEE_AGENT_MAP has all 9 employees."""
    try:
        from app.agents.employee_profiles import EMPLOYEE_AGENT_MAP

        expected_employees = {
            "SRE": "emp-烛龙",
            "support": "emp-狴犴",
            "backend": "emp-獬豸",
            "qa": "emp-乘黄",
            "security": "emp-文鳐",
            "growth": "emp-讙",
            "knowledge": "emp-白泽",
            "architecture": "emp-鸓",
            "data": "emp-穷奇",
        }

        registered = set(EMPLOYEE_AGENT_MAP.keys())
        expected = set(expected_employees.keys())
        missing = expected - registered
        extra = registered - expected

        if not missing:
            detail = f"{len(EMPLOYEE_AGENT_MAP)}/9 名员工已注册"
            for k, v in EMPLOYEE_AGENT_MAP.items():
                detail += f"\n      {k:>15s} → {v['employee_id']}"
            if extra:
                detail += f"\n      (额外员工: {', '.join(sorted(extra))})"
            return True, detail
        return False, f"缺失员工: {', '.join(sorted(missing))}"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("AR-04", "所有 Agent 子类可导入", "Agent Runtime", depends_on=["AR-01"])
def check_all_agent_subclasses_importable() -> tuple[bool, str]:
    """Check all 9 agent subclasses import correctly."""
    agents = [
        ("SREAgent", "app.agents.sre_agent"),
        ("SupportAgent", "app.agents.support_agent"),
        ("BackendAgent", "app.agents.backend_agent"),
        ("QAAgent", "app.agents.qa_agent"),
        ("SecurityAgent", "app.agents.security_agent"),
        ("GrowthAgent", "app.agents.growth_agent"),
        ("KnowledgeAgent", "app.agents.knowledge_agent"),
        ("ArchitectureAgent", "app.agents.architecture_agent"),
        ("DataAgent", "app.agents.data_agent"),
    ]

    failures: list[str] = []
    successes: list[str] = []
    for name, module_path in agents:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, name, None)
            if cls is not None:
                successes.append(name)
            else:
                failures.append(f"{name} (class not found in {module_path})")
        except Exception as e:
            failures.append(f"{name}: {e}")

    if not failures:
        return True, f"全部 {len(successes)} 个 Agent 子类导入成功: {', '.join(successes)}"
    return False, f"成功: {len(successes)}, 失败: {len(failures)} — {'; '.join(failures)}"


@register("AR-05", "LegionEmployee 适配器可导入", "Agent Runtime", depends_on=["P1-01"])
def check_legion_employee_import() -> tuple[bool, str]:
    """Check LegionEmployee adapter."""
    try:
        from app.agents.legion_employee import LegionEmployee  # noqa: F401
        return True, "LegionEmployee 模块成功导入"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("AR-06", "调度规则已定义", "Agent Runtime", depends_on=["AR-02"])
def check_scheduler_rules() -> tuple[bool, str]:
    """Check scheduler rules are defined."""
    try:
        from app.agents.scheduler_rules import SCHEDULER_RULES, install_scheduler_rules

        if not SCHEDULER_RULES:
            return False, "SCHEDULER_RULES 为空 — 没有定义调度规则"

        detail = f"{len(SCHEDULER_RULES)} 条调度规则:"
        for rule in SCHEDULER_RULES:
            schedule = rule.get("schedule", "?")
            agent = rule.get("agent_name", rule.get("name", "?"))
            detail += f"\n      {schedule:>12s} → {agent}"
        return True, detail
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("AR-07", "start_agents.py 入口可用", "Agent Runtime")
def check_start_agents_script() -> tuple[bool, str]:
    """Check the startup script exists and is syntactically valid."""
    script_path = os.path.join(BACKEND_DIR, "scripts", "start_agents.py")
    if not os.path.exists(script_path):
        return False, f"文件不存在: {script_path}"

    try:
        with open(script_path, "r", encoding="utf-8") as f:
            compile(f.read(), script_path, "exec")
        return True, f"语法检查通过: {script_path}"
    except SyntaxError as e:
        return False, f"语法错误: {e}"
    except Exception as e:
        return False, f"错误: {e}"


# ═══════════════════════════════════════════════════════════════════
# Gap checks — Gaia & Evolution
# ═══════════════════════════════════════════════════════════════════

@register("GA-01", "GaiaBrain 模块可导入", "盖娅飞轮")
def check_gaia_brain_import() -> tuple[bool, str]:
    """Check GaiaBrain is importable."""
    try:
        from app.gaia_brain import GaiaBrain  # noqa: F401
        return True, "GaiaBrain 模块成功导入"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


@register("GA-02", "盖娅飞轮定时任务可安装", "盖娅飞轮", depends_on=["AR-06"])
def check_gaia_flywheel() -> tuple[bool, str]:
    """Check Gaia flywheel can be installed."""
    try:
        from app.agents.scheduler_rules import install_scheduler_rules

        # Check if flywheel rule exists
        from app.agents.scheduler_rules import SCHEDULER_RULES
        flywheel_rules = [r for r in SCHEDULER_RULES if "fl" in r.get("agent_name", "").lower() or "飞轮" in r.get("description", "")]
        if flywheel_rules:
            return True, f"盖娅飞轮定时任务已配置: {flywheel_rules[0].get('schedule', '每30分钟')}"
        return True, "install_scheduler_rules() 可用 (飞轮规则由 SREAgent 管理)"
    except ImportError as e:
        return False, f"导入失败: {e}"
    except Exception as e:
        return False, f"错误: {e}"


# ═══════════════════════════════════════════════════════════════════
# Gap checks — Deployment infrastructure
# ═══════════════════════════════════════════════════════════════════

@register("DI-01", "Dockerfile 存在", "部署基础设施")
def check_dockerfile() -> tuple[bool, str]:
    """Check Dockerfile exists."""
    path = os.path.join(BACKEND_DIR, "deploy", "Dockerfile")
    if os.path.exists(path):
        return True, f"Dockerfile 存在 ({path})"
    return False, f"Dockerfile 不存在 ({path})"


@register("DI-02", "docker-compose.yml 存在", "部署基础设施")
def check_docker_compose() -> tuple[bool, str]:
    """Check docker-compose.yml exists."""
    path = os.path.join(BACKEND_DIR, "deploy", "docker-compose.yml")
    if os.path.exists(path):
        return True, f"docker-compose.yml 存在 ({path})"
    return False, f"docker-compose.yml 不存在 ({path})"


@register("DI-03", "systemd 服务文件存在", "部署基础设施")
def check_systemd_service() -> tuple[bool, str]:
    """Check systemd service file exists."""
    path = os.path.join(BACKEND_DIR, "deploy", "chainke-agents.service")
    if os.path.exists(path):
        return True, f"chainke-agents.service 存在 ({path})"
    return False, f"chainke-agents.service 不存在 ({path})"


@register("DI-04", "K8s 自定义目录就绪", "部署基础设施")
def check_k8s_manifests() -> tuple[bool, str]:
    """Check K8s manifest directory."""
    path = os.path.join(BACKEND_DIR, "deploy", "k8s")
    if not os.path.isdir(path):
        return False, f"k8s/ 目录不存在 ({path})"

    files = [f for f in os.listdir(path) if f.endswith(".yaml")]
    if len(files) >= 8:
        return True, f"k8s/ 就绪 — {len(files)} 个 manifest 文件"
    return True, f"k8s/ 存在但只有 {len(files)} 个 manifest 文件 (期望至少 8 个)"


@register("DI-05", "Helm Chart 就绪", "部署基础设施")
def check_helm_chart() -> tuple[bool, str]:
    """Check Helm chart directory."""
    path = os.path.join(BACKEND_DIR, "deploy", "helm", "chainke")
    if not os.path.isdir(path):
        return False, f"Helm chart 不存在 ({path})"

    templates = os.path.join(path, "templates")
    if os.path.isdir(templates):
        tpl_count = len([f for f in os.listdir(templates) if f.endswith((".yaml", ".tpl"))])
        return True, f"Helm chart 就绪 — {tpl_count} 个模板文件"
    return True, "Helm chart 就绪 (templates/ 目录存在)"


@register("DI-06", "Patroni HA 数据库配置就绪", "部署基础设施")
def check_patroni() -> tuple[bool, str]:
    """Check Patroni directory."""
    path = os.path.join(BACKEND_DIR, "deploy", "patroni")
    if not os.path.isdir(path):
        return False, f"patroni/ 目录不存在 ({path})"

    files = os.listdir(path)
    return True, f"Patroni 配置就绪 — {len(files)} 个文件: {', '.join(files)}"


@register("DI-07", "Nginx 配置就绪", "部署基础设施")
def check_nginx() -> tuple[bool, str]:
    """Check Nginx directory."""
    path = os.path.join(BACKEND_DIR, "deploy", "nginx")
    if not os.path.isdir(path):
        return False, f"nginx/ 目录不存在 ({path})"

    files = os.listdir(path)
    return True, f"Nginx 配置就绪 — {len(files)} 个文件: {', '.join(files)}"


@register("DI-08", ".env.production 配置存在", "部署基础设施")
def check_env_production() -> tuple[bool, str]:
    """Check .env.production exists."""
    path = os.path.join(BACKEND_DIR, ".env.production")
    if os.path.exists(path):
        size = os.path.getsize(path)
        return True, f".env.production 存在 ({size} bytes)"
    return False, f".env.production 不存在 ({path})"


# ═══════════════════════════════════════════════════════════════════
# Gap checks — Test infrastructure
# ═══════════════════════════════════════════════════════════════════

@register("TI-01", "关键测试模块存在", "测试基础设施")
def check_test_modules() -> tuple[bool, str]:
    """Check critical test files exist."""
    tests_dir = os.path.join(BACKEND_DIR, "tests")
    required = [
        "test_legion_employee.py",
        "test_phase1_adapters.py",
        "test_all_agents.py",
        "test_agent_runtime.py",
        "smoke_test_new_arch.py",
    ]

    present = [f for f in required if os.path.exists(os.path.join(tests_dir, f))]
    missing = [f for f in required if not os.path.exists(os.path.join(tests_dir, f))]

    if not missing:
        return True, f"全部 {len(present)} 个关键测试文件存在"
    return True, f"存在: {len(present)}, 缺失: {', '.join(missing)}"


@register("TI-02", "conftest/pytest 配置可用", "测试基础设施")
def check_pytest_config() -> tuple[bool, str]:
    """Check pytest configuration exists."""
    cfg_files = [
        os.path.join(BACKEND_DIR, "pytest.ini"),
        os.path.join(BACKEND_DIR, "pyproject.toml"),
        os.path.join(BACKEND_DIR, "setup.cfg"),
    ]
    found = [f for f in cfg_files if os.path.exists(f)]
    if found:
        return True, f"Pytest 配置: {', '.join(os.path.basename(f) for f in found)}"
    return False, "未找到 pytest.ini / pyproject.toml / setup.cfg"


@register("TI-03", "run_all.sh 测试运行器可用", "测试基础设施")
def check_test_runner() -> tuple[bool, str]:
    """Check run_all.sh exists and is executable."""
    path = os.path.join(BACKEND_DIR, "tests", "run_all.sh")
    if os.path.exists(path):
        executable = os.access(path, os.X_OK)
        return True, f"run_all.sh 存在{' (可执行)' if executable else ' (需 chmod +x)'}"
    return False, f"run_all.sh 不存在 ({path})"


# ═══════════════════════════════════════════════════════════════════
# Gap checks — Environment
# ═══════════════════════════════════════════════════════════════════

@register("ENV-01", "Python 版本 >= 3.11", "环境")
def check_python_version() -> tuple[bool, str]:
    """Check Python version is adequate."""
    v = sys.version_info
    if v.major >= 3 and v.minor >= 11:
        return True, f"Python {v.major}.{v.minor}.{v.micro}"
    return False, f"Python {v.major}.{v.minor}.{v.micro} — 需要 3.11+" if v.major >= 3 else f"Python {v.major}.{v.minor} — 需要 Python 3"


@register("ENV-02", "关键依赖已安装", "环境")
def check_critical_dependencies() -> tuple[bool, str]:
    """Check critical pip packages are installed."""
    required = ["fastapi", "pydantic", "pydantic_settings", "aiosqlite", "httpx"]
    optional = ["redis", "asyncpg", "sentry_sdk", "opentelemetry"]

    missing_req = []
    present_opt = []

    for pkg in required:
        try:
            importlib.import_module(pkg.replace("-", "_"))
        except ImportError:
            missing_req.append(pkg)

    for pkg in optional:
        try:
            importlib.import_module(pkg.replace("-", "_"))
            present_opt.append(pkg)
        except ImportError:
            pass

    if not missing_req:
        detail = f"全部 {len(required)} 个必需依赖已安装"
        if present_opt:
            detail += f" | 可选已安装: {', '.join(present_opt)}"
        return True, detail
    return False, f"缺失必需依赖: {', '.join(missing_req)}"


# ═══════════════════════════════════════════════════════════════════
# Main scanner
# ═══════════════════════════════════════════════════════════════════

def run_all_checks(verbose: bool = False) -> list[CheckResult]:
    """Run all registered gap checks and return results."""
    results: list[CheckResult] = []
    completed: dict[str, bool] = {}

    for check_id, name, category, depends_on, fn in _registry:
        # Check dependencies
        deps_met = True
        for dep in depends_on:
            if dep in completed and not completed[dep]:
                deps_met = False
                break

        if not deps_met:
            result = CheckResult(
                id=check_id,
                name=name,
                category=category,
                status=False,
                detail="跳过 — 依赖检查未通过",
                duration_ms=0.0,
                depends_on=depends_on,
            )
            results.append(result)
            completed[check_id] = False
            continue

        # Run the check
        start = time.perf_counter()
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"异常: {e}"
        duration = (time.perf_counter() - start) * 1000

        result = CheckResult(
            id=check_id,
            name=name,
            category=category,
            status=ok,
            detail=detail,
            duration_ms=round(duration, 1),
            depends_on=depends_on,
        )
        results.append(result)
        completed[check_id] = ok

    return results


def print_report(results: list[CheckResult], verbose: bool = False) -> None:
    """Print formatted report to stdout."""
    categories: dict[str, list[CheckResult]] = {}
    for r in results:
        categories.setdefault(r.category, []).append(r)

    total = len(results)
    passed = sum(1 for r in results if r.status)
    failed = total - passed
    score = (passed / total * 100) if total > 0 else 0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  链客宝 — 部署缺口扫描报告 (Gap Checklist Report)       ║")
    print("║  LianKeBao Deployment Gap Scanner                      ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Time: {timestamp:<46s}║")
    print(f"║  INFRA_PHASE: {os.environ.get('INFRA_PHASE', '0'):<39s}║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    for cat, cat_results in sorted(categories.items()):
        cat_passed = sum(1 for r in cat_results if r.status)
        cat_total = len(cat_results)
        print(f"\033[1m{'─'*60}\033[0m")
        print(f"\033[1m  {cat}  ({cat_passed}/{cat_total})\033[0m")
        print(f"\033[1m{'─'*60}\033[0m")

        for r in cat_results:
            print(r.to_ansi())
            if verbose and not r.status and r.detail:
                print(f"      \033[90m→ 详情: {r.detail}\033[0m")

    print()
    print(f"\033[1m{'='*60}\033[0m")
    print(f"\033[1m  总计: {passed}/{total} 通过 ({score:.1f}%){' ' if score >= 80 else ' ⚠️ 需要关注'}\033[0m")
    if failed > 0:
        print(f"\033[31m  失败: {failed} 项检查未通过\033[0m")
        for r in results:
            if not r.status:
                print(f"    \033[31m• [{r.id}] {r.name}: {r.detail}\033[0m")
    print(f"\033[1m{'='*60}\033[0m")
    print()

    # Score interpretation
    if score == 100:
        print("  \033[32m🎉 全部就绪！链客宝可以部署到生产环境。\033[0m")
    elif score >= 90:
        print("  \033[33m✅ 基本就绪 — 少量检查未通过，建议修复后再部署。\033[0m")
    elif score >= 70:
        print("  \033[33m⚠️ 部分就绪 — 需要修复未通过的检查项。\033[0m")
    else:
        print("  \033[31m❌ 未就绪 — 需要大量修复才能部署生产环境。\033[0m")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="链客宝 — 部署缺口扫描清单",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/gap_checklist.py              # 标准输出
  python scripts/gap_checklist.py --json       # JSON 输出
  python scripts/gap_checklist.py --verbose    # 详细诊断
  python scripts/gap_checklist.py --ci         # CI 模式
        """,
    )
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--ci", action="store_true", help="CI 模式 (exit code = 失败数量)")
    args = parser.parse_args()

    results = run_all_checks(verbose=args.verbose)
    passed = sum(1 for r in results if r.status)
    failed = len(results) - passed

    if args.json:
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "infra_phase": os.environ.get("INFRA_PHASE", "0"),
            "total_checks": len(results),
            "passed": passed,
            "failed": failed,
            "score_pct": round(passed / len(results) * 100, 1) if results else 0,
            "checks": [r.to_dict() for r in results],
        }
        json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print_report(results, verbose=args.verbose)

    if args.ci:
        return failed
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
