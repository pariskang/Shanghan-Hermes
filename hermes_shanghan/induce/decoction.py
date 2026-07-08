"""煎服法解析器 — 方後原文的規則化建模（A 層逐字錨定）.

傷寒論的方後注本身就是最權威的煎服法規則庫：「以水七升，微火煮取三升，
去滓，適寒溫，服一升……禁生冷、黏滑……」。所以本模塊的設計次序是：

  1. **方後原文解析為主**：煎煮介質/先煮後下/烊化沖服/火候水量/服用頻次/
     溫度時機/啜粥溫覆/飲食禁忌/強羸加減/中病即止——每個字段都帶逐字
     source span，屬 A 層證據；
  2. **類別通則兜底**（herb_lexicon.CATEGORY_DECOCTION_RULES）：僅當方後
     原文對某類藥無明文時，以「礦物先煎/膠類烊化」等後世通則補充，
     一律標注 D 層，絕不覆蓋原文；
  3. **安全審校強制觸發**：毒性/妊娠/十八反掃描（herb_lexicon.toxicity_flags）、
     外用方識別（蜜煎導「內穀道中」不是內服！）、漢制劑量不可直接折現代
     劑量的固定警示。

輸出的每一條都可回源：clause_id + 逐字 span。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .. import herb_lexicon

# —— 煎煮介質 ————————————————————————————————————————
RE_MEDIA = re.compile(
    r"(以\s*(?:甘瀾水|潦水|清漿水|漿水|清酒|苦酒|水|蜜|白飲|麻沸湯)"
    r"[一二三四五六七八九十百]*[斗升合]?(?:[，,]?\s*水[一二三四五六七八九十]+[斗升])?)")
MEDIA_NAMES = ["甘瀾水", "潦水", "清漿水", "漿水", "清酒", "苦酒", "麻沸湯",
               "白飲", "蜜", "水"]

# —— 先煮/後內/烊化/去滓再煎 ————————————————————————————
RE_PRE_BOIL = re.compile(r"先煮([^，,。；]{1,12})[，,]([^。；]{0,24})")
RE_ADD_LATER = re.compile(r"內([^，,。；]{1,10})[，,]?")
RE_MELT = re.compile(r"(烊消?盡|烊化|消盡)")
RE_REDECOCT = re.compile(r"去滓[，,]?\s*再煎")
RE_BOIL_TO = re.compile(r"[煮煎]取([一二三四五六七八九十百]+[升合])")
RE_FIRE = re.compile(r"(微火|文火|武火|急火|小火)")
RE_RICE_DONE = re.compile(r"煮米熟|米熟湯成|煮米令熟")
RE_POWDER = re.compile(r"(為散|作散|杵為散|搗(?:篩|為散)|為末|研)")
RE_PILL = re.compile(r"(為丸|作丸|煉蜜.{0,6}丸|丸如)")
# 外用途徑：導法/灌腸/外洗/熏——絕不能誤判為內服
RE_EXTERNAL = re.compile(r"(內穀道|灌穀道|導(?:之|法)?|外洗|熏之|坐藥|摩|敷)")

# —— 服法 ————————————————————————————————————————————
RE_PER_DOSE = re.compile(
    r"(?<![停後更盡再能])服([一二三四五六七八九十百半]+(?:[升合枚]|錢匕?))")
RE_FREQUENCY = re.compile(r"(日[一二三四五六七八九十]+服|日再服|日[再三]?夜[一二三四五六七八九十]服|"
                          r"分溫[再三四]服|頓服(?:之)?|少少溫服(?:之)?|平旦服|日三度)")
RE_TEMPERATURE = re.compile(r"(溫服|熱服|冷服|小冷|適寒溫)")
RE_STOP_RULE = re.compile(r"((?:得(?:吐|快利|利|下|汗)|汗出|若一服[^，,。]{0,8})[^。；]{0,14}"
                          r"(?:止後服|停後服|勿更服|餘勿服|不必盡劑))")
RE_ADJUST = re.compile(r"(強人[^。；，,]{0,10}|羸人[^。；，,]{0,10}|老小[^。；，,]{0,10}|"
                       r"病重者[^。；]{0,16})")
RE_DIET_CARE = re.compile(r"(歠熱稀粥[^。；]{0,10}|啜粥|溫覆[^。；]{0,8}|"
                          r"禁[^。；]{2,24}(?:等物)?|忌[^。；]{2,16})")

_MELT_HERBS = ("阿膠", "膠飴", "食蜜")


def _spans(regex: re.Pattern, text: str) -> List[str]:
    out, seen = [], set()
    for m in regex.finditer(text or ""):
        s = m.group(0).strip("，, ")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def parse_decoction(formula: str, preparation: str, administration: str,
                    herbs: List[str], clause_id: str = "") -> Dict:
    """方後原文 →結構化煎服方案；每個字段帶逐字 span（A 層）。"""
    prep = preparation or ""
    admin = administration or ""
    full = prep + admin

    # 劑型與途徑
    if RE_EXTERNAL.search(full):
        dosage_form, route = "外用製劑", "外用（非內服！）"
    elif RE_PILL.search(full):
        dosage_form, route = "丸劑", "內服"
    elif RE_POWDER.search(full) and "煮" not in prep:
        dosage_form, route = "散劑", "內服"
    elif RE_POWDER.search(full):
        dosage_form, route = "散劑（湯調/煮服）", "內服"
    else:
        dosage_form, route = "湯劑", "內服"

    media = []
    for m in RE_MEDIA.finditer(prep):
        media.append({"text": m.group(1), "layer": "A"})
    if not media:
        for name in MEDIA_NAMES:
            if name in prep:
                media.append({"text": name, "layer": "A"})
                break

    steps: List[Dict] = []
    for m in RE_PRE_BOIL.finditer(prep):
        steps.append({"method": "先煮", "target": m.group(1).strip(),
                      "detail": m.group(2).strip(" ，,"),
                      "span": m.group(0), "layer": "A"})
    for m in RE_ADD_LATER.finditer(prep):
        target = m.group(1).strip()
        if "穀道" in target or "道中" in target:
            continue                      # 外用導法的「內」是塞入，非後下
        if target.startswith(("諸藥", "藥")):
            steps.append({"method": "內諸藥（後合煎）", "target": "諸藥",
                          "span": m.group(0), "layer": "A"})
        elif any(h in target for h in _MELT_HERBS) or RE_MELT.search(target) \
                or RE_MELT.search(prep[m.end():m.end() + 8]):
            steps.append({"method": "烊化兌入",
                          "target": RE_MELT.sub("", target).strip("，, ") or target,
                          "span": m.group(0), "layer": "A"})
        else:
            steps.append({"method": "後內", "target": target,
                          "span": m.group(0), "layer": "A"})
    if RE_REDECOCT.search(prep):
        steps.append({"method": "去滓再煎", "target": "全方",
                      "span": RE_REDECOCT.search(prep).group(0), "layer": "A"})
    if RE_RICE_DONE.search(prep):
        steps.append({"method": "煮米熟為度", "target": "粳米",
                      "span": RE_RICE_DONE.search(prep).group(0), "layer": "A"})

    fire = _spans(RE_FIRE, prep)
    boil_to = _spans(RE_BOIL_TO, prep)

    # 類別通則兜底：方後未明文處理的礦物/膠類——僅提示，不冒充原文
    covered = "".join(s.get("target", "") for s in steps)
    generic: List[Dict] = []
    for h in herbs:
        info = herb_lexicon.herb_info(h)
        if not info:
            continue
        rule = herb_lexicon.CATEGORY_DECOCTION_RULES.get(info["category"])
        if rule and h not in covered and h not in prep:
            generic.append({"herb": h, "rule": rule, "layer": "D"})

    # 服法信息可能落在 preparation 或 administration 任一段（如十棗湯的
    # 「強人服一錢匕」在製法段末）——統一掃描全文
    service = {
        "per_dose": _spans(RE_PER_DOSE, full)[:2],
        "frequency": _spans(RE_FREQUENCY, full)[:3],
        "temperature": _spans(RE_TEMPERATURE, full)[:2],
        "stop_rules": _spans(RE_STOP_RULE, full)[:3],        # 中病即止
        "adjustments": _spans(RE_ADJUST, full)[:3],          # 強人/羸人
        "diet_and_care": _spans(RE_DIET_CARE, full)[:6],     # 啜粥/溫覆/禁忌
        "layer": "A",
    }

    safety = herb_lexicon.toxicity_flags(herbs)
    if route.startswith("外用"):
        safety.insert(0, {"kind": "route", "note":
                          "本方為外用/導法，方後明言用法，切勿誤作內服湯劑"})
    safety.append({"kind": "dose_conversion", "note":
                   "漢制兩/升不可直接等同現代克/毫升——折算須指明學派假設"
                   "（見 shanghan_dose_convert 三家折算），臨床劑量遵醫囑"})

    return {
        "formula": formula,
        "clause_id": clause_id,
        "dosage_form": dosage_form,
        "route": route,
        "media": media,
        "fire": fire,
        "boil_to": boil_to,
        "steps": steps,
        "service": service,
        "generic_rules": generic,
        "safety_flags": safety,
        "source": {"preparation": prep, "administration": admin[:400],
                   "layer": "A 方後原文逐字"},
    }
