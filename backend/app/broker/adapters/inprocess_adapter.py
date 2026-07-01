"""InProcessBroker — ServiceBrokerProtocol adapter for in-process communication.

Resolves service names to locally-registered Python objects and calls
their methods directly — no serialization, no network overhead.

Thread-safe (asyncio.Lock) and trace_id aware.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from app.broker.interfaces import (
    ServiceBrokerProtocol,
    ServiceHandler,
    ServiceRequest,
    ServiceResponse,
)

logger = logging.getLogger(__name__)


class InProcessBroker(ServiceBrokerProtocol):
    """In-process service broker that calls registered services locally.

    Services are registered as ``(service_instance, handler_method_lookup)``
    pairs.  When ``call()`` is invoked the broker resolves
    ``service_name.method_name`` on the registered instance and awaits the
    result.

    Thread-safe via ``asyncio.Lock`` for registration / resolution.
    Trace IDs from ``ServiceRequest`` are propagated into handler calls
    as a keyword argument so downstream code can observe the correlation ID.
    """

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        """Mapping service_name → service_instance."""

        self._lock = asyncio.Lock()

    # ── Registration helpers ──────────────────────────────────────────

    async def register_service(
        self,
        service_name: str,
        instance: Any,
    ) -> None:
        """Register a service instance.

        The instance's public methods become callable via
        ``broker.call(ServiceRequest(service=service_name, method="method_name"))``.

        Args:
            service_name: Canonical service name (e.g. ``"knowledge"``).
            instance: Any Python object whose methods will be invoked.
        """
        async with self._lock:
            self._services[service_name] = instance
            logger.info("Service registered: %s (%s)", service_name, type(instance).__name__)

    async def unregister_service(self, service_name: str) -> bool:
        """Remove a previously registered service.

        Returns True if found and removed, False otherwise.
        """
        async with self._lock:
            if service_name in self._services:
                del self._services[service_name]
                logger.info("Service unregistered: %s", service_name)
                return True
            return False

    async def list_services(self) -> list[str]:
        """Return all registered service names."""
        async with self._lock:
            return list(self._services.keys())

    # ── ServiceBrokerProtocol ─────────────────────────────────────────

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """Call a single service method.

        Resolves ``request.service`` to a registered instance and invokes
        ``request.method`` with ``request.params``.  The trace_id from the
        request is also passed as a keyword argument if the method accepts it.

        Returns a ``ServiceResponse`` — wraps any exception in a failure response.
        """
        instance = await self._resolve_service(request.service)
        if instance is None:
            return ServiceResponse.fail(
                f"Service '{request.service}' is not registered"
            )

        method = self._resolve_method(instance, request.method)
        if method is None:
            return ServiceResponse.fail(
                f"Method '{request.method}' not found on service '{request.service}'"
            )

        try:
            params = dict(request.params)
            params.setdefault("trace_id", request.trace_id)

            # Apply timeout if configured
            if request.timeout_ms:
                result = await asyncio.wait_for(
                    method(**params),
                    timeout=request.timeout_ms / 1000.0,
                )
            else:
                result = await method(**params)

            return ServiceResponse.ok(result)
        except asyncio.TimeoutError:
            logger.warning(
                "Timeout calling %s.%s (trace=%s, timeout=%dms)",
                request.service,
                request.method,
                request.trace_id,
                request.timeout_ms,
            )
            return ServiceResponse.fail(
                f"Call to {request.service}.{request.method} timed out "
                f"after {request.timeout_ms}ms"
            )
        except Exception as exc:
            logger.exception(
                "Error calling %s.%s (trace=%s)",
                request.service,
                request.method,
                request.trace_id,
            )
            return ServiceResponse.fail(f"{type(exc).__name__}: {exc}")

    async def call_many(
        self,
        requests: list[ServiceRequest],
        fail_fast: bool = False,
    ) -> list[ServiceResponse]:
        """Call multiple service methods concurrently.

        Uses ``asyncio.gather`` to run all requests in parallel.

        Args:
            requests: List of service requests.
            fail_fast: If True, cancels remaining calls on first failure.

        Returns:
            List of ServiceResponse objects in the same order as *requests*.
        """
        if fail_fast:
            # Build tasks; if any raises, gather will propagate
            tasks = [self._call_or_raise(r) for r in requests]
            try:
                results = await asyncio.gather(*tasks)
                return list(results)
            except Exception:
                # Cancel remaining tasks
                for t in tasks:
                    if not t.done():
                        t.cancel()
                raise
        else:
            # Run all and capture exceptions as failure responses
            coros = [self.call(r) for r in requests]
            return list(await asyncio.gather(*coros))

    async def broadcast(
        self,
        request: ServiceRequest,
        service_selector: str | None = None,
    ) -> dict[str, ServiceResponse]:
        """Broadcast a request to all (or matching) registered services.

        Args:
            request: The request to broadcast.
            service_selector: Optional exact service name.  If provided,
                only that service receives the call.  If None, all registered
                services are called.

        Returns:
            Dict mapping service_name → ServiceResponse.
        """
        async with self._lock:
            if service_selector:
                names = [s for s in self._services if s == service_selector]
            else:
                names = list(self._services.keys())

        if not names:
            return {}

        results: dict[str, ServiceResponse] = {}
        tasks = []
        for name in names:
            req = ServiceRequest(
                service=name,
                method=request.method,
                params=request.params,
                trace_id=request.trace_id,
                timeout_ms=request.timeout_ms,
            )
            tasks.append(self.call(req))

        responses = await asyncio.gather(*tasks)
        for name, resp in zip(names, responses):
            results[name] = resp

        return results

    # ── Internals ─────────────────────────────────────────────────────

    async def _resolve_service(self, name: str) -> Any | None:
        """Thread-safe service instance lookup."""
        async with self._lock:
            return self._services.get(name)

    @staticmethod
    def _resolve_method(instance: Any, method_name: str) -> Callable | None:
        """Resolve a method name on a service instance."""
        method = getattr(instance, method_name, None)
        if method is None:
            return None
        if not callable(method):
            return None
        return method

    async def _call_or_raise(self, request: ServiceRequest) -> ServiceResponse:
        """Call a service and let exceptions propagate (for fail_fast)."""
        resp = await self.call(request)
        if not resp.success:
            raise RuntimeError(resp.error or "Unknown error")
        return resp
