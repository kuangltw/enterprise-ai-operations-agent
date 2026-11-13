# M2-01 第二切片獨立驗證報告

**結論：CONDITIONAL PASS。不得開始第三切片高風險刪除實作，直到下列條件解除。**

## 範圍與基準

- 本輪範圍為獨立複驗、既有並行測試與報告；初評及差異重評均命中租戶／ACL、交易鎖、並行及復原強制升級。加分：本輪未修改 Migration 或資料約束 +0；未修改重要 API 契約或三個模組 +0；審查範圍明確 +0，總分 0，仍因強制條件由 Sol High 安全與架構角色審查。
- 審查對象及驗證時 HEAD：`1c444c61272688106dc34a5d7f6bf07770a39cb6`；經 `git merge-base --is-ancestor` 確認位於 `main` 歷史。
- 檢查 `0010_document_retired_keys.py`、`document_cleanup_preview.py`、`test_document_cleanup_preview_postgres.py`、`document_uploads.py`、`object_storage.py`、索引工作 Migration 與提交差異；另檢查現行 `.githooks/pre-commit` 和暫存掃描腳本。
- 起始工作目錄僅 `.githooks/pre-commit` 顯示修改，忽略行尾空白後無內容差異；未清除或覆蓋。`git show --check 1c444c6` 與 `git diff --check` 無錯誤。
- 新對話已完成獨立安全及架構靜態審查。子代理執行紀錄的 `session_meta` 將 `01a1d489-8b73-7c80-bae8-d038c956d974` 識別為 `security-reviewer`，其實際回合 `01a1d489-8cb0-7e33-b345-feb27619316a` 的 `turn_context` 為 `gpt-6.1-sol`／`high`；`01a1d48a-482b-7123-b498-43554f4a7562` 識別為 `architect`，實際回合 `01a1d48a-496b-76a0-a9e7-331040d150b9` 同為 `gpt-6.1-sol`／`high`。兩者均唯讀檢視本切片及新增測試，未另跑資料庫測試。前一對話的代理名額阻礙已解除。

## 測試與環境

建立新 Docker 網路及 tmpfs PostgreSQL 16／MinIO，使用合成資料及獨立非 Root MinIO 測試帳號，未連接現有服務。測試容器以目前 `requirements-dev.txt` 安裝依賴，測後移除本次容器及網路，未刪除既有 Volume。

- `alembic upgrade head` 從空白資料庫升至 `0010_document_retired_keys`，再執行一次 `alembic upgrade head`，皆成功。
- `python -m pytest -q -p no:cacheprovider tests/test_document_cleanup_preview_postgres.py tests/test_document_upload_completion_postgres_minio.py tests/test_document_upload_api.py tests/test_document_upload_reservation_postgres.py tests/test_document_upload_state_postgres.py tests/test_documents_postgres.py tests/test_document_list_postgres.py tests/test_document_status_postgres.py tests/test_document_api_postgres.py tests/test_object_storage_minio.py`：**26 passed、1 warning**。既有測試含空退役表降版後回滾、非空表拒絕降版並保留紀錄、租戶與鍵格式、預覽排除條件、PDF 與 ACL 回歸。
- 另一個全新 tmpfs PostgreSQL 中，`python -m pytest -q -p no:cacheprovider tests/test_independent_m2_concurrency_postgres.py`：**2 passed**。使用兩條連線，確認未提交的 `stored` 更新持鎖時預覽仍看到已提交的舊狀態，提交後新查詢排除；另確認未提交的退役鍵插入阻擋 `ACCESS EXCLUSIVE`，鎖逾時 SQLSTATE 為 `55P03`，插入提交後紀錄存在。測試僅覆蓋這兩個邊界，不代表完整 Uploader 或 Cleaner 競態已驗證。
- 上傳 DB commit 結果不明案例以包裝 `Session.commit` 注入例外，並非實際網路斷線。

## 架構、Migration 與安全發現

1. **High／第三切片阻擋：退役紀錄不保證鍵已脫離有效版本。** `0010_document_retired_keys.py` 只對退役表自身的 `storage_key` 設主鍵及複合外鍵；沒有約束阻止同一鍵仍為 `document_versions.storage_key`。現有 `test_preview_filters_protected_and_unowned_candidates_without_writes` 實際以版本現用鍵新增退役紀錄。此切片沒有刪除入口，預覽亦排除此情況；但後續刪除必須先以受審查的原子鍵切換及鎖內重驗，保證任何有效版本均不引用舊鍵，並處理延遲 PUT／DELETE。
2. **獨立審查結果：CONDITIONAL PASS。** 安全及架構審查均未發現第二切片唯讀功能的阻擋缺陷；其結論不構成第三切片實作、實際刪除或正式降版授權。
3. **Medium：預覽不具刪除授權。** `document_cleanup_preview.py` 明示版本建立時間不是最後活動時間，查詢不鎖資料列且可能看到進行中上傳。兩連線測試實際確認此快照行為；正式操作必須另建持久寫入意圖／最後嘗試資訊及鎖內重新驗證，不可消費預覽結果直接刪除。
4. **Medium：降版鎖順序及營運範圍待驗。** `0010` 先鎖退役表，之後移除版本表約束；若另一交易先持有版本表存取鎖、再執行預覽而等待退役表，可能與降版形成死鎖。此為靜態推論，未重現，並非宣稱單一 SELECT 必然依此順序取鎖。新增測試只執行裸 `LOCK`，未呼叫完整 Alembic 降版。仍須驗證完整交錯、中斷及資料保留，並在代表性資料量量測升級鎖定時間；正式降版未獲放行，須規劃停寫及停止預覽的維護窗口。
5. 複合外鍵與 canonical 鍵格式的既有測試拒絕錯誤租戶及格式；預覽 SQL 要求 tenant 並排除已儲存、發布、索引工作、已退役及其他版本共用鍵。未發現此切片公開物件刪除入口；未驗證完整同鍵並行 Uploader、查詢開始時新上傳、所有狀態鍵碰撞或真實網路中斷。
6. 第三切片設計須處理 READ COMMITTED 下等待資料列鎖與同一語句快照的差異：取得共同鎖後以新查詢重驗退役、發布、索引及所有引用，並以共同鎖域或約束防止其他版本插入相同鍵；單一版本列鎖不足以鎖定尚不存在的共用鍵。降版護欄亦須考量隔離等級與快照，並於無並行操作的維護窗口驗證。

## 機密與供應鏈

- Gitleaks 8.30.1 `git --log-opts='-1 1c444c61272688106dc34a5d7f6bf07770a39cb6'`：1 Commit 掃描，未發現機密；結果不等同完整歷史及所有未追蹤檔案無機密。
- `pip-audit -r requirements-dev.txt`：未發現已知漏洞；此為當次解析結果，非完整依賴鎖定與映像供應鏈驗證。
- `python -m unittest discover -s tests/security -p test_pre_commit.py -v` 首次因 Gitleaks 不在 PATH 而失敗；加入既有安裝路徑後在隔離暫存 Git 儲存庫重跑，**6 passed**。沒有繞過 Hook。
- 本報告及新增測試的暫存掃描與實際提交 Hook 結果以本次提交紀錄為準；不得包含既有 Hook 行尾差異。

## 放行條件

獨立架構與安全審查已完成；第三切片仍須先完成前置設計與審查，補足關鍵並行、Migration 中斷與失敗注入驗證，以可測試協定保障退役鍵不再被有效版本使用，並審查實際刪除的授權與鎖序。完成前不得啟動第三切片高風險刪除實作。`docs/database/SCHEMA.md` 既有文字仍稱退役鍵尚未實作：實際上資料表已存在，換鍵及退役寫入流程尚未實作；`SECURITY.md` 也有 API 狀態過時文字，應另行同步。尚未 Push。
