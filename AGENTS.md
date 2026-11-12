# Coding Agent Instructions

This repository is currently in **design stage**. Read `README.md`, `docs/architecture/SYSTEM.md`, `docs/database/SCHEMA.md`, `docs/api/CONTRACT.md`, `docs/agent/WORKFLOW.md`, `docs/security/SECURITY.md`, and `docs/testing/ACCEPTANCE.md` before implementing.

## Engineering requirements

1. Use Traditional Chinese (Taiwan) for project explanations and documentation; use standard English technical identifiers in code.
2. Prefer modular monolith boundaries with Python/FastAPI + LangGraph; PHP demo ERP communicates via versioned HTTP API.
3. Never bypass tenant membership, per-resource ACL, warehouse scope or server-side tool policy.
4. LLM output is untrusted. Inventory arithmetic, approval decisions, price checks and ERP writes must be deterministic and server-authorized.
5. Never let the model run arbitrary SQL or invoke arbitrary tools.
6. External purchase writes require a valid, current, independently authorized approval; atomic decision + outbox, stable idempotency key, and reconciliation on timeout.
7. Schema changes require Alembic migrations, explicit constraints, and rollback considerations. Do not alter production data ad hoc.
8. Write unit, integration, contract or E2E tests for each domain behavior; security and idempotency tests are mandatory for privileged operations.
9. Update OpenAPI/schema/docs/fixtures when behavior changes. Mark unimplemented features explicitly.
10. Do not commit secrets, real enterprise/customer data, credentials, raw sensitive logs, unlicensed third-party code or sample real documents.
11. Prefer controlled, observable state transitions; bounded retries, explicit error types and structured logs with trace IDs.
12. Before claiming a task complete, report changed paths, Git diff summary, tests executed and unresolved risks. Do not claim tests passed unless executed.

## Development order

M1 foundations → M2 RAG → M3 ERP/Agent → M4 approvals → M5 observability/reliability → M6 public demo. Avoid premature microservices, multi-agent autonomy and Kubernetes.

## Definition of done

- Contract maintained, tests for relevant acceptance IDs added and run.
- Permission, failure and concurrency paths considered.
- Documentation reflects **implemented**, **planned**, or **experiment** status precisely.
- No private data and no unexpected API writes.
