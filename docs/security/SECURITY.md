# Security Model（安全模型）v0.1

> **安全設計基準，尚未通過完整安全稽核。** M1 已[有條件驗收通過](../testing/ACCEPTANCE.md)，歷史登出 500 的根因仍未確認。M2 已實作文件中繼資料讀取時的 Tenant Membership 與 ACL 檢查；文件上傳、檢索與 ERP 實際執行點授權仍待實作及驗收。

## 1. Trust Boundary（信任邊界）

1. **HTTP 邊界**：JWT 驗證使用者、檢查啟用狀態與 Tenant Membership（租戶成員資格）；`X-Tenant-ID` 僅為選擇租戶。
2. **LLM 邊界**：聊天訊息、SOP 文件、檢索文字、模型回應皆為 Untrusted Input（不可信輸入），不得給予工具權限。
3. **Tool 邊界**：工具白名單、JSON Schema（結構）驗證、倉庫 Scope（範圍）、逾時、大小限制及執行點授權。
4. **資料邊界**：PostgreSQL 跨租戶複合鍵與 RLS（資料列層級安全）、Qdrant Tenant + ACL 篩選、引用前再次檢查 PostgreSQL。
5. **ERP 交易邊界**：人工核准、職責分離、最新資料驗證、Outbox、ERP 冪等鍵與結果對帳。
6. **跨語言服務邊界**：Python FastAPI 與 **C# ASP.NET Core Demo ERP** 需有服務身分驗證，禁止直接讓外部使用者呼叫 ERP 內部寫入端點。

## 2. Role（角色）政策

| Role | SOP 問答 | 庫存分析 | 採購草稿 | 核准 |
|---|---|---|---|---|
| admin | 依 ACL | 依倉庫範圍 | 可 | 可 |
| manager | 依 ACL | 依倉庫範圍 | 可 | 可 |
| staff | 依 ACL | 依倉庫範圍 | 可 | 不可 |
| viewer | 依 ACL | 限定範圍只讀 | 不可 | 不可 |

角色僅是基本允許條件，不能自動取得全部文件或倉庫資料權限。核准時還需檢查人員與草稿建立者不可相同（職責分離）。

M1-03 已建立可重用的 Role Policy（角色政策）：`tenant.read` 開放所有成員、`member.manage` 僅 admin、`knowledge.ask` 與 `inventory.read` 開放所有成員、`purchase.draft.create` 開放 staff 以上、`purchase.approve` 開放 manager 以上。未知角色或權限一律拒絕。實際業務端點仍須另行檢查文件 ACL、Warehouse Scope（倉庫資料範圍）、核准狀態與職責分離；目前未實作這些業務端點。

## 3. 威脅與控制

| 威脅 | 防護方式 | 驗證測試 |
|---|---|---|
| 跨 Tenant 資料洩漏 | Trusted Context、複合 FK、RLS、ACL | RAG-T07 |
| SOP 文件 Prompt Injection（提示詞注入） | 文件視為資料；Tool Policy Gate（工具政策關卡） | RAG-T08 |
| Agent 執行未授權工具 | Tool Registry 白名單與執行點授權 | ERP-T07、ERP-T08 |
| 未核准採購 | DB Approval State + 權限驗證 | APR-T02、APR-T10 |
| 重放／重複採購 | 固定冪等鍵、ERP Unique Constraint、對帳 | APR-T05、APR-T07 |
| 庫存變更造成舊核准失效 | Snapshot Version（快照版本）重新驗證 | APR-T06 |
| 敏感資料落入 Log／Trace | Redaction（遮蔽）、大小限制、存取控管 | OBS-T08 |
| 惡意上傳檔案 | 類型／大小限制、解析沙箱、掃描與逾時 | Security Test |
| 資源耗盡 | Rate Limit（速率限制）、Token／Tool Budget、並行限制 | Load Test |

## 4. 資料與金鑰管理

- GitHub 公開程式庫只允許 Synthetic Data（合成資料）。
- 不提交 `.env`、API Key、JWT Secret、密碼、真實 ERP 資料或使用者個資。
- 使用 `.env.example` 放置假值，正式環境透過 Secret Manager（密鑰管理服務）或部署環境注入。
- 不在 Log 中保存完整 JWT、Prompt、文件、ERP 回應或不必要個資。
- 正常 API 程序不可使用 PostgreSQL Superuser（超級使用者）帳號；稽核 Log 對一般應用程式帳號採 Append-only（僅新增）。
- 外部 LLM Provider（模型供應者）可能涉及資料傳輸，應明確揭露並允許替換為本機 Ollama。

## 5. 公開文件政策

可公開架構、通用安全控制、API 契約與合成資料測試報告；不可公開真實環境的帳密、私密網路設定、內部事件紀錄及可立即利用的未修補弱點細節。

正式實作參考：OWASP LLM Top 10、PostgreSQL Row Security Policies、LangGraph Persistence／Interrupt、Qdrant Filter／Multitenancy 官方文件。導入前確認版本與相容性。
