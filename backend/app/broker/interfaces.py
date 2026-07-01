"""Service Broker interfaces — inter-service communication contracts.

Architecture principle:
    Every service in the system discovers and calls other services through
    ServiceBrokerProtocol. This decouples callers from the transport layer
    (in-process, Redis pub/sub, RabbitMQ, Kafka, gRPC, HTTP).

    Local services register themselves with CurrentServiceRegistry.
    Remote services are resolved through the broker's routing layer.

These contracts are STABLE — they will never change as the system scales
from a single monolith to a distributed microservice mesh.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Callable, Protocol, runtime_checkable


# ======================================================================
# Data Models
# ======================================================================


@dataclasses.dataclass
class ServiceRequest:
    """A request to invoke a service method.

    Encodes everything needed to route and execute a service call,
    regardless of transport mechanism.

    Attributes:
        service: Target service name (e.g. "knowledge", "recommendation", "gaia").
        method: Method name to invoke on the service (e.g. "search_semantic").
        params: Keyword arguments to pass to the method.
        trace_id: Distributed tracing ID for correlation across service boundaries.
        timeout_ms: Maximum execution time in milliseconds before the call is aborted.
    """

    service: str
    method: str
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    trace_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)
    timeout_ms: int = 30_000  # 30 seconds default

    def __post_init__(self) -> None:
        if not self.service.strip():
            raise ValueError("service name must not be empty")
        if not self.method.strip():
            raise ValueError("method name must not be empty")
        if self.timeout_ms < 1:
            raise ValueError(f"timeout_ms must be >= 1, got {self.timeout_ms}")


@dataclasses.dataclass
class ServiceResponse:
    """The result of a service call.

    Attributes:
        success: Whether the call completed successfully.
        data: The response payload (any picklable/serializable value).
        error: Error message if success is False, otherwise None.
    """

    success: bool
    data: Any = None
    error: str | None = None

    @classmethod
    def ok(cls, data: Any = None) -> "ServiceResponse":
        """Create a success response."""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> "ServiceResponse":
        """Create a failure response."""
        return cls(success=False, error=error)


# ======================================================================
# Service Handler
# ======================================================================


class ServiceHandler(Protocol):
    """Callable that implements a service method.

    The handler accepts arbitrary keyword arguments and returns
    a ServiceResponse. This is the unit of work registered in the broker.
    """

    async def __call__(self, **params: Any) -> ServiceResponse:
        """Execute the service method.

        Args:
            **params: Method parameters.

        Returns:
            A ServiceResponse indicating success or failure.
        """
        ...


# ======================================================================
# Service Broker Protocol
# ======================================================================


@runtime_checkable
class ServiceBrokerProtocol(Protocol):
    """Unified interface for invoking services across process/network boundaries.

    The broker abstracts away:
        - Local in-process calls (same process, no serialization)
        - Redis pub/sub (same machine, light serialization)
        - RabbitMQ / Kafka (distributed, durable queuing)
        - gRPC / HTTP (cross-network, polyglot)

    Usage:
        resp = await broker.call(ServiceRequest(
            service="knowledge",
            method="search_semantic",
            params={"query": "user preferences", "top_k": 5},
        ))
    """

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """Call a single service method and wait for the response.

        Args:
            request: Fully-specified service request.

        Returns:
            ServiceResponse with the result or error.

        Raises:
            TimeoutError: If the call exceeds request.timeout_ms.
        """
        ...

    async def call_many(
        self,
        requests: list[ServiceRequest],
        fail_fast: bool = False,
    ) -> list[ServiceResponse]:
        """Call multiple service methods concurrently.

        Args:
            requests: List of service requests to execute.
            fail_fast: If True, cancel all remaining calls on first failure.

        Returns:
            List of ServiceResponse objects in the same order as requests.
        """
        ...

    async def broadcast(
        self,
        request: ServiceRequest,
        service_selector: str | None = None,
    ) -> dict[str, ServiceResponse]:
        """Broadcast a request to all (or matching) service instances.

        Args:
            request: The request to broadcast.
            service_selector: If provided, only broadcast to instances whose
                service name matches this pattern (exact or wildcard).
                If None, broadcast to ALL registered services.

        Returns:
            Dict mapping instance_id → ServiceResponse.
        """
        ...


# ======================================================================
# Current Service Registry
# ======================================================================


@runtime_checkable
class ServiceRegistryProtocol(Protocol):
    """Local service registration — what *this* process offers.

    In-process services register their handlers here so the broker
    can route calls to them without serialization overhead.
    """

    async def register(
        self,
        service: str,
        handler: ServiceHandler,
        description: str = "",
    ) -> None:
        """Register a local service handler.

        Args:
            service: Canonical service name (e.g. "gaia.knowledge").
            handler: Async callable that processes service requests.
            description: Human-readable description of the service.
        """
        ...

    async def unregister(self, service: str) -> bool:
        """Remove a previously registered service.

        Args:
            service: The service name to unregister.

        Returns:
            True if the service was found and removed, False otherwise.
        """
        ...

    async def resolve(self, service: str) -> ServiceHandler | None:
        """Resolve a service name to its registered handler.

        Args:
            service: The service name to look up.

        Returns:
            The registered handler, or None if not found.
        """
        ...

    async def list_services(self) -> list[dict[str, Any]]:
        """List all currently registered services.

        Returns:
            List of dicts with keys: service, description, registered_at.
        """
        ...


# ======================================================================
# Convenience: CurrentServiceRegistry factory
# ======================================================================


class CurrentServiceRegistry:
    """In-process service registry for local-only service routing.

    This is the simplest adapter — a thread-safe dict of handlers.
    For distributed setups, replace with RedisRegistry or ConsulRegistry.

    Usage:
        registry = CurrentServiceRegistry()
        await registry.register("gaia.knowledge", my_handler)
        handler = await registry.resolve("gaia.knowledge")
    """

    def __init__(self) -> None:
        self._handlers: dict[str, tuple[ServiceHandler, str]] = {}

    async def register(
        self,
        service: str,
        handler: ServiceHandler,
        description: str = "",
    ) -> None:
        self._handlers[service] = (handler, description)

    async def unregister(self, service: str) -> bool:
        return self._handlers.pop(service, None) is not None

    async def resolve(self, service: str) -> ServiceHandler | None:
        result = self._handlers.get(service)
        return result[0] if result else None

    async def list_services(self) -> list[dict[str, Any]]:
        return [
            {"service": name, "description": desc}
            for name, (_, desc) in self._handlers.items()
        ]
