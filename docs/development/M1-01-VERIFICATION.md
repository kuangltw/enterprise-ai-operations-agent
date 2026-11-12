# M1-01 基礎環境驗證紀錄

## 範圍與環境

- 日期：2026-11-12（台灣時間）。
- 環境：Windows、Docker Desktop Engine 29.4.2、Docker Compose v5.1.3；建置使用映像內的 Python 3.12、Node.js 22、.NET 10 SDK。
- 執行前，此 Compose 專案沒有服務或資料庫 Volume。本次建立的 Volume 未刪除；重跑 Migration 使用相同 Volume。
- 本機 `.env` 由 `.env.example` 複製後換成隨機測試密碼，已由 Git 忽略。以下紀錄不含密碼。

## 發現的問題與修復

| 問題 | 重現結果與根因 | 修復與回歸防護 |
|---|---|---|
| MinIO 無法拉取 | 初次 `docker compose up -d` 回報 `pull access denied for minio/minio`；既有 Docker Hub 映像來源已不可取得。Quay 的相同版本也回應 HTTP 401。 | 改用可拉取的公開 ECR MinIO 鏡像並固定 SHA256 Digest；CI 增加 `docker compose pull minio`。此鏡像為第三方重新發布，須持續評估來源維護與安全性。 |
| Python 測試無法收集 | 在 API 映像執行 `pytest -q` 出現 `ModuleNotFoundError: No module named 'src'`；測試根目錄未加入 import path。 | 新增 `pytest.ini` 設定 `pythonpath = .`，維持 CI 原有指令；新增資料庫可用與不可用的 Readiness（就緒檢查）案例。 |
| C# 相依套件警告 | 原 `dotnet build` 顯示 `System.Security.Cryptography.Pkcs 9.0.0` 的 NU1902／NU1903；`dotnet nuget why` 指向 EF Core Design 10.0.0 的設計時相依套件。 | EF Core Design 與 HealthChecks 更新至 10.0.13；重新建置為 0 警告，依賴圖不再含 Pkcs。CI 增加 EF Core ModelSnapshot 一致性檢查。 |

## 實際執行與結果

| 指令或檢查 | 結果 |
|---|---|
| `docker compose config --quiet` | Exit 0。 |
| `docker compose build` | `web`、`api`、`agent-migrate`、`demo-erp` 全部建置成功；React 建置執行 `tsc --noEmit && vite build`，成功。 |
| `docker compose pull minio` | 固定 Digest 的 ECR 映像成功拉取。 |
| `docker compose up -d`、`docker compose ps -a` | Agent DB、ERP DB、Redis、FastAPI、Demo ERP 均為 healthy；Alembic Job 為 Exited (0)；Web、MinIO、Qdrant 為 Up。 |
| `docker compose logs agent-migrate` | 套用 `0001_identity`，Exit 0。 |
| `docker compose exec -T agent-db psql -U agent_app -d agent_ops -tAc "SELECT version_num FROM alembic_version"` | `0001_identity`；表格包含 `alembic_version`、`memberships`、`tenants`、`users`。 |
| `docker compose exec -T erp-db psql -U erp_app -d demo_erp -tAc 'SELECT "MigrationId" FROM "__EFMigrationsHistory"'` | `202611120001_InitialErp`；表格包含 `__EFMigrationsHistory`、`erp_inventory`、`erp_products`、`erp_warehouses`。 |
| `docker compose run --rm agent-migrate`、`docker compose up -d demo-erp` | 既有 Volume 上重跑成功；Migration 版本維持不變，Demo ERP 再次健康。 |
| `curl.exe -fsS http://127.0.0.1:8000/health/live` 與 `/health/ready` | HTTP 200，分別回傳 `status: ok`、`status: ready`。 |
| `curl.exe -fsS http://127.0.0.1:8080/health/live` 與 `/health/ready` | HTTP 200，分別回傳 `status: ok`、`Healthy`。 |
| `curl.exe -fsS http://127.0.0.1:5173/` | HTTP 200，回傳前端 HTML。 |
| API 映像內 `python -m compileall -q src migrations && pytest -q` | 3 passed；另有 1 項 Starlette／`httpx` 的 DeprecationWarning（棄用警告）。 |
| .NET SDK 建置映像內 `dotnet build EnterpriseDemoErp.csproj -c Release --no-restore` | Build succeeded，0 Warning、0 Error。 |
| .NET SDK 建置映像內 `dotnet-ef migrations has-pending-model-changes --project EnterpriseDemoErp.csproj` | `No changes have been made to the model since the last migration.` |

## 尚未執行與風險

- GitHub Actions 遠端 CI 尚未執行；本紀錄只涵蓋本機實測，CI 新增步驟仍待遠端結果。
- M1 的 Authentication（身分驗證）、Tenant（租戶）隔離、RBAC（角色式存取控制）及跨服務 Contract Test（契約測試）尚未實作或執行；M2–M6 的業務、安全、效能與端對端驗收亦未執行。
- MinIO 目前使用第三方 ECR 鏡像的固定 Digest。此舉讓乾淨環境可重現啟動，但仍需後續確認長期供應與來源信任。參考：[公開映像頁面](https://gallery.ecr.aws/y9w4h2u9/minio)。
- Python 測試的 Starlette／`httpx` 棄用警告不影響此次 3 項測試通過；後續升級相依套件時需重新檢查。
