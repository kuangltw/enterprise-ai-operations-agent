# AI Coding（AI 輔助程式開發）協作規範

本 Repository 的 M1 已於 2026-11-13 標記為 Accepted with Known Issues（有條件驗收通過），目前進行 M2 文件與 RAG 開發。開始寫程式前，先閱讀 `README.md` 及 `docs/` 中的架構、Schema、API、Workflow、安全與驗收文件。

## 語言與版本管理規範

1. **所有說明、技術文件、README、ADR、Issue 說明以正體中文（台灣習慣用語）為主**，避免簡體中文與中國用語。
2. 技術專有名詞第一次出現時優先使用 **English（中文）**，例如 `Agent Orchestrator（代理程式編排器）`、`Idempotency（冪等性）`。已有標準中文譯名的通用詞可直接用中文。
3. 程式碼識別字、類別名稱、套件名稱、API Path（路徑）、JSON Key（欄位鍵）、SQL DDL 與指令保留英文，避免影響可執行性。
4. **Git Commit Message（提交訊息）以中文為主**，允許標準類別前綴：例如 `docs: 統一正體中文技術文件`、`feat: 新增庫存查詢 API`、`test: 補上跨租戶授權測試`。
5. 不得把未完成規格描述成已實作；文件需明確區分「規劃中」「已實作」「已測試」。
6. 調整設計時同步更新 API、Migration、測試及 ADR，不能留下矛盾文件。

## 技術選型（已確認）

- 前端：React + TypeScript。
- Agent / RAG 後端：Python + FastAPI + LangGraph。
- **Demo ERP：C# + ASP.NET Core Web API**；使用 PostgreSQL，經過 HTTP API 與 AI 後端整合。
- 非同步任務：Redis + Celery；文件：MinIO；向量索引：Qdrant。
- 監控：OpenTelemetry（開放遙測）。
- 架構：Modular Monolith（模組化單體）+ Worker（背景工作程序）；不提前建立微服務。

## 安全與交易設計不可違反的規則

1. 不得繞過 Tenant Membership（租戶成員資格）、RBAC（角色式存取控制）、ACL（存取控制清單）與倉庫資料範圍。
2. 模型回應及外部文件皆視為不可信輸入，LLM 不得自行取得工具權限。
3. 庫存、採購數量、單價、核准與交易條件必須由可測試的確定性程式處理。
4. 不允許 Agent 執行任意 SQL；只允許 Tool Registry（工具註冊中心）白名單工具。
5. ERP 寫入前須具備有效人工核准、即時資料驗證、Outbox 與穩定 Idempotency Key（冪等鍵）。
6. 執行結果不明時先向 ERP 查詢／對帳，不可盲目重試建立採購單。
7. Schema 變更必須使用 Migration；禁止人工修改正式資料庫結構。
8. 禁止提交真實企業資料、密鑰、Token、敏感 Log 及未授權的第三方程式碼。

## 自主開發循環與機密防護（強制）

- 使用 Codex Desktop 時，必須遵守 [AUTONOMOUS_LOOP.md](docs/development/AUTONOMOUS_LOOP.md)，並以 [PROGRESS.md](docs/development/PROGRESS.md) 記錄每輪任務。
- M1 階段限制已依[驗收決策](docs/testing/ACCEPTANCE.md)解除；M2 依 [PROGRESS.md](docs/development/PROGRESS.md) 的工作清單逐項進行，不得一次實作完整 RAG，也不得自行進入 M3。
- 每項小任務依序執行：檢查規格 → 實作 → 測試 → Code Review（程式碼審查）→ Secret Scan（機密掃描）→ 中文 Commit → 更新進度。
- 額度若能可靠取得官方剩餘數值，任一適用額度 ≤15% 時停止新工作；**無法確認額度時最多完成兩項小任務就停止，要求人工確認**，不得自行估算。
- 禁止自動 `git push`、Force Push、`git reset --hard`、`git clean`、`docker compose down -v`、修改 Git 歷史或部署到正式環境。
- Commit 前必須檢查 Staged Diff（暫存區差異）與 Gitleaks 掃描結果，缺少掃描工具時禁止提交。不得使用 `--no-verify` 或其他方式繞過 Hook。
- 禁止提交 `.env`、API Key、Token、JWT Secret、私密金鑰、真實連線密碼、Cookie、真實企業資料、個資及敏感 Log。若疑似洩漏，停止作業、不要輸出值，通知使用者評估撤銷或輪替。
- `.gitignore` 不能防護已追蹤檔案；禁止僅依賴 GitHub Actions（上傳後檢查）取代本機 Pre-commit Hook（提交前檢查）。
- Git Hook 的本機啟用方式與掃描工具安裝限制，請見自主開發循環文件。

## 開發流程與完成條件

- 依序完成 M1 → M2 → M3 → M4 → M5 → M6，不得為趕進度跳過安全性或交易一致性驗證。
- 新增或修改 Domain Service（領域服務）時，必須附上對應 Unit Test（單元測試）或 Integration Test（整合測試）。
- 修改 API 必須同步更新 OpenAPI 與 Contract Test（契約測試）。
- 完成任務要回報：變更檔案、Git Diff（差異摘要）、實際執行的測試、失敗或未執行項目、剩餘風險。
- 不得宣稱測試通過，除非已實際執行並取得結果。
