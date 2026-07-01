"""ArchitectureAgent — Architecture Engineer Digital Employee.

An AI employee that reviews design proposals, estimates capacity needs,
and suggests architecture evolution strategies.

Architecture:
    Extends BaseAgent with architecture-specific tools and cron jobs.
    Delegates to SREAgent for capacity data. Runs daily system health
    reviews from an architectural perspective.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.base_agent import BaseAgent, AgentConfig, CronJob, AgentStatus

logger = logging.getLogger(__name__)


class ArchitectureAgent(BaseAgent):
    """Architecture Engineer — design review, capacity planning,
    architecture evolution.

    This agent is the autonomous software architect. It reviews design
    proposals, estimates infrastructure capacity needs, and suggests
    evolutionary improvements to the system architecture.

    Args:
        config: Agent configuration (defaults to Architecture role).
        brain: GaiaEvolutionBrain reference for knowledge lookup and learning.
        broker: ServiceBrokerProtocol reference for cross-service calls.
        event_bus: EventBusProtocol reference for publishing events.
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        brain: Any | None = None,
        broker: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        arch_config = config or AgentConfig(
            agent_name="architecture_engineer",
            agent_role="architecture_engineer",
            knowledge_base_name="architecture",
            max_concurrent_tasks=10,
        )
        super().__init__(config=arch_config, brain=brain)
        self.broker: Any | None = broker
        self.event_bus: Any | None = event_bus

        # Tracking
        self._designs_reviewed: int = 0
        self._capacity_estimates: int = 0
        self._evolution_suggestions: int = 0

        # Delegate agents (set externally by AgentRuntime)
        self._sre_agent: Any = None

        # Architecture principles
        self._architecture_principles: list[dict[str, str]] = [
            {
                "principle": "Separation of Concerns",
                "description": "Each module should have a single, well-defined responsibility",
            },
            {
                "principle": "Loose Coupling",
                "description": "Modules should interact through well-defined interfaces, not direct dependencies",
            },
            {
                "principle": "High Cohesion",
                "description": "Related functionality should be grouped together within modules",
            },
            {
                "principle": "Scalability",
                "description": "System should scale horizontally by adding more instances",
            },
            {
                "principle": "Resilience",
                "description": "System should handle failures gracefully with circuit breakers and retries",
            },
            {
                "principle": "Observability",
                "description": "All components must expose metrics, logs, and traces",
            },
            {
                "principle": "Security by Design",
                "description": "Security controls must be integrated from the start, not bolted on",
            },
            {
                "principle": "Evolutionary Design",
                "description": "Architecture should evolve incrementally, not through big-bang rewrites",
            },
        ]

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def init(self) -> None:
        """Register architecture tools, cron jobs, and event handlers."""
        # Register tools
        self.register_tool("review_design", self.review_design)
        self.register_tool("capacity_estimate", self.capacity_estimate)
        self.register_tool("evolution_suggestion", self.evolution_suggestion)

        # Register event handlers
        self.register_event_handler("design.proposal_submitted", self.review_design)
        self.register_event_handler("architecture.review_requested", self.review_design)

        # Register cron jobs
        self.add_cron_job(CronJob(
            schedule="0 0 * * *",
            action=self.review_system_health,
            name="review_system_health_24h",
        ))

        logger.info(
            "ArchitectureAgent initialized with %d principles",
            len(self._architecture_principles),
        )

    async def stop(self) -> None:
        """Clean up architecture agent resources."""
        logger.info(
            "ArchitectureAgent stopping — designs=%d capacities=%d evolutions=%d",
            self._designs_reviewed,
            self._capacity_estimates,
            self._evolution_suggestions,
        )

        await self.learn(
            observation=(
                f"ArchitectureAgent reviewed {self._designs_reviewed} designs, "
                f"estimated {self._capacity_estimates} capacity plans, "
                f"suggested {self._evolution_suggestions} evolution strategies."
            ),
            metadata={
                "designs_reviewed": self._designs_reviewed,
                "capacity_estimates": self._capacity_estimates,
                "evolution_suggestions": self._evolution_suggestions,
                "source": "architecture_agent",
            },
        )
        self.status = AgentStatus.STOPPED
        logger.info("ArchitectureAgent stopped")

    # ── Delegation ────────────────────────────────────────────────────

    def set_sre_agent(self, agent: Any) -> None:
        """Set the SRE agent for delegating capacity data requests.

        Args:
            agent: The SREAgent instance.
        """
        self._sre_agent = agent
        logger.debug("ArchitectureAgent: SREAgent set for delegation")

    async def _get_capacity_data_from_sre(self) -> dict[str, Any] | None:
        """Delegate to SREAgent for current capacity data.

        Returns:
            Capacity metrics dict, or None if SRE agent is not available.
        """
        if self._sre_agent is not None:
            try:
                # Try calling the SRE agent's capacity_forecast tool
                if hasattr(self._sre_agent, "capacity_forecast"):
                    result = await self._sre_agent.capacity_forecast()
                    if isinstance(result, dict):
                        return result
            except Exception as exc:
                logger.warning(
                    "Failed to get capacity data from SREAgent: %s", exc
                )

        # Fallback: try broker-based approach
        if self.broker is not None:
            try:
                from app.broker.interfaces import ServiceRequest

                resp = await self.broker.call(ServiceRequest(
                    service="sre",
                    method="capacity_forecast",
                    timeout_ms=10_000,
                ))
                if resp.success and isinstance(resp.data, dict):
                    return resp.data
            except Exception:
                logger.debug("Broker-based SRE capacity request failed")

        return None

    # ── Design Review ─────────────────────────────────────────────────

    async def review_design(self, proposal: Any) -> dict[str, Any]:
        """Review an architecture design proposal.

        Evaluates the proposal against architecture principles and
        provides feedback on strengths, risks, and recommendations.

        Args:
            proposal: Dict, Event payload, or string description.
                Supports 'title', 'description', 'components', 'diagram',
                'tech_stack', 'constraints'.

        Returns:
            Dict with review findings, scores, and recommendations.
        """
        self._designs_reviewed += 1

        # Normalize input
        if hasattr(proposal, "payload"):
            data = getattr(proposal, "payload", {})
        elif isinstance(proposal, dict):
            data = proposal
        else:
            data = {"description": str(proposal)}

        title = data.get("title", data.get("name", f"Design Proposal #{self._designs_reviewed}"))
        description = data.get("description", "")
        components = data.get("components", data.get("modules", []))
        tech_stack = data.get("tech_stack", data.get("technologies", []))
        constraints = data.get("constraints", data.get("requirements", []))

        logger.info("Reviewing design proposal: %s", title)

        # Check against architecture principles
        principle_findings: list[dict[str, Any]] = []
        scores: list[int] = []

        for principle in self._architecture_principles:
            p_name = principle["principle"]
            p_desc = principle["description"]

            # Check if the design addresses this principle
            combined_text = f"{description} {' '.join(str(c) for c in components)} {' '.join(str(t) for t in tech_stack)}".lower()

            # Simple keyword-based checks
            principle_keywords: dict[str, list[str]] = {
                "Separation of Concerns": ["separat", "modular", "layered", "tier"],
                "Loose Coupling": ["interface", "api", "event", "message", "queue"],
                "High Cohesion": ["module", "package", "namespace", "domain"],
                "Scalability": ["scale", "horizontal", "shard", "partition", "replica"],
                "Resilience": ["failover", "retry", "circuit", "timeout", "backup"],
                "Observability": ["log", "metric", "trace", "monitor", "dashboard"],
                "Security by Design": ["auth", "encrypt", "permission", "rbac", "token"],
                "Evolutionary Design": ["migration", "version", "backward", "compat"],
            }

            keywords = principle_keywords.get(p_name, [])
            addressed = any(kw in combined_text for kw in keywords)

            if addressed:
                scores.append(10)
                principle_findings.append({
                    "principle": p_name,
                    "status": "addressed",
                    "score": 10,
                    "note": f"Design addresses {p_desc.lower()}",
                })
            else:
                scores.append(5)
                principle_findings.append({
                    "principle": p_name,
                    "status": "not_addressed",
                    "score": 5,
                    "note": f"Design does not explicitly address {p_desc.lower()}",
                })

        # Calculate overall score
        overall_score = round(sum(scores) / len(scores), 2) if scores else 0

        # Identify risks
        risks: list[str] = []
        if not components:
            risks.append("No component/module breakdown provided — architecture may be monolithic")
        if not tech_stack:
            risks.append("No technology stack specified — technology risk assessment not possible")

        combined_lower = (description + " " + " ".join(str(c) for c in components)).lower()
        if "monolith" in combined_lower and "migration" not in combined_lower:
            risks.append("Monolithic architecture without migration plan — scalability concern")
        if "single point" in combined_lower or "single database" in combined_lower:
            risks.append("Potential single point of failure identified")

        # Generate recommendations
        recommendations: list[str] = []
        for finding in principle_findings:
            if finding["status"] == "not_addressed":
                recommendations.append(f"Address '{finding['principle']}': {finding['note']}")
        recommendations.append("Consider creating an Architecture Decision Record (ADR) for key decisions")
        recommendations.append("Plan for incremental evolution rather than big-bang deployment")

        # Check if SRE capacity data is needed
        sre_data = None
        if self._sre_agent is not None:
            sre_data = await self._get_capacity_data_from_sre()

        result = {
            "title": title,
            "overall_score": overall_score,
            "max_score": 10,
            "principle_assessment": principle_findings,
            "risks": risks,
            "recommendations": recommendations,
            "sre_capacity_context": sre_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Design review for '%s': score=%.2f/10, %d risks, %d recommendations",
            title,
            overall_score,
            len(risks),
            len(recommendations),
        )

        # Learn from this review
        await self.learn(
            observation=(
                f"Design review of '{title}': score={overall_score}/10, "
                f"{len(risks)} risks identified, {len(recommendations)} recommendations"
            ),
            metadata={
                "proposal_title": title,
                "score": overall_score,
                "risks": len(risks),
                "recommendations": len(recommendations),
                "source": "architecture_agent",
            },
        )

        return result

    # ── Capacity Estimation ───────────────────────────────────────────

    async def capacity_estimate(self, metrics: Any) -> dict[str, Any]:
        """Estimate capacity needs based on current metrics.

        Analyzes system metrics and growth trends to estimate future
        capacity requirements.

        Args:
            metrics: Dict, Event payload, or string with metrics data.
                Supports 'current_users', 'growth_rate', 'requests_per_sec',
                'data_volume', 'response_time'.

        Returns:
            Dict with capacity analysis and recommendations.
        """
        self._capacity_estimates += 1

        # Normalize input
        if hasattr(metrics, "payload"):
            data = getattr(metrics, "payload", {})
        elif isinstance(metrics, dict):
            data = metrics
        else:
            data = {"raw_metrics": str(metrics)}

        current_users = self._safe_int(data.get("current_users", data.get("users", 0)), 1000)
        growth_rate = float(data.get("growth_rate", data.get("growth", 0.15)))
        requests_per_sec = self._safe_int(data.get("requests_per_sec", data.get("rps", 0)), 100)
        data_volume_gb = float(data.get("data_volume", data.get("data_gb", 50)))
        avg_response_time_ms = float(data.get("response_time", data.get("latency_ms", 200)))

        logger.info(
            "Estimating capacity: %d users, %.0f%% growth, %d RPS, %.1f GB data",
            current_users,
            growth_rate * 100,
            requests_per_sec,
            data_volume_gb,
        )

        # Get SRE data if available
        sre_data = await self._get_capacity_data_from_sre()

        # Project forward (3 months, 6 months, 12 months)
        projections: list[dict[str, Any]] = []
        for months in [3, 6, 12]:
            projected_users = int(current_users * (1 + growth_rate) ** months)
            projected_rps = int(requests_per_sec * (1 + growth_rate) ** months)
            projected_data = data_volume_gb * (1 + growth_rate) ** months

            # Estimate infrastructure needs
            app_instances = max(2, projected_rps // 500 + 1)  # Assume 500 RPS per instance
            db_read_replicas = max(1, projected_users // 50000 + 1)
            cache_size_gb = max(1, projected_data * 0.1)  # 10% in cache

            projections.append({
                "months_out": months,
                "projected_users": projected_users,
                "projected_rps": projected_rps,
                "projected_data_gb": round(projected_data, 1),
                "recommended_app_instances": app_instances,
                "recommended_db_replicas": db_read_replicas,
                "recommended_cache_gb": round(cache_size_gb, 1),
            })

        # Current status
        current_status: dict[str, Any] = {
            "users": current_users,
            "requests_per_sec": requests_per_sec,
            "data_volume_gb": data_volume_gb,
            "avg_response_time_ms": avg_response_time_ms,
            "estimated_headroom_pct": round(
                max(0, 100 - (avg_response_time_ms / 1000 * 100)), 2
            ),
        }

        # Bottleneck analysis
        bottlenecks: list[str] = []
        if avg_response_time_ms > 500:
            bottlenecks.append("High response time — consider caching and query optimization")
        if requests_per_sec > 1000 and current_users < 100000:
            bottlenecks.append("High RPS-to-user ratio — check for excessive API calls or inefficient batching")
        if data_volume_gb > 500:
            bottlenecks.append("Large data volume — consider data archival and partitioning strategy")

        if not bottlenecks:
            bottlenecks.append("No immediate bottlenecks detected — current architecture appears adequate")

        # Recommendations
        recommendations: list[str] = [
            "Implement auto-scaling for application tier based on CPU/memory utilization",
            "Add read replicas for database as user base grows",
            "Implement CDN caching for static assets to reduce origin load",
            "Consider sharding strategy for database when exceeding 500GB",
            "Set up monitoring alerts at 70% capacity utilization",
        ]

        result = {
            "current": current_status,
            "projections": projections,
            "bottlenecks": bottlenecks,
            "recommendations": recommendations,
            "sre_data_used": sre_data is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Capacity estimate complete: %d projections, %d bottlenecks",
            len(projections),
            len(bottlenecks),
        )

        # Learn from this estimate
        await self.learn(
            observation=(
                f"Capacity estimate: {current_users} users, {growth_rate*100:.0f}% growth. "
                f"3mo projection: {projections[0]['projected_users']} users, "
                f"{projections[0]['recommended_app_instances']} instances needed"
            ),
            metadata={
                "current_users": current_users,
                "growth_rate": growth_rate,
                "projections_count": len(projections),
                "bottlenecks": len(bottlenecks),
                "source": "architecture_agent",
            },
        )

        return result

    # ── Evolution Suggestion ──────────────────────────────────────────

    async def evolution_suggestion(self, current_arch: Any) -> dict[str, Any]:
        """Suggest the next evolution step for the architecture.

        Analyzes the current architecture and suggests evolutionary
        improvements based on best practices and observed patterns.

        Args:
            current_arch: Dict, Event payload, or string describing the
                current architecture.

        Returns:
            Dict with evolution suggestions and roadmap.
        """
        self._evolution_suggestions += 1

        # Normalize input
        if hasattr(current_arch, "payload"):
            data = getattr(current_arch, "payload", {})
        elif isinstance(current_arch, dict):
            data = current_arch
        else:
            data = {"architecture": str(current_arch)}

        arch_name = data.get("name", data.get("architecture", f"System #{self._evolution_suggestions}"))
        arch_type = data.get("type", data.get("pattern", "monolith"))
        scale = data.get("scale", data.get("size", "medium"))
        pain_points = data.get("pain_points", data.get("challenges", []))
        tech_stack = data.get("tech_stack", data.get("technologies", []))

        logger.info("Suggesting evolution for: %s (%s)", arch_name, arch_type)

        # Evolution paths based on current architecture type
        evolution_paths: dict[str, list[dict[str, Any]]] = {
            "monolith": [
                {
                    "step": 1,
                    "name": "Extract first bounded context",
                    "description": "Identify the most independent module and extract it as a microservice",
                    "effort": "medium",
                    "impact": "high",
                    "timeline": "4-8 weeks",
                },
                {
                    "step": 2,
                    "name": "Implement API gateway",
                    "description": "Add an API gateway to route requests between monolith and new services",
                    "effort": "high",
                    "impact": "high",
                    "timeline": "6-12 weeks",
                },
                {
                    "step": 3,
                    "name": "Database decomposition",
                    "description": "Split the monolith database into domain-specific databases",
                    "effort": "high",
                    "impact": "critical",
                    "timeline": "8-16 weeks",
                },
                {
                    "step": 4,
                    "name": "Strangler pattern migration",
                    "description": "Gradually replace monolith functionality with microservices",
                    "effort": "very_high",
                    "impact": "critical",
                    "timeline": "12-24 weeks",
                },
            ],
            "microservices": [
                {
                    "step": 1,
                    "name": "Implement service mesh",
                    "description": "Add service mesh (e.g., Istio, Linkerd) for observability and traffic management",
                    "effort": "high",
                    "impact": "high",
                    "timeline": "4-8 weeks",
                },
                {
                    "step": 2,
                    "name": "Event-driven communication",
                    "description": "Transition from synchronous HTTP to event-driven messaging for non-critical paths",
                    "effort": "high",
                    "impact": "medium",
                    "timeline": "8-16 weeks",
                },
                {
                    "step": 3,
                    "name": "Saga pattern for distributed transactions",
                    "description": "Implement choreography-based saga pattern for multi-service transactions",
                    "effort": "medium",
                    "impact": "high",
                    "timeline": "6-10 weeks",
                },
                {
                    "step": 4,
                    "name": "Autonomous teams per service",
                    "description": "Organize teams around individual services with full ownership",
                    "effort": "organizational",
                    "impact": "high",
                    "timeline": "ongoing",
                },
            ],
            "serverless": [
                {
                    "step": 1,
                    "name": "Cold start optimization",
                    "description": "Implement Lambda warmers and provisioned concurrency for critical functions",
                    "effort": "low",
                    "impact": "medium",
                    "timeline": "1-2 weeks",
                },
                {
                    "step": 2,
                    "name": "Step functions for workflows",
                    "description": "Replace complex function chains with AWS Step Functions",
                    "effort": "medium",
                    "impact": "high",
                    "timeline": "3-6 weeks",
                },
                {
                    "step": 3,
                    "name": "Multi-region deployment",
                    "description": "Deploy to multiple regions for lower latency and disaster recovery",
                    "effort": "high",
                    "impact": "high",
                    "timeline": "8-12 weeks",
                },
            ],
        }

        # Find matching evolution path
        arch_key = arch_type.lower().replace(" ", "_").replace("-", "_")
        if arch_key not in evolution_paths:
            # Default path for unknown architectures
            evolution_paths[arch_key] = [
                {
                    "step": 1,
                    "name": "Architecture assessment",
                    "description": "Conduct a thorough assessment of current architecture strengths and weaknesses",
                    "effort": "medium",
                    "impact": "high",
                    "timeline": "2-4 weeks",
                },
                {
                    "step": 2,
                    "name": "Document architecture",
                    "description": "Create comprehensive architecture documentation including C4 diagrams",
                    "effort": "medium",
                    "impact": "medium",
                    "timeline": "2-4 weeks",
                },
                {
                    "step": 3,
                    "name": "Identify improvement areas",
                    "description": "Identify top 3 areas for architectural improvement based on pain points",
                    "effort": "low",
                    "impact": "high",
                    "timeline": "1-2 weeks",
                },
            ]

        path = evolution_paths.get(arch_key, evolution_paths["monolith"])

        # Incorporate pain points
        pain_point_recommendations: list[str] = []
        if pain_points:
            for pp in pain_points if isinstance(pain_points, list) else [str(pain_points)]:
                pain_point_recommendations.append(f"Address '{pp}' in the architecture evolution roadmap")

        result = {
            "current_architecture": arch_name,
            "architecture_type": arch_type,
            "evolution_path": path,
            "total_steps": len(path),
            "estimated_total_timeline": path[-1]["timeline"] if path else "unknown",
            "pain_point_recommendations": pain_point_recommendations,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Evolution suggestion for '%s': %d steps, timeline=%s",
            arch_name,
            len(path),
            result["estimated_total_timeline"],
        )

        # Learn from this suggestion
        await self.learn(
            observation=(
                f"Architecture evolution suggestion for '{arch_name}' "
                f"({arch_type}): {len(path)} steps, timeline={result['estimated_total_timeline']}"
            ),
            metadata={
                "architecture": arch_name,
                "type": arch_type,
                "evolution_steps": len(path),
                "timeline": result["estimated_total_timeline"],
                "source": "architecture_agent",
            },
        )

        return result

    # ── Cron Job ──────────────────────────────────────────────────────

    async def review_system_health(self) -> dict[str, Any]:
        """Daily cron job: review system health from an architecture perspective.

        Analyzes the overall system architecture health, identifies
        structural issues, and suggests improvements.

        Returns:
            Dict with system health assessment.
        """
        logger.info("ArchitectureAgent: daily system health review...")

        # Get capacity data from SRE if available
        sre_data = await self._get_capacity_data_from_sre()

        health_assessment: dict[str, Any] = {
            "overall_health": "good",
            "sre_capacity_available": sre_data is not None,
            "observations": [],
            "recommendations": [],
        }

        if sre_data:
            health_assessment["observations"].append(
                "SRE capacity data available — architecture review incorporates operational metrics"
            )
        else:
            health_assessment["observations"].append(
                "SRE capacity data not available — consider integrating with SREAgent"
            )

        # Architecture health checks
        health_assessment["observations"].append(
            "Architecture principles should be reviewed periodically for continued relevance"
        )

        health_assessment["recommendations"] = [
            "Review Architecture Decision Records (ADRs) for outdated decisions",
            "Check for architecture drift between documented design and actual implementation",
            "Verify that all services have defined SLAs and SLOs",
            "Ensure all critical paths have redundancy and failover mechanisms",
            "Review dependency graph for circular dependencies",
        ]

        health_assessment["timestamp"] = datetime.now(timezone.utc).isoformat()

        logger.info(
            "System health review: overall=%s, %d observations, %d recommendations",
            health_assessment["overall_health"],
            len(health_assessment["observations"]),
            len(health_assessment["recommendations"]),
        )

        # Learn from this review
        await self.learn(
            observation=(
                f"Daily system health review: overall={health_assessment['overall_health']}, "
                f"SRE data available={sre_data is not None}"
            ),
            metadata={
                "sre_data_available": sre_data is not None,
                "observations": len(health_assessment["observations"]),
                "recommendations": len(health_assessment["recommendations"]),
                "source": "architecture_agent",
            },
        )

        return health_assessment

    # ── Utility ───────────────────────────────────────────────────────

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Safely convert a value to int.

        Args:
            value: The value to convert.
            default: Default if conversion fails.

        Returns:
            int value.
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    # ── Public API ────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Return architecture agent statistics.

        Returns:
            Dict with stats on designs, capacities, and evolutions.
        """
        return {
            "agent": self.agent_name,
            "role": self.agent_role,
            "status": self.status.value,
            "designs_reviewed": self._designs_reviewed,
            "capacity_estimates": self._capacity_estimates,
            "evolution_suggestions": self._evolution_suggestions,
            "sre_agent_connected": self._sre_agent is not None,
        }
