# ADR 0001：採用 Modular Monolith（模組化單體）+ Worker

- 日期：2026-11-12
- 狀態：Proposed（提案）

## 背景

專案由個人開發，需要在有限資源下整合 RAG、Agent、採購與監控，同時提供可以重現的本機部署。

## 決策

AI 應用核心採 Python + FastAPI Modular Monolith（模組化單體），以明確領域邊界隔離模組，使用 Celery Worker（背景工作程序）處理文件索引與 Outbox。**Demo ERP 使用 C# + ASP.NET Core Web API**，作為有明確 API Contract（介面契約）的獨立業務系統。

## 替代方案

- Microservices（微服務）：可獨立部署，但營運與分散式資料一致性成本較高。
- 完全耦合的單一程式：建立簡單，但後續維護與測試困難。

## 影響

方便本機 Docker、CI（持續整合）與整合測試；必須維持模組間依賴規則。API 部署節點仍會形成單一故障範圍，後續依實測再評估拆分。
