# M1 開發環境啟動與驗證

> M1-01 已於 2026-11-12 在 Windows Docker Desktop 執行基礎環境驗證。實際指令與結果見 [驗證紀錄](M1-01-VERIFICATION.md)；完整 M1 與後續里程碑尚未驗收。

## 環境需求

- Docker Engine 與 Docker Compose Plugin（組合服務工具）
- 可用的 Docker Build 網路（首次下載映像檔與套件）
- 本機測試可使用 WSL2（Windows Linux 子系統）

## 啟動

```bash
git clone https://github.com/kuangltw/enterprise-ai-operations-agent.git
cd enterprise-ai-operations-agent
cp .env.example .env
# 編輯 .env，替換所有 change- 開頭的密碼；.env 已由 Git 忽略
docker compose up --build -d
docker compose ps
```

預設服務：
- React 前端：`http://127.0.0.1:5173`（目前僅展示功能規劃）
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

注意：`docker compose exec` 指令中的變數需由目前 Shell 提供；執行前可先 `set -a; source .env; set +a` 匯出，或改用具體的本機測試帳號與資料庫名稱。

預期 Agent DB 含 `tenants`、`users`、`memberships`、`alembic_version`；ERP DB 含 `erp_products`、`erp_warehouses`、`erp_inventory`、`__EFMigrationsHistory`。

## M1-01 已執行驗證

2026-11-12 已從本專案尚無 Compose Volume 的狀態執行 `docker compose config --quiet`、`docker compose build` 與 `docker compose up -d`。Alembic 套用 `0001_identity`，EF Core 套用 `202611120001_InitialErp`；重跑 Migration 後版本維持不變。FastAPI 與 Demo ERP 的 `/health/live`、`/health/ready` 均回應 HTTP 200。Python 測試為 3 passed；C# Release Build 為 0 警告、0 錯誤；React 由 Docker Build 完成 TypeScript 與 Vite 建置。EF Core `has-pending-model-changes` 回報沒有未記錄的模型變動。詳見 [可查證的指令與結果](M1-01-VERIFICATION.md)。

## 關閉及清除

```bash
docker compose down
# 以下指令會永久刪除本機 Volume 及資料，請確認後使用
docker compose down -v
```

## 已知限制與 M1 待辦

- 目前提供健康檢查、登入、目前使用者、登出及本人可存取的租戶讀取端點；租戶 admin 可建立新 User 與非 admin Membership，並變更或撤銷這些成員的角色與資格。使用前須在本機 `.env` 設定至少 32 bytes 的隨機 `JWT_SIGNING_KEY`。未設定或仍為 `change-` 範例值時，登入會回傳 503。首次建立管理員與租戶可在空白資料庫執行 `docker compose run --rm api python -m src.bootstrap_identity`，依終端機提示輸入 Email、租戶名稱與密碼；密碼不應放在指令參數。資料庫已有 User 或 Tenant 時此指令會拒絕重做。公開註冊、完整 RBAC（角色式存取控制）及新 Tenant 寫入 API 仍未實作。
- 全域 User 停權僅供有 Agent 資料庫操作權限者執行：`docker compose run --rm api python -m src.disable_user`。依提示輸入 Email 並確認；指令會在同筆交易停權 User 及撤銷其所有 Session。租戶 admin API 僅能撤銷其租戶 Membership，無法停用全域帳號。執行前應依組織的操作程序核對身分與影響範圍。
- C# ERP 只有商品、倉庫與庫存初始資料模型，尚未實作銷售、採購、實際業務工具 API。
- EF Core 的啟動自動 Migration 只用於本機 Demo；正式環境改以專用部署 Job 執行。
- React 前端目前僅有靜態 M1 首頁，尚未接入 API 或登入流程。
- 跨服務 Contract Test（契約測試）、完整身分驗證驗收、租戶隔離與安全測試仍未執行；GitHub Actions CI 尚未在遠端執行驗證。
