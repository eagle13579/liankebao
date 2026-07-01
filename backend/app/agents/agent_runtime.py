"""AgentRuntime — Agent Runtime Engine for managing AI Digital Employees.

The runtime is the orchestrator that manages the lifecycle of all AI
employees. It handles:
    - Agent registration and lifecycle (start/stop)
    - Cron job scheduling and execution
    - Event routing via EventBusProtocol
    - Status aggregation and reporting

Singleton — one runtime per process.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import AgentStatus, BaseAgent, CronJob

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Singleton runtime engine that manages all AI Digital Employees.

    Usage:
        runtime = AgentRuntime()
        await runtime.register(sre_agent)
        await runtime.register(support_agent)
        await runtime.start()

        # ... application runs ...

        await runtime.stop()

    Attributes:
        agents: Dict of agent_name → BaseAgent instance.
        event_bus: The event bus used for inter-agent communication.
        broker: The service broker for cross-service calls.
    """

    _instance: AgentRuntime | None = None
    _instance_lock = asyncio.Lock()

    def __init__(
        self,
        event_bus: Any | None = None,
        broker: Any | None = None,
    ) -> None:
        """Initialize the runtime.

        Args:
            event_bus: EventBusProtocol instance for event routing.
            broker: ServiceBrokerProtocol instance for service calls.
        """
        self.agents: dict[str, BaseAgent] = {}
        self.event_bus: Any | None = event_bus
        self.broker: Any | None = broker

        self._running = False
        self._scheduler_task: asyncio.Task[None] | None = None
        self._event_listener_task: asyncio.Task[None] | None = None
        self._start_time: datetime | None = None

    @classmethod
    async def get_instance(
        cls,
        event_bus: Any | None = None,
        broker: Any | None = None,
    ) -> AgentRuntime:
        """Get or create the singleton AgentRuntime instance.

        Args:
            event_bus: Event bus to use for a new instance (ignored if exists).
            broker: Service broker to use for a new instance (ignored if exists).

        Returns:
            The shared AgentRuntime singleton.
        """
        async with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(event_bus=event_bus, broker=broker)
            return cls._instance

    # ── Agent Registration ────────────────────────────────────────────

    async def register(self, agent: BaseAgent) -> None:
        """Register an AI employee agent.

        If the runtime is already running, the agent's lifecycle
        is started immediately. Otherwise, it will be started when
        start() is called.

        Args:
            agent: A BaseAgent subclass instance.

        Raises:
            ValueError: If an agent with the same name is already registered.
        """
        if agent.agent_name in self.agents:
            raise ValueError(f"Agent '{agent.agent_name}' is already registered")

        self.agents[agent.agent_name] = agent
        logger.info(
            "Agent registered: '%s' (%s) — role=%s",
            agent.agent_name,
            agent.agent_id[:8],
            agent.agent_role,
        )

        # If runtime is already running, start the agent immediately
        if self._running:
            await agent.start()
            logger.info(
                "Agent '%s' started immediately on registration",
                agent.agent_name,
            )

    async def unregister(self, agent_name: str) -> bool:
        """Unregister and stop an agent.

        Args:
            agent_name: Name of the agent to remove.

        Returns:
            True if the agent was found and removed, False otherwise.
        """
        agent = self.agents.pop(agent_name, None)
        if agent is None:
            logger.warning("Agent '%s' not found for unregistration", agent_name)
            return False

        try:
            await agent.stop()
            logger.info("Agent '%s' unregistered and stopped", agent_name)
        except Exception:
            logger.exception("Error stopping agent '%s' during unregister", agent_name)

        return True

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the runtime and all registered agents.

        Flow:
            1. Start event listener loop (if event_bus is configured)
            2. Start cron scheduler loop
            3. Start all registered agents
            4. Subscribe runtime to system events
        """
        if self._running:
            logger.warning("AgentRuntime is already running")
            return

        self._running = True
        self._start_time = datetime.now(UTC)
        logger.info("AgentRuntime starting...")

        # Step 1: Start background loops
        self._event_listener_task = asyncio.create_task(
            self._event_listener_loop(),
            name="runtime-event-listener",
        )
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(),
            name="runtime-scheduler",
        )

        # Step 2: Subscribe to system events via event bus
        if self.event_bus is not None:
            try:
                await self.event_bus.subscribe(
                    "runtime.*",
                    self._handle_runtime_event,
                    description="AgentRuntime system event handler",
                )
                await self.event_bus.subscribe(
                    "support.ticket_escalated",
                    self._handle_escalation,
                    description="AgentRuntime escalation handler",
                )
            except Exception as exc:
                logger.warning("Failed to subscribe to event bus: %s", exc)

        # Step 3: Start all registered agents
        start_tasks = []
        for name, agent in self.agents.items():
            start_tasks.append(self._start_agent(agent))

        if start_tasks:
            results = await asyncio.gather(*start_tasks, return_exceptions=True)
            for name, result in zip(self.agents.keys(), results):
                if isinstance(result, Exception):
                    logger.error(
                        "Agent '%s' failed to start: %s",
                        name,
                        result,
                    )

        # Step 4: Publish runtime started event
        if self.event_bus is not None:
            try:
                from app.events.interfaces import Event

                await self.event_bus.publish(
                    Event(
                        type="runtime.started",
                        source="agent_runtime",
                        payload={
                            "agent_count": len(self.agents),
                            "agents": list(self.agents.keys()),
                            "timestamp": self._start_time.isoformat(),
                        },
                    )
                )
            except Exception:
                logger.warning("Failed to publish runtime.started event")

        started = sum(1 for a in self.agents.values() if a.status == AgentStatus.IDLE)
        logger.info(
            "AgentRuntime started: %d/%d agents running",
            started,
            len(self.agents),
        )

    async def stop(self) -> None:
        """Gracefully stop the runtime and all agents.

        Flow:
            1. Stop cron scheduler loop
            2. Stop event listener loop
            3. Stop all agents
            4. Unsubscribe from event bus
        """
        if not self._running:
            logger.warning("AgentRuntime is not running")
            return

        logger.info("AgentRuntime stopping...")

        # Step 1: Stop background loops
        self._running = False

        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None

        if self._event_listener_task is not None:
            self._event_listener_task.cancel()
            try:
                await self._event_listener_task
            except asyncio.CancelledError:
                pass
            self._event_listener_task = None

        # Step 2: Stop all agents (in reverse order)
        for name in reversed(list(self.agents.keys())):
            agent = self.agents[name]
            try:
                await agent.stop()
                logger.debug("Agent '%s' stopped", name)
            except Exception:
                logger.exception("Error stopping agent '%s'", name)

        # Step 3: Unsubscribe from event bus
        if self.event_bus is not None:
            try:
                await self.event_bus.unsubscribe("runtime.*", self._handle_runtime_event)
                await self.event_bus.unsubscribe(
                    "support.ticket_escalated",
                    self._handle_escalation,
                )
            except Exception:
                logger.warning("Failed to unsubscribe from event bus")

        uptime = (datetime.now(UTC) - self._start_time).total_seconds() if self._start_time else 0
        logger.info(
            "AgentRuntime stopped (uptime=%.1fs, agents=%d)",
            uptime,
            len(self.agents),
        )

    async def _start_agent(self, agent: BaseAgent) -> None:
        """Start a single agent with error handling.

        Args:
            agent: The agent to start.
        """
        try:
            await agent.start()
            logger.info("Agent '%s' started (status=%s)", agent.agent_name, agent.status.value)
        except Exception:
            logger.exception("Agent '%s' failed to start", agent.agent_name)
            raise

    # ── Agent Access ──────────────────────────────────────────────────

    def get_agent(self, name: str) -> BaseAgent | None:
        """Retrieve a registered agent by name.

        Args:
            name: The agent's name (agent_name).

        Returns:
            The agent if found, None otherwise.
        """
        return self.agents.get(name)

    def get_agents(self) -> dict[str, BaseAgent]:
        """Return a copy of the agents dict.

        Returns:
            Dict of agent_name → BaseAgent.
        """
        return dict(self.agents)

    async def get_status(self) -> dict[str, Any]:
        """Return the status of all agents and the runtime itself.

        Returns:
            Dict with runtime info and per-agent status.
        """
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(UTC) - self._start_time).total_seconds()

        agent_statuses: dict[str, Any] = {}
        for name, agent in self.agents.items():
            agent_statuses[name] = {
                "name": agent.agent_name,
                "id": agent.agent_id[:12],
                "role": agent.agent_role,
                "status": agent.status.value,
                "is_available": agent.is_available,
                "active_tasks": agent._active_tasks,
                "max_concurrent": agent.config.max_concurrent_tasks,
                "tool_count": len(agent.tools),
                "event_handler_count": sum(len(h) for h in agent.event_handlers.values()),
                "cron_job_count": len(agent.cron_jobs),
                "memory_experience_count": agent.memory.get("experience_count", 0),
            }

        return {
            "runtime": {
                "running": self._running,
                "uptime_seconds": round(uptime, 2),
                "start_time": (self._start_time.isoformat() if self._start_time else None),
                "agent_count": len(self.agents),
                "event_bus_connected": self.event_bus is not None,
                "broker_connected": self.broker is not None,
            },
            "agents": agent_statuses,
        }

    # ── Event Dispatch ────────────────────────────────────────────────

    async def dispatch_event(self, event: Any) -> None:
        """Dispatch an event to all subscribed agents.

        Each agent's handle_event() is called concurrently.
        If an event bus is configured, the event is also published
        through it for external subscribers.

        Args:
            event: The event to dispatch (Event dataclass or compatible).
        """
        # Publish via event bus if available
        if self.event_bus is not None:
            try:
                await self.event_bus.publish(event)
            except Exception:
                logger.warning("Failed to publish event via bus: %s", getattr(event, "type", "unknown"))

        # Deliver to all agents concurrently
        tasks = []
        for agent in self.agents.values():
            tasks.append(self._deliver_to_agent(agent, event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver_to_agent(
        self,
        agent: BaseAgent,
        event: Any,
    ) -> None:
        """Deliver an event to a single agent, handling errors gracefully.

        Args:
            agent: The target agent.
            event: The event to deliver.
        """
        try:
            await agent.handle_event(event)
        except Exception:
            logger.exception(
                "Error delivering event to agent '%s'",
                agent.agent_name,
            )

    # ── Cron Scheduling ───────────────────────────────────────────────

    async def run_cron_cycle(self) -> None:
        """Check all agents' cron schedules and execute due jobs.

        This method uses a simple interval-based approach:
        - Runs every 30 seconds (via _scheduler_loop)
        - Checks if each cron job's schedule matches the current time
        - Executes due jobs concurrently
        """
        now = datetime.now(UTC)
        tasks = []

        for agent in self.agents.values():
            for job in agent.cron_jobs:
                if not job.enabled:
                    continue
                if self._is_job_due(job, now):
                    tasks.append(self._execute_cron_job(agent, job))

        if tasks:
            logger.debug("Running %d cron jobs across %d agents", len(tasks), len(self.agents))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_cron_job(
        self,
        agent: BaseAgent,
        job: CronJob,
    ) -> None:
        """Execute a single cron job for a specific agent.

        Args:
            agent: The agent that owns the cron job.
            job: The cron job to execute.
        """
        try:
            await agent.run_cron(job)
            logger.debug(
                "Cron job '%s' executed for agent '%s'",
                job.name or job.schedule,
                agent.agent_name,
            )
        except Exception:
            logger.exception(
                "Cron job '%s' failed for agent '%s'",
                job.name or job.schedule,
                agent.agent_name,
            )

    @staticmethod
    def _is_job_due(job: CronJob, now: datetime) -> bool:
        """Check if a cron job is due at the current time.

        Uses a simplified scheduling check:
        - Supports: */5 * * * * (every N minutes)
          */30 * * * * (every N minutes on the :00)
        - Checks if current minute matches the schedule pattern.

        Args:
            job: The cron job to check.
            now: The current datetime.

        Returns:
            True if the job is due for execution.
        """
        schedule = job.schedule.strip()
        parts = schedule.split()

        if len(parts) != 5:
            logger.warning("Invalid cron expression: %s", schedule)
            return False

        minute_pattern = parts[0]
        hour_pattern = parts[1]

        # Check minute pattern: */N or exact minute
        if minute_pattern.startswith("*/"):
            try:
                interval = int(minute_pattern[2:])
                if now.minute % interval != 0:
                    return False
            except ValueError:
                return False
        elif minute_pattern != "*":
            try:
                if now.minute != int(minute_pattern):
                    return False
            except ValueError:
                return False

        # Check hour pattern: */N or exact hour
        if hour_pattern.startswith("*/"):
            try:
                interval = int(hour_pattern[2:])
                if now.hour % interval != 0:
                    return False
            except ValueError:
                return False
        elif hour_pattern != "*":
            try:
                if now.hour != int(hour_pattern):
                    return False
            except ValueError:
                return False

        return True

    # ── Background Loops ──────────────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        """Background loop: checks cron schedules every 30 seconds.

        This loop runs as long as the runtime is active.
        It calls run_cron_cycle() periodically to execute due jobs.
        """
        logger.info("Cron scheduler loop started (interval=30s)")

        while self._running:
            try:
                await asyncio.sleep(30)
                if self._running:
                    await self.run_cron_cycle()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in cron scheduler loop")

        logger.info("Cron scheduler loop stopped")

    async def _event_listener_loop(self) -> None:
        """Background loop: listens for events from the event bus.

        This loop runs as long as the runtime is active.
        For in-process event buses, this is handled via subscriptions.
        For distributed buses, this polls or listens for messages.
        """
        logger.info("Event listener loop started")

        # For now, the event listener loop maintains the subscription
        # and handles any bus-level processing needed.
        # Actual event delivery is handled by the event bus's consumer loop
        # and the runtime's dispatch_event() method.

        while self._running:
            try:
                await asyncio.sleep(60)
                # Periodically log queue health if event bus supports it
                if self.event_bus is not None and hasattr(self.event_bus, "queue_size"):
                    qsize = self.event_bus.queue_size
                    if qsize > 100:
                        logger.info("Event bus queue size: %d", qsize)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in event listener loop")

        logger.info("Event listener loop stopped")

    # ── Event Handlers for Runtime Events ────────────────────────────

    async def _handle_runtime_event(self, event: Any) -> None:
        """Handle runtime.* events from the event bus.

        Args:
            event: The runtime event to handle.
        """
        event_type = getattr(event, "type", "runtime.unknown")
        payload = getattr(event, "payload", {})

        logger.debug("Runtime received system event: %s", event_type)

        if event_type == "runtime.health_check":
            # Respond with current runtime status
            if self.event_bus is not None:
                try:
                    from app.events.interfaces import Event

                    status = await self.get_status()
                    await self.event_bus.publish(
                        Event(
                            type="runtime.health_report",
                            source="agent_runtime",
                            payload=status,
                        )
                    )
                except Exception:
                    logger.warning("Failed to publish health report")

    async def _handle_escalation(self, event: Any) -> None:
        """Handle support.ticket_escalated events for routing.

        Args:
            event: The escalation event.
        """
        payload = getattr(event, "payload", {})
        escalation_id = payload.get("escalation_id", "unknown")
        logger.info(
            "Runtime routing escalation %s to available human support",
            escalation_id,
        )

        # Record the escalation in runtime tracking
        await self._log_escalation(payload)

    async def _log_escalation(self, payload: dict[str, Any]) -> None:
        """Log an escalation for tracking purposes.

        Args:
            payload: The escalation payload.
        """
        logger.debug(
            "Escalation tracked: id=%s, ticket=%s, user=%s",
            payload.get("escalation_id"),
            payload.get("ticket_id"),
            payload.get("user_id"),
        )

    # ── Utility ───────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Whether the runtime is currently active."""
        return self._running

    def __repr__(self) -> str:
        return (
            f"<AgentRuntime running={self._running} "
            f"agents={len(self.agents)} "
            f"event_bus={'yes' if self.event_bus else 'no'}>"
        )
