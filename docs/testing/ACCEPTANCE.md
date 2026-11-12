# Acceptance Tests（驗收測試）與 Release Gate（發布門檻）v0.1

> **目前全是規劃測試，尚未執行。** 指標為專案初始目標，不能視為已達成的效能或品質成果。

## 1. 測試層級

- Unit Test（單元測試）：庫存公式、權限政策、狀態轉換。
- Contract Test（契約測試）：FastAPI 與 ASP.NET Core Demo ERP 的 OpenAPI、Request／Response 及錯誤碼。
- Integration Test（整合測試）：PostgreSQL、Outbox、Qdrant ACL、Object Storage（物件儲存）。
- E2E Test（端對端測試）：文件上傳至來源引用、ERP 分析、採購草稿核准至安全寫入。
- Security Test（安全測試）：跨 Tenant（租戶）、Prompt Injection（提示詞注入）、Tool Authorization（工具授權）。
- Reliability Test（可靠性測試）：Worker 中斷、Timeout、ERP 寫入結果不明、Checkpoint 恢復。

## 2. SOP Knowledge（知識問答）

| ID | 測試情境 | 預期結果 |
|---|---|---|
| RAG-T01 | 上傳正常 PDF | 文件建立且索引任務排入佇列 |
| RAG-T02 | 重複上傳同 SHA256 | 依去重規則不產生非預期重複版本 |
| RAG-T03 | 上傳新版本 | 新索引 Ready 後才切換可查詢版本 |
| RAG-T04 | 查詢有來源的 SOP | 回答與有效 Citation（引用來源） |
| RAG-T05 | 查詢不存在的規範 | 標記 `insufficient`，不得虛構引用 |
| RAG-T06 | 查詢無 ACL 權限文件 | 不洩漏內文、摘要或 Metadata |
| RAG-T07 | Tenant A 查詢 Tenant B 文件 | 不回傳跨租戶資料 |
| RAG-T08 | 文件夾帶 Prompt Injection | 不執行未授權工具指令 |
| RAG-T09 | 生成期間撤銷權限 | 回傳前重新檢查權限 |
| RAG-T10 | Qdrant 不可用 | 回報依賴服務異常，不捏造答案 |

Evaluation Dataset（評估資料集）至少 100 題：60 題直接查詢、20 題跨文件、10 題無答案、10 題權限／攻擊測試。建議初始門檻：Recall@5 ≥ 85%、Citation Correctness（引用正確率）≥ 95%、Abstention Accuracy（無答案拒答正確率）≥ 95%。公開資料版本、實際分子／分母、模型設定及失敗案例。

## 3. 庫存與銷售分析

| ID | 測試情境 | 預期結果 |
|---|---|---|
| ERP-T01 | 查詢授權倉庫 | 只回傳授權範圍 |
| ERP-T02 | 最近 30 天銷量彙總 | 與 C# ERP 測試資料基準一致 |
| ERP-T03 | 有未到貨採購單 | 庫存部位只加計一次 |
| ERP-T04 | 銷售數量為零 | 不除零、不捏造需求 |
| ERP-T05 | 有 MOQ 與 Pack Size | 正確進位 |
| ERP-T06 | ERP Read API Timeout | 有上限的重試與可觀測錯誤 |
| ERP-T07 | Agent 呼叫未知 Tool | Registry 拒絕 |
| ERP-T08 | 未授權倉庫 ID | C# ERP 與 Agent 執行層拒絕 |

## 4. 採購核准與交易

| ID | 測試情境 | 預期結果 |
|---|---|---|
| APR-T01 | 產生採購草稿 | 正確建立版本與明細 |
| APR-T02 | Staff 嘗試核准 | HTTP 403 |
| APR-T03 | Manager 核准有效草稿 | Outbox 建立且排入 ERP 任務 |
| APR-T04 | 兩人同時核准 | 僅一筆決策成功 |
| APR-T05 | 重複送出核准／重試 | 不重複建立 ERP 採購單 |
| APR-T06 | 核准後庫存或價格改變 | 標記 Stale，阻止寫入 |
| APR-T07 | ERP 已提交但回應 Timeout | 先用冪等鍵對帳，不重複建立 |
| APR-T08 | 寫入中停止 Worker | 恢復後維持單一業務效果 |
| APR-T09 | 修改已核准草稿 | 核准失效，重新送審 |
| APR-T10 | 建議單建立人自行核准 | 依職責分離政策拒絕 |

ASP.NET Core Demo ERP 需具備 Transaction（交易）、Unique Constraint（唯一約束）及依冪等鍵查詢結果的 Contract Test，不能只依賴 Python 端避免重複提交。

## 5. Agent Monitoring（執行監控）

| ID | 測試情境 | 預期結果 |
|---|---|---|
| OBS-T01 | 建立 Run | 唯一 Run ID 與 Trace ID |
| OBS-T02 | 多節點執行 | 可追蹤排序後的節點事件 |
| OBS-T03 | LLM 呼叫失敗 | 記錄錯誤類型與節點 |
| OBS-T04 | Agent 等待人工核准 | 等待時間與執行延遲分開計算 |
| OBS-T05 | 呼叫 ERP Tool | 記錄耗時、工具名稱與狀態 |
| OBS-T06 | 查詢 Token 與費用 | 與資料集預期值一致 |
| OBS-T07 | 讀取其他人的私有 Run | 無權限者無法存取 |
| OBS-T08 | Tool 回應含機密 | Log／Trace 不保存機密原文 |

## 6. 初始營運目標（尚未實測）

| 指標 | 初始目標 | 備註 |
|---|---|---|
| API Availability（可用率） | ≥ 99.5% | 需另訂量測期間 |
| SOP 一般查詢 P95 Latency（延遲） | ≤ 10 秒 | 排除人工核准等待 |
| Recall@5 | ≥ 85% | 固定標註資料集 |
| Citation Correctness | ≥ 95% | 引用需能查回實際原文 |
| 跨租戶非法讀取 | 0 筆 | 執行對抗測試 |
| 無效核准造成採購寫入 | 0 次 | E2E 不變條件 |
| 同一冪等鍵重複採購 | 0 筆 | 包含 Timeout-after-commit |

## 7. M1–M6 工作拆分

| Milestone（里程碑） | 主要工作 | 完成條件 |
|---|---|---|
| M1：環境與安全 | Docker、FastAPI、React、Identity、Migration、CI | 可啟動且具租戶隔離 |
| M2：RAG | 匯入、切分、Embedding、混合檢索、引用 | SOP 問答通過測試 |
| M3：ERP 與 Agent | **C# ASP.NET Core Demo ERP**、EF Core、OpenAPI、LangGraph | 可重現庫存分析結果 |
| M4：採購 | 草稿、規則、核准、Interrupt、Outbox、冪等寫入 | 安全完成一次採購交易 |
| M5：監控 | OpenTelemetry、Dashboard、故障與安全測試 | 可追蹤且可安全恢復 |
| M6：發布 | README、Demo Data、E2E、License、Release | 外部開發者可重現示範 |

## 8. v0.1.0 發布檢核

- [ ] `docker compose up` 可從乾淨環境啟動。
- [ ] Alembic 與 EF Core Migration 正常執行。
- [ ] Synthetic Data（合成資料）可重建。
- [ ] 四項 MVP 的 E2E 測試通過。
- [ ] 跨租戶、ACL、核准授權測試通過。
- [ ] ERP 冪等、Timeout-after-commit、Worker 故障恢復測試通過。
- [ ] RAG Evaluation（評估）公開方法與實際數據。
- [ ] FastAPI 與 ASP.NET Core OpenAPI Contract 驗證通過。
- [ ] README 有正確部署說明且 Demo 不包含真實企業資料。
- [ ] CI（持續整合）全部通過，無已知 Critical（重大）問題。

預估排程不是交付承諾；安全性、資料一致性及可驗證性優先。
