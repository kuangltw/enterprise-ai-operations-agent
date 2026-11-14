# M2-01 第三切片：退役鍵與清理安全設計

**狀態：清理設計提案；正式 Cleaner DELETE 未實作或驗證，也未獲授權。** 本切片新增 Migration `0011_document_key_registry` 及隔離測試；資料庫、PDF／ACL 回歸與獨立審查結果見開發進度。下文有關輪替、attempt、fencing、DELETE 與 crash recovery 的測試矩陣仍為待執行規格。`0010` 單獨不強制 Registry 不變條件；預覽不是刪除命令。

## 下一階段決策關卡：Registry 0011 與受控換鍵

- [換鍵 ADR](ADR-M2-01-KEY-ROTATION.md) 記錄 A／B 取捨及原型證據。建議以受控的同版本換鍵恢復未完成上傳。0011 本身仍禁止修改版本儲存鍵，正式能力需要獨立前向 Migration 與應用程式接線。
- 原型在一次性 0011 資料庫保留 Trigger 與外鍵，限定專用角色依序登錄新鍵、切換版本、退役原鍵並留下 `waiting_fence` 操作結果。證據涵蓋真實 COMMIT 回應遺失及鎖等待，實驗未接入現行 Uploader。
- [Key Registry 0011 專項 Workflow](../../.github/workflows/key-registry.yml) 已在本機透過隔離執行器驗證。GitHub Actions 遠端執行待 Push 後確認。
- 正式 Cleaner DELETE 持續封鎖。尚待證明寫入屏障與排空、部署角色與租戶資料面隔離、完整鎖序、備份還原及刪除授權／對帳。

## 範圍、不變條件與威脅

物件識別為受控 storage namespace／bucket 與完整 canonical key；不信任呼叫者提供的 key、租戶、預覽結果或 MinIO 回應。正式刪除僅限可信服務身分，須在後端重新授權 tenant、operation、bucket、key、owner、狀態及政策。禁止任意 key 或跨租戶清理；不向呼叫者洩露其他租戶資訊。

1. 每個仍可使用的版本，包括 `stored`、發布、待上傳及可恢復版本，其引用必須指向屬於同租戶／文件／版本及 generation 的 live key；不得引用 retired key。
2. 所有被正式刪除的 key 均永久 retired，且在刪除前後均無任何有效版本引用。key 永不重用；相同 namespace 的 key 全域唯一，不僅租戶內唯一。
3. 同一 retirement operation ID 及不可變參數重試，回傳同一持久結果或尚待對帳；同 ID 不同參數拒絕，不另行換鍵或新增刪除目標。
4. Cleaner、Uploader、Recovery 並行不能破壞有效文件；舊請求不能完成舊 generation 或令其復活。僅做 `NOT EXISTS`、版本單列鎖或依時間等待均不足以保證此條件。
5. Tenant A 的工作不得刪除 B 的物件；格式、完整 owner 與實際 namespace 均須符合。Dry Run 是快照，不具正式刪除授權。
6. PostgreSQL 已提交而 MinIO 結果不明，須保留不可變對帳紀錄，能以新連線安全恢復；未知不等於成功或失敗。

## 狀態、約束與原子切換

Migration `0011_document_key_registry` 建立永久 Key Registry（鍵登錄），以固定邏輯 namespace `documents` 與完整 storage key 作永久唯一身分，記錄 tenant、document、version、generation、狀態及退役時間。Generation 沿用 canonical key 尾端 UUID，僅作世代識別，不代表時間排序或舊寫入已排空。版本以包含完整 owner、generation 及固定 `live` 的非空複合外鍵引用登錄；資料庫觸發器在版本建立交易中登錄鍵，禁止修改版本儲存身分，並禁止 Registry 身分變更、退役後復活、DELETE、TRUNCATE。退役只可 `live → retired`。`0010` 退役資料回填至單一 Registry，舊表名改為不可自動更新的相容 View。

Migration 固定使用 `public` schema，並在 `READ COMMITTED` 及立即取得相關 ACCESS EXCLUSIVE 鎖的條件下執行。重複鍵、非 canonical key、現用鍵與墓碑衝突、舊墓碑表或欄位有明確 ACL、舊表啟用 RLS、遷移角色並非舊表擁有者等情形均 fail closed，不自動修正既有業務資料；downgrade 一律拒絕。隔離測試與獨立安全審查見 [開發進度](../development/PROGRESS.md)。

目前只完成鍵身分的資料庫基礎，沒有正式鍵輪替、恢復、Cleaner、刪除意圖或 MinIO DELETE 實作。Compose 的 API 與 Migration 仍共用資料庫特權帳號，因此不能宣稱正式服務角色已拆權。正式環境若有舊墓碑表明確 ACL，Migration 會拒絕升級，須先規劃相容處置；同名 View 的 SELECT 權限部署也仍須驗證。

複合外鍵所有欄位均 `NOT NULL`，固定 live 欄位須以 `NOT NULL` 加 CHECK 或生成欄位強制；被參照 tuple 使用無條件唯一約束，禁止以 CASCADE／SET NULL 破壞不變條件。runtime 角色不得繞過 trigger、執行 DDL 或 TRUNCATE。另對 `(namespace, old_key, old_generation)` 設唯一工作約束，避免不同 operation ID 重複處理同一代；直接 SQL 的 NULL、錯 owner／generation、狀態逆轉與撞鍵皆須測試。

僅符合清理政策的未完成版本可切換：單筆 PostgreSQL 交易依下述鎖序鎖住並以新的 READ COMMITTED 語句重新讀取；檢查 owner、狀態、發布、所有引用、索引工作、活動寫入及操作 ID；登錄全新唯一 key、以舊 key/generation 條件更新版本至新 generation、停止舊寫入意圖、將舊 key 設為 retired 並持久建立綁定原 owner/key/generation 的刪除意圖，全部提交或全部回滾。失敗時不做外部刪除。stored／發布版本或其他引用存在時拒絕；不以切換掩蓋它們。預先存在的墓碑與現用鍵衝突、重複或非正規資料須封鎖 migration 並人工處置，不能自動認定安全或刪除。

操作 ID 唯一綁定 namespace、old key、old generation 與 owner；重試攜帶預期舊世代，先查歷史並回原本的新 key／generation，不能把目前新鍵再退役。可先插入新 registry、更新版本外鍵、再退役舊 registry；外鍵與觸發器的實際可行性仍須驗證。保留版本 ID、內容摘要及上傳冪等鍵；只處理符合最後活動門檻且無索引工作的 pending／failed 版本。

鎖內另要求 document active、版本非 current、indexing pending 且無任何索引工作；所有 stored／current 切換、索引工作建立和相關有效鍵讀取必須遵循共同協定與 generation 驗證。初期同一 key/generation 同時只允許一個 armed PUT／Recovery；失聯不得以 lease 宣告終止，可符合切換資格時換鍵讓新請求前進，舊鍵繼續隔離。

健康活動中的 attempt 應拒絕輪替；已 armed 但失聯且符合政策者可輪替並隔離舊鍵，不能視作已停止。舊 generation 的 stored 與退役不可同時成功，新 generation 可在重新授權後上傳。PUT 只准持久授權的 attempt 發送，完成與索引前重驗 membership／ACL；若政策要求撤銷後立即阻斷已送出的 PUT，還需要資料面 fence，DB 重驗無法撤銷它。須測 ACL 撤銷後 stale completion／recovery 不發布、不建立索引。

狀態概念：`live → retired / waiting_fence → delete_ready → delete_unknown → deleted_verified`；明確失敗保持待處理，未知可重新對帳。`retired` 永久保留，即使已確認刪除；`deleted_verified` 只能在寫入已被可靠阻斷且對帳證明指定物件缺席後記錄。狀態與 operation ID 必須可由條件更新、唯一約束及持久稽核保護。

## 共用鎖序與交易邊界

所有業務交易先取得全域 schema gate 的 shared transaction advisory lock；新 DDL 先取 exclusive gate。之後固定依序取得認證／tenant／membership／ACL 列、預約專用 tenant/idempotency 鎖、document、version、registry key、attempt/job；同類多列依實際鎖識別排序，一次處理一個版本。後續操作不可持有 document/key 後回取 idempotency 鎖；查候選僅以非鎖定方式讀取識別，不能先持 job 鎖再反向取 version。不得假定 JOIN `FOR UPDATE` 自動按文字順序鎖列。建立新鍵透過全域唯一約束序列化，碰撞則整筆回滾換鍵，不能對不存在的列使用 `FOR UPDATE` 假裝已鎖定。所有建立引用路徑須先取得相同 document/version 鎖，資料庫外鍵及唯一約束另外防止繞過；具體鎖定、外鍵隱含鎖及跨版本路徑必須實測。若既有流程以相反順序取鎖，須先修改並驗證所有入口；發生 deadlock／serialization failure 時整筆回滾，以相同 operation ID 從頭重試並重新授權。

取得共同鎖後使用新語句重新查詢，而不是沿用等待鎖之前的語句快照；約束與所有寫入路徑鎖約定共同阻止新引用插入。不要持資料庫交易鎖跨越 MinIO 網路呼叫：交易 A 完成不可逆退役、工作及授權資料並 commit；外部呼叫後交易 B 重新上鎖與核對同一工作，再記錄結果。DB commit 回應不明時不呼叫 MinIO，使用新連線以 operation ID 查詢已提交結果；若無紀錄，以原 ID 安全重試，不能推定回滾。

Uploader／Recovery 在每次發送 PUT 前確認持久寫入 attempt（含 key、generation、attempt ID）已提交並核對授權；完成時重新取得共同鎖，以新語句檢查 registry、owner、目前 generation 和權限，失敗則不可標記 stored 或登錄索引。必須封閉旁路、舊版客戶端與未記錄的 SDK／代理透明重送，或個別記錄所有可能被受理的實體請求；舊鍵缺少完整寫入歷史時隔離。DB 鎖或 lease 到期本身無法取消已送出的 PUT，也不能 fence 已中斷連線的客戶端。

發送前 attempt 須先持久進入 `armed`，即使程序停在送出前也視為可能送出，不能因逾時、取消列或 HEAD 缺席判定未送出；尚未 armed 的準備工作才能在鎖內撤銷並禁止其後發送。任何不明 attempt 未獲儲存端可驗證排空證據時都阻止刪除。完成上傳使用 generation CAS；舊 worker 醒來的發送亦必須納入 fencing，而不僅拒絕完成交易。

`prepared` 不得送出；只有確認 `armed` commit 後才可送出，commit 不明時不得發送。重連查到 armed 仍視為可能送出，不盲目重送同一實體 attempt。受控單一 PUT 且所有實體 attempt 均有可證明終止結果時才可判定排空；任一 unknown、未納管 legacy、multipart 或代理緩衝保持 waiting_fence，除非通過可驗證的資料面屏障。測試應由 MinIO 側觀察實際 PUT／DELETE，不能僅計數應用程式呼叫。

## Delete Authorization 與外部 fencing

退役不是刪除授權。正式刪除前依共同順序取得鎖，在新語句驗證操作身分及租戶、完整 key 與 bucket 的可信配置、永久 retired、無任何版本引用、無尚可執行的舊寫入，且確認本次操作政策仍有效。提交綁定固定目標的刪除 attempt 後才呼叫 MinIO；僅確認該提交後才可發送。結果更新以 attempt ID 條件更新，舊回應不能覆寫較新結果。調度租約不阻擋晚到 DELETE；安全依賴目標不可重用及不可撤回的精確目標授權。競爭的 cleaner 以同一工作序列化；重複刪除須由明確驗證的儲存服務語意支持。

授權時間點是刪除 attempt 的 DB commit；回應不明時以 primary 上 operation ID／attempt token 與共同鎖查明，無法確認就不發送。已發出請求不能依停權或租約到期撤銷，後續新 attempt 須重新授權。namespace 必須包含可信且不因同名 bucket 重建而混淆的服務／bucket 身分；最小權限分租戶憑證或等價資料面隔離須實測，單一全 bucket 刪除憑證不能證明跨租戶隔離。維護時停止資料面執行器，gate 本身不會排空外部 I/O；不明 DELETE 保留待對帳。

流程分為 T1 退役與登錄工作、T2 重驗並提交刪除 attempt、外部 I/O、T3 對帳；T1 本身不授權 DELETE。T2 已授權而未結案一律視為可能已送出；T1、T2、T3 各自 commit 不明均須在 authoritative primary 取得共同鎖、等待原交易結束後以原識別查明，分別測試。HEAD 的 403、5xx、NoSuchBucket 或錯誤 endpoint 一律未知；versioning（含 suspended）、Object Lock 或未驗證 incarnation 預設拒絕。

操作身分須認證，tenant scope 由可信來源綁定 operation 與 owner；固定 storage cluster 和 bucket incarnation，禁止重綁或重用。隔離測試必須以 A 的資料面憑證直接嘗試刪除 B 的 prefix 並確認儲存層拒絕，不能只測資料庫檢查。恢復舊備份時須停放可能延遲的 worker，還原完整墓碑並對帳後才能重開。

**阻擋條件：**現行 MinIO PUT 逾時後可能遲到，且 DB 交易、lease、client timeout、一次 HEAD 或等待固定時間均不能證明寫入已結束。必須先選定並測試能在儲存端或網路邊界真正阻斷舊 generation 所有在途及未來寫入的 fencing 機制，並取得可驗證的排空證據；若無法證明，工作永留 `waiting_fence`，不得發送 DELETE，也不得宣稱物件已永久消失。憑證撤銷是否終止已授權在途請求、multipart、代理緩衝及服務端持久化均不可假設。禁用 bucket versioning／物件鎖或支援其精確版本及 delete marker 語意、特權寫入路徑、跨叢集複寫與存放政策也須先驗證；無法證明時禁止刪除。

墓碑及授權結果須存在具所需提交耐久性的 authoritative primary；故障切換不可回退已授權墓碑。備份還原或 PITR 回到舊狀態時先隔離寫入、發布及刪除，重建永久墓碑並完成外部對帳後才可開放；不能將歷史 key 重新指派或發布已刪內容。若無法滿足此部署前提則維持停用。

## Crash Recovery 與 Failure Matrix

| 故障點 | 安全處置 |
|---|---|
| 退役交易提交前中斷 | 回滾；原版本仍指向 live key，無刪除授權；同 ID 重新核對後重試。 |
| 提交回應遺失 | 新連線按 operation ID 查確定結果；查不到才在唯一約束下重試，不以原連線或猜測決定。 |
| 退役提交後、刪除前中斷 | 掃描持久工作，重新授權、鎖內重驗及確認 fencing，再繼續。 |
| DELETE 成功但回應遺失、逾時或連線中斷 | 標記／保留 unknown，於 fence 已證實後重新連線核對精確 namespace/key 及物件版本；缺席才記錄完成，存在則依已驗證冪等語意重試；無法判定即停止並告警。 |
| DB 結果記錄提交不明 | 以 operation ID 新連線查狀態；未知不重建新 key 或新操作。 |
| MinIO 權限錯誤、版本化或儲存端狀態不明 | 保留墓碑與工作並告警，修正環境後重驗；不得將錯誤當作不存在。 |

## Migration 與 Preview

Migration 上線前先盤點全域撞鍵、錯誤 owner、非 canonical key、現用鍵與既有墓碑衝突及所有寫入路徑；衝突封鎖並人工處置。部署需有停寫／停 worker 的維護窗口，回填與約束驗證完成後才能啟用新路徑；不得讓舊版繞過共同鎖與 registry。

現有 `0010` downgrade 先鎖墓碑表，再移除版本表約束；preview 涉及兩表，存在反向鎖序風險，現有裸鎖測試不等於完整 Alembic 驗證。正式 downgrade 必須停止 uploader、recovery、cleaner、preview 與其他相關交易，確認連線排空；保留墓碑／registry／未決工作，非空或存在不可逆退役時拒絕降版。先在隔離環境以完整 Alembic、實際 preview 交錯、中斷及代表性資料量驗證鎖順序、timeout、死鎖回滾與資料保留；不宣稱目前已驗證。

**`0011` 的降版政策更嚴格：一律拒絕，包含 Registry 空表。** 不得將永久鍵目錄降回 `0010`，因舊 Schema 無法表示完整 Generation 身分與所有新墓碑。備份／還原須使用同一一致性時間點的完整 Schema 與資料，包含 Registry、版本、約束、觸發器及部署所需 GRANT；不得將部分表的 data-only dump 附加到已有登錄觸發器的資料庫，否則可能重複登錄或遺失墓碑。PITR 回到舊時間或落後複本接手時，先隔離上傳、發布及任何清理；用可信完整歷程補齊永久鍵身分並完成對帳後才能恢復。若無法重建，維持隔離並封鎖受影響 namespace。這些是營運安全前提，尚未完成正式備份還原演練。

本切片的隔離驗證包含空庫 Migration、已存在的 `0010` Schema 與合成鍵／墓碑、衝突時回滾、鎖競爭與 ACL 相容檢查，以及一條不呼叫 MinIO DELETE 的 PDF 上傳／冪等重試／ACL 撤銷回歸。獨立 Security Reviewer 結論為 CONDITIONAL PASS，未發現本切片 Critical／High；測試通過不代表 Cleaner、fencing、正式備份還原、正式角色拆分或 DELETE 已通過驗收。

## Test Matrix（待執行）

共同斷言：每次檢查 registry／版本 owner、live 外鍵、永久墓碑、工作唯一及精確租戶物件；所有測試以隔離 PostgreSQL、MinIO、合成資料與非 root 測試帳號執行，使用 barrier 控制交錯並記錄新連線查詢結果。下表 PG／S 分別代表 PostgreSQL／MinIO；操作均是未來測試規格，並非本輪已執行。

| 案例與初始狀態 | 執行順序與預期交易 | PG 與 MinIO 不變條件／必要 assertion | 恢復方式 |
|---|---|---|---|
| 1 同鍵競態：pending、live、無索引 | U 持鍵鎖與 C 同時競爭，雙向交換先後；C 提交切換或 U 完成 stored，另一方鎖後重驗 | 只有一個勝出；stored 不退休；舊 generation 不能完成；S 中有效鍵內容不變 | 失敗方同 ID 重新查詢；未 fence 不 DELETE |
| 2 Recovery 競態：failed、有不明 PUT | R 與 C 同鍵交錯至鎖後重驗 | 無 retired 引用；R 不能復活舊鍵；S 可能有晚到物件但不得損毀有效鍵 | 舊鍵等待 fence，R 使用新 generation |
| 3 退役寫入前中斷：pending/live | 鎖後、寫墓碑前 kill 交易 | PG 回滾、原鍵 live、無工作；S 未刪除 | 同 ID 新交易重試 |
| 4 提交後刪除前中斷：retired/job | 提交後 kill worker | PG 墓碑及新鍵原子存在；S 原物件保留 | 新 worker 重驗權限及 fence |
| 5 刪除成功回應遺失：已 fence | DELETE 到達後丟棄回應 | PG unknown、不重用鍵；S 精確目標缺席且其他鍵完整；斷言不提前記完成 | 重連查證缺席並記完成 |
| 6 失敗／逾時：已 fence | 注入拒絕、逾時和稍後成功兩種結果 | PG 不誤報完成；S 未知時不假定存在或缺席；其他鍵不變 | 對帳後依證實的冪等語意重試 |
| 7 commit 不明：pending/live | 真正斷線或代理切斷 commit 回應；同時測提交與回滾 | PG 同 ID 最多一個結果，版本與墓碑不半套；未查清前 S 無 DELETE | 新連線查 ID，再安全重試 |
| 8 重複操作：已有退休工作 | 同 ID 同參數並行重試；另試不同參數 | PG 一筆操作、一個新 generation；不同參數拒絕；S 不影響其他鍵 | 回原結果或等待對帳 |
| 9 有效引用：stored／發布或另一版本引用 | C 加鎖後重驗 | PG 拒絕退休及刪除意圖；S 有效物件不變；斷言無 DELETE | 保留版本，調查異常引用 |
| 10 跨租戶撞鍵：A 與 B 試用同 namespace/key | B 插入／操作與 A 清理交錯 | PG 全域唯一或 owner 約束拒絕；C 不洩露 B；S B 物件不變 | 隔離衝突並人工處理 |
| 11 Preview／Downgrade：0010 存在及非空、空表各測 | 完整 Alembic 與真實 preview 以兩連線分別先取得不同表鎖，含中斷 | PG 不丟墓碑，非空拒絕；有限 timeout／死鎖回滾；S 無操作 | 停止相關連線後維護窗口重試 |
| 12 真網路斷線：隔離服務與已提交工作 | 以網路代理實際切斷並恢復 PG、MinIO，各測請求前／途中／回應時 | PG 操作唯一、無半套；S 不損毀其他物件；斷言 unknown 與重新連線對帳 | 確認 fence 後新連線對帳，不能以 mock 取代 |

另須測舊 PUT 在 timeout／程序死亡後晚到、fence 前後的在途 PUT 與 multipart、兩 cleaner 同時處理、錯誤 bucket／路徑、直接 SQL 違反外鍵、操作 ID 衝突、DB 失聯持鎖釋放、不同隔離等級及 migration 回填衝突。測試必須證明 fence 的真實邊界，否則僅驗證 fail-closed。

特別以兩連線及 barrier 驗證：候選讀取後另一交易先完成 stored／index，Cleaner 鎖後新語句必須拒絕；切換後舊 generation finalize 無效；worker 在 armed commit 後、實際發送前暫停，DB 失鎖後醒來仍不得提前刪除。真實網路切斷須區分伺服器未處理、已處理但 ACK 遺失及舊請求仍在途，並由獨立 observer 確認。

## 已知限制與放行條件

本設計尚未選定或驗證足以排空在途 PUT 的 fencing；正式儲存服務語意、輪替／清理的完整鎖序、維護操作及上述測試均待驗。`0011` 已提供鍵登錄約束，但既有業務程式尚未採用未來清理所需的共同鎖與輪替協定。必須完成清理功能的獨立安全審查，解決 Critical／High，完成隔離並行、故障、真實斷線與正式部署驗證；在此之前不得進入正式刪除功能實作或啟用刪除。
