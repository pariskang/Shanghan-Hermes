"""本草種子詞典 — 傷寒論 85 味藥的性味/功效/類別/毒性通識層.

定位（誠實的證據分層）：
  * 性味與功效標籤屬 **本草學通識（D 層後世歸納）**，主要依《神農本草經》
    《名醫別錄》通行認識整理，供藥解/方解模塊作解釋基底——絕不冒充
    《傷寒論》原文（A 層）；
  * category 供煎服法規則引擎作兜底分類（礦物先煎/膠類烊化等通則，僅在
    方後原文未明時以 D 層規則補充——傷寒論方後原文永遠優先）；
  * toxicity/pregnancy_caution/十八反 供安全審校強制觸發，寧嚴勿鬆。

字段：nature 性味 · functions 功效標籤(2-4) · category 類別 ·
toxicity 0無/1小毒慎用/2有毒/3大毒峻烈 · pregnancy 妊娠慎用
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# alias → canonical（語料中的異寫與通行名歸一）
HERB_ALIASES: Dict[str, str] = {
    "肥梔子": "梔子", "黃檗": "黃柏", "代赭石": "代赭", "麻仁": "麻子仁",
    "香豉": "香豉", "豆豉": "香豉", "淡豆豉": "香豉", "天花粉": "栝蔞根",
    "瓜蔞根": "栝蔞根", "瓜蔞實": "栝蔞實", "禹餘糧": "太一禹餘糧",
    "飴糖": "膠飴", "連翹根": "連軺", "白芍": "芍藥", "赤芍": "芍藥",
    "炙甘草": "甘草", "生甘草": "甘草", "熟附子": "附子", "生附子": "附子",
    "川椒": "蜀椒", "花椒": "蜀椒", "麥冬": "麥門冬", "天冬": "天門冬",
}

# 每味藥：nature/functions/category/toxicity(/pregnancy)
HERB_INFO: Dict[str, Dict] = {
    "甘草": {"nature": "甘平", "functions": ["補中益氣", "調和諸藥", "緩急止痛"], "category": "根莖", "toxicity": 0},
    "桂枝": {"nature": "辛甘溫", "functions": ["解肌發表", "溫通經脈", "助陽化氣"], "category": "枝皮", "toxicity": 0},
    "大棗": {"nature": "甘溫", "functions": ["補中益氣", "養血安神", "調和營衛"], "category": "果實", "toxicity": 0},
    "生薑": {"nature": "辛微溫", "functions": ["發散風寒", "溫中止嘔", "化痰"], "category": "根莖", "toxicity": 0},
    "芍藥": {"nature": "苦酸微寒", "functions": ["養血斂陰", "柔肝止痛", "和營"], "category": "根莖", "toxicity": 0},
    "乾薑": {"nature": "辛熱", "functions": ["溫中散寒", "回陽通脈", "溫肺化飲"], "category": "根莖", "toxicity": 0},
    "附子": {"nature": "辛甘大熱", "functions": ["回陽救逆", "補火助陽", "散寒止痛"], "category": "根莖", "toxicity": 2, "pregnancy": True},
    "人參": {"nature": "甘微苦微溫", "functions": ["大補元氣", "生津", "安神"], "category": "根莖", "toxicity": 0},
    "半夏": {"nature": "辛溫", "functions": ["燥濕化痰", "降逆止嘔", "消痞散結"], "category": "根莖", "toxicity": 2, "pregnancy": True},
    "黃芩": {"nature": "苦寒", "functions": ["清熱燥濕", "瀉火解毒", "止血"], "category": "根莖", "toxicity": 0},
    "麻黃": {"nature": "辛微苦溫", "functions": ["發汗解表", "宣肺平喘", "利水消腫"], "category": "草莖", "toxicity": 1},
    "大黃": {"nature": "苦寒", "functions": ["瀉下攻積", "清熱瀉火", "逐瘀通經"], "category": "根莖", "toxicity": 1, "pregnancy": True},
    "茯苓": {"nature": "甘淡平", "functions": ["利水滲濕", "健脾", "寧心"], "category": "菌核", "toxicity": 0},
    "黃連": {"nature": "苦寒", "functions": ["清熱燥濕", "瀉火解毒", "除煩"], "category": "根莖", "toxicity": 0},
    "白朮": {"nature": "苦甘溫", "functions": ["健脾益氣", "燥濕利水", "止汗"], "category": "根莖", "toxicity": 0},
    "杏仁": {"nature": "苦微溫", "functions": ["止咳平喘", "潤腸通便"], "category": "種子", "toxicity": 1},
    "石膏": {"nature": "辛甘大寒", "functions": ["清熱瀉火", "除煩止渴"], "category": "礦物", "toxicity": 0},
    "梔子": {"nature": "苦寒", "functions": ["瀉火除煩", "清熱利濕", "涼血"], "category": "果實", "toxicity": 0},
    "枳實": {"nature": "苦辛微寒", "functions": ["破氣消積", "化痰除痞"], "category": "果實", "toxicity": 0, "pregnancy": True},
    "柴胡": {"nature": "苦微寒", "functions": ["和解表裏", "疏肝解鬱", "升舉陽氣"], "category": "根莖", "toxicity": 0},
    "芒硝": {"nature": "鹹苦寒", "functions": ["瀉下軟堅", "清熱"], "category": "礦物鹽", "toxicity": 1, "pregnancy": True},
    "厚朴": {"nature": "苦辛溫", "functions": ["燥濕消痰", "下氣除滿"], "category": "樹皮", "toxicity": 0},
    "細辛": {"nature": "辛溫", "functions": ["解表散寒", "祛風止痛", "溫肺化飲"], "category": "全草", "toxicity": 2},
    "牡蠣": {"nature": "鹹微寒", "functions": ["重鎮安神", "潛陽補陰", "軟堅散結"], "category": "貝殼", "toxicity": 0},
    "葛根": {"nature": "甘辛涼", "functions": ["解肌退熱", "生津", "升陽止瀉"], "category": "根莖", "toxicity": 0},
    "粳米": {"nature": "甘平", "functions": ["益氣和中", "護胃"], "category": "穀物", "toxicity": 0},
    "香豉": {"nature": "苦寒", "functions": ["宣鬱除煩", "解表"], "category": "發酵豆", "toxicity": 0},
    "當歸": {"nature": "甘辛溫", "functions": ["補血活血", "調經止痛"], "category": "根莖", "toxicity": 0},
    "知母": {"nature": "苦甘寒", "functions": ["清熱瀉火", "滋陰潤燥"], "category": "根莖", "toxicity": 0},
    "澤瀉": {"nature": "甘寒", "functions": ["利水滲濕", "泄熱"], "category": "塊莖", "toxicity": 0},
    "桃仁": {"nature": "苦甘平", "functions": ["活血祛瘀", "潤腸通便"], "category": "種子", "toxicity": 1, "pregnancy": True},
    "龍骨": {"nature": "甘澀平", "functions": ["鎮驚安神", "平肝潛陽", "收斂固澀"], "category": "礦物骨", "toxicity": 0},
    "豬苓": {"nature": "甘淡平", "functions": ["利水滲濕"], "category": "菌核", "toxicity": 0},
    "蜀漆": {"nature": "辛平", "functions": ["祛痰截瘧"], "category": "全草", "toxicity": 2},
    "水蛭": {"nature": "鹹苦平", "functions": ["破血逐瘀"], "category": "蟲類", "toxicity": 2, "pregnancy": True},
    "虻蟲": {"nature": "苦微寒", "functions": ["破血逐瘀"], "category": "蟲類", "toxicity": 2, "pregnancy": True},
    "葶藶子": {"nature": "辛苦大寒", "functions": ["瀉肺平喘", "利水消腫"], "category": "種子", "toxicity": 1},
    "甘遂": {"nature": "苦寒", "functions": ["瀉水逐飲"], "category": "根莖", "toxicity": 3, "pregnancy": True},
    "桔梗": {"nature": "苦辛平", "functions": ["宣肺利咽", "祛痰排膿"], "category": "根莖", "toxicity": 0},
    "栝蔞根": {"nature": "甘微苦微寒", "functions": ["清熱生津", "消腫排膿"], "category": "根莖", "toxicity": 0},
    "栝蔞實": {"nature": "甘微苦寒", "functions": ["清熱化痰", "寬胸散結"], "category": "果實", "toxicity": 0},
    "赤石脂": {"nature": "甘澀溫", "functions": ["澀腸止瀉", "收斂止血"], "category": "礦物", "toxicity": 0},
    "赤小豆": {"nature": "甘酸平", "functions": ["利水消腫", "解毒排膿"], "category": "種子", "toxicity": 0},
    "阿膠": {"nature": "甘平", "functions": ["補血滋陰", "潤燥止血"], "category": "膠類", "toxicity": 0},
    "麥門冬": {"nature": "甘微苦微寒", "functions": ["養陰生津", "潤肺清心"], "category": "根莖", "toxicity": 0},
    "吳茱萸": {"nature": "辛苦熱", "functions": ["散寒止痛", "降逆止嘔", "助陽止瀉"], "category": "果實", "toxicity": 1},
    "蔥白": {"nature": "辛溫", "functions": ["發表通陽"], "category": "鱗莖", "toxicity": 0},
    "豬膽汁": {"nature": "苦寒", "functions": ["清熱潤燥", "滑腸"], "category": "動物液", "toxicity": 0},
    "黃柏": {"nature": "苦寒", "functions": ["清熱燥濕", "瀉火解毒"], "category": "樹皮", "toxicity": 0},
    "通草": {"nature": "甘淡微寒", "functions": ["通利血脈", "利水"], "category": "藤莖", "toxicity": 0},
    "五味子": {"nature": "酸甘溫", "functions": ["收斂固澀", "益氣生津", "斂肺"], "category": "果實", "toxicity": 0},
    "膠飴": {"nature": "甘溫", "functions": ["補中緩急"], "category": "膠飴類", "toxicity": 0},
    "鉛丹": {"nature": "辛微寒", "functions": ["鎮驚墜痰"], "category": "礦物", "toxicity": 3},
    "文蛤": {"nature": "鹹平", "functions": ["清熱利濕", "軟堅"], "category": "貝殼", "toxicity": 0},
    "巴豆": {"nature": "辛熱", "functions": ["峻下冷積", "逐水"], "category": "種子", "toxicity": 3, "pregnancy": True},
    "貝母": {"nature": "苦甘微寒", "functions": ["清熱化痰", "散結"], "category": "鱗莖", "toxicity": 0},
    "芫花": {"nature": "苦辛溫", "functions": ["瀉水逐飲"], "category": "花", "toxicity": 3, "pregnancy": True},
    "大戟": {"nature": "苦寒", "functions": ["瀉水逐飲"], "category": "根莖", "toxicity": 3, "pregnancy": True},
    "太一禹餘糧": {"nature": "甘澀平", "functions": ["澀腸止瀉", "收斂止血"], "category": "礦物", "toxicity": 0},
    "旋覆花": {"nature": "苦辛鹹微溫", "functions": ["降氣消痰", "止噫"], "category": "花", "toxicity": 0},
    "代赭": {"nature": "苦寒", "functions": ["重鎮降逆", "平肝"], "category": "礦物", "toxicity": 0, "pregnancy": True},
    "瓜蒂": {"nature": "苦寒", "functions": ["湧吐痰食"], "category": "果蒂", "toxicity": 2},
    "生地黃": {"nature": "甘苦寒", "functions": ["清熱涼血", "養陰生津"], "category": "根莖", "toxicity": 0},
    "麻子仁": {"nature": "甘平", "functions": ["潤腸通便"], "category": "種子", "toxicity": 0},
    "滑石": {"nature": "甘淡寒", "functions": ["利尿通淋", "清熱"], "category": "礦物", "toxicity": 0},
    "食蜜": {"nature": "甘平", "functions": ["補中潤燥", "滑腸"], "category": "蜜類", "toxicity": 0},
    "茵陳蒿": {"nature": "苦微寒", "functions": ["清利濕熱", "退黃"], "category": "全草", "toxicity": 0},
    "連軺": {"nature": "苦寒", "functions": ["清熱解毒", "利濕"], "category": "根莖", "toxicity": 0},
    "生梓白皮": {"nature": "苦寒", "functions": ["清熱利濕"], "category": "樹皮", "toxicity": 0},
    "雞子黃": {"nature": "甘平", "functions": ["滋陰養血", "安神"], "category": "動物卵", "toxicity": 0},
    "雞子": {"nature": "甘平", "functions": ["滋陰潤燥", "利咽"], "category": "動物卵", "toxicity": 0},
    "豬膚": {"nature": "甘涼", "functions": ["滋陰潤燥", "利咽"], "category": "動物皮", "toxicity": 0},
    "人尿": {"nature": "鹹寒", "functions": ["滋陰降火"], "category": "動物液", "toxicity": 0},
    "烏梅": {"nature": "酸澀平", "functions": ["斂肺澀腸", "安蛔生津"], "category": "果實", "toxicity": 0},
    "蜀椒": {"nature": "辛熱", "functions": ["溫中止痛", "殺蟲"], "category": "果實", "toxicity": 1},
    "升麻": {"nature": "辛微甘微寒", "functions": ["發表透疹", "清熱解毒", "升舉陽氣"], "category": "根莖", "toxicity": 0},
    "天門冬": {"nature": "甘苦寒", "functions": ["養陰潤燥", "清肺生津"], "category": "根莖", "toxicity": 0},
    "白頭翁": {"nature": "苦寒", "functions": ["清熱解毒", "涼血止痢"], "category": "根莖", "toxicity": 0},
    "秦皮": {"nature": "苦澀寒", "functions": ["清熱燥濕", "止痢", "明目"], "category": "樹皮", "toxicity": 0},
    "商陸根": {"nature": "苦寒", "functions": ["逐水消腫"], "category": "根莖", "toxicity": 2, "pregnancy": True},
    "海藻": {"nature": "鹹寒", "functions": ["軟堅散結", "利水"], "category": "藻類", "toxicity": 0},
    "竹葉": {"nature": "甘辛淡寒", "functions": ["清熱除煩", "生津利尿"], "category": "葉", "toxicity": 0},
}

# 十八反（後世配伍之誡，D 層法度）：經方中偶有同用之例（如甘遂半夏湯），
# 系統的職責是「顯式標注供覆核」，而非替古人裁決——所以是 flag 不是 block。
SHIBAFAN_GROUPS: List[Tuple[str, List[str]]] = [
    ("甘草", ["甘遂", "大戟", "芫花", "海藻"]),
    ("附子", ["半夏", "栝蔞根", "栝蔞實", "貝母"]),   # 烏頭類與半蔞貝蘞芨
]

# 煎法兜底通則（僅方後原文未明時援引，全部標 D 層）
CATEGORY_DECOCTION_RULES: Dict[str, str] = {
    "礦物": "礦物類質重難出，通則宜先煎（D 層通則；方後原文有明文者從原文）",
    "礦物骨": "骨類質重難出，通則宜先煎（D 層通則）",
    "貝殼": "貝殼類質重難出，通則宜先煎（D 層通則）",
    "膠類": "膠類不入煎，通則烊化兌服（D 層通則）",
    "膠飴類": "飴糖不入煎，通則烊化兌服（D 層通則）",
}


def canonical_herb(name: str) -> str:
    name = name.strip()
    return HERB_ALIASES.get(name, name)


def herb_info(name: str) -> Optional[Dict]:
    return HERB_INFO.get(canonical_herb(name))


def toxicity_flags(herbs: List[str]) -> List[Dict]:
    """毒性/妊娠慎用/十八反掃描——安全審校的強制觸發點."""
    canon = [canonical_herb(h) for h in herbs]
    flags: List[Dict] = []
    for h in canon:
        info = HERB_INFO.get(h)
        if not info:
            continue
        if info.get("toxicity", 0) >= 2:
            flags.append({"kind": "toxicity", "herb": h,
                          "level": info["toxicity"],
                          "note": f"{h}屬{'大毒峻烈' if info['toxicity'] >= 3 else '有毒'}之品，"
                                  "炮製與劑量須嚴格遵醫囑"})
        if info.get("pregnancy"):
            flags.append({"kind": "pregnancy", "herb": h,
                          "note": f"{h}妊娠慎用/禁用（後世本草通識）"})
    present = set(canon)
    for a, group in SHIBAFAN_GROUPS:
        if a in present:
            hits = [b for b in group if b in present]
            if hits:
                flags.append({"kind": "shibafan", "herb": a,
                              "with": hits,
                              "note": f"{a}與{'、'.join(hits)}同用，觸後世十八反之誡"
                                      "（D 層法度；經方偶有同用例，須醫師覆核）"})
    return flags
