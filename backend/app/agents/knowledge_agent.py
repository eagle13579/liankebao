"""KnowledgeAgent — Knowledge Engineer Digital Employee.

An AI employee that generates documentation, creates Architecture Decision
Records (ADRs), summarizes code changes, and manages the knowledge base.

Architecture:
    Extends BaseAgent with knowledge-management tools and event handlers.
    Primarily writes to the Gaia Evolution Brain knowledge base for
    persistence. Generates release notes on production deployments.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.base_agent import BaseAgent, AgentConfig, AgentStatus

logger = logging.getLogger(__name__)


class KnowledgeAgent(BaseAgent):
    """Knowledge Engineer — documentation generation, ADR creation,
    change summarization, knowledge base management.

    This agent is the autonomous documentarian. It ensures that code
    changes are properly documented, architectural decisions are recorded,
    and the team's collective knowledge is captured in the Gaia Brain.

    Args:
        config: Agent configuration (defaults to Knowledge role).
        brain: GaiaEvolutionBrain reference for knowledge storage.
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
        knowledge_config = config or AgentConfig(
            agent_name="knowledge_engineer",
            agent_role="knowledge_engineer",
            knowledge_base_name="knowledge",
            max_concurrent_tasks=10,
        )
        super().__init__(config=knowledge_config, brain=brain)
        self.broker: Any | None = broker
        self.event_bus: Any | None = event_bus

        # Tracking
        self._docs_generated: int = 0
        self._adrs_created: int = 0
        self._summaries_written: int = 0
        self._release_notes_generated: int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def init(self) -> None:
        """Register knowledge tools and event handlers."""
        # Register tools
        self.register_tool("generate_docs", self.generate_docs)
        self.register_tool("create_adr", self.create_adr)
        self.register_tool("summarize_changes", self.summarize_changes)

        # Register event handlers
        self.register_event_handler("deploy.production", self._handle_deploy_production)

        logger.info("KnowledgeAgent initialized")

    async def stop(self) -> None:
        """Clean up knowledge agent resources."""
        logger.info(
            "KnowledgeAgent stopping — docs=%d adrs=%d summaries=%d releases=%d",
            self._docs_generated,
            self._adrs_created,
            self._summaries_written,
            self._release_notes_generated,
        )

        await self.learn(
            observation=(
                f"KnowledgeAgent generated {self._docs_generated} docs, "
                f"created {self._adrs_created} ADRs, "
                f"wrote {self._summaries_written} summaries, "
                f"produced {self._release_notes_generated} release notes."
            ),
            metadata={
                "docs_generated": self._docs_generated,
                "adrs_created": self._adrs_created,
                "summaries_written": self._summaries_written,
                "release_notes": self._release_notes_generated,
                "source": "knowledge_agent",
            },
        )
        self.status = AgentStatus.STOPPED
        logger.info("KnowledgeAgent stopped")

    # ── Documentation Generation ──────────────────────────────────────

    async def generate_docs(self, code_path: Any) -> dict[str, Any]:
        """Generate or update documentation for code at the given path.

        Analyzes the code and produces README-style documentation
        including usage examples, API references, and architecture notes.

        Args:
            code_path: Dict, Event payload, or string path to the code.
                Supports 'code_path', 'code', 'file_path', 'module_name'.

        Returns:
            Dict with generated documentation and metadata.
        """
        self._docs_generated += 1

        # Normalize input
        if hasattr(code_path, "payload"):
            data = getattr(code_path, "payload", {})
        elif isinstance(code_path, dict):
            data = code_path
        else:
            data = {"code_path": str(code_path)}

        path = data.get("code_path", data.get("file_path", data.get("path", "unknown")))
        code = data.get("code", "")
        module_name = data.get("module_name", data.get("name", ""))

        logger.info("Generating documentation for: %s", path)

        import re

        # Extract module docstring
        existing_doc = ""
        doc_match = re.search(r'"""(.*?)"""', code, re.DOTALL)
        if doc_match:
            existing_doc = doc_match.group(1).strip()

        # Extract classes
        classes = re.findall(r"class (\w+)\s*[\(:](?:.*?):\s*\"\"\"(.*?)\"\"\"", code, re.DOTALL)
        class_docs: list[dict[str, str]] = []
        for cls_name, cls_doc in classes:
            class_docs.append({
                "name": cls_name,
                "doc": cls_doc.strip() if cls_doc else "No description provided.",
            })

        # Extract public functions
        functions = re.findall(
            r"(?:async )?def (\w+)\s*\((.*?)\)(?:\s*->\s*(\S+))?\s*:\s*(?:\"\"\"(.*?)\"\"\")?",
            code, re.DOTALL,
        )
        func_docs: list[dict[str, str]] = []
        for func_name, params_str, return_type, func_doc in functions:
            if not func_name.startswith("_"):
                # Parse parameters
                params = [p.strip().split(":")[0].strip() for p in params_str.split(",") if p.strip() and "self" not in p]
                func_docs.append({
                    "name": func_name,
                    "params": params,
                    "return_type": return_type or "None",
                    "doc": func_doc.strip() if func_doc else "No description provided.",
                })

        # Build documentation
        title = module_name or path.replace("/", ".").replace("\\", ".").replace(".py", "")
        doc_lines: list[str] = [
            f"# {title}",
            "",
        ]

        if existing_doc:
            doc_lines.append(existing_doc)
            doc_lines.append("")

        if class_docs:
            doc_lines.append("## Classes")
            doc_lines.append("")
            for cls in class_docs:
                doc_lines.append(f"### `{cls['name']}`")
                doc_lines.append("")
                doc_lines.append(cls["doc"])
                doc_lines.append("")

        if func_docs:
            doc_lines.append("## Functions")
            doc_lines.append("")
            for func in func_docs:
                params_str = ", ".join(func["params"]) if func["params"] else ""
                doc_lines.append(f"### `{func['name']}({params_str}) -> {func['return_type']}`")
                doc_lines.append("")
                doc_lines.append(func["doc"])
                doc_lines.append("")

        if not class_docs and not func_docs and not existing_doc:
            doc_lines.append("*No documentation could be auto-generated. Add docstrings to your code.*")
            doc_lines.append("")

        doc_lines.append("---")
        doc_lines.append(f"*Auto-generated by KnowledgeAgent on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*")
        doc_lines.append("")

        documentation = "\n".join(doc_lines)

        result = {
            "code_path": path,
            "title": title,
            "documentation": documentation,
            "classes_documented": len(class_docs),
            "functions_documented": len(func_docs),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Generated docs for %s: %d classes, %d functions (%d lines)",
            path,
            len(class_docs),
            len(func_docs),
            len(documentation.splitlines()),
        )

        # Store documentation in Gaia Brain
        await self.learn(
            observation=(
                f"Generated documentation for {path}: {len(class_docs)} classes, "
                f"{len(func_docs)} functions documented"
            ),
            metadata={
                "code_path": path,
                "classes": len(class_docs),
                "functions": len(func_docs),
                "doc_lines": len(documentation.splitlines()),
                "knowledge_type": "documentation",
                "source": "knowledge_agent",
            },
        )

        return result

    # ── Architecture Decision Records ─────────────────────────────────

    async def create_adr(self, title: Any, decision: str = "", context: str = "") -> dict[str, Any]:
        """Create an Architecture Decision Record (ADR).

        ADRs capture important architectural decisions for future
        reference following the MADR (Markdown ADR) format.

        Args:
            title: Dict, Event payload, or string title of the ADR.
            decision: The decision that was made.
            context: The context and rationale for the decision.

        Returns:
            Dict with the ADR content and metadata.
        """
        self._adrs_created += 1

        # Normalize input
        if hasattr(title, "payload"):
            data = getattr(title, "payload", {})
            title_str = data.get("title", str(title))
            decision = data.get("decision", decision)
            context = data.get("context", context)
        elif isinstance(title, dict):
            title_str = title.get("title", "Untitled Decision")
            decision = title.get("decision", decision)
            context = title.get("context", context)
        else:
            title_str = str(title)

        logger.info("Creating ADR: %s", title_str)

        # ADR number based on count
        adr_number = self._adrs_created

        # Generate status
        status = "proposed"

        # Build ADR in MADR format
        adr_body = (
            f"# ADR-{adr_number:03d}: {title_str}\n\n"
            f"- **Status:** {status}\n"
            f"- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"- **Author:** KnowledgeAgent (AI Digital Employee)\n\n"
            f"## Context\n\n"
            f"{context or 'No context provided. This decision was made based on technical requirements.'}\n\n"
            f"## Decision\n\n"
            f"{decision or 'The specific decision details were not recorded at the time of creation.'}\n\n"
            f"## Consequences\n\n"
            f"- This decision affects the overall system architecture.\n"
            f"- Future contributors should review this ADR before making related changes.\n"
            f"- This ADR may be updated as more information becomes available.\n\n"
            f"## Compliance\n\n"
            f"- This decision follows the project's architectural principles.\n"
            f"- Regular reviews should verify ongoing alignment with this decision.\n\n"
            f"---\n"
            f"*Created by KnowledgeAgent on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n"
        )

        result = {
            "adr_number": adr_number,
            "title": title_str,
            "status": status,
            "body": adr_body,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("ADR-%03d created: %s", adr_number, title_str)

        # Store ADR in Gaia Brain for permanent record
        await self.learn(
            observation=(
                f"ADR-{adr_number:03d}: {title_str} — {status}. "
                f"Context: {context[:100] if context else 'Not provided'}"
            ),
            metadata={
                "adr_number": adr_number,
                "title": title_str,
                "status": status,
                "knowledge_type": "architecture_decision_record",
                "source": "knowledge_agent",
            },
        )

        return result

    # ── Change Summarization ──────────────────────────────────────────

    async def summarize_changes(self, diff: Any) -> dict[str, Any]:
        """Summarize code changes (diff) in natural language.

        Analyzes a diff or change description and produces a human-readable
        summary suitable for changelogs or release notes.

        Args:
            diff: Dict, Event payload, or string diff/content.
                Supports 'diff', 'changes', 'files', 'commit_message'.

        Returns:
            Dict with summary, impact analysis, and categorized changes.
        """
        self._summaries_written += 1

        # Normalize input
        if hasattr(diff, "payload"):
            data = getattr(diff, "payload", {})
        elif isinstance(diff, dict):
            data = diff
        else:
            data = {"diff": str(diff)}

        diff_content = data.get("diff", data.get("changes", data.get("content", "")))
        files = data.get("files", data.get("changed_files", []))
        commit_message = data.get("commit_message", data.get("message", ""))

        logger.info(
            "Summarizing changes: %d files, commit: %s",
            len(files) if isinstance(files, list) else 1,
            commit_message[:80],
        )

        import re

        # Categorize changes
        categories: dict[str, list[str]] = {
            "features": [],
            "bug_fixes": [],
            "refactors": [],
            "dependencies": [],
            "documentation": [],
            "tests": [],
            "config": [],
            "other": [],
        }

        file_list = files if isinstance(files, list) else []
        if not file_list and diff_content:
            # Try to extract file paths from diff
            file_matches = re.findall(r"^\+\+\+\s+(?:b/)?(.+)$", diff_content, re.MULTILINE)
            file_list = file_matches

        for f in file_list:
            f_lower = f.lower() if isinstance(f, str) else str(f).lower()
            if any(kw in f_lower for kw in ["feat", "feature", "add ", "new "]):
                categories["features"].append(str(f))
            elif any(kw in f_lower for kw in ["fix", "bug", "hotfix", "patch"]):
                categories["bug_fixes"].append(str(f))
            elif any(kw in f_lower for kw in ["refactor", "clean", "rename", "move"]):
                categories["refactors"].append(str(f))
            elif any(kw in f_lower for kw in ["dep", "requirement", "package", "pip"]):
                categories["dependencies"].append(str(f))
            elif any(kw in f_lower for kw in ["doc", "readme", "md"]):
                categories["documentation"].append(str(f))
            elif any(kw in f_lower for kw in ["test", "spec", "mock"]):
                categories["tests"].append(str(f))
            elif "config" in f_lower:
                categories["config"].append(str(f))
            else:
                categories["other"].append(str(f))

        # Count changes in diff
        additions = len(re.findall(r"^\+", diff_content, re.MULTILINE)) if diff_content else 0
        deletions = len(re.findall(r"^-", diff_content, re.MULTILINE)) if diff_content else 0

        # Build summary
        summary_parts: list[str] = []

        if commit_message:
            summary_parts.append(f"**{commit_message}**\n")

        summary_parts.append(f"**Files changed:** {len(file_list)}")

        if additions or deletions:
            summary_parts.append(f"**Changes:** +{additions}/-{deletions} lines")

        # Add category summaries
        for cat, cat_files in categories.items():
            if cat_files:
                human_cat = cat.replace("_", " ").title()
                summary_parts.append(f"\n**{human_cat}:**")
                for f in cat_files[:5]:  # Show top 5 per category
                    summary_parts.append(f"- `{f}`")
                if len(cat_files) > 5:
                    summary_parts.append(f"- *...and {len(cat_files) - 5} more*")

        summary = "\n".join(summary_parts)

        result = {
            "summary": summary,
            "commit_message": commit_message,
            "files_changed": len(file_list),
            "additions": additions,
            "deletions": deletions,
            "categories": {k: v for k, v in categories.items() if v},
            "impact_areas": list(categories.keys()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Change summary: %d files, +%d/-%d lines, %d categories",
            len(file_list),
            additions,
            deletions,
            sum(1 for v in categories.values() if v),
        )

        # Store summary in knowledge base
        await self.learn(
            observation=(
                f"Change summary: {len(file_list)} files, +{additions}/-{deletions} lines. "
                f"Commit: {commit_message[:100]}"
            ),
            metadata={
                "files_changed": len(file_list),
                "additions": additions,
                "deletions": deletions,
                "categories": list(categories.keys()),
                "knowledge_type": "change_summary",
                "source": "knowledge_agent",
            },
        )

        return result

    # ── Event Handler ─────────────────────────────────────────────────

    async def _handle_deploy_production(self, event: Any) -> None:
        """Handle deploy.production events by generating release notes.

        Creates comprehensive release notes summarizing the changes
        included in a production deployment.

        Args:
            event: The deployment event with details about the release.
        """
        logger.info("KnowledgeAgent: deploy.production event — generating release notes")
        payload = getattr(event, "payload", {})

        version = payload.get("version", payload.get("tag", f"v{datetime.now(timezone.utc).strftime('%Y.%m.%d.%H%M')}"))
        changes = payload.get("changes", payload.get("commits", []))
        description = payload.get("description", "")

        # Summarize changes
        change_summary = await self.summarize_changes({
            "files": changes,
            "commit_message": description or f"Release {version}",
        })

        # Build release notes
        release_notes_body = (
            f"# Release {version}\n\n"
            f"- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"- **Generated by:** KnowledgeAgent\n\n"
            f"## Overview\n\n"
            f"{description or 'Production deployment containing multiple improvements and fixes.'}\n\n"
            f"## Changes\n\n"
            f"{change_summary['summary']}\n\n"
            f"## Files Changed\n\n"
            f"Total: {change_summary['files_changed']} files (+{change_summary['additions']}/-{change_summary['deletions']} lines)\n\n"
            f"---\n"
            f"*Auto-generated by KnowledgeAgent*\n"
        )

        self._release_notes_generated += 1

        result = {
            "version": version,
            "release_notes": release_notes_body,
            "change_summary": change_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Publish release notes event
        if self.event_bus is not None:
            try:
                from app.events.interfaces import Event

                await self.event_bus.publish(Event(
                    type="docs.release_notes_generated",
                    source=self.agent_id,
                    payload=result,
                ))
            except Exception:
                logger.warning("KnowledgeAgent failed to publish release notes event")

        # Store in knowledge base
        await self.learn(
            observation=(
                f"Release notes generated for {version}: "
                f"{change_summary['files_changed']} files changed, "
                f"{change_summary['additions']} additions, "
                f"{change_summary['deletions']} deletions"
            ),
            metadata={
                "version": version,
                "files_changed": change_summary["files_changed"],
                "knowledge_type": "release_notes",
                "source": "knowledge_agent",
            },
        )

        logger.info("Release notes generated for %s", version)

    # ── Public API ────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Return knowledge agent statistics.

        Returns:
            Dict with stats on docs, ADRs, summaries, and releases.
        """
        return {
            "agent": self.agent_name,
            "role": self.agent_role,
            "status": self.status.value,
            "docs_generated": self._docs_generated,
            "adrs_created": self._adrs_created,
            "summaries_written": self._summaries_written,
            "release_notes_generated": self._release_notes_generated,
        }
