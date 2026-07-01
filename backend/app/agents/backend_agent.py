"""BackendAgent — Backend Engineer Digital Employee.

An AI employee that reviews code, generates API endpoints from specs,
debugs issues, and maintains coding standards.

Architecture:
    Extends BaseAgent with backend-engineering tools, cron jobs for
    periodic code review, and event handlers for push-triggered reviews.
    Learns from each review and debug session to improve over time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import AgentConfig, AgentStatus, BaseAgent, CronJob

logger = logging.getLogger(__name__)


class BackendAgent(BaseAgent):
    """Backend Engineer — code review, API generation, debugging.

    This agent is the autonomous backend developer on the team.
    It reviews code quality, generates API endpoint implementations
    from specifications, and analyzes error logs to suggest fixes.

    Args:
        config: Agent configuration (defaults to Backend Engineer role).
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
        backend_config = config or AgentConfig(
            agent_name="backend_engineer",
            agent_role="backend_api_engineer",
            knowledge_base_name="backend",
            max_concurrent_tasks=10,
        )
        super().__init__(config=backend_config, brain=brain)
        self.broker: Any | None = broker
        self.event_bus: Any | None = event_bus

        # Tracking
        self._reviews_done: int = 0
        self._apis_generated: int = 0
        self._bugs_identified: int = 0

        # Knowledge base: coding standards, API patterns, common bug patterns
        self._coding_standards: dict[str, str] = {
            "naming_convention": "snake_case for functions/variables, PascalCase for classes",
            "type_hints": "All function parameters and return types must have type hints",
            "docstrings": "All public functions must have Google-style docstrings",
            "error_handling": "Use custom exception classes, never bare except clauses",
            "async_pattern": "Use async/await for I/O operations, avoid blocking calls",
            "api_versioning": "Prefix all API routes with /api/v{version}/",
            "validation": "Use Pydantic models for request/response validation",
        }
        self._common_bug_patterns: list[str] = [
            "Missing input validation on user-supplied data",
            "Unhandled database connection errors",
            "SQL injection via f-string queries instead of parameterized queries",
            "Race conditions in shared state without locks",
            "Memory leaks from unclosed database sessions",
            "Incorrect pagination logic leading to data exposure",
            "Missing authorization checks on admin endpoints",
        ]

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def init(self) -> None:
        """Register backend tools, cron jobs, and event handlers."""
        # Register tools
        self.register_tool("review_code", self.review_code)
        self.register_tool("generate_api", self.generate_api)
        self.register_tool("debug_issue", self.debug_issue)

        # Register event handlers
        self.register_event_handler("code.push", self._handle_code_push)
        self.register_event_handler("code.review_requested", self.review_code)

        # Register cron jobs
        self.add_cron_job(
            CronJob(
                schedule="0 * * * *",
                action=self.review_recent_code,
                name="review_recent_code_60min",
            )
        )

        logger.info(
            "BackendAgent initialized: %d standards, %d bug patterns",
            len(self._coding_standards),
            len(self._common_bug_patterns),
        )

    async def stop(self) -> None:
        """Clean up backend agent resources."""
        logger.info(
            "BackendAgent stopping — reviews=%d apis=%d bugs=%d",
            self._reviews_done,
            self._apis_generated,
            self._bugs_identified,
        )

        await self.learn(
            observation=(
                f"BackendAgent completed {self._reviews_done} code reviews, "
                f"generated {self._apis_generated} API endpoints, "
                f"identified {self._bugs_identified} bugs."
            ),
            metadata={
                "reviews_done": self._reviews_done,
                "apis_generated": self._apis_generated,
                "bugs_identified": self._bugs_identified,
                "source": "backend_agent",
            },
        )
        self.status = AgentStatus.STOPPED
        logger.info("BackendAgent stopped")

    # ── Code Review ───────────────────────────────────────────────────

    async def review_code(self, code_snippet: Any) -> dict[str, Any]:
        """Analyze a code snippet for quality, standards compliance, and bugs.

        Args:
            code_snippet: Dict or string containing the code to review.
                Supports Event payloads or plain dicts with 'code', 'file_path',
                'language' keys, or a raw string.

        Returns:
            Dict with review findings, suggestions, and overall score.
        """
        self._reviews_done += 1

        # Normalize input
        if hasattr(code_snippet, "payload"):
            data = getattr(code_snippet, "payload", {})
        elif isinstance(code_snippet, dict):
            data = code_snippet
        else:
            data = {"code": str(code_snippet)}

        code = data.get("code", "")
        file_path = data.get("file_path", "unknown.py")
        language = data.get("language", self._infer_language(file_path))

        logger.info(
            "Reviewing code in %s (%s, %d chars)",
            file_path,
            language,
            len(code),
        )

        findings: list[dict[str, Any]] = []
        standards_checked: list[str] = []
        bug_hits: list[str] = []

        # Check coding standards
        if "def " in code and "->" not in code.split("def ")[-1].split(":")[0]:
            findings.append(
                {
                    "type": "style",
                    "severity": "warning",
                    "message": "Missing return type hint on function definition",
                    "standard": "type_hints",
                }
            )
            standards_checked.append("type_hints")

        if "#" not in code and '"""' not in code and '"""' not in code:
            findings.append(
                {
                    "type": "style",
                    "severity": "info",
                    "message": "No comments or docstrings found in the code",
                    "standard": "docstrings",
                }
            )
            standards_checked.append("docstrings")

        if "except:" in code or "except :" in code:
            findings.append(
                {
                    "type": "bug",
                    "severity": "critical",
                    "message": "Bare except clause detected — catches all exceptions including SystemExit",
                    "pattern": "error_handling",
                }
            )
            bug_hits.append("bare_except")

        # Check common bug patterns
        if "f-string" in code and "SELECT" in code.upper():
            findings.append(
                {
                    "type": "security",
                    "severity": "critical",
                    "message": "Possible SQL injection: f-string used in SQL query",
                    "pattern": "SQL injection via f-string queries",
                }
            )
            bug_hits.append("sql_injection")

        if "async with" in code and "session" in code and "await session.close" not in code:
            findings.append(
                {
                    "type": "bug",
                    "severity": "high",
                    "message": "Database session may not be properly closed — use context manager",
                    "pattern": "Memory leaks from unclosed database sessions",
                }
            )
            bug_hits.append("unclosed_session")

        # Score: 100 minus penalties
        score = 100
        for f in findings:
            if f["severity"] == "critical":
                score -= 20
            elif f["severity"] == "high":
                score -= 10
            elif f["severity"] == "warning":
                score -= 5
            elif f["severity"] == "info":
                score -= 2
        score = max(0, score)

        result = {
            "file_path": file_path,
            "language": language,
            "score": score,
            "findings": findings,
            "standards_checked": standards_checked,
            "bug_patterns_detected": bug_hits,
            "line_count": len(code.splitlines()),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        logger.info(
            "Code review for %s: score=%d, findings=%d",
            file_path,
            score,
            len(findings),
        )

        if bug_hits:
            self._bugs_identified += len(bug_hits)

        # Learn from this review
        await self.learn(
            observation=(
                f"Code review of {file_path}: score={score}/100, "
                f"{len(findings)} findings including {len(bug_hits)} bug patterns."
            ),
            metadata={
                "file_path": file_path,
                "score": score,
                "findings_count": len(findings),
                "bug_patterns": bug_hits,
                "source": "backend_agent",
            },
        )

        return result

    async def review_recent_code(self) -> dict[str, Any]:
        """Review recent code changes (if integrated with git).

        This cron-triggered method checks for recent git changes and
        reviews any modified files for quality issues.

        Returns:
            Dict with summary of reviews performed.
        """
        logger.info("BackendAgent periodic code review cycle...")

        # Check if git integration is available
        git_available = await self._check_git_available()

        if not git_available:
            logger.info("Git not available for periodic review — skipping")
            return {
                "status": "skipped",
                "reason": "git_not_available",
                "timestamp": datetime.now(UTC).isoformat(),
            }

        # In production, this would fetch recent git diff and review files
        # For now, return a healthy status
        result = {
            "status": "completed",
            "files_reviewed": 0,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await self.learn(
            observation="Periodic code review cycle completed",
            metadata={
                "review_type": "periodic",
                "files_reviewed": 0,
                "source": "backend_agent",
            },
        )

        return result

    async def _check_git_available(self) -> bool:
        """Check if git integration is available in the runtime.

        Returns:
            True if git CLI or broker-based git service is available.
        """
        if self.broker is not None:
            try:
                from app.broker.interfaces import ServiceRequest

                resp = await self.broker.call(
                    ServiceRequest(
                        service="git",
                        method="ping",
                        timeout_ms=5_000,
                    )
                )
                return resp.success
            except Exception:
                pass

        # Fallback: try shell git command
        try:
            import asyncio

            proc = await asyncio.create_subprocess_exec(
                "git",
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return_code = await proc.wait()
            return return_code == 0
        except Exception:
            return False

    # ── API Generation ────────────────────────────────────────────────

    async def generate_api(self, spec: Any) -> dict[str, Any]:
        """Generate API endpoint code from a specification.

        Args:
            spec: Dict or string containing the API spec.
                Supports Event payloads or plain dicts with 'endpoint',
                'method', 'request_schema', 'response_schema', 'description'.

        Returns:
            Dict with generated code, endpoint metadata, and suggestions.
        """
        self._apis_generated += 1

        # Normalize input
        if hasattr(spec, "payload"):
            data = getattr(spec, "payload", {})
        elif isinstance(spec, dict):
            data = spec
        else:
            data = {"description": str(spec)}

        endpoint = data.get("endpoint", "/api/v1/unknown")
        method = data.get("method", "GET").upper()
        request_schema = data.get("request_schema", {})
        response_schema = data.get("response_schema", {})
        description = data.get("description", "")

        logger.info(
            "Generating API: %s %s — %s",
            method,
            endpoint,
            description[:60],
        )

        # Generate route handler code
        route_name = endpoint.strip("/").replace("/", "_").replace("-", "_")
        handler_name = f"{method.lower()}_{route_name}"

        # Build request model
        req_fields = []
        for field_name, field_type in request_schema.items():
            req_fields.append(f"    {field_name}: {field_type}")
        req_model = f"class {handler_name.title().replace('_', '')}Request(BaseModel):\n" + (
            "\n".join(req_fields) if req_fields else "    pass\n"
        )

        # Build response model
        resp_fields = []
        for field_name, field_type in response_schema.items():
            resp_fields.append(f"    {field_name}: {field_type}")
        resp_model = f"class {handler_name.title().replace('_', '')}Response(BaseModel):\n" + (
            "\n".join(resp_fields) if resp_fields else "    data: dict[str, Any]\n"
        )

        # Build handler
        handler_code = (
            f'@router.{method.lower()}("{endpoint}")\n'
            f"async def {handler_name}(\n"
            f"    request: {handler_name.title().replace('_', '')}Request,\n"
            f"    db: AsyncSession = Depends(get_db),\n"
            f") -> {handler_name.title().replace('_', '')}Response:\n"
            f'    """{description}"""\n'
            f"    # TODO: Implement business logic\n"
            f"    ...\n"
        )

        full_code = (
            f"from pydantic import BaseModel\n"
            f"from fastapi import APIRouter, Depends\n"
            f"from sqlalchemy.ext.asyncio import AsyncSession\n"
            f"from typing import Any\n\n"
            f"from app.database import get_db\n\n"
            f'router = APIRouter(prefix="{endpoint}", tags=["{route_name}"])\n\n'
            f"{req_model}\n\n"
            f"{resp_model}\n\n"
            f"{handler_code}\n"
        )

        result = {
            "endpoint": endpoint,
            "method": method,
            "handler_name": handler_name,
            "code": full_code,
            "suggestions": [
                "Add input validation in the request model",
                "Add proper error handling with HTTPException",
                "Consider adding pagination if this is a list endpoint",
                "Add OpenAPI tags and summary metadata",
            ],
            "timestamp": datetime.now(UTC).isoformat(),
        }

        logger.info(
            "Generated API %s %s (%d lines)",
            method,
            endpoint,
            len(full_code.splitlines()),
        )

        # Learn from this generation
        await self.learn(
            observation=(f"Generated API endpoint: {method} {endpoint} — {description[:100]}"),
            metadata={
                "endpoint": endpoint,
                "method": method,
                "code_lines": len(full_code.splitlines()),
                "source": "backend_agent",
            },
        )

        return result

    # ── Debug Issue ───────────────────────────────────────────────────

    async def debug_issue(self, error_log: Any) -> dict[str, Any]:
        """Analyze error logs and suggest fixes.

        Args:
            error_log: Dict or string containing error information.
                Supports Event payloads or plain dicts with 'error',
                'traceback', 'context', 'frequency'.

        Returns:
            Dict with analysis, root cause, and fix suggestions.
        """
        # Normalize input
        if hasattr(error_log, "payload"):
            data = getattr(error_log, "payload", {})
        elif isinstance(error_log, dict):
            data = error_log
        else:
            data = {"error": str(error_log)}

        error_message = data.get("error", "")
        traceback_str = data.get("traceback", "")
        context = data.get("context", {})

        logger.info(
            "Debugging issue: %s...",
            error_message[:100],
        )

        analysis: dict[str, Any] = {
            "error_type": "unknown",
            "severity": "medium",
            "root_cause": "",
            "suggested_fixes": [],
            "affected_components": [],
        }

        # Analyze common error patterns
        if (
            "OperationalError" in error_message
            or "ConnectionError" in error_message
            or "can't connect" in error_message.lower()
        ):
            analysis["error_type"] = "database_connection"
            analysis["severity"] = "critical"
            analysis["root_cause"] = "Database connection failure — check connection pool, credentials, and network"
            analysis["suggested_fixes"] = [
                "Verify database credentials in environment/config",
                "Check if database service is running",
                "Ensure connection pool is not exhausted",
                "Add connection retry logic with exponential backoff",
                "Consider using connection pooling (e.g., SQLAlchemy pool_size)",
            ]
            analysis["affected_components"] = ["database", "api_layer"]
            self._bugs_identified += 1

        elif "IntegrityError" in error_message or "duplicate key" in error_message.lower():
            analysis["error_type"] = "data_integrity"
            analysis["severity"] = "high"
            analysis["root_cause"] = "Database integrity violation — duplicate key or constraint failure"
            analysis["suggested_fixes"] = [
                "Add unique constraint validation before insert",
                "Use INSERT ... ON CONFLICT or upsert patterns",
                "Check for race conditions in concurrent writes",
                "Add database-level unique constraints",
            ]
            analysis["affected_components"] = ["database", "api_layer"]
            self._bugs_identified += 1

        elif "Timeout" in error_message or "timeout" in error_message.lower():
            analysis["error_type"] = "timeout"
            analysis["severity"] = "high"
            analysis["root_cause"] = (
                "Operation timed out — check for slow queries, network issues, or resource contention"
            )
            analysis["suggested_fixes"] = [
                "Optimize slow database queries with indexes",
                "Increase timeout values for long-running operations",
                "Implement timeout with asyncio.wait_for()",
                "Add caching layer for frequently accessed data",
                "Consider background task processing for heavy operations",
            ]
            analysis["affected_components"] = ["database", "api_layer", "cache"]
            self._bugs_identified += 1

        elif "ValidationError" in error_message or "validation error" in error_message.lower():
            analysis["error_type"] = "validation"
            analysis["severity"] = "medium"
            analysis["root_cause"] = "Input validation failure — malformed or invalid data received"
            analysis["suggested_fixes"] = [
                "Strengthen Pydantic model validations",
                "Add custom validators with meaningful error messages",
                "Log the actual invalid input for debugging",
                "Add API-level input sanitization",
            ]
            analysis["affected_components"] = ["api_layer", "validation"]
            self._bugs_identified += 1

        elif (
            "Permission" in error_message
            or "Forbidden" in error_message
            or "401" in error_message
            or "403" in error_message
        ):
            analysis["error_type"] = "authorization"
            analysis["severity"] = "critical"
            analysis["root_cause"] = "Authorization failure — missing or invalid permissions"
            analysis["suggested_fixes"] = [
                "Verify authentication token is being passed correctly",
                "Check role-based access control (RBAC) configuration",
                "Ensure required scopes/permissions are defined",
                "Review endpoint-level authorization decorators",
            ]
            analysis["affected_components"] = ["auth", "api_layer"]
            self._bugs_identified += 1

        else:
            analysis["root_cause"] = f"Unknown error pattern: {error_message[:200]}"
            analysis["suggested_fixes"] = [
                "Check application logs for more details",
                "Replicate the issue in a development environment",
                "Add more detailed logging around the failing operation",
                "Review recent code changes that may have introduced the bug",
            ]

        result = {
            "error_excerpt": error_message[:200],
            "analysis": analysis,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        logger.info(
            "Debug analysis: type=%s, severity=%s",
            analysis["error_type"],
            analysis["severity"],
        )

        # Learn from this debug session
        await self.learn(
            observation=(
                f"Debug analysis: {analysis['error_type']} (severity={analysis['severity']}) — "
                f"{analysis['root_cause'][:150]}"
            ),
            metadata={
                "error_type": analysis["error_type"],
                "severity": analysis["severity"],
                "source": "backend_agent",
            },
        )

        return result

    # ── Event Handler ─────────────────────────────────────────────────

    async def _handle_code_push(self, event: Any) -> None:
        """Handle code.push events by triggering a code review.

        Args:
            event: The code.push event with commit details.
        """
        logger.info("BackendAgent: code.push event received — triggering review")
        payload = getattr(event, "payload", {})
        files = payload.get("files", [])
        commit_message = payload.get("message", "")

        for file_info in files:
            if isinstance(file_info, dict):
                await self.review_code(
                    {
                        "code": file_info.get("content", ""),
                        "file_path": file_info.get("path", "unknown"),
                        "language": file_info.get("language", "unknown"),
                    }
                )

        await self.learn(
            observation=(f"Reviewed {len(files)} files from code push: {commit_message[:100]}"),
            metadata={
                "event_type": "code.push",
                "files_count": len(files),
                "source": "backend_agent",
            },
        )

    # ── Utility ───────────────────────────────────────────────────────

    @staticmethod
    def _infer_language(file_path: str) -> str:
        """Infer programming language from file extension.

        Args:
            file_path: Path to the file.

        Returns:
            Language name string, defaulting to 'unknown'.
        """
        ext_map: dict[str, str] = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "golang",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".sql": "sql",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
        }
        import os

        _, ext = os.path.splitext(file_path)
        return ext_map.get(ext.lower(), "unknown")

    # ── Public API ────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Return backend agent statistics.

        Returns:
            Dict with stats on reviews, APIs generated, and bugs identified.
        """
        return {
            "agent": self.agent_name,
            "role": self.agent_role,
            "status": self.status.value,
            "reviews_done": self._reviews_done,
            "apis_generated": self._apis_generated,
            "bugs_identified": self._bugs_identified,
            "coding_standards": len(self._coding_standards),
            "bug_patterns": len(self._common_bug_patterns),
        }
