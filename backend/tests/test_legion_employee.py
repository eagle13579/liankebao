"""Tests for LegionEmployee adapter — connecting code agents to 记忆宫殿 legion employees.

Tests cover:
    1. LegionEmployee loads correctly from existing employee directories
    2. Personality traits are accessible from soul-injection.yaml
    3. Mental models are loaded (Daoist wisdom models)
    4. memorize() writes to memory.db
    5. remember() retrieves from memory.db
    6. learn() feeds to both memory and (mock) Gaia Brain
    7. create_legion_agent() returns properly connected employee+agent
    8. All 9 employee mappings resolve correctly with valid directories
    9. Graceful fallback when employee directory is missing
    10. Dual-memory (own memory.db + Gaia Brain) work correctly
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Module under test ─────────────────────────────────────────────

from app.agents.legion_employee import (
    LEGION_PATH,
    LegionEmployee,
    _resolve_employee_dir,
    _safe_load_yaml,
    _query_memory_db,
    _write_memory_db,
)
from app.agents.employee_profiles import (
    EMPLOYEE_AGENT_MAP,
    create_legion_agent,
    create_all_legion_agents,
)
from app.agents.base_agent import BaseAgent

# ── Constants ─────────────────────────────────────────────────────

# The 9 legion employee IDs we expect to connect
EXPECTED_EMPLOYEES = [
    "emp-烛龙",
    "emp-狴犴",
    "emp-獬豸",
    "emp-乘黄",
    "emp-文鳐",
    "emp-开明兽",
    "emp-计然",
    "emp-䑏疏",
    "emp-白泽",  # Resolves to emp-白泽-3c6ee223 on disk
]

EXPECTED_AGENT_TYPES = [
    "backend",
    "qa",
    "security",
    "growth",
    "knowledge",
    "architecture",
    "data",
    "sre",
    "support",
]


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _legion_exists() -> bool:
    """Check if the legion path exists on this system."""
    return os.path.isdir(LEGION_PATH)


# ═══════════════════════════════════════════════════════════════════
# 1. Employee directory resolution
# ═══════════════════════════════════════════════════════════════════


class TestEmployeeDirectoryResolution:
    """Verify that employee IDs resolve to real directories."""

    def test_legion_path_exists(self):
        """The legion employees directory must exist."""
        assert _legion_exists(), (
            f"LEGION_PATH does not exist: {LEGION_PATH}\n"
            "Tests requiring real employee files will be skipped."
        )

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_all_expected_employees_resolve(self):
        """Each of the 9 expected employee IDs must resolve to a directory."""
        for emp_id in EXPECTED_EMPLOYEES:
            resolved = _resolve_employee_dir(emp_id)
            assert resolved, f"Failed to resolve employee directory for '{emp_id}'"
            assert os.path.isdir(resolved), (
                f"Resolved path is not a directory: {resolved} (from {emp_id})"
            )

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_bian_resolves_to_base(self):
        """emp-狴犴 should resolve to emp-狴犴 (not -P8 variant)."""
        resolved = _resolve_employee_dir("emp-狴犴")
        assert "emp-狴犴" in resolved
        # Should prefer shortest name (no suffix)
        assert resolved.endswith("emp-狴犴") or resolved.endswith("emp-狴犴/")

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_baize_resolves_with_suffix(self):
        """emp-白泽 should resolve to emp-白泽-3c6ee223 (the only baize dir)."""
        resolved = _resolve_employee_dir("emp-白泽")
        assert resolved, "emp-白泽 should resolve"
        assert "-3c6ee223" in resolved or "白泽" in resolved

    def test_missing_employee_returns_empty(self):
        """Unknown employee IDs should return empty string."""
        resolved = _resolve_employee_dir("emp-不存在的")
        assert resolved == ""


# ═══════════════════════════════════════════════════════════════════
# 2. YAML loading (handles custom tags, broken syntax)
# ═══════════════════════════════════════════════════════════════════


class TestSafeYamlLoading:
    """Verify YAML loading handles the legion's custom formats."""

    def test_load_missing_file_returns_empty(self):
        result = _safe_load_yaml("/nonexistent/path.yaml")
        assert result == {}

    def test_load_empty_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            path = f.name
        try:
            result = _safe_load_yaml(path)
            assert result == {}
        finally:
            os.unlink(path)

    def test_load_simple_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("name: test\nvalue: 42\n")
            path = f.name
        try:
            result = _safe_load_yaml(path)
            assert result == {"name": "test", "value": 42}
        finally:
            os.unlink(path)

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_load_real_employee_yaml(self):
        """Load an actual employee.yaml from the legion."""
        for emp_id in ["emp-烛龙", "emp-狴犴", "emp-獬豸"]:
            resolved = _resolve_employee_dir(emp_id)
            if not resolved:
                continue
            path = f"{resolved}/employee.yaml"
            data = _safe_load_yaml(path)
            assert isinstance(data, dict), f"employee.yaml for {emp_id} should be dict"
            # Every employee should have an employee_id or name
            has_id = "employee_id" in data or "name" in data
            assert has_id, f"employee.yaml for {emp_id} missing employee_id or name"

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_load_real_soul_injection_yaml(self):
        """Load actual soul-injection.yaml which has complex structure."""
        resolved = _resolve_employee_dir("emp-烛龙")
        if not resolved:
            pytest.skip("emp-烛龙 not found")
        path = f"{resolved}/soul-injection.yaml"
        data = _safe_load_yaml(path)
        assert isinstance(data, dict), "soul-injection.yaml should be a dict"
        # Should have mental_models, personality, capabilities
        assert "mental_models" in data or "personality" in data, (
            "soul-injection.yaml should have mental_models or personality"
        )


# ═══════════════════════════════════════════════════════════════════
# 3. LegionEmployee instance creation
# ═══════════════════════════════════════════════════════════════════


class TestLegionEmployeeLoading:
    """Verify LegionEmployee loads correctly from existing employee dirs."""

    @pytest.fixture
    def employee(self):
        """Create a LegionEmployee for emp-烛龙."""
        if not _legion_exists():
            pytest.skip("Legion path not found")
        resolved = _resolve_employee_dir("emp-烛龙")
        if not resolved:
            pytest.skip("emp-烛龙 directory not found")
        return LegionEmployee("emp-烛龙")

    def test_employee_has_name(self, employee):
        """Employee should have a name from soul-injection."""
        assert employee.name, "Employee should have a name"
        assert "烛龙" in employee.name

    def test_employee_has_personality(self, employee):
        """Personality should be loaded from soul-injection.yaml."""
        assert employee.personality is not None
        assert isinstance(employee.personality, dict)

    def test_employee_has_personality_traits(self, employee):
        """Personality traits should be accessible."""
        traits = employee.personality_traits
        assert isinstance(traits, list)

    def test_employee_has_mental_models(self, employee):
        """Mental models should be loaded from soul-injection.yaml."""
        assert employee.mental_models is not None
        assert isinstance(employee.mental_models, list)
        # 烛龙 should have mental_models
        if len(employee.mental_models) > 0:
            first = employee.mental_models[0]
            assert isinstance(first, dict)
            assert "name" in first or "content" in first

    def test_employee_has_capabilities(self, employee):
        """Capabilities should be collected from both yamls."""
        assert employee.capabilities is not None
        assert isinstance(employee.capabilities, list)

    def test_employee_has_display_name(self, employee):
        """Display name should include employee_id."""
        display = employee.display_name
        assert employee.name in display
        assert "emp-烛龙" in display

    def test_employee_has_emp_dir(self, employee):
        """Employee directory should be resolved."""
        assert employee.emp_dir
        assert os.path.isdir(employee.emp_dir)

    def test_employee_level(self, employee):
        """Employee level should be loaded."""
        # 烛龙 is P8
        assert employee.level
        assert "P" in employee.level or "L" in employee.level

    def test_employee_personality_style(self, employee):
        """Personality style should be accessible."""
        style = employee.personality_style
        assert isinstance(style, str)

    def test_employee_worldview(self, employee):
        """Worldview should be loaded (long text)."""
        assert employee.worldview

    def test_employee_introduction(self, employee):
        """Introduction should be loaded (long text)."""
        assert employee.introduction

    def test_employee_get_stats(self, employee):
        """get_stats() returns a summary dict."""
        stats = asyncio.run(employee.get_stats())
        assert isinstance(stats, dict)
        assert stats["employee_id"] == "emp-烛龙"
        assert "name" in stats
        assert "tools" in stats
        assert "has_memory" in stats
        assert "mental_models" in stats


# ═══════════════════════════════════════════════════════════════════
# 4. Employee with tools attached
# ═══════════════════════════════════════════════════════════════════


class TestEmployeeWithTools:
    """Verify tools can be attached to an employee."""

    @pytest.fixture
    def employee_with_tools(self):
        if not _legion_exists():
            pytest.skip("Legion path not found")
        tools = {
            "test_tool": lambda: "hello",
            "another_tool": lambda x: x * 2,
        }
        return LegionEmployee("emp-狴犴", agent_tools=tools)

    def test_tools_are_attached(self, employee_with_tools):
        assert "test_tool" in employee_with_tools.tools
        assert "another_tool" in employee_with_tools.tools

    def test_stats_show_tools(self, employee_with_tools):
        stats = asyncio.run(employee_with_tools.get_stats())
        assert "test_tool" in stats["tools"]

    def test_repr(self, employee_with_tools):
        r = repr(employee_with_tools)
        assert "LegionEmployee" in r
        assert employee_with_tools.name in r


# ═══════════════════════════════════════════════════════════════════
# 5. Memory operations (memory.db)
# ═══════════════════════════════════════════════════════════════════


class TestMemoryOperations:
    """Verify memorize() and remember() work with memory.db."""

    @pytest.fixture
    def employee_with_memory(self):
        """Use 白泽 who has the largest memory.db (753KB)."""
        if not _legion_exists():
            pytest.skip("Legion path not found")
        emp = LegionEmployee("emp-白泽")
        if not emp.memory_db_path:
            pytest.skip(f"no memory.db for emp-白泽 at {emp.emp_dir}")
        return emp

    def test_has_memory_db(self, employee_with_memory):
        """Employee should have a memory.db file."""
        assert employee_with_memory.memory_db_path is not None
        assert os.path.exists(employee_with_memory.memory_db_path)

    def test_remember_returns_list(self, employee_with_memory):
        """remember() should return a list of memory entries."""
        results = asyncio.run(employee_with_memory.remember("AI"))
        assert isinstance(results, list)

    def test_remember_returns_content_and_created(self, employee_with_memory):
        """Each memory result should have content and created_at."""
        results = asyncio.run(employee_with_memory.remember("双三角", limit=2))
        if results:
            entry = results[0]
            assert "content" in entry
            assert "created_at" in entry

    def test_remember_empty_key_returns_results(self, employee_with_memory):
        """An empty key should match broadly but still return safely."""
        results = asyncio.run(employee_with_memory.remember("", limit=2))
        assert isinstance(results, list)

    def test_remember_nonexistent_returns_empty(self, employee_with_memory):
        """A highly specific key that won't match should return empty."""
        results = asyncio.run(employee_with_memory.remember("___NONEXISTENT___xyzzy___"))
        assert isinstance(results, list)
        # Should be empty or very small
        assert len(results) < 2

    def test_memorize_and_remember(self, employee_with_memory):
        """Write then read back should find the entry."""
        test_content = f"PYTEST_TEST_MEM_{__import__('time').time()}"
        asyncio.run(employee_with_memory.memorize(test_content, "test"))
        results = asyncio.run(employee_with_memory.remember(test_content, limit=5))
        contents = [r.get("content", "") for r in results]
        assert any(test_content in c for c in contents), (
            f"memorized content '{test_content}' should be findable via remember()"
        )

    def test_learn_calls_memorize(self, employee_with_memory):
        """learn() should be equivalent to memorize()."""
        test_content = f"PYTEST_LEARN_TEST_{__import__('time').time()}"
        asyncio.run(employee_with_memory.learn(
            test_content,
            metadata={"type": "test", "source": "pytest"}
        ))
        results = asyncio.run(employee_with_memory.remember(test_content, limit=5))
        contents = [r.get("content", "") for r in results]
        assert any(test_content in c for c in contents)


# ═══════════════════════════════════════════════════════════════════
# 6. Dual memory: own memory.db + Gaia Brain
# ═══════════════════════════════════════════════════════════════════


class TestDualMemory:
    """Verify dual-write to own memory.db and (mock) Gaia Brain."""

    @pytest.fixture
    def mock_brain(self):
        brain = MagicMock()
        brain.ingest_knowledge = AsyncMock()
        return brain

    def test_memorize_writes_to_both(self, mock_brain):
        """Should write to both memory.db and Gaia Brain."""
        if not _legion_exists():
            pytest.skip("Legion path not found")
        emp = LegionEmployee("emp-计然", brain=mock_brain)
        if not emp.memory_db_path:
            pytest.skip("no memory.db for emp-计然")

        content = f"DUAL_MEM_TEST_{__import__('time').time()}"
        asyncio.run(emp.memorize(content, "test_dual"))

        # Should have been ingested to mock brain
        mock_brain.ingest_knowledge.assert_called_once()
        call_kwargs = mock_brain.ingest_knowledge.call_args[1]
        assert call_kwargs["source"] == f"employee:{emp.employee_id}"
        assert content in call_kwargs["content"]

        # Should also be findable in local memory
        results = asyncio.run(emp.remember(content, limit=3))
        contents = [r.get("content", "") for r in results]
        assert any(content in c for c in contents)

    def test_learn_feeds_to_both(self, mock_brain):
        """learn() should feed to both memory and Gaia."""
        if not _legion_exists():
            pytest.skip("Legion path not found")
        emp = LegionEmployee("emp-文鳐", brain=mock_brain)
        if not emp.memory_db_path:
            pytest.skip("no memory.db for emp-文鳐")

        content = f"LEARN_DUAL_{__import__('time').time()}"
        asyncio.run(emp.learn(content, {"type": "test_insight", "source": "pytest"}))

        mock_brain.ingest_knowledge.assert_called_once()

        results = asyncio.run(emp.remember(content, limit=3))
        contents = [r.get("content", "") for r in results]
        assert any(content in c for c in contents)

    def test_no_brain_does_not_crash(self):
        """memorize/learn should work even without Gaia Brain."""
        if not _legion_exists():
            pytest.skip("Legion path not found")
        emp = LegionEmployee("emp-獬豸")  # No brain
        if not emp.memory_db_path:
            pytest.skip("no memory.db for emp-獬豸")

        content = f"NO_BRAIN_TEST_{__import__('time').time()}"
        try:
            asyncio.run(emp.memorize(content, "test"))
            results = asyncio.run(emp.remember(content, limit=3))
            contents = [r.get("content", "") for r in results]
            assert any(content in c for c in contents)
        except Exception as e:
            pytest.fail(f"Should not crash without brain: {e}")


# ═══════════════════════════════════════════════════════════════════
# 7. create_legion_agent factory
# ═══════════════════════════════════════════════════════════════════


class TestCreateLegionAgent:
    """Verify create_legion_agent returns properly connected pairs."""

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_backend_agent(self):
        """Backend agent should pair with emp-烛龙."""
        employee, agent = asyncio.run(
            create_legion_agent("backend")
        )
        assert employee.employee_id == "emp-烛龙"
        assert employee.name == "烛龙" or "烛龙" in employee.name
        assert isinstance(agent, BaseAgent)
        # Agent should have employee attached
        assert hasattr(agent, "employee")
        assert agent.employee is employee

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_qa_agent(self):
        """QA agent should pair with emp-狴犴."""
        employee, agent = asyncio.run(
            create_legion_agent("qa")
        )
        assert employee.employee_id == "emp-狴犴"
        assert hasattr(agent, "employee")
        assert agent.employee is employee

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_security_agent(self):
        """Security agent should pair with emp-獬豸."""
        employee, agent = asyncio.run(
            create_legion_agent("security")
        )
        assert employee.employee_id == "emp-獬豸"
        assert hasattr(agent, "employee")
        assert agent.employee is employee

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_growth_agent(self):
        """Growth agent should pair with emp-乘黄."""
        employee, agent = asyncio.run(
            create_legion_agent("growth")
        )
        assert employee.employee_id == "emp-乘黄"
        assert hasattr(agent, "employee")

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_knowledge_agent(self):
        """Knowledge agent should pair with emp-文鳐."""
        employee, agent = asyncio.run(
            create_legion_agent("knowledge")
        )
        assert employee.employee_id == "emp-文鳐"

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_architecture_agent(self):
        """Architecture agent should pair with emp-开明兽."""
        employee, agent = asyncio.run(
            create_legion_agent("architecture")
        )
        assert employee.employee_id == "emp-开明兽"

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_data_agent(self):
        """Data agent should pair with emp-计然."""
        employee, agent = asyncio.run(
            create_legion_agent("data")
        )
        assert employee.employee_id == "emp-计然"

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_sre_agent(self):
        """SRE agent should pair with emp-䑏疏."""
        employee, agent = asyncio.run(
            create_legion_agent("sre")
        )
        assert employee.employee_id == "emp-䑏疏"

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_create_support_agent(self):
        """Support agent should pair with emp-白泽 (resolves to emp-白泽-3c6ee223)."""
        employee, agent = asyncio.run(
            create_legion_agent("support")
        )
        assert employee.employee_id == "emp-白泽"
        assert employee.name == "白泽" or "白泽" in employee.name
        assert hasattr(agent, "employee")

    def test_unknown_agent_type_raises(self):
        """Unknown agent type should raise KeyError."""
        with pytest.raises(KeyError):
            asyncio.run(create_legion_agent("nonexistent"))


# ═══════════════════════════════════════════════════════════════════
# 8. All 9 employee mappings
# ═══════════════════════════════════════════════════════════════════


class TestEmployeeMappingResolution:
    """Verify all 9 employee mappings resolve correctly."""

    def test_map_has_all_types(self):
        """EMPLOYEE_AGENT_MAP should have all 9 agent types."""
        for agent_type in EXPECTED_AGENT_TYPES:
            assert agent_type in EMPLOYEE_AGENT_MAP, f"Missing: {agent_type}"

    def test_map_has_all_employees(self):
        """EMPLOYEE_AGENT_MAP should reference all 9 expected employee IDs."""
        emp_ids_found = set()
        for mapping in EMPLOYEE_AGENT_MAP.values():
            emp_ids_found.add(mapping["employee_id"])
        for expected in EXPECTED_EMPLOYEES:
            assert expected in emp_ids_found, f"Missing employee mapping: {expected}"

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_all_employees_have_soul_files(self):
        """Each mapped employee should have a soul-injection.yaml."""
        for agent_type, mapping in EMPLOYEE_AGENT_MAP.items():
            emp_id = mapping["employee_id"]
            resolved = _resolve_employee_dir(emp_id)
            assert resolved, f"{agent_type} ({emp_id}) did not resolve to a directory"
            soul_path = f"{resolved}/soul-injection.yaml"
            assert os.path.exists(soul_path), (
                f"{agent_type} ({emp_id}) missing soul-injection.yaml at {soul_path}"
            )
            employee_yaml = f"{resolved}/employee.yaml"
            assert os.path.exists(employee_yaml), (
                f"{agent_type} ({emp_id}) missing employee.yaml at {employee_yaml}"
            )

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_all_employees_have_agent_classes(self):
        """Each mapping should reference a valid agent class."""
        for agent_type, mapping in EMPLOYEE_AGENT_MAP.items():
            agent_class = mapping["agent_class"]
            assert issubclass(agent_class, BaseAgent), (
                f"{agent_type}'s agent_class {agent_class.__name__} "
                "does not inherit from BaseAgent"
            )
            # The class should be instantiatable
            instance = agent_class()
            assert isinstance(instance, BaseAgent)
            # Clean up if needed (some agents might have __del__)
            del instance

    def test_create_all_returns_all(self):
        """create_all_legion_agents should return all 9 agent types."""
        if not _legion_exists():
            pytest.skip("Legion path not found")
        agents = asyncio.run(create_all_legion_agents())
        for agent_type in EXPECTED_AGENT_TYPES:
            assert agent_type in agents, f"Missing agent: {agent_type}"
            employee, agent = agents[agent_type]
            assert isinstance(employee, LegionEmployee)
            assert isinstance(agent, BaseAgent)


# ═══════════════════════════════════════════════════════════════════
# 9. Graceful fallback
# ═══════════════════════════════════════════════════════════════════


class TestGracefulFallback:
    """Verify graceful fallback when employee directory is missing."""

    def test_missing_employee_creates_generic(self):
        """A missing employee should create a generic fallback, not crash."""
        emp = LegionEmployee("emp-不存在的")
        assert emp.name == "emp-不存在的"  # Falls back to employee_id
        assert emp.emp_dir == ""  # No directory
        assert emp.memory_db_path is None  # No memory
        # Generic fallback is created with minimal personality
        assert isinstance(emp.personality, dict)
        assert emp.mental_models == []
        assert emp.capabilities == []

    def test_missing_employee_still_usable(self):
        """A missing employee should still be usable (tools, stats, etc.)."""
        emp = LegionEmployee("emp-不存在的", agent_tools={"ping": lambda: "pong"})
        stats = asyncio.run(emp.get_stats())
        assert stats["employee_id"] == "emp-不存在的"
        assert stats["has_memory"] is False

        # remember should not crash
        results = asyncio.run(emp.remember("test"))
        assert results == []

        # memorize should not crash
        try:
            asyncio.run(emp.memorize("test", "test"))
        except Exception as e:
            pytest.fail(f"memorize should not crash on generic employee: {e}")

        # learn should not crash
        try:
            asyncio.run(emp.learn("test"))
        except Exception as e:
            pytest.fail(f"learn should not crash on generic employee: {e}")


# ═══════════════════════════════════════════════════════════════════
# 10. Mental model edge cases
# ═══════════════════════════════════════════════════════════════════


class TestMentalModelsEdgeCases:
    """Verify mental models collection handles mixed formats."""

    def test_mixed_format_models(self):
        """Handle both string and dict formats in mental_models."""
        soul_with_mixed = {
            "mental_models": [
                "simple_model_name",
                {"name": "complex_model", "content": "detailed description"},
                {"content": "content_only_model"},
                {"employee_id": "emp-test", "memory_type": "mental_model",
                 "content": "legacy_format_model", "tags": ["tag1"]},
            ]
        }
        emp = object.__new__(LegionEmployee)
        emp.soul = soul_with_mixed
        emp.mental_models = emp._collect_mental_models()
        assert len(emp.mental_models) == 4
        names = [m["name"] for m in emp.mental_models]
        assert "simple_model_name" in names
        assert "complex_model" in names
        assert any("content_only" in n for n in names)

    def test_non_list_models_returns_empty(self):
        """Non-list mental_models should gracefully return empty."""
        soul = {"mental_models": "not_a_list"}
        emp = object.__new__(LegionEmployee)
        emp.soul = soul
        emp.mental_models = emp._collect_mental_models()
        assert emp.mental_models == []

    def test_missing_models_returns_empty(self):
        """Missing mental_models key should return empty list."""
        soul = {}
        emp = object.__new__(LegionEmployee)
        emp.soul = soul
        emp.mental_models = emp._collect_mental_models()
        assert emp.mental_models == []


# ═══════════════════════════════════════════════════════════════════
# 11. Agent tools from create_legion_agent
# ═══════════════════════════════════════════════════════════════════


class TestAgentToolsFromProfile:
    """Verify create_legion_agent attaches employee tools to agent."""

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_agent_has_employee_tools(self):
        """Agent should get get_mental_models, get_employee_profile, etc."""
        employee, agent = asyncio.run(create_legion_agent("backend"))
        tools = agent.tools
        assert "get_mental_models" in tools, (
            "Agent should have get_mental_models tool"
        )
        assert "get_employee_profile" in tools
        assert "remember_from_legion" in tools
        assert "memorize_to_legion" in tools

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_get_mental_models_returns_list(self):
        """get_mental_models tool should return a list of model dicts."""
        employee, agent = asyncio.run(create_legion_agent("backend"))
        models = asyncio.run(agent.tools["get_mental_models"]())
        assert isinstance(models, list)
        if models:
            assert "name" in models[0]

    @pytest.mark.skipif(not _legion_exists(), reason="Legion path not found")
    def test_get_employee_profile_returns_stats(self):
        """get_employee_profile tool should return stats."""
        employee, agent = asyncio.run(create_legion_agent("data"))
        stats = asyncio.run(agent.tools["get_employee_profile"]())
        assert isinstance(stats, dict)
        assert "employee_id" in stats


# ═══════════════════════════════════════════════════════════════════
# 12. Direct memory.db operations
# ═══════════════════════════════════════════════════════════════════


class TestDirectMemoryDB:
    """Verify direct read/write to memory.db works."""

    def _create_temp_db(self):
        """Create a temporary memory.db with memories table."""
        import sqlite3
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memories "
            "(id INTEGER PRIMARY KEY, content TEXT, category TEXT, created_at REAL)"
        )
        conn.execute(
            "INSERT INTO memories (content, category, created_at) VALUES (?, ?, ?)",
            ("test entry 1", "experience", 1000.0),
        )
        conn.execute(
            "INSERT INTO memories (content, category, created_at) VALUES (?, ?, ?)",
            ("test entry 2 about AI", "insight", 2000.0),
        )
        conn.commit()
        conn.close()
        return db_path

    def test_query_memory_db(self):
        db_path = self._create_temp_db()
        try:
            results = asyncio.run(_query_memory_db(db_path, "AI", limit=5))
            assert len(results) >= 1
            assert any("AI" in r["content"] for r in results)
        finally:
            os.unlink(db_path)

    def test_write_and_query(self):
        db_path = self._create_temp_db()
        try:
            ok = asyncio.run(_write_memory_db(db_path, "new test entry", "test"))
            assert ok
            results = asyncio.run(_query_memory_db(db_path, "new test", limit=5))
            assert any("new test" in r["content"] for r in results)
        finally:
            os.unlink(db_path)

    def test_query_nonexistent_db(self):
        results = asyncio.run(_query_memory_db("/nonexistent/memory.db", "test"))
        assert results == []

    def test_write_nonexistent_db(self):
        ok = asyncio.run(_write_memory_db("/nonexistent/memory.db", "test"))
        assert ok is False
