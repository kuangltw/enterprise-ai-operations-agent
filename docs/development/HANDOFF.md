# Codex → agy 開發交接

## 基本資訊

- Project：enterprise-ai-operations-agent
- From：Codex Desktop；To：Antigravity CLI 1.4.12（agy）
- Handoff Mode：Handoff Only（僅交接）；交接時間：2026-11-13 16:11（台灣時間，UTC+8）。
- 分支：`main`；交接檢查時的基準 HEAD：`7c61e1444a0d4b3275ffbdfc4606c0b963375419`，亦為第一切片 Commit。若另建立交接 Commit，HEAD 將改變，其 SHA 以 Git 紀錄為準。
- 檢查時本機領先 `origin/main` 一筆，第一切片未 Push；本次不 Push。交接前工作目錄不乾淨，含下列未提交修改。

## 專案現況及限制

M1 已於 2026-11-13 標記為 Accepted with Known Issues（有條件驗收通過）；歷史登出 HTTP 500 仍追蹤。現處 M2-01：PDF 上傳、版本管理與失敗補償。已實作文件中繼資料、租戶／角色／ACL 檢查、PDF 上傳、PostgreSQL 版本預約、MinIO 物件寫入、冪等鍵與索引工作持久登錄。清理、Worker、文件掃描、解析、索引及問答仍未完成，RAG-T01 尚未驗收。

架構為模組化單體加背景工作程序；PostgreSQL 與 MinIO 沒有共同交易。不得繞過租戶成員資格、RBAC 或 ACL；外部文件視為不可信輸入。Schema 必須使用 Migration；不得使用真實企業資料、提交機密、操作正式環境或刪除既有 Docker Volume。不得自動 Push。詳細規範見 `AGENTS.md`、`AUTONOMOUS_LOOP.md` 與 `ACCEPTANCE.md`。

## 第一切片：已提交

Commit `7c61e1444a0d4b3275ffbdfc4606c0b963375419` 加入上傳失敗狀態：MinIO 寫入失敗且讀回確認缺少物件時記錄 `failed`；同鍵重試重新對帳，已 `stored` 版本不降級，索引工作維持唯一。資料庫提交結果不明時回 503，以原鍵重試，不推定失敗或刪除物件。`failed` 不證明物件不存在，逾時的 PUT 可能晚到。

- 隔離 PostgreSQL／MinIO 上傳故障測試 **12 passed**；PDF 上傳、ACL 與物件儲存回歸 **19 passed**。使用合成資料與非 Root MinIO 應用帳號。
- Sol High 安全差異審查及複驗未見阻擋；Gitleaks 暫存掃描及 Git Hook 均通過。
- 資料庫提交回應遺失是 Fault Injection（故障注入）模擬，使用兩條獨立連線；**真正網路斷線尚未驗證**。

## 第二切片：未完成、未提交

交接檢查時的未提交內容如下；交接文件提交後，`PROGRESS.md` 可成為已提交的交接紀錄，但三個程式檔必須保持未追蹤並保留原內容：

| 路徑 | 交接前狀態 | 用途 |
|---|---|---|
| `docs/development/PROGRESS.md` | 已修改 | 第一切片結果、第二切片停止位置與風險紀錄。 |
| `apps/api/migrations/versions/0010_document_retired_keys.py` | 未追蹤 | 新增退役鍵表、租戶／文件／版本複合外鍵及正規鍵約束；降版先取排他表鎖，再拒絕刪除非空退役紀錄。 |
| `apps/api/src/document_cleanup_preview.py` | 未追蹤 | 指定租戶、限制年齡和筆數的內部唯讀 Dry Run（試跑）候選預覽，不連接 MinIO 或刪除物件。 |
| `apps/api/tests/test_document_cleanup_preview_postgres.py` | 未追蹤 | 預覽篩選、租戶與資料約束、降版保護測試；修正後尚待執行。 |

首版在隔離 tmpfs PostgreSQL 套用至 `0010`，六個測試檔 **10 passed、1 warning**；此測試發生在降版競態修正之前。Architect 與 Security Reviewer 發現空表檢查與刪表間可並行插入；初稿改成同交易先取得 `ACCESS EXCLUSIVE` 鎖，Architect 靜態重驗通過。**修正後測試及 Security Reviewer 安全複驗尚未執行**，實際並行降版、離線 SQL 與完整差異重評亦待驗。第二切片尚未執行 Gitleaks、尚未 Commit，沒有執行正式物件刪除。

## 已知風險

- Cleaner 與 Uploader 並行、鎖定範圍與鎖順序可能造成競態或 Deadlock（死鎖）；實際清理前須在一致鎖序下重新檢查。
- 目前預覽使用版本建立時間，進行中的上傳也可能出現；Dry Run 是快照盤點，不能授權刪除，亦不能證明物件存在。
- 已儲存或發布的有效版本不得誤刪；必須維持跨租戶物件隔離及 ACL。`failed` 不能單獨授權清理。
- PostgreSQL 與 MinIO 可能不一致；延遲 PUT／DELETE 可能在逾時後才完成。退役舊鍵、切換新鍵與重掃尚未實作；真正網路斷線尚未驗證。

## agy 接手後第一項任務

1. 先閱讀 `AGENTS.md` 與本文件，確認 agy 實際載入共同規範。
2. 檢查 Git Status、HEAD、Diff 與 Untracked Files，確認上述修改完整存在；禁止 `git reset`、`git clean` 或覆蓋現有修改。
3. 以隔離 PostgreSQL 與合成資料重跑第二切片競態修正後測試，補充並行、鎖定、降版與必要的離線 SQL 驗證。
4. 完成獨立 Security Review（安全審查）、依完整差異重評風險，必要時修正後交回重驗。
5. 只有測試與審查通過後，檢查暫存差異、執行 Gitleaks 與 Git Hook，再建立第二切片中文 Commit；不得自動 Push。
6. 不得直接開始正式孤兒物件刪除。第二切片完成後才評估退役鍵切換、受控孤兒清理，以及 Dry Run 與實際刪除的獨立授權機制。

## 工具差異

Codex 與 agy 的模型、對話及 Agent 設定互相獨立。`.codex/` 是 Codex 專屬設定；agy 應使用自身實際支援的設定，不得假設可直接使用 Codex 子代理 TOML 或讀取 Codex 對話歷史。共同專案規範以 `AGENTS.md` 為準，但須確認 agy 實際載入。高風險設計及獨立安全複驗應依 agy 的實際可用能力及專案風險政策執行；無法確認必要審查時暫停受影響實作或提交。

**Codex 已停止於 M2-01 第二切片的競態修正後、重新測試前。第二切片尚未完成驗收。接手者必須保留全部未提交修改，先驗證再繼續。**
