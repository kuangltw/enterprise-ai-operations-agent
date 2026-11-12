# ADR 0004: Guard Purchase Writes with Approval + Outbox + Idempotency

- Date: 2026-11-12
- Status: Proposed

## Context
LLM-driven procurement can cause costly, unauthorized or duplicate ERP transactions.

## Decision
Only deterministic backend services create frozen drafts and request approval. A current authorized approval and source revalidation are required before a queued ERP write. Approval and outbox event commit atomically; ERP endpoint enforces stable idempotency keys. Ambiguous results are reconciled before retry.

## Alternatives
- Direct model tool write: unacceptable authorization and consistency risk.
- Synchronous API write in approval request: risks timeout/duplicate confusion, tightly couples ERP availability to approval UX.

## Consequences
Requires more states, reconciliation tooling and test coverage; provides strong auditability and safe at-least-once message dispatch.
