# API Contract（API 介面契約）v0.1

> 本文件包含已實作的 M1 身分驗證端點與後續預定規格；尚未完成租戶及業務端點。

## 1. 共通規範

- 對外 Base Path（基本路徑）：`/api/v1`。
- `Authorization: Bearer <JWT>`：使用者驗證。
- `X-Tenant-ID: <uuid>`：選擇租戶；後端必須驗證成員資格，Header 不等於授權。
- `X-Request-ID: <uuid>`：Trace Correlation（追蹤關聯）。
- `Idempotency-Key: <uuid>`：非同步建立與高風險交易防重複。
- 時間使用 ISO 8601 UTC、ID 使用 UUID、金額與精確數量在 JSON 中使用十進位字串。
- List API（列表介面）使用 `items` 與 `next_cursor` 分頁。
- 授權條件同時包含 Tenant、Role（角色）、文件 ACL 與倉庫範圍。

### 統一錯誤格式

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

狀態碼：400 參數錯誤、401 未登入、403 無權限、404 不存在或不可存取、409 衝突、422 Schema 驗證失敗、429 速率限制、503 依賴服務不可用。

### 已實作：身分驗證端點

| Method | Endpoint | 功能 |
|---|---|---|
| POST | `/auth/login` | 以 Email 與密碼登入，回傳 15 分鐘有效的 JWT |
| GET | `/auth/me` | 驗證 JWT、使用者狀態與未撤銷 Session，回傳使用者 ID 及 Email |
| POST | `/auth/logout` | 撤銷目前 Session，回傳 204 |

登入請求：`{"email":"user@example.invalid","password":"<password>"}`。成功回應包含 `access_token`、`token_type`（`Bearer`）及 UTC `expires_at`。JWT 的 `sub` 為 User ID、`jti` 為 Session ID；每次存取受保護端點必須重新檢查資料庫狀態。登入與身分驗證錯誤回傳上述 `error` 格式；422 請求結構錯誤仍使用 FastAPI 預設格式，待 M1-05 統一。尚未提供 Refresh Token（更新憑證）、公開註冊或租戶選擇 API。

登入嘗試以 Redis 對來源 IP 設定每 60 秒 10 次、對帳號設每 300 秒 5 次限制，超過回傳 429；Redis 無法使用時回傳 503。帳號識別以 HMAC 處理，不將 Email 原文寫入 Redis Key。伺服器只使用連線來源位址，不採信未受控的代理轉送 Header。

首次管理員與租戶透過本機互動式初始化指令建立；目前沒有公開註冊 API，也沒有管理其他使用者與 Membership（成員資格）的寫入 API。

### 已實作：租戶讀取端點

| Method | Endpoint | 功能 |
|---|---|---|
| GET | `/tenants` | 只列出目前使用者所屬且啟用的租戶，使用 UUID `cursor` 分頁，每頁最多 50 筆 |
| GET | `/tenants/{tenant_id}` | 查詢目前使用者所屬的啟用租戶；其他租戶及不存在的租戶均回 404 |

列表回應為 `{"items":[{"id":"<uuid>","name":"合成租戶","role":"staff"}],"next_cursor":null}`。這兩個端點只供租戶選擇與呈現；後續受保護業務端點仍須重新驗證 `X-Tenant-ID` 與 Membership。

## 2. SOP Knowledge（知識庫）API

| Method | Endpoint | 功能 | 權限 |
|---|---|---|---|
| POST | `/documents` | 上傳文件並建立非同步索引任務 | staff 以上 |
| GET | `/documents` | 列出可存取文件 | 成員 + ACL |
| GET | `/documents/{id}` | 文件 Metadata（中繼資料） | ACL |
| GET | `/documents/{id}/status` | 查看索引狀態 | ACL |
| POST | `/documents/{id}/versions` | 上傳新版本 | Owner / manager / admin |
| POST | `/knowledge/search` | ACL 篩選檢索 | 成員 + ACL |
| POST | `/knowledge/ask` | 產生附來源引用的回答 | 成員 + ACL |
| DELETE | `/documents/{id}` | 邏輯刪除 | Owner / admin |

`POST /knowledge/ask` Request（請求）：

```json
{"question":"商品缺貨時的採購處理規範是什麼？","top_k":5}
```

Response（回應）200：

```json
{
  "answer": "依採購規範，應先確認現有庫存及待入庫數量。",
  "citations": [
    {
      "document_id": "<uuid>",
      "version": 2,
      "chunk_id": "<uuid>",
      "page": 3,
      "quote": "缺貨商品應先確認可用庫存...",
      "score": 0.91
    }
  ],
  "evidence_status": "supported",
  "trace_id": "trace-example"
}
```

資料不足：`evidence_status = "insufficient"`，`citations = []`。Score（排序分數）不等於經校準的回答正確率。

## 3. Agent Run（執行）API

| Method | Endpoint | 用途 |
|---|---|---|
| POST | `/agent/threads` | 建立對話 |
| POST | `/agent/runs` | 建立非同步 Agent Run |
| GET | `/agent/runs/{id}` | 查詢結果與狀態 |
| GET | `/agent/runs/{id}/events` | SSE（伺服器推送事件） |
| POST | `/agent/runs/{id}/cancel` | 要求取消 |
| GET | `/agent/runs/{id}/trace` | 查詢執行節點摘要 |

`POST /agent/runs`：

```json
{
  "thread_id": "<uuid>",
  "message": "分析最近30天缺貨商品，產生採購建議",
  "context": {"warehouse_ids": ["WH-001"], "period_days": 30}
}
```

回傳 `202 Accepted`：

```json
{
  "run_id": "<uuid>",
  "status": "queued",
  "events_url": "/api/v1/agent/runs/<uuid>/events"
}
```

`cancel` 是 Best-effort（盡力取消），不能復原 ERP 已提交交易。SSE 與 Trace 同樣需要使用者授權。

## 4. Demo ERP Tool Contract（工具契約）

**使用 C# + ASP.NET Core Web API 實作**，由 Python Agent 的 Tool Adapter（工具轉接器）以 HTTP 呼叫。ERP 內部端點不直接暴露於公網。建議使用 ASP.NET Core Controllers 或 Minimal API；正式選型於 M3 決定，OpenAPI Contract 優先。

| Tool Name | ERP Method / Path | 類型 |
|---|---|---|
| `inventory.list_low_stock` | GET `/internal/inventory/low-stock` | 讀取 |
| `inventory.get_snapshot` | GET `/internal/inventory/snapshot` | 讀取 |
| `sales.get_summary` | GET `/internal/sales/summary` | 讀取 |
| `purchase.get_open_orders` | GET `/internal/purchases/open` | 讀取 |
| `purchase.simulate` | POST `/internal/purchases/simulate` | 只讀模擬 |
| `purchase.create_order` | POST `/internal/purchases` | 受核准控管寫入 |
| `purchase.get_by_idempotency_key` | GET `/internal/purchases/by-idempotency-key/{key}` | 寫入對帳 |

每個 Tool 必須定義 Input/Output Schema（輸入輸出結構）、授權、Timeout（逾時）、Retry（重試）、大小限制與 Audit（稽核）。ERP 端也必須獨立驗證內部服務身分及授權上下文，禁止任意 SQL。

庫存快照範例：

```json
{
  "sku": "SKU-10001",
  "warehouse_id": "WH-001",
  "on_hand": "120",
  "reserved": "35",
  "available": "85",
  "incoming": "40",
  "version": 18,
  "as_of": "2026-11-12T10:00:00Z"
}
```

`reserved` 與 `backorders` 的定義必須在 M3 確認，避免補貨公式重複扣除已承諾數量。C# 端金額／數量使用 `decimal` 而非 `double`。

## 5. 採購及人工核准 API

| Method | Endpoint | 用途 |
|---|---|---|
| GET | `/purchase-drafts` | 採購草稿列表 |
| GET | `/purchase-drafts/{id}` | 明細與來源依據 |
| POST | `/purchase-drafts/{id}/submit` | 凍結版本並送審 |
| GET | `/approvals` | 待審清單 |
| POST | `/approvals/{id}/decision` | 核准／駁回 |
| GET | `/erp-actions/{id}` | ERP 寫入狀態及對帳 |

核准 Request：

```json
{
  "decision": "approve",
  "expected_draft_version": 3,
  "note": "補貨需求確認"
}
```

Response `202 Accepted`：

```json
{
  "approval_id": "<uuid>",
  "status": "approved",
  "erp_action_status": "pending"
}
```

核准不代表 ERP 已建立採購單。核准時需在資料庫 Transaction（交易）中鎖定草稿、驗證權限與版本、寫入決策及 Outbox Event；Worker 重新驗證資料後才執行 ERP Write API。未知結果先依固定冪等鍵對帳。

## 6. Contract Test（契約測試）

FastAPI 與 ASP.NET Core 均應產生 OpenAPI 文件，並在 CI 比對契約；測試跨語言 Decimal 字串、UUID、版本衝突、授權錯誤及冪等語意。所有外部參數需進行 DTO（資料傳輸物件）驗證。
