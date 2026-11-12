# M1 開發環境啟動與驗證

> 目前提供原始碼及環境設定；尚未由專案維護者完成 Docker / .NET 實際執行驗證。不得將本文件視為測試通過報告。

## 環境需求

- Docker Engine 與 Docker Compose Plugin（組合服務工具）
- 可用的 Docker Build 網路（首次下載映像檔與套件）
- 本機測試可使用 WSL2（Windows Linux 子系統）

## 啟動

```bash
git clone https://github.com/kuangltw/enterprise-ai-operations-agent.git
cd enterprise-ai-operations-agent
cp .env.example .env
# 編輯 .env，替換所有 change- 開頭的密碼
docker compose up --build -d
docker compose ps
```

預設服務：
- FastAPI：`http://127.0.0.1:8000/docs`（Swagger API 文件）
- FastAPI Liveness（存活檢查）：`http://127.0.0.1:8000/health/live`
- FastAPI Readiness（就緒檢查）：`http://127.0.0.1:8000/health/ready`
- ASP.NET Core Liveness：`http://127.0.0.1:8080/health/live`
- ASP.NET Core Readiness：`http://127.0.0.1:8080/health/ready`

PostgreSQL（兩個實例）、Redis、Qdrant、MinIO 預設只在 Compose 內部網路提供服務。資料庫使用獨立 Volume（資料卷）。

## 驗證 Migration

```bash
docker compose logs agent-migrate
docker compose logs demo-erp
docker compose exec agent-db psql -U "${AGENT_DB_USER}" -d "${AGENT_DB_NAME}" -c '\dt'
docker compose exec erp-db psql -U "${ERP_DB_USER}" -d "${ERP_DB_NAME}" -c '\dt'
```

注意：`docker compose exec` 指令中的變數需由目前 Shell 提供；執行前可先 `source .env` 並 `set -a` 匯出，或改用具體的本機測試帳號與資料庫名稱。

預期 Agent DB 含 `tenants`、`users`、`memberships`、`alembic_version`；ERP DB 含 `erp_products`、`erp_warehouses`、`erp_inventory`、`__EFMigrationsHistory`。

## 關閉及清除

```bash
docker compose down
# 以下指令會永久刪除本機 Volume 及資料，請確認後使用
docker compose down -v
```

## 已知限制與 M1 待辦

- 目前只提供健康檢查，尚未實作 Authentication（驗證）、RBAC（角色式存取控制）及 Tenant API。
- C# ERP 只有商品、倉庫與庫存初始資料模型，尚未實作銷售、採購、實際業務工具 API。
- EF Core 的啟動自動 Migration 只用於本機 Demo；正式環境改以專用部署 Job 執行。
- 尚未建立 React 前端；在完成 M1 安全基礎後再新增。
- 仍須完成 Docker 實測、跨服務 Contract Test（契約測試）與安全測試。
