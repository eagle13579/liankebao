# Credentials Checklist — Payment Integration

> **Project:** Chainkefull  
> **Purpose:** Track all payment-related credentials, API keys, and secrets required for production deployment.  
> **Status:** ☐ Not started  ☐ In progress  ☑ Collected  ☐ Verified  ☐ Rotated  

---

## 1. Payment Gateway

| # | Credential | Source / Issuer | Production Value | Status | Notes |
|---|-----------|-----------------|-----------------|--------|-------|
| 1.1 | `PAYMENT_GATEWAY_API_KEY` | Gateway Dashboard | | ☐ | Live environment API key |
| 1.2 | `PAYMENT_GATEWAY_SECRET` | Gateway Dashboard | | ☐ | HMAC / signing secret |
| 1.3 | `PAYMENT_GATEWAY_WEBHOOK_SECRET` | Gateway Dashboard | | ☐ | Used to verify webhook payloads |
| 1.4 | `PAYMENT_GATEWAY_MERCHANT_ID` | Gateway Dashboard | | ☐ | May not be needed if API key is sufficient |
| 1.5 | Gateway account email | N/A | | ☐ | Account owner contact |
| 1.6 | Webhook endpoint URL | Deploy config | `https://api.chainkefull.com/payments/webhook` | ☐ | Configure in gateway dashboard |

### Sandbox / Test Credentials

| # | Credential | Value | Expires | Notes |
|---|-----------|-------|---------|-------|
| 1.7 | Sandbox API Key | | | For local + staging integration tests |
| 1.8 | Test card numbers | `4111-1111-1111-1111` | N/A | Stripe / gateway-specific test cards |
| 1.9 | Webhook test secret | | | Obtained from sandbox dashboard |

---

## 2. Database (PostgreSQL — Production)

| # | Credential | Environment Variable | Production Value | Status | Notes |
|---|-----------|---------------------|-----------------|--------|-------|
| 2.1 | PG connection string | `PG_URL` | `postgresql://...` | ☐ | Contains user, password, host, dbname |
| 2.2 | DB read-only user | | | ☐ | Optional — for analytics dashboards |
| 2.3 | SSL root cert (RDS / Cloud SQL) | | | ☐ | For encrypted connections |

---

## 3. Authentication & Security

| # | Credential | Environment Variable | Production Value | Status | Notes |
|---|-----------|---------------------|-----------------|--------|-------|
| 3.1 | `SECRET_KEY` | `SECRET_KEY` | | ☐ | Django / Flask signing key (min 50 chars) |
| 3.2 | `JWT_SECRET` | `JWT_SECRET` | | ☐ | Token signing secret |
| 3.3 | `ENCRYPTION_KEY` | `ENCRYPTION_KEY` | | ☐ | For encrypting sensitive stored data |
| 3.4 | API rate-limit token | `RATE_LIMIT_TOKEN` | | ☐ | Used by upstream rate-limit service |

---

## 4. External Integrations (Tied to Payments)

| # | Service / Integration | Credential | Env Var | Status | Notes |
|---|----------------------|-----------|---------|--------|-------|
| 4.1 | Email (transactional) | SMTP password or API key | `EMAIL_API_KEY` | ☐ | Sends payment receipts |
| 4.2 | SMS gateway | API token | `SMS_API_TOKEN` | ☐ | Payment confirmations |
| 4.3 | Tax calculation service | API key | `TAX_API_KEY` | ☐ | If applicable |
| 4.4 | Fraud detection service | API key | `FRAUD_API_KEY` | ☐ | If applicable |
| 4.5 | Accounting export (QuickBooks/Xero) | OAuth token | `ACCOUNTING_TOKEN` | ☐ | If applicable |

---

## 5. Infrastructure & CI/CD

| # | Credential | Issuer / Location | Production Value | Status | Notes |
|---|-----------|-------------------|-----------------|--------|-------|
| 5.1 | Database password (Vault / Secrets Manager) | AWS / Vault | | ☐ | Rotated every 90 days |
| 5.2 | CI/CD deploy key | GitHub / GitLab | | ☐ | SSH deploy key with read-only access |
| 5.3 | Docker registry token | Docker Hub / ECR | | ☐ | For automated image pulls in CI |
| 5.4 | Sentry DSN | sentry.io | | ☐ | Error tracking incl. payment error events |

---

## 6. Security Verification

> **Checklist for production launch readiness.**

- [ ] All Production values filled in (above)
- [ ] All credentials stored in **secrets manager** (Vault / AWS Secrets Manager / 1Password)
- [ ] No secrets hard-coded in source code
- [ ] No `.env` files committed to git (confirm `.gitignore` excludes `*.env`)
- [ ] `PG_URL` uses TLS/SSL (`?sslmode=require` or certificate)
- [ ] Payment webhook secret rotated quarterly
- [ ] Least-privilege DB user created (no `DROP TABLE` for app user)
- [ ] Audit log enabled for all payment API calls
- [ ] Rate limiting configured on payment endpoints
- [ ] Alerting set up for payment failure rate > 1%

---

## 7. Rotation Schedule

| Credential Type | Rotation Interval | Last Rotated | Next Due |
|----------------|-------------------|-------------|----------|
| Payment API key | Every 12 months | | |
| Webhook secret | Every 6 months | | |
| DB password | Every 90 days | | |
| JWT signing secret | Every 12 months | | |
| Encryption key | Every 24 months | | |

---

*Last updated: $(date +%Y-%m-%d)*  
*Owner: Chainkefull DevOps / Security Team*
