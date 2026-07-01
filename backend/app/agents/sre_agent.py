"""SREAgent — Site Reliability Engineer Digital Employee.

An AI employee that proactively monitors system health, auto-remediates
common issues, forecasts capacity needs, and responds to critical incidents.

Architecture:
    Extends BaseAgent with SRE-specific tools, cron jobs, and event handlers.
    Works via three mechanisms:
        1. Cron-driven health checks (every 5 min) + capacity forecasts (every 30 min)
        2. Event-driven incident response (metrics.alert_critical)
        3. Auto-remediation of known failure patterns
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import AgentConfig, AgentStatus, BaseAgent, CronJob

logger = logging.getLogger(__name__)


class SREAgent(BaseAgent):
    """Site Reliability Engineer — monitors, remediates, forecasts.

    This agent is the autonomous SRE on-call. It continuously checks
    the health of all critical infrastructure components and takes
    corrective action when anomalies are detected.

    Args:
        config: Agent configuration (defaults to SRE role).
        brain: GaiaEvolutionBrain reference for learning and trend analysis.
        broker: ServiceBrokerProtocol reference for cross-service calls.
        event_bus: EventBusProtocol reference for publishing alerts.
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        brain: Any | None = None,
        broker: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        sre_config = config or AgentConfig(
            agent_name="sre_engineer",
            agent_role="site_reliability_engineer",
            knowledge_base_name="infrastructure",
            max_concurrent_tasks=10,
        )
        super().__init__(config=sre_config, brain=brain)
        self.broker: Any | None = broker
        self.event_bus: Any | None = event_bus

        # Track consecutive failures for flap detection
        self._health_history: list[dict[str, Any]] = []
        self._max_history = 100

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def init(self) -> None:
        """Register SRE tools, cron jobs, and event handlers."""
        # Register tools
        self.register_tool("health_check", self.health_check)
        self.register_tool("auto_remediate", self.auto_remediate)
        self.register_tool("capacity_forecast", self.capacity_forecast)

        # Register event handlers
        self.register_event_handler("metrics.alert_critical", self.incident_response)
        self.register_event_handler("infra.service_down", self._handle_service_down)
        self.register_event_handler("infra.high_latency", self._handle_high_latency)

        # Register cron jobs
        self.add_cron_job(
            CronJob(
                schedule="*/5 * * * *",
                action=self.health_check,
                name="health_check_5min",
            )
        )
        self.add_cron_job(
            CronJob(
                schedule="*/30 * * * *",
                action=self.capacity_forecast,
                name="capacity_forecast_30min",
            )
        )

        logger.info("SREAgent initialized with cron jobs and event handlers")

    async def stop(self) -> None:
        """Clean up SRE resources."""
        logger.info("SREAgent stopping — flushing health history")
        # Flush observations to brain
        if self._health_history:
            summary = (
                f"SREAgent performed {len(self._health_history)} health checks. "
                f"Last status: {self._health_history[-1].get('overall', 'unknown')}"
            )
            await self.learn(
                observation=summary,
                metadata={"checks": len(self._health_history), "source": "sre_agent"},
            )
        self._health_history.clear()
        self.status = AgentStatus.STOPPED
        logger.info("SREAgent stopped")

    # ── Health Check ──────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """Run a full infrastructure health check.

        Checks:
            - Database connectivity
            - Redis connectivity (if available)
            - AI Gateway responsiveness
            - Gaia Flywheel operational status

        Returns:
            Dict with per-component status and overall health.
        """
        logger.info("SREAgent running health check cycle...")

        checks: dict[str, Any] = {
            "database": await self._check_db(),
            "redis": await self._check_redis(),
            "ai_gateway": await self._check_ai_gateway(),
            "flywheel": await self._check_flywheel(),
        }

        # Determine overall status
        all_ok = all(c.get("status") == "ok" for c in checks.values())
        any_failed = any(c.get("status") == "error" for c in checks.values())

        overall = "ok" if all_ok else ("degraded" if not any_failed else "error")

        # Determine latency level
        max_latency = max(
            (c.get("latency_ms", 0) for c in checks.values()),
            default=0,
        )
        latency_level = "low"
        if max_latency > 5000:
            latency_level = "high"
        elif max_latency > 1000:
            latency_level = "medium"

        result: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "overall": overall,
            "latency_level": latency_level,
            "max_latency_ms": max_latency,
            "checks": checks,
        }

        # Track history
        self._health_history.append(result)
        if len(self._health_history) > self._max_history:
            self._health_history.pop(0)

        # Learn from health check
        await self.learn(
            observation=(
                f"SRE health check completed: overall={overall}, "
                f"latency={latency_level}, db={checks['database'].get('status')}, "
                f"redis={checks['redis'].get('status')}, "
                f"gateway={checks['ai_gateway'].get('status')}, "
                f"flywheel={checks['flywheel'].get('status')}"
            ),
            metadata={
                "check_type": "full_health",
                "overall": overall,
                "latency_level": latency_level,
                "max_latency_ms": max_latency,
            },
        )

        # Auto-remediate if issues found
        if overall == "error":
            await self.auto_remediate(result)

        # Publish event if degraded or error
        if overall in ("degraded", "error") and self.event_bus is not None:
            try:
                from app.events.interfaces import Event, EventPriority

                await self.event_bus.publish(
                    Event(
                        type="infra.health_degraded",
                        source=self.agent_id,
                        payload={
                            "overall": overall,
                            "checks": {k: v.get("status") for k, v in checks.items()},
                            "timestamp": result["timestamp"],
                        },
                        priority=EventPriority.HIGH,
                    )
                )
            except Exception:
                logger.warning("SREAgent failed to publish health event")

        logger.info(
            "Health check: overall=%s, latency=%s, max_latency=%dms",
            overall,
            latency_level,
            max_latency,
        )
        return result

    async def _check_db(self) -> dict[str, Any]:
        """Check database connectivity by running a simple query.

        Returns:
            Dict with status, latency_ms, and optional error.
        """
        start = datetime.now(UTC)
        try:
            # Try to query the database via broker or directly
            if self.broker is not None:
                from app.broker.interfaces import ServiceRequest

                resp = await self.broker.call(
                    ServiceRequest(
                        service="database",
                        method="check_connection",
                        timeout_ms=10_000,
                    )
                )
                if resp.success:
                    elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
                    return {"status": "ok", "latency_ms": round(elapsed, 2)}
                else:
                    elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
                    return {
                        "status": "error",
                        "latency_ms": round(elapsed, 2),
                        "error": resp.error or "DB check returned failure",
                    }

            # Fallback: try a direct DB query
            try:
                from sqlalchemy import select, text

                from app.database import AsyncSessionLocal
            except ImportError:
                return {
                    "status": "unknown",
                    "latency_ms": 0,
                    "error": "database module not available",
                }

            async with AsyncSessionLocal() as db:
                result = await db.execute(text("SELECT 1"))
                row = result.scalar_one()
                elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
                if row == 1:
                    return {"status": "ok", "latency_ms": round(elapsed, 2)}
                return {
                    "status": "error",
                    "latency_ms": round(elapsed, 2),
                    "error": f"Unexpected result: {row}",
                }

        except Exception as exc:
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            logger.warning("DB health check failed: %s", exc)
            return {
                "status": "error",
                "latency_ms": round(elapsed, 2),
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def _check_redis(self) -> dict[str, Any]:
        """Check Redis connectivity via ping.

        Returns:
            Dict with status, latency_ms, and optional error.
        """
        start = datetime.now(UTC)

        # Try Redis via broker if available
        if self.broker is not None:
            try:
                from app.broker.interfaces import ServiceRequest

                resp = await self.broker.call(
                    ServiceRequest(
                        service="cache",
                        method="ping",
                        timeout_ms=5_000,
                    )
                )
                elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
                if resp.success:
                    return {"status": "ok", "latency_ms": round(elapsed, 2)}
                return {
                    "status": "error",
                    "latency_ms": round(elapsed, 2),
                    "error": resp.error or "Redis ping failed",
                }
            except Exception as exc:
                elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
                return {
                    "status": "error",
                    "latency_ms": round(elapsed, 2),
                    "error": f"{type(exc).__name__}: {exc}",
                }

        # Fallback: try importing redis directly
        try:
            import redis.asyncio as aioredis

            from app.config import settings

            r = aioredis.Redis.from_url(
                getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=3,
            )
            pong = await r.ping()
            await r.aclose()
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            if pong:
                return {"status": "ok", "latency_ms": round(elapsed, 2)}
            return {
                "status": "error",
                "latency_ms": round(elapsed, 2),
                "error": "Redis ping returned False",
            }
        except ImportError:
            # Redis library not installed — mark as unavailable
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            return {
                "status": "unavailable",
                "latency_ms": round(elapsed, 2),
                "error": "redis library not installed",
            }
        except Exception as exc:
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            return {
                "status": "error",
                "latency_ms": round(elapsed, 2),
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def _check_ai_gateway(self) -> dict[str, Any]:
        """Check AI Gateway responsiveness with a minimal chat call.

        Returns:
            Dict with status, latency_ms, and optional error.
        """
        start = datetime.now(UTC)
        try:
            from app.ai.gateway.interfaces import AIRequest

            if self.brain is not None and hasattr(self.brain, "_backend"):
                gateway = getattr(self.brain._backend, "gateway", None)
                if gateway is not None and hasattr(gateway, "chat"):
                    resp = await gateway.chat(
                        AIRequest(
                            model="deepseek-chat",
                            messages=[{"role": "user", "content": "ping"}],
                            max_tokens=5,
                        )
                    )
                    elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
                    if resp.content and resp.finish_reason != "error":
                        return {"status": "ok", "latency_ms": round(elapsed, 2)}
                    return {
                        "status": "error",
                        "latency_ms": round(elapsed, 2),
                        "error": f"Gateway returned error: {resp.content[:100]}",
                    }

            # Try broker-based gateway call
            if self.broker is not None:
                from app.broker.interfaces import ServiceRequest

                resp = await self.broker.call(
                    ServiceRequest(
                        service="ai_gateway",
                        method="chat",
                        params={
                            "messages": [{"role": "user", "content": "ping"}],
                            "max_tokens": 5,
                        },
                        timeout_ms=30_000,
                    )
                )
                elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
                if resp.success:
                    return {"status": "ok", "latency_ms": round(elapsed, 2)}
                return {
                    "status": "error",
                    "latency_ms": round(elapsed, 2),
                    "error": resp.error or "AI Gateway call failed",
                }

            # No gateway available
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            return {
                "status": "unavailable",
                "latency_ms": round(elapsed, 2),
                "error": "AI Gateway not accessible",
            }

        except Exception as exc:
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            logger.warning("AI Gateway health check failed: %s", exc)
            return {
                "status": "error",
                "latency_ms": round(elapsed, 2),
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def _check_flywheel(self) -> dict[str, Any]:
        """Check Gaia Flywheel operational status.

        Returns:
            Dict with status, latency_ms, and optional stats.
        """
        start = datetime.now(UTC)
        try:
            from app.ai.gaia_flywheel import get_flywheel

            flywheel = get_flywheel()
            stats = flywheel.get_stats()
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000

            # Determine flywheel health
            if stats.get("cycle_count", 0) > 0:
                return {
                    "status": "ok",
                    "latency_ms": round(elapsed, 2),
                    "stats": stats,
                }

            return {
                "status": "ok",
                "latency_ms": round(elapsed, 2),
                "stats": stats,
                "note": "flywheel initialized, no cycles yet",
            }

        except Exception as exc:
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            logger.warning("Flywheel health check failed: %s", exc)
            return {
                "status": "error",
                "latency_ms": round(elapsed, 2),
                "error": f"{type(exc).__name__}: {exc}",
            }

    # ── Auto-Remediation ──────────────────────────────────────────────

    async def auto_remediate(self, checks: dict[str, Any]) -> dict[str, Any]:
        """Attempt to auto-remediate common issues found in health checks.

        Args:
            checks: The full health check result dict.

        Returns:
            Dict with remediation actions taken and their outcomes.
        """
        actions: list[dict[str, Any]] = []
        check_results = checks.get("checks", checks)

        # DB connection issue → log + alert
        db_status = check_results.get("database", {}).get("status", "")
        if db_status == "error":
            db_error = check_results.get("database", {}).get("error", "unknown")
            action = {
                "component": "database",
                "issue": db_error,
                "action_taken": "logged_and_alerted",
                "recommendation": "Check database connection pool and credentials",
            }
            actions.append(action)
            logger.warning("SRE auto-remediation: DB issue detected — %s", db_error)

            # Feed to brain for learning
            await self.learn(
                observation=f"Database health check failed: {db_error}",
                metadata={
                    "component": "database",
                    "severity": "high",
                    "action": "alerted",
                },
            )

        # High latency → report to gaia brain
        latency_level = checks.get("latency_level", "low")
        if latency_level == "high":
            action = {
                "component": "system",
                "issue": f"High latency detected: {checks.get('max_latency_ms', 0)}ms",
                "action_taken": "reported_to_gaia_brain",
                "recommendation": "Investigate slow queries, add caching, scale resources",
            }
            actions.append(action)
            logger.warning(
                "SRE auto-remediation: High latency (%dms) reported to brain",
                checks.get("max_latency_ms", 0),
            )

            await self.learn(
                observation=(
                    f"System-wide high latency: {checks.get('max_latency_ms', 0)}ms. "
                    f"DB={check_results.get('database', {}).get('latency_ms', 0)}ms, "
                    f"Redis={check_results.get('redis', {}).get('latency_ms', 0)}ms, "
                    f"Gateway={check_results.get('ai_gateway', {}).get('latency_ms', 0)}ms"
                ),
                metadata={
                    "component": "latency",
                    "severity": "medium",
                    "max_latency_ms": checks.get("max_latency_ms", 0),
                    "action": "reported",
                },
            )

        # Flywheel stuck → suggest restart
        flywheel_status = check_results.get("flywheel", {})
        if flywheel_status.get("status") == "error":
            action = {
                "component": "flywheel",
                "issue": flywheel_status.get("error", "unknown"),
                "action_taken": "suggested_restart",
                "recommendation": "Restart Gaia Flywheel service",
            }
            actions.append(action)
            logger.warning("SRE auto-remediation: Flywheel error — restart suggested")

            await self.learn(
                observation=f"Flywheel health check failed: {flywheel_status.get('error', 'unknown')}",
                metadata={
                    "component": "flywheel",
                    "severity": "high",
                    "action": "restart_suggested",
                },
            )

        # Redis unavailable → log
        redis_status = check_results.get("redis", {}).get("status", "")
        if redis_status == "unavailable":
            actions.append(
                {
                    "component": "redis",
                    "issue": "Redis library not installed or unavailable",
                    "action_taken": "noted",
                    "recommendation": "Install redis-py or check Redis connection config",
                }
            )

        # Gateway unavailable → log
        gateway_status = check_results.get("ai_gateway", {}).get("status", "")
        if gateway_status == "unavailable":
            actions.append(
                {
                    "component": "ai_gateway",
                    "issue": "AI Gateway not directly accessible",
                    "action_taken": "noted",
                    "recommendation": "Configure AI Gateway connection in settings",
                }
            )

        # Publish remediation event
        if actions and self.event_bus is not None:
            try:
                from app.events.interfaces import Event

                await self.event_bus.publish(
                    Event(
                        type="infra.remediation_executed",
                        source=self.agent_id,
                        payload={
                            "actions": actions,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                )
            except Exception:
                logger.warning("SREAgent failed to publish remediation event")

        result = {
            "actions_taken": len(actions),
            "actions": actions,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        logger.info("SRE auto-remediation: %d actions taken", len(actions))
        return result

    # ── Capacity Forecasting ──────────────────────────────────────────

    async def capacity_forecast(self) -> dict[str, Any]:
        """Analyze trends from Gaia knowledge to forecast capacity needs.

        Queries the brain for recent infrastructure observations and
        produces a capacity forecast report.

        Returns:
            Dict with trend analysis and capacity recommendations.
        """
        logger.info("SREAgent running capacity forecast...")

        # Query brain for infrastructure trends
        trends = await self.ask_brain(
            query="Infrastructure performance trends, latency patterns, resource usage",
            top_k=20,
        )

        # Analyze health history for trends
        recent_checks = self._health_history[-50:] if len(self._health_history) > 50 else self._health_history
        error_count = sum(1 for c in recent_checks if c.get("overall") == "error")
        degraded_count = sum(1 for c in recent_checks if c.get("overall") == "degraded")
        high_latency_count = sum(1 for c in recent_checks if c.get("latency_level") == "high")
        total_checks = len(recent_checks) or 1

        # Compute trends
        reliability_pct = round((1 - (error_count + degraded_count) / total_checks) * 100, 2)
        latency_issue_rate = round(high_latency_count / total_checks * 100, 2)

        forecast: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "reliability_percentage": reliability_pct,
            "latency_issue_rate_percentage": latency_issue_rate,
            "total_observations": len(trends),
            "recent_checks_analyzed": total_checks,
            "error_count": error_count,
            "degraded_count": degraded_count,
            "high_latency_count": high_latency_count,
            "recommendations": [],
            "trend_insights": [],
        }

        # Generate recommendations based on analysis
        if reliability_pct < 95:
            forecast["recommendations"].append(
                "CRITICAL: System reliability below 95%. Investigate root causes of failures."
            )
        if latency_issue_rate > 10:
            forecast["recommendations"].append(
                f"High latency detected in {latency_issue_rate}% of recent checks. "
                "Consider scaling infrastructure or optimizing queries."
            )
        if error_count > 10:
            forecast["recommendations"].append(
                f"{error_count} errors in last {total_checks} checks. Review database and gateway connections."
            )

        if not forecast["recommendations"]:
            forecast["recommendations"].append("System health is stable. Continue monitoring.")

        # Extract insights from brain knowledge
        for t in trends[:5]:
            if isinstance(t, dict):
                content = t.get("content", t.get("title", str(t)))
                forecast["trend_insights"].append(content[:200])

        # Learn the forecast
        await self.learn(
            observation=(
                f"Capacity forecast: reliability={reliability_pct}%, "
                f"latency_issues={latency_issue_rate}%, "
                f"recommendations={len(forecast['recommendations'])}"
            ),
            metadata={
                "report_type": "capacity_forecast",
                "reliability": reliability_pct,
                "latency_issue_rate": latency_issue_rate,
                "recommendations": forecast["recommendations"],
            },
        )

        logger.info(
            "Capacity forecast: reliability=%s%%, latency_issues=%s%%",
            reliability_pct,
            latency_issue_rate,
        )
        return forecast

    # ── Incident Response ─────────────────────────────────────────────

    async def incident_response(self, event: Any) -> None:
        """Respond to a critical metrics alert by creating an incident record.

        Args:
            event: The triggering event (should have type, payload, source).
        """
        event_type = getattr(event, "type", "unknown")
        event_payload = getattr(event, "payload", {})
        event_source = getattr(event, "source", "unknown")

        logger.warning(
            "SREAgent responding to critical incident: type=%s, source=%s",
            event_type,
            event_source,
        )

        # Create incident record in brain
        incident_id = f"inc_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{self.agent_id[:4]}"

        await self.learn(
            observation=(
                f"CRITICAL INCIDENT: {incident_id}. Event: {event_type} from {event_source}. Payload: {event_payload}"
            ),
            metadata={
                "incident_id": incident_id,
                "event_type": event_type,
                "event_source": event_source,
                "severity": "critical",
                "status": "open",
            },
        )

        # Publish incident event
        if self.event_bus is not None:
            try:
                from app.events.interfaces import Event, EventPriority

                await self.event_bus.publish(
                    Event(
                        type="infra.incident_created",
                        source=self.agent_id,
                        payload={
                            "incident_id": incident_id,
                            "event_type": event_type,
                            "event_source": event_source,
                            "severity": "critical",
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                        priority=EventPriority.CRITICAL,
                    )
                )
            except Exception:
                logger.warning("SREAgent failed to publish incident event")

        # Run a health check immediately
        health = await self.health_check()
        logger.info(
            "Incident %s — post-incident health: %s",
            incident_id,
            health.get("overall"),
        )

    # ── Additional event handlers ─────────────────────────────────────

    async def _handle_service_down(self, event: Any) -> None:
        """Handle infra.service_down events."""
        payload = getattr(event, "payload", {})
        service = payload.get("service", "unknown")
        logger.error("Service down detected: %s", service)

        await self.learn(
            observation=f"Service down: {service}. Initiating recovery procedures.",
            metadata={"event": "service_down", "service": service, "severity": "critical"},
        )

        # Run health check to assess full impact
        await self.health_check()

    async def _handle_high_latency(self, event: Any) -> None:
        """Handle infra.high_latency events."""
        payload = getattr(event, "payload", {})
        component = payload.get("component", "unknown")
        latency = payload.get("latency_ms", 0)
        logger.warning("High latency on %s: %dms", component, latency)

        await self.learn(
            observation=f"High latency on {component}: {latency}ms",
            metadata={
                "event": "high_latency",
                "component": component,
                "latency_ms": latency,
                "severity": "medium",
            },
        )

    # ── Public API ────────────────────────────────────────────────────

    async def get_status_summary(self) -> dict[str, Any]:
        """Return a human-readable status summary for this SRE agent.

        Returns:
            Dict with agent name, status, last health check, and uptime hints.
        """
        last_check = self._health_history[-1] if self._health_history else None
        return {
            "agent": self.agent_name,
            "role": self.agent_role,
            "status": self.status.value,
            "last_health_check": last_check,
            "total_checks_performed": len(self._health_history),
        }
