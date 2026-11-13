# ADR（Architecture Decision Record，架構決策紀錄）

ADR 用來記錄「為什麼這樣設計」、評估過哪些替代方案及其代價。

| ADR | 決策 |
|---|---|
| [0001](0001-modular-monolith.md) | 採用 Modular Monolith（模組化單體）與 Worker |
| [0002](0002-langgraph-orchestration.md) | LangGraph 編排與獨立採購交易狀態機 |
| [0003](0003-rag-index-separation.md) | PostgreSQL 文件權限資料與 Qdrant 檢索索引分離 |
| [0004](0004-approval-before-erp-write.md) | ERP 寫入前必須核准、Outbox、冪等處理 |
| [0005](0005-aspnet-core-demo-erp.md) | Demo ERP 使用 C# + ASP.NET Core |
| [0006](0006-browser-session-cookie.md) | 瀏覽器沿用短效工作階段 |

更新架構決策時必須記錄日期、替代方案與影響，並同步檢查相關規格及測試。
