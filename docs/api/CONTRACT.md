# API Contract（API 介面契約）v0.1

> 本文件區分已實作的 M1 身分驗證、租戶管理端點與後續預定的業務端點。

## 1. 共通規範

- 對外 Base Path（基本路徑）：`/api/v1`。
- `Authorization: Bearer <JWT>`：使用者驗證；已實作的受保護端點在 OpenAPI 中宣告 HTTP Bearer Security Scheme（安全機制）。
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
| POST | `/auth/session` | 瀏覽器登入，成功回 204，使用 `Set-Cookie` 傳送工作階段憑證 |
| GET | `/auth/me` | 驗證 Bearer 或工作階段 Cookie、使用者狀態與未撤銷 Session，回傳使用者 ID 及 Email |
| POST | `/auth/logout` | 撤銷目前 Session，瀏覽器模式另清除 Cookie，回傳 204 |

登入請求：`{"email":"user@example.invalid","password":"<password>"}`。成功回應包含 `access_token`、`token_type`（`Bearer`）及 UTC `expires_at`。JWT 的 `sub` 為 User ID、`jti` 為 Session ID；每次存取受保護端點必須重新檢查資料庫狀態。登入與身分驗證錯誤回傳上述 `error` 格式；422 請求結構錯誤使用 `VALIDATION_ERROR`，不回傳使用者輸入原文。尚未提供 Refresh Token（更新憑證）或公開註冊 API。

上述 JWT 回應適用於 `POST /auth/login`。瀏覽器使用同來源的 `POST /auth/session`，帳密欄位相同。後端回傳 `__Secure-agent-session` Cookie（`HttpOnly`、`Secure`、`SameSite=Strict`、`Path=/api/v1`），有效期與 JWT 和資料庫工作階段相同。瀏覽器登入與使用 Cookie 的非安全方法須帶 `X-Session-Request: 1`，缺少時回 403。提供 `Authorization` 時以該標頭為準。重新載入時 `/auth/me` 回 401 才回到登入畫面，暫時性錯誤提供重試。

登入嘗試以 Redis 對來源 IP 設定每 60 秒 10 次、對帳號設每 300 秒 5 次限制，超過回傳 429；Redis 無法使用時回傳 503。帳號識別以 HMAC 處理，不將 Email 原文寫入 Redis Key。伺服器只使用連線來源位址，不採信未受控的代理轉送 Header。

首次管理員與租戶透過本機互動式初始化指令建立；目前沒有公開註冊 API。

### 已實作：租戶讀取端點

| Method | Endpoint | 功能 |
|---|---|---|
| GET | `/tenants` | 只列出目前使用者所屬且啟用的租戶，使用 UUID `cursor` 分頁，每頁最多 50 筆 |
| GET | `/tenants/{tenant_id}` | 查詢目前使用者所屬的啟用租戶；其他租戶及不存在的租戶均回 404 |
| GET | `/tenants/current` | 依 `X-Tenant-ID` 查詢目前選擇的啟用租戶；每次以資料庫成員資格建立可信 Tenant Context（租戶上下文） |
| GET | `/tenants/current/warehouse-scopes` | 列出目前成員明確授權的倉庫代碼，無授權時回空列表 |
| GET | `/tenants/current/warehouse-scopes/{warehouse_code}` | 檢查指定倉庫代碼是否在目前成員的租戶範圍內，未授權與不存在均回 404 |
| POST | `/tenants/{tenant_id}/members` | 該租戶 admin 建立新 User 與 manager、staff 或 viewer Membership；回傳 201 |
| PATCH | `/tenants/{tenant_id}/members/{user_id}` | 該租戶 admin 變更非 admin 成員角色；回傳更新後成員 |
| DELETE | `/tenants/{tenant_id}/members/{user_id}` | 該租戶 admin 撤銷非 admin 成員資格；回傳 204 |
| PUT | `/tenants/{tenant_id}/members/{user_id}/warehouse-scopes/{warehouse_code}` | 該租戶 admin 對現有成員授予已登錄至本租戶的倉庫範圍；重複執行安全 |
| DELETE | `/tenants/{tenant_id}/members/{user_id}/warehouse-scopes/{warehouse_code}` | 該租戶 admin 撤銷成員的指定倉庫範圍；回傳 204 |

列表回應為 `{"items":[{"id":"<uuid>","name":"合成租戶","role":"staff"}],"next_cursor":null}`。前兩個讀取端點只供租戶選擇與呈現；後續受保護業務端點仍須重新驗證 `X-Tenant-ID` 與 Membership。

`GET /tenants/current` 必須同時帶有效憑證與 `X-Tenant-ID`。Header 只表示選擇；後端從資料庫檢查啟用租戶及目前 User 的 Membership，其他租戶與停用租戶回 404。成功回應包含 `id`、`name`、`role` 及目前角色的 `permissions` 陣列。個別資源仍須通過 ACL 或倉庫範圍檢查。

倉庫範圍端點也需有效 JWT 與 `X-Tenant-ID`，先檢查 `inventory.read` 角色權限，再以 `(tenant_id, user_id, warehouse_code)` 查詢明確授權。列表回應為 `{"items":["WH-001"],"next_cursor":null}`；使用代碼字串 `cursor` 分頁，每頁最多 50 筆。目前只提供授權代碼查詢，尚未查詢 ERP 倉庫資料或驗證其租戶歸屬。授權寫入與 ERP 讀取必須在後續工作補上雙重檢查。

倉庫範圍寫入須先由資料庫操作員核對 ERP 歸屬並登錄 `tenant_warehouses`。租戶 admin 只能將本租戶已登錄的代碼授予本租戶現有成員；跨租戶、未知成員、未登錄代碼均回 404，非 admin 回 403。`PUT` 回 `{"warehouse_code":"WH-001"}`；重複 `PUT` 不新增重複資料列，Membership 撤銷時倉庫 Scope 由外鍵連動刪除。此流程不取代 ERP Read API 實際執行點的租戶與倉庫權限再驗證。

新增成員請求為 `{"email":"new@example.invalid","password":"<password>","role":"staff"}`，回應包含新 User 的 `id`、`tenant_id`、正規化後的 `email` 與 `role`，不回傳密碼或雜湊。端點在同筆交易建立 User 與 Membership，鎖定呼叫者在該租戶的 admin Membership。無成員資格或租戶停用回 404，非 admin 回 403，Email 已存在回 409；不得藉此建立其他租戶的成員或新的 admin。

角色變更請求為 `{"role":"manager"}`，僅允許 manager、staff 或 viewer。撤銷只刪除指定租戶的 Membership，User 在其他租戶的成員資格不受影響；已撤銷者下一次租戶查詢立即看不到該租戶。不可修改 admin Membership。全域 User 停權及新租戶建立限資料庫操作員透過本機受控指令執行；未提供可由 JWT 呼叫的全域管理 API。

## 2. SOP Knowledge（知識庫）API

| Method | Endpoint | 功能 | 權限 |
|---|---|---|---|
| POST | `/documents` | 儲存 PDF 並持久登錄待處理工作 | staff 以上 |
| GET | `/documents` | 列出可存取文件 | 成員 + ACL |
| GET | `/documents/{id}` | 文件 Metadata（中繼資料） | ACL |
| GET | `/documents/{id}/status` | 查看索引狀態 | ACL |
| POST | `/documents/{id}/versions` | 上傳新版本 | Owner / manager / admin |
| POST | `/knowledge/search` | ACL 篩選檢索 | 成員 + ACL |
| POST | `/knowledge/ask` | 產生附來源引用的回答 | 成員 + ACL |
| DELETE | `/documents/{id}` | 邏輯刪除 | Owner / admin |

上傳端點 `POST /documents` 接受 `multipart/form-data`，包含 `title`（去除首尾空白後 1–255 字元）及一個 `file`（`application/pdf`、最多 10 MiB、須有 PDF 檔頭）。整體請求上限為 10 MiB + 64 KiB。須帶入 `X-Tenant-ID` 及 UUID 格式的 `Idempotency-Key`，並使用 Bearer JWT 或瀏覽器工作階段（Cookie 請求另帶 `X-Session-Request: 1`）。

成功回 202 及 `document_id`、`version_id`。同租戶、建立者、標題及 SHA256 使用同鍵重試，須仍具上傳角色與建立者 ACL 才能取得相同識別。不同內容或無法使用原預約回 409。超限回 413，媒體類型或 PDF 檔頭不符回 415，欄位或 multipart 錯誤回 422。無法確認儲存時回 503，可使用原鍵及原內容重試。202 表示已儲存並登錄待處理工作，版本尚未發布。

中繼資料端點 `GET /documents/{id}` 已實作。必須帶 `Authorization: Bearer <JWT>` 與 `X-Tenant-ID`；後端重新驗證有效租戶成員資格，且該成員目前角色須在文件的 `document_acl` 中，或使用者須在 `document_user_acl` 中。只回傳 `status = active` 的文件；文件不存在、屬於其他租戶、已刪除或沒有 ACL 權限時一律回 404 `DOCUMENT_NOT_FOUND`，避免洩漏存在與否。成功回應為 `{"id":"<uuid>","tenant_id":"<uuid>","title":"合成文件","current_version":null,"created_at":"<UTC timestamp>"}`。`current_version` 為 `null` 表示尚未發布版本；此端點不回傳原始文件或索引內容。原文讀取及知識 API 仍為規劃中。

`GET /documents` 以相同租戶與 ACL 條件列出未刪除文件，依文件 UUID 遞增排序；每頁最多 50 筆，接受可選的 `cursor` UUID，回傳 `{"items":[<上述 Metadata>],"next_cursor":"<uuid>"}`，末頁的 `next_cursor` 為 `null`。不得從項目數量或游標洩漏其他租戶或無權限文件。

`GET /documents/{id}/status` 已實作，沿用單筆文件的有效成員資格與角色／指定使用者 ACL 判斷；無權限、已刪除或不存在均回 404 `DOCUMENT_NOT_FOUND`。回應為 `{"document_id":"<uuid>","current_version":1,"latest_version":2,"storage_status":"pending_upload","indexing_status":"pending"}`；尚無版本時後四個狀態欄位均為 `null`。`latest_version` 是版本號最大的紀錄，`current_version` 是已選版本，兩者可能不同；此端點不回傳原始文件、物件鍵或索引內容，也不代表索引已排程。

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
