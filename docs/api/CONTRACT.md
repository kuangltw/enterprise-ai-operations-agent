# API Contract v0.1

> Planned REST/SSE API specification. No endpoints are implemented as of 2026-11-12. Base path: `/api/v1`.

## Global conventions

- Authorization: `Authorization: Bearer <JWT>`.
- Tenant selection: `X-Tenant-ID: <uuid>`; server verifies active membership. Header is **not** an authorization grant.
- Correlation: `X-Request-ID: <uuid>`; every request has a trace ID.
- Mutating async requests: `Idempotency-Key: <uuid>`; enforce scope, payload fingerprint and unique constraint.
- Use UTC ISO 8601, UUID identifiers, JSON Decimal strings for money and quantities; paginated list responses have `items` and `next_cursor`.
- Errors: consistent typed error envelope; do not expose cross-tenant resource existence.
- Permission scope includes user role, document ACL and authorized warehouses; role alone is insufficient.

### Error envelope

```json
{
  "error": {
    "code": "APPROVAL_VERSION_CONFLICT",
    "message": "採購草稿版本已變更，請重新載入。",
    "details": {"expected_version": 3, "current_version": 4},
    "trace_id": "trace-example"
  }
}
```

Status policy: 400 invalid input; 401 unauthenticated; 403 forbidden; 404 not found/inaccessible; 409 conflict; 422 schema validation; 429 rate limit; 503 dependency unavailable.

## Document/knowledge endpoints

| Method | Endpoint | Purpose | Authorization |
|---|---|---|---|
| POST | `/documents` | Multipart upload, async ingestion | staff+ |
| GET | `/documents` | Paginated accessible document list | membership + ACL |
| GET | `/documents/{id}` | Document metadata | ACL |
| GET | `/documents/{id}/status` | Indexing state | ACL |
| POST | `/documents/{id}/versions` | Upload replacement version | owner/manager/admin |
| POST | `/knowledge/search` | ACL-filtered search | membership + ACL |
| POST | `/knowledge/ask` | Evidence-backed answer | membership + ACL |
| DELETE | `/documents/{id}` | Logical deletion | owner/admin |

Example request `POST /knowledge/ask`:

```json
{"question":"商品缺貨時的採購處理規範是什麼？","top_k":5}
```

Example `200` response (placeholder IDs denote UUIDs in actual implementation):

```json
{
  "answer":"依採購規範，應先確認現有庫存及待入庫量。",
  "citations":[{"document_id":"<uuid>","version":2,"chunk_id":"<uuid>","page":3,"quote":"缺貨商品應先確認可用庫存...","score":0.91}],
  "evidence_status":"supported",
  "trace_id":"trace-example"
}
```

Insufficient evidence: `{"answer":"目前知識庫沒有足夠資料可以確認。","citations":[],"evidence_status":"insufficient"}`. Citation `score` is not a calibrated confidence probability.

## Agent execution endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/agent/threads` | Create conversation thread |
| POST | `/agent/runs` | Create asynchronous run |
| GET | `/agent/runs/{id}` | Read run status and output |
| GET | `/agent/runs/{id}/events` | Authenticated SSE stream |
| POST | `/agent/runs/{id}/cancel` | Request cancellation |
| GET | `/agent/runs/{id}/trace` | Authorized summarized event trace |

`POST /agent/runs`:

```json
{"thread_id":"<uuid>","message":"分析最近30天缺貨商品，產生採購建議","context":{"warehouse_ids":["WH-001"],"period_days":30}}
```

`202 Accepted`:
```json
{"run_id":"<uuid>","status":"queued","events_url":"/api/v1/agent/runs/<uuid>/events"}
```

Use event IDs for resumption where supported; redact event payloads; do not leak traces across users. Cancel is best-effort and cannot roll back already committed ERP writes.

## ERP internal tool contract (not publicly exposed)

| Tool | Method/path | Side effect |
|---|---|---|
| inventory.list_low_stock | GET `/internal/inventory/low-stock` | read |
| inventory.get_snapshot | GET `/internal/inventory/snapshot` | read |
| sales.get_summary | GET `/internal/sales/summary` | read |
| purchase.get_open_orders | GET `/internal/purchases/open` | read |
| purchase.simulate | POST `/internal/purchases/simulate` | deterministic, read-only |
| purchase.create_order | POST `/internal/purchases` | write, strictly approval-gated |

Every tool declares: input/output JSON schema, required permission, scope, timeout, allowed retries, maximum result size and auditing. ERP endpoints recheck authorization and never accept unbounded SQL.

Sample `inventory.get_snapshot` input:
```json
{"warehouse_id":"WH-001","sku":"SKU-10001"}
```

Output:
```json
{"sku":"SKU-10001","warehouse_id":"WH-001","on_hand":"120","reserved":"35","available":"85","incoming":"40","version":18,"as_of":"2026-11-12T10:00:00Z"}
```

**Terminology invariant:** specify if `reserved` equals outstanding demand; avoid deducting the same committed quantity again as `backorders`. Record snapshot/source versions in analysis results.

## Purchase/approval endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/purchase-drafts` | Authorized list |
| GET | `/purchase-drafts/{id}` | Draft with evidence and calculations |
| POST | `/purchase-drafts/{id}/submit` | Submit frozen version for approval |
| GET | `/approvals` | Current user's eligible pending approvals |
| POST | `/approvals/{id}/decision` | Approve or reject |
| GET | `/erp-actions/{id}` | Execution/reconciliation state |

Approval request:
```json
{"decision":"approve","expected_draft_version":3,"note":"補貨需求確認"}
```

`202 Accepted`:
```json
{"approval_id":"<uuid>","status":"approved","erp_action_status":"pending"}
```

Approval is an authorization decision only; ERP commit occurs asynchronously. Under DB transaction: lock draft + approval, check actor permission / separation of duties / version, commit decision and outbox event. A worker then performs revalidation and guarded write. Unknown write results must be reconciled by idempotency key.

## Planned OpenAPI verification

Use FastAPI-generated `/openapi.json` as executable API schema, snapshot/validate in CI and keep examples in this document synchronized with the implementation. All DTOs require Pydantic validation; reject unknown action names, unexpected warehouse IDs, invalid currency/quantity, oversized payloads.
