# Codex Desktop 自主開發循環與安全檢查

> 目前本 Repository 採用 Windows 原生 Codex Desktop + Docker Desktop；不強制在 WSL2 開發。本文件是執行政策，並不代表 Codex Desktop 能在任何情況下可靠讀取官方額度百分比。

## 任務順序

以 `docs/development/PROGRESS.md` 與 `docs/testing/ACCEPTANCE.md` 為基準，從 M1-02 依序完成 M1-03、M1-04、M1-05。M1-01 已經本機驗證，避免重做。**M1 全部完成或遇到阻礙就停止，不擅自進入 M2。**

每個小任務：
1. 讀取現有規格、Git 狀態及進度。
2. 規劃可驗收的最小工作項。
3. 實作並執行必要的 Unit / Integration / Security Test。
4. 檢查 Git Diff（版本差異）、安全風險與 Regression（回歸錯誤）。
5. 針對 Staged Files（暫存檔案）執行機密掃描，通過後才 Commit（提交）。
6. 更新進度檔，保留測試指令、結果、Commit SHA 與剩餘風險。
7. 檢查停止條件，再決定是否進入下一項工作。

## 額度停止政策

- 目標保留 **至少 15%** 可用額度。
- 只有能取得官方可信數據時，才依剩餘百分比自動判斷。
- 任一適用額度剩餘 ≤ 15%、收到 Rate Limit（速率限制）或需額外付費時，停止啟動新任務。
- **無法可靠取得額度資訊時，每最多兩項小任務就停止，請使用者確認。** 不得猜測剩餘額度，也不應宣稱能在桌面版無限背景循環。
- 遇到安全風險、破壞性操作或三次修復失敗，立即停止。

## Git 與安全規則

- 允許在工作區修改、測試及建立經審查的中文 Commit。
- **禁止自動 `git push`、Force Push、`git reset --hard`、`git clean`、`docker compose down -v`。**
- 不得自行修改遠端儲存庫設定或清除歷史。
- 禁止在任何 Git 內容提交 `.env`、Token、API Key、私密金鑰、實際資料庫連線密碼、個資與公司內部資料。
- 檢測到疑似機密時停止，不把內容貼到對話或 Log；由使用者處理輪替與必要的版本歷史清除。
- 只使用 Synthetic Data（合成資料）；模型輸出不能取代後端授權。
- 重要交易需要 Approval（核准）、Idempotency（冪等性）及可復原性。
- 不得略過前置檢查，例如使用 `git -c core.hooksPath=/dev/null commit` 或 `--no-verify`。
- `.gitignore` 只防止未追蹤檔案被加入，已追蹤檔案仍需要人工檢查。

## 本機安裝與啟用（Windows PowerShell）

在專案根目錄操作：

```powershell
# 先確認 Gitleaks 已安裝且可執行
gitleaks version

# 使用 Git 內建 Hook 執行機制，不需額外 Pre-commit 套件
git config --local core.hooksPath .githooks

# 確認設置
git config --local --get core.hooksPath

# 手動執行目前暫存區掃描
python scripts/security/check_staged_secrets.py
```

Gitleaks 安裝：請參考 [官方安裝指引](https://github.com/gitleaks/gitleaks)。如果尚未安裝，Hook 會拒絕含新增／修改檔案的 Commit。Git Hook 設定屬於本機設定，`git clone` **不會自動啟用 Hook**，每台開發電腦需設定一次。

### 兩層防護

1. Local Pre-commit Hook（本機提交前檢查）：阻擋暫存內容中疑似密鑰及高風險檔名。
2. GitHub Actions（遠端持續整合）：對目前程式碼與 Git 歷史進行 Gitleaks 檢查。

**重要：GitHub Actions 會在程式碼上傳後執行，無法代替本機提交前檢查。** 安裝 Hook 前，勿讓 Codex 自動提交。即使兩層掃描均通過，也不能保證完全沒有機密，人工 Code Review（程式碼審查）仍是必要程序。

## Codex Desktop Loop 啟動提示

請遵循 `AGENTS.md` 與本文件。執行 M1-02 → M1-03 → M1-04 → M1-05 的自主開發循環。每個小任務依序執行規劃、實作、測試、Code Review、Gitleaks、Git Commit、更新 PROGRESS.md。禁止自動 Push 或破壞性操作；無法讀取可信額度時最多完成兩項小任務就暫停；任一已知剩餘額度 ≤15% 時停止。先確認本機 Hook 啟用並有可用的 Gitleaks；否則只允許非提交的檢查與安裝說明。每次停止須回報已完成項目、測試、Commit SHA、未提交變更與下一個任務。
