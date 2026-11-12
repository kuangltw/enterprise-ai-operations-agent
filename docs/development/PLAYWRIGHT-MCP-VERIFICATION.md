# Playwright MCP 前端瀏覽器驗收（2026-11-13）

## 環境與設定

- Windows 原生 Node.js `v24.22.2`、npm／npx `11.19.1`，符合 Playwright MCP 的 Node.js 20 以上要求。
- 原有 `chrome-devtools` MCP 無法取得分頁：`list_pages` 回報設定的 `/home/kuang/.local/bin/google-chrome` 不存在。該設定屬 WSL 路徑，與目前 Windows 原生執行環境不符；未改動原有設定。
- 執行 `codex mcp add playwright npx "@playwright/mcp@latest"` 成功；`codex mcp get playwright` 顯示啟用的 stdio Server 與預期的 `npx` 參數。既有 MCP 設定未覆蓋。
- `npx -y @playwright/mcp@latest --version` 回報 `0.0.85`。Windows 使用者快取已有 `chromium-1243` 與 `chromium_headless_shell-1243`；實際以隔離、Headless（無視窗）模式啟動 Chromium 成功，無須另行下載。
- 新增 MCP 設定後，既有 Codex 對話尚未載入 Playwright 工具；本輪以 `scripts/testing/playwright_mcp_probe.py` 直接經 MCP stdio 協定呼叫同一個 Server 完成實測。重新啟動 Codex 或建立新對話後，仍須確認內建工具清單可使用 `browser_navigate` 等 Playwright 工具。

## 已通過

1. 官方 `https://demo.playwright.dev/todomvc`：Playwright MCP 開啟頁面、新增待辦事項、勾選完成，並擷取畫面至 `test-results/playwright-mcp/todomvc.png`。
2. 前端依賴安裝完成，`npm run build` 通過 TypeScript 與 Vite 建置。Vite 開發服務僅綁定本機介面，於 `http://127.0.0.1:5174/` 啟動，HTTP 回應 200。
3. 開發服務的 `/api` 代理轉送至本機 FastAPI `127.0.0.1:8000`。Playwright MCP 開啟登入頁、輸入一次合成無效帳號、提交表單；`POST /api/v1/auth/login` 回應預期的 401，頁面顯示「帳號或密碼錯誤」，畫面存於 `test-results/playwright-mcp/project-login.png`。
4. `test-results/`、`.playwright-mcp/`、`node_modules/`、`dist/` 已排除於 Git 追蹤；MCP 測試使用 `--isolated`，不保留瀏覽器 Session。

## 發現與未測項目

- 專案頁 Console 有兩項 Error：合成無效登入的 401 屬預期結果；`favicon.ico` 回應 404，屬現有靜態資源缺少，未影響本輪互動。
- 未以有效帳號測試登入成功、租戶選擇與登出：本輪未讀取或使用任何真實帳號憑證，也未建立測試管理員。這些流程需要安全的合成測試帳號與獨立資料狀態。
- SOP、庫存、採購、監控功能卡片仍標示「尚未實作」，無可執行的前端業務流程。
- 既有 `chrome-devtools` MCP 的 WSL 路徑問題仍在；Playwright MCP 已提供可用的瀏覽器測試途徑。

## 重現與重啟後驗證

1. 確保本機 Compose API 執行，於 `apps/web` 執行 `npm install --no-save --package-lock=false`，再執行 `npm run dev -- --port 5174`。
2. 在專案根目錄執行 `python scripts/testing/playwright_mcp_probe.py`；此腳本使用合成無效帳號，只驗證 401，不需密鑰。
3. 重啟 Codex 或建立新對話後，確認 Playwright MCP 工具已載入，請工具開啟官方 TodoMVC、操作待辦事項並擷取 Screenshot。若工具仍未顯示，檢查 `codex mcp get playwright` 與 MCP 啟動日誌。

畫面與 MCP 產生的快照、Console 紀錄為本機測試輸出，不納入 Git。
