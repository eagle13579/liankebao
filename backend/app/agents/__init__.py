"""Agents: AI Employee Framework — Interface + Adapter pattern.

This package defines the stable base class and contracts for AI employees.
Each agent is an autonomous unit with a brain, knowledge base, tools, and lifecycle.

The package has been extended with LegionEmployee integration, connecting
each code agent to a 记忆宫殿 legion employee with soul, personality, and
persistent memory (memory.db + Gaia Brain).

Available agents:
    - BaseAgent: Abstract base class for all AI employees.
    - BackendAgent: Backend Engineer — code review, API generation, debugging.
    - QAAgent: Quality Assurance — test generation, coverage analysis.
    - SecurityAgent: Security Engineer — vulnerability scanning, compliance.
    - GrowthAgent: Growth Engineer — A/B test analysis, conversion optimization.
    - KnowledgeAgent: Knowledge Engineer — documentation, ADR creation.
    - ArchitectureAgent: Architecture Engineer — design review, capacity planning.
    - DataAgent: Data Engineer — schema migration, ETL, data quality.
    - SREAgent: Site Reliability Engineer — monitors, remediates, forecasts.
    - SupportAgent: User Technical Support — handles tickets, searches knowledge.
    - AgentRuntime: Orchestrator managing all AI employee lifecycles.
    - LegionEmployee: Adapter wrapping 记忆宫殿 employees with soul + memory.
    - create_legion_agent: Factory pairing a legion employee with an agent.
    - EMPLOYEE_AGENT_MAP: Registry mapping agent types to legion employees.
"""

# ── Runtime ───────────────────────────────────────────────────────
from app.agents.agent_runtime import AgentRuntime
from app.agents.architecture_agent import ArchitectureAgent

# ── All 9 code agents ─────────────────────────────────────────────
from app.agents.backend_agent import BackendAgent
from app.agents.base_agent import AgentConfig, AgentMessage, AgentStatus, BaseAgent, CronJob
from app.agents.data_agent import DataAgent
from app.agents.employee_profiles import EMPLOYEE_AGENT_MAP, create_all_legion_agents, create_legion_agent
from app.agents.growth_agent import GrowthAgent
from app.agents.knowledge_agent import KnowledgeAgent

# ── Legion Employee integration ───────────────────────────────────
from app.agents.legion_employee import LegionEmployee
from app.agents.qa_agent import QAAgent
from app.agents.security_agent import SecurityAgent
from app.agents.sre_agent import SREAgent
from app.agents.support_agent import SupportAgent

__all__ = [
    # Base
    "BaseAgent",
    "AgentConfig",
    "AgentStatus",
    "CronJob",
    "AgentMessage",
    # Agents
    "BackendAgent",
    "QAAgent",
    "SecurityAgent",
    "GrowthAgent",
    "KnowledgeAgent",
    "ArchitectureAgent",
    "DataAgent",
    "SREAgent",
    "SupportAgent",
    # Runtime
    "AgentRuntime",
    # Legion integration
    "LegionEmployee",
    "create_legion_agent",
    "create_all_legion_agents",
    "EMPLOYEE_AGENT_MAP",
]
