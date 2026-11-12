# ADR 0003: Separate Knowledge Source from Retrieval Index

- Date: 2026-11-12
- Status: Proposed

## Context
SOP documents require source citations, version history and tenant/document ACL. Vector indexes may be rebuilt or unavailable.

## Decision
Store ownership, versions, ACL, authoritative source chunks and ingestion status in PostgreSQL; raw files in S3-compatible object storage; dense/sparse retrieval vectors and filtering payload in Qdrant.

## Alternatives
- All metadata solely in Qdrant: simpler but weakens authoritative ACL/version lifecycle.
- PostgreSQL-only pgvector: fewer services but different scaling/retrieval tradeoffs.

## Consequences
Index consistency and reindexing must be implemented. Permission filtering must be checked both during retrieval and again before returning evidence.
