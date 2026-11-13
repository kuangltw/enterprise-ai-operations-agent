# 登出 API 歷史間歇性 HTTP 500 與工作階段撤銷時差

## 首次發生與重現結果

2026-11-13 使用與 CI 相同的 `npm run test:e2e` 入口時，Playwright「跨租戶要求由 API 拒絕」案例的一次 `POST /api/v1/auth/logout` 回 HTTP 500。原隔離容器已清理，該次 API 例外紀錄未保存。後續兩次完整 E2E、同環境 API 案例四次、六個新隔離環境各四項 E2E、遠端 `6af29ac` 與 `66aabc9` 的 E2E，以及本次再執行的一個新隔離環境四項 E2E，皆通過且未重現。

檢查 FastAPI 登出與 Session 驗證、SQLAlchemy 連線池與交易、PostgreSQL Session 約束，以及 Playwright 單 worker、案例資料與清理時序，尚無可確認根因。登出更新以 `revoked_at IS NULL` 限制並提交；舊 JWT 在後續請求重新查詢資料庫。SQLite 回歸測試及既有 PostgreSQL／E2E 測試確認登出後 `/auth/me` 回 401；新增的再次登出斷言確認仍回 401，不會恢復 Session。新增的 PostgreSQL 再次登出斷言尚待下次 CI 執行。

## 風險與再發處理

2026-11-13 M2 回歸在 Windows 原生 Python 與新建 Docker PostgreSQL 執行 `test_login_and_revocation_against_postgres` 時，登出更新觸發 `ck_sessions_revoked_after_creation`。觀察到應用程式提供的撤銷時間比資料庫建立時間早約 0.25 秒。此證據重新開啟 Session 撤銷調查；原瀏覽器事件是否同源仍待確認。假設為應用與資料庫時間來源不同。退出條件為以可控時差重現、修正並驗證原憑證在登出後失效，再執行授權回歸。依 AGENTS.md 採兩輪、每輪至多三種策略。

在獨立 PostgreSQL 將測試工作階段建立時間推至約 30 秒後，修正前登出觸發相同約束。登出與全域停權改在撤銷 SQL 中將時間下限設為 `created_at`，使時差無法中止撤銷。原瀏覽器事件缺少例外紀錄，仍為 Unreproduced / Tracked。

根因**尚未確認**，也沒有證據證明歷史 500 已修復。若再次發生，可能造成撤銷交易未完成、Session 狀態不明或認證服務暫時不可用。再次發生時收集 Trace ID／Request ID、UTC 時間、例外類型、SQLSTATE（若有）、安全處理後的 API／PostgreSQL Log、連線池與服務關閉時序，以及登出後原 JWT 對 `/auth/me` 的 HTTP 狀態。不得輸出或保存 JWT、密碼、金鑰、Cookie、完整連線字串及敏感 Log。

以下任一條件成立即重新列為 Blocker：目前可重現登出 HTTP 500；撤銷後舊 JWT 仍有效或再次登出恢復 Session；跨租戶資料洩漏；核心 API、Migration、E2E 或 Gitleaks 測試失敗；有證據顯示重大交易一致性或安全風險。

2026-11-13 後續核對：`7ef7248` 的 Python、dotnet、frontend、compose、e2e 與 Gitleaks CI 均成功；Playwright MCP 只驗證錯誤帳密與未登入文件讀取，沒有執行新的登出重現策略。本次沒有新錯誤證據，依 `AGENTS.md` 的退出條件不重啟歷史 500 調查，保留上述重新調查門檻。

GitHub Issue 建立動作於 2026-11-13 被自動審核拒絕，原因為認證與安全風險資訊將持久傳送到尚未確認信任狀態的遠端儲存庫。本檔為獨立的本機待追蹤紀錄；遠端 Issue 尚未建立。
