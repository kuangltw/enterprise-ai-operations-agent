# M2-01 Storage Safety Proof（儲存安全性實證）

2026-11-13。獨立安全審查結論為 **CONDITIONAL PASS**。隔離實驗已證實晚到 PUT 可重建退役鍵，尚無可靠的寫入排空證據。正式第三切片 Cleaner DELETE 維持封鎖，工作須保持 `waiting_fence`。

## 基準與環境

- 起始 HEAD 為 `464d85e48acf33aff840e124b5f4a0810da0507f`，`main` 超前本機的 `origin/main` 六筆，工作目錄及暫存區皆乾淨。設計及既有證據見[第三切片設計](../architecture/M2-01-CLEANUP-DESIGN.md)與[第二切片獨立驗證](../development/INDEPENDENT-REVIEW-M2-01.md)。
- 現行 Migration `0010_document_retired_keys` 的複合外鍵驗證墓碑歸屬，仍可同時存在指向該鍵的有效版本。預覽是唯讀快照。Uploader 與 Recovery 共用完成流程並在交易內執行 MinIO I/O。現有 API 已停用 SDK 自動重試，尚無永久 Key Registry（鍵登錄）、共用鎖序、持久化已授權送出的 PUT attempt 或世代完成檢查。
- Docker Desktop 4.72.0、Engine 29.4.2，Linux amd64。PostgreSQL 16.15，映像 SHA256 `aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139`。MinIO `RELEASE.2025-09-07T16-13-09Z`，commit `07c3a429bfed433e49018cb0f78a52145d4bedeb`，沿用專案指定第三方 ECR 映像，SHA256 `14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`。測試容器使用快取 API 映像 `8a8292c6621a9b5cad51e0701a79808c9cb4444d152f4356eb53b48c45a10ed5` 中的 Python 3.12.16、minio-py 7.2.20、psycopg 3.3.9、urllib3 2.8.0，入口為測試腳本。
- 每輪建立專用 internal network、固定當輪服務別名、全新 PostgreSQL 與 MinIO 容器，資料放 tmpfs。無公開主機埠、既有資料掛載、Docker socket 掛載或 `.env` 讀取。MinIO 管理身分僅用於建立兩個當輪 Bucket、版本控制、測試帳號及政策。物件操作使用隨機產生憑證的非 Root 帳號。所有內容與識別均為合成資料。早期試跑將 MinIO 資料放在 `/proof-data` 的 tmpfs，映像因此還建立了未使用的匿名 `/data` Volume。正式取證兩輪改用 `/data` 的 tmpfs。

## 執行紀錄

於儲存庫根目錄執行，所需映像須已快取。

```powershell
python scripts/testing/storage_safety/run.py
python scripts/testing/storage_safety/run.py --followup
```

- 全量取證 `storage-proof-5432c392c4be9d54`，退出碼 0。下列 MinIO、外鍵、鎖競態及 COMMIT 回應證據沿用此輪結果。
- 補測 `storage-proof-257fa58f69dad42f`，退出碼 0。僅執行更新後的空表、首次登錄並行及非空降版三案、PostgreSQL backend 中斷後提交確認、主動取消 PUT，共五案。
- 補測後以 `docker ps -a --filter label=storage-safety-proof` 與 `docker network ls --filter label=storage-safety-proof` 查無本次測試資源。早期試跑留下的未使用匿名 Volume 無當輪標記，未清除任何 Volume。
- 早期兩次失敗均發生於測試程式。觀察連線尚未釋放讀鎖使 TRUNCATE 探測得到 `57014`，將觀察連線改為 autocommit 後，護欄回 `23514`。PostgreSQL 代理原先假設 `CommitComplete` 後緊接 `ReadyForQuery`，修正為繼續依協定讀取至 idle frame 後，實際截斷與重連驗證成功。
- 兩輪使用真實 TCP 連線，由測試代理注入扣住請求尾端、扣住回應或關閉 socket 的故障。另有真實 client `SIGKILL` 和 PostgreSQL backend 終止。這些結果涵蓋受控代理拓撲、半關閉及程序中止，實體網路故障、其他代理拓撲與完整已送出請求在直接斷線後的行為仍待驗。

## MinIO 與晚到寫入

同鍵交錯時，測試代理先轉送 PUT header 和第一個 body byte，保留其餘 body 及 upstream TCP。客戶端逾時並關閉 downstream TCP 後，非 Root 帳號透過另一路徑刪除舊鍵並確認 `NoSuchKey`，才放行尾端。MinIO 回 200，直接 GET 再次讀到舊鍵內容。這個順序依據代理 socket、MinIO 回應及直接觀察，DELETE 前 MinIO 何時完成授權或進入寫入處理仍未觀測。

| 實驗 | 客戶端觀察 | PostgreSQL 新連線所見 | MinIO 新連線／上游所見 |
|---|---|---|---|
| 同鍵交錯，平面 Bucket | `TimeoutError`、下游 TCP 關閉 | 世代 1 retired、世代 2 pending、工作 `waiting_fence`，舊世代 finalize 為 false | DELETE 後 `NoSuchKey`，放行尾端得 200，舊鍵復現。再 DELETE 並重複 PUT 同一內容也重建舊鍵。新鍵內容維持 `new-generation`。無 Version ID |
| 同鍵交錯，版本化 Bucket | `TimeoutError`、下游 TCP 關閉 | 同上 | DELETE 產生最新 delete marker，原版仍可依 Version ID 讀取。晚到 PUT 取得新 Version ID 並成為最新。指定刪除原 Version ID 後該版本回 `NoSuchVersion`，晚到版本仍可讀。再 DELETE 與同內容 PUT 又產生新版本。新世代內容及 Version ID 維持原樣 |
| MinIO 已接受，代理扣住回應 | `TimeoutError`、下游 TCP 關閉 | 不適用，獨立物件操作 | upstream 200，重連取得原內容及 `99f9e816-53e3-4e81-89d7-544ef443a696` |
| MinIO 已接受後終止客戶端 | `SIGKILL`、下游 TCP 關閉 | 不適用 | upstream 200，重連取得原內容及 `60883747-0644-4169-b35b-28228e15253e` |
| PUT 尚未完成時主動終止客戶端 | `SIGKILL`、下游 TCP 關閉 | 不適用 | 尾端放行前 `NoSuchKey` 且無版本，放行後 upstream 200，獨立連線讀回 `5eb00ffa-d35e-4b1b-b0d7-21fe8e4e6918` |
| 實際半關閉 upstream TCP 的寫入方向 | `TimeoutError` | 不適用 | MinIO 對未完成 body 回 499，重連 `NoSuchKey`，版本清單為空 |

兩次交錯的 Bucket 分別為 `storage-proof-5432c392c4be9d54-plain` 與 `storage-proof-5432c392c4be9d54-versioned`。完整 Object Key 為下列前綴接該列檔名。

| Bucket | Key 前綴 |
|---|---|
| 平面 | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/5cfd8b45-7310-4c95-8008-0dbb4d78bd92/89ddbff7-d7be-4918-80e9-50f124acd358/` |
| 版本化 | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/021a73a1-874d-464d-9707-14a002e1b718/f6e9e8e7-6cd9-4810-84df-2d14d235da29/` |

| Bucket | 舊鍵檔名 | 新鍵檔名 | 觀測到的 Version ID |
|---|---|---|---|
| 平面 | `1f2cc443-5b64-4b83-a7af-d00222b2544b.pdf` | `b12e2c33-8597-45b3-9191-05fe857d1667.pdf` | 無 |
| 版本化 | `5a927a14-0f29-464d-af72-8aefddbe7305.pdf` | `42c0c85d-3ce4-47b0-a795-de35478feb1e.pdf` | 原版 `88f581e0-1b1e-481c-b167-032653f62ec0`，marker `6e01db42-c9aa-492f-98b2-d9d759df1e90`，晚到 `73ef9631-cef7-4e48-8786-c8360e49bebf`，重複 `20f4971d-92b2-4803-82e3-5079eaa650b1`，新世代 `eec07170-0a66-487b-a6f6-c69b6d2d272c` |

獨立故障案的合成 Object Key 如下。

| 實驗 | Object Key |
|---|---|
| 接受後逾時 | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/395454bf-7a64-443d-a428-1a54d8641aa4/b1b631e0-cae2-4385-b5f9-5a0ec43e25a2/d756d84f-7e26-489c-ae7d-b3c21bcacb52.pdf` |
| 接受後程序中斷 | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/395454bf-7a64-443d-a428-1a54d8641aa4/b1b631e0-cae2-4385-b5f9-5a0ec43e25a2/9d648115-0120-4ea1-b5dd-55e550d7bd98.pdf` |
| 完成前主動終止，補測 Bucket | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/ad48d0bc-2a44-425a-9f8f-646b0fef95be/c48b370d-c322-4ece-9304-6cc9be436a88/8a29e158-a335-4eee-ac73-9a52531ba2a5.pdf` |
| upstream 半關閉 | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/395454bf-7a64-443d-a428-1a54d8641aa4/b1b631e0-cae2-4385-b5f9-5a0ec43e25a2/b7a7db73-8597-4574-9cc0-7ccc583c2631.pdf` |

採用每個世代永久不重用的實體鍵，可隔離已綁定舊鍵的寫入，並防止舊鍵身分重用（ABA）。版本控制保留版本歷程，晚到 PUT 仍可改變同鍵最新版本。兩者都無法證明舊鍵已排空。MinIO 文件作為行為參考，本報告的結論以指定 Community Server 映像觀察為準。 [MinIO 版本控制](https://docs.min.io/aistor/administration/objects-and-versioning/versioning/) · [MinIO 物件刪除](https://docs.min.io/aistor/administration/objects-and-versioning/object-delete/)

## PostgreSQL 不變條件

原型 SQL 位於 `scripts/testing/storage_safety`。永久登錄以 `(namespace, object_key)` 為主鍵，另限制同 namespace／tenant／document／version 的 generation 唯一。版本的生成欄位固定為 `live`，所有複合外鍵欄位非空。一般 CHECK 無法跨表維持此狀態，原型以無條件唯一約束為外鍵目標，並用觸發器保護身分與終態。測試 runtime 以非擁有者身分登入，只有讀取及兩個受控函式的權限。管理角色可改 DDL，屬管理信任邊界。 [PostgreSQL 16 約束](https://www.postgresql.org/docs/16/ddl-constraints.html) · [PostgreSQL 16 鎖定](https://www.postgresql.org/docs/16/explicit-locking.html)

| 驗證項 | 實際結果 |
|---|---|
| 版本只能引用相同歸屬與世代的 live key | 錯 tenant、document、version、generation 及直接退役仍被引用的鍵皆回 `23503`，NULL 回 `23502` |
| 終態及全域鍵唯一 | 復活、改 owner、DELETE、TRUNCATE 回 `23514`，重用舊鍵回 `23505`。runtime 的表寫入、TRUNCATE 和停用觸發器回 `42501` |
| 原子提交與冪等 | 觀察連線在提交前及回滾後未見新鍵或工作，原鍵維持 live。提交後可見新鍵、換鍵、退役及工作。相同 ID 並行等待後取回同一鍵，不同參數回 `22023`。後續再輪替仍保留先前工作結果 |
| 外鍵及版本競態 | `pg_blocking_pids` 確認外鍵引用與退役雙向實際等待，後執行的違規操作皆回 `23503`。完成先提交時換鍵拒絕，換鍵先提交時舊世代完成回 false |
| 已提交但 COMMIT 回應遺失 | 代理收到真實 `CommitComplete` 與 `ReadyForQuery(I)` 後截斷下游。客戶端 `OperationalError`，新連線依 `df6549a4-c865-4623-926b-9082fbc40ff0` 讀到工作，再以相同 ID 回傳同一替換鍵 |
| 提交前 backend 中斷 | `pg_terminate_backend` 終止測試連線後，原客戶端 `OperationalError`，新連線觀察原鍵仍 live 且無工作。用相同操作 ID 重試，再從另一條連線讀到兩鍵、換鍵及工作均已提交 |
| 降版安全 | 檢查、鎖與 DROP 置於單一 DO statement。空登錄於交易內可移除，測試隨後回滾。autocommit 降版確實等待未提交的首次登錄及換鍵，兩案提交後均回 `55000` 且保留鍵身分和已建立的工作。REPEATABLE READ 回 `22023` |

受控函式使用 READ COMMITTED（讀取已提交），依 schema gate、operation ID、版本列、鍵與工作取得鎖並以新語句檢查。這組原型只涵蓋單版本換鍵與完成的資料庫行為。尚待測試正式 Uploader／Recovery／Cleaner 的完整共同鎖序、正式 Alembic 與預覽查詢交錯、歷史鍵回填及正式降版。原型全表觀察讀取未納入 gate，空表降版與跨表讀取的鎖定交錯待驗。

## 租戶隔離

- 非 Root 帳號 A 與 B 分別由各自的 MinIO IAM 政策授予專用前綴。A 可讀寫刪除自己的物件，B 可寫入並讀回自己的內容。A 對確實存在的 B 鍵 GET／PUT／DELETE、使用格式正確但宣稱 B 歸屬的新鍵 PUT，以及匿名 GET 皆得到 `AccessDenied`。版本化 Bucket 另拒絕 A 讀取或刪除 B 的指定 Version ID 及列出該鍵版本。B 重新讀取的內容與版本歷程相同，該版本為 `d592455d-26c8-4a6b-bf7e-5cffcd6fb67c`。
- 共用合成帳號依政策可存取兩個前綴，測試實際確認它可讀取 A 與 B 的物件。現行 Compose 為 API 設定一組 MinIO 憑證和單一 Bucket，租戶與 ACL 由應用層檢查。部署時採用的 MinIO 資料面權限待驗。PostgreSQL 原型 runtime 是受信任的共用服務角色，其讀取和函式權限不構成租戶身分授權。

## 獨立審查與放行條件

初評與差異重評均命中安全架構與租戶隔離、跨系統一致性、交易與鎖、並行、冪等及復原的強制升級條件。隔離資料約束原型 +2，未修改正式 API 或三個正式模組 +0，規格明確 +0，共 2 分。Architect 完成前置與原型審查，Security Reviewer 完成前置、實測與修正重驗，角色的實際執行紀錄皆核對為 GPT-6.1 Sol High。主代理以本會話實際配置的 GPT-6.1 Sol High 整合及執行。

Security Reviewer 結論為 **CONDITIONAL PASS**。原型降版原先將護欄與 DROP 分成多個頂層 SQL，直接以 autocommit 執行時，呼叫端可能在護欄報錯後繼續送 DROP。已合併為單一 DO，重測空表、首次登錄及已有退役鍵時的降版。另補驗無須等待客戶端逾時即可主動終止 PUT 程序的情境。Security Reviewer 已核對兩輪原始工具輸出與最終測試程式，確認修正，並同意提交隔離原型與證據文件。

- Architect 實際回合 `01a1d4c6-325e-73c3-9451-79f9bbbffbbb`、`01a1d4d0-492b-7ee3-900b-08ffc76be057`、`01a1d4d6-d771-7f71-b06d-30c43a8a7fdc`。
- Security Reviewer 實際回合 `01a1d4c6-468d-7660-8a60-9a5b35a49148`、`01a1d4d0-6a1b-7531-ad04-d0a55af1fa55`、`01a1d4d6-b99f-7283-957c-5c2138021295`。

1. 先證明儲存端或網路邊界有可驗證的寫入屏障，能阻斷並排空舊鍵所有可能寫入。須涵蓋 multipart、延遲 worker、代理緩衝、重送、舊版和特權寫入。現有 10 MiB 上限搭配 SDK 預設分段，超過 5 MiB 會走 multipart，本輪只測單 PUT。 [minio-py 7.2.20 分段計算](https://github.com/minio/minio-py/blob/7.2.20/minio/helpers.py#L145-L158)
2. 將實體鍵世代綁定可信叢集與 Bucket incarnation，驗證正式資料面租戶隔離，包含共享服務身分、政策變更、ACL 撤銷及同名 Bucket 重建。若要支援版本化刪除，另驗 suspended、精確 Version ID、Object Lock 及版本保留政策。
3. 驗證正式 Migration、舊墓碑整併、完整鎖序、授權及索引入口。驗證 authoritative primary、PITR、備份還原及故障切換能保留已授權墓碑，並在恢復寫入前完成對帳。
4. 重新獨立審查正式刪除授權交易、回應不明及結果對帳。實際啟用仍須經過後續實作驗收及明確授權。

在上述放行條件解除前，第三切片正式 Cleaner DELETE 不得進入受控實作。本輪交付範圍為可重跑的隔離測試原型與驗證紀錄。
