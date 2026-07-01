"""Base Agent — AI Employee abstract base class.

Architecture principle:
    Every AI employee (agent) inherits from BaseAgent. The base provides:
        - Lifecycle management (init → start → handle_event → run_cron → stop)
        - Gaia Evolution Brain integration for learning and knowledge retrieval
        - Tool registry for pluggable capabilities
        - Event handler registry for reactive behavior
        - Cron job scheduling for proactive behavior
        - Inter-agent delegation for task distribution

    Concrete agents (CopywriterAgent, AnalystAgent, ResearchAgent, etc.)
    override specific methods to define their unique behavior while
    inheriting the full lifecycle and infrastructure.

These contracts are STABLE — they will never change as the agent framework
scales from 3 local agents to 300+ distributed agents across a global mesh.
"""

from __future__ import annotations

import abc
import asyncio
import dataclasses
import enum
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ======================================================================
# Enums & Data Models
# ======================================================================


class AgentStatus(enum.Enum):
    """The current lifecycle state of an AI employee agent.

    INITIALIZING — Agent is being set up (resources are being allocated).
    IDLE         — Agent is ready and waiting for work.
    BUSY         — Agent is actively processing a task or event.
    ERROR        — Agent encountered a non-recoverable error.
    STOPPED      — Agent has been gracefully shut down.
    """

    INITIALIZING = "initializing"
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"


@dataclasses.dataclass
class AgentConfig:
    """Configuration for an AI employee agent.

    Attributes:
        agent_id: Unique identifier for this agent instance.
        agent_name: Human-readable name (e.g. "文案写手", "数据分析师").
        agent_role: Role description (e.g. "文案撰写", "用户行为分析").
        knowledge_base_name: Name of this agent's domain-specific
            knowledge base for RAG queries.
        enabled: Whether the agent starts enabled on initialization.
        max_concurrent_tasks: Maximum tasks this agent can handle simultaneously.
        default_timeout_seconds: Default timeout for task execution.
    """

    agent_id: str = ""
    agent_name: str = "unnamed_agent"
    agent_role: str = "general"
    knowledge_base_name: str = "default"
    enabled: bool = True
    max_concurrent_tasks: int = 5
    default_timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if not self.agent_id:
            self.agent_id = f"agent_{uuid.uuid4().hex[:12]}"
        if self.max_concurrent_tasks < 1:
            raise ValueError(f"max_concurrent_tasks must be >= 1, got {self.max_concurrent_tasks}")


@dataclasses.dataclass
class AgentMessage:
    """A message sent between agents for inter-agent communication.

    Attributes:
        source_id: Agent ID of the sender.
        target_id: Agent ID of the intended recipient (or "broadcast" for all).
        message_type: Type of message (task, response, notification, query).
        payload: Message content (JSON-serializable).
        correlation_id: Links related messages together (e.g., task → response).
        timestamp: When the message was created.
        message_id: Unique identifier for this message.
    """

    source_id: str
    target_id: str
    message_type: str = "task"
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)
    correlation_id: str = ""
    timestamp: datetime = dataclasses.field(default_factory=lambda: datetime.now(UTC))
    message_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)


# ======================================================================
# Type Aliases
# ======================================================================

# A tool is a named async or sync callable that takes **kwargs and returns Any
ToolFunc = Callable[..., Coroutine[Any, Any, Any] | Any]


# A cron job is a schedule expression + the action to execute
@dataclasses.dataclass
class CronJob:
    """A scheduled job that the agent executes on a recurring basis.

    Attributes:
        schedule: Cron expression (e.g. "*/5 * * * *" for every 5 minutes).
        action: Async callable that performs the job.
        name: Human-readable name for logging.
        enabled: Whether this cron job is active.
    """

    schedule: str
    action: Callable[[], Coroutine[Any, Any, Any]]
    name: str = ""
    enabled: bool = True


# ======================================================================
# Base Agent
# ======================================================================


class BaseAgent(abc.ABC):
    """Abstract base class for all AI employee agents.

    Provides a complete lifecycle system, Gaia Brain integration,
    tool/event/cron registries, and inter-agent communication.

    Subclasses must implement:
        - init()       : One-time setup (register tools, subscribe to events)
        - stop()       : Clean up resources (close connections, save state)

    Subclasses MAY override:
        - start()      : Post-init startup logic
        - handle_event(event) : Custom event processing
        - run_cron(job)       : Custom cron job execution

    Usage:
        class CopywriterAgent(BaseAgent):
            async def init(self):
                self.tools["generate_copy"] = self._generate_copy

            async def stop(self):
                await self._save_drafts()

            async def _generate_copy(self, style: str, prompt: str) -> str:
                return await self.ask_brain(f"Write {style} copy: {prompt}")
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        brain: Any | None = None,  # GaiaEvolutionBrain reference
    ):
        self.config: AgentConfig = config or AgentConfig()
        self.brain: Any | None = brain
        self.agent_id: str = self.config.agent_id
        self.agent_name: str = self.config.agent_name
        self.agent_role: str = self.config.agent_role

        # Status lifecycle
        self._status: AgentStatus = AgentStatus.INITIALIZING
        self._active_tasks: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

        # Registries
        self.tools: dict[str, ToolFunc] = {}
        self.event_handlers: dict[str, list[Callable[[Any], Coroutine[Any, Any, None]]]] = {}
        self.cron_jobs: list[CronJob] = []

        # Agent memory — learned patterns and observations
        self.memory: dict[str, Any] = {
            "experience_count": 0,
            "last_learned": None,
            "patterns": [],
            "observations": [],
        }

        logger.info(
            "Agent [%s] '%s' created (role=%s)",
            self.agent_id[:8],
            self.agent_name,
            self.agent_role,
        )

    # ── Properties ─────────────────────────────────────────────────

    @property
    def status(self) -> AgentStatus:
        """Current lifecycle status of the agent."""
        return self._status

    @status.setter
    def status(self, value: AgentStatus) -> None:
        self._status = value
        logger.debug("Agent '%s' status → %s", self.agent_name, value.value)

    @property
    def is_available(self) -> bool:
        """Whether the agent can accept new work."""
        return self._status == AgentStatus.IDLE and self._active_tasks < self.config.max_concurrent_tasks

    # ── Lifecycle ──────────────────────────────────────────────────

    @abc.abstractmethod
    async def init(self) -> None:
        """One-time initialization.

        Override this to:
            - Register tools in self.tools
            - Subscribe to events via self.event_handlers
            - Schedule cron jobs via self.cron_jobs
            - Load agent-specific resources

        This is called during start() before the agent becomes IDLE.
        """
        ...

    async def start(self) -> None:
        """Start the agent lifecycle.

        Flow: INITIALIZING → [init() called] → IDLE
        Called once when the agent is deployed.
        """
        if self._status != AgentStatus.INITIALIZING:
            logger.warning(
                "Agent '%s' start() called but status=%s",
                self.agent_name,
                self._status.value,
            )
            return

        try:
            await self.init()
            self.status = AgentStatus.IDLE
            logger.info("Agent '%s' started successfully", self.agent_name)
        except Exception:
            self.status = AgentStatus.ERROR
            logger.exception("Agent '%s' failed to start", self.agent_name)
            raise

    @abc.abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the agent.

        Override this to:
            - Close network connections (DB, Redis, AI provider)
            - Flush buffered observations to the brain
            - Save agent state/memory to persistent storage
            - Cancel active tasks

        Called once when the agent is being undeployed.
        """
        ...

    async def handle_event(self, event: Any) -> None:
        """Process an incoming event.

        The default implementation dispatches to registered event_handlers.
        Override this to implement custom event routing logic.

        Args:
            event: The event to process (Event dataclass or compatible).
        """
        event_type = getattr(event, "type", None) or getattr(event, "event_type", None)
        if event_type and event_type in self.event_handlers:
            handlers = self.event_handlers[event_type]
            async with self._lock:
                self._active_tasks += 1
            try:
                for handler in handlers:
                    await handler(event)
            finally:
                async with self._lock:
                    self._active_tasks -= 1

    async def run_cron(self, job: CronJob) -> None:
        """Execute a scheduled cron job.

        The default implementation calls the job's action directly.
        Override to add logging, error handling, or retry logic.

        Args:
            job: The CronJob to execute.
        """
        if not job.enabled:
            return
        try:
            async with self._lock:
                self._active_tasks += 1
                self.status = AgentStatus.BUSY
            await job.action()
        except Exception:
            logger.exception(
                "Agent '%s' cron job '%s' failed",
                self.agent_name,
                job.name or job.schedule,
            )
        finally:
            async with self._lock:
                self._active_tasks -= 1
                if self._active_tasks == 0:
                    self.status = AgentStatus.IDLE

    # ── Gaia Brain Integration ────────────────────────────────────

    async def learn(
        self,
        observation: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Feed an observation to the Gaia Evolution Brain.

        The brain will process the observation and update its knowledge base,
        potentially affecting the entire system's evolution.

        Args:
            observation: Natural language description of the observation.
            metadata: Optional structured data about the observation
                (context, confidence, source, etc.).
        """
        self.memory["experience_count"] += 1
        self.memory["last_learned"] = datetime.now(UTC).isoformat()
        self.memory["observations"].append(
            {
                "observation": observation,
                "metadata": metadata or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        if self.brain is not None and hasattr(self.brain, "ingest_knowledge"):
            try:
                ingest_kwargs = {
                    "source": f"agent_{self.agent_id}",
                    "source_id": f"obs_{self.memory['experience_count']}",
                    "knowledge_type": "insight",
                    "title": f"{self.agent_name}: {observation[:80]}",
                    "content": observation,
                }
                if metadata:
                    ingest_kwargs["tags"] = list(metadata.keys())[:5]
                    ingest_kwargs["confidence"] = metadata.get("confidence", 0.8)
                await self.brain.ingest_knowledge(**ingest_kwargs)
            except Exception:
                logger.warning(
                    "Agent '%s' failed to feed observation to brain",
                    self.agent_name,
                )
        else:
            logger.debug(
                "Agent '%s' learned (brain not available): %s",
                self.agent_name,
                observation[:60],
            )

    async def ask_brain(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Query the Gaia Evolution Brain for relevant knowledge.

        Args:
            query: Natural language query.
            top_k: Maximum number of knowledge entries to retrieve.

        Returns:
            List of knowledge entries with relevance scores.
            Empty list if brain is not available or query fails.
        """
        if self.brain is not None and hasattr(self.brain, "vector_index"):
            try:
                results = self.brain.vector_index.search(
                    content_type="gaia_knowledge",
                    query=query,
                    top_k=top_k,
                )
                return results if results else []
            except Exception:
                logger.warning(
                    "Agent '%s' brain query failed: %s",
                    self.agent_name,
                    query[:60],
                )
        return []

    # ── Inter-Agent Communication ─────────────────────────────────

    async def delegate_to(
        self,
        target_agent: BaseAgent,
        task: str,
        params: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """Delegate a task to another agent.

        Creates an AgentMessage and sends it to the target agent's
        event handler or direct communication channel.

        Args:
            target_agent: The recipient agent.
            task: Description of the task to delegate.
            params: Task parameters.

        Returns:
            The AgentMessage that was sent (for tracking).
        """
        message = AgentMessage(
            source_id=self.agent_id,
            target_id=target_agent.agent_id,
            message_type="task",
            payload={
                "task": task,
                "params": params or {},
                "delegator": self.agent_name,
            },
        )
        # Send via target's handle_event if it accepts AgentMessage
        try:
            await target_agent.handle_event(message)
        except Exception:
            logger.exception(
                "Agent '%s' failed to delegate to '%s'",
                self.agent_name,
                target_agent.agent_name,
            )
        return message

    # ── Utility ───────────────────────────────────────────────────

    def register_tool(self, name: str, func: ToolFunc) -> None:
        """Register a tool that this agent can use.

        Args:
            name: Tool name (e.g. "generate_copy", "search_knowledge").
            func: Callable that implements the tool.
        """
        self.tools[name] = func
        logger.debug(
            "Agent '%s' registered tool: %s",
            self.agent_name,
            name,
        )

    def register_event_handler(
        self,
        event_type: str,
        handler: Callable[[Any], Coroutine[Any, Any, None]],
    ) -> None:
        """Register an event handler for a specific event type.

        Args:
            event_type: Event type string to subscribe to.
            handler: Async callable that processes matching events.
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        logger.debug(
            "Agent '%s' subscribed to event: %s",
            self.agent_name,
            event_type,
        )

    def add_cron_job(self, job: CronJob) -> None:
        """Register a recurring cron job for this agent.

        Args:
            job: CronJob with schedule and action.
        """
        if not job.name:
            job.name = f"cron_{len(self.cron_jobs) + 1}"
        self.cron_jobs.append(job)
        logger.debug(
            "Agent '%s' added cron job: %s [%s]",
            self.agent_name,
            job.name,
            job.schedule,
        )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.agent_id[:8]} name={self.agent_name!r} status={self._status.value}>"
        )
