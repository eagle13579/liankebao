"""Identity & Tenant Layer — authentication, authorization, multi-tenancy contracts.

Architecture principle:
    Every auth, tenant, and authorization decision goes through
    these protocols. This decouples business logic from:
        - Which auth provider is used (JWT, OAuth, SAML, LDAP)
        - How tenants are stored and resolved
        - How RBAC rules are defined and evaluated
        - Which identity federation providers are available

    Layer 6 is the outermost layer — it protects all inner layers.

These contracts are STABLE — they will never change as the system
scales from single-tenant file-based auth to multi-provider
federated identity with distributed RBAC.
"""
