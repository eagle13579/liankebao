"""Comprehensive test suite for Agent Runtime integration.

Tests cover:
  1. Registering multiple agents
  2. start() starts all agents
  3. dispatch_event routes to correct handlers
  4. run_cron_cycle executes due jobs
  5. stop() stops all agents gracefully
  6. Singleton pattern (get_instance)
  7. Agent status tracking via get_status()
  8. Duplicate registration rejection
  9. Unregister and re-register
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.base_agent import AgentConfig, AgentStatus, BaseAgent, CronJob

# ═══════════════════════════════════════════════════════════════════════════
# Helper: concrete agent for testing
# ═══════════════════════════════════════════════════════════════════════════


class TestAgent(BaseAgent):
    """Minimal concrete agent for testing runtime integration."""

    def __init__(self, name: str = "test_agent", **kwargs):
        config = AgentConfig(
            agent_name=name,
            agent_role="test_role",
            knowledge_base_name="test_kb",
        )
        super().__init__(config=config)
        self.init_called = False
        self.stop_called = False
        self.events_received: list = []

    async def init(self):
        self.init_called = True
        self.register_tool("ping", self._ping)
        self.register_event_handler("test.event", self._handle_test_event)
        self.add_cron_job(
            CronJob(
                schedule="* * * * *",
                action=self._cron_action,
                name="every_minute",
            )
        )

    async def stop(self):
        self.stop_called = True
        self.status = AgentStatus.STOPPED

    async def _ping(self, **kwargs):
        return "pong"

    async def _handle_test_event(self, event):
        self.events_received.append(event)

    async def _cron_action(self):
        self._cron_ran = True


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAgentRuntimeRegistration:
    """Agent registration: register, unregister, duplicate detection."""

    async def test_register_single_agent(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="agent_1")
        await runtime.register(agent)

        assert "agent_1" in runtime.agents
        assert runtime.agents["agent_1"] is agent

    async def test_register_multiple_agents(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agents = [TestAgent(name=f"agent_{i}") for i in range(1, 4)]
        for a in agents:
            await runtime.register(a)

        assert len(runtime.agents) == 3
        for i in range(1, 4):
            assert f"agent_{i}" in runtime.agents

    async def test_register_duplicate_raises(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent_a = TestAgent(name="same_name")
        agent_b = TestAgent(name="same_name")

        await runtime.register(agent_a)
        with pytest.raises(ValueError, match="already registered"):
            await runtime.register(agent_b)

    async def test_unregister_existing(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="removable")
        await runtime.register(agent)
        result = await runtime.unregister("removable")
        assert result is True
        assert "removable" not in runtime.agents
        assert agent.stop_called is True

    async def test_unregister_nonexistent(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        result = await runtime.unregister("ghost")
        assert result is False

    async def test_register_then_re_register_after_unregister(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        a1 = TestAgent(name="cyclic")
        await runtime.register(a1)
        await runtime.unregister("cyclic")

        a2 = TestAgent(name="cyclic")
        await runtime.register(a2)  # Should succeed
        assert "cyclic" in runtime.agents


@pytest.mark.asyncio
class TestAgentRuntimeLifecycle:
    """Runtime lifecycle: start, stop, and agent state transitions."""

    async def test_start_starts_all_agents(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        a1 = TestAgent(name="alpha")
        a2 = TestAgent(name="beta")

        await runtime.register(a1)
        await runtime.register(a2)

        assert a1.status.value == "initializing"
        assert a2.status.value == "initializing"

        await runtime.start()

        # Agents should now be IDLE
        assert a1.status.value == "idle", f"Expected idle, got {a1.status.value}"
        assert a2.status.value == "idle", f"Expected idle, got {a2.status.value}"
        assert a1.init_called is True
        assert a2.init_called is True

        await runtime.stop()

    async def test_stop_stops_all_agents(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        a1 = TestAgent(name="gamma")
        a2 = TestAgent(name="delta")

        await runtime.register(a1)
        await runtime.register(a2)
        await runtime.start()
        await runtime.stop()

        assert a1.stop_called is True
        assert a2.stop_called is True

    async def test_double_start_is_idempotent(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="epsilon")
        await runtime.register(agent)

        await runtime.start()
        assert runtime._running is True

        # Second start should not crash
        await runtime.start()
        assert runtime._running is True

        await runtime.stop()

    async def test_double_stop_is_idempotent(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="zeta")
        await runtime.register(agent)
        await runtime.start()
        await runtime.stop()
        assert runtime._running is False

        # Second stop should not crash
        await runtime.stop()
        assert runtime._running is False

    async def test_start_registers_already_running_agent(self):
        """If runtime is already running, newly registered agent starts immediately."""
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        a1 = TestAgent(name="existing")
        await runtime.register(a1)
        await runtime.start()

        # Register another agent while runtime is running
        a2 = TestAgent(name="latecomer")
        await runtime.register(a2)

        # latecomer should have been started immediately
        assert a2.status.value == "idle"
        assert a2.init_called is True

        await runtime.stop()

    async def test_get_agent(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="gettable")
        await runtime.register(agent)

        retrieved = runtime.get_agent("gettable")
        assert retrieved is agent

        missing = runtime.get_agent("nonexistent")
        assert missing is None

    async def test_get_agents_returns_copy(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        await runtime.register(TestAgent(name="eta"))
        agents_copy = runtime.get_agents()
        assert isinstance(agents_copy, dict)
        assert "eta" in agents_copy
        # Modification of copy should not affect runtime
        agents_copy.clear()
        assert "eta" in runtime.agents


@pytest.mark.asyncio
class TestAgentRuntimeEventDispatch:
    """Event dispatching: dispatch_event routes to correct handlers."""

    async def test_dispatch_routes_to_subscribed_handlers(self):
        from app.agents.agent_runtime import AgentRuntime
        from app.events.interfaces import Event

        runtime = AgentRuntime()
        agent = TestAgent(name="event_listener")
        await runtime.register(agent)
        await runtime.start()

        event = Event(type="test.event", source="test", payload={"key": "value"})
        await runtime.dispatch_event(event)

        assert len(agent.events_received) >= 1
        received = agent.events_received[0]
        assert received.type == "test.event"
        assert received.payload == {"key": "value"}

        await runtime.stop()

    async def test_dispatch_routes_to_all_subscribed_agents(self):
        from app.agents.agent_runtime import AgentRuntime
        from app.events.interfaces import Event

        runtime = AgentRuntime()
        a1 = TestAgent(name="subscriber_1")
        a2 = TestAgent(name="subscriber_2")
        a3 = TestAgent(name="subscriber_3")

        for a in (a1, a2, a3):
            await runtime.register(a)
        await runtime.start()

        event = Event(type="test.event", source="test", payload={"broadcast": True})
        await runtime.dispatch_event(event)

        for agent in (a1, a2, a3):
            assert len(agent.events_received) >= 1

        await runtime.stop()

    async def test_dispatch_unhandled_event_no_error(self):
        from app.agents.agent_runtime import AgentRuntime
        from app.events.interfaces import Event

        runtime = AgentRuntime()
        agent = TestAgent(name="no_match_handler")
        await runtime.register(agent)
        await runtime.start()

        # Event type that no agent handles
        event = Event(type="unmatched.type", source="test")
        try:
            await runtime.dispatch_event(event)
        except Exception:
            pytest.fail("dispatch_event should not raise on unhandled events")

        await runtime.stop()

    async def test_dispatch_with_event_bus(self):
        from app.agents.agent_runtime import AgentRuntime
        from app.events.interfaces import Event

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        mock_bus.subscribe = AsyncMock()
        mock_bus.unsubscribe = AsyncMock()

        runtime = AgentRuntime(event_bus=mock_bus)
        agent = TestAgent(name="bus_agent")
        await runtime.register(agent)
        await runtime.start()

        event = Event(type="test.event", source="test")
        await runtime.dispatch_event(event)

        # Event bus publish should have been called
        mock_bus.publish.assert_called_once()

        await runtime.stop()


@pytest.mark.asyncio
class TestAgentRuntimeCron:
    """Cron scheduling: run_cron_cycle executes due jobs."""

    async def test_run_cron_cycle_executes_due_jobs(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="cron_agent")
        await runtime.register(agent)
        await runtime.start()

        # The agent has an every-minute cron job. Since it's a new datetime,
        # _is_job_due should match if current minute matches.
        # Let's run the cycle explicitly.
        await runtime.run_cron_cycle()

        # The cron action sets _cron_ran to True
        assert hasattr(agent, "_cron_ran")

        await runtime.stop()

    async def test_run_cron_cycle_no_jobs(self):
        """Runtime with no cron jobs does not error."""
        from app.agents.agent_runtime import AgentRuntime
        from app.agents.base_agent import AgentConfig

        class NoCronAgent(BaseAgent):
            async def init(self):
                pass

            async def stop(self):
                self.status = AgentStatus.STOPPED

        runtime = AgentRuntime()
        agent = NoCronAgent(config=AgentConfig(agent_name="no_cron"))
        await runtime.register(agent)
        await runtime.start()

        # Should not raise even though agent has no cron jobs
        await runtime.run_cron_cycle()

        await runtime.stop()


@pytest.mark.asyncio
class TestAgentRuntimeStatus:
    """Status reporting: get_status returns correct state."""

    async def test_get_status_reports_runtime_info(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="status_agent")
        await runtime.register(agent)

        status = await runtime.get_status()
        assert "runtime" in status
        assert "agents" in status
        assert status["runtime"]["running"] is False
        assert status["runtime"]["agent_count"] == 1

    async def test_get_status_after_start(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="running_agent")
        await runtime.register(agent)
        await runtime.start()

        status = await runtime.get_status()
        assert status["runtime"]["running"] is True
        assert status["runtime"]["agent_count"] == 1
        assert "running_agent" in status["agents"]
        agent_status = status["agents"]["running_agent"]
        assert agent_status["status"] == "idle"
        assert agent_status["tool_count"] >= 1

        await runtime.stop()

    async def test_get_status_after_stop(self):
        from app.agents.agent_runtime import AgentRuntime

        runtime = AgentRuntime()
        agent = TestAgent(name="stopped_agent")
        await runtime.register(agent)
        await runtime.start()
        await runtime.stop()

        status = await runtime.get_status()
        assert status["runtime"]["running"] is False


@pytest.mark.asyncio
class TestAgentRuntimeSingleton:
    """Singleton pattern: get_instance returns the same instance."""

    async def test_get_instance_returns_singleton(self):
        from app.agents.agent_runtime import AgentRuntime

        # Reset singleton for test isolation
        AgentRuntime._instance = None

        inst1 = await AgentRuntime.get_instance()
        inst2 = await AgentRuntime.get_instance()
        assert inst1 is inst2

    async def test_get_instance_with_params(self):
        from app.agents.agent_runtime import AgentRuntime

        AgentRuntime._instance = None

        mock_bus = MagicMock()
        inst = await AgentRuntime.get_instance(event_bus=mock_bus)
        assert inst.event_bus is mock_bus

        # Second call with different params should return same instance
        inst2 = await AgentRuntime.get_instance(event_bus=None)
        assert inst2 is inst
        # event_bus should still be the original
        assert inst2.event_bus is mock_bus
