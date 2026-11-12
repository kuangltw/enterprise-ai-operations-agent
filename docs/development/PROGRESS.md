# 開發進度（Codex 交接紀錄）

> 狀態以實際測試與 Commit 為準，禁止未經驗證直接標示完成。

| 階段 | 狀態 | 證據 |
|---|---|---|
| M1-01 環境驗證 | 本機已完成 | [驗證紀錄](M1-01-VERIFICATION.md) |
| 本機 Git 機密防護 | 本機已完成 | 2026-11-12 隔離 Repository 提交測試 6 項通過；安全修正 `141ffae9f35f91ecde0e16060ac10d9447d186f0` |
| M1-02 身分驗證與租戶管理 | 進行中 | 密碼雜湊、Session 資料表及 JWT 元件已實作；登入、撤銷與租戶 API 尚未實作 |
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
