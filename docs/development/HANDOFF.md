# Codex → agy 開發交接

## 基本資訊

- Project：enterprise-ai-operations-agent
- From：Codex Desktop；To：Antigravity CLI 1.4.12（agy）
- Handoff Mode：Handoff Only（僅交接）；交接時間：2026-11-13 16:11（台灣時間，UTC+8）。
- 分支：`main`；Codex 交接前基準為 `7c61e1444a0d4b3275ffbdfc4606c0b963375419`（第一切片），交接 Commit 為 `9fa837b0134eef319458f091aa9a79bbb6ccede6`；最新 HEAD 以 Git 紀錄為準。
- 本機領先 `origin/main`，第一切片及交接 Commit 均未 Push；本次不 Push。

## 專案現況及限制

M1 已於 2026-11-13 標記為 Accepted with Known Issues（有條件驗收通過）；歷史登出 HTTP 500 仍追蹤。現處 M2-01：PDF 上傳、版本管理與失敗補償。已實作文件中繼資料、租戶／角色／ACL 檢查、PDF 上傳、PostgreSQL 版本預約、MinIO 物件寫入、冪等鍵與索引工作持久登錄。清理、Worker、文件掃描、解析、索引及問答仍未完成，RAG-T01 尚未驗收。

架構為模組化單體加背景工作程序；PostgreSQL 與 MinIO 沒有共同交易。不得繞過租戶成員資格、RBAC 或 ACL；外部文件視為不可信輸入。Schema 必須使用 Migration；不得使用真實企業資料、提交機密、操作正式環境或刪除既有 Docker Volume。不得自動 Push。詳細規範見 `AGENTS.md`、`AUTONOMOUS_LOOP.md` 與 `ACCEPTANCE.md`。

## 第一切片：已提交

Commit `7c61e1444a0d4b3275ffbdfc4606c0b963375419` 加入上傳失敗狀態：MinIO 寫入失敗且讀回確認缺少物件時記錄 `failed`；同鍵重試重新對帳，已 `stored` 版本不降級，索引工作維持唯一。資料庫提交結果不明時回 503，以原鍵重試，不推定失敗或刪除物件。`failed` 不證明物件不存在，逾時的 PUT 可能晚到。

- 隔離 PostgreSQL／MinIO 上傳故障測試 **12 passed**；PDF 上傳、ACL 與物件儲存回歸 **19 passed**。使用合成資料與非 Root MinIO 應用帳號。
- Sol High 安全差異審查及複驗未見阻擋；Gitleaks 暫存掃描及 Git Hook 均通過。
- 資料庫提交回應遺失是 Fault Injection（故障注入）模擬，使用兩條獨立連線；**真正網路斷線尚未驗證**。

## 第二切片：已完成驗證與審查（agy 接手）

- agy 已於隔離 tmpfs PostgreSQL 與 MinIO 完成第二切片修正後驗證：
  - `alembic upgrade head`（`0010_document_retired_keys`）與離線 SQL（`alembic downgrade 0010_document_retired_keys:0009_document_index_jobs --sql`）均通過，確認含 `BEGIN; ... LOCK TABLE document_upload_retired_keys IN ACCESS EXCLUSIVE MODE; DO $$ ... $$ ... COMMIT;`。
  - 六個核心測試檔：**12 passed, 1 warning**；十二個文件／上傳／ACL／儲存全套回歸測試檔：**35 passed, 1 warning**。
  - 並行測試：驗證未提交插入與降版 `ACCESS EXCLUSIVE` 鎖互相阻塞並安全拒絕非空降版；驗證 Uploader 持有 `FOR UPDATE` 鎖定期間 Cleaner 預覽不阻塞，且完成儲存後立即排除已儲存版本。
- 獨立 Security Review（高推理模型唯讀審查）判定 **通過（Pass with Recommendations）**，無 Critical 阻擋項。

## 已知風險與第三階段必納項目

- Cleaner 與 Uploader 並行、鎖定範圍與鎖順序可能造成競態或 Deadlock（死鎖）；實際清理前須在一致鎖序下重新檢查（含 `complete_document_upload` 必須檢查 `NOT EXISTS` 退役鍵，防止已退役鍵被舊請求復活）。
- 目前預覽使用版本建立時間，進行中的上傳也可能出現；Dry Run 是快照盤點，不能授權刪除，亦不能證明物件存在。
- 已儲存或發布的有效版本不得誤刪；必須維持跨租戶物件隔離及 ACL。`failed` 不能單獨授權清理。
- PostgreSQL 與 MinIO 可能不一致；延遲 PUT／DELETE 可能在逾時後才完成。退役舊鍵、切換新鍵、可控孤兒清理、Dry Run／實際刪除／授權分離與故障注入回歸將於第三階段實作。
- 建議於後續 Migration 為 `document_versions(storage_key)` 建立索引以優化撞鍵排除查詢，並於未來強化正規鍵比對為 `\\Z`。

## agy 下一階段任務

1. 第二切片通過 Gitleaks 與 `.githooks/pre-commit` 後建立正體中文 Commit（不自動 Push）。
2. 確認第二切片驗收完成後，進入第三階段：退役鍵切換、可控孤兒物件清理、Dry Run／實際刪除／授權檢查分離、故障注入與並行回歸測試。

## 工具差異

Codex 與 agy 的模型、對話及 Agent 設定互相獨立。`.codex/` 是 Codex 專屬設定；agy 應使用自身實際支援的設定，不得假設可直接使用 Codex 子代理 TOML 或讀取 Codex 對話歷史。共同專案規範以 `AGENTS.md` 為準，但須確認 agy 實際載入。高風險設計及獨立安全複驗應依 agy 的實際可用能力及專案風險政策執行；無法確認必要審查時暫停受影響實作或提交。
