"""Dependency Injection — Factory functions that wire the entire system.

Each function returns the interface type (Protocol), but the implementation
can be swapped by changing just ONE line — the import or instantiation
inside the factory.

Architecture:
    - All factories return Protocol types (CacheProtocol, EventBusProtocol, etc.)
    - All implementations live in adapters/ subpackages
    - Swapping from in-process to distributed requires changing ONE factory body

Usage:
    from app.dependencies import (
        get_cache,
        get_event_bus,
        get_service_broker,
        get_ai_gateway,
        get_knowledge_repository,
        get_agent_runtime,
        get_gaia_brain,
    )

    event_bus = get_event_bus()
    await event_bus.start()
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.ai.gateway.interfaces import AIGatewayProtocol
from app.broker.interfaces import ServiceBrokerProtocol
from app.cache.interfaces import CacheProtocol
from app.events.interfaces import EventBusProtocol
from app.repositories.interfaces import KnowledgeRepositoryProtocol

logger = logging.getLogger(__name__)

# ======================================================================
# Cache
# ======================================================================

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  SWAP: Change this ONE import to switch cache backend               ║
# ║  InMemoryCache  →  RedisCache / ClusterRedisCache / TwoTierCache    ║
# ╚══════════════════════════════════════════════════════════════════════╝

_cache_instance: CacheProtocol | None = None


def get_cache() -> CacheProtocol:
    """Return the singleton cache instance.

    Phase 0 (default): InMemoryCache (in-process dict with TTL).
    Phase 1+:         RedisCache (distributed, via redis.asyncio).
                      Falls back to InMemoryCache if Redis is unavailable.
    """
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    if int(os.environ.get("INFRA_PHASE", "0")) >= 1:
        try:
            from app.cache.adapters.redis_adapter import RedisCache
            from app.config import settings

            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
            _cache_instance = RedisCache.from_url(
                redis_url,
                prefix="liankebao:cache",
                namespace="default",
                default_ttl=settings.REDIS_CACHE_TTL,
            )
            logger.info(
                "DI: Cache RedisCache (url=%s, ttl=%ds)",
                redis_url,
                settings.REDIS_CACHE_TTL,
            )
            return _cache_instance
        except Exception as e:
            logger.warning("DI: RedisCache unavailable, falling back to InMemoryCache: %s", e)

    from app.cache.adapters.memory_adapter import InMemoryCache

    _cache_instance = InMemoryCache(default_ttl=300, cleanup_interval=60)
    logger.info(
        "DI: Cache %s (default_ttl=%ds)",
        type(_cache_instance).__name__,
        300,
    )
    return _cache_instance


# ======================================================================
# Service Broker
# ======================================================================

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  SWAP: Change this ONE import to switch broker transport            ║
# ║  InProcessBroker  →  RedisBroker / RabbitMQBroker / KafkaBroker     ║
# ╚══════════════════════════════════════════════════════════════════════╝

_broker_instance: ServiceBrokerProtocol | None = None


def get_service_broker() -> ServiceBrokerProtocol:
    """Return the singleton service broker instance.

    Default: InProcessBroker (in-process direct method calls).
    To switch to distributed, replace the import and constructor below.
    """
    global _broker_instance
    if _broker_instance is not None:
        return _broker_instance

    from app.broker.adapters.inprocess_adapter import InProcessBroker

    _broker_instance = InProcessBroker()
    logger.info("DI: ServiceBroker → %s", type(_broker_instance).__name__)
    return _broker_instance


# ======================================================================
# Event Bus
# ======================================================================

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  SWAP: Change this ONE import to switch event bus transport         ║
# ║  InProcessEventBus  →  RedisEventBus / KafkaEventBus / RabbitMQBus  ║
# ╚══════════════════════════════════════════════════════════════════════╝

_event_bus_instance: EventBusProtocol | None = None


def get_event_bus() -> EventBusProtocol:
    """Return the singleton event bus instance.

    Phase 0 (default): InProcessEventBus (asyncio.Queue-based in-process bus).
    Phase 1+:         SQLiteEventBus (persistent, via aiosqlite).
                      Falls back to InProcessEventBus if aiosqlite is unavailable.
    """
    global _event_bus_instance
    if _event_bus_instance is not None:
        return _event_bus_instance

    if int(os.environ.get("INFRA_PHASE", "0")) >= 1:
        try:
            from pathlib import Path

            from app.events.adapters.sqlite_adapter import SQLiteEventBus

            db_path = Path("data/events.db")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _event_bus_instance = SQLiteEventBus(
                db_path=str(db_path),
                poll_interval=1.0,
                batch_size=50,
                max_retries=3,
            )
            logger.info(
                "DI: EventBus -> SQLiteEventBus (db=%s)",
                db_path,
            )
            return _event_bus_instance
        except Exception as e:
            logger.warning("DI: SQLiteEventBus unavailable, falling back to InProcessEventBus: %s", e)

    from app.events.adapters.inprocess_adapter import InProcessEventBus

    _event_bus_instance = InProcessEventBus(max_queue_size=10_000)
    logger.info("DI: EventBus -> %s", type(_event_bus_instance).__name__)
    return _event_bus_instance


# ======================================================================
# AI Gateway
# ======================================================================

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  SWAP: Change this ONE import to switch AI provider                 ║
# ║  DirectAIGateway  →  OpenAIGateway / AnthropicGateway / OllamaGW    ║
# ╚══════════════════════════════════════════════════════════════════════╝

_ai_gateway_instance: AIGatewayProtocol | None = None


def get_ai_gateway() -> AIGatewayProtocol:
    """Return the singleton AI gateway instance.

    Default: DirectAIGateway (calls DeepSeek API directly via httpx).
    To switch providers, replace the import and constructor below.
    """
    global _ai_gateway_instance
    if _ai_gateway_instance is not None:
        return _ai_gateway_instance

    from app.ai.gateway.adapters.direct_api_adapter import DirectAIGateway

    _ai_gateway_instance = DirectAIGateway()
    logger.info("DI: AIGateway → %s", type(_ai_gateway_instance).__name__)
    return _ai_gateway_instance


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  PHASE 2 CONFIGURATION (uncomment to activate caching + fallback)   ║
# ║  CachedAIGateway  +  FallbackAIGateway  =  production-grade AI      ║
# ╚══════════════════════════════════════════════════════════════════════╝

# from app.ai.gateway.adapters.cached_gateway_adapter import CachedAIGateway
# from app.ai.gateway.adapters.fallback_gateway_adapter import FallbackAIGateway
#
#
# def get_ai_gateway_v2() -> AIGatewayProtocol:
#     """Return a Phase 2 AI gateway with caching, rate limiting, and fallback.
#
#     Wraps the primary DirectAIGateway in:
#         1. CachedAIGateway — response caching, rate limiting, circuit breaker
#         2. FallbackAIGateway — falls back to a raw DirectAIGateway on error
#
#     This provides two layers of resilience:
#         - Cache hits avoid API calls entirely (cost savings + latency)
#         - If the cached gateway fails (circuit open / rate limited), the
#           inner fallback handles the request
#     """
#     if PHASE >= 2:
#         direct = DirectAIGateway()
#         cached = CachedAIGateway(
#             inner=direct,
#             cache=get_cache(),
#             cache_ttl=3600,
#             rate_limit_rpm=60,
#             circuit_breaker_threshold=3,
#             circuit_breaker_cooldown=30.0,
#         )
#         return FallbackAIGateway(
#             gateways=[cached, direct],
#             log_on_fallback=True,
#         )
#     return DirectAIGateway()


# ======================================================================
# Knowledge Repository
# ======================================================================

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  SWAP: Change this ONE import to switch data backend                ║
# ║  SQLAlchemyKnowledgeRepository  →  MongoKnowledgeRepository  →  ... ║
# ╚══════════════════════════════════════════════════════════════════════╝

_knowledge_repo_instance: KnowledgeRepositoryProtocol | None = None


def get_knowledge_repository() -> KnowledgeRepositoryProtocol:
    """Return the singleton knowledge repository instance.

    Default: SQLAlchemyKnowledgeRepository using AsyncSessionLocal.
    To switch to MongoDB or another backend, replace the import and
    constructor below.
    """
    global _knowledge_repo_instance
    if _knowledge_repo_instance is not None:
        return _knowledge_repo_instance

    from app.database import AsyncSessionLocal
    from app.repositories.adapters.sqlalchemy_adapter import (
        SQLAlchemyKnowledgeRepository,
    )

    _knowledge_repo_instance = SQLAlchemyKnowledgeRepository(AsyncSessionLocal)
    logger.info(
        "DI: KnowledgeRepository → %s",
        type(_knowledge_repo_instance).__name__,
    )
    return _knowledge_repo_instance


# ======================================================================
# Gaia Evolution Brain
# ======================================================================


def get_gaia_brain() -> Any:
    """Return the singleton GaiaEvolutionBrain instance.

    This delegates to the existing singleton in gaia_evolution_brain.py.
    Note: GaiaEvolutionBrain is not a Protocol — it's a concrete class
    that is already a singleton in the existing codebase.

    Returns:
        The shared GaiaEvolutionBrain instance.
    """
    from app.ai.gaia_evolution_brain import get_gaia_brain as _get_brain

    return _get_brain()


# ======================================================================
# Agent Runtime (wires all AI Digital Employees)
# ======================================================================

_runtime_instance: Any | None = None


def get_agent_runtime() -> Any:
    """Return the singleton AgentRuntime with ALL 9 AI Digital Employees
    wired to their 记忆宫殿 legion employee souls.

    This is the top-level factory that wires everything together:
        1. Creates/retrieves all infrastructure singletons
        2. Creates all 9 legion-backed AI employee agents via create_legion_agent
        3. Registers each agent's employee personality + memory.db + mental models
        4. Returns the runtime (caller must call .start() separately)

    Each agent is connected to a real legion employee:
        emp-烛龙 → Backend    | emp-狴犴 → QA        | emp-獬豸 → Security
        emp-乘黄 → Growth     | emp-文鳐 → Knowledge | emp-开明兽 → Architecture
        emp-计然 → Data       | emp-䑏疏 → SRE       | emp-白泽 → Support/CEO

    Returns:
        AgentRuntime instance with all 9 agents registered.
    """
    global _runtime_instance
    if _runtime_instance is not None:
        return _runtime_instance

    # ── 1. Get infrastructure singletons ────────────────────────────
    event_bus = get_event_bus()
    broker = get_service_broker()
    brain = get_gaia_brain()

    # ── 2. Import the runtime ───────────────────────────────────────
    from app.agents.agent_runtime import AgentRuntime

    runtime = AgentRuntime(event_bus=event_bus, broker=broker)

    # ── 3. Create all legion-backed AI employees ────────────────────
    #     Each agent gets its legion employee's soul, memory, and personality
    from app.agents.employee_profiles import create_legion_agent

    agent_types = [
        "backend",
        "qa",
        "security",
        "growth",
        "knowledge",
        "architecture",
        "data",
        "sre",
        "support",
    ]

    created_agents = []
    for agent_type in agent_types:
        try:
            employee, agent = create_legion_agent(
                agent_type=agent_type,
                brain=brain,
                broker=broker,
                event_bus=event_bus,
            )
            created_agents.append(agent)
            logger.info(
                "DI: Created legion agent '%s' → %s (%s)",
                agent_type,
                employee.name,
                employee.employee_id,
            )
        except Exception as exc:
            logger.error(
                "DI: Failed to create legion agent '%s': %s",
                agent_type,
                exc,
            )

    # ── 4. Register with runtime ────────────────────────────────────
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        for agent in created_agents:
            loop.create_task(runtime.register(agent))
    except RuntimeError:
        # No running loop — will need manual registration
        logger.warning("No running event loop — agents will need manual registration")

    _runtime_instance = runtime
    logger.info(
        "DI: AgentRuntime created with %d legion-backed agents",
        len(created_agents),
    )

    return _runtime_instance


# ======================================================================
# Convenience: Initialize all singletons
# ======================================================================


async def init_all() -> dict[str, Any]:
    """Initialize all system singletons and return them in a dict.

    This is the "one-call" setup for the entire AI Digital Employee system.
    Call this at application startup.

    Returns:
        Dict with keys: cache, broker, event_bus, ai_gateway,
        knowledge_repository, gaia_brain, agent_runtime.
    """
    logger.info("Initializing all system dependencies...")

    # Initialize singletons (order matters: infrastructure first)
    cache = get_cache()
    broker = get_service_broker()
    event_bus = get_event_bus()
    ai_gateway = get_ai_gateway()
    knowledge_repo = get_knowledge_repository()
    brain = get_gaia_brain()
    runtime = get_agent_runtime()

    # Start infrastructure that needs lifecycle management
    if hasattr(event_bus, "start"):
        await event_bus.start()
        logger.info("Event bus started")

    if hasattr(cache, "start"):
        await cache.start()
        logger.info("Cache started")

    # Start the runtime (this starts all agents)
    await runtime.start()
    logger.info("Agent runtime started")

    return {
        "cache": cache,
        "broker": broker,
        "event_bus": event_bus,
        "ai_gateway": ai_gateway,
        "knowledge_repository": knowledge_repo,
        "gaia_brain": brain,
        "agent_runtime": runtime,
    }


async def shutdown_all() -> None:
    """Gracefully shut down all system singletons.

    Call this at application shutdown to ensure clean teardown.
    """
    logger.info("Shutting down all system dependencies...")

    global _runtime_instance, _event_bus_instance, _cache_instance

    # Stop runtime (stops all agents)
    if _runtime_instance is not None:
        try:
            await _runtime_instance.stop()
            logger.info("Agent runtime stopped")
        except Exception as exc:
            logger.error("Error stopping runtime: %s", exc)

    # Stop event bus
    if _event_bus_instance is not None:
        try:
            if hasattr(_event_bus_instance, "stop"):
                await _event_bus_instance.stop()
                logger.info("Event bus stopped")
        except Exception as exc:
            logger.error("Error stopping event bus: %s", exc)

    # Stop cache
    if _cache_instance is not None:
        try:
            if hasattr(_cache_instance, "stop"):
                await _cache_instance.stop()
                logger.info("Cache stopped")
        except Exception as exc:
            logger.error("Error stopping cache: %s", exc)

    # Reset singletons
    _runtime_instance = None
    _event_bus_instance = None
    _cache_instance = None
    _broker_instance = None
    _ai_gateway_instance = None
    _knowledge_repo_instance = None

    logger.info("All system dependencies shut down")
