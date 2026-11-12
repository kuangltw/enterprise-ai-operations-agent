# Architecture Decision Records (ADRs)

ADRs document **why** a decision was made, alternative approaches and consequences. Proposed decisions below are subject to validation during implementation.

| ADR | Decision |
|---|---|
| [0001](0001-modular-monolith.md) | Modular Monolith + Worker |
| [0002](0002-langgraph-orchestration.md) | LangGraph with independent transaction state |
| [0003](0003-rag-index-separation.md) | PostgreSQL authoritative documents + Qdrant index |
| [0004](0004-approval-before-erp-write.md) | Approval, outbox and idempotency before ERP write |

Status lifecycle: Proposed → Accepted → Superseded. Update ADR status with a dated explanation if implementation differs.
