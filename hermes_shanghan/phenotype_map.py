"""現代表型 → 古籍病證映射（跨時代檢索橋，候選映射不作病名等同）.

科學邊界（回應方案 §13，全部落實為數據結構而非空話）：
  * 每條映射帶 **grade**：A 症狀高度一致 / B 病機或表型部分一致 /
    C 機制相關但病名不等同 / D 僅為研究假設；
  * 每條映射帶固定 **disclaimer**：古籍病名與現代疾病不能機械等同——
    映射僅用於知識發現與輔助檢索；
  * 經此通道召回的條目一律標 evidence_type=現代映射（D 層），
    絕不冒充直接原文證據。

詞表為人工精選，覆蓋《傷寒論》與笈成全庫語境下最常被問到的現代問題。

標準詞表對接（HPO / ICD-11）：CODES 表提供精選種子交叉映射——
  * HPO（Human Phenotype Ontology，hpo.jax.org）：表型級標準詞條；
  * ICD-11（WHO）：疾病編碼，部分僅到 block 級精度；ICD-11 第 26 章
    傳統醫學模塊（TM1）收錄中醫病證分類，作為橋接錨點標注但不虛構碼值；
  * 只收錄高置信條目；未確證的編碼顯式標 verify（待人工核對官方發布），
    寧缺毋錯——科研使用前請對照 HPO/ICD-11 官方最新版本核驗。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .textutil import normalize_query

DISCLAIMER = ("古籍病名與現代疾病不能機械等同：本映射僅列出在症狀/病機/表型層面"
              "存在相似性的候選古籍表達，供知識發現與檢索使用，須經臨床表型、"
              "病機語義與文獻證據進一步驗證。")

# modern → {aliases, phenotypes(現代表型), tcm_semantics(病機語義),
#           classical_terms(古籍病證/檢索詞), methods_hint(治法方向), grade}
PHENOTYPE_MAP: Dict[str, Dict] = {
    "感冒": {"aliases": ["上呼吸道感染", "流感", "流行性感冒"],
             "phenotypes": ["發熱", "惡寒", "鼻塞", "頭痛", "咳嗽"],
             "tcm_semantics": ["風寒束表", "風熱犯衛", "表證"],
             "classical_terms": ["傷寒", "中風", "溫病", "發熱", "惡寒", "頭痛"],
             "methods_hint": ["解表", "發汗", "辛涼解表"], "grade": "A"},
    "骨質疏鬆": {"aliases": ["骨質疏鬆症", "骨質疏松", "骨质疏松", "低骨量", "骨密度下降"],
                 "phenotypes": ["骨痛", "腰背痛", "易骨折", "身高變矮"],
                 "tcm_semantics": ["腎虛", "精虧", "髓減", "骨失所養", "肝腎不足"],
                 "classical_terms": ["骨痿", "骨痹", "骨枯", "虛勞", "腰痛", "腰脊痛"],
                 "methods_hint": ["補腎", "填精", "強筋壯骨"], "grade": "B"},
    "肌少症": {"aliases": ["肌肉減少", "肌肉萎縮", "肌力下降"],
               "phenotypes": ["肌肉消瘦", "乏力", "四肢無力"],
               "tcm_semantics": ["脾虛", "氣虛", "肝腎不足"],
               "classical_terms": ["肉痿", "痿證", "虛勞", "羸瘦", "四肢不用"],
               "methods_hint": ["健脾", "益氣", "補肝腎"], "grade": "B"},
    "糖尿病": {"aliases": ["高血糖", "2型糖尿病", "血糖高"],
               "phenotypes": ["多飲", "多尿", "多食", "消瘦", "乏力"],
               "tcm_semantics": ["陰虛燥熱", "津傷", "腎虛"],
               "classical_terms": ["消渴", "消癉", "渴欲飲水", "小便數"],
               "methods_hint": ["清熱生津", "滋陰", "益氣"], "grade": "B"},
    "銀屑病": {"aliases": ["牛皮癬"],
               "phenotypes": ["紅斑", "鱗屑", "瘙癢", "皮膚增厚", "反覆發作"],
               "tcm_semantics": ["血熱", "血燥", "血瘀", "風熱"],
               "classical_terms": ["白疕", "乾癬", "松皮癬", "風癬", "蛇蝨"],
               "methods_hint": ["清熱涼血", "養血潤燥", "活血化瘀"], "grade": "B"},
    "血栓": {"aliases": ["靜脈血栓", "血栓形成", "栓塞", "深靜脈血栓"],
             "phenotypes": ["局部腫脹", "脹痛", "血流不暢", "活動後加重"],
             "tcm_semantics": ["血瘀", "氣滯血瘀", "絡阻"],
             "classical_terms": ["瘀血", "蓄血", "血結", "脈痹", "血痹"],
             "methods_hint": ["活血化瘀", "行氣通絡"], "grade": "C",
             "safety_note": "涉及血栓/抗凝藥/出血風險時，古籍檢索僅用於知識發現，"
                            "不能替代現代血栓規範治療"},
    "冠心病": {"aliases": ["心絞痛", "心肌缺血"],
               "phenotypes": ["胸痛", "胸悶", "心悸", "氣短"],
               "tcm_semantics": ["胸陽不振", "痰瘀互結", "氣滯血瘀"],
               "classical_terms": ["胸痹", "心痛", "心痛徹背", "短氣"],
               "methods_hint": ["宣痹通陽", "活血", "化痰"], "grade": "C"},
    "高血壓": {"aliases": ["血壓高", "高血压", "血压高"],
               "phenotypes": ["頭暈", "頭痛", "面赤", "耳鳴"],
               "tcm_semantics": ["肝陽上亢", "肝風", "陰虛陽亢"],
               "classical_terms": ["眩暈", "頭眩", "頭痛", "肝風", "中風"],
               "methods_hint": ["平肝潛陽", "滋陰"], "grade": "C"},
    "失眠": {"aliases": ["睡眠障礙", "入睡困難"],
             "phenotypes": ["入睡難", "易醒", "多夢", "心煩"],
             "tcm_semantics": ["陰虛火旺", "心腎不交", "胃不和"],
             "classical_terms": ["不得眠", "不得臥", "虛煩不得眠", "目不瞑", "不寐"],
             "methods_hint": ["清心除煩", "滋陰", "和胃"], "grade": "A"},
    "焦慮抑鬱": {"aliases": ["焦慮", "抑鬱", "抑郁", "情緒低落", "驚恐"],
                 "phenotypes": ["心煩", "驚悸", "善太息", "咽中異物感"],
                 "tcm_semantics": ["肝鬱", "氣鬱", "心膽氣虛"],
                 "classical_terms": ["臟躁", "百合病", "梅核氣", "驚悸", "煩驚", "奔豚"],
                 "methods_hint": ["疏肝解鬱", "養心安神"], "grade": "B"},
    "類風濕關節炎": {"aliases": ["關節炎", "風濕", "關節腫痛", "类风湿", "类风湿关节炎", "风湿"],
                     "phenotypes": ["關節疼痛", "腫脹", "晨僵", "變形"],
                     "tcm_semantics": ["風寒濕痹", "濕熱痹阻", "肝腎虧虛"],
                     "classical_terms": ["痹", "歷節", "白虎歷節", "骨節疼痛", "風濕"],
                     "methods_hint": ["祛風除濕", "溫經通絡", "補肝腎"], "grade": "B"},
    "痛風": {"aliases": ["高尿酸", "痛风"],
             "phenotypes": ["關節紅腫熱痛", "夜間痛甚", "反覆發作"],
             "tcm_semantics": ["濕熱下注", "濁瘀痹阻"],
             "classical_terms": ["歷節", "白虎歷節", "腳氣", "痹"],
             "methods_hint": ["清熱利濕", "通絡止痛"], "grade": "B"},
    "哮喘": {"aliases": ["支氣管哮喘", "氣道高反應"],
             "phenotypes": ["喘息", "氣促", "喉中痰鳴", "咳嗽"],
             "tcm_semantics": ["痰飲伏肺", "風寒束肺", "腎不納氣"],
             "classical_terms": ["喘", "上氣", "咳逆倚息", "哮", "痰飲"],
             "methods_hint": ["宣肺平喘", "溫化痰飲", "納氣"], "grade": "A"},
    "慢性胃炎": {"aliases": ["胃炎", "消化不良", "胃脹"],
                 "phenotypes": ["胃脘脹滿", "噯氣", "納差", "嘈雜"],
                 "tcm_semantics": ["脾胃虛弱", "肝胃不和", "寒熱錯雜"],
                 "classical_terms": ["心下痞", "痞滿", "胃脘痛", "噫氣", "不能食"],
                 "methods_hint": ["健脾和胃", "辛開苦降"], "grade": "B"},
    "便秘": {"aliases": ["排便困難"],
             "phenotypes": ["大便乾結", "排便費力", "腹脹"],
             "tcm_semantics": ["腸燥津虧", "胃腸實熱", "氣虛"],
             "classical_terms": ["不大便", "大便難", "大便硬", "燥屎", "脾約"],
             "methods_hint": ["潤腸", "瀉下", "益氣"], "grade": "A"},
    "腹瀉": {"aliases": ["急性腸炎", "慢性腹瀉", "腹泻"],
             "phenotypes": ["大便稀溏", "次數增多", "腹痛"],
             "tcm_semantics": ["脾虛濕盛", "腎陽虛", "傷食"],
             "classical_terms": ["下利", "泄瀉", "自利", "下利清穀", "飧泄"],
             "methods_hint": ["健脾滲濕", "溫腎", "澀腸"], "grade": "A"},
    "水腫": {"aliases": ["浮腫", "腎性水腫", "心源性水腫", "水肿"],
             "phenotypes": ["面目浮腫", "下肢腫", "尿少"],
             "tcm_semantics": ["脾虛水泛", "腎陽虛", "水濕內停"],
             "classical_terms": ["水腫", "腫滿", "水氣", "溢飲", "風水", "皮水"],
             "methods_hint": ["利水滲濕", "溫陽化氣", "健脾"], "grade": "A"},
    "尿路感染": {"aliases": ["膀胱炎", "尿頻尿急尿痛"],
                 "phenotypes": ["尿頻", "尿急", "尿痛", "小便黃赤"],
                 "tcm_semantics": ["濕熱下注", "膀胱濕熱"],
                 "classical_terms": ["淋", "淋證", "小便不利", "小便難", "血淋"],
                 "methods_hint": ["清熱利濕", "通淋"], "grade": "A"},
    "偏頭痛": {"aliases": ["頭痛", "血管性頭痛", "偏头痛"],
               "phenotypes": ["一側頭痛", "搏動性痛", "畏光", "噁心"],
               "tcm_semantics": ["肝陽", "風痰", "瘀血阻絡"],
               "classical_terms": ["頭痛", "偏頭風", "首風", "腦風"],
               "methods_hint": ["平肝", "祛風", "活血"], "grade": "B"},
    "眩暈症": {"aliases": ["眩暈", "美尼爾", "梅尼埃", "耳石症", "眩晕"],
               "phenotypes": ["天旋地轉", "噁心嘔吐", "耳鳴", "站立不穩"],
               "tcm_semantics": ["痰飲上犯", "肝陽上亢", "氣血虧虛"],
               "classical_terms": ["眩暈", "頭眩", "眩冒", "冒眩", "支飲"],
               "methods_hint": ["化飲", "平肝", "補益氣血"], "grade": "A"},
    "心律失常": {"aliases": ["心悸", "早搏", "心動過速"],
                 "phenotypes": ["心慌", "心跳不齊", "胸悶"],
                 "tcm_semantics": ["心陽不足", "氣血兩虛", "水飲凌心"],
                 "classical_terms": ["心動悸", "心下悸", "驚悸", "怔忡", "脈結代"],
                 "methods_hint": ["溫通心陽", "益氣養血", "復脈"], "grade": "A"},
    "貧血": {"aliases": ["血虛", "面色蒼白", "贫血"],
             "phenotypes": ["面色萎黃", "乏力", "頭暈", "心悸"],
             "tcm_semantics": ["氣血兩虛", "脾不生血"],
             "classical_terms": ["血虛", "虛勞", "萎黃", "亡血"],
             "methods_hint": ["補氣生血", "健脾"], "grade": "B"},
    "痛經": {"aliases": ["月經痛", "經行腹痛", "痛经"],
             "phenotypes": ["經期小腹痛", "血塊", "得溫則減"],
             "tcm_semantics": ["寒凝血瘀", "氣滯血瘀", "衝任虛寒"],
             "classical_terms": ["經水不利", "帶下", "少腹急結", "瘀血"],
             "methods_hint": ["溫經散寒", "活血調經"], "grade": "B"},
    "更年期綜合徵": {"aliases": ["更年期", "圍絕經期", "更年期综合征"],
                     "phenotypes": ["烘熱汗出", "煩躁", "失眠", "情緒波動"],
                     "tcm_semantics": ["腎陰虛", "陰虛火旺", "肝鬱"],
                     "classical_terms": ["臟躁", "百合病", "虛煩", "盜汗"],
                     "methods_hint": ["滋腎", "清熱除煩", "甘潤緩急"], "grade": "B"},
    "濕疹": {"aliases": ["特應性皮炎", "皮炎", "湿疹"],
             "phenotypes": ["皮膚瘙癢", "滲出", "紅斑", "反覆發作"],
             "tcm_semantics": ["濕熱蘊膚", "血虛風燥"],
             "classical_terms": ["浸淫瘡", "濕瘡", "身癢", "風癢"],
             "methods_hint": ["清熱利濕", "養血祛風"], "grade": "B"},
    "慢性疲勞": {"aliases": ["疲勞綜合徵", "亞健康", "乏力", "慢性疲劳"],
                 "phenotypes": ["持續疲乏", "勞則加重", "精神不振"],
                 "tcm_semantics": ["氣虛", "脾虛", "勞倦內傷"],
                 "classical_terms": ["虛勞", "勞倦", "四肢倦怠", "少氣"],
                 "methods_hint": ["補中益氣", "甘溫除熱"], "grade": "B"},
    "炎症": {"aliases": ["感染", "紅腫熱痛"],
             "phenotypes": ["紅", "腫", "熱", "痛"],
             "tcm_semantics": ["熱毒", "濕熱", "瘀熱"],
             "classical_terms": ["熱毒", "癰腫", "瘡瘍", "紅腫熱痛"],
             "methods_hint": ["清熱解毒", "涼血消腫"], "grade": "C"},
}

# —— 標準詞表交叉映射（精選種子；status: curated=高置信 / verify=待核） ——
CODES: Dict[str, Dict] = {
    "感冒": {"icd11": {"code": "CA00", "title": "Common cold", "status": "curated"},
             "hpo": [{"id": "HP:0001945", "label": "Fever 發熱"},
                     {"id": "HP:0012735", "label": "Cough 咳嗽"}]},
    "骨質疏鬆": {"icd11": {"code": "FB83", "title": "Osteoporosis（block 級）",
                           "status": "curated"},
                 "hpo": [{"id": "HP:0000939", "label": "Osteoporosis 骨質疏鬆"},
                         {"id": "HP:0002653", "label": "Bone pain 骨痛"}]},
    "肌少症": {"icd11": {"code": "", "title": "Sarcopenia", "status": "verify"},
               "hpo": [{"id": "HP:0003202", "label": "Skeletal muscle atrophy 骨骼肌萎縮"},
                       {"id": "HP:0001324", "label": "Muscle weakness 肌無力"}]},
    "糖尿病": {"icd11": {"code": "5A11", "title": "Type 2 diabetes mellitus",
                         "status": "curated"},
               "hpo": [{"id": "HP:0000819", "label": "Diabetes mellitus 糖尿病"}]},
    "銀屑病": {"icd11": {"code": "EA90", "title": "Psoriasis", "status": "curated"},
               "hpo": [{"id": "HP:0000989", "label": "Pruritus 瘙癢"}]},
    "血栓": {"icd11": {"code": "", "title": "Venous thromboembolism",
                       "status": "verify"}, "hpo": []},
    "冠心病": {"icd11": {"code": "BA40", "title": "Angina pectoris",
                         "status": "curated"},
               "hpo": [{"id": "HP:0001681", "label": "Angina pectoris 心絞痛"}]},
    "高血壓": {"icd11": {"code": "BA00", "title": "Essential hypertension",
                         "status": "curated"},
               "hpo": [{"id": "HP:0000822", "label": "Hypertension 高血壓"}]},
    "失眠": {"icd11": {"code": "7A00", "title": "Insomnia disorders",
                       "status": "curated"},
             "hpo": [{"id": "HP:0100785", "label": "Insomnia 失眠"}]},
    "焦慮抑鬱": {"icd11": {"code": "6A70 / 6B00",
                           "title": "Depressive / Anxiety disorders",
                           "status": "curated"},
                 "hpo": [{"id": "HP:0000716", "label": "Depression 抑鬱"},
                         {"id": "HP:0000739", "label": "Anxiety 焦慮"}]},
    "類風濕關節炎": {"icd11": {"code": "FA20", "title": "Rheumatoid arthritis",
                               "status": "curated"},
                     "hpo": [{"id": "HP:0002829", "label": "Arthralgia 關節痛"}]},
    "痛風": {"icd11": {"code": "FA25", "title": "Gout", "status": "curated"},
             "hpo": [{"id": "HP:0001997", "label": "Gout 痛風"}]},
    "哮喘": {"icd11": {"code": "CA23", "title": "Asthma", "status": "curated"},
             "hpo": [{"id": "HP:0002099", "label": "Asthma 哮喘"}]},
    "慢性胃炎": {"icd11": {"code": "DA42", "title": "Gastritis", "status": "curated"},
                 "hpo": [{"id": "HP:0002018", "label": "Nausea 噁心"}]},
    "便秘": {"icd11": {"code": "", "title": "Constipation", "status": "verify"},
             "hpo": [{"id": "HP:0002019", "label": "Constipation 便秘"}]},
    "腹瀉": {"icd11": {"code": "", "title": "Diarrhoea", "status": "verify"},
             "hpo": [{"id": "HP:0002014", "label": "Diarrhea 腹瀉"}]},
    "水腫": {"icd11": {"code": "", "title": "Oedema", "status": "verify"},
             "hpo": [{"id": "HP:0000969", "label": "Edema 水腫"}]},
    "尿路感染": {"icd11": {"code": "", "title": "Urinary tract infection",
                           "status": "verify"},
                 "hpo": [{"id": "HP:0000010",
                          "label": "Recurrent urinary tract infections 反覆尿路感染"}]},
    "偏頭痛": {"icd11": {"code": "8A80", "title": "Migraine", "status": "curated"},
               "hpo": [{"id": "HP:0002076", "label": "Migraine 偏頭痛"}]},
    "眩暈症": {"icd11": {"code": "AB31.0", "title": "Ménière disease",
                         "status": "curated"},
               "hpo": [{"id": "HP:0002321", "label": "Vertigo 眩暈"}]},
    "心律失常": {"icd11": {"code": "", "title": "Cardiac arrhythmia",
                           "status": "verify"},
                 "hpo": [{"id": "HP:0011675", "label": "Arrhythmia 心律失常"}]},
    "貧血": {"icd11": {"code": "", "title": "Anaemia", "status": "verify"},
             "hpo": [{"id": "HP:0001903", "label": "Anemia 貧血"}]},
    "痛經": {"icd11": {"code": "", "title": "Dysmenorrhoea", "status": "verify"},
             "hpo": [{"id": "HP:0100607", "label": "Dysmenorrhea 痛經"}]},
    "更年期綜合徵": {"icd11": {"code": "", "title": "Menopausal symptoms",
                               "status": "verify"}, "hpo": []},
    "濕疹": {"icd11": {"code": "EA80", "title": "Atopic eczema", "status": "curated"},
             "hpo": [{"id": "HP:0000964", "label": "Eczema 濕疹"}]},
    "慢性疲勞": {"icd11": {"code": "", "title": "Fatigue", "status": "verify"},
                 "hpo": [{"id": "HP:0012378", "label": "Fatigue 疲勞"}]},
    "炎症": {"icd11": {"code": "", "title": "（非單一病種，不設疾病編碼）",
                       "status": "not_applicable"}, "hpo": []},
}

CODES_NOTE = ("HPO/ICD-11 為精選種子交叉映射（部分僅 block 級精度；"
              "status=verify 者待對照官方發布核驗）；ICD-11 第 26 章傳統醫學"
              "模塊（TM1）收錄中醫病證分類，可作古籍病證的現代編碼橋接錨點。")


def standard_codes(name: str) -> Optional[Dict]:
    """現代術語 → HPO/ICD-11 種子交叉映射（含 status 與核驗提示）。"""
    key = _ALIAS_INDEX.get(normalize_query(name))
    if key is None or key not in CODES:
        return None
    return {"modern": key, **CODES[key], "note": CODES_NOTE}


_ALIAS_INDEX: Dict[str, str] = {}
for name, entry in PHENOTYPE_MAP.items():
    _ALIAS_INDEX[normalize_query(name)] = name
    for a in entry.get("aliases", []):
        _ALIAS_INDEX[normalize_query(a)] = name


def detect_modern(query: str) -> Optional[str]:
    """在查詢中檢出現代疾病/表型詞（最長優先）。"""
    q = normalize_query(query)
    for alias in sorted(_ALIAS_INDEX, key=len, reverse=True):
        if alias and alias in q:
            return _ALIAS_INDEX[alias]
    return None


def map_modern(name: str) -> Optional[Dict]:
    """現代術語 → 完整映射鏈（表型→病機→古籍詞→治法方向）+ 等級 + 免責。"""
    key = _ALIAS_INDEX.get(normalize_query(name))
    if key is None:
        return None
    e = PHENOTYPE_MAP[key]
    return {"modern": key,
            "phenotypes": e["phenotypes"],
            "tcm_semantics": e["tcm_semantics"],
            "classical_terms": e["classical_terms"],
            "methods_hint": e["methods_hint"],
            "grade": e["grade"],
            "grade_note": {"A": "症狀高度一致", "B": "病機或表型部分一致",
                           "C": "機制相關但病名不等同",
                           "D": "僅為研究假設"}[e["grade"]],
            "safety_note": e.get("safety_note", ""),
            "codes": ({**CODES[key], "note": CODES_NOTE}
                      if key in CODES else None),
            "disclaimer": DISCLAIMER,
            "layer": "D 現代映射（候選，不作病名等同）"}
