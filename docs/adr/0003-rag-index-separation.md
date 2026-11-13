# ADR 0003：將 RAG 權威資料與檢索索引分離

- 日期：2026-11-12
- 狀態：Proposed（提案）

## 背景

SOP 文件需有版本歷程、引用來源與 Tenant／ACL 存取控制。Vector Index（向量索引）可能重建或暫時不可用。

## 決策

PostgreSQL 保存文件權限、版本、來源 Chunk（區塊）與索引狀態；MinIO 保存原始檔案；Qdrant 保存 Dense／Sparse Retrieval（語意與稀疏檢索）索引與必要篩選欄位。

## 替代方案

- 所有 Metadata（中繼資料）放在 Qdrant：元件較少，但權限與版本的一致性較難管理。
- PostgreSQL + pgvector：服務數量較少，但檢索策略與擴充特性不同。

## 影響

上傳 API 在私有物件核對成功，且 PostgreSQL 提交儲存狀態與索引工作後回應 202。上傳及重試皆保留原有 `current_version`；後續發布須有安全掃描及索引就緒證據。回應遺失時使用原冪等鍵對帳，並重新驗證角色及建立者 ACL。

需要設計索引一致性、重建、版本發布機制。檢索前套用 Tenant／ACL Filter（篩選），回答前再次依 PostgreSQL 驗證權限。

M2 已新增 `document_index_jobs` 持久工作登錄表：原始檔經 MinIO 讀回核對後，`storage_status = stored` 與每版本唯一的 `pending` 工作在同一 PostgreSQL 交易提交。這避免儲存完成卻遺漏索引工作登錄；Redis／Celery 發送、Worker 消費、重試上限、Qdrant 寫入與 `ready` 後發布仍未實作，因此本 ADR 仍為 Proposed（提案），不得將工作登錄視為索引已完成。
