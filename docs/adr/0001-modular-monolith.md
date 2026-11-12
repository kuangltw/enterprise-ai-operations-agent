# ADR 0001: Modular Monolith + Worker

- Date: 2026-11-12
- Status: Proposed

## Context
One developer must deliver integrated RAG, Agent, purchasing and monitoring with reproducible local deployment.

## Decision
Use FastAPI modular monolith with separate domain modules and a Celery worker for asynchronous ingestion/outbox processing. Keep PHP ERP mock as a versioned external API for integration demonstration.

## Alternatives
- Microservices: independent deployability but operational/distributed consistency overhead.
- One tightly coupled application: less setup but poor domain separation.

## Consequences
Simple CI, local Docker and cross-module testing; require strict dependency boundaries so modules can separate later. A single API deployment remains a scaling and failure-domain constraint.
