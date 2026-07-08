# LLM 接入、智能體與 Harness 集成

本文檔說明 Hermes-Shanghanlun 的神經符號（neuro-symbolic）增益層：如何接入大
語言模型、智能體如何在保持「證據回源」鐵律的前提下自主取證作答，以及如何被
Claude Code / Codex / OpenCode（openclaw）等智能體框架調用。

## 設計哲學：LLM 只做增益，絕不繞過證據閘門

```text
┌─────────────────────────────────────────────────────────────┐
│  可信底座（確定性）                                          │
│  條文 681 · 規則 1471 · 審核閘門 6 道 · 安全治理 · BM25 RAG  │
└───────────────▲─────────────────────────────▲───────────────┘
                │ 取證(工具調用)               │ 證據核驗(citation guard)
┌───────────────┴─────────────────────────────┴───────────────┐
│  增益層（LLM，可選）                                         │
│  自然語言推理 · 更難的抽取 · 語義批評 · 多輪智能體           │
└─────────────────────────────────────────────────────────────┘
```

- LLM 產出的每一句話，回給用戶前都要過 **citation guard**：凡引用的 clause_id
  或原文引文無法在語料中核實，一律標記警告。
- LLM 抽取的每一條規則，都要過 **同一套審核閘門**（證據回源是安全網）。
- 患者語境：意圖守衛在任何模型/工具調用**之前**攔截診斷/處方/劑量請求。
- **優雅降級**：未安裝 litellm 或無 API key 時，自動使用 `local` 確定性後端，
  全系統離線可用、可測試，代碼路徑與在線完全一致。

## 啟用真實大模型

```bash
pip install "litellm>=1.40"          # 或 pip install -e ".[llm]"
export ANTHROPIC_API_KEY=sk-...       # 或 OPENAI_API_KEY 等任一 provider key
export HERMES_LLM_MODEL=anthropic/claude-opus-4-8   # 可選，默認即此
python3 -m hermes_shanghan llm-status              # 確認後端
```

支持的後端（經 LiteLLM，100+ provider）：Anthropic Claude、OpenAI、Azure、
Gemini、Groq、Mistral、DeepSeek、OpenRouter、本地 Ollama 等；另內建兩個
OpenAI 兼容網關路由：

```bash
# Azure OpenAI（litellm 原生）
export AZURE_API_KEY=... AZURE_API_BASE=https://<res>.openai.azure.com AZURE_API_VERSION=2024-06-01
export HERMES_LLM_MODEL=azure/<deployment-name>

# Poe（OpenAI 兼容端點 api.poe.com/v1）
export POE_API_KEY=...
export HERMES_LLM_MODEL=poe/Claude-Sonnet-4.5

# MiniMax（默認國際站 api.minimax.io/v1；國內站用 MINIMAX_API_BASE 覆蓋）
export MINIMAX_API_KEY=...
export HERMES_LLM_MODEL=minimax/MiniMax-M2
export MINIMAX_API_BASE=https://api.minimaxi.com/v1   # 可選
```

| 環境變量 | 作用 | 默認 |
|---|---|---|
| `HERMES_LLM_PROVIDER` | `auto`/`litellm`/`local`/`scripted` | auto |
| `HERMES_LLM_MODEL` | litellm 模型 id | anthropic/claude-opus-4-8 |
| `HERMES_LLM_TEMPERATURE` | 採樣溫度 | 0.0 |
| `HERMES_LLM_MAX_TOKENS` | 最大輸出下限（按任務自動分級提升） | 1536 |
| `HERMES_LLM_CACHE` | 磁盤緩存響應（可復現；含批量抽取/批評任務） | 1 |
| `HERMES_LLM_FALLBACK` | 調用失敗回退 `local`/`none` | local |

`auto` 僅在「litellm 已安裝 **且** 檢測到 API key」時選用真實模型，否則 `local`。

**max_tokens 按任務分級**：論文起草 ≥8192、證據綜合 ≥4096、規則抽取/批評
≥2048；`HERMES_LLM_MAX_TOKENS` 設得更高時以用戶設置為準。證據綜合把條文
**全文**（每條至多 500 字、按 clause_id 去重）交給模型，不再截斷。

## LLM 起草論文（增益層）

```bash
python3 -m hermes_shanghan paper --type formula_pattern --topic 桂枝湯類方證
python3 -m hermes_shanghan paper --type mistreatment --no-llm   # 純模板
```

`PaperWriter` 把 `data/shanghan/research/` 的計量資產（頻次表、方-證共現
網絡、家族樹、誤治傳變路徑）壓縮成摘要交給模型，起草**引言、計量結果
解讀、討論、結論**四節；模板繼續負責結構、方法學與全部數據表格。模型
文本合入稿件前過 CitationGuard：核實的 clause_id 列入文末「增益層引用
核驗」，未核實編號顯式標記「請勿採信」，`paper_meta.json` 記錄
`llm_backend` 與完整 `citation_report`。離線時 `local` 後端經同一代碼
路徑生成確定性解讀，全流程可測試。

## 智能體問答

```bash
# 自動推斷角色 + 工具取證 + 回源核驗 + 安全治理
python3 -m hermes_shanghan agent "少陰病寒化與熱化怎麼區分？" --role student
python3 -m hermes_shanghan agent "病人往來寒熱、胸脅苦滿、口苦，考慮什麼方？" --role doctor --answer-only
python3 -m hermes_shanghan agent "给我开个方" --role patient   # 被意圖守衛拒絕
```

智能體循環（在線/離線同構）：
```
system(角色契約) → user(問題) → [tool_call → tool_result]* → answer
                                          ↓
                          citation guard（核驗每個 clause_id/引文）
                                          ↓
                          safety.governed（角色化安全治理）
```

返回結構包含 `tools_used`、`evidence_clause_ids`、`citation_report`、
`reflection_rounds`、`agent_trace`（每一步工具調用與裁決），完全可審計。

## 智能體架構：反思自糾 · 複合編排 · 會話記憶

- **反思自糾**（agent.py）：答案先過 CitationGuard；含未核實編號、或有取證
  卻無引用時，裁決作為反饋回注模型，允許在有界輪數內補充取證並重答；
  仍不過關則響亮標注「請勿採信」後交付——絕不靜默。每問另設
  `max_tool_calls` 硬預算：超限後不再提供工具，強制據已有證據作答。
- **任務圖規劃**（planner.py）：複合問題不再只做句切分——對比類問題
  （「少陰寒化與熱化怎麼區分？」）自動展開為「逐對象取證（T1/T2/…）→
  依賴匯總（Tn，depends_on 全部取證任務）」的任務圖，並產出
  `success_criteria`（「必須分別覆蓋：寒化、熱化」等）；執行器按拓撲序
  派遣，匯總任務可見依賴任務的已核實證據；`criteria_check` 對最終回答做
  覆蓋審計，未覆蓋項響亮提示。方劑對比仍走 `shanghan_differential`
  專用工具（已有能力不重複展開）。
- **複合任務編排**（complex_agent.py，CLI `solve`）：每個子任務派遣一個
  ShanghanAgent，其 ToolRegistry 經 `ScopedRegistry` 裁剪到該類型所需工具
  （最小權限）→ research 型子任務改派 DeepResearcher → 綜合答覆整體再過
  一次核驗，且 `allowed_ids` 綁定各子任務證據並集——合併答案同樣
  「引用必須來自本輪取證」。`orchestrator_trace` 記錄計劃/工具域/實際調用。
- **會話記憶**（session.py，HTTP `POST /api/chat` 按 session_id 隔離）：
  跨輪累積方名錨點與已核實條文台賬；追問（「它的劑量比呢？」）自動前置
  緊湊上下文完成指代消解；複合追問自動路由到編排器。用戶糾錯
  （「不是桂枝加芍藥湯，而是桂枝去芍藥湯」）被記入 `corrections` 並持久化
  到 `correction_memory`，此後每輪上下文注入「用戶已糾正，請勿再犯」。

## 證據綁定與多假設推理（EvidenceBinder / HypothesisManager）

- **EvidenceBinder**（evidence_binder.py）：最終回答逐句拆為 claims，
  每句綁定到**本輪工具結果中出現過的** clause_id，標注
  `support_type`（direct / cited_low_overlap / inferred / ungrounded）、
  `evidence_layer`（A/B/C/D；句中出現後世病機術語如「營衛不和」一律降為
  D/E，不得冒充原文）與置信度；聚合為 `claim_grounding_rate` 隨 payload
  返回——「無證據鏈，不成回答」從答案級細化到句級。
- **HypothesisManager + 鑒別追問**（hypothesis.py，工具
  `shanghan_hypotheses`）：方證匹配不再輸出單一答案，而是並列假設——
  每個假設帶支持證據/反證/「何種表現會削弱本假設」（由互斥證對確定性
  生成，如桂枝湯之於「無汗」）/尚未確認的核心證/置信分層；top 候選評分
  接近或關鍵鑒別變量缺失時 `needs_clarification=true`，自動生成鑒別追問
  （「是『汗出』還是『無汗』？（汗出→桂枝湯；無汗→麻黃湯）」）。
  醫師/教學端回答自動附【多假設方證分析】與【鑒別追問】區塊；患者端
  永不輸出。

## 工具結果統一信封（evidence_level / confidence / 緩存 / 校驗 / 消歧）

- 每個成功的工具結果統一標注 `evidence_level`（A 原文／B 異文／C 注家／
  D 歸納／旁證）與確定性來源的 `confidence`（匹配分/發布等級/命中率，
  非模型自評），必要時附 `limitations`。
- **參數校驗與修復**：缺必填/未知參數在執行前擋下並回 schema；常見模型
  筆誤自動修復（`top_k:"3"`→3、`symptoms:"惡寒，發熱"`→列表）。
- **方名消歧**：`桂枝` → `{"ambiguous":true,"candidates":["桂枝湯","桂枝加
  桂湯",…]}`；別名（理中湯→理中丸）自動歸一並回報 `resolved_from`。
  formula_rule / dose / contraindication_check / differential 全部接線。
- **結果緩存**：同一（工具,參數）調用在註冊表生命週期內直接命中緩存
  （深拷貝隔離，`cache_hit:true` 可見），科研復現與多智能體重複取證免費。

## 全景多路檢索（omni_search）——從「查詞」到「查知識鏈」

六通道召回，每條命中標注 evidence_type，誠實與高效並重：

| 通道 | 機制 | 延遲 |
|---|---|---|
| 直接原文 | BM25+結構化（傷寒論 681 條） | <1ms |
| 本體擴展 | 44 組古籍同義詞（水腫→腫滿/浮腫/溢飲/水氣） | +幾ms |
| 語義向量 | 雙後端：HERMES_EMBED_MODEL 設定時走真神經嵌入（litellm，681 條嵌入批量計算+磁盤緩存，語料 sha 鍵控自動失效）；否則字符二元 TF-IDF 確定性兜底——失敗自動回退，絕不斷流 | +幾ms（tfidf）/ 1 次嵌入調用 |
| 現代映射 | 28 個現代疾病→表型→病機→古籍詞（A-D 等級+固定免責，不作病名等同）；附 **HPO/ICD-11 種子交叉映射**（僅收高置信；未確證顯式 verify 待核；ICD-11 第 26 章 TM1 橋接標注） | +幾ms |
| 圖譜關聯 | top 命中的條文關係鄰接 | +幾ms |
| 文獻旁證 | 笈成 800+ 部全庫**段落級檢索**（一段≈一條條文+注，穩定 pid 可回源；多詞一次調用、同段共現優先；字符倒排剪枝+硬時間預算，超時顯式 truncated） | 30-450ms |

實測（warm）：經文層多路 3-6ms；含全庫段落級通道典型 40-450ms
（骨痿+骨痹 同段共現命中《三十年臨證經驗集·填精益腎療骨疾》171ms）。
`latency_ms` 隨結果返回可回歸監控。重排為確定性加權（通道權重×BM25 歸一分
+多通道匯聚加成），無不可復現的學習排序。現代疾病問題（「骨質疏鬆在古籍中
如何對應？」）由本地路由自動走全景檢索，映射鏈與免責聲明隨答案輸出。

## 方證對應引擎（correspondence）——從「推薦方」到「證明方證關係」

八段式推理鏈（工具 `shanghan_correspondence`）：

```
症狀組合 → 病機結構(D/E,依據逐項可見) → 治法 → 候選方多維評分（透明分解）
  → 方證關係分級（原文標記推導） → 類方鑒別+追問 → 證據鏈 → 適用邊界
```

- **方證關係分級是可數的事實**：主之(143條)→A 直接方證、宜/屬→B 方症
  證據、與/可與→B- 試用性方證、無標記→D 類方歸納——由宋本處方語式
  確定性推導，每級附標記計數與示例條文，非模型判斷；
- **病機推理表**（21 條，覆蓋六經主要病機）：required/supporting/excluded
  三段匹配 + 軟飽和評分（證據越多分越高，與條目大小無關），營衛不和等
  術語一律標 D/E 後世歸納；
- **多維評分透明分解**：症狀 0.35 + 病機 0.15 + 治法 0.15 + 脈 0.10 +
  證據 0.25 − 禁忌 0.25，分項與權重隨結果返回可覆核；
- **方證畫像**（profile）：核心證/兼證/排除證（互斥證對推導）/病機候選
  （必備證+六經雙約束）/治法/關係分級/類方（同族優先）；
- **誠實邊界**：宋本無舌診主證體系——不設舌象維度並顯式聲明；現代疾病
  入口經表型映射轉譯（不作病名等同），宋本未覆蓋的後世方（腎氣丸類）
  給出 omni_search 全庫旁證指引而非硬湊候選。

## 多觀點論證引擎（perspectives）——不消滅分歧，而是結構化分歧

古籍解讀最難的不是檢索，而是條文背後的醫理、學派分歧、隱含前提與適用
邊界。工具 `shanghan_perspectives`（入口：條文號或方名）讓**七個解釋範式
並立論證**，各自產出一個結構化觀點節點：

```
觀點節點 = claim（主張）+ supporting_evidence（clause_id 證據鏈）
         + reasoning_path（論證路徑，逐步可見）+ scope（適用範圍）
         + limitation（侷限）+ layer（證據層）+ strength（強度）
```

| 範式 | 關注點 | 證據層 |
|---|---|---|
| 條文字面 | 原文症狀/方名/處方語式 | A |
| 六經辨證 | 六經定位/提綱互證 | D（錨定 A 層提綱） |
| 方證對應 | 方證關係分級（主之→A） | A（語式推導） |
| 病機醫理 | 隱含機理補全 | D/E（推斷顯式標注） |
| 藥證藥組 | 藥味角色/配伍邏輯 | D/E（推導透明） |
| 類方鑒別 | 同族方邊界 | D |
| 注家歷史 | 九注本真實注文與分歧度 | C |

- **隱含醫理補全**：症狀→機理映射表（嗇嗇惡寒→寒邪外束或陽氣不足…）
  一律標「D/E 層推斷，非條文逐字明示」——補全不冒充原文；
- **注家範式錨定真實計量**：第12條 7 家注、術語分歧度 0.9167、各家
  特徵術語（成無己重榮衛/腠理，柯琴重寒熱/胃氣）直接來自
  `commentary_divergence.json` 對齊層數據，注文摘錄 verbatim；
- **爭議仲裁不裁決**：輸出共同點/分歧點/各範式強度表/適用場景指引——
  「病機層是主要分歧點」這類元信息本身就是結論，歷史分歧結構化保留；
- **絕不硬湊**：某範式無數據（如無提綱條文可錨）即返回 None 靜默缺位，
  不生成無證據觀點；患者端硬隔離（不在 PATIENT_SAFE_TOOLS）。

路由入口：「第12條怎麼理解？」→ perspectives（問詮釋）；「第12條的原文
是什麼？」→ get_clause（問文本）；「注家對第12條有何分歧？」→
divergence_atlas（問計量圖譜）——三路互不侵佔。

## 方藥知識解析（藥解 · 方解 · 煎服法）——規則與模型各守其位

三個模塊回應「單獨一方不能佔比過高」的混合設計：

- **規則層永遠在場**：內證統計（某藥見於哪些方/劑量炮製/高頻藥對，逐條
  A 錨定 clause_id）、本草種子詞典（85 味性味功效，明確標 D 層通識）、
  方後原文逐字解析（先煮/烊化/啜粥/禁忌/強羸加減/中病即止，每字段帶
  verbatim span，A 層）、君臣佐使候選（方名藥/銖權重/調和之品——推導
  方法全程可見，標 D/E）、安全審校強制掃描（毒性/妊娠/十八反/外用識別/
  漢制劑量警示）。
- **模型層證據約束下自主判斷**（接入真模型時）：在既有藥味內覆核角色
  判定（標 E 層+理由）、撰寫方義文本（過 CitationGuard）；離線走同一
  代碼路徑的確定性模板。
- **誠實邊界**：君臣佐使原文無明文——一律標後世方論框架；現代藥理/靶點
  映射無證據庫——顯式 deferred，不憑空生成；蜜煎導等外用方硬識別，
  絕不誤作內服。

## 患者端硬隔離與紅旗分診

- **能力面隔離**（`PATIENT_SAFE_TOOLS` + `registry.for_role("patient")`）：
  患者會話拿到的註冊表**不含**方證匹配/組成/劑量/治法/禁忌檢查等工具——
  不是提示詞約束，而是工具面裁剪；ScopedRegistry 之上再裁剪同樣成立。
- **紅旗分診**（safety.red_flag_triage，先於意圖守衛）：危險徵象（高熱
  不退/呼吸困難/胸痛/神志改變/嘔血…）或重點人群（孕婦/嬰幼兒/老人）疊加
  症狀/用藥語境時，直接升級為就醫優先的分診回覆，不進入任何模型/工具
  調用；三個智能體入口（ShanghanAgent/ComplexAgent/Council）與患者教育
  端全部接線。

## 多智能體合議：獨立判斷 → 共識/分歧裁決（ConsensusJudge）

每位專家先產出**獨立結構化判斷** `{hypothesis, support, against, evidence,
confidence}`（方證專家由 HypothesisManager 供給多假設與追問）；
`ConsensusJudge`（consensus.py）按固定評分規則合議：證據直接性 0-3、條文
數量 0-2、支持覆蓋 0-3、反證衝突與安全風險扣分、完整度 0-2 →
`final_confidence` 與 `decision`（probable / probable_but_needs_more_information /
insufficient_evidence）。答覆自動附「◎ 共識 / ◎ 分歧 / ◎ 需要補充確認 /
◎ 合議置信度」區塊——方證與六經定位不一致、候選評分接近（麻黃湯 vs
大青龍湯）等衝突顯式呈現而非被單一答案掩蓋；合議最終答案的引用同樣
綁定本輪各專家取回的證據（`allowed_ids`）。

## LLM 增強的規則挖掘

```bash
# 單條：LLM 抽取候選規則 → 過全部審核閘門
python3 -m hermes_shanghan llm-extract 12

# 全量：LLM 抽取增強 + LLM 對抗式批評器（候選仍受證據閘門約束）
python3 -m hermes_shanghan pipeline --llm-extract --llm-critic
```

- `--llm-extract`：LLM 候選規則與確定性規則合併去重後，**統一過審核**。
  在 `local` 後端，LLM 鏡像規則引擎，增量為 0；真實模型才會擴大召回。
  全部 15 種條文級規則類型均開放給 LLM（異文/成注規則屬 B/C 層對齊產物，
  不經此路徑）。
- `--llm-critic`：LLM 對抗式批評器作為**附加閘門**，僅能下調等級（advisory），
  不能把證據不實的規則提升放行——硬證據閘門始終優先。

## 多智能體合議的專家評述

接入真實模型時（`available=True`），合議庭的每位專家（方證/鑒別/六經/誤治）
會基於**自己那一步的工具證據**追加一至三句評述（`💬`，時間線可見）；每句
評述先過 CitationGuard——引用了證據之外的條文編號會被就地標記
「⚠️ 含未核實條文編號」。可用 `Council(llm_specialists=False)` 關閉，
離線 `local` 後端自動跳過。

## 26 個可調用工具（智能體 / harness 共用同一能力面）

`shanghan_search`、`shanghan_get_clause`、`shanghan_match_formula`、
`shanghan_hypotheses`（多假設方證分析+鑒別追問）、
`shanghan_omni_search`（全景多路檢索：字詞+本體+圖譜+現代映射+全庫旁證）、
`shanghan_correspondence`（方證對應八段式推理：病機/評分分解/關係分級/類方）、
`shanghan_perspectives`（多觀點論證：七解釋範式並立+爭議仲裁不裁決）、
`shanghan_herb`（藥解：本草通識D+內證統計A+安全審校）、
`shanghan_formula_explain`（方解知識卡：君臣佐使透明推導D/E+配伍+方義）、
`shanghan_decoction`（煎服法：方後原文逐字解析A層+外用識別）、
`shanghan_differential`、`shanghan_six_channel`、`shanghan_formula_rule`、
`shanghan_mistreatment`、`shanghan_list_formulas`，以及十一個**研究/推理/文獻模塊**：
`shanghan_divergence_atlas`（注家分歧圖譜）、`shanghan_dose`（劑量計量）、
`shanghan_corpus_stats`（全庫統計）、`shanghan_eval_metrics`（評測指標）、
`shanghan_variants`（B層異文對勘）、`shanghan_relations`（關係圖譜遍歷，
多跳推理）、`shanghan_therapy`（治法法度）、`shanghan_contraindication_check`
（禁忌檢查：方+證候→證候衝突/原文禁例/法度禁例，複合推理）、
`shanghan_dose_convert`（漢制劑量換算計算器，確定性）、
`shanghan_case_search`（經方實驗錄醫案，旁證層+經文錨點）、
`shanghan_library`（中醫笈成全庫 800+ 部快速查閱：編目/全文/按章閱讀，
文獻旁證層；`library fetch` 一鍵自動下載）。
全部只讀、回源 clause_id；模型經 function-calling 自主選擇調用。

## 深度研究循環（deep-research）

`DeepResearcher`（`agent/research_loop.py`）實現 loop engineering：規劃器
（真模型 JSON 規劃 / local 覆蓋驅動）→ 子代理逐模塊取證並寫出引用核驗的
發現 → 批評家查六維度缺口（含醫案例證）→ 迭代收斂。產出的溯源檔案驅動
`paper --type provenance` 一鍵生成學術溯源論文（含 SVG 統計圖表）。
檔案（dossier）另含：`research_questions`（研究問題細化器把裸主題展開為
六個可回答的具體問題）、`gap_report`（每個未覆蓋維度附可執行補證建議，
如「調用 shanghan_variants 對勘桂林古本」）；每條發現的引用綁定其
**自身模塊結果**中的 clause_id（allowed_ids 逐發現核驗）。

## 智能體基準（eval/agent_bench.py，`evaluate` 默認第四套件）

| 基準 | 測什麼 | 指標 |
|---|---|---|
| routing | 問題→工具選擇 | tool_selection_accuracy / wrong_tool_rate |
| grounding | 回答級接地 | outside_evidence_citation_rate / claim_grounding_rate |
| differential | 鑒別軸覆蓋（桂枝湯vs麻黃湯須含汗出/無汗軸等） | axis_coverage_rate |
| safety | 患者端拒答/劑量泄漏/越權工具/過度拒答 | refusal_accuracy / dose_leakage_rate / unsafe_tool_rate / over_refusal_rate |

全部離線確定性運行，結果寫入 `data/shanghan/eval/agent_bench_results.json`
並匯入 `eval_summary.json`——智能體行為回歸從此有數字可盯。

```bash
python3 -m hermes_shanghan tool-call shanghan_differential --args '{"formulas":["桂枝湯","麻黃湯"]}'
python3 -m hermes_shanghan export-tools --out tools.json   # OpenAI+Anthropic 規格
```

## 接入智能體框架

### Claude Code / Claude Desktop（MCP）
```bash
claude mcp add shanghan -- python3 -m hermes_shanghan serve-mcp
```
暴露上述 26 個工具 + `shanghan_ask`（完整智能體）。MCP 服務器為純標準庫實現的
JSON-RPC over stdio，無第三方依賴。

### Codex CLI / OpenCode / openclaw（OpenAI 兼容工具）
```bash
python3 -m hermes_shanghan export-tools --out tools.json
python3 -m hermes_shanghan tool-call shanghan_search --args '{"query":"結胸"}'
```
或在 Python 函數調用循環中：
```python
from hermes_shanghan.integrations import openai_tool_specs, dispatch
tools = openai_tool_specs()
dispatch("shanghan_six_channel", {"channel": "太陽病"})
```

### 任意 LiteLLM 智能體
```python
from hermes_shanghan.agent import ShanghanAgent
print(ShanghanAgent().ask("桂枝湯與麻黃湯如何鑒別？", role="doctor")["answer"])
```

詳見 `hermes_shanghan/integrations/AGENTS.md`。

## 模塊一覽

```text
hermes_shanghan/llm/         config · cache · prompts · providers(litellm/local/scripted) · client
hermes_shanghan/agent/       tools(19+ScopedRegistry) · citation_guard · agent(ReAct+反思)
                             · complex_agent(編排) · session(會話) · research_loop(循環)
hermes_shanghan/extract/     llm_extractor（LLM 抽取，過審核閘門）
hermes_shanghan/review/      llm_critic（可選附加閘門）
hermes_shanghan/integrations/ tool_specs(OpenAI/Anthropic) · mcp_server · AGENTS.md
```
