# ADR 0002: LangGraph Orchestration

- Date: 2026-11-12
- Status: Proposed

## Context
Agent workflows require explicit routes, checkpointing, human approval interruption and recovery.

## Decision
Use one bounded LangGraph orchestrator. Graph state manages workflow progress; PostgreSQL purchase/approval tables separately govern business transactions.

## Alternatives
- Unbounded multi-agent collaboration: difficult to audit and evaluate for transactional actions.
- Hand-built state machine only: possible, but more application-level persistence/workflow code.

## Consequences
Checkpoint/resume improves observability but cannot supply distributed atomicity. Interrupt re-entry and retries require idempotent side-effect nodes and DB-backed approvals.
