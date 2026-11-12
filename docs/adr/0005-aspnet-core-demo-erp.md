# ADR 0005：Demo ERP 採用 C# + ASP.NET Core

- 日期：2026-11-12
- 狀態：Accepted（已確認技術選型；程式尚未實作）
- 決策範圍：Demo ERP（ERP 模擬業務系統）

## 背景

本專案主要用途之一是公開 GitHub 作品集，展示 AI Agent（人工智慧代理程式）、RAG（檢索增強生成）、Enterprise Backend Engineering（企業後端工程）與跨語言 API Integration（API 整合）能力。

AI 核心已使用 Python + FastAPI + LangGraph。Demo ERP 應展示獨立的企業業務系統開發能力，並方便建立可測試的 Transaction（交易）、Concurrency Control（並行控制）及 Idempotency（冪等性）機制。

## 決策

採用 **C# + ASP.NET Core Web API + EF Core + Npgsql + PostgreSQL**。

- Demo ERP 提供商品、倉庫、庫存、銷售、採購與冪等執行紀錄。
- Python Agent 透過正式定義的 HTTP API 呼叫 ERP；不得直接連線修改 ERP Database（資料庫）。
- 對外提供 OpenAPI（開放 API 規格），建立 Python 與 C# 的 Contract Test（契約測試）。
- C# Domain Service（領域服務）負責確定性的庫存與交易驗證；金額與數量使用 `decimal`。
- ERP Database 使用 EF Core Migration（資料庫結構遷移），與 Python Alembic 管理的 Agent Database 分開。
- 在 ERP 端強制 Idempotency Key 唯一約束與 Transaction（交易），並提供依冪等鍵查詢結果的 API。
- 測試優先採 xUnit；容器化使用 Docker。

## 替代方案

| 技術 | 優勢 | 未採用理由 |
|---|---|---|
| PHP + Laravel | 開發快速、既有成熟經驗 | 相較 C#，額外展示的跨技術棧能力較少 |
| Java + Spring Boot | 企業市場成熟、強型別架構 | 本階段選擇 C# 作為開發投入與示範範圍的平衡 |
| Go + Gin | 部署精簡、並行處理能力佳 | 目前希望展示偏企業資訊系統與交易流程的技術 |
| Python + FastAPI | 技術棧一致、維護成本低 | AI 核心已採用 Python，對跨語言整合展示較少 |

## 後果與風險

- 需維護 Python 與 C# 兩套建置、測試及套件安全更新流程。
- 跨語言 DTO（資料傳輸物件）、Decimal（十進位數）與日期格式須透過契約測試驗證。
- 採購寫入跨系統無法直接形成單一 DB Transaction；需 Outbox（交易式寄件匣）與 ERP 端冪等處理。
- Demo ERP 不追求完整大型 ERP 功能，先滿足四項 MVP 情境。
- 不因 AI Coding（AI 輔助程式開發）產出而直接宣稱具備實務 C# 年資，應以可驗證的設計、測試與程式品質說明成果。

## 相關文件

- [系統架構](../architecture/SYSTEM.md)
- [資料庫 Schema](../database/SCHEMA.md)
- [API Contract](../api/CONTRACT.md)
- [驗收測試](../testing/ACCEPTANCE.md)
