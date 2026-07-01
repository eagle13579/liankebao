"""Application lifecycle management — wires AgentRuntime into FastAPI startup/shutdown.

Phase 1 infrastructure: wires the Agent Runtime into the application lifecycle,
enabling persistent multi-process operation with proper startup and graceful
shutdown of all AI Digital Employee agents.

Usage (modern FastAPI lifespan pattern):
    from contextlib import asynccontextmanager
    from app.lifespan import agent_lifespan

    @asynccontextmanager
    async def lifespan(app):
        async with agent_lifespan(app):
            yield

    app = FastAPI(lifespan=lifespan)

Usage (legacy add_event_handler pattern — compatible with existing create_app):
    from fastapi import FastAPI
    from app.lifespan import startup_handler, shutdown_handler

    app = FastAPI()
    app.add_event_handler("startup", startup_handler)
    app.add_event_handler("shutdown", shutdown_handler)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.dependencies import get_agent_runtime, init_all, shutdown_all

logger = logging.getLogger(__name__)

# ======================================================================
# Legacy event handler functions (compatible with @app.on_event)
# ======================================================================


async def startup_handler() -> None:
    """Initialize all system dependencies and start the Agent Runtime.

    Called on application startup (via @app.on_event("startup") or
    app.add_event_handler("startup", startup_handler)).

    Flow:
        1. Initialize all infrastructure singletons (cache, event bus, broker, etc.)
        2. Create and register all AI employee agents
        3. Start the Agent Runtime (cron scheduler, event listener, agent lifecycle)
    """
    logger.info("=== Phase 1 startup: Initializing all system dependencies ===")

    try:
        await init_all()
        logger.info("All system dependencies initialized and runtime started")
    except Exception as exc:
        logger.exception(
            "FATAL: Failed to initialize system dependencies: %s", exc
        )
        # In non-production environments, we may continue with degraded functionality
        raise


async def shutdown_handler() -> None:
    """Gracefully shut down all system dependencies.

    Called on application shutdown (via @app.on_event("shutdown") or
    app.add_event_handler("shutdown", shutdown_handler)).

    Flow:
        1. Stop the Agent Runtime (gracefully stops all agents)
        2. Stop event bus consumer
        3. Stop cache background tasks
        4. Close database connections
    """
    logger.info("=== Phase 1 shutdown: Shutting down all system dependencies ===")

    try:
        await shutdown_all()
        logger.info("All system dependencies shut down gracefully")
    except Exception as exc:
        logger.exception("Error during system shutdown: %s", exc)


# ======================================================================
# Context manager (modern FastAPI lifespan pattern)
# ======================================================================


@asynccontextmanager
async def agent_lifespan(app: object) -> AsyncIterator[None]:
    """Context manager for Agent Runtime lifecycle.

    Use with FastAPI's lifespan parameter for modern lifecycle management.

    Example:
        app = FastAPI(lifespan=agent_lifespan)

    Args:
        app: The FastAPI application instance (used for context only).

    Yields:
        None — the application runs while this context manager is active.
    """
    # ── Startup ───────────────────────────────────────────────────────
    logger.info("Agent lifespan context manager started")

    # 1. Get or create the Agent Runtime singleton (registers all agents)
    try:
        runtime = get_agent_runtime()
        logger.info("AgentRuntime instance acquired: %s", runtime)
    except Exception as exc:
        logger.exception("FATAL: Failed to create AgentRuntime: %s", exc)
        # Yield anyway — the app might handle partial functionality
        yield
        return

    # 2. Start the runtime (starts all registered agents, cron, event listener)
    try:
        await runtime.start()
        logger.info("AgentRuntime started successfully")
    except Exception as exc:
        logger.exception("FATAL: Failed to start AgentRuntime: %s", exc)
        yield
        await _safe_stop(runtime)
        return

    # ── Yield — application runs here ─────────────────────────────────
    try:
        yield
    finally:
        # ── Shutdown ──────────────────────────────────────────────────
        logger.info("Agent lifespan context manager shutting down...")
        await _safe_stop(runtime)
        logger.info("Agent lifespan context manager shut down complete")


async def _safe_stop(runtime: object) -> None:
    """Safely stop the Agent Runtime, catching and logging all errors.

    Args:
        runtime: The AgentRuntime instance to stop.
    """
    if runtime is None:
        return

    try:
        # Try to call runtime.stop()
        stop_method = getattr(runtime, "stop", None)
        if stop_method is not None:
            await stop_method()
            logger.info("AgentRuntime stopped")
    except asyncio.CancelledError:
        logger.info("AgentRuntime stop was cancelled (shutdown in progress)")
    except Exception as exc:
        logger.exception("Error during AgentRuntime shutdown: %s", exc)


# ======================================================================
# Convenience: Wire runtime into an existing FastAPI app
# ======================================================================


def wire_into_app(app: object) -> None:
    """Wire Agent Runtime lifecycle into a FastAPI application.

    Adds startup and shutdown event handlers to the app. Compatible
    with the existing ``@app.on_event("startup")`` pattern used in
    ``create_app()``.

    Args:
        app: A FastAPI application instance (must have ``add_event_handler`` method).
    """
    if not hasattr(app, "add_event_handler"):
        logger.warning(
            "Can't wire AgentRuntime: app does not support add_event_handler"
        )
        return

    # Remove any existing handlers for these events to avoid duplicates
    app.add_event_handler("startup", startup_handler)
    app.add_event_handler("shutdown", shutdown_handler)

    logger.info(
        "Agent Runtime lifecycle wired into app via startup/shutdown event handlers"
    )
