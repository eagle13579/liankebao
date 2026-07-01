"""Simple Tenant Adapter — implements TenantProtocol with an in-memory store.

Phase 0 implementation with no external database dependency.
Uses threading.Lock for thread-safe access.

Plan-to-features mapping:
    free:       basic CRUD, 3 brochures, no AI features
    pro:        all free + AI recommendation, bulk export, 50 brochures
    enterprise: all pro + custom branding, SSO, priority support, unlimited

Upgrade path:
    Phase 1+: Replace in-memory store with PostgreSQL-backed adapter
              using the existing database models and SQLAlchemy sessions.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from app.identity.interfaces import (
    Identity,
    Tenant,
)

logger = __import__("logging").getLogger(__name__)

# Default feature sets per plan
PLAN_FEATURES: dict[str, list[str]] = {
    "free": [
        "basic_crud",
        "brochure_share",
        "visitor_tracking",
    ],
    "pro": [
        "basic_crud",
        "brochure_share",
        "visitor_tracking",
        "ai_recommendation",
        "bulk_export",
        "analytics_dashboard",
        "team_collaboration",
    ],
    "enterprise": [
        "basic_crud",
        "brochure_share",
        "visitor_tracking",
        "ai_recommendation",
        "bulk_export",
        "analytics_dashboard",
        "team_collaboration",
        "custom_branding",
        "sso_integration",
        "priority_support",
        "webhook_access",
        "audit_logs",
        "unlimited_brochures",
    ],
}


class SimpleTenantAdapter:
    """In-memory TenantProtocol implementation for Phase 0 development.

    Stores tenants in a dict and resolves feature flags based on plan level.
    Thread-safe via threading.Lock.

    Usage:
        adapter = SimpleTenantAdapter()

        # Create a tenant
        tenant = await adapter.create_tenant({
            "name": "Acme Corp",
            "plan": "pro",
        })

        # Get tenant info
        result = await adapter.get_tenant(tenant.tenant_id)

        # List identity's tenants
        tenants = await adapter.get_identity_tenants(identity)
    """

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        # tenant_id → set of user_ids (identity-tenant assignments)
        self._assignments: dict[str, set[str]] = {}
        # user_id → set of tenant_ids (reverse lookup)
        self._user_tenants: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    # ── TenantProtocol Implementation ─────────────────────────────────

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Fetch a tenant by its ID.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The Tenant if found and active, None otherwise.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None or not tenant.is_active:
                return None
            return tenant

    async def get_identity_tenants(self, identity: Identity) -> list[Tenant]:
        """List all tenants accessible by the given identity.

        Super-admin identities (having "admin" or "super_admin" role) see
        all tenants. Regular users see only their assigned tenants.

        Args:
            identity: The verified identity.

        Returns:
            List of accessible Tenant objects.
        """
        with self._lock:
            # Super-admin / admin: return all active tenants
            if "admin" in identity.roles or "super_admin" in identity.roles:
                return [t for t in self._tenants.values() if t.is_active]

            # Regular user: return assigned tenants
            assigned = self._user_tenants.get(identity.user_id, set())
            return [self._tenants[tid] for tid in assigned if tid in self._tenants and self._tenants[tid].is_active]

    async def create_tenant(self, config: dict[str, Any]) -> Tenant:
        """Provision a new tenant.

        Args:
            config: Tenant configuration dict.
                Supported keys:
                    - tenant_id (str): Optional, auto-generates if omitted.
                    - name (str): Required. Human-readable name.
                    - plan (str): "free", "pro", or "enterprise". Default: "free".
                    - settings (dict): Optional tenant-specific config.
                    - features (list[str]): Optional override; defaults to plan defaults.

        Returns:
            The newly created Tenant.

        Raises:
            ValueError: If name is empty or plan is invalid.
        """
        name = config.get("name", "").strip()
        if not name:
            raise ValueError("tenant name is required")

        plan = config.get("plan", "free")
        if plan not in ("free", "pro", "enterprise"):
            raise ValueError(f"Invalid plan '{plan}'. Must be one of: free, pro, enterprise")

        tenant_id = config.get("tenant_id", "").strip() or uuid.uuid4().hex[:16]
        settings = config.get("settings", {})
        features = config.get("features", list(PLAN_FEATURES.get(plan, [])))

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            plan=plan,
            features=features,
            settings=settings,
            is_active=True,
        )

        with self._lock:
            if tenant_id in self._tenants:
                raise ValueError(f"Tenant '{tenant_id}' already exists")
            self._tenants[tenant_id] = tenant

        logger.info(
            "Created tenant: id=%s name=%s plan=%s features=%d",
            tenant_id,
            name,
            plan,
            len(features),
        )
        return tenant

    # ── Tenant-Identity Assignment ────────────────────────────────────

    async def assign_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        """Assign a user to a tenant.

        Args:
            tenant_id: The tenant to assign to.
            user_id: The user to assign.

        Returns:
            True if assigned, False if tenant doesn't exist.
        """
        with self._lock:
            if tenant_id not in self._tenants:
                return False

            self._assignments.setdefault(tenant_id, set()).add(user_id)
            self._user_tenants.setdefault(user_id, set()).add(tenant_id)
            return True

    async def unassign_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        """Remove a user from a tenant.

        Args:
            tenant_id: The tenant to remove from.
            user_id: The user to remove.

        Returns:
            True if removed, False if assignment didn't exist.
        """
        with self._lock:
            removed = False
            if tenant_id in self._assignments:
                if user_id in self._assignments[tenant_id]:
                    self._assignments[tenant_id].discard(user_id)
                    removed = True

            if user_id in self._user_tenants:
                self._user_tenants[user_id].discard(tenant_id)
                if not self._user_tenants[user_id]:
                    del self._user_tenants[user_id]

            return removed

    async def get_tenant_users(self, tenant_id: str) -> list[str]:
        """List all user IDs assigned to a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            List of user IDs.
        """
        with self._lock:
            return list(self._assignments.get(tenant_id, set()))

    async def update_tenant(
        self,
        tenant_id: str,
        updates: dict[str, Any],
    ) -> Tenant | None:
        """Update tenant properties.

        Args:
            tenant_id: The tenant to update.
            updates: Dict with keys to update (name, plan, settings, features, is_active).

        Returns:
            The updated Tenant, or None if not found.
        """
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                return None

            if "name" in updates:
                tenant.name = updates["name"]
            if "plan" in updates:
                plan = updates["plan"]
                if plan not in ("free", "pro", "enterprise"):
                    raise ValueError(f"Invalid plan '{plan}'")
                tenant.plan = plan
                # Update features to match new plan if features not explicitly set
                if "features" not in updates:
                    tenant.features = list(PLAN_FEATURES.get(plan, []))
            if "features" in updates:
                tenant.features = list(updates["features"])
            if "settings" in updates:
                tenant.settings = dict(updates["settings"])
            if "is_active" in updates:
                tenant.is_active = bool(updates["is_active"])

            logger.info("Updated tenant: id=%s name=%s", tenant_id, tenant.name)
            return tenant

    async def deactivate_tenant(self, tenant_id: str) -> bool:
        """Deactivate a tenant (soft-delete).

        Args:
            tenant_id: The tenant to deactivate.

        Returns:
            True if deactivated, False if not found.
        """
        return await self.update_tenant(tenant_id, {"is_active": False}) is not None

    # ── Feature Flag Resolution ───────────────────────────────────────

    async def has_feature(self, tenant_id: str, feature: str) -> bool:
        """Check if a tenant has a specific feature enabled.

        Args:
            tenant_id: The tenant to check.
            feature: The feature flag name (e.g. "ai_recommendation").

        Returns:
            True if the tenant exists, is active, and has the feature.
        """
        tenant = await self.get_tenant(tenant_id)
        if tenant is None:
            return False
        return feature in tenant.features

    async def list_tenants(
        self,
        plan: str | None = None,
        active_only: bool = True,
    ) -> list[Tenant]:
        """List all tenants, optionally filtered.

        Args:
            plan: Optional plan filter ("free", "pro", "enterprise").
            active_only: If True (default), only return active tenants.

        Returns:
            List of matching Tenant objects.
        """
        with self._lock:
            result = list(self._tenants.values())
            if active_only:
                result = [t for t in result if t.is_active]
            if plan:
                result = [t for t in result if t.plan == plan]
            return result
