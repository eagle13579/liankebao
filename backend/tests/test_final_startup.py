"""
链客宝 — Final Startup Verification Test

Tests that our new architecture layers can be imported WITHOUT
triggering circular imports.  These layers are independent of
the old app circular import chain:

    1. Identity layer (app.identity) — RBAC, JWT, tenant isolation
    2. CachedAIGateway (app.ai.gateway.adapters.cached_gateway_adapter)
    3. FallbackAIGateway (app.ai.gateway.adapters.fallback_gateway_adapter)

Each test imports the module directly in a fresh sub-interpreter context
(separate process) to ensure no circular-import pollution from prior
imports.  If ALL three pass, the new architecture is circular-import-safe.

Usage:
    # Run directly (no pytest required):
    python tests/test_final_startup.py

    # Run with pytest (verbose):
    python -m pytest tests/test_final_startup.py -v

    # Run the circular import stress test:
    python tests/test_final_startup.py --stress
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import subprocess
import sys
import time
from typing import Any

# ── Ensure backend is on sys.path ────────────────────────────────────
BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ── Set INFRA_PHASE so dependencies choose Phase 1 implementations ──
os.environ.setdefault("INFRA_PHASE", "1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("test_final_startup")


# ======================================================================
# Test helpers
# ======================================================================


class TestResult:
    """Result of a single import test."""

    def __init__(self, name: str, module_path: str) -> None:
        self.name = name
        self.module_path = module_path
        self.passed: bool = False
        self.duration_ms: float = 0.0
        self.error: str | None = None

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name} ({self.duration_ms:.0f}ms): {self.error or 'ok'}"


def _import_in_fresh_process(module_path: str, timeout: int = 30) -> tuple[bool, str]:
    """Import a module in a *fresh subprocess* to avoid import pollution.

    This is the gold-standard test for circular-import safety: by running
    in a brand-new Python interpreter, we guarantee no prior imports can
    mask a real circular import.

    Args:
        module_path: Dotted module path (e.g. 'app.identity.interfaces').
        timeout: Max seconds to wait for the subprocess.

    Returns:
        Tuple of (success: bool, error_message: str).
    """
    probe_code = f"""
import sys, os
sys.path.insert(0, {BACKEND_DIR!r})
os.environ['INFRA_PHASE'] = '1'
try:
    import importlib
    mod = importlib.import_module({module_path!r})
    print(f'OK: {{mod.__name__}} imported successfully from {{getattr(mod, "__file__", "?")}}')
except Exception as e:
    print(f'FAIL: {{e}}', file=sys.stderr)
    sys.exit(1)
"""
    start = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = (time.monotonic() - start) * 1000.0
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000.0
        return False, f"Timed out after {timeout}s"
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000.0
        return False, str(e)


def _import_directly(module_path: str) -> tuple[bool, str]:
    """Import a module in-process (faster, less isolated).

    Useful for quick checks; the subprocess approach is used for the
    definitive circular-import test.
    """
    try:
        mod = importlib.import_module(module_path)
        return True, f"{mod.__name__} from {getattr(mod, '__file__', '?')}"
    except Exception as e:
        return False, str(e)


# ======================================================================
# Test suites
# ======================================================================


# ── Identity layer ───────────────────────────────────────────────────

MODULES_IDENTITY = [
    ("IdentityInterfaces", "app.identity.interfaces"),
    ("RBACAdapter", "app.identity.adapters.rbac_adapter"),
    ("JWTLibAdapter", "app.identity.adapters.jwt_adapter"),
    ("TenantAdapter", "app.identity.adapters.simple_tenant_adapter"),
]


def test_identity_imports(subprocess: bool = True) -> list[TestResult]:
    """Test that all identity-layer modules circular-import safely."""
    results: list[TestResult] = []
    for name, mod_path in MODULES_IDENTITY:
        result = TestResult(name, mod_path)
        start = time.monotonic()
        if subprocess:
            ok, msg = _import_in_fresh_process(mod_path)
        else:
            ok, msg = _import_directly(mod_path)
        result.duration_ms = (time.monotonic() - start) * 1000.0
        result.passed = ok
        result.error = None if ok else msg
        results.append(result)
    return results


# ── CachedAIGateway layer ────────────────────────────────────────────

MODULES_CACHED_GATEWAY = [
    ("CachedAIGateway", "app.ai.gateway.adapters.cached_gateway_adapter"),
]


def test_cached_gateway_imports(subprocess: bool = True) -> list[TestResult]:
    """Test that CachedAIGateway imports without circular deps."""
    results: list[TestResult] = []
    for name, mod_path in MODULES_CACHED_GATEWAY:
        result = TestResult(name, mod_path)
        start = time.monotonic()
        if subprocess:
            ok, msg = _import_in_fresh_process(mod_path)
        else:
            ok, msg = _import_directly(mod_path)
        result.duration_ms = (time.monotonic() - start) * 1000.0
        result.passed = ok
        result.error = None if ok else msg
        results.append(result)
    return results


# ── FallbackAIGateway layer ──────────────────────────────────────────

MODULES_FALLBACK_GATEWAY = [
    ("FallbackAIGateway", "app.ai.gateway.adapters.fallback_gateway_adapter"),
]


def test_fallback_gateway_imports(subprocess: bool = True) -> list[TestResult]:
    """Test that FallbackAIGateway imports without circular deps."""
    results: list[TestResult] = []
    for name, mod_path in MODULES_FALLBACK_GATEWAY:
        result = TestResult(name, mod_path)
        start = time.monotonic()
        if subprocess:
            ok, msg = _import_in_fresh_process(mod_path)
        else:
            ok, msg = _import_directly(mod_path)
        result.duration_ms = (time.monotonic() - start) * 1000.0
        result.passed = ok
        result.error = None if ok else msg
        results.append(result)
    return results


# ── Stress test: import all layers simultaneously ────────────────────


def test_all_layers_stress() -> list[TestResult]:
    """Stress test: import ALL new-architecture layers in one process.

    This simulates the real runtime import order and verifies no
    module prevents another from loading.
    """
    all_modules = MODULES_IDENTITY + MODULES_CACHED_GATEWAY + MODULES_FALLBACK_GATEWAY
    results: list[TestResult] = []

    for name, mod_path in all_modules:
        result = TestResult(name, mod_path)
        start = time.monotonic()
        ok, msg = _import_directly(mod_path)
        result.duration_ms = (time.monotonic() - start) * 1000.0
        result.passed = ok
        result.error = None if ok else msg
        results.append(result)

    return results


# ======================================================================
# Runner
# ======================================================================


def run_all(subprocess: bool = True, stress: bool = False) -> int:
    """Run all startup verification tests.

    Args:
        subprocess: Use subprocess isolation (True = gold standard).
        stress: Also run the in-process stress test.

    Returns:
        0 if all tests pass, 1 if any fail.
    """
    logger.info("=" * 60)
    logger.info(" 链客宝 Final Startup Verification")
    logger.info(" Mode: %s", "subprocess (isolated)" if subprocess else "in-process")
    logger.info(" INFRA_PHASE: %s", os.environ.get("INFRA_PHASE", "1"))
    logger.info(" Python:      %s", sys.version.split()[0])
    logger.info("=" * 60)

    all_results: list[TestResult] = []

    # ── Identity layer ─────────────────────────────────────────────
    logger.info("\n📁 Identity Layer")
    results = test_identity_imports(subprocess=subprocess)
    all_results.extend(results)

    # ── CachedAIGateway layer ──────────────────────────────────────
    logger.info("\n📁 CachedAIGateway Layer")
    results = test_cached_gateway_imports(subprocess=subprocess)
    all_results.extend(results)

    # ── FallbackAIGateway layer ────────────────────────────────────
    logger.info("\n📁 FallbackAIGateway Layer")
    results = test_fallback_gateway_imports(subprocess=subprocess)
    all_results.extend(results)

    # ── Stress test (optional) ────────────────────────────────────
    if stress:
        logger.info("\n💥 Stress Test (all layers in one process)")
        results = test_all_layers_stress()
        all_results.extend(results)

    # ── Report ────────────────────────────────────────────────────
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total = len(all_results)

    logger.info("\n" + "=" * 60)
    logger.info(" RESULTS")
    logger.info("=" * 60)
    for r in all_results:
        mark = " ✅" if r.passed else " ❌"
        logger.info("  %s  %s  (%.0fms)", mark, r.name, r.duration_ms)
        if r.error:
            logger.info("       Error: %s", r.error)

    logger.info("─" * 60)
    logger.info("  Passed: %d/%d", passed, total)
    logger.info("  Failed: %d/%d", failed, total)
    if failed == 0:
        logger.info("  ✅ ALL CIRCULAR IMPORT TESTS PASSED — new architecture layers are safe")
    else:
        logger.info("  ❌ %d test(s) failed — check errors above", failed)
    logger.info("=" * 60)

    return 0 if failed == 0 else 1


# ======================================================================
# Pytest-compatible test functions
# ======================================================================


def test_identity_interfaces_import() -> None:
    """Test app.identity.interfaces imports cleanly."""
    ok, msg = _import_in_fresh_process("app.identity.interfaces")
    assert ok, f"Identity interfaces import failed: {msg}"


def test_identity_rbac_adapter_import() -> None:
    """Test app.identity.adapters.rbac_adapter imports cleanly."""
    ok, msg = _import_in_fresh_process("app.identity.adapters.rbac_adapter")
    assert ok, f"RBAC adapter import failed: {msg}"


def test_identity_jwt_adapter_import() -> None:
    """Test app.identity.adapters.jwt_adapter imports cleanly."""
    ok, msg = _import_in_fresh_process("app.identity.adapters.jwt_adapter")
    assert ok, f"JWT adapter import failed: {msg}"


def test_cached_gateway_import() -> None:
    """Test CachedAIGateway imports without circular deps."""
    ok, msg = _import_in_fresh_process(
        "app.ai.gateway.adapters.cached_gateway_adapter"
    )
    assert ok, f"CachedAIGateway import failed: {msg}"


def test_fallback_gateway_import() -> None:
    """Test FallbackAIGateway imports without circular deps."""
    ok, msg = _import_in_fresh_process(
        "app.ai.gateway.adapters.fallback_gateway_adapter"
    )
    assert ok, f"FallbackAIGateway import failed: {msg}"


# ======================================================================
# CLI entry point
# ======================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="链客宝 Final Startup Verification",
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="Run in-process stress test (imports all layers at once)",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Use in-process imports instead of subprocess isolation",
    )
    args = parser.parse_args()

    exit_code = run_all(
        subprocess=not args.in_process,
        stress=args.stress,
    )
    sys.exit(exit_code)
