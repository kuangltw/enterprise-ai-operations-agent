# 開發進度（Codex 交接紀錄）

> 狀態以實際測試與 Commit 為準，禁止未經驗證直接標示完成。

| 階段 | 狀態 | 證據 |
|---|---|---|
| M1-01 環境驗證 | 本機已完成 | [驗證紀錄](M1-01-VERIFICATION.md) |
| 本機 Git 機密防護 | 本機已完成 | 2026-11-12 隔離 Repository 提交測試 6 項通過；安全修正 `141ffae9f35f91ecde0e16060ac10d9447d186f0` |
| M1-02 身分驗證與租戶管理 | 本機功能完成，整合驗收待 M1-05 | 密碼雜湊、JWT、Session、首次建帳、受控新租戶、成員管理及全域停權已有測試；空白資料庫初始化案例在既有資料庫跳過 |
| M1-03 RBAC 與租戶隔離 | 本機基礎完成，ERP 執行點待 M3 | Tenant Context、Role Policy、倉庫 Scope 與跨租戶測試已實作；實際 ERP 倉庫歸屬仍需 M3 複驗 |
| M1-04 React 登入與管理介面 | 本機 Headless 瀏覽器驗收通過，仍有間歇性 API 風險 | Playwright Test 驗證登入、錯誤密碼、租戶切換、跨租戶拒絕與登出；一次登出回 500 後未再重現 |
| M1-05 CI 與整合驗收 | Accepted with Known Issues（有條件驗收通過） | `66aabc9` 的 Python、dotnet、frontend、compose、e2e 與 Gitleaks 工作成功；本次隔離 E2E 4 passed；單次登出 500 留存[獨立追蹤](issues/LOGOUT-500.md) |
| M2 RAG | 文件中繼資料、ACL、PDF 上傳與索引工作持久登錄已實作 | `0006_documents` 至 `0009_document_index_jobs`；隔離 PostgreSQL／MinIO 已測上傳 API；清理、Worker、掃描、解析、索引及問答待完成 |

## 下一個任務

> 2026-11-13 第三切片安全設計：新增 [清理設計與待執行測試矩陣](../architecture/M2-01-CLEANUP-DESIGN.md)。獨立安全審查為 **CONDITIONAL PASS**；舊 PUT 排空、故障還原與資料面隔離仍有 High 未驗證，**不得開始正式刪除實作**。

> 2026-11-13 獨立複驗：第二切片唯讀範圍為 **CONDITIONAL PASS**；第三切片高風險刪除實作仍受阻，詳見 [獨立驗證報告](INDEPENDENT-REVIEW-M2-01.md)。下方既有工作清單與 agy 歷史測試記錄不代表解除此限制。

1. M2-01 第三階段：退役鍵切換、可控孤兒物件清理（Dry Run、實際刪除與授權檢查分離，並在 `complete_document_upload` 防範已退役鍵復活），以及故障注入與並行回歸測試。第一切片已提交 `7c61e1444a0d4b3275ffbdfc4606c0b963375419`，第二切片已由 agy 完成驗證與獨立安全審查（本切片 Commit SHA 以 Git 紀錄為準）。RAG-T01 仍待驗收。歷史瀏覽器登出 500 依[追蹤紀錄](issues/LOGOUT-500.md)保留。
2. 每完成小任務更新本檔：日期、檔案、測試指令、執行結果、Commit SHA、資安風險及下一項工作。

## 2026-11-13 M2-01 第三切片安全設計

- 範圍：僅設計及測試規格，未修改業務程式、操作 PostgreSQL／MinIO 或執行刪除。初評及文件差異重評均命中租戶隔離、安全架構、跨系統一致性、交易鎖、並行、冪等與復原強制條件；本輪未修改 migration／約束 +0、未修改 API 或三個程式模組 +0、需求明確 +0，合計 0 分，仍強制升級。主代理整合；Architect 前置設計及 Security Reviewer 獨立設計審查與修訂重驗均為唯讀。
- 執行證據：Architect 子代理 `01a1d4b4-3930-7202-b920-4c8b69229c52` 實際回合 `01a1d4b4-3a3d-7e63-b3b1-a6ccdb723bdf`、Security Reviewer 子代理 `01a1d4b6-6f4d-7450-b058-b3605ffa8ed3` 實際回合 `01a1d4b6-704e-75f1-b1cc-1900f6b35994` 的執行紀錄皆為 `gpt-6.1-sol`／`high`。Security Reviewer 結論 **CONDITIONAL PASS**；未發現 Critical，但在途 PUT 排空、永久墓碑與 storage incarnation 的故障存續、DB 約束與資料面租戶隔離仍為 High 放行阻礙。
- 測試：本輪為靜態設計審查，未執行隔離 PostgreSQL、MinIO、實際網路中斷或完整 Alembic 並行驗證；文件的 12 類案例及附加案例均為待執行規格。既有結果見獨立驗證報告，不重稱為本輪測試。
- 本輪檔案：清理架構設計與本進度紀錄。提交識別、Gitleaks、Hook 與最終工作樹狀態以本輪實際結果及 Git 紀錄為準；未 Push。官方額度起始五小時剩餘 74%、每週剩餘 68%。
- 下一步：先設計並在隔離環境證明有效寫入排空及租戶資料面隔離，驗證具體 DDL、鎖序、故障恢復及完整 downgrade，並重新取得獨立高風險審查；上述條件未解除前不得開始正式刪除實作。

## 2026-11-13 M2-01 第二切片獨立複驗

- 獨立 Security Reviewer 與 Architect 均依實際回合紀錄確認為 GPT-6.1 Sol High，唯讀審查上傳、退役鍵、預覽、0010、鎖序及第三切片邊界；結論為 CONDITIONAL PASS，未發現第二切片唯讀功能的阻擋缺陷。
- 沿用前輪隔離環境的 26 項回歸、2 項 PostgreSQL 邊界測試及 6 項 Hook 測試結果，本輪審查未重跑；完整 Alembic 並行降版、真實網路中斷及 Cleaner／Uploader 交錯仍待驗。退役鍵仍可被有效版本引用，降版與預覽存在未重現的潛在反向鎖序；不得據此授權實際刪除或正式降版。
- 本輪修改獨立報告及本進度紀錄，保留既有新增並行測試與 Hook 行尾差異；提交與掃描狀態以 Git 紀錄及最終交接為準。未 Push。

## 2026-11-13 M2-01 退役鍵預覽（agy 接手驗證完成）

- agy 接手後核對 `HANDOFF.md` 與 Git 狀態（基準 HEAD `9fa837b`，三個未追蹤第二切片檔案完整保留），在隔離 tmpfs PostgreSQL 與 MinIO（合成資料）完成修正後驗證：
  - `alembic upgrade head` 套用至 `0010_document_retired_keys` 成功；`alembic downgrade 0010_document_retired_keys:0009_document_index_jobs --sql` 產出離線 SQL 明確包含 `BEGIN;`、`LOCK TABLE document_upload_retired_keys IN ACCESS EXCLUSIVE MODE;`、`DO $$ ... RAISE EXCEPTION ... $$` 與 `COMMIT;`。
  - 修正後重跑第二切片與文件／ACL 六個測試檔（`test_document_cleanup_preview_postgres.py`、`test_documents_postgres.py`、`test_document_api_postgres.py`、`test_document_list_postgres.py`、`test_document_status_postgres.py`、`test_document_upload_state_postgres.py`）：**12 passed, 1 warning**。
  - 並行與鎖定驗證（2 項隔離並行案例全數通過）：(1) Session 2 先插入退役鍵未提交時，Session 1 執行 `downgrade()` 會被 `ACCESS EXCLUSIVE` 鎖阻塞，待 Session 2 提交後立即拋出「退役鍵紀錄非空」並保留資料表與紀錄；(2) Uploader 持有 `FOR UPDATE` 鎖定版本期間，Cleaner 唯讀預覽 `preview_upload_cleanup` 不阻塞，且 Uploader 完成上傳寫入 `stored` 與 `document_index_jobs` 後，預覽立即排除該版本。
  - 全套文件／上傳／ACL／儲存回歸測試（12 個測試檔於乾淨 tmpfs PostgreSQL + MinIO）：**35 passed, 1 warning**。
- 獨立 Security Review（`research` 子代理高推理模型唯讀審查）：判定**通過（Pass with Recommendations）**，無 Critical 阻擋項。另於 PostgreSQL 16 實測 `E'abc\n' ~ '^abc$'` 回傳 `false`，確認預設 ARE 模式不會誤納末尾換行符。審查所提「`complete_document_upload` 防範已退役鍵復活」、「Cleaner 刪除前須在 `FOR UPDATE` 下重驗資格並寫入退役鍵」與「`document_versions(storage_key)` 索引」已列為第三階段設計必納項目。
- 本切片於通過 Gitleaks 8.30.1 暫存區掃描與 `.githooks/pre-commit` Hook 檢查後建立正體中文 Commit（SHA 以 Git 紀錄為準），未 Push。退役鍵實際切換、延遲 PUT／DELETE 對帳與可控孤兒清理待第三階段實作。

## 2026-11-13 M2-01 上傳失敗狀態（第一切片已提交）

- 實作差異已加入 `complete_document_upload`：MinIO 寫入後只有重新讀取明確回報 `NoSuchKey` 時才將仍在版本鎖下的 `pending_upload`／`failed` 記為 `failed`；內容不符或讀取結果不明時保留原狀。`stored` 不會降級；資料庫提交結果不明會回 503，供同鍵重試重新讀取與對帳。`failed` 代表本次未確認成功且可重試，先前逾時的 PUT 仍可能晚到，故不是物件不存在的證明或清理授權。
- 初評命中 PostgreSQL／MinIO 一致性、交易鎖、並行、冪等、復原及 Tenant／ACL 安全強制升級條件。加分為：無 Migration／資料約束 +0；在既有 503 契約內調整，未達影響至少三個模組的標準 +0；規格已有設計且非難重現錯誤 +0，合計 0 分但因強制條件升級。實作後依 Diff 重評，仍命中相同強制條件、加分 0 分。Architect 前置設計與 Security Reviewer Sol High 獨立差異審查均已完成；主代理 Code Review 已完成，未發現阻擋缺陷。Explorer 使用 GPT-6 Luna Low 完成唯讀追蹤。實際物件刪除仍須另行設計實作及獨立審查。
- 在隔離 PostgreSQL／MinIO 容器（資料使用 tmpfs、合成測試資料、MinIO 測試應用帳號非 Root）套用 `alembic upgrade head` 至 `0009_document_index_jobs` 成功；兩個上傳測試檔共 **12 passed、1 warning**。首次收集測試因環境缺少 `python-multipart` 相依而失敗；改以目前 `requirements-dev.txt` 安裝測試相依後重跑通過。容器與測試資料已清理。
- 另以隔離環境執行 PDF 上傳 API、ACL 與物件儲存回歸，共九個測試檔 **19 passed、1 warning**；未改動測試以放寬授權條件。此結果與前述兩個上傳測試檔分開記錄。
- 測試涵蓋寫入失敗後同鍵恢復、`stored` 不降級、索引工作唯一性及提交結果不明。提交回應遺失由包裝 `Session.commit` 的故障注入模擬，並非真正資料庫連線中斷；因此不宣稱已驗證實際斷線後由全新連線重試。Security Reviewer 依 GPT-6.1 Sol High 執行紀錄完成差異審查，未發現阻擋缺陷；`failed` 仍可能遇到晚到的 MinIO PUT，禁止 Cleaner 僅依此狀態刪除。
- 第一切片 Gitleaks 暫存掃描及提交 Hook 均掃描 7 個檔案通過；中文 Commit 為 `7c61e1444a0d4b3275ffbdfc4606c0b963375419`，未 Push。孤兒清理、退役鍵切換、延遲 PUT／DELETE 對帳及 Cleaner 並行仍未實作或驗收。

## 2026-11-13 強制風險評分與模型分流

- `AGENTS.md` 定義任務初評、實作後依 Git Diff 重評、強制條件與 4 分升級門檻。Architect、Security Reviewer 依分流做設計、審查或修正重驗；Implementer、Tester 將新風險交回主代理。只有執行紀錄確認 Sol High 且審查完成，才能記為已審。
- 依 [OpenAI 子代理文件](https://learn.chatgpt.com/docs/agent-configuration/subagents)使用專案指令與自訂角色的 `developer_instructions`、`model`、`model_reasoning_effort`。Python 3.12 `tomllib` 核對七個 TOML；Desktop 內建執行檔與獨立 CLI 的 `app-server --strict-config --print-startup-config` 均成功。Desktop 內建 App Server 新對話仍採 Terra Medium，並行上限為 2。
- 新開唯讀對話以九個合成案例核對風險分流，九案結果符合預期，涵蓋 0 分強制升級、4 分升級、同列只計一次、實作後新風險、模型待驗、重大問題重驗及雙角色審查。測試只驗證分流判定，本輪未實際委派 Sol 審查。未執行 M2 業務測試；本輪僅調整開發規範，提交識別見 Git 紀錄。

## 2026-11-13 Codex Desktop 多代理調度

- 新增 `.codex/config.toml` 及 `.codex/agents/` 下六個自訂角色，`AGENTS.md` 定義自動分工、高風險 Sol High 審查與主代理的測試、機密掃描及提交責任。專案預設 GPT-6.1 Terra Medium，每個對話最多同時開啟兩個子代理。
- 本機版本為 Codex Desktop `26.1106.6628.0`，內建執行檔 `0.167.0-alpha.4.1`，獨立 CLI `0.167.1`。Python 3.12 `tomllib` 通過七個設定檔的解析、角色欄位及模型／強度檢查。兩個執行檔的 `app-server --strict-config --print-startup-config` 均成功；Desktop 內建 App Server 的 `config/read` 讀到專案預設與並行上限，`model/list` 列出三組指定模型及強度，`thread/start` 在未指定模型時採用 Terra Medium。
- 專案需受信任才會載入設定。已開啟的對話可能保留舊設定，請用專案新對話核對。Desktop 介面若帶入其他模型或推理強度，在輸入框下方選 GPT-6.1 Terra／Medium。子代理繼承主對話的沙箱與核准權限，角色的唯讀要求由指令約束；工具層級唯讀由主對話權限設定。依據 [OpenAI 子代理文件](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[設定優先順序](https://learn.chatgpt.com/docs/config-file/config-basic)及[模型文件](https://learn.chatgpt.com/docs/models)。
- 暫存唯讀 App Server 對話以 `never` 核准策略執行。六個角色均完成，`subAgentActivity` 啟動事件確認 Explorer／Docs 為 Luna Low、Implementer／Tester 為 Terra Medium、Architect／Security Reviewer 為 Sol High。測試分批執行，每批最多兩個。
- Explorer 追蹤 PDF 上傳入口及 MinIO 寫入點。Tester 獨立執行 `git diff --check -- AGENTS.md`，退出碼 0；子代理啟動 Python 遭拒，七個 TOML 的解析由主代理驗證。Architect 核對版本發布不變條件，提出儲存成功而資料庫提交失敗時保留舊發布版本的測試情境。Docs、Implementer、Security Reviewer 完成調度規則、預設模型及權限繼承的唯讀檢查。
- Desktop 圖形介面的新對話模型選擇優先順序、超過並行上限的拒絕行為及寫入權限未實測。未取得可按模型歸屬的用量統計。提交識別見本節的 Git 紀錄。

## 2026-11-13 工作階段撤銷時差回歸

- 上傳整合回歸發現 PostgreSQL 拒絕早於工作階段建立時間的撤銷時間。以可控 30 秒差重現；登出和全域停權在同一筆 SQL 更新保留建立時間下限，原憑證撤銷後回 401。SQLite 測試表補上與 PostgreSQL Migration 相符的建立時間欄位。
- 隔離 PostgreSQL／MinIO／Redis 套用 `alembic upgrade head`，執行 `python -m pytest -q tests`，結果 **61 passed、19 個棄用警告**。容器已清理。瀏覽器 E2E 與本輪遠端 CI 尚待驗；歷史瀏覽器登出 500 缺少原始例外，仍持續追蹤。提交識別見 Git 紀錄。

## 2026-11-13 M2 PDF 上傳 API

- `POST /api/v1/documents` 先驗證工作階段、租戶及角色，再計量並解析 multipart，沿用 PDF 檔頭與摘要檢查、資料庫預約、MinIO 對帳及工作登錄。完成交易重驗並鎖住建立者 ACL，MinIO 傳輸設短逾時並停用自動重試。202 回傳文件及版本識別，版本保留未發布。
- 隔離 tmpfs PostgreSQL／MinIO 執行 `alembic upgrade head` 到 `0009_document_index_jobs`，再執行 `python -m pytest -q tests`，結果 **59 passed、1 failed、1 skipped**。上傳契約、HTTP 上傳／重試／ACL 撤銷與儲存對帳均通過；登出回歸在 `ck_sessions_revoked_after_creation` 失敗，Redis 整合未啟用。容器已清理。 `python -m pip_audit -r apps/api/requirements-dev.txt` 未發現已知漏洞。
- MinIO 測試使用隔離服務的合成管理憑證；實際受限帳號與 Bucket 政策、並行請求及瀏覽器驗收仍待驗。遠端起始 `808dd5d` 的建置與機密掃描成功，本次變更的遠端 CI 待驗。提交識別見 Git 紀錄。

## 2026-11-13 M2 上傳交易模組可維護性

- 依新版 `AGENTS.md` 的註解規範，針對目前開發的 `document_uploads.py` 補明 PostgreSQL／MinIO 無共同交易、預約與完成函式的前置條件、副作用、冪等重試及失敗語意。抽出共用的 PDF 完整性檢查與 User／Tenant／Membership 鎖定，避免兩條流程的授權規則日後分歧；未變更資料表或對外 API。
- 一次性 tmpfs PostgreSQL／MinIO 從空白 Migration 後重跑上傳預約及完成整合測試 **2 passed**；容器與網路已清理。此項沒有補齊全部既有程式註解，範圍限正在修改的高風險模組。
- 本項在 `93f327d` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 索引工作持久登錄

- `0009_document_index_jobs` 為每個文件版本建立租戶隔離、唯一的索引工作紀錄。`complete_document_upload` 在已核對 MinIO 內容後，同筆 PostgreSQL 交易更新 `storage_status = stored` 並新增 `pending` 工作；同鍵重試使用唯一約束避免重複，寫入前失敗不登錄工作。
- 一次性 tmpfs PostgreSQL／MinIO 從空白套用 Alembic 至 `0009_document_index_jobs`，執行上傳完成、預約與狀態整合測試 **3 passed、1 個既有棄用警告**；容器和網路已清理。同步 Schema 與 RAG 索引分離 ADR。Redis／Celery Worker、索引重試與 `ready` 發布仍未實作，不能宣稱索引或 RAG-T01 驗收通過。
- 本項在 `bf93829` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 私有文件儲存連線設定

- 新增可選的 MinIO Endpoint、受限應用憑證、Bucket 與 TLS 設定。API 只在設定齊全時建立 Client；明文連線僅允許 Compose 內部 `minio` 或本機位址。`docker-compose.yml` 將文件儲存設定傳給 API，但不重用 MinIO Root 憑證；`.env.example` 留空應用憑證並註明須另外建立僅限私有 `documents` Bucket 的權限。
- 合成設定單元測試驗證缺少憑證拒絕、外部明文端點拒絕及內部端點接受，結果 **3 passed**；`docker compose config --quiet` 通過。尚未建立或檢查實際 Bucket 與應用憑證，也未對外開放上傳 API；目前缺少設定時功能維持關閉。
- 本項在 `972ee0f` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。歷史登出 500 無新證據，未增加重現策略。

## 2026-11-13 M2 文件狀態查詢

- 與遠端 `main` 分岔時安全合併 `bd5dad9` 的 `AGENTS.md` 程式碼註解規範，中文 Merge Commit 為 `bd11be2`；本機既有兩筆 Commit 與未提交端點改動均保留，未改寫歷史。依新版規範，正在修改的文件查詢模組補上 Tenant／ACL、游標及狀態回應的設計說明。
- 新增 `GET /api/v1/documents/{document_id}/status`，以同一筆 SQL 查詢重驗目前成員、角色與 ACL 並讀取最新版本，避免沿用舊 Tenant Context 洩漏狀態；回傳已選版本號與最新版本的儲存／索引狀態。單筆、列表與狀態共用相同授權 SQL 條件，防止日後規則分歧。沒有版本時回 `null`，不回傳原文或物件鍵。同步 OpenAPI Contract Test、PostgreSQL 整合測試與 API 契約文件。隔離 PostgreSQL 的狀態、撤權、單筆／列表與契約測試 **4 passed、1 個既有棄用警告**；容器已清理。提交 SHA 見本輪 Git 紀錄；未 Push。
- 此端點只提供狀態查詢；上傳 API、索引排程與端對端文件流程仍未完成。歷史登出 500 無新證據，維持未重現／保留追蹤。

## 2026-11-13 M2 上傳物件寫入與狀態對帳

- 新增內部 `complete_document_upload`：再次確認 User／Tenant／Membership 與 `document.upload` 權限，鎖定指定版本，在持有版本鎖期間核對 MinIO 物件；找不到才寫入，寫入回應不明時再讀回比對大小與 SHA256，確認後才將 `storage_status` 改為 `stored`。已標記儲存完成卻缺少物件時明確報錯，不誤報成功。
- 以一次性 tmpfs PostgreSQL 與 MinIO 實測正常寫入、重試、寫入後回應遺失、寫入前失敗、角色降權及物件遺失；加上預約與角色政策回歸共 **8 passed**。合成資料位於隔離環境，容器及網路已清理，未使用 `down -v`。
- 尚未提供 API、Bucket 正式設定、文件解析／索引任務或孤兒物件定期清理。外部儲存 I/O 期間持有資料庫鎖，需在 API 整合時設定短逾時與受控重試；資料庫提交結果不明時可透過相同冪等鍵再次核對。此項不代表完整文件上傳驗收。
- 本項在 `7a9c333` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 文件上傳預約交易

- 新增內部服務 `reserve_document_upload`，在 PostgreSQL 交易中重驗 User／Tenant／Membership 狀態與 `document.upload` 角色權限，按租戶及冪等鍵取得交易鎖，再建立文件、版本及建立者專屬 ACL。相同建立者、標題與 SHA256 重試回傳原預約；衝突請求拒絕。`viewer` 無上傳權限。此項尚未寫入 MinIO 或開放 API。
- 在一次性 tmpfs PostgreSQL 從空白套用 Alembic 至 `0008_document_user_acl`，執行預約、上傳狀態、文件 ACL 讀取及角色政策測試：**10 passed、1 個既有棄用警告**。隔離容器以 `docker compose down` 清理，沒有刪除 Volume。未執行並行請求壓力測試；資料庫唯一約束仍是並行重複鍵的最後防線。
- 上傳前準備資料重新核對大小、檔頭與 SHA256；未完成 MinIO 寫入、補償與索引排程之前，不應將預約視為已完成上傳，也不應暴露端點。歷史登出 500 無新證據，維持未重現／保留追蹤。
- 起始本機與 `origin/main` 同為 `bdc7f80`，工作目錄乾淨；官方額度開始時 5 小時剩餘 52%、每週剩餘 93%。本項未 Push；提交 SHA 以 Git 紀錄為準。
## 2026-11-13 重新整理後恢復登入

- 影響為已登入使用者重新整理後失去工作區狀態，需重新輸入帳密。修正前以隔離 Playwright 重現，登入與選擇租戶成功，重新整理後找不到工作區。原因是 React 記憶體中的 JWT 與狀態被清空，啟動時也未向後端驗證。退出條件為 Chromium 可恢復工作區與目前租戶，過期或登出後回到登入畫面，且通過既有授權回歸。
- `auth.py` 新增瀏覽器登入端點，將原 15 分鐘 JWT 放入 HttpOnly、Secure、SameSite=Strict Cookie，沿用資料庫驗證與撤銷。前端在 `api.ts`、`main.tsx` 依 `/auth/me` 恢復身分，從 `tenants.py`、`role_policy.py` 取得重驗的租戶與角色權限。分頁僅保存租戶選擇，API 持續檢查目前成員資格及資源授權。
- `python scripts/testing/run_m1_e2e.py` 修正前 3 通過、2 失敗，修正後 **5 通過**。涵蓋登入、重新整理後身分與租戶、登出後無法恢復、跨租戶拒絕，以及模擬 503 可重試和 401 回到登入。一次性 PostgreSQL、Redis、MinIO 套用至 `0009_document_index_jobs`，`pytest -q -p no:cacheprovider` **53 通過、17 則相依套件棄用警告**，直接驗證資料庫工作階段到期、Cookie 登出撤銷及角色降權後的即時權限。`npm run build` 通過。
- 正式部署依 [ADR 0006](../adr/0006-browser-session-cookie.md) 使用同來源 HTTPS。本輪瀏覽器以本機 loopback 驗證，正式 HTTPS 代理尚未驗證。期限仍為 15 分鐘，過期需登入。歷史登出 500 依既有紀錄追蹤。提交 SHA 以本輪 Git 紀錄為準，下一項依本檔 M2 工作清單。
- 驗證缺失：提交 `2f81a51` 的 Chromium 測試只涵蓋新建的隔離環境，未從使用者實際操作的 `http://127.0.0.1:5173/` 驗證登入與重新整理。使用者回報 F5 仍登出後，確認該入口仍提供舊前端，且後端未提供 `/auth/session`。重建本機 Web／API 後，已從該網址確認新版前端與登入端點可達，實際登入後重新整理仍待在該入口驗證。後續前端變更須依 `AGENTS.md` 在使用者實際入口以瀏覽器驗證受影響流程，並回報測試環境與未驗項目。

## 2026-11-13 M2 單一使用者文件授權

- `0008_document_user_acl` 新增 `(tenant_id, document_id, user_id)` 授權表，複合外鍵同時約束文件與租戶成員資格；撤銷成員資格會連動刪除授權。文件單筆與列表查詢允許符合角色 ACL 或指定使用者 ACL 的目前成員，避免未來上傳時因建立者角色而自動讓所有同角色成員讀取。
- 一次性 tmpfs PostgreSQL 從空白套用 Alembic 至 `0008_document_user_acl` 成功；文件相關整合測試 **4 passed、1 個既有棄用警告**，驗證同租戶同角色的另一位使用者無法單筆讀取或在列表看見私有文件，且撤銷成員資格後授權列連動移除。容器已清理；此項尚未提供 ACL 管理 API 或對外上傳。
- 本項在 `8b3aed3` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 PDF 交易前準備

- 新增 `prepare_pdf`：在建立資料庫上傳紀錄前限制 PDF 大小、檢查檔頭並計算 SHA256；`store_prepared_pdf` 使用預留物件鍵寫入，且重新核對準備資料的大小、檔頭與摘要。原本的 `store_pdf` 保持可用，改由這兩步組成。
- 一次性 tmpfs MinIO 整合測試涵蓋準備、儲存、偽造摘要拒絕與既有介面，結果 **1 passed**；容器與隔離網路已清理。資料庫上傳交易、冪等重試與對外 API 尚未實作；PDF 檔頭檢查並非惡意檔掃描。
- 本項在 `4c6fabb` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 MinIO 寫入結果對帳

- 新增 `verify_stored_pdf`：先核對租戶／文件／版本物件鍵，再從 MinIO 讀回，依預期大小與 SHA256 確認內容；找不到物件回傳 `False`，內容不符或其他儲存錯誤則拒絕或向上傳遞，所有回應連線均關閉。最多讀取允許的 PDF 大小再加 1 byte，避免對帳時無界讀取。
- 一次性 tmpfs MinIO 整合測試涵蓋成功、缺失、摘要不符、跨版本鍵與既有格式／大小限制，結果 **1 passed**；容器與隔離網路已清理。這只是後續上傳交易的對帳元件，尚未接入資料庫狀態更新或對外 API，也不能解決同鍵並行覆寫競態。
- 本項在 `b419db3` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 預留原始文件物件鍵

- `reserve_pdf_key` 可在建立資料庫上傳紀錄前產生伺服器控制的租戶／文件／版本物件鍵；`store_pdf` 可使用該鍵寫入 MinIO，並拒絕與版本不符、空白或不符合 UUID 格式的鍵。既有未提供預留鍵的呼叫方式仍可用。
- 一次性 tmpfs MinIO 的 PDF 寫入、讀回、大小／格式拒絕及預留鍵驗證整合測試 **1 passed**；測試容器與隔離網路已清理。此元件尚不處理同鍵重試時的物件對帳或覆寫競態；後續上傳流程須先查詢 MinIO 狀態並決定補償策略，且不可把預留鍵作為對外輸入。
- 本項在 `2f8d00b` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 文件上傳狀態前置工作

- 新增 `0007_document_upload_state`：文件版本預設 `pending_upload`，可轉為 `stored` 或 `failed`；可選 UUID 冪等鍵在同租戶內唯一。既有版本保守地標為 `pending_upload`，不得推定 MinIO 物件已存在。此項只建立資料庫約束，尚無對外上傳 API 或自動補償流程。
- 在一次性 tmpfs PostgreSQL 從空白套用 Alembic 至 `0007_document_upload_state` 成功；安裝隔離容器的測試相依套件後，執行上傳狀態、既有文件跨租戶約束及 ACL 讀取整合測試，結果 **4 passed、1 個既有棄用警告**。第一次測試容器缺少 `pytest` 而未能執行，已修正測試環境；容器用 `docker compose down` 清理，沒有刪除 Volume。
- 後續上傳流程須明確預留物件鍵，對 MinIO 不確定結果先查詢物件，再更新儲存狀態；冪等鍵重用時需核對請求內容，不能僅依唯一約束回傳成功。發布版本仍須驗證儲存與索引就緒，目前資料庫尚未強制此條件。本輪未新增登出 500 重現策略，狀態仍為未重現／保留追蹤。
- 本項在本機 `main` 的 `a836ce6` 後進行，未 Push；提交 SHA 以 Git 紀錄為準。

## 2026-11-13 M2 文件列表與有界歷史問題處置

- 起始本機與 GitHub `main` 同為 `7ef7248`，工作目錄乾淨。該版本的 Python、dotnet、frontend、compose、e2e 與 Gitleaks CI 均成功；官方額度開始時 5 小時剩餘 85%、每週剩餘 98%。
- Playwright MCP 已在現有前端驗證合成錯誤帳密的登入請求回 401、頁面顯示預期錯誤且未進入工作空間；在以目前原始碼建置的獨立 tmpfs Compose 環境，未登入讀取 `/api/v1/documents/{id}` 回 401。該隔離環境已用 `docker compose down` 清理，沒有使用 `down -v`。尚無文件上傳 UI，未執行 M2 已登入的瀏覽器流程；API 授權由 PostgreSQL 整合測試驗證。
- 歷史登出 500 狀態為 **Unreproduced / Tracked（未重現／持續追蹤）**。本輪未增加登出重現策略；既有重現結果、可能的 Session／交易影響與重新列為 Blocker 條件見[獨立追蹤紀錄](issues/LOGOUT-500.md)。目前沒有新 CI 錯誤或可重現證據，不重啟調查，也不宣稱已修復。
- 文件列表 `GET /api/v1/documents` 以目前租戶成員資格、文件 ACL 及未刪除狀態篩選，依 UUID 遞增分頁，每頁最多 50 筆。新 OpenAPI 契約測試先因缺少端點而失敗；實作後在新建 tmpfs PostgreSQL 從空白套用 Alembic 至 `0006_documents`，執行列表、單筆讀取及身分驗證測試 **9 passed、8 warnings**。跨租戶與無 ACL 的資料不會出現在項目或游標中。此項提交 SHA 以本輪 Git 紀錄為準，未 Push。

## 2026-11-13 M2 MinIO 原始文件儲存元件

- 依 [MinIO Python SDK 官方 API](https://github.com/minio/minio-py/blob/master/docs/API.md) 的 `put_object` 介面，新增固定版本 `minio==7.2.20`。`object_storage.store_pdf` 只接受最多 10 MiB、具 `%PDF-` 檔頭的輸入；使用伺服器產生的 UUID 物件鍵，固定 `application/pdf`，回傳 SHA256 與大小，不使用使用者檔名。此檔頭檢查不等同安全掃描或完整 PDF 驗證。
- 在獨立 tmpfs MinIO 容器執行寫入、讀回、格式與大小拒絕、刪除的整合測試，結果 **1 passed**，容器已清理。`pip-audit -r requirements-dev.txt --progress-spinner off` 回報 **No known vulnerabilities found**。目前儲存元件沒有對外 API；私有 Bucket 建立、租戶授權、資料庫交易、上傳失敗補償、惡意檔掃描與解析沙箱仍待後續工作。MinIO 伺服器映像來源的信任評估仍未完成。
- 本輪開始時官方 5 小時與每週額度均剩餘 100%；文件讀取 API 已提交 `d9e51f3`，未 Push。此項提交 SHA 以本輪 Git 紀錄為準。

## 2026-11-13 M2 文件讀取 API

- 起始本機 `main` 乾淨，領先遠端三筆；GitHub `main` 仍為 `66aabc9`，未 Push。官方額度開始時 5 小時與每週視窗均剩餘 100%。
- 新增僅回傳中繼資料的 `GET /api/v1/documents/{document_id}`。JWT 與 `X-Tenant-ID` 必填；`get_tenant_context` 重驗有效成員資格，SQL 再以租戶、文件、目前角色的 ACL 及未刪除狀態篩選。無權限與不存在均回 404，不回傳原始文件或索引內容。
- 更新 API 契約與 OpenAPI 契約測試，新增 PostgreSQL 整合測試。先執行新契約測試，因端點尚未實作而如預期失敗；實作後在新建 tmpfs PostgreSQL 從空白套用 Alembic 至 `0006_documents`，執行文件 API、文件跨租戶約束、身分驗證 PostgreSQL 與 SQLite 測試，結果 **11 passed、8 warnings**。測試容器已清理。
- 文件上傳、版本發布、MinIO 寫入、解析、索引、檢索與問答仍未實作。資料庫目前不能保證已選版本處於 `ready`，也尚未限制 Owner 必須是同租戶成員；對外只開放 ACL 保護的 Metadata 讀取。

## 2026-11-13 M1 驗收決策與 M2 工作清單

- M1 判定：**Accepted with Known Issues（有條件驗收通過）**。GitHub `main` 與本機起始 `HEAD` 同為 `66aabc9488ab8f5fe296c8e20d913f7415ca6180`，工作目錄起始乾淨。[最新 M1 CI](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43320328553)五項 Job 與[最新 Gitleaks](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43320328556)成功。本機最後一次新隔離環境 E2E 為 4 passed；新增再次登出測試的 SQLite 案例為 7 passed。沒有目前可重現的 M1 Blocker；歷史登出 500 根因未確認，見[待追蹤紀錄](issues/LOGOUT-500.md)。新增的 PostgreSQL 斷言待下次 CI 驗證。本輪未執行 Push。
- M2 工作清單（依相依順序拆為可驗收小項）：
  1. 文件上傳與版本管理：Metadata、ACL、版本 Schema 與交易不變條件；再實作 API 與 Contract Test。
  2. MinIO 原始文件儲存：受控物件鍵、檔案大小／類型限制、清理與失敗補償。
  3. 文件解析與 Chunking（區塊切分）：不可信文件隔離解析、頁碼及可追溯區塊。
  4. Embedding（向量嵌入）：模型與版本紀錄、批次處理、失敗重試界線。
  5. Qdrant 索引：帶租戶與 ACL 資訊的可重建索引、Ready 後發布版本。
  6. Tenant／ACL 權限篩選：檢索前篩選與回應前 PostgreSQL 重驗。
  7. Hybrid Retrieval（混合檢索）：Dense／Sparse 融合與排序測試。
  8. Citation（來源引用）：文件版本、區塊、頁碼與原文驗證。
  9. RAG Evaluation（檢索評估）：固定合成／公開資料集、Recall@5、引用正確率及拒答率。
- M2 首項實作：`apps/api/migrations/versions/0006_documents.py` 建立文件、版本、ACL 與同租戶複合外鍵；`apps/api/tests/test_documents_postgres.py` 驗證跨租戶版本／ACL 拒絕及 `current_version` 必須指向現有版本。隔離 tmpfs PostgreSQL 從空白套用 Alembic 至 head，並執行文件及登出整合測試共 **3 passed、1 warning**；容器已清理。`ready` 後發布、Owner 同租戶成員資格、SHA256 去重、上傳、MinIO、解析、索引及問答仍為規劃中，禁止提前開放對外 API。此項提交 SHA 以本輪 Git 紀錄為準。
- 本輪結束時官方額度工具回報 5 小時視窗已用 85%（剩餘 **15%**）、每週已用 43%（剩餘 57%）。已達 ≤15% 停止門檻，不再啟動新工作；待額度恢復後再繼續 M2。未使用額度重設點數。

## 2026-11-13 自動續作

- M1-05 第六項：新增獨立 tmpfs PostgreSQL／Redis 的 `docker-compose.e2e.yml`、執行時產生合成帳密的跨平台執行器、Playwright Test 四項案例與 GitHub Actions `e2e` Job。驗證未登入、錯誤密碼、登入後租戶切換與登出、跨租戶 404 及撤銷 Session 後 401。功能提交 `83f57a1`（`test: 加入隔離的 Playwright 登入與租戶驗收`）；詳細流程見 [E2E 驗收紀錄](M1-E2E-VERIFICATION.md)。
- 本機驗證：Headless Chromium 完整測試最後兩次均為 4 passed；`npm run build --prefix apps/web`、提交前安全測試 6 passed、`npm audit --prefix apps/web --audit-level=high` 0 個已知漏洞；E2E 測試容器已清理。首次 seed 因模組路徑缺失失敗，補上隔離容器 `PYTHONPATH` 後解決。另一次 E2E 的跨租戶案例登出請求回 500，後續未重現；保留為未解風險，失敗時執行器僅回報 API 例外類型，不輸出憑證。`git diff --cached --check` 與 Gitleaks 9 個檔案暫存掃描、Hook 再掃描均通過。
- 待推送範圍：檢查時本機 `main` 相對 `origin/main` 超前 1 筆，即 `83f57a1`，Staged Diff 為空。Gitleaks 對 `origin/main..HEAD` 掃描 1 筆 Commit、約 15.76 KB，未發現機密。遠端追蹤分支已在本輪期間更新，推送前須再核對；未執行 Push。官方額度：此項提交後 5 小時剩餘 58%、每週剩餘 64%。
- M1 驗收尚未完成：遠端 Python、C#、React、Compose、Secret Scan、Playwright Job 未就本次 E2E Commit 取得結果；乾淨資料庫初始化案例在既有資料庫跳過，隔離 E2E 已驗證 Alembic 建立新資料庫。間歇性登出 500 須持續追查，不得視為已修復。
- 遠端唯讀核對：`origin/main` 的 `58213d1` 已有 [M1 建置工作](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43316334610)與[機密掃描工作](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43316334596)成功結果；前者的 Python、dotnet、frontend、compose 四個 Job 均成功，後者的 Gitleaks Job 成功。這些結果不包含本輪新增的 E2E Job 與本機待推送 Commit。
- 間歇性登出 500 追查：執行器新增可轉交 Playwright 參數，提交 `79799b7`（`test: 支援隔離環境重複執行 Playwright 案例`）；以 `--grep=API --repeat-each=4` 在隔離資料庫重跑跨租戶與登出案例，4 passed，未再出現 500。`git diff --cached --check` 與 Gitleaks 暫存區 2 個檔案掃描、Hook 再掃描通過。原因尚未確定，不宣稱已修復；提交後官方額度為 5 小時剩餘 45%、每週剩餘 62%。
- 追加追查：在六個新建的隔離環境重跑完整 Playwright E2E，各為 4 passed；測試容器均已清理。檢視 Session CHECK、JWT 驗證、登出更新與 Tenant Context，未找到可確認的一次性 500 根因；原失敗容器已清理，沒有該次 API Traceback 可供還原。未以重試或放寬驗證掩蓋問題。官方額度檢查為 5 小時剩餘 38%、每週剩餘 61%。
- 遠端追蹤分支在本輪期間由外部更新至 `6af29ac`，本代理未執行 Push。[M1 CI](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43319565777)的 Python、dotnet、frontend、compose、e2e 均成功，E2E Log 為 4 passed；[Gitleaks](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43319565690)成功。遠端亦未重現 500，但不能據此宣稱缺陷已修復。

- 本輪重新查詢官方額度：開始時 5 小時剩餘 98%、每週剩餘 70%；Git 工作區乾淨。瀏覽器控制工具僅回報空的 MCP Apps 分頁及原生 app-server 啟動失敗，Chrome DevTools 也找不到瀏覽器，因此 M1-04 互動驗收尚未執行。
- M1-05 第三項：受保護 API 於 OpenAPI 宣告 HTTP Bearer Security Scheme，並以 Contract Test 檢查登入端點公開、受保護端點需 Bearer；另驗證錯誤格式的憑證仍回 401。同步 API 契約文件。提交 `46a62bd`（`test: 補齊 Bearer 驗證的 OpenAPI 契約`）。
- 驗證：重建 API 映像，使用 Compose PostgreSQL／Redis 與兩種整合測試旗標執行 `python -m pytest -p no:cacheprovider -q`，39 passed、1 skipped（既有資料庫不適用空白初始化案例）、6 個既有棄用警告。`git diff --cached --check` 通過；Gitleaks 掃描 3 個暫存檔未發現機密，Hook 提交前再掃描通過。未新增依賴。提交後官方額度為 5 小時剩餘 90%、每週剩餘 69%。
- 下一項：M1-05 依賴安全稽核與本機 Compose 完整驗收；遠端 CI 須 Push 後才能執行，但本循環禁止自動 Push。
- M1-05 第四項：新增 `apps/web/package-lock.json`，Docker 與 GitHub Actions 前端建置改用 `npm ci`；CI 加入 `npm audit --audit-level=high`。提交 `0fce7fd`（`ci: 鎖定前端相依版本並執行漏洞稽核`）。
- 驗證：本機 `npm audit --prefix apps/web --audit-level=high` 回報 0 個漏洞；`docker compose build web` 中 `npm ci`、TypeScript、Vite 均成功；`docker compose config --quiet` 通過。`git diff --cached --check` 與 Gitleaks 暫存區 3 個檔案掃描均通過，提交 Hook 再掃描通過。嘗試 Python `pip_audit` 時本機尚未安裝該工具，待下項補做；新增的前端間接依賴已納入 npm audit。提交後官方額度為 5 小時剩餘 85%、每週剩餘 68%。
- 下一項：執行 Python 依賴稽核、Compose Migration 與完整回歸；M1-04 瀏覽器互動及遠端 GitHub Actions 仍待可用工具或人工 Push。
- M1-05 第五項：在暫時性 API 容器安裝 `pip-audit` 並解析 `requirements-dev.txt`，結果 `No known vulnerabilities found`。重跑本機 Alembic Migration 成功；`docker compose build demo-erp` 成功，`docker compose up -d` 啟動完整服務且 API、Demo ERP、資料庫與 Redis 健康。本機 Web 首頁 200、經 Web 代理的未登入 `/api/v1/auth/me` 401、API `/health/ready` 200。
- 安全回歸：第一次執行提交前安全測試因目前終端 PATH 缺少 Gitleaks 而失敗；以已安裝的 Gitleaks 路徑重新執行 `python -m unittest discover -s tests/security -p test_*.py -v`，6 項通過。此為環境設定問題，未修改或放寬測試。API 全套 PostgreSQL／Redis 回歸在第三項工作已執行，39 passed、1 skipped；遠端 GitHub Actions 仍未執行。此次僅更新驗收紀錄，未改動依賴或業務程式。
- 剩餘：M1-04 實際瀏覽器登入／租戶選擇互動，乾淨資料庫首次初始化、遠端 CI。不得為驗證乾淨資料庫刪除現有 Docker Volume；本機現有資料庫的空白初始化案例維持跳過。
- **本輪停止條件：**官方額度為 5 小時剩餘 76%、每週剩餘 66%，未達 15% 門檻；但 M1-05 遠端 GitHub Actions 驗收需要外部 Push，屬自主循環禁止操作。瀏覽器控制目前無可用分頁，M1-04 成功登入與租戶切換尚未通過視覺互動驗收。停止建立新任務，M1 不標示完成，也不進入 M2。下一輪在使用者自行 Push 並提供 CI 結果、且瀏覽器工具可用後，先完成這兩項驗收；再核對 M1 完成條件。

- 官方 Codex 額度恢復後續作：開始時 5 小時剩餘 100%、每週剩餘 84%；工作區 Git 狀態乾淨。一次性 Thread Automation `m1` 已在喚醒後刪除，避免重複執行。
- 第十二項工作：新增 `apps/api/src/create_tenant.py` 及 PostgreSQL 整合測試；資料庫操作員可指定既有啟用 User 作為新租戶首位 admin，租戶與 Membership 在同筆交易寫入。同步 API 契約及啟動文件。未提供租戶 admin 可呼叫的全域建立租戶 API，避免任意擴張租戶。
- 測試：Docker API 映像建置成功；在既有 PostgreSQL、Redis Compose 服務以合成資料執行 `python -m pytest -p no:cacheprovider -q`，結果 28 passed、1 skipped（空白資料庫初始化案例，因現有資料庫已初始化）、6 個既有棄用警告。新租戶案例以外層交易回滾，未建立真實租戶。
- Code Review 與安全：檢查啟用 User 狀態、交易原子性、明確操作員確認及停權帳號拒絕；`.gitignore` 與本機 Hook 已核對。`git diff --cached --check` 通過，Gitleaks 8.30.1 掃描 4 個暫存檔未發現機密；未新增依賴。測試容器第一次未安裝 pytest、第二次因 Windows Shell 引號錯誤未執行，改用互動式容器安裝開發依賴後完成測試。
- 功能提交：`1ccbce5`（`feat: 新增受控租戶建立指令`）。提交後官方額度為 5 小時剩餘 93%、每週剩餘 83%，未觸發停止條件。
- 尚未完成：M1-02 完整驗收、M1-03 授權與隔離、M1-04 前端、M1-05 整合驗收。下一項先驗證新租戶建立後的可見性與跨租戶拒絕。
- 第十三項工作：新增新租戶建立後的 API 整合案例。首位 admin 可登入並查詢新租戶；無成員資格的另一位 User 查詢該租戶回 404，租戶列表為空。合成資料由外層交易回滾。提交 `1a24907`（`test: 驗證新租戶只對管理員可見`）。
- 回歸測試：重建 API 映像後在 Compose PostgreSQL、Redis 上執行完整 API 測試，29 passed、1 skipped、6 個既有棄用警告。`git diff --cached --check` 與 Gitleaks 掃描 1 個暫存檔均通過；未新增依賴。提交後官方額度為 5 小時剩餘 89%、每週剩餘 83%，可繼續 M1-02 完整驗收。
- M1-02 本機功能審查：JWT 宣告不含可自行宣稱的 Role／Tenant，受保護端點重新查詢 User、Session 與 Membership；停權及成員撤銷均已測試。新租戶建立僅限資料庫操作員的受控指令。完整 M1 Contract／CI／乾淨資料庫驗收仍列於 M1-05，不宣稱已完成。
- M1-03 首項：新增 `TenantContext` 相依性與 `GET /api/v1/tenants/current`，每次依 JWT 身分及 `X-Tenant-ID` 查詢啟用租戶的 Membership；跨租戶及停用租戶均回 404。同步 OpenAPI 路徑測試及 API 契約。提交 `7fe6f80`（`feat: 建立可信租戶上下文查詢`）。
- 測試與安全：Docker API 映像重建、Compose PostgreSQL／Redis 完整 API 測試 29 passed、1 skipped、6 個既有棄用警告；`git diff --cached --check` 通過，Gitleaks 掃描 5 個暫存檔未發現機密；未新增依賴。提交後官方額度為 5 小時剩餘 85%、每週剩餘 82%，可繼續 Role Policy。
- M1-03 第二項：建立 `Role Policy` 與可重用的 `require_permission` 相依性，會員管理端點也改採同一政策。角色矩陣依安全規格實作，未知角色及未知權限一律拒絕。ACL、倉庫範圍與職責分離尚須另行檢查。提交 `c7b8a86`（`feat: 新增可重用角色授權政策`）。
- 驗證：API 映像重建與 Compose PostgreSQL／Redis 完整測試 35 passed、1 skipped、6 個既有棄用警告；暫存差異檢查通過，Gitleaks 掃描 4 個檔案未發現機密。無新增依賴。提交後官方額度為 5 小時剩餘 80%、每週剩餘 81%；下一項為倉庫資料範圍的 Schema 與授權檢查。
- M1-03 第三項：Alembic `0004_warehouse_scopes` 建立以複合外鍵綁定 Membership 的倉庫範圍表；無明確資料列即無倉庫權限，撤銷 Membership 時連動刪除。同步 Schema 文件及 PostgreSQL 跨租戶外鍵測試。提交 `4a7cddc`（`feat: 建立成員倉庫授權範圍結構`）。
- 資料庫驗證：`docker compose build agent-migrate`、`docker compose run --rm agent-migrate` 首次及重跑均成功；API 映像重建後完整測試 36 passed、1 skipped、6 個既有棄用警告，合成資料回滾。`git diff --cached --check` 通過，Gitleaks 掃描 3 個檔案未發現機密；未新增依賴。未執行 downgrade 以免破壞現有開發資料庫。
- 風險與下一項：ERP 位於獨立資料庫，無法對倉庫代碼做跨資料庫外鍵；授權寫入與 ERP 讀取前仍須檢查倉庫存在及租戶歸屬。提交後官方額度為 5 小時剩餘 74%、每週剩餘 80%。下一項為 Warehouse Scope 查詢與授權相依性。
- M1-03 第四項：新增 `/tenants/current/warehouse-scopes` 分頁列表與單筆代碼檢查，先經 Tenant Context 與 `inventory.read` 角色政策，再以 `(tenant_id,user_id,warehouse_code)` 查詢明確授權；跨租戶及未授權代碼回 404。提交 `45cfccc`（`feat: 新增租戶倉庫範圍查詢與檢查`）。
- 測試：首次完整 API 測試發現 PostgreSQL 無法推斷空 `cursor` 參數型別；改由程式在提供 cursor 時才加入參數化條件後，重建映像與重跑完整測試為 37 passed、1 skipped、6 個既有棄用警告。`git diff --cached --check` 通過，Gitleaks 掃描 5 個檔案未發現機密；未新增依賴。
- 目前限制：倉庫授權寫入尚未提供受控操作，ERP 倉庫存在與租戶歸屬尚未驗證，現階段僅可查詢已記錄的代碼；不得視為 ERP Read API 的完整授權。提交後官方額度為 5 小時剩餘 66%、每週剩餘 79%。
- M1-03 第五項：新增 `0005_tenant_warehouses` Migration，以全域唯一倉庫代碼登錄租戶，並以複合外鍵限制 Membership 倉庫 Scope 只能指向同租戶倉庫。PostgreSQL 測試涵蓋無 Membership 與錯租戶代碼拒絕。提交 `a075fc9`（`feat: 約束倉庫代碼的租戶歸屬`）。
- 驗證：Migration 套用與重跑成功；API 映像重建後完整測試 37 passed、1 skipped、6 個既有棄用警告；`git diff --cached --check` 通過，Gitleaks 掃描 3 個暫存檔未發現機密。未新增依賴，未執行破壞性 downgrade。
- 風險與下一項：若既有環境已有未登錄的 Scope 資料列，此 Migration 會安全失敗，須由操作員先核實歸屬；目前本機套用成功。仍需受控登錄倉庫與分配 Scope 的流程，且 ERP 實際倉庫歸屬需在後續整合驗證。提交後官方額度為 5 小時剩餘 60%、每週剩餘 78%。
- M1-03 第六項：新增資料庫操作員互動式倉庫登錄指令，要求先在 ERP 核實代碼與租戶歸屬，再明確確認。停用租戶、無效代碼及跨租戶重複代碼均拒絕；沒有讓一般租戶 admin 自行認領任意倉庫。提交 `f8da34c`（`feat: 新增受控倉庫代碼登錄指令`）。
- 測試：Docker API 映像重建後完整測試 38 passed、1 skipped、6 個既有棄用警告；合成登錄資料回滾。`git diff --cached --check` 通過，Gitleaks 掃描 3 個檔案未發現機密，無新增依賴。未對真實 ERP 倉庫執行登錄。提交後官方額度為 5 小時剩餘 55%、每週剩餘 77%。下一項為 admin 分配成員倉庫 Scope 的 API。
- M1-03 第七項：租戶 admin 可對本租戶現有成員 `PUT`／`DELETE` 已登錄的倉庫 Scope；不接受未登錄代碼、其他租戶或非 admin，重複授予安全，撤銷 Membership 時 Scope 連動清除。同步 API 契約與 OpenAPI 路徑測試。提交 `b945c0c`（`feat: 允許管理員分配已登錄倉庫範圍`）。
- 驗證：Docker API 映像重建後完整測試 38 passed、1 skipped、6 個既有棄用警告；`git diff --cached --check` 通過，Gitleaks 掃描 4 個暫存檔未發現機密，無新增依賴。提交後官方額度為 5 小時剩餘 48%、每週剩餘 76%。M1-03 的本機身分、角色、租戶與倉庫 Scope 基礎已實作；ERP 實際存取點複驗須於 M3 完成。
- M1-04 首項：React 提供登入、登出、租戶選擇、受保護功能概覽與 API 錯誤處理；JWT 僅存記憶體，不寫入 Local Storage。租戶列表依 Cursor 取完所有頁，選擇租戶時再次呼叫受保護的 `/tenants/current`。Nginx 對 `/api/` 使用同源固定代理。提交 `70050e6`（`feat: 建立登入與租戶選擇前端`）。
- 驗證：`docker compose build web` 的 TypeScript 與 Vite 建置通過；`docker compose config --quiet` 通過；`docker compose up -d web` 啟動成功，本機 HTTP 首頁回 200。前端代理 `/api/v1/auth/me` 回 503，原因是本機 Compose JWT 金鑰尚未設定為有效值，符合後端安全預期，未用真實憑證測試。瀏覽器工具找不到設定的 Chrome 可執行檔，UI 互動與視覺驗收未執行。`git diff --cached --check` 通過，Gitleaks 掃描 7 個檔案未發現機密；未新增依賴。
- 官方額度：提交後 5 小時剩餘 38%、每週剩餘 75%。下一項為 M1-05 Contract／安全／CI 整合驗收；前端登入成功路徑尚需瀏覽器驗證。
- M1-05 首項：統一 FastAPI 請求驗證錯誤為既定 `error` 格式，422 回 `VALIDATION_ERROR` 且不回傳輸入原文，並更新 API 契約與測試。提交 `9a3790f`（`feat: 統一請求驗證錯誤格式`）。
- 驗證：Docker API 映像重建後完整 PostgreSQL 測試 39 passed、1 skipped（Redis 整合案例尚未啟用）、6 個既有棄用警告；暫存差異與 Gitleaks 3 個檔案掃描通過，無新增依賴。提交後官方額度為 5 小時剩餘 30%、每週剩餘 74%。下一項為 CI 整合測試工作。
- M1-05 第二項：GitHub Actions 的 Python 工作新增 PostgreSQL、Redis 服務與 Alembic Migration，啟用兩種整合測試。提交 `4f03783`（`ci: 執行資料庫與 Redis 整合測試`）。本機以兩種整合旗標實際執行 40 passed、6 個既有棄用警告；暫存差異檢查與 Gitleaks 掃描 1 個檔案通過。遠端 GitHub Actions 尚未執行，不宣稱遠端 CI 通過。提交後官方額度為 5 小時剩餘 23%、每週剩餘 72%。
- **掃描判定修正：**全工作目錄 Gitleaks 曾在本機 `.env` 回報 2 筆 `generic-api-key` 特徵，在 `tests/security/__pycache__/test_pre_commit.cpython-312.pyc` 回報 1 筆 `aws-access-token` 特徵，因而暫停。重新核對後，兩檔均未被 Git 追蹤，暫存區為空，Git 歷史 126 筆 Commit 掃描未發現機密；目前沒有提交或外洩證據。這次將「被忽略的本機檔案命中」誤判為外洩停止條件，已更正。未讀取或記錄機密值；本機 `.env` 仍須維持忽略，不應提交。
- 額度與後續：重新查詢官方 Codex 額度先為 5 小時剩餘 16%、每週剩餘 71%；完成本次安全判定修正提交 `455264d` 後，5 小時剩餘 13%、每週剩餘 71%，已觸發 ≤15% 停止條件，不再啟動新任務。下一輪先查額度與 Git 狀態，再完成 M1-05 遠端 CI、瀏覽器互動驗收、依賴漏洞檢查及完整回歸。M1-04 的瀏覽器成功登入路徑仍未驗證；M1-05 未完成，不進入 M2。

## 2026-11-12 M1-02 自主開發循環

- 啟動核對：M1-01 的四筆提交依序為 `736e665`、`30d079b`、`e01f8a8`、`308b81a`，與本機驗證紀錄一致；既有進度檔已存在，本輪更新其交接狀態。
- 首項工作：新增 `apps/api/src/passwords.py` 與 `apps/api/tests/test_passwords.py`。使用 scrypt、每筆隨機鹽值、定長參數與常數時間比較；不接受異常雜湊參數。
- 測試：WSL `python3 -m pytest -p no:cacheprovider -q tests/test_passwords.py` 為 3 passed；Docker API 映像以合成資料庫連線設定執行全部 API 測試為 6 passed、1 個既有棄用警告。第一次 WSL 全套測試因環境未安裝 FastAPI 無法收集，已改於 Docker 完成回歸測試。
- 審查與機密掃描：暫存區僅含上述兩個新檔；`git diff --cached --check` 通過，Gitleaks 8.30.1 掃描 2 個暫存檔未發現機密；未新增依賴套件。
- 功能提交：`d0d8a910ffcc7482c1953778ae26abca2fd42ba1`。尚無登入、JWT 或 Session API，M1-02 未完成。
- Git 注意事項：啟動時 51 個既有追蹤檔呈現 CRLF 換行差異；`git diff --ignore-space-at-eol` 無內容差異。本輪僅暫存明確的新檔，不納入其餘換行差異。
- 額度：官方 Codex 使用量工具回報本輪首項完成後 5 小時剩餘 67%、每週剩餘 94%，尚未觸發 15% 停止門檻。
- 第二項工作：新增 `0002_sessions` Alembic Migration 並同步 Schema 文件，支援工作階段到期及撤銷時間欄位。提交 `744d4c5c875fe9777194f4408ef5b5b2ba8f795e`。
- 資料庫驗證：`docker compose build agent-migrate` 與 `docker compose run --rm agent-migrate` 成功；版本為 `0002_sessions`，重跑 Migration 成功。PostgreSQL 交易以合成使用者驗證有效 Session 可寫入、錯誤到期時間及錯誤撤銷時間被 CHECK 拒絕；交易均已回滾。
- 回歸與安全：Docker API 測試 6 passed、1 個既有棄用警告；`git diff --cached --check` 通過，Gitleaks 掃描 2 個暫存檔未發現機密；未新增依賴套件。Migration 未測試 downgrade，避免破壞現有開發資料庫。
- 官方額度：第二項完成後 5 小時剩餘 64%、每週剩餘 94%，未觸發停止條件。下一項為 JWT 驗證及登入流程。
- 第三項工作：新增固定 HS256 的短效 JWT 簽發及驗證元件；必要宣告包含 `sub`、`jti`、`iss`、`aud`、`iat`、`exp`，不信任 Token 自述的 Tenant 或 Role。提交 `6767d0a3fbd72d12d41360683cee71ef428e872c`。
- 測試與稽核：Docker API 測試 10 passed、1 個既有棄用警告；`pip-audit -r requirements-dev.txt` 未發現已知漏洞；`git diff --cached --check` 通過，Gitleaks 掃描 4 個暫存檔未發現機密。PyJWT 固定為 2.15.1。
- 官方額度：第三項完成後 5 小時剩餘 60%、每週剩餘 93%。下一項為將 JWT、Session 與使用者狀態接入登入 API。
- 第四項工作：新增 `/api/v1/auth/login`、`/me`、`/logout`，每次受保護請求查詢 User 與 Session 狀態，登出寫入撤銷時間；未設有效 JWT 金鑰時登入拒絕服務。同步 Compose、`.env.example`、API 契約及開發文件。提交 `7c85cfa2bcf8f06db37fe286b4f240c6c9cec8fe`。
- 測試：`docker compose config --quiet` 與 `docker compose build api` 成功；Docker Compose 連接實際 PostgreSQL 的完整 API 測試為 16 passed、6 個棄用警告。PostgreSQL 整合測試以外層交易回滾合成資料；OpenAPI 路徑契約測試通過。
- 安全審查：`git diff --cached --check` 通過，Gitleaks 掃描 10 個暫存檔未發現機密。登入尚無 Rate Limit（速率限制），目前 Compose API 僅綁本機 `127.0.0.1`；後續須在擴大暴露前補上限制。尚無受控建帳與租戶 API，M1-02 未完成。
- 官方額度：第四項完成後 5 小時剩餘 54%、每週剩餘 92%。下一項先補登入速率限制。
- 第五項工作：登入前以 Redis Lua Script 原子計數，限制來源 IP 每 60 秒 10 次、帳號每 300 秒 5 次；帳號以 HMAC 鍵識別，不儲存 Email 原文。Redis 失效時登入回 503。提交 `14616966181080857b265353a0cfa7f3cd9057bc`。
- 測試與安全：Compose API 與實際 PostgreSQL、Redis 的完整測試 21 passed、6 個棄用警告；Redis 整合案例驗證第 6 次遭拒及兩類 Key 的 TTL。`docker compose config --quiet` 通過；`pip-audit -r requirements-dev.txt` 未發現已知漏洞；`git diff --cached --check` 通過，Gitleaks 掃描 11 個暫存檔未發現機密。
- 官方額度：第五項完成後 5 小時剩餘 47%、每週剩餘 91%。下一項為受控建立使用者與租戶。
- 第六項工作：新增只限空白資料庫的互動式首次建帳指令，在單筆交易建立 User、Tenant 與 admin Membership；密碼由隱藏輸入讀取，已有資料時拒絕重做。提交 `9a730b56ea8e19cf042193bf005fb8e93eff97fb`。
- 測試與安全：實際 PostgreSQL 首次建帳、防重複及交易回滾案例在完整 API 測試中通過，總計 25 passed、6 個既有棄用警告；`git diff --cached --check` 通過，Gitleaks 掃描 5 個暫存檔未發現機密。未執行真實管理員建帳，避免佔用或污染本機開發資料庫。
- 官方額度：第六項完成後 5 小時剩餘 43%、每週剩餘 91%。下一項為租戶列表與成員資格查詢 API。
- 第七項工作：新增只列出目前使用者所屬啟用租戶的列表與單筆查詢 API，列表以 UUID Cursor 分頁；其他使用者的租戶與不存在租戶均回 404。提交 `8072e223739913e95b216386c5ac23146ccae8ef`。
- 測試與安全：實際 PostgreSQL 驗證跨租戶查詢、停用租戶隱藏與 Cursor；完整 API 測試 25 passed、6 個既有棄用警告。`git diff --cached --check` 通過，Gitleaks 掃描 6 個暫存檔未發現機密；未新增依賴。
- 官方額度：第七項完成後 5 小時剩餘 36%、每週剩餘 90%。下一項先補 Email 大小寫唯一約束，再建立受控使用者與 Membership 寫入。
- 第八項工作：新增 `0003_email_case_unique` Migration，以 PostgreSQL 唯一索引阻止 Email 大小寫變體重複，並同步 Schema。提交 `ac293487ec29e92684f9539391032b47703e5a35`。
- 驗證：套用前只讀檢查為 0 組大小寫重複；Migration 套用至 `0003_email_case_unique` 並成功重跑。PostgreSQL 整合測試確認重複 Email 被拒絕且合成資料回滾；完整 API 測試 26 passed、6 個既有棄用警告。`git diff --cached --check` 通過，Gitleaks 掃描 3 個暫存檔未發現機密。
- 官方額度：第八項完成後 5 小時剩餘 31%、每週剩餘 89%。下一項為受控 User 與 Membership 寫入 API。
- 第九項工作：新增租戶 admin 專用的成員建立 API，鎖定呼叫者 Membership，交易內建立新 User 與 manager／staff／viewer Membership；非 admin 回 403、跨租戶回 404、重複 Email 回 409，禁止建立新的 admin。提交 `9fe54638e36d382b857ea420983930094e8e9f71`。
- 測試與安全：實際 PostgreSQL 的 admin 建帳、角色限制、跨租戶與重複帳號案例通過；完整 API 測試 27 passed、6 個既有棄用警告。`git diff --cached --check` 通過，Gitleaks 掃描 7 個暫存檔未發現機密；未新增依賴。
- 官方額度：第九項完成後 5 小時剩餘 24%、每週剩餘 88%。M1-02 仍需成員角色與停權管理，尚未進入 M1-03。
- 第十項工作：租戶 admin 可變更 manager／staff／viewer 角色及撤銷這些成員的指定租戶 Membership；其他租戶回 404、非 admin 回 403，admin Membership 不可變更。提交 `8a3a75ac362b1d1125745e29287ed8111a75129b`。
- 測試與安全：實際 PostgreSQL 驗證角色變更、跨租戶拒絕、admin 保護及撤銷後租戶列表立即更新；完整 API 測試 27 passed、6 個既有棄用警告。`git diff --cached --check` 通過，Gitleaks 掃描 5 個暫存檔未發現機密；未新增套件或 Schema。
- 官方額度：第十項完成後 5 小時剩餘 19%、每週剩餘 87%。下一項為受控全域 User 停權與 Session 撤銷；完成後重新查詢額度。
- 第十一項工作：新增資料庫操作員的互動式全域 User 停權指令，在單筆交易停權 User 並撤銷其所有 Session；租戶 admin API 不具此權限。提交 `65fb1d3a0d252e2ced5008acf0d366157a0394cb`。
- 測試與安全：實際 PostgreSQL 驗證停權後既有 JWT 與新登入均回 401、重複停權可安全執行、所有 Session 已撤銷；合成資料已回滾。完整 API 測試 28 passed、6 個既有棄用警告。`git diff --cached --check` 通過，Gitleaks 掃描 4 個暫存檔未發現機密；未對真實帳號執行停權。
- **停止條件：**官方 Codex 額度工具在第十一項完成後回報 5 小時剩餘 12%、每週剩餘 86%；5 小時額度已低於 15%，本輪停止啟動新任務，未進入 M1-03、M1-04 或 M1-05。
- 下一輪：先重查官方適用額度與 Git 狀態，確認可繼續後從 M1-02 的新租戶建立權限設計與 API／受控操作流程開始；再完成 M1-02 完整驗收，依序進入 M1-03、M1-04、M1-05。GitHub Actions 遠端執行、完整 Contract Test、前端及端對端驗收仍未完成。

## 2026-11-12 本機 Git 機密防護驗證

- Gitleaks 8.30.1 透過 Winget `Gitleaks.Gitleaks` 使用者層級安裝；Winget 從 [官方 Release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1) 下載並驗證安裝檔雜湊。使用者 PATH 已更新；安裝前啟動的終端機需重新載入 PATH。
- 目前 Repository 的 Local Git Configuration 已設定 `core.hooksPath=.githooks`。Git for Windows 使用可執行的 `python` 入口；Hook 的 Gitleaks `dir --no-banner --redact --exit-code 1` 參數與已安裝版本相容。
- `python -m unittest discover -s tests/security -p 'test_*.py' -v`：6 項通過，包含正常提交、`.env` 拒絕、官方合成密鑰拒絕、缺少 Gitleaks 時拒絕、只掃 Git Index，以及輸出不洩漏檔名或密鑰。測試以隔離 Git Repository 的 `git commit` 實際觸發 Hook。
- Secret Scan Workflow 的 YAML 與最小 `contents: read` 權限已在本機解析檢查；修正 Go module 安裝路徑，並在官方 Go 1.24 容器實際安裝 Gitleaks v8.28.0。工作目錄與 Git 歷程掃描指令已檢查；遠端 GitHub Actions 執行仍待驗證。
- `gitleaks git --log-opts=--all`、暫存區掃描均通過；已追蹤檔案沒有高風險機密檔名。Compose 服務僅將 Web、API、Demo ERP 綁定 `127.0.0.1`；`docker compose config --quiet` 與四個映像建置通過。
- `pip-audit` 對 Python 開發相依套件解析 27 個套件、`npm audit` 對前端臨時解析 70 個套件、.NET SDK 容器對直接與轉接套件稽核，均未回報已知漏洞。Python 與 Node 版本範圍沒有鎖定檔，後續安裝結果仍可能不同。
- 安全修正 Commit：`141ffae9f35f91ecde0e16060ac10d9447d186f0`。未執行 Git Push。

## 尚待確認事項

- GitHub Actions 遠端 CI 實際結果。
- MinIO 第三方 ECR 映像來源信任與長期供應。
- Python 測試現有的棄用警告。
- 本機 Hook 已在目前 Repository 啟用；其他電腦或重新 Clone 後仍須個別啟用。

## 2026-11-13 前端瀏覽器自動化環境

- 工作項目：安裝並驗證 Playwright MCP，修復 Vite 開發服務的本機 `/api` 代理，執行官方頁面與專案登入錯誤流程的瀏覽器互動測試。
- 修改檔案：`.gitignore`、`apps/web/package.json`、`apps/web/vite.config.ts`、`scripts/testing/playwright_mcp_probe.py`、`docs/development/PLAYWRIGHT-MCP-VERIFICATION.md` 及本紀錄；另新增使用者層級的 Playwright MCP 設定，未更動原有 MCP 設定。
- 實際測試：`npx -y @playwright/mcp@latest --version` 回報 `0.0.85`；`npm run build` 通過；`python scripts/testing/playwright_mcp_probe.py` 通過官方 TodoMVC 新增／勾選及本機登入 401 互動測試，兩張 Screenshot 保存在忽略追蹤的 `test-results/`。
- 限制：目前對話需重啟 Codex／建立新對話後確認 Playwright 工具載入；未使用有效帳號，登入成功、租戶選擇與登出未測。詳見 [Playwright MCP 驗收紀錄](PLAYWRIGHT-MCP-VERIFICATION.md)。
- 下一項任務：使用獨立合成測試帳號與資料狀態，補齊前端成功登入、租戶選擇及登出的 E2E 測試。

## Codex 每輪紀錄範本

### 日期與任務編號

- 工作項目：
- 修改檔案：
- 實際測試指令與結果：
- Gitleaks 暫存區掃描結果：
- Commit SHA：
- 未提交變更：
- 無法確認的額度狀態：
- 風險與阻礙：
- 下一項任務：
