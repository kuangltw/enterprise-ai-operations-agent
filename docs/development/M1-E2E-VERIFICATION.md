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

## 尚未完成

- 新增的 GitHub Actions `e2e` Job 尚未遠端執行；需使用者核准 Push 後核對實際結果。
- 登出曾出現一次無法重現的 500；若遠端或本機再發生，需依錯誤類型分析原因並修正。
- 此套測試使用新建的合成資料庫；既有開發資料庫中的真實帳號與租戶未納入測試。
