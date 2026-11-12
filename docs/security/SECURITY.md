# Security Model v0.1

> Threat-model baseline, not a claim that security controls have already been implemented.

## Trust boundaries

1. **Public HTTP boundary:** authenticate JWT, validate user status and tenant membership. `X-Tenant-ID` is a requested tenant, not trusted identity.
2. **Agent/model boundary:** user text, documents, retrieval passages and LLM outputs are untrusted. Model cannot grant its own permissions.
3. **Tool boundary:** allowlisted tool names, validated JSON schema, warehouse scoping, safe timeout/result size, per-call policy check.
4. **Data boundary:** PostgreSQL tenant-scoped relations, RLS as defense in depth, Qdrant tenant + ACL filter, PostgreSQL permission recheck before citation.
5. **Transaction boundary:** approval required, separation of duties, revalidation, outbox, idempotent ERP endpoint and reconciliation.

## Role permissions (baseline)

| Role | SOP Q&A | ERP analysis | Purchase draft | Approve |
|---|---|---|---|---|
| admin | ACL-restricted | scoped | yes | yes |
| manager | ACL-restricted | scoped | yes | yes |
| staff | ACL-restricted | scoped | yes | no |
| viewer | ACL-restricted | scoped read | no | no |

A manager/admin cannot automatically view documents outside applicable resource ACL. Some tenants may configure narrower roles; the server enforces effective permissions (role + resource + scope).

## Threat scenarios

| Threat | Control | Required test |
|---|---|---|
| Cross-tenant exfiltration | Trusted context, compound tenant keys, scoped queries, RLS | RAG-T07 / security suite |
| Prompt injection in SOP document | Treat retrieved content as data, not instructions; tool policy gate | RAG-T08 |
| Overprivileged tool invocation | Registry allowlist + per-call auth | ERP-T07 / ERP-T08 |
| Unauthorized purchase | DB approval state + self-approval restriction + current permissions | APR-T02 / APR-T10 |
| Replay or duplicate purchase | Stable idempotency key + ERP uniqueness + reconciliation | APR-T05 / APR-T07 |
| Approval on stale inventory | Source versions and revalidation | APR-T06 |
| Secret exposure in logs | Redaction, bounded event payloads, strict telemetry access | OBS-T08 |
| Malicious uploads | File size/type limits, parser sandbox, object scanning and timeout | Security test |
| Resource exhaustion | Rate limit, query/tool budgets, circuit breaker, bounded concurrency | Load/failure test |

## Sensitive data rules

- Use only synthetic ERP/customer/document fixtures in public repo and demos.
- Never commit `.env`, API keys, session secrets, real purchase/customer data or private support conversations.
- Use `.env.example` with placeholders; keep secrets in runtime secret management.
- Do not log raw JWT, complete prompts, full documents, sensitive tool outputs or payment data.
- Audit logs must be append-only to normal application roles, have retention and controlled access.
- Use least-privilege service credentials; DB admin role is not used by normal API.
- External model data transfer must be explicit and configurable; local Ollama mode should be testable.

## Publication policy

Publish architecture, public API contract, generic security controls and synthetic test coverage. Exclude active exploit details, production infrastructure identifiers, real environment configuration, security secrets and private incident data.

## References for implementation review

- OWASP Top 10 for LLM Applications / Agentic security guidance.
- PostgreSQL Row Security Policies documentation.
- LangGraph persistence / interrupt documentation.
- Qdrant payload filtering and multitenancy documentation.

Verify versions/compatibility before coding; this file is a design checkpoint, not an audit report.
