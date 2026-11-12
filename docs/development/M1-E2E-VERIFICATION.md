# M1 Playwright E2E 驗收（2026-11-13）

## 執行方式

Windows 與 GitHub Actions 均使用同一個執行器。在專案根目錄執行：

```powershell
npm ci --prefix apps/web --no-audit --no-fund
npm exec --prefix apps/web -- playwright install chromium
python scripts/testing/run_m1_e2e.py
```

CI 的 Linux Runner 另以 `npx playwright install --with-deps chromium` 安裝系統依賴。`docker-compose.e2e.yml` 使用獨立的隨機 Compose Project、PostgreSQL tmpfs 與無持久化 Redis；Web 只綁定 `127.0.0.1` 的隨機連接埠。執行器每次產生合成帳號、密碼、JWT 簽章金鑰與資料庫密碼，只透過程序環境傳給測試容器，不寫入 Repository 或測試報告。結束時執行 `docker compose down` 清理該次測試容器及網路，不使用 `down -v`，也不碰現有開發資料庫的 Volume。

Playwright 關閉 Trace（追蹤）、Screenshot（截圖）與 Video（錄影）輸出，避免驗收產物保存測試憑證。`test-results/` 已被 `.gitignore` 排除；執行時仍須保護本機程序環境與 Docker 管理權限。

## 本機結果

- Headless Chromium：4 passed。涵蓋未登入畫面與重新整理、錯誤密碼、登入成功後切換合成租戶甲／乙及登出、另一個帳號無權讀取租戶甲與無成員資格租戶。
- API 跨租戶端點回 404；登出後使用同一 JWT 查詢 `/auth/me` 回 401。
- 首次執行因 seed 腳本找不到 `src` 模組而失敗；為隔離 API 容器設定 `PYTHONPATH=/app` 後重跑通過，未放寬測試或授權條件。
- 改用 CI 相同的 `npm run test:e2e` 入口後，曾有一次 API 跨租戶案例的登出請求回 500；之後兩次完整重跑皆為 4 passed，原因尚未確定。執行器在未來失敗時只回報 API 例外類型，不輸出測試憑證；此間歇性失敗仍列為驗收風險，不視為已修復。
- 針對該案例再以 `python scripts/testing/run_m1_e2e.py --grep=API --repeat-each=4` 在同一個隔離環境重複執行 4 次，結果 4 passed。執行器允許將命令列參數轉交 Playwright，供後續在隔離環境重現；目前仍無法確認先前 500 的原因。
- 再於六個新建的隔離環境執行完整 E2E，每輪 4 passed，均未重現登出 500。檢查 Session 約束、登出更新與 Tenant Context 後，尚無足以確認根因的例外紀錄；原失敗所屬容器已在測試結束時清理。依偵錯流程保留失敗證據與後續僅輸出例外類型的診斷，不以猜測修改驗證或授權邏輯。
- 遠端 `6af29ac` 的 [M1 CI](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43319565777)之 Python、dotnet、frontend、compose、e2e 五個 Job 均成功；E2E Job Log 顯示 4 passed。[Gitleaks 工作](https://github.com/kuangltw/enterprise-ai-operations-agent/actions/runs/43319565690)亦成功。這是遠端未重現的證據，不足以證明單次 500 的原因或已修復。

## 最後一次有範圍的調查與判定

- 2026-11-13 於新建的獨立 tmpfs PostgreSQL／Redis 環境執行一次完整 `python scripts/testing/run_m1_e2e.py`，結果 4 passed，未重現 500；執行器以 `docker compose down` 清理該次容器與網路。
- FastAPI 使用共用 SQLAlchemy Engine（啟用 `pool_pre_ping`）；每個請求由 `get_db` 建立並關閉 Session。登出先由 `get_current_user` 查詢有效且未撤銷的 Session，再以同一 Session 更新及 `commit`。程式未實作額外的服務關閉回呼；檢查期間未發現可確認的連線池、交易或關閉競態。原失敗當次缺少 Traceback，不能推定根因。
- Playwright 設定 `workers: 1`，案例依序執行；同一組合成帳號供兩個案例登入，但各次登入建立獨立 Session。未發現共用 JWT 或跨案例撤銷；測試結束由執行器清理隔離資源。
- 登出後舊 JWT 對 `/auth/me` 回 401；再次登出回 401，且後續 `/auth/me` 仍為 401。新增的 SQLite 斷言已通過；PostgreSQL 斷言已加入測試，待下次 CI 驗證。這只證明已測情境，不代表歷史 500 已修復。
- 歷史失敗與再發時的蒐證、重新列為 Blocker 條件，見[獨立追蹤紀錄](issues/LOGOUT-500.md)。

## 後續追蹤

- 登出曾出現一次無法重現的 500；保留為 Known Issue（已知問題），若再次符合追蹤紀錄的條件，重新列為 Blocker 並調查。
- 此套測試使用新建的合成資料庫；既有開發資料庫中的真實帳號與租戶未納入測試。
