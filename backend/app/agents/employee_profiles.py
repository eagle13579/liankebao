"""Employee Profiles — Registry mapping agent types to legion employees.

Each of our 9 code agent types maps to a specific 记忆宫殿 legion employee
with a pre-assigned soul, personality, memory, and mental models.

Employee → Agent role mapping (from the legion lore):
    emp-烛龙 (Candle Dragon)     → Backend/Engineering    🔥
    emp-狴犴 (Bi'an)             → QA/Testing             🔍
    emp-獬豸 (Xiezhi)            → Security               ⚖️
    emp-乘黄 (Chenghuang)        → Growth                 📈
    emp-文鳐 (Wenyao)            → Knowledge              📝
    emp-开明兽 (Kaimingshou)     → Architecture           🏛️
    emp-计然 (Jiran)             → Data                   📊
    emp-䑏疏 (Quanshu)           → SRE/Operations         🔧
    emp-白泽 (Baize)             → Support/CEO            👑

Usage:
    from app.agents.employee_profiles import create_legion_agent, EMPLOYEE_AGENT_MAP

    # Create a legion-backed agent
    employee, agent = await create_legion_agent("backend", brain=gaia_brain)
    await agent.start()
    result = await agent.tools["review_code"]("...")

    # Or access the employee directly
    employee.mental_models  # Daoist wisdom models
    employee.personality_traits  # Personality from soul-injection
    await employee.remember("architecture")  # From memory.db
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.architecture_agent import ArchitectureAgent

# ── Agent imports ────────────────────────────────────────────────
from app.agents.backend_agent import BackendAgent
from app.agents.base_agent import AgentConfig, BaseAgent
from app.agents.data_agent import DataAgent
from app.agents.growth_agent import GrowthAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.legion_employee import LegionEmployee
from app.agents.qa_agent import QAAgent
from app.agents.security_agent import SecurityAgent
from app.agents.sre_agent import SREAgent
from app.agents.support_agent import SupportAgent

logger = logging.getLogger(__name__)

# ── Employee-to-Agent mapping ────────────────────────────────────

# NOTE: emp-白泽 lives under 'emp-白泽-3c6ee223' on disk.
# The directory resolver in LegionEmployee handles this via prefix matching.

EMPLOYEE_AGENT_MAP: dict[str, dict[str, Any]] = {
    "backend": {
        "employee_id": "emp-烛龙",
        "agent_class": BackendAgent,
        "role_description": "Backend Engineer — code review, API generation, debugging",
    },
    "qa": {
        "employee_id": "emp-狴犴",
        "agent_class": QAAgent,
        "role_description": "QA Engineer — test generation, coverage analysis, regression detection",
    },
    "security": {
        "employee_id": "emp-獬豸",
        "agent_class": SecurityAgent,
        "role_description": "Security Engineer — vulnerability scanning, compliance monitoring",
    },
    "growth": {
        "employee_id": "emp-乘黄",
        "agent_class": GrowthAgent,
        "role_description": "Growth Engineer — A/B test analysis, user behavior insights",
    },
    "knowledge": {
        "employee_id": "emp-文鳐",
        "agent_class": KnowledgeAgent,
        "role_description": "Knowledge Engineer — documentation, ADRs, knowledge base management",
    },
    "architecture": {
        "employee_id": "emp-开明兽",
        "agent_class": ArchitectureAgent,
        "role_description": "Architecture Engineer — design review, capacity planning",
    },
    "data": {
        "employee_id": "emp-计然",
        "agent_class": DataAgent,
        "role_description": "Data Engineer — schema migration, ETL, data quality",
    },
    "sre": {
        "employee_id": "emp-䑏疏",
        "agent_class": SREAgent,
        "role_description": "SRE Engineer — monitoring, remediation, capacity forecasting",
    },
    "support": {
        "employee_id": "emp-白泽",
        "agent_class": SupportAgent,
        "role_description": "Support Engineer — ticket handling, FAQ, resolution learning",
    },
}


def _resolve_employee_id_for_agent_type(agent_type: str) -> str:
    """Get the canonical employee_id for a given agent type.

    Args:
        agent_type: One of the keys in EMPLOYEE_AGENT_MAP.

    Returns:
        The employee_id string (e.g., 'emp-烛龙').

    Raises:
        KeyError: If agent_type is not in the map.
    """
    mapping = EMPLOYEE_AGENT_MAP.get(agent_type)
    if not mapping:
        raise KeyError(f"Unknown agent type '{agent_type}'. Available: {list(EMPLOYEE_AGENT_MAP.keys())}")
    return mapping["employee_id"]


def _build_agent_config(
    agent_type: str,
    employee: LegionEmployee,
    mapping: dict[str, Any],
) -> AgentConfig:
    """Build an AgentConfig from the employee's soul data.

    Uses the employee's name, level, and mental models to create
    a richer AgentConfig than the default.

    Args:
        agent_type: The type key (e.g., 'backend').
        employee: The loaded LegionEmployee instance.
        mapping: The entry from EMPLOYEE_AGENT_MAP.

    Returns:
        An AgentConfig with employee-derived metadata.
    """
    agent_class = mapping["agent_class"]
    # Get the default config from the agent class constructor
    default_config = AgentConfig(
        agent_name=f"{agent_type}_{employee.name}",
        agent_role=employee.identity.get("role", agent_type),
        knowledge_base_name=agent_type,
        max_concurrent_tasks=10,
    )

    # If we have a level, we could adjust max_concurrent_tasks
    level = employee.level
    if level:
        # Higher-level employees can handle more work
        level_num = 0
        try:
            level_num = int(level.lstrip("P").lstrip("L") or "0")
        except (ValueError, AttributeError):
            pass
        if level_num >= 8:
            default_config.max_concurrent_tasks = 15
        elif level_num >= 6:
            default_config.max_concurrent_tasks = 10
        else:
            default_config.max_concurrent_tasks = 5

    return default_config


def create_legion_agent(
    agent_type: str,
    brain: Any | None = None,
    broker: Any | None = None,
    event_bus: Any | None = None,
) -> tuple[LegionEmployee, BaseAgent]:
    """Create a legion-backed agent pair.

    Returns a tuple of (LegionEmployee, Agent) where:
    - LegionEmployee wraps the 记忆宫殿 employee (with soul, memory, personality)
    - Agent is the existing BaseAgent subclass (with tools, cron, events)

    The employee's personality, mental models, and memory.db are attached
    to the agent via the employee wrapper. The agent's tools become the
    employee's capabilities.

    Args:
        agent_type: One of 'backend', 'qa', 'security', 'growth',
                    'knowledge', 'architecture', 'data', 'sre', 'support'.
        brain: GaiaEvolutionBrain reference (optional).
        broker: ServiceBrokerProtocol reference (optional).
        event_bus: EventBusProtocol reference (optional).

    Returns:
        Tuple of (LegionEmployee, Agent subclass instance).

    Raises:
        KeyError: If agent_type is unknown.
    """
    # 1. Get the mapping
    mapping = EMPLOYEE_AGENT_MAP.get(agent_type)
    if not mapping:
        raise KeyError(f"Unknown agent type '{agent_type}'. Available: {list(EMPLOYEE_AGENT_MAP.keys())}")

    employee_id = mapping["employee_id"]
    agent_class = mapping["agent_class"]

    # 2. Create the employee wrapper (loads soul, memory, personality)
    employee = LegionEmployee(
        employee_id=employee_id,
        brain=brain,
    )

    # 3. Build the agent config with employee-derived metadata
    config = _build_agent_config(agent_type, employee, mapping)

    # 4. Create the agent instance with employee-derived config
    agent = agent_class(
        config=config,
        brain=brain,
        broker=broker,
        event_bus=event_bus,
    )

    # 5. Attach employee tools to the agent's tool registry
    #    (employee is accessed as agent.employee)
    agent.employee = employee  # type: ignore[attr-defined]

    # 6. Register employee's mental models as an agent capability
    if employee.mental_models:
        agent.register_tool("get_mental_models", _make_get_mental_models(employee))
        agent.register_tool("get_employee_profile", _make_get_employee_profile(employee))
        agent.register_tool("remember_from_legion", _make_remember(employee))
        agent.register_tool("memorize_to_legion", _make_memorize(employee))

    logger.info(
        "Legion agent created: %s → %s (soul=%s, tools=%d, models=%d)",
        agent_type,
        employee.name,
        employee.employee_id,
        len(agent.tools),
        len(employee.mental_models),
    )

    return employee, agent


# ── Tool factories (closures that bind employee methods) ──────────


def _make_get_mental_models(employee: LegionEmployee):
    """Return a callable tool that gets the employee's mental models."""

    async def get_mental_models() -> list[dict[str, Any]]:
        """Get the Daoist wisdom mental models from the employee's soul."""
        return [
            {
                "name": m.get("name", str(m)) if isinstance(m, dict) else str(m),
                "content": m.get("content", "") if isinstance(m, dict) else "",
            }
            for m in employee.mental_models
        ]

    return get_mental_models


def _make_get_employee_profile(employee: LegionEmployee):
    """Return a callable tool that gets the full employee profile."""

    async def get_employee_profile() -> dict[str, Any]:
        """Get the full employee profile including soul, personality, and stats."""
        return await employee.get_stats()

    return get_employee_profile


def _make_remember(employee: LegionEmployee):
    """Return a callable tool that queries the employee's memory.db."""

    async def remember_from_legion(key: str, limit: int = 5) -> list[dict[str, Any]]:
        """Query the legion employee's memory.db for relevant memories.

        Args:
            key: Search term to match.
            limit: Max results (default 5).

        Returns:
            List of matching memory entries.
        """
        return await employee.remember(key, limit)

    return remember_from_legion


def _make_memorize(employee: LegionEmployee):
    """Return a callable tool that writes to the employee's memory.db."""

    async def memorize_to_legion(content: str, category: str = "experience") -> str:
        """Store a memory in the employee's own memory.db.

        Args:
            content: The memory content.
            category: Category/type (default 'experience').

        Returns:
            Status message.
        """
        await employee.memorize(content, category)
        return f"Memory stored for {employee.name} (category: {category})"

    return memorize_to_legion


# ── Convenience: Create all agents at once ────────────────────────


async def create_all_legion_agents(
    brain: Any | None = None,
    broker: Any | None = None,
    event_bus: Any | None = None,
) -> dict[str, tuple[LegionEmployee, BaseAgent]]:
    """Create all 9 legion-backed agents at once.

    Args:
        brain: GaiaEvolutionBrain reference.
        broker: ServiceBrokerProtocol reference.
        event_bus: EventBusProtocol reference.

    Returns:
        Dict mapping agent_type → (LegionEmployee, Agent) tuple.
    """
    agents: dict[str, tuple[LegionEmployee, BaseAgent]] = {}
    for agent_type in EMPLOYEE_AGENT_MAP:
        try:
            employee, agent = await create_legion_agent(
                agent_type=agent_type,
                brain=brain,
                broker=broker,
                event_bus=event_bus,
            )
            agents[agent_type] = (employee, agent)
            logger.info("Created legion agent: %s → %s", agent_type, employee.name)
        except Exception as exc:
            logger.error("Failed to create legion agent '%s': %s", agent_type, exc)
    return agents
