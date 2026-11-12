# 開發進度（Codex 交接紀錄）

> 狀態以實際測試與 Commit 為準，禁止未經驗證直接標示完成。

| 階段 | 狀態 | 證據 |
|---|---|---|
| M1-01 環境驗證 | 本機已完成 | [驗證紀錄](M1-01-VERIFICATION.md) |
| 本機 Git 機密防護 | 本機已完成 | 2026-11-12 隔離 Repository 提交測試 6 項通過；安全修正 `141ffae9f35f91ecde0e16060ac10d9447d186f0` |
| M1-02 身分驗證與租戶管理 | 本機功能完成，整合驗收待 M1-05 | 密碼雜湊、JWT、Session、首次建帳、受控新租戶、成員管理及全域停權已有測試；空白資料庫初始化案例在既有資料庫跳過 |
| M1-03 RBAC 與租戶隔離 | 本機基礎完成，ERP 執行點待 M3 | Tenant Context、Role Policy、倉庫 Scope 與跨租戶測試已實作；實際 ERP 倉庫歸屬仍需 M3 複驗 |
| M1-04 React 登入與管理介面 | 本機建置完成，瀏覽器驗收待執行 | 登入、登出、租戶選擇、受保護畫面與 API 錯誤處理已實作；目前瀏覽器工具不可用 |
| M1-05 CI 與整合驗收 | 進行中 | 422 錯誤契約與 PostgreSQL／Redis CI 測試設定已提交；遠端 CI、瀏覽器驗收及完整回歸待完成 |

## 下一個任務

1. 繼續 M1-05，先補全 M1 Contract Test（契約測試）與 CI，再完成 Docker Compose、安全及前端驗收。
2. 每完成小任務更新本檔：日期、檔案、測試指令、執行結果、Commit SHA、資安風險及下一項工作。

## 2026-11-13 自動續作

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
