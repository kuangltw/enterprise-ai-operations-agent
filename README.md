# Enterprise AI Operations Agent

> **Status: Design / Pre-implementation** — This repository currently contains architecture and implementation specifications. No runnable application is claimed.

A production-oriented, open-source reference project for enterprise AI operations: **SOP knowledge Q&A (RAG), inventory/sales analysis, purchase recommendations with human approval, and Agent execution observability**.

本專案為企業 AI Agent + RAG 參考實作計畫，聚焦 **權限、可追溯性、業務規則與安全交易**。目前公開的是技術設計，程式、API、資料庫 Migration、測試結果及正式環境能力均尚待實作與驗證。

## Planned MVP

| Feature | Scope | Status |
|---|---|---|
| SOP Knowledge Q&A | Document ingestion, hybrid retrieval, citations, ACL | Planned |
| Inventory & sales analysis | Authorized ERP API tools, deterministic calculations | Planned |
| Purchase approval | Draft → approval → revalidation → idempotent ERP write | Planned |
| Operations monitoring | Run events, traces, latency, token usage, cost | Planned |

## Proposed architecture

```text
React / TypeScript
        |
FastAPI (Authentication / Tenant / RBAC / API)
        |
LangGraph Application Orchestrator
   |           |              |
   RAG         ERP Tools      Approval & Audit
   |           |              |
Qdrant      PHP Demo ERP     PostgreSQL
   |           |              |
Object Store  ERP API      Outbox / Checkpoint
        |
Celery Worker / Redis / OpenTelemetry
```

- **Modular Monolith + Worker**; do not begin with microservices.
- **LLM** interprets and explains; deterministic services own calculations and transaction decisions.
- **Trusted execution context** supplies user/tenant identity; never take tenant identity from LLM output.
- **Approval + DB state machine + outbox + idempotency** guard external writes.
- **PostgreSQL** is source of truth; **Qdrant** is a rebuildable retrieval index.

## Design documents

| Document | Description |
|---|---|
| [System architecture](docs/architecture/SYSTEM.md) | Modules, boundaries, dependencies, reliability |
| [Database schema](docs/database/SCHEMA.md) | PostgreSQL logical model, constraints, migrations |
| [API contract](docs/api/CONTRACT.md) | REST/SSE, authorization, requests and responses |
| [Agent workflow](docs/agent/WORKFLOW.md) | LangGraph state, nodes, routes, checkpoint and approval |
| [Acceptance tests](docs/testing/ACCEPTANCE.md) | Functional, security, failure recovery and release gates |
| [Security model](docs/security/SECURITY.md) | Tenant isolation, tool safety, sensitive data |
| [Architecture decisions](docs/adr/README.md) | Documented design tradeoffs |
| [Development conventions](AGENTS.md) | Instructions for coding agents and contributors |

## Implementation sequence

1. Infrastructure, identity and tenant-aware database foundations.
2. Document ingestion, retrieval and evidence-backed SOP Q&A.
3. Mock ERP API and deterministic inventory/sales analysis.
4. Purchase draft, approval, version validation and idempotent execution.
5. Observability, reliability testing, evaluation and demo release.

See [acceptance criteria](docs/testing/ACCEPTANCE.md). **No listed performance/SLO/evaluation target is currently a measured result.**

## Local development

Not yet available. A future release will supply `docker compose up`, migrations, seeded synthetic data and end-to-end demos. Do not use this repository for real ERP purchase execution until security and transaction tests pass.

## Data and license

- Example/test data must be synthetic. Never commit company records, credentials, live tokens or personal data.
- Third-party dependencies and datasets must be checked for license compatibility before adding them.
- **Project license: to be selected before source-code release.** No permission beyond applicable law is implied by an absent license.

## Project state

Architecture proposal v0.1 · 2026-11-12. Specifications may change during implementation; implementation and tests take precedence over outdated proposals.
