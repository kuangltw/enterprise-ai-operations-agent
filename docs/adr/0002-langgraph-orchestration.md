# ADR 0002：使用 LangGraph 編排 Agent

- 日期：2026-11-12
- 狀態：Proposed（提案）

## 背景

Agent Workflow（代理程式工作流程）需要明確狀態、Checkpoint（檢查點）、人工核准暫停與故障恢復。

## 決策

以一個受控的 LangGraph Orchestrator（代理程式編排器）為主。Graph State（圖形流程狀態）負責流程進度；PostgreSQL 採購與核准資料表另行負責交易授權及狀態。外部 ERP Tool 使用 C# + ASP.NET Core API。

## 替代方案

- 自由協作的 Multi-Agent（多代理程式）：決策不確定性較高，較難測試交易。
- 完全自行實作 State Machine（狀態機）：可行，但需要額外建置流程持久化與恢復邏輯。

## 影響

Checkpoint／Resume（恢復）能支援觀測與流程延續，但無法保證跨系統原子交易。Interrupt（中斷）重入時，副作用必須具備冪等性。
