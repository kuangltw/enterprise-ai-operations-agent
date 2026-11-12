# Enterprise AI Operations Agent（企業 AI 營運代理系統）

> **目前階段：Design / Pre-implementation（設計中／尚未實作）**。本 Repository 現階段提供技術規格，尚無可執行的正式系統，也尚未通過驗收。

本專案是可公開檢視的企業 AI Agent + RAG（檢索增強生成）參考實作，包含 **SOP 知識問答、庫存與銷售分析、採購建議及人工核准、Agent 執行監控**。重點為跨系統整合、權限、安全交易與可復原性。

## MVP（最小可行產品）

| 模組 | 規劃功能 | 狀態 |
|---|---|---|
| SOP 知識問答 | 文件上傳、Hybrid Retrieval（混合檢索）、引用來源、ACL（存取控制清單） | 規劃中 |
| 庫存與銷售分析 | 呼叫受控 ERP API、確定性庫存與銷售計算 | 規劃中 |
| 採購與人工核准 | 建議草稿、審核、重新驗證、冪等 ERP 寫入 | 規劃中 |
| Agent 執行監控 | Run 歷程、Trace（追蹤）、延遲、Token 與成本 | 規劃中 |

## 預定架構

```mermaid
flowchart TD
  UI["React + TypeScript（前端）"] --> API["Python / FastAPI（身分驗證與 API）"]
  API --> AG["LangGraph（Agent 編排）"]
  AG --> RAG["RAG（知識檢索）"]
  AG --> TOOLS["Tool Registry（工具註冊與授權）"]
  AG --> APR["Approval（核准流程）"]
  TOOLS --> ERP["C# / ASP.NET Core（Demo ERP）"]
  RAG --> Q["Qdrant（向量索引）"]
  APR --> DB["PostgreSQL（業務狀態）"]
  API --> DB
  ERP --> EDB["PostgreSQL（獨立 ERP 資料庫）"]
  WORK["Celery Worker（背景工作程序）"] --> DB
  WORK --> ERP
```

- 採用 Modular Monolith（模組化單體）+ Worker（背景工作程序），暫不導入 Microservices（微服務）。
- AI 核心：Python、FastAPI、LangGraph、Qdrant、Redis、MinIO。
- **Demo ERP：C# + ASP.NET Core Web API**，透過 OpenAPI（開放 API 規格）與 AI 核心整合；使用獨立 PostgreSQL Schema／資料庫帳號，首選獨立資料庫。
- LLM（大型語言模型）負責語意理解與說明；庫存計算、授權、審核及交易寫入由確定性程式負責。
- PostgreSQL 為業務資料的 Source of Truth（權威資料來源）；Qdrant 是可重建的檢索索引。

## 技術文件

| 文件 | 內容 |
|---|---|
| [系統架構](docs/architecture/SYSTEM.md) | 模組職責、資料流與可靠性 |
| [資料庫 Schema（結構）](docs/database/SCHEMA.md) | PostgreSQL DDL（資料定義語言）與資料約束 |
| [API Contract（介面契約）](docs/api/CONTRACT.md) | REST、SSE、ERP Tool 規範 |
| [Agent Workflow（代理程式工作流程）](docs/agent/WORKFLOW.md) | State、Node、核准及恢復 |
| [驗收測試](docs/testing/ACCEPTANCE.md) | 測試案例、量測門檻與發布條件 |
| [安全設計](docs/security/SECURITY.md) | 租戶隔離、工具授權、資料保護 |
| [ADR（架構決策紀錄）](docs/adr/README.md) | 設計取捨及替代方案 |
| [AGENTS.md](AGENTS.md) | AI Coding（AI 輔助程式開發）及文件規範 |

## 預定開發順序

1. **M1**：基礎環境、身分驗證、Tenant（租戶）隔離、資料庫 Migration（結構遷移）。
2. **M2**：文件匯入、RAG、來源引用、檢索評估。
3. **M3**：C# Demo ERP、工具契約、Agent 與庫存分析。
4. **M4**：採購草稿、人工核准、Transactional Outbox（交易式寄件匣）與 Idempotency（冪等性）。
5. **M5**：監控、安全與故障恢復測試。
6. **M6**：公開 Demo、文件與 Release（發布）。

## 專案狀態與使用限制

- 目前只有設計文件；尚未提供 `docker compose up` 可啟動的完整環境。
- 未完成安全、交易一致性及 E2E（端對端）測試前，不可接入真實採購交易。
- 所有展示資料必須為 Synthetic Data（合成資料），禁止提交真實企業資料、個資與密鑰。
- 本專案採用 Apache License 2.0（Apache 2.0 開源授權），詳見 [LICENSE](LICENSE)；第三方套件與整合服務仍須依各自授權條款評估。
- 測試門檻為**預設驗收目標**，並非已取得的測試結果。

**設計基準版本：v0.1，2026-11-12。** 實作時若改變設計，必須同步更新文件、測試與 ADR。
