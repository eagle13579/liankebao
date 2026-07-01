"""Agent Scheduling Rules — What each AI employee does, and on what schedule.

Each rule binds an agent to a cron expression (recurring interval) or an
event type pattern (reactive trigger). The rules are loaded by the Agent
Runtime's scheduler subsystem and the event bus's subscription system.

Architecture:
    - Cron rules: periodic tasks executed by AgentRuntime.run_cron_cycle()
    - Event rules: reactive tasks triggered by EventBus events
    - Installation happens once at startup via install_scheduler_rules()

Master schedule (9 employees × their beats):

    Agent           │ Cron (periodic)                │ Event (reactive)
    ────────────────┼────────────────────────────────┼──────────────────────
    SREAgent        │ health_check     ─ ─5 min     │ — none (polling)
                    │ capacity_forecast ─30 min      │
    SupportAgent    │ — none                        │ support.ticket_created
    BackendAgent    │ code_review      ─ ─60 min    │ code.review_requested
    QAAgent         │ regression_check ─60 min      │ code.review_completed
    SecurityAgent   │ compliance_scan  ─ ──4 h      │ deploy.staging
    GrowthAgent     │ ab_test_analysis ─ ──24 h     │ — none (daily sweep)
    KnowledgeAgent  │ knowledge_sync   ─ ──24 h     │ deploy.production
    ArchitectureAgent│ system_review   ─ ──24 h     │ schema.change_needed
    DataAgent       │ data_quality     ─ ──30 min   │ schema.change_needed
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base_agent import CronJob

logger = logging.getLogger(__name__)

# ======================================================================
# Cron Schedule Definitions
# ======================================================================
#
# Format: standard cron "minute hour day month day-of-week"
#   */N  = every N minutes
#   N    = at minute N of the hour
#   *    = every


async def _noop_action() -> dict[str, Any]:
    """Placeholder action until the real agent tool is wired."""
    return {"status": "noop", "message": "Action not yet wired to agent tool"}


def _get_agent_jobs() -> dict[str, list[CronJob]]:
    """Return the cron jobs for each agent type.

    Each entry maps agent_type → list[CronJob].
    Jobs are registered with the agent's run_cron() method at startup.

    Returns:
        Dict: agent_type → [CronJob, ...]
    """
    return {
        # ── SREAgent: Health checks every 5 min, capacity planning every 30 ──
        "sre": [
            CronJob(
                name="health_check",
                schedule="*/5 * * * *",
                action=_noop_action,
                enabled=True,
            ),
            CronJob(
                name="capacity_forecast",
                schedule="*/30 * * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
        # ── SupportAgent: Event-driven only, no cron ═────────────────────────
        "support": [],
        # ── BackendAgent: Code review every 60 min ────────────────────────────
        "backend": [
            CronJob(
                name="code_review",
                schedule="0 * * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
        # ── QAAgent: Regression checks every 60 min ──────────────────────────
        "qa": [
            CronJob(
                name="regression_check",
                schedule="30 * * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
        # ── SecurityAgent: Compliance scan every 4 hours ─────────────────────
        "security": [
            CronJob(
                name="compliance_scan",
                schedule="0 */4 * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
        # ── GrowthAgent: A/B test analysis every 24 hours ────────────────────
        "growth": [
            CronJob(
                name="ab_test_analysis",
                schedule="0 6 * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
        # ── KnowledgeAgent: Knowledge base sync every 24 hours ───────────────
        "knowledge": [
            CronJob(
                name="knowledge_sync",
                schedule="0 4 * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
        # ── ArchitectureAgent: System architecture review every 24 hours ─────
        "architecture": [
            CronJob(
                name="system_review",
                schedule="0 3 * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
        # ── DataAgent: Data quality checks every 30 min ──────────────────────
        "data": [
            CronJob(
                name="data_quality",
                schedule="*/30 * * * *",
                action=_noop_action,
                enabled=True,
            ),
        ],
    }


# ======================================================================
# Event Subscription Rules
# ======================================================================


def get_event_rules() -> dict[str, list[str]]:
    """Return the event subscription rules for each agent type.

    Maps agent_type → list of event type patterns the agent should
    subscribe to.

    Returns:
        Dict: agent_type → [event_type_pattern, ...]
    """
    return {
        "support": [
            "support.ticket_created",
            "support.ticket_escalated",
        ],
        "backend": [
            "code.review_requested",
        ],
        "qa": [
            "code.review_completed",
        ],
        "security": [
            "deploy.staging",
            "security.vulnerability_found",
        ],
        "growth": [
            "analytics.ab_test_ready",
        ],
        "knowledge": [
            "deploy.production",
            "knowledge.doc_requested",
        ],
        "architecture": [
            "schema.change_needed",
            "architecture.design_review_requested",
        ],
        "data": [
            "schema.change_needed",
            "data.quality_alert",
        ],
        "sre": [],  # SRE is polling-based, no event subscriptions
    }


# ======================================================================
# Rule Summary (for reporting / debugging)
# ======================================================================


def get_all_rules_summary() -> dict[str, Any]:
    """Get a human-readable summary of all scheduling rules.

    Returns:
        Dict with cron and event rules for each agent type.
    """
    cron_jobs = _get_agent_jobs()
    event_rules = get_event_rules()

    summary: dict[str, Any] = {}
    for agent_type in sorted(cron_jobs.keys()):
        jobs = cron_jobs.get(agent_type, [])
        events = event_rules.get(agent_type, [])
        summary[agent_type] = {
            "cron_jobs": [
                {
                    "name": j.name or j.schedule,
                    "schedule": j.schedule,
                    "enabled": j.enabled,
                }
                for j in jobs
            ],
            "event_subscriptions": [e for e in events],
        }

    return summary


# ======================================================================
# Installation — called at Agent Runtime startup
# ======================================================================


async def install_scheduler_rules() -> None:
    """Install all scheduling rules into the Agent Runtime.

    This function:
        1. Gets the Agent Runtime singleton
        2. For each registered agent, adds its cron jobs
        3. Subscribes each agent to its configured event patterns
        4. Logs the final rule set

    Called by start_agents.py during the startup sequence.
    """
    try:
        from app.dependencies import get_agent_runtime

        runtime = get_agent_runtime()
    except Exception as exc:
        logger.error("Cannot install scheduler rules — runtime unavailable: %s", exc)
        return

    cron_jobs = _get_agent_jobs()
    event_rules = get_event_rules()

    installed_cron = 0
    installed_events = 0

    for agent_name, agent in runtime.agents.items():
        # Map agent_name back to agent_type (agent_name looks like "sre_emp-䑏疏")
        agent_type = agent_name.split("_")[0] if "_" in agent_name else agent_name

        # ── Install cron jobs ─────────────────────────────────────────
        jobs = cron_jobs.get(agent_type, [])
        for job in jobs:
            # Replace the noop action with a real call to the agent's run_cron
            real_job = CronJob(
                schedule=job.schedule,
                action=lambda a=agent, j=job: a.run_cron(j),  # type: ignore[misc]
                name=job.name,
                enabled=job.enabled,
            )
            agent.cron_jobs.append(real_job)
            logger.debug(
                "  [cron] %s ← %s (%s)",
                agent_name,
                job.name or "unnamed",
                job.schedule,
            )
            installed_cron += 1

        # ── Install event subscriptions ───────────────────────────────
        events = event_rules.get(agent_type, [])
        for event_pattern in events:
            if runtime.event_bus is not None:
                try:
                    await runtime.event_bus.subscribe(
                        event_pattern,
                        agent.handle_event,
                        description=f"{agent_name} handles {event_pattern}",
                    )
                    logger.debug(
                        "  [event] %s ← %s",
                        agent_name,
                        event_pattern,
                    )
                    installed_events += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to subscribe %s to %s: %s",
                        agent_name,
                        event_pattern,
                        exc,
                    )
            else:
                logger.debug(
                    "  [event] %s ← %s (no event bus — deferred)",
                    agent_name,
                    event_pattern,
                )

    enabled_cron = sum(1 for j in jobs if j.enabled for jobs in cron_jobs.values())
    logger.info(
        "Scheduler rules installed: %d cron jobs, %d event subscriptions "
        "across %d agents",
        installed_cron,
        installed_events,
        len(runtime.agents),
    )
