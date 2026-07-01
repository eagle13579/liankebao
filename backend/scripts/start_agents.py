"""Agent Runtime Startup Script — Launch all 9 AI Digital Employees 24/7.

Usage:
    python scripts/start_agents.py

    Or with explicit settings:
    REDIS_HOST=redis REDIS_PORT=6379 python scripts/start_agents.py

This script:
    1. Sets INFRA_PHASE=1 by default (Phase 1 infrastructure)
    2. Verifies Phase 1 modules (RedisCache + SQLiteEventBus)
    3. Initialises Phase 1 infrastructure singletons
    4. Creates all 9 legion-backed AI employees
    5. Connects them to Gaia Evolution Brain
    6. Starts the Agent Runtime
    7. Reports agent health status on startup
    8. Prints an "ALL SYSTEMS GO" report at the end
    9. Handles SIGTERM/SIGINT for graceful shutdown
    10. Runs indefinitely until terminated
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone

# ── Auto-set INFRA_PHASE to 1 unless explicitly set ─────────────────
os.environ.setdefault("INFRA_PHASE", "1")

# ── Ensure backend is on sys.path ────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
logger = logging.getLogger("start_agents")

# Suppress noisy libs
for lib in ("aiosqlite", "httpx", "httpcore", "urllib3", "asyncio"):
    logging.getLogger(lib).setLevel(logging.WARNING)


# ======================================================================
# Phase 1 infrastructure verification
# ======================================================================


def verify_infrastructure_modules() -> dict[str, bool]:
    """Import and verify each Phase 1 infrastructure module.

    This runs *before* any singletons are created, allowing us to
    surface missing dependencies early with a clear error message.

    Returns:
        Dict mapping module name → import success (True/False).
    """
    results: dict[str, bool] = {}

    # ── RedisCache ────────────────────────────────────────────────
    try:
        from app.cache.adapters.redis_adapter import RedisCache  # noqa: F401
        results["RedisCache"] = True
    except ImportError as e:
        results["RedisCache"] = False
        logger.warning("RedisCache import failed — will fall back to InMemoryCache: %s", e)
    except Exception as e:
        results["RedisCache"] = False
        logger.warning("RedisCache unexpected error — will fall back to InMemoryCache: %s", e)

    # ── SQLiteEventBus ────────────────────────────────────────────
    try:
        from app.events.adapters.sqlite_adapter import SQLiteEventBus  # noqa: F401
        results["SQLiteEventBus"] = True
    except ImportError as e:
        results["SQLiteEventBus"] = False
        logger.warning("SQLiteEventBus import failed — will fall back to InProcessEventBus: %s", e)
    except Exception as e:
        results["SQLiteEventBus"] = False
        logger.warning("SQLiteEventBus unexpected error — will fall back to InProcessEventBus: %s", e)

    # ── New architecture layers (circular-import-safe) ────────────
    for mod_name, mod_path in [
        ("IdentityInterfaces", "app.identity.interfaces"),
        ("CachedAIGateway", "app.ai.gateway.adapters.cached_gateway_adapter"),
        ("FallbackAIGateway", "app.ai.gateway.adapters.fallback_gateway_adapter"),
    ]:
        try:
            importlib = __import__("importlib")
            importlib.import_module(mod_path)
            results[mod_name] = True
        except Exception as e:
            results[mod_name] = False
            logger.warning("%s import failed: %s", mod_name, e)

    return results


# ======================================================================
# Signal handling — graceful shutdown
# ======================================================================

_shutdown_event = asyncio.Event()


def _handle_signal(sig: int, _frame: object | None = None) -> None:
    """Set the shutdown event on SIGTERM/SIGINT."""
    sig_name = signal.Signals(sig).name
    logger.info("Received signal %s — initiating graceful shutdown...", sig_name)
    _shutdown_event.set()


def _install_signal_handlers() -> None:
    """Install signal handlers for graceful shutdown.

    Runs in the main thread before the event loop starts.
    """
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
            logger.debug("Installed handler for %s", signal.Signals(sig).name)
        except (ValueError, OSError) as exc:
            logger.warning("Could not install handler for %s: %s", sig, exc)


# ======================================================================
# Main startup
# ======================================================================


async def main() -> int:
    """Start the Agent Runtime with all 9 AI employees.

    Returns:
        0 on clean exit, 1 on error.
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info(" 链客宝 Agent Runtime — Starting up")
    logger.info(" Phase: %s", os.environ.get("INFRA_PHASE", "1"))
    logger.info(" PID: %d", os.getpid())
    logger.info(" Time: %s", start_time.isoformat())
    logger.info("=" * 60)

    # ── 0. Verify infrastructure modules ──────────────────────────
    logger.info("Step 0/5: Verifying infrastructure modules...")
    infra_results = verify_infrastructure_modules()
    all_ok = all(infra_results.values())
    for name, ok in infra_results.items():
        mark = " ✅" if ok else " ⚠️"
        logger.info("   %s:%s", name.ljust(30), mark)
    if not all_ok:
        logger.warning("Some modules unavailable — will use graceful fallbacks")

    # ── 1. Initialise all infrastructure singletons ────────────────
    logger.info("Step 1/5: Initialising infrastructure singletons...")
    try:
        # Import here so INFRA_PHASE env var is already set
        from app.dependencies import (
            get_cache,
            get_event_bus,
            get_service_broker,
            get_gaia_brain,
            get_agent_runtime,
        )

        cache = get_cache()
        event_bus = get_event_bus()
        broker = get_service_broker()
        brain = get_gaia_brain()

        logger.info(
            "Infrastructure: cache=%s  event_bus=%s  broker=%s  brain=%s",
            type(cache).__name__,
            type(event_bus).__name__,
            type(broker).__name__,
            type(brain).__name__,
        )
    except Exception as exc:
        logger.exception("Failed to initialise infrastructure: %s", exc)
        return 1

    # ── 2. Start infrastructure that needs lifecycle ───────────────
    logger.info("Step 2/5: Starting infrastructure lifecycle...")
    try:
        if hasattr(event_bus, "start"):
            await event_bus.start()
            logger.info("Event bus started: %s", type(event_bus).__name__)

        if hasattr(cache, "start"):
            await cache.start()
            logger.info("Cache started: %s", type(cache).__name__)
    except Exception as exc:
        logger.exception("Failed to start infrastructure: %s", exc)
        return 1

    # ── 3. Get the Agent Runtime (creates all 9 agents) ────────────
    logger.info("Step 3/5: Initialising Agent Runtime with all 9 employees...")
    try:
        runtime = get_agent_runtime()
        logger.info(
            "Agent Runtime created with %d agents",
            len(runtime.agents),
        )
    except Exception as exc:
        logger.exception("Failed to create Agent Runtime: %s", exc)
        return 1

    # ── 4. Start the runtime ───────────────────────────────────────
    logger.info("Step 4/5: Starting Agent Runtime...")
    try:
        await runtime.start()
    except Exception as exc:
        logger.exception("Failed to start Agent Runtime: %s", exc)
        return 1

    # ── 5. Report agent health ─────────────────────────────────────
    status = await runtime.get_status()
    running_count = sum(
        1 for a in status.get("agents", {}).values() if a.get("status") == "idle"
    )
    total_count = len(status.get("agents", {}))
    uptime = status.get("runtime", {}).get("uptime_seconds", 0)

    logger.info("─" * 60)
    logger.info(
        " 🟢 %d/%d agents running (uptime=%.1fs)",
        running_count,
        total_count,
        uptime,
    )
    for name, agent_status in status.get("agents", {}).items():
        logger.info(
            "    %s: %s (tools=%d, cron=%d, tasks=%d/%d)",
            name.ljust(15),
            agent_status.get("status", "?").center(12),
            agent_status.get("tool_count", 0),
            agent_status.get("cron_job_count", 0),
            agent_status.get("active_tasks", 0),
            agent_status.get("max_concurrent", 5),
        )
    logger.info("─" * 60)

    # ── Install scheduler rules ────────────────────────────────────
    try:
        from app.agents.scheduler_rules import install_scheduler_rules

        await install_scheduler_rules()
        logger.info("Scheduler rules installed for all agents")
    except Exception as exc:
        logger.warning("Failed to install scheduler rules: %s", exc)

    # ── ALL SYSTEMS GO report ───────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info("  🚀  ALL SYSTEMS GO")
    logger.info("=" * 60)
    logger.info("  链客宝 Agent Runtime")
    logger.info("  Phase:      %s", os.environ.get("INFRA_PHASE", "1"))
    logger.info("  Agents:     %d/%d running", running_count, total_count)
    logger.info("  Cache:      %s", type(cache).__name__)
    logger.info("  EventBus:   %s", type(event_bus).__name__)
    logger.info("  Broker:     %s", type(broker).__name__)
    logger.info("  Brain:      %s", type(brain).__name__)
    logger.info("  PID:        %d", os.getpid())
    logger.info("  Startup:    %.1fs", elapsed)
    for name, agent_status in status.get("agents", {}).items():
        logger.info(
            "    %s: %s",
            name.ljust(20),
            agent_status.get("status", "?"),
        )
    logger.info("─" * 60)
    logger.info(" Infrastructure modules:")
    for mod_name, ok in infra_results.items():
        logger.info("    %s [%s]", mod_name.ljust(25), "OK" if ok else "FALLBACK")
    logger.info("=" * 60)
    logger.info(
        " 🚀 Agent Runtime fully operational in %.1fs — awaiting shutdown signal...",
        elapsed,
    )

    await _shutdown_event.wait()

    # ── Graceful shutdown ──────────────────────────────────────────
    logger.info("Initiating graceful shutdown...")
    try:
        from app.dependencies import shutdown_all

        await shutdown_all()
        logger.info("All systems shut down cleanly")
    except Exception as exc:
        logger.exception("Error during shutdown: %s", exc)
        return 1

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        " ⏹️  Agent Runtime shut down after %.1f seconds of operation",
        elapsed,
    )
    return 0


# ======================================================================
# Entry point
# ======================================================================

if __name__ == "__main__":
    _install_signal_handlers()

    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
        exit_code = 0
    except Exception as exc:
        logger.exception("Unhandled exception in Agent Runtime: %s", exc)
        exit_code = 1

    sys.exit(exit_code)
