"""SupportAgent — User Technical Support Digital Employee.

An AI employee that handles user support tickets, searches knowledge bases,
generates responses, escalates when necessary, and learns from resolutions.

Architecture:
    Extends BaseAgent with support-specific tools and event handlers.
    Works via three mechanisms:
        1. Event-driven ticket handling (support.ticket_created)
        2. Proactive FAQ lookup for common questions
        3. Continuous learning from successful resolutions
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import AgentConfig, AgentStatus, BaseAgent

logger = logging.getLogger(__name__)

# ── Built-in FAQ database ──────────────────────────────────────────────

BUILTIN_FAQ: dict[str, str] = {
    "how_to_reset_password": (
        "To reset your password:\n"
        "1. Go to the login page.\n"
        "2. Click 'Forgot Password'.\n"
        "3. Enter your registered email address.\n"
        "4. Check your email for a password reset link.\n"
        "5. Follow the link to create a new password."
    ),
    "how_to_export_data": (
        "To export your data:\n"
        "1. Go to Settings > Data Management.\n"
        "2. Select 'Export Data'.\n"
        "3. Choose the data types you want to export.\n"
        "4. Click 'Start Export'.\n"
        "5. You will receive an email with a download link."
    ),
    "billing_issue": (
        "For billing issues:\n"
        "- Check your payment method in Settings > Billing.\n"
        "- Ensure your subscription is active.\n"
        "- Contact billing support at billing@liankebao.com.\n"
        "- Include your invoice number for faster resolution."
    ),
    "api_rate_limit": (
        "API rate limits:\n"
        "- Free tier: 100 requests/hour.\n"
        "- Pro tier: 10,000 requests/hour.\n"
        "- Enterprise: Custom limits.\n"
        "If you're hitting limits, consider upgrading your plan or "
        "implementing request batching."
    ),
    "integration_guide": (
        "To integrate with our API:\n"
        "1. Get your API key from Developer > API Keys.\n"
        "2. Read our API documentation at docs.liankebao.com.\n"
        "3. Use the provided SDKs for Python, JavaScript, and Java.\n"
        "4. Test in our sandbox environment first."
    ),
}


class SupportAgent(BaseAgent):
    """User Technical Support — handles tickets, searches knowledge, escalates.

    This agent is the first line of user support. It attempts to resolve
    issues automatically using the knowledge base and FAQ, and escalates
    to human agents when it cannot.

    Args:
        config: Agent configuration (defaults to Support role).
        brain: GaiaEvolutionBrain reference for knowledge lookup.
        broker: ServiceBrokerProtocol reference for cross-service delegation.
        event_bus: EventBusProtocol reference for publishing events.
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        brain: Any | None = None,
        broker: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        support_config = config or AgentConfig(
            agent_name="support_agent",
            agent_role="user_technical_support",
            knowledge_base_name="support",
            max_concurrent_tasks=20,
        )
        super().__init__(config=support_config, brain=brain)
        self.broker: Any | None = broker
        self.event_bus: Any | None = event_bus

        # Tracking
        self._tickets_handled: int = 0
        self._tickets_escalated: int = 0
        self._tickets_resolved: int = 0

        # Delegate agents (set externally by AgentRuntime)
        self._backend_agent: Any = None
        self._security_agent: Any = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def init(self) -> None:
        """Register support tools and event handlers."""
        # Register tools
        self.register_tool("handle_ticket", self.handle_ticket)
        self.register_tool("faq_lookup", self.faq_lookup)
        self.register_tool("learn_from_resolution", self.learn_from_resolution)

        # Register event handlers
        self.register_event_handler("support.ticket_created", self.handle_ticket)

        logger.info(
            "SupportAgent initialized: %d built-in FAQ entries",
            len(BUILTIN_FAQ),
        )

    async def stop(self) -> None:
        """Clean up support agent resources."""
        logger.info(
            "SupportAgent stopping — handled=%d resolved=%d escalated=%d",
            self._tickets_handled,
            self._tickets_resolved,
            self._tickets_escalated,
        )

        # Learn summary
        await self.learn(
            observation=(
                f"SupportAgent processed {self._tickets_handled} tickets: "
                f"{self._tickets_resolved} resolved, {self._tickets_escalated} escalated."
            ),
            metadata={
                "tickets_handled": self._tickets_handled,
                "tickets_resolved": self._tickets_resolved,
                "tickets_escalated": self._tickets_escalated,
                "source": "support_agent",
            },
        )
        self.status = AgentStatus.STOPPED
        logger.info("SupportAgent stopped")

    # ── Ticket Handling ───────────────────────────────────────────────

    async def handle_ticket(self, ticket_data: Any) -> dict[str, Any]:
        """Receive and process a user support ticket.

        Resolution flow:
            1. Parse the issue from ticket data
            2. Check FAQ for direct match
            3. Search knowledge base for related solutions
            4. Generate AI response if knowledge found
            5. Escalate to human if AI cannot resolve

        Args:
            ticket_data: Dict or Event with ticket_id, user_id, issue, etc.

        Returns:
            Dict with resolution status, response, and actions taken.
        """
        self._tickets_handled += 1

        # Normalize input (supports Event objects or plain dicts)
        if hasattr(ticket_data, "payload"):
            ticket = getattr(ticket_data, "payload", {})
        elif isinstance(ticket_data, dict):
            ticket = ticket_data
        else:
            ticket = {"issue": str(ticket_data)}

        ticket_id = ticket.get("ticket_id", f"ticket_{self._tickets_handled}")
        user_id = ticket.get("user_id", "anonymous")
        issue = ticket.get("issue", ticket.get("question", ticket.get("description", "")))
        issue_lower = issue.strip().lower()

        logger.info(
            "Handling ticket %s from user %s: %s...",
            ticket_id,
            user_id,
            issue[:80],
        )

        # Phase 1: Direct FAQ lookup
        faq_answer = self.faq_lookup(issue_lower)
        if faq_answer:
            self._tickets_resolved += 1
            result = {
                "ticket_id": ticket_id,
                "user_id": user_id,
                "resolution": "faq",
                "response": faq_answer,
                "confidence": 0.95,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            logger.info("Ticket %s resolved via FAQ", ticket_id)
            await self._publish_resolution(ticket_id, user_id, "faq")
            return result

        # Phase 2: Search knowledge base
        knowledge = await self._search_knowledge_base(issue)
        if knowledge:
            response = await self._generate_response(issue, knowledge)
            confidence = (
                max((k.get("confidence", 0.5) if isinstance(k, dict) else 0.5) for k in knowledge) if knowledge else 0.5
            )

            if confidence >= 0.6:
                self._tickets_resolved += 1
                result = {
                    "ticket_id": ticket_id,
                    "user_id": user_id,
                    "resolution": "knowledge_base",
                    "response": response,
                    "confidence": round(confidence, 2),
                    "knowledge_sources": len(knowledge),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                logger.info(
                    "Ticket %s resolved via knowledge base (confidence=%.2f)",
                    ticket_id,
                    confidence,
                )

                # Learn from this resolution
                await self.learn_from_resolution(
                    ticket={"ticket_id": ticket_id, "issue": issue, "user_id": user_id},
                    resolution=result,
                )

                await self._publish_resolution(ticket_id, user_id, "knowledge_base")
                return result

        # Phase 3: Try AI generation even with low-confidence knowledge
        if knowledge:
            response = await self._generate_response(issue, knowledge)
            result = {
                "ticket_id": ticket_id,
                "user_id": user_id,
                "resolution": "ai_suggested",
                "response": response,
                "confidence": 0.3,
                "knowledge_sources": len(knowledge),
                "note": "Low confidence — suggested response, manual review recommended",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            logger.info(
                "Ticket %s: AI-suggested response (low confidence), recommending review",
                ticket_id,
            )
            return result

        # Phase 4: Escalate to human
        escalation = await self._escalate_to_human(
            {
                "ticket_id": ticket_id,
                "user_id": user_id,
                "issue": issue,
            }
        )

        result = {
            "ticket_id": ticket_id,
            "user_id": user_id,
            "resolution": "escalated",
            "response": escalation.get("message", "Your issue has been forwarded to our support team."),
            "escalation_id": escalation.get("escalation_id"),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        logger.info("Ticket %s escalated to human support", ticket_id)
        return result

    async def _search_knowledge_base(self, issue: str) -> list[Any]:
        """Search the Gaia knowledge base for relevant solutions.

        Uses the brain's vector index to find semantically related
        knowledge entries about the issue.

        Args:
            issue: The user's issue description.

        Returns:
            List of relevant knowledge entries (dicts or domain objects).
        """
        try:
            results = await self.ask_brain(query=issue, top_k=5)
            if results:
                logger.debug(
                    "Knowledge base search returned %d results for: %s...",
                    len(results),
                    issue[:60],
                )
                return results
        except Exception as exc:
            logger.warning("Knowledge base search failed: %s", exc)

        return []

    async def _generate_response(
        self,
        issue: str,
        knowledge: list[Any],
    ) -> str:
        """Generate a support response using AI based on the issue and knowledge.

        If a brain with AI capabilities is available, uses it to draft
        a contextual response. Otherwise, falls back to template-based response.

        Args:
            issue: The user's issue description.
            knowledge: List of knowledge entries relevant to the issue.

        Returns:
            A response string addressing the user's issue.
        """
        # Format knowledge for context
        knowledge_text = ""
        for i, k in enumerate(knowledge[:3], 1):
            if isinstance(k, dict):
                title = k.get("title", k.get("content", str(k)))[:100]
                content = k.get("content", k.get("description", ""))[:300]
                knowledge_text += f"{i}. {title}\n   {content}\n\n"
            else:
                knowledge_text += f"{i}. {str(k)[:300]}\n\n"

        # Try brain-based generation
        if self.brain is not None and hasattr(self.brain, "vector_index"):
            try:
                from app.ai.gateway.interfaces import AIRequest

                # Check if there's a gateway accessible through the brain
                gateway = getattr(self.brain, "_backend", None)
                if gateway and hasattr(gateway, "gateway"):
                    ai_gateway = gateway.gateway
                    if hasattr(ai_gateway, "chat"):
                        resp = await ai_gateway.chat(
                            AIRequest(
                                model="deepseek-chat",
                                prompt=(
                                    "You are a technical support agent. Answer the user's issue "
                                    "using ONLY the provided knowledge base context. Be concise, "
                                    "helpful, and professional."
                                ),
                                messages=[
                                    {
                                        "role": "user",
                                        "content": (
                                            f"Knowledge base context:\n{knowledge_text}\n"
                                            f"User issue: {issue}\n\n"
                                            f"Provide a helpful support response based on the knowledge above."
                                        ),
                                    },
                                ],
                                max_tokens=500,
                                temperature=0.3,
                            )
                        )
                        if resp.content and resp.finish_reason != "error":
                            return resp.content
            except Exception as exc:
                logger.debug("AI response generation failed, using template: %s", exc)

        # Template fallback
        response_parts = [
            f"Thank you for reaching out. I've looked into your issue about '{issue[:100]}'.",
        ]
        if knowledge_text:
            response_parts.append("\n\nBased on our knowledge base, here's what I found:")
            response_parts.append(f"\n{knowledge_text[:500]}")

        response_parts.append(
            "\n\nIf this doesn't fully resolve your issue, please provide more details "
            "and I'll be happy to help further."
        )

        return "".join(response_parts)

    async def _escalate_to_human(self, issue: dict[str, Any]) -> dict[str, Any]:
        """Escalate an issue to a human support agent.

        Creates an escalation record in Gaia knowledge and publishes
        an escalation event.

        Args:
            issue: Dict with ticket_id, user_id, issue.

        Returns:
            Dict with escalation_id and message for the user.
        """
        self._tickets_escalated += 1
        escalation_id = f"esc_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{self.agent_id[:4]}"

        # Record escalation in brain
        await self.learn(
            observation=(
                f"ESCALATION #{escalation_id}: Ticket {issue.get('ticket_id')} "
                f"from user {issue.get('user_id')} escalated. "
                f"Issue: {issue.get('issue', '')[:200]}"
            ),
            metadata={
                "escalation_id": escalation_id,
                "ticket_id": issue.get("ticket_id"),
                "user_id": issue.get("user_id"),
                "resolution": "escalated",
                "source": "support_agent",
            },
        )

        # Publish escalation event
        if self.event_bus is not None:
            try:
                from app.events.interfaces import Event

                await self.event_bus.publish(
                    Event(
                        type="support.ticket_escalated",
                        source=self.agent_id,
                        payload={
                            "escalation_id": escalation_id,
                            "ticket_id": issue.get("ticket_id"),
                            "user_id": issue.get("user_id"),
                            "issue": issue.get("issue", "")[:500],
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                )
            except Exception:
                logger.warning("SupportAgent failed to publish escalation event")

        return {
            "escalation_id": escalation_id,
            "message": (
                "Your issue has been forwarded to our senior support team. "
                "They will follow up with you within 24 hours. "
                f"Your escalation ID is: {escalation_id}"
            ),
        }

    # ── FAQ Lookup ───────────────────────────────────────────────────

    async def faq_lookup(self, question: str) -> str | None:
        """Look up a question in the built-in FAQ database.

        Matches using keyword overlap between the question and FAQ keys.

        Args:
            question: The user's question string (lowercased).

        Returns:
            The FAQ answer string, or None if no match found.
        """
        # Normalize: remove punctuation, split into words
        import re

        words = set(re.sub(r"[^\w\s]", "", question).lower().split())

        best_match = None
        best_score = 0.0

        for key, answer in BUILTIN_FAQ.items():
            key_words = set(key.replace("_", " ").split())
            overlap = len(words & key_words)
            if len(key_words) == 0:
                continue
            score = overlap / len(key_words)
            if score > best_score:
                best_score = score
                best_match = answer

        # Require at least 50% keyword overlap for a match
        if best_match and best_score >= 0.5:
            logger.debug("FAQ match found (score=%.2f): %s", best_score, question[:60])
            return best_match

        return None

    # ── Learning from Resolutions ─────────────────────────────────────

    async def learn_from_resolution(
        self,
        ticket: dict[str, Any],
        resolution: dict[str, Any],
    ) -> None:
        """Feed a successful resolution back to the Gaia brain for learning.

        Args:
            ticket: Original ticket data (issue, user_id, ticket_id).
            resolution: Resolution data (response, confidence, etc.).
        """
        issue = ticket.get("issue", "")
        response = resolution.get("response", "")
        confidence = resolution.get("confidence", 0.8)

        await self.learn(
            observation=(
                f"Support resolution: Ticket {ticket.get('ticket_id')} resolved. "
                f"Issue: {issue[:200]}. Resolution: {response[:200]}"
            ),
            metadata={
                "ticket_id": ticket.get("ticket_id"),
                "user_id": ticket.get("user_id"),
                "resolution_type": resolution.get("resolution", "unknown"),
                "confidence": confidence,
                "source": "support_agent",
                "knowledge_type": "support_resolution",
            },
        )

        logger.debug(
            "Learned from ticket %s resolution (confidence=%.2f)",
            ticket.get("ticket_id"),
            confidence,
        )

    # ── Delegation ────────────────────────────────────────────────────

    def set_backend_agent(self, agent: Any) -> None:
        """Set the backend agent for delegating bug-related issues."""
        self._backend_agent = agent

    def set_security_agent(self, agent: Any) -> None:
        """Set the security agent for delegating security-related issues."""
        self._security_agent = agent

    async def delegate_to_backend(self, issue: dict[str, Any]) -> None:
        """Delegate a bug-related ticket to the BackendAgent.

        Args:
            issue: Dict with ticket_id, user_id, issue description.
        """
        if self._backend_agent is not None:
            await self.delegate_to(
                self._backend_agent,
                task="handle_bug_report",
                params=issue,
            )
            logger.info(
                "Delegated ticket %s to BackendAgent",
                issue.get("ticket_id"),
            )
        else:
            logger.warning("No BackendAgent available for delegation")

    async def delegate_to_security(self, issue: dict[str, Any]) -> None:
        """Delegate a security-related ticket to the SecurityAgent.

        Args:
            issue: Dict with ticket_id, user_id, issue description.
        """
        if self._security_agent is not None:
            await self.delegate_to(
                self._security_agent,
                task="handle_security_issue",
                params=issue,
            )
            logger.info(
                "Delegated ticket %s to SecurityAgent",
                issue.get("ticket_id"),
            )
        else:
            logger.warning("No SecurityAgent available for delegation")

    # ── Event Publishing ──────────────────────────────────────────────

    async def _publish_resolution(
        self,
        ticket_id: str,
        user_id: str,
        resolution_type: str,
    ) -> None:
        """Publish a ticket resolution event.

        Args:
            ticket_id: The ID of the resolved ticket.
            user_id: The ID of the user who submitted the ticket.
            resolution_type: How the ticket was resolved (faq, knowledge_base, etc.).
        """
        if self.event_bus is None:
            return

        try:
            from app.events.interfaces import Event

            await self.event_bus.publish(
                Event(
                    type="support.ticket_resolved",
                    source=self.agent_id,
                    payload={
                        "ticket_id": ticket_id,
                        "user_id": user_id,
                        "resolution_type": resolution_type,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            )
        except Exception:
            logger.warning("SupportAgent failed to publish resolution event")

    # ── Public API ───────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Return support agent statistics.

        Returns:
            Dict with stats on tickets handled, resolved, and escalated.
        """
        return {
            "agent": self.agent_name,
            "role": self.agent_role,
            "status": self.status.value,
            "tickets_handled": self._tickets_handled,
            "tickets_resolved": self._tickets_resolved,
            "tickets_escalated": self._tickets_escalated,
            "resolution_rate": (round(self._tickets_resolved / max(self._tickets_handled, 1) * 100, 2)),
            "faq_entries": len(BUILTIN_FAQ),
        }
