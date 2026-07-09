# 智能體路線圖（評審建議的採納狀態與規劃）

外部評審提出 14 個智能體建議（A1–A5 證據溯源類、B6–B9 方證辨證類、
C10–C12 方藥知識類、D13–D14 注家學派類）。本文檔記錄逐項處置：
**A 組與 C10/C11 已落地**；B/D 組屬臨床交互與裁決類產品能力，體量與
安全審查要求高，列入規劃並標明現有部分能力，不倉促上線。

## 已落地（本輪）

| # | 建議 | 落點 |
|---|---|---|
| A1 | Scope Consistency Auditor | `trace-audit-scope`：三 scope 輸出全文遞歸掃描違例，CI 可跑（`scientometrics.audit_scope_consistency`） |
| A2 | Citation Evidence Auditor | `trace-audit-citation --book X --clause N`：逐邊給出模式/最長片段/覆蓋率/歸屬歧義/套語邊界/斷章風險提示/轉引標記 + 確定性可靠性分級 |
| A3 | Quotation Gold-standard Builder | `trace-gold-sample --n 50 --out gold.csv`（確定性等距抽樣+算法預測列）→ 人工標註 → `trace-gold-eval --file gold.csv`（P/R/F1 + 模式一致率 + 分歧樣本） |
| A4 | Misquotation Detection | `trace "營衛不和，桂枝湯主之" -t quote`：逐片段判定原文逐字/後世歸納語，關聯方證觀點庫與 A 層相關表述，整句給直引可否結論 |
| A5 | Claim Lineage | claims.json 增補 `first_proponent`（最早可見注家，以在庫注本為限）與 `term_first_use`（各術語首現注家/朝代） |
| C10 | 藥解 | `herb 桂枝`：出現方劑/條文/劑量寫法/配伍共現網絡；**不編造藥性解釋**（本草層未隨庫，如實聲明） |
| C11 | 方解 | `formula-explain 桂枝湯`：首見/方證/組成劑量比/煎服/禁忌/類方鑒別/方名傳播/觀點分級一站式 |

## 規劃中（B/D 組：需要獨立迭代與安全評審）

| # | 建議 | 現有部分能力 | 評估與規劃 |
|---|---|---|---|
| B6 | 四診信息採集 | 患者端意圖守衛與就診信息整理（`apps/patient.py`）；實體抽取器可識別症狀/脈象/病程 | **合理，優先級最高**。需新增：結構化四診 schema（主訴/病程時間線/寒熱汗渴二便腹證舌脈/誤治史）、缺失信息追問生成。患者端嚴格限「就診信息整理」，方證匹配僅醫師端——沿用既有硬隔離 |
| B7 | 方證多假設裁決 | `shanghan_hypotheses` 已有並列假設+支持/反證/缺失關鍵證+鑒別追問 | **合理**。差距在「裁決層」：傾向 A/B/不能裁決三態輸出 + 3 個關鍵補問。可基於 `agent/hypothesis.py` 擴展，複用 `consensus.py` 裁決機制 |
| B8 | 方證衝突審計 | `shanghan_contraindication_check`（方+證候→衝突/禁例）已覆蓋大半；匹配器對 negated_findings 有懲罰 | **合理**。差距：衝突強度分級與「改判建議」。宜作為 contraindication_check 的增強版而非新智能體，避免能力面重複 |
| B9 | 誤治傳變路徑模擬 | `shanghan_mistreatment` 有 60 條誤治→變證→救治路徑（含條文依據） | **合理**。差距：多步動態模擬（誤治鏈式傳變）與圖形化。規則已成圖（ClauseRelation mistreatment_transformation 邊），需路徑搜索 + Web UI 呈現 |
| C12 | 煎服法智能體 | FormulaBlock 已結構化 preparation/administration/post_notes；方證規則含 administration_notes | **合理**。差距：服後觀察/中病即止/調護的規則化抽取 + 患者端脫敏解釋（「現代不可直接執行」提示涉醫療安全，需審慎措辭） |
| D13 | 注家爭議裁決 | 分歧圖譜有爭點條文榜/一致度矩陣/指紋；`commentator_chain` 有學派歸屬與被轉引樞紐度 | **部分合理**。「裁決」措辭與「多觀點並存不裁決」原則衝突——改為「爭議結構化呈現」：分歧類型標註（訓詁/方證/病機/治法）可由注文術語剖面確定性分類；「貼近原文程度」可用注文與條文的逐字重合率計算。列入下輪 |
| D14 | 學派比較 | `school_chain` + 一致度矩陣 + 指紋 + 引文網絡差異均已可查 | **大半已具備**。差距：兩注家/兩學派的對照報告模板（把現有六類資產拼成一份對比文檔），適合作 `paper --type school_compare` 論文類型 |

## 設計約束（所有後續智能體一體遵守）

1. 無證據鏈不成回答：新智能體輸出必須攜帶可核驗 clause_id；
2. 原文直述/後世歸納分層：D13/D14 的任何「裁決」只呈現證據結構，不判對錯；
3. 患者端硬隔離：B6 四診採集在患者端僅作信息整理，禁入方證匹配；
4. 確定性優先：能用規則與計量實現的不依賴 LLM；LLM 僅作增益層且過引用核驗。
