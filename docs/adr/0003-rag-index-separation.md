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

需要設計索引一致性、重建、版本發布機制。檢索前套用 Tenant／ACL Filter（篩選），回答前再次依 PostgreSQL 驗證權限。
