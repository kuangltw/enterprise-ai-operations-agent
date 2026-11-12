# Acceptance Tests & Release Gates v0.1

> **Proposed tests only.** No tests have been run. Targets are project-specific initial goals, not measured benchmarks or universal industry standards.

## Test levels

- Unit: inventory math, policy decisions, status transitions, deterministic validators.
- Contract: FastAPI schemas, PHP ERP tool request/response, error codes.
- Integration: PostgreSQL transactions, outbox, Qdrant ACL filtering, object storage.
- E2E: document upload → RAG citation; authorized ERP analysis; draft → approval → idempotent purchase.
- Security: cross-tenant reads, Prompt Injection, tool authorization, log redaction.
- Reliability: worker termination, retries, ambiguous external write result, restored checkpoints.

## SOP knowledge QA

| ID | Scenario | Expected result |
|---|---|---|
| RAG-T01 | Upload valid PDF | Document created, ingestion queued |
| RAG-T02 | Re-upload identical SHA-256 | No unintended duplicate version/ingestion |
| RAG-T03 | Upload a new version | Publish only after index marked ready |
| RAG-T04 | Ask supported SOP question | Evidence-backed answer, valid source citation |
| RAG-T05 | Ask question lacking evidence | `insufficient` and no fabricated citation |
| RAG-T06 | User lacks document ACL | No snippet, metadata or answer leakage |
| RAG-T07 | Tenant A queries tenant B | No cross-tenant retrieval |
| RAG-T08 | Inject tool instructions into document | Document text cannot authorize tool action |
| RAG-T09 | Revoke access during generation | Recheck before returning evidence |
| RAG-T10 | Qdrant unavailable | Explicit dependency error; no fabricated answer |

**Evaluation fixture:** at least 100 curated queries: 60 direct, 20 cross-document, 10 unanswerable, 10 ACL/adversarial. Initial goals: Recall@5 ≥85%, citation correctness ≥95%, correct abstention ≥95%. Publish definitions, dataset version, raw counts, model config, timestamps and false-positive analysis.

## Inventory and sales

| ID | Scenario | Expected |
|---|---|---|
| ERP-T01 | Read authorized warehouse | Results limited to authorized scope |
| ERP-T02 | Aggregate 30-day sales | Equals deterministic fixture |
| ERP-T03 | Open incoming purchase order | Included exactly once in inventory position |
| ERP-T04 | Zero sales | No divide-by-zero or fabricated demand |
| ERP-T05 | MOQ / pack multiple | Correct rounded quantities |
| ERP-T06 | ERP read timeout | Bounded retry + observable failure |
| ERP-T07 | Unknown tool name | Denied by registry |
| ERP-T08 | Unauthorized warehouse argument | Denied at execution point |

## Approval and ERP write

| ID | Scenario | Expected |
|---|---|---|
| APR-T01 | Generate draft | Versioned draft and items persisted |
| APR-T02 | Staff tries to approve | 403 |
| APR-T03 | Manager approves valid draft | Outbox created; async execution queued |
| APR-T04 | Two approvers race | Exactly one successful decision |
| APR-T05 | Duplicate decision / retry | No duplicate ERP purchase |
| APR-T06 | Stock/pricing changes after approval | Mark stale; block write |
| APR-T07 | ERP write times out after commit | Reconcile by idempotency key; no blind duplicate |
| APR-T08 | Kill worker during write | Recovered state; one business effect |
| APR-T09 | Modify approved draft | Invalidate approval and require reapproval |
| APR-T10 | Creator attempts self-approval | Denied by separation-of-duties policy |

## Monitoring

| ID | Scenario | Expected |
|---|---|---|
| OBS-T01 | Create agent run | Unique Run ID and trace correlation |
| OBS-T02 | Execute multi-node graph | Ordered sanitized node events |
| OBS-T03 | Model request fails | Error class and node identified |
| OBS-T04 | Wait for human approval | Wait time separate from active latency |
| OBS-T05 | Call tool | Duration, status and tool name recorded |
| OBS-T06 | Query usage totals | Token/cost aggregation matches fixtures |
| OBS-T07 | Read another user's private run | Permission denied |
| OBS-T08 | Tool returns sensitive content | No sensitive raw data in telemetry |

## Security and resilience gates

- All tenant-owned relations have tenant-aware constraints or transaction-checked invariants.
- ACL and warehouse-scope checks exist at execution point.
- Prompt Injection test cannot trigger a privileged tool.
- External purchase endpoint verifies idempotency key and duplicate payload compatibility.
- Unknown ERP write reconciles before retry; purchase writes are never directly invoked by LLM.
- Interrupted and restarted workflows never bypass approval.
- No real company/customer data or secrets in Git history, fixtures, logs or screenshots.
- Dependency failure has bounded timeouts and clear error codes.

## Operational indicators (initial design targets)

| Metric | Initial target | Caveat |
|---|---|---|
| API availability | ≥99.5% | Must define measurement window and exclusion policy |
| Normal Q&A p95 latency | ≤10s | Separate from human-approval waiting time |
| RAG Recall@5 | ≥85% | Versioned labeled dataset |
| Citation correctness | ≥95% | Manually checked evidence references |
| Cross-tenant unauthorized read | 0 cases | Run adversarial tests |
| Purchases executed without valid approval | 0 | End-to-end invariants |
| Duplicate ERP documents on retry | 0 | Include timeout-after-commit test |

Do not assert compliance with these targets until measured and published.

## Release checklist (v0.1.0)

- [ ] `docker compose up` launches required services from a clean checkout.
- [ ] Alembic migrations and synthetic fixtures install cleanly.
- [ ] Four MVP E2E paths pass in CI.
- [ ] Tenant/ACL/approval security suite passes.
- [ ] Idempotency, timeout-after-commit and worker recovery pass.
- [ ] RAG evaluation reports raw results and methodology.
- [ ] OpenAPI contract verified against implementation.
- [ ] README deployment guide and public demo use synthetic data.
- [ ] CI complete and no known Critical vulnerabilities.
- [ ] License and third-party attribution reviewed.

## Milestone backlog

| Milestone | Tasks | Exit |
|---|---|---|
| M1 Infrastructure | Docker, FastAPI, React, auth, migrations, CI | Multi-tenant skeleton with secure API |
| M2 RAG | Upload, parser, chunk, dense/sparse index, rerank, citations | Evidence-backed SOP Q&A |
| M3 ERP & Agent | PHP Demo ERP, tool contracts, LangGraph, analysis | Reproducible inventory report |
| M4 Approval | Draft, rule engine, approval, interrupt/resume, outbox | One authorized purchase despite retry |
| M5 Operations | Telemetry, dashboard, failures, security, load tests | Traceable runs and failure recovery |
| M6 Release | Docs, synthetic datasets, E2E report, demo, release | Reproducible public showcase |

Schedule is an estimate, not a commitment. Prioritize correctness, isolation and recoverability over deadline.
