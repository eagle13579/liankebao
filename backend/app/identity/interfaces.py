"""Identity & Tenant Layer — protocol interfaces for auth, tenant, RBAC, federation.

Architecture:
    IdentityProtocol  → authentication & token lifecycle
    TenantProtocol    → multi-tenant resolution & feature flags
    AuthorizationProtocol → RBAC permission checks
    FederationProtocol   → external identity provider integration

These contracts are STABLE — they will never change as the system
scales from in-memory Phase-0 adapters to Redis-backed, PostgreSQL-backed,
or LDAP-backed implementations.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol, runtime_checkable


# ======================================================================
# Data Models
# ======================================================================


@dataclasses.dataclass
class Identity:
    """A verified user identity with roles, permissions, and tenant context.

    Attributes:
        user_id: Unique identifier for the user across the system.
        tenant_id: The tenant this identity belongs to (empty string for super-admin).
        roles: List of role names assigned to this identity
            (e.g. ["admin", "enterprise_user"]).
        permissions: Resolved list of permission strings for quick checks.
        auth_provider: Which provider authenticated this identity
            (e.g. "jwt", "wechat", "oauth_google").
        is_authenticated: Whether this identity has been fully authenticated.
        metadata: Arbitrary key-value store for provider-specific claims
            (e.g. {"openid": "...", "session_key": "..."}).
    """

    user_id: str
    tenant_id: str = ""
    roles: list[str] = dataclasses.field(default_factory=list)
    permissions: list[str] = dataclasses.field(default_factory=list)
    auth_provider: str = "jwt"
    is_authenticated: bool = False
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Tenant:
    """A tenant in the multi-tenant system.

    Attributes:
        tenant_id: Unique identifier for this tenant.
        name: Human-readable tenant name (e.g. "Acme Corp").
        plan: Subscription plan — determines feature entitlement.
        features: List of feature flags enabled for this tenant
            (e.g. ["ai_recommendation", "bulk_export", "custom_branding"]).
        settings: Tenant-specific configuration key-value store.
        is_active: Whether this tenant is active and accepting requests.
    """

    tenant_id: str
    name: str = ""
    plan: str = "free"  # free | pro | enterprise
    features: list[str] = dataclasses.field(default_factory=list)
    settings: dict[str, Any] = dataclasses.field(default_factory=dict)
    is_active: bool = True


@dataclasses.dataclass
class AuthRequest:
    """A request to authenticate a user with a specific provider.

    Attributes:
        provider: Authentication provider identifier
            (e.g. "password", "wechat", "oauth_google", "oauth_github").
        credentials: Provider-specific credentials.
            For "password": {"username": "...", "password": "..."}.
            For "wechat": {"code": "..."}.
            For "oauth_google": {"access_token": "..."}.
        scope: Requested permission scopes (e.g. ["openid", "profile", "email"]).
    """

    provider: str
    credentials: dict[str, Any] = dataclasses.field(default_factory=dict)
    scope: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must not be empty")


@dataclasses.dataclass
class AuthResponse:
    """The result of a successful authentication.

    Attributes:
        identity: The fully resolved Identity object.
        token: The issued access token string (JWT or provider-specific).
        expires_at: Unix timestamp when the token expires.
        refresh_token: Optional token for refreshing the session.
    """

    identity: Identity
    token: str
    expires_at: float
    refresh_token: str | None = None


# ======================================================================
# Identity Protocol — Authentication & Token Lifecycle
# ======================================================================


@runtime_checkable
class IdentityProtocol(Protocol):
    """Unified interface for authenticating users and managing token lifecycle.

    Provides:
        1. authenticate() — Validate credentials and issue tokens
        2. validate_token() — Decode and verify an existing token
        3. refresh_token() — Issue a new token using a refresh token
        4. invalidate() — Revoke a token (add to blacklist)
    """

    async def authenticate(self, request: AuthRequest) -> AuthResponse:
        """Authenticate a user and issue tokens.

        Args:
            request: AuthRequest with provider and credentials.

        Returns:
            AuthResponse with identity and tokens.

        Raises:
            ValueError: If credentials are invalid.
            ConnectionError: If the auth provider is unreachable.
        """
        ...

    async def validate_token(self, token: str) -> Identity:
        """Decode, verify, and resolve a token into an Identity.

        Args:
            token: The JWT or provider-specific token string.

        Returns:
            The verified Identity with roles and permissions resolved.

        Raises:
            ValueError: If the token is invalid, expired, or blacklisted.
        """
        ...

    async def refresh_token(self, token: str) -> AuthResponse:
        """Issue a new access token using a refresh token.

        Args:
            token: The refresh token string.

        Returns:
            A new AuthResponse with fresh tokens.

        Raises:
            ValueError: If the refresh token is invalid or expired.
        """
        ...

    async def invalidate(self, token: str) -> None:
        """Revoke a token, preventing further use.

        Args:
            token: The token to invalidate (add to blacklist).
        """
        ...


# ======================================================================
# Tenant Protocol — Multi-Tenancy Resolution
# ======================================================================


@runtime_checkable
class TenantProtocol(Protocol):
    """Unified interface for tenant lifecycle and resolution.

    Provides:
        1. get_tenant() — Fetch tenant metadata by ID
        2. get_identity_tenants() — List tenants accessible by an identity
        3. create_tenant() — Provision a new tenant
    """

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Fetch a tenant by its unique ID.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The Tenant object if found, None otherwise.
        """
        ...

    async def get_identity_tenants(self, identity: Identity) -> list[Tenant]:
        """List all tenants accessible by the given identity.

        For super-admin identities, returns all tenants.
        For regular users, returns only their assigned tenants.

        Args:
            identity: The verified identity.

        Returns:
            List of Tenant objects the identity can access.
        """
        ...

    async def create_tenant(self, config: dict[str, Any]) -> Tenant:
        """Provision a new tenant.

        Args:
            config: Tenant configuration dict with keys:
                - tenant_id (str): Optional, auto-generated if omitted.
                - name (str): Human-readable name.
                - plan (str): "free", "pro", or "enterprise".
                - settings (dict): Tenant-specific settings.

        Returns:
            The newly created Tenant object.

        Raises:
            ValueError: If the tenant configuration is invalid.
        """
        ...


# ======================================================================
# Authorization Protocol — RBAC Permission Checks
# ======================================================================


@runtime_checkable
class AuthorizationProtocol(Protocol):
    """Unified interface for role-based access control.

    Provides:
        1. check_permission() — Test whether an identity can perform an action
        2. get_effective_roles() — Resolve all roles for an identity
    """

    async def check_permission(
        self,
        identity: Identity,
        resource: str,
        action: str,
    ) -> bool:
        """Check whether an identity has permission to perform an action on a resource.

        Args:
            identity: The verified identity to check.
            resource: The resource type (e.g. "brochure", "user", "tenant", "payment").
            action: The action to perform (e.g. "create", "read", "update", "delete",
                "manage", "export").

        Returns:
            True if the identity is authorized, False otherwise.

        Note:
            Super-admin / admin roles bypass resource-specific checks and
            always return True for any resource/action combination.
        """
        ...

    async def get_effective_roles(self, identity: Identity) -> list[str]:
        """Resolve the complete list of roles applicable to an identity.

        This includes inherited roles, group-derived roles, and any
        tenant-specific role mappings.

        Args:
            identity: The identity to resolve roles for.

        Returns:
            List of effective role strings (e.g. ["admin", "enterprise_user"]).
            Returns ["anonymous"] for unauthenticated identities.
        """
        ...


# ======================================================================
# Federation Protocol — External Identity Provider Integration
# ======================================================================


@runtime_checkable
class FederationProtocol(Protocol):
    """Unified interface for federated identity provider login flows.

    Provides:
        1. get_federation_providers() — List configured external providers
        2. initiate_login() — Get the redirect URL for an external provider
        3. handle_callback() — Process the OAuth callback and return tokens
    """

    async def get_federation_providers(self) -> list[str]:
        """List all currently configured federation providers.

        Returns:
            List of provider identifiers (e.g. ["wechat", "google", "github"]).
            Returns an empty list if no providers are configured.
        """
        ...

    async def initiate_login(self, provider: str) -> str:
        """Generate the redirect URL for initiating an external login.

        Args:
            provider: The federation provider identifier
                (e.g. "wechat", "google", "github").

        Returns:
            The full redirect URL the client should navigate to.

        Raises:
            ValueError: If the provider is not configured.
        """
        ...

    async def handle_callback(
        self,
        provider: str,
        code: str,
    ) -> AuthResponse:
        """Process the OAuth callback from an external provider.

        Exchanges the authorization code for tokens, resolves the
        user identity, and returns the AuthResponse.

        Args:
            provider: The federation provider identifier.
            code: The authorization code from the provider's callback.

        Returns:
            AuthResponse with the authenticated identity and tokens.

        Raises:
            ValueError: If the code is invalid or the provider rejects it.
            ConnectionError: If the provider is unreachable.
        """
        ...
