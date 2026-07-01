"""RBAC Authorization Adapter — implements AuthorizationProtocol with an
in-memory role-permission matrix.

Phase 0 implementation:
    - In-memory role → permissions mapping
    - Built-in roles: super_admin, admin, enterprise_user, standard_user, anonymous
    - Thread-safe via threading.Lock

Built-in permissions cover all major modules:
    - brochure: create, read, update, delete, share, export
    - user: create, read, update, delete, manage
    - tenant: create, read, update, delete, manage
    - payment: read, process, refund, manage
    - ai: chat, recommend, embed, manage
    - admin: system_config, audit_log, manage_all

Upgrade path:
    Phase 1+: Load permissions from database (SQLAlchemy-based adapter)
    Phase 2+: Add attribute-based access control (ABAC) rules
    Phase 3+: Add policy-as-code with Open Policy Agent (OPA)
"""

from __future__ import annotations

import threading
from typing import Any

from app.identity.interfaces import (
    AuthorizationProtocol,
    Identity,
)

logger = __import__("logging").getLogger(__name__)


# Default role → permissions mapping
# Permission format: "resource:action"
# Resource types: brochure, user, tenant, payment, ai, admin
# Action types: create, read, update, delete, manage, share, export,
#               process, refund, chat, recommend, embed
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": [
        # Full access to everything
        "brochure:create", "brochure:read", "brochure:update", "brochure:delete",
        "brochure:share", "brochure:export",
        "user:create", "user:read", "user:update", "user:delete", "user:manage",
        "tenant:create", "tenant:read", "tenant:update", "tenant:delete",
        "tenant:manage",
        "payment:read", "payment:process", "payment:refund", "payment:manage",
        "ai:chat", "ai:recommend", "ai:embed", "ai:manage",
        "admin:system_config", "admin:audit_log", "admin:manage_all",
    ],
    "admin": [
        # Tenant-level administration
        "brochure:create", "brochure:read", "brochure:update", "brochure:delete",
        "brochure:share", "brochure:export",
        "user:create", "user:read", "user:update", "user:delete", "user:manage",
        "tenant:read", "tenant:update",
        "payment:read", "payment:process",
        "ai:chat", "ai:recommend", "ai:embed", "ai:manage",
        "admin:audit_log",
    ],
    "enterprise_user": [
        # Full brochure management
        "brochure:create", "brochure:read", "brochure:update", "brochure:delete",
        "brochure:share", "brochure:export",
        "user:read", "user:update",
        "tenant:read",
        "payment:read",
        "ai:chat", "ai:recommend", "ai:embed",
    ],
    "standard_user": [
        # Basic brochure access
        "brochure:create", "brochure:read", "brochure:update", "brochure:delete",
        "brochure:share",
        "user:read", "user:update",
        "tenant:read",
        "payment:read",
        "ai:chat",
    ],
    "anonymous": [
        # Public access only
        "brochure:read",
    ],
}


class RBACAuthorizationAdapter:
    """In-memory RBAC authorization adapter for Phase 0.

    Uses a role-permission matrix stored in a dict. Thread-safe via
    threading.Lock. Allows dynamic role creation, permission grants,
    and permission revocations at runtime.

    Usage:
        rbac = RBACAuthorizationAdapter()

        identity = Identity(
            user_id="user_1",
            roles=["standard_user"],
            is_authenticated=True,
        )

        # Check permission
        allowed = await rbac.check_permission(identity, "brochure", "create")
        # → True for standard_user

        # Get effective roles
        roles = await rbac.get_effective_roles(identity)
        # → ["standard_user"]
    """

    def __init__(self) -> None:
        self._role_permissions: dict[str, list[str]] = {}
        self._role_permissions.update(DEFAULT_ROLE_PERMISSIONS)
        self._lock = threading.Lock()

        # Additional: role inheritance (child_role → parent_role)
        # e.g., enterprise_user inherits from standard_user
        self._role_inheritance: dict[str, str] = {}

    # ── AuthorizationProtocol Implementation ─────────────────────────

    async def check_permission(
        self,
        identity: Identity,
        resource: str,
        action: str,
    ) -> bool:
        """Check whether an identity has permission to perform an action.

        Resolution logic:
            1. Get all effective roles (including inherited)
            2. Get all permissions for those roles
            3. Check if "resource:action" is in the resolved permissions
            4. Super_admin and admin have a wildcard bypass for most checks

        Args:
            identity: The verified identity.
            resource: Resource type (e.g. "brochure", "user", "tenant").
            action: Action (e.g. "create", "read", "update", "delete").

        Returns:
            True if authorized, False otherwise.
        """
        with self._lock:
            roles = await self._resolve_roles(identity.roles)
            permission = f"{resource}:{action}"

            for role in roles:
                perms = self._role_permissions.get(role, [])
                if permission in perms:
                    return True

            return False

    async def get_effective_roles(self, identity: Identity) -> list[str]:
        """Resolve the complete list of roles applicable to an identity.

        Includes role inheritance (e.g., enterprise_user inherits
        standard_user permissions).

        Args:
            identity: The identity to resolve roles for.

        Returns:
            List of effective role strings. Returns ["anonymous"] for
            unauthenticated identities.
        """
        if not identity.is_authenticated:
            return ["anonymous"]

        with self._lock:
            return await self._resolve_roles(identity.roles)

    # ── Role & Permission Management ─────────────────────────────────

    async def add_role(self, role: str, permissions: list[str] | None = None) -> None:
        """Register a new role with optional initial permissions.

        Args:
            role: The role name (e.g. "premium_user").
            permissions: List of permission strings to grant.

        Raises:
            ValueError: If the role already exists.
        """
        with self._lock:
            if role in self._role_permissions:
                raise ValueError(f"Role '{role}' already exists")
            self._role_permissions[role] = list(permissions or [])

    async def remove_role(self, role: str) -> bool:
        """Remove a role and all its permissions.

        Args:
            role: The role name to remove.

        Returns:
            True if removed, False if not found.
        """
        with self._lock:
            if role not in self._role_permissions:
                return False
            del self._role_permissions[role]
            # Clean up inheritance references
            self._role_inheritance = {
                child: parent
                for child, parent in self._role_inheritance.items()
                if child != role and parent != role
            }
            return True

    async def grant_permission(
        self,
        role: str,
        resource: str,
        action: str,
    ) -> bool:
        """Grant a specific permission to a role.

        Args:
            role: The role to modify.
            resource: Resource type (e.g. "brochure").
            action: Action (e.g. "export").

        Returns:
            True if granted, False if role doesn't exist.
        """
        permission = f"{resource}:{action}"
        with self._lock:
            if role not in self._role_permissions:
                return False
            if permission not in self._role_permissions[role]:
                self._role_permissions[role].append(permission)
            return True

    async def revoke_permission(
        self,
        role: str,
        resource: str,
        action: str,
    ) -> bool:
        """Revoke a specific permission from a role.

        Args:
            role: The role to modify.
            resource: Resource type.
            action: Action.

        Returns:
            True if revoked, False if role or permission doesn't exist.
        """
        permission = f"{resource}:{action}"
        with self._lock:
            if role not in self._role_permissions:
                return False
            if permission not in self._role_permissions[role]:
                return False
            self._role_permissions[role].remove(permission)
            return True

    async def get_role_permissions(self, role: str) -> list[str]:
        """Get all permissions assigned to a role.

        Args:
            role: The role name.

        Returns:
            List of permission strings, or empty list if role not found.
        """
        with self._lock:
            return list(self._role_permissions.get(role, []))

    async def set_role_inheritance(
        self,
        child_role: str,
        parent_role: str,
    ) -> bool:
        """Set inheritance: child_role inherits permissions from parent_role.

        Args:
            child_role: The role that inherits.
            parent_role: The role to inherit from.

        Returns:
            True if set, False if either role doesn't exist.
        """
        with self._lock:
            if child_role not in self._role_permissions or parent_role not in self._role_permissions:
                return False
            self._role_inheritance[child_role] = parent_role
            return True

    async def list_roles(self) -> list[dict[str, Any]]:
        """List all registered roles with their metadata.

        Returns:
            List of dicts with keys: role, permission_count, inherits_from.
        """
        with self._lock:
            return [
                {
                    "role": role,
                    "permission_count": len(perms),
                    "inherits_from": self._role_inheritance.get(role),
                }
                for role, perms in self._role_permissions.items()
            ]

    # ── Internal Helpers ─────────────────────────────────────────────

    async def _resolve_roles(self, base_roles: list[str]) -> list[str]:
        """Resolve a list of base roles into the full effective role set.

        Follows role inheritance chains recursively.

        Args:
            base_roles: The roles directly assigned to the identity.

        Returns:
            Complete list of effective roles (de-duplicated).
        """
        resolved: list[str] = []
        seen: set[str] = set()

        def _add_role(role: str) -> None:
            if role in seen:
                return
            seen.add(role)
            resolved.append(role)

            # Follow inheritance chain
            parent = self._role_inheritance.get(role)
            if parent:
                _add_role(parent)

        for role in base_roles:
            _add_role(role)

        return resolved

    async def reset_to_defaults(self) -> None:
        """Reset the role-permission matrix to the built-in defaults."""
        with self._lock:
            self._role_permissions.clear()
            self._role_permissions.update(
                {k: list(v) for k, v in DEFAULT_ROLE_PERMISSIONS.items()}
            )
            self._role_inheritance.clear()
