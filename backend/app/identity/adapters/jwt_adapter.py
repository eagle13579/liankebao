"""JWT Identity Adapter — implements IdentityProtocol using JWT tokens.

Follows the existing JWT patterns from app.auth_jwt but as a standalone,
dependency-free implementation using the same shared auth_jwt module.

Phase 0: In-memory token blacklist (no Redis dependency).
Phase 1+: Replace with Redis-backed blacklist for horizontal scaling.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from jose import JWTError

from app.auth_jwt import create_access_token, decode_access_token
from app.config import settings
from app.identity.interfaces import (
    AuthRequest,
    AuthResponse,
    Identity,
    IdentityProtocol,
)

logger = logging.getLogger(__name__)


class JWTIdentityAdapter:
    """IdentityProtocol implementation using JWT tokens.

    Token lifecycle:
        - authenticate(): Validates credentials, creates JWT with claims
        - validate_token(): Decodes JWT, checks blacklist, resolves Identity
        - refresh_token(): Validates refresh token, issues new JWT pair
        - invalidate(): Adds token to in-memory blacklist

    The adapter is thread-safe for the blacklist via threading.Lock.

    Basic auth (password-based) is built in. For WeChat, OAuth, or other
    providers, pass validated external credentials via the credentials dict
    and the adapter will issue a JWT wrapping the external identity.
    """

    def __init__(self) -> None:
        # In-memory token blacklist: {token_jti: expiry_timestamp}
        self._blacklist: dict[str, float] = {}
        self._lock = threading.Lock()
        # Default token lifespan from settings
        self._token_ttl_minutes: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        # Refresh token lifespan: 30 days
        self._refresh_ttl_minutes: int = 60 * 24 * 30
        # Simple in-memory user store for Phase 0 (password-based auth)
        # {username: {"password": "hashed", "user_id": str, "roles": [...], ...}}
        self._users: dict[str, dict[str, Any]] = {}
        self._users_by_id: dict[str, dict[str, Any]] = {}

    # ── User Management (Phase 0 helpers for testing/development) ──────

    def register_user(
        self,
        username: str,
        password: str,
        user_id: str | None = None,
        roles: list[str] | None = None,
        tenant_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Register a user in the in-memory store for password-based auth.

        Args:
            username: Unique username/phone/email.
            password: Plaintext password (stored as-is for Phase 0; use
                hashing in production).
            user_id: Optional. Auto-generated UUID if not provided.
            roles: List of role names. Defaults to ["standard_user"].
            tenant_id: Optional tenant assignment.
            metadata: Optional additional user metadata.

        Returns:
            The assigned user_id.
        """
        if username in self._users:
            raise ValueError(f"User '{username}' already exists")

        uid = user_id or uuid.uuid4().hex[:16]
        roles = roles or ["standard_user"]
        entry: dict[str, Any] = {
            "password": password,
            "user_id": uid,
            "roles": list(roles),
            "tenant_id": tenant_id,
            "metadata": dict(metadata or {}),
        }
        self._users[username] = entry
        self._users_by_id[uid] = entry
        return uid

    def remove_user(self, username: str) -> bool:
        """Remove a registered user from the in-memory store."""
        entry = self._users.pop(username, None)
        if entry:
            self._users_by_id.pop(entry["user_id"], None)
            return True
        return False

    # ── IdentityProtocol Implementation ────────────────────────────────

    async def authenticate(self, request: AuthRequest) -> AuthResponse:
        """Authenticate a user and issue JWT tokens.

        Supported providers:
            - "password": Validates username/password from in-memory store.
            - "wechat" / "external": Accepts pre-validated external identity
              data in credentials (user_id, roles, etc.) and wraps in JWT.

        Args:
            request: AuthRequest with provider and credentials.

        Returns:
            AuthResponse with JWT access token and refresh token.

        Raises:
            ValueError: If credentials are invalid or provider unknown.
        """
        if request.provider == "password":
            return await self._authenticate_password(request)
        if request.provider in ("wechat", "external"):
            return await self._authenticate_external(request)
        raise ValueError(
            f"Unsupported auth provider '{request.provider}'. "
            f"Supported: password, wechat, external"
        )

    async def _authenticate_password(self, request: AuthRequest) -> AuthResponse:
        """Password-based authentication against in-memory user store."""
        username = request.credentials.get("username", "")
        password = request.credentials.get("password", "")

        if not username or not password:
            raise ValueError("username and password are required")

        user = self._users.get(username)
        if user is None or user["password"] != password:
            raise ValueError("Invalid username or password")

        return await self._issue_tokens(user)

    async def _authenticate_external(self, request: AuthRequest) -> AuthResponse:
        """External provider authentication — wrap pre-validated identity in JWT.

        Expected credentials keys:
            - user_id (str): Required. The external user identifier.
            - roles (list[str]): Optional. Defaults to ["standard_user"].
            - tenant_id (str): Optional. Tenant assignment.
            - metadata (dict): Optional. Additional claims.
        """
        user_id = request.credentials.get("user_id", "")
        if not user_id:
            raise ValueError("user_id is required for external auth")

        roles = request.credentials.get("roles", ["standard_user"])
        tenant_id = request.credentials.get("tenant_id", "")
        metadata = request.credentials.get("metadata", {})

        user: dict[str, Any] = {
            "password": "",
            "user_id": user_id,
            "roles": roles,
            "tenant_id": tenant_id,
            "metadata": metadata,
            "_external": True,
        }

        return await self._issue_tokens(user, auth_provider=request.provider)

    async def validate_token(self, token: str) -> Identity:
        """Decode and verify a JWT token, returning the resolved Identity.

        Validates:
            1. JWT signature (RS256 → HS256 fallback)
            2. Token expiration
            3. Token blacklist

        Args:
            token: The JWT access token string.

        Returns:
            Identity with all fields populated from token claims.

        Raises:
            ValueError: If the token is invalid, expired, or blacklisted.
        """
        # Check blacklist first
        if self._is_blacklisted(token):
            raise ValueError("Token has been revoked")

        try:
            payload = decode_access_token(token)
        except JWTError as exc:
            raise ValueError(f"Invalid token: {exc}") from exc

        # Extract claims
        user_id = payload.get("sub", "")
        if not user_id:
            raise ValueError("Token missing 'sub' claim")

        tenant_id = payload.get("tenant_id", "")
        roles = payload.get("roles", [])
        permissions = payload.get("permissions", [])
        auth_provider = payload.get("auth_provider", "jwt")
        metadata = payload.get("metadata", {})

        return Identity(
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            roles=list(roles),
            permissions=list(permissions),
            auth_provider=str(auth_provider),
            is_authenticated=True,
            metadata=dict(metadata),
        )

    async def refresh_token(self, token: str) -> AuthResponse:
        """Issue a new access token using a refresh token.

        The refresh token is a JWT with type="refresh" in its claims.

        Args:
            token: The refresh JWT token string.

        Returns:
            A new AuthResponse with fresh access and refresh tokens.

        Raises:
            ValueError: If the refresh token is invalid or expired.
        """
        if self._is_blacklisted(token):
            raise ValueError("Refresh token has been revoked")

        try:
            payload = decode_access_token(token)
        except JWTError as exc:
            raise ValueError(f"Invalid refresh token: {exc}") from exc

        if payload.get("type") != "refresh":
            raise ValueError("Token is not a refresh token")

        # Extract user info from the refresh token payload
        user_id = payload.get("sub", "")
        if not user_id:
            raise ValueError("Refresh token missing 'sub' claim")

        # Rebuild user record for _issue_tokens
        roles = payload.get("roles", ["standard_user"])
        tenant_id = payload.get("tenant_id", "")
        metadata = payload.get("metadata", {})
        auth_provider = payload.get("auth_provider", "jwt")

        # Invalidate old refresh token
        await self.invalidate(token)

        user: dict[str, Any] = {
            "password": "",
            "user_id": user_id,
            "roles": roles,
            "tenant_id": tenant_id,
            "metadata": metadata,
        }

        return await self._issue_tokens(user, auth_provider=auth_provider)

    async def invalidate(self, token: str) -> None:
        """Revoke a token by adding it to the blacklist.

        Extracts the token's JTI (JWT ID) and expiration to manage
        blacklist cleanup.

        Args:
            token: The token string to revoke.
        """
        try:
            payload = decode_access_token(token)
            jti = payload.get("jti", token)  # fallback: use token itself
            exp = payload.get("exp", time.time() + 3600)
            self._add_to_blacklist(str(jti), float(exp))
        except JWTError:
            logger.warning("Attempted to invalidate an already-invalid token")
            # Even if decode fails, mark the token string itself as blacklisted
            self._add_to_blacklist(token, time.time() + 3600)

    # ── Internal Helpers ───────────────────────────────────────────────

    async def _issue_tokens(
        self,
        user: dict[str, Any],
        auth_provider: str = "password",
    ) -> AuthResponse:
        """Issue access + refresh JWT tokens for a validated user.

        Args:
            user: User record dict with user_id, roles, tenant_id, metadata.
            auth_provider: String identifying the auth provider.

        Returns:
            AuthResponse with signed tokens.
        """
        user_id = user["user_id"]
        roles = user.get("roles", ["standard_user"])
        tenant_id = user.get("tenant_id", "")
        metadata = user.get("metadata", {})

        # Build JWT claims
        now = datetime.utcnow()
        access_exp = now + timedelta(minutes=self._token_ttl_minutes)
        refresh_exp = now + timedelta(minutes=self._refresh_ttl_minutes)

        access_claims = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "roles": roles,
            "auth_provider": auth_provider,
            "metadata": metadata,
            "type": "access",
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": access_exp,
        }

        refresh_claims = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "roles": roles,
            "metadata": metadata,
            "auth_provider": auth_provider,
            "type": "refresh",
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": refresh_exp,
        }

        access_token = create_access_token(access_claims)
        refresh_token = create_access_token(refresh_claims)

        return AuthResponse(
            identity=Identity(
                user_id=user_id,
                tenant_id=tenant_id,
                roles=list(roles),
                permissions=[],  # Permissions resolved by AuthorizationProtocol
                auth_provider=auth_provider,
                is_authenticated=True,
                metadata=dict(metadata),
            ),
            token=access_token,
            expires_at=access_exp.timestamp(),
            refresh_token=refresh_token,
        )

    # ── Blacklist Management ──────────────────────────────────────────

    def _add_to_blacklist(self, token_id: str, expiry: float) -> None:
        """Add a token identifier to the blacklist with cleanup."""
        with self._lock:
            # Evict expired entries
            now = time.time()
            expired_keys = [k for k, v in self._blacklist.items() if v < now]
            for k in expired_keys:
                del self._blacklist[k]
            # Add new entry
            self._blacklist[token_id] = expiry

    def _is_blacklisted(self, token: str) -> bool:
        """Check if a token is in the blacklist.

        Tries both the JTI from decoded token and the raw token string.

        Args:
            token: The token string to check.

        Returns:
            True if the token is blacklisted.
        """
        with self._lock:
            # Evict expired entries
            now = time.time()
            expired_keys = [k for v in self._blacklist.items() if v is not None]
            # Check raw token
            if token in self._blacklist:
                return True
            # Try to extract JTI
            try:
                payload = decode_access_token(token)
                jti = payload.get("jti")
                if jti and jti in self._blacklist:
                    return True
            except JWTError:
                pass
            return False
