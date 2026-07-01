"""QAAgent — Quality Assurance Engineer Digital Employee.

An AI employee that generates test cases, analyzes coverage reports,
detects regression risks, and ensures code quality.

Architecture:
    Extends BaseAgent with QA-specific tools and event handlers.
    Reacts to completed code reviews by generating tests for changed code.
    Maintains counters for tests generated and bugs found.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.base_agent import BaseAgent, AgentConfig, AgentStatus

logger = logging.getLogger(__name__)


class QAAgent(BaseAgent):
    """Quality Assurance Engineer — test generation, coverage analysis,
    regression detection.

    This agent ensures code quality by generating comprehensive tests,
    analyzing coverage reports for untested paths, and identifying
    what needs retesting when code changes.

    Args:
        config: Agent configuration (defaults to QA role).
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
        qa_config = config or AgentConfig(
            agent_name="qa_engineer",
            agent_role="quality_assurance_engineer",
            knowledge_base_name="qa",
            max_concurrent_tasks=10,
        )
        super().__init__(config=qa_config, brain=brain)
        self.broker: Any | None = broker
        self.event_bus: Any | None = event_bus

        # Tracking counters
        self._tests_generated: int = 0
        self._bugs_found: int = 0
        self._coverage_reports_analyzed: int = 0
        self._regression_checks_run: int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def init(self) -> None:
        """Register QA tools and event handlers."""
        # Register tools
        self.register_tool("generate_tests", self.generate_tests)
        self.register_tool("analyze_coverage", self.analyze_coverage)
        self.register_tool("regression_check", self.regression_check)

        # Register event handlers
        self.register_event_handler("code.review_completed", self._handle_review_completed)

        logger.info("QAAgent initialized")

    async def stop(self) -> None:
        """Clean up QA agent resources."""
        logger.info(
            "QAAgent stopping — tests=%d bugs=%d coverage=%d regressions=%d",
            self._tests_generated,
            self._bugs_found,
            self._coverage_reports_analyzed,
            self._regression_checks_run,
        )

        await self.learn(
            observation=(
                f"QAAgent generated {self._tests_generated} tests, "
                f"found {self._bugs_found} bugs, "
                f"analyzed {self._coverage_reports_analyzed} coverage reports, "
                f"ran {self._regression_checks_run} regression checks."
            ),
            metadata={
                "tests_generated": self._tests_generated,
                "bugs_found": self._bugs_found,
                "coverage_analyzed": self._coverage_reports_analyzed,
                "regression_checks": self._regression_checks_run,
                "source": "qa_agent",
            },
        )
        self.status = AgentStatus.STOPPED
        logger.info("QAAgent stopped")

    # ── Test Generation ───────────────────────────────────────────────

    async def generate_tests(self, code_path: Any) -> dict[str, Any]:
        """Analyze code and suggest test cases.

        Scans the code at the given path and generates pytest-compatible
        test suggestions covering the main logic paths.

        Args:
            code_path: Dict, Event payload, or string path to the code.
                Supports 'code_path', 'code', or 'file_path' keys.

        Returns:
            Dict with generated test suggestions and metadata.
        """
        self._tests_generated += 1

        # Normalize input
        if hasattr(code_path, "payload"):
            data = getattr(code_path, "payload", {})
        elif isinstance(code_path, dict):
            data = code_path
        else:
            data = {"code_path": str(code_path)}

        path = data.get("code_path", data.get("file_path", data.get("code", "unknown.py")))
        code = data.get("code", "")

        logger.info("Generating tests for: %s", path)

        suggestions: list[dict[str, Any]] = []
        test_functions: list[str] = []

        # Analyze code for functions and methods to test
        import re

        # Find function definitions
        functions = re.findall(r"async def (\w+)\s*\(|def (\w+)\s*\(", code)
        function_names = [f[0] or f[1] for f in functions if any(f)]

        # Find class definitions
        classes = re.findall(r"class (\w+)\s*[\(:]", code)

        for func_name in function_names:
            if func_name.startswith("_"):
                # Private function — internal, test indirectly
                suggestions.append({
                    "type": "indirect",
                    "target": func_name,
                    "priority": "low",
                    "reason": "Private function — test through public API",
                })
            elif "test_" in func_name:
                # It's already a test function
                suggestions.append({
                    "type": "existing_test",
                    "target": func_name,
                    "priority": "info",
                    "reason": "Already a test function",
                })
            else:
                # Generate a test suggestion
                test_code = (
                    f"async def test_{func_name}():\n"
                    f'    """Test {func_name} function."""\n'
                    f"    # Arrange\n"
                    f"    # TODO: Set up test data and mocks\n"
                    f"\n"
                    f"    # Act\n"
                    f"    result = await {func_name}(...)\n"
                    f"\n"
                    f"    # Assert\n"
                    f"    assert result is not None\n"
                    f'    assert isinstance(result, ...)\n'
                )
                test_functions.append(test_code)
                suggestions.append({
                    "type": "new_test",
                    "target": func_name,
                    "priority": "high",
                    "test_code": test_code,
                    "reason": f"Function '{func_name}' needs unit test coverage",
                })

        for cls_name in classes:
            suggestions.append({
                "type": "class_test",
                "target": cls_name,
                "priority": "medium",
                "reason": f"Class '{cls_name}' should have integration tests for its public methods",
            })

        # Generate edge case tests
        edge_case_tests: list[str] = []
        if functions:
            edge_case_tests = [
                "# Edge case: empty input",
                "# Edge case: None/null values",
                "# Edge case: maximum allowed values",
                "# Edge case: concurrent calls",
                "# Edge case: timeout scenarios",
            ]

        result = {
            "code_path": path,
            "total_suggestions": len(suggestions),
            "function_count": len(function_names),
            "class_count": len(classes),
            "suggestions": suggestions,
            "generated_test_code": test_functions,
            "edge_case_considerations": edge_case_tests,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Generated %d test suggestions for %s (%d functions, %d classes)",
            len(suggestions),
            path,
            len(function_names),
            len(classes),
        )

        # Learn from this generation
        await self.learn(
            observation=(
                f"Generated {len(suggestions)} test suggestions for {path}: "
                f"{len(function_names)} functions, {len(classes)} classes"
            ),
            metadata={
                "code_path": path,
                "suggestions": len(suggestions),
                "functions": len(function_names),
                "classes": len(classes),
                "source": "qa_agent",
            },
        )

        return result

    # ── Coverage Analysis ─────────────────────────────────────────────

    async def analyze_coverage(self, report: Any) -> dict[str, Any]:
        """Analyze a coverage report to identify untested paths.

        Args:
            report: Dict, Event payload, or string with coverage data.
                Supports 'coverage_data', 'report_path', 'lines',
                'branches' keys for structured data.

        Returns:
            Dict with coverage analysis, gaps, and recommendations.
        """
        self._coverage_reports_analyzed += 1

        # Normalize input
        if hasattr(report, "payload"):
            data = getattr(report, "payload", {})
        elif isinstance(report, dict):
            data = report
        else:
            data = {"report_path": str(report)}

        report_path = data.get("report_path", data.get("path", "unknown"))
        lines_data = data.get("lines", data.get("line_rate", None))
        branches_data = data.get("branches", data.get("branch_rate", None))

        logger.info("Analyzing coverage report: %s", report_path)

        # Parse coverage metrics
        line_coverage = None
        branch_coverage = None

        if isinstance(lines_data, (int, float)):
            line_coverage = float(lines_data)
        if isinstance(branches_data, (int, float)):
            branch_coverage = float(branches_data)

        # If no structured data, try to parse raw text
        if line_coverage is None and isinstance(data.get("raw", ""), str):
            import re
            raw = data["raw"]
            match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", raw)
            if match:
                line_coverage = int(match.group(1)) / 100.0

        # Identify untested paths
        untested_paths: list[str] = []

        if line_coverage is not None:
            if line_coverage < 0.5:
                untested_paths.append(
                    "Critical: Overall coverage below 50%% — major testing gaps exist"
                )
            elif line_coverage < 0.7:
                untested_paths.append(
                    "Warning: Coverage below 70%% — significant untested code paths"
                )
            elif line_coverage < 0.8:
                untested_paths.append(
                    "Info: Coverage below 80%% — some code paths remain untested"
                )

        if branch_coverage is not None:
            if branch_coverage < 0.5:
                untested_paths.append(
                    "Critical: Branch coverage below 50%% — many conditional paths untested"
                )
            elif branch_coverage < 0.7:
                untested_paths.append(
                    "Warning: Branch coverage below 70%% — significant conditional gaps"
                )

        recommendations: list[str] = []
        if untested_paths:
            recommendations = [
                "Add unit tests for uncovered functions",
                "Add integration tests for critical user flows",
                "Consider property-based testing for complex logic",
                "Add edge case tests for boundary conditions",
                "Implement contract tests for API endpoints",
            ]

        result = {
            "report_path": report_path,
            "line_coverage": line_coverage,
            "branch_coverage": branch_coverage,
            "untested_paths": untested_paths,
            "recommendations": recommendations,
            "needs_improvement": len(untested_paths) > 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Coverage analysis: line=%.1f%%, branch=%s",
            (line_coverage * 100) if line_coverage is not None else None,
            (f"{branch_coverage * 100:.1f}%" if branch_coverage is not None else "N/A"),
        )

        # Learn from this analysis
        await self.learn(
            observation=(
                f"Coverage analysis of {report_path}: "
                f"line_coverage={line_coverage}, "
                f"branch_coverage={branch_coverage}, "
                f"{len(untested_paths)} gaps identified"
            ),
            metadata={
                "report_path": report_path,
                "line_coverage": line_coverage,
                "branch_coverage": branch_coverage,
                "gaps_count": len(untested_paths),
                "source": "qa_agent",
            },
        )

        return result

    # ── Regression Check ──────────────────────────────────────────────

    async def regression_check(self, changes: Any) -> dict[str, Any]:
        """Identify what needs retesting based on code changes.

        Analyzes a set of changes (files, modules, dependencies) and
        determines the regression risk and recommended test scope.

        Args:
            changes: Dict, Event payload, or string describing changes.
                Supports 'files', 'modules', 'dependencies', 'description'.

        Returns:
            Dict with regression analysis, risk assessment, and test plan.
        """
        self._regression_checks_run += 1

        # Normalize input
        if hasattr(changes, "payload"):
            data = getattr(changes, "payload", {})
        elif isinstance(changes, dict):
            data = changes
        else:
            data = {"description": str(changes)}

        files = data.get("files", data.get("changed_files", []))
        modules = data.get("modules", data.get("affected_modules", []))
        description = data.get("description", "")

        logger.info(
            "Running regression check: %d files, %d modules",
            len(files) if isinstance(files, list) else 1,
            len(modules) if isinstance(modules, list) else 1,
        )

        # Assess risk levels
        high_risk_modules: list[str] = []
        medium_risk_modules: list[str] = []
        low_risk_modules: list[str] = []

        risk_keywords_high = ["auth", "payment", "database", "security", "core", "middleware"]
        risk_keywords_medium = ["api", "service", "handler", "controller", "route"]

        all_items = list(files) + list(modules) if isinstance(files, list) and isinstance(modules, list) else []

        for item in all_items:
            item_lower = item.lower() if isinstance(item, str) else ""
            if any(kw in item_lower for kw in risk_keywords_high):
                high_risk_modules.append(item)
            elif any(kw in item_lower for kw in risk_keywords_medium):
                medium_risk_modules.append(item)
            else:
                low_risk_modules.append(item)

        # Determine overall risk
        if high_risk_modules:
            overall_risk = "high"
        elif medium_risk_modules:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        # Generate test plan
        test_plan: list[str] = []

        if high_risk_modules:
            test_plan.append("Full regression suite: ALL tests must pass")
            test_plan.append("Integration tests for affected high-risk modules")
            test_plan.append("Smoke tests on critical user flows")

        if medium_risk_modules:
            test_plan.append("Unit tests for all changed functions")
            test_plan.append("Integration tests for affected API endpoints")

        test_plan.append("Lint and type checking on all changed files")
        test_plan.append("Verify no new warnings introduced")

        if overall_risk == "low":
            test_plan.append("Basic smoke test sufficient")

        result = {
            "overall_risk": overall_risk,
            "high_risk_modules": high_risk_modules,
            "medium_risk_modules": medium_risk_modules,
            "low_risk_modules": low_risk_modules,
            "test_plan": test_plan,
            "description": description[:200] if description else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Regression check: risk=%s, high=%d, medium=%d, low=%d",
            overall_risk,
            len(high_risk_modules),
            len(medium_risk_modules),
            len(low_risk_modules),
        )

        # Learn from this check
        await self.learn(
            observation=(
                f"Regression check: risk={overall_risk}, "
                f"{len(high_risk_modules)} high-risk modules, "
                f"test plan has {len(test_plan)} items"
            ),
            metadata={
                "overall_risk": overall_risk,
                "high_risk_count": len(high_risk_modules),
                "test_plan_items": len(test_plan),
                "source": "qa_agent",
            },
        )

        return result

    # ── Event Handler ─────────────────────────────────────────────────

    async def _handle_review_completed(self, event: Any) -> None:
        """Handle code.review_completed events by generating tests.

        Args:
            event: The review completed event with details about
                   the reviewed code.
        """
        logger.info("QAAgent: code.review_completed event received")
        payload = getattr(event, "payload", {})
        code_path = payload.get("file_path", payload.get("code_path", "unknown"))
        code = payload.get("code", "")

        await self.generate_tests({
            "code_path": code_path,
            "code": code,
        })

        await self.learn(
            observation=(
                f"Generated tests following code review of {code_path}"
            ),
            metadata={
                "event_type": "code.review_completed",
                "code_path": code_path,
                "source": "qa_agent",
            },
        )

    # ── Public API ────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Return QA agent statistics.

        Returns:
            Dict with stats on tests generated, bugs found, etc.
        """
        return {
            "agent": self.agent_name,
            "role": self.agent_role,
            "status": self.status.value,
            "tests_generated": self._tests_generated,
            "bugs_found": self._bugs_found,
            "coverage_reports_analyzed": self._coverage_reports_analyzed,
            "regression_checks_run": self._regression_checks_run,
        }
