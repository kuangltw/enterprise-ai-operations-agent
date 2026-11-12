# 開發進度（Codex 交接紀錄）

> 狀態以實際測試與 Commit 為準，禁止未經驗證直接標示完成。

| 階段 | 狀態 | 證據 |
|---|---|---|
| M1-01 環境驗證 | 本機已完成 | [驗證紀錄](M1-01-VERIFICATION.md) |
| 本機 Git 機密防護 | 本機已完成 | 2026-11-12 隔離 Repository 提交測試 6 項通過；安全修正 `141ffae9f35f91ecde0e16060ac10d9447d186f0` |
| M1-02 身分驗證與租戶管理 | 進行中 | 首次建帳、登入、Session 撤銷、租戶讀取及 admin 建立成員已實作；成員角色變更與停權尚未實作 |
| M1-03 RBAC 與租戶隔離 | 待開始 | 尚未實作 |
| M1-04 React 登入與管理介面 | 待開始 | 尚未實作 |
| M1-05 CI 與整合驗收 | 待開始 | 尚未實作 |

## 下一個任務

1. 繼續 M1-02，先完成身分驗證所需的下一項最小工作。
2. 每完成小任務更新本檔：日期、檔案、測試指令、執行結果、Commit SHA、資安風險及下一項工作。

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
