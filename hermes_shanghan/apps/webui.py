"""醫哲未來人工智能研究院 · 粉晶 Gradio 界面 (Rose-Quartz Web Studio).

One Gradio app integrating the whole agent stack:

  對話研習   AgentSession 多輪對話（單智能體/複合編排/多智能體合議 × 四角色），
             右側四聯面板：檢索原文 / 推理軌跡 / 多假設鑒別 / 引用核驗
  深度研究   DeepResearcher 溯源檔案（研究問題細化/六維度發現/缺口報告）
  方證工具台 檢索 · 條文全息 · 多假設匹配 · 鑒別 · 劑量 · 禁忌
  評測基準   四套件指標速覽 + 智能體基準一鍵重跑
  結果導出   對話與研究檔案一鍵導出 Markdown / JSON

Design language: rose quartz（粉晶）× international minimalism — soft
gradients, serif classical text, generous whitespace. Launch helpers cover
Colab（ngrok 公網映射 / gradio share）與本地。Gradio is an optional
dependency: `pip install hermes-shanghan[webui]`.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BRAND_CN = "醫哲未來人工智能研究院"
BRAND_EN = "YIZHE FUTURE AI RESEARCH INSTITUTE"
APP_TITLE = "傷寒·赫爾墨斯 Hermes-Shanghanlun"

ROLES = {"醫師": "doctor", "科研": "researcher", "學生": "student", "患者": "patient"}
MODES = ("單智能體", "複合編排", "多智能體合議")
LAYER_COLORS = {"A": "#C96B72", "B": "#B08968", "C": "#7D8CC4",
                "D": "#9C7BA8", "D/E": "#9C7BA8", "旁證": "#8A8F98"}

CSS = """
:root{
  --rq-ink:#3D2C2E; --rq-sub:#8C5A60; --rq-accent:#C96B72;
  --rq-line:#F2DFE0; --rq-bg:#FDF8F8; --rq-chip:#FBEDEE;
}
.gradio-container{max-width:1440px !important; margin:0 auto !important;}
/* ── hero ─────────────────────────────────────────────── */
.hermes-hero{background:linear-gradient(135deg,#F7CAC9 0%,#F5D7E3 42%,#E8EAF6 100%);
  border-radius:22px; padding:30px 38px 26px; margin:6px 0 14px;
  border:1px solid rgba(201,107,114,.18); box-shadow:0 10px 34px rgba(222,139,143,.16);}
.hermes-hero .en{letter-spacing:.42em; font-size:.7rem; font-weight:600;
  color:#8C5A60; text-transform:uppercase; margin-bottom:6px;}
.hermes-hero h1{font-family:'Noto Serif TC','Songti TC',serif; font-size:1.9rem;
  letter-spacing:.08em; color:#3D2C2E; margin:0 0 6px; font-weight:600;}
.hermes-hero .sub{color:#6B4A50; font-size:.92rem; letter-spacing:.02em;}
.hermes-hero .pill-row{margin-top:14px; display:flex; gap:8px; flex-wrap:wrap;}
.hero-pill{background:rgba(255,255,255,.65); border:1px solid rgba(201,107,114,.25);
  color:#A94E57; border-radius:999px; padding:4px 14px; font-size:.76rem;
  letter-spacing:.05em; backdrop-filter:blur(4px);}
/* ── panels & cards ───────────────────────────────────── */
.panel-scroll{max-height:560px; overflow-y:auto; padding-right:4px;}
.clause-card{background:#fff; border:1px solid var(--rq-line);
  border-left:4px solid var(--rq-accent); border-radius:14px;
  padding:14px 18px; margin:10px 2px; box-shadow:0 2px 12px rgba(222,139,143,.08);}
.clause-card .meta{display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px;}
.cid{font-family:ui-monospace,SFMono-Regular,monospace; font-size:.7rem;
  background:var(--rq-chip); color:#A94E57; padding:2px 10px; border-radius:999px;}
.ctag{font-size:.7rem; color:#8C5A60; background:#F7F1F2; padding:2px 10px; border-radius:999px;}
.ctext{font-family:'Noto Serif TC','Songti TC',serif; line-height:2.0;
  color:var(--rq-ink); font-size:.98rem;}
.layer-badge{display:inline-block; font-size:.66rem; font-weight:700; color:#fff;
  border-radius:6px; padding:1px 7px; margin-right:6px; letter-spacing:.05em;}
.hyp-card{background:#fff; border:1px solid var(--rq-line); border-radius:14px;
  padding:14px 18px; margin:10px 2px; box-shadow:0 2px 12px rgba(222,139,143,.08);}
.hyp-card h4{margin:0 0 8px; color:var(--rq-ink); font-size:1rem;}
.hyp-row{font-size:.86rem; color:#5B4348; margin:3px 0; line-height:1.7;}
.hyp-row b{color:#A94E57; font-weight:600;}
.conf-chip{float:right; font-size:.72rem; padding:2px 12px; border-radius:999px;
  background:linear-gradient(90deg,#F7CAC9,#E8EAF6); color:#6B2E37; font-weight:700;}
.ask-box{background:#FFF7F0; border:1px dashed #E4B7A0; border-radius:12px;
  padding:12px 16px; margin:12px 2px; font-size:.88rem; color:#7A4E33; line-height:1.9;}
.verdict-ok{background:#F0F7F1; border-left:4px solid #7BA886;}
.verdict-warn{background:#FDF3EE; border-left:4px solid #D89A6E;}
.consensus-box{background:#fff; border:1px solid var(--rq-line); border-radius:14px;
  padding:14px 18px; margin:10px 2px;}
.consensus-box h4{margin:2px 0 8px; color:#A94E57;}
.stat-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:12px; margin:8px 0;}
.stat-tile{background:linear-gradient(160deg,#FFFFFF, #FDF3F3);
  border:1px solid var(--rq-line); border-radius:16px; padding:16px 18px;
  box-shadow:0 2px 12px rgba(222,139,143,.07);}
.stat-tile .v{font-size:1.55rem; font-weight:700; color:#A94E57;
  font-variant-numeric:tabular-nums;}
.stat-tile .k{font-size:.74rem; color:#8C5A60; letter-spacing:.06em; margin-top:2px;}
.section-note{font-size:.8rem; color:#8C5A60; line-height:1.7; margin:4px 2px 10px;}
.hermes-footer{text-align:center; color:#A98A8E; font-size:.76rem;
  letter-spacing:.14em; margin:22px 0 8px; line-height:2;}
table.diff-table{width:100%; border-collapse:collapse; font-size:.86rem;}
table.diff-table th{background:var(--rq-chip); color:#A94E57; padding:8px 10px;
  text-align:left; font-weight:600; border:1px solid var(--rq-line);}
table.diff-table td{padding:8px 10px; border:1px solid var(--rq-line);
  color:var(--rq-ink); font-family:'Noto Serif TC',serif; line-height:1.8;}
/* dark mode – keep panels legible */
.dark .clause-card,.dark .hyp-card,.dark .consensus-box,.dark .stat-tile{
  background:#2A2224; border-color:#4A3A3D;}
.dark .ctext,.dark .hyp-card h4{color:#F2E5E6;}
.dark .hyp-row{color:#D8C3C6;}
"""

HEAD = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:'
        'wght@400;600&display=swap" rel="stylesheet">')

HERO = f"""
<div class="hermes-hero">
  <div class="en">{BRAND_EN}</div>
  <h1>傷寒 · 赫爾墨斯 <span style="font-size:1.05rem;color:#8C5A60;">Hermes-Shanghanlun</span></h1>
  <div class="sub">{BRAND_CN} · 《傷寒論》證據回源智能體平台 —— 無原文，不成規則；無條文編號，不成證據；無證據鏈，不成回答</div>
  <div class="pill-row">
    <span class="hero-pill">🧭 任務圖規劃</span><span class="hero-pill">📎 句級證據綁定</span>
    <span class="hero-pill">🔬 多假設鑒別</span><span class="hero-pill">⚖️ 合議裁決</span>
    <span class="hero-pill">🛡️ 患者硬隔離</span><span class="hero-pill">📊 智能體基準</span>
  </div>
</div>"""

FOOTER = (f'<div class="hermes-footer">{BRAND_CN} · {BRAND_EN}<br>'
          '本平台輸出基於《傷寒論》原文的結構化轉寫，僅供學術研究、教學與醫師參考，'
          '不構成醫療建議 · Evidence-grounded, assistive only</div>')


# ═══════════════════════════════════════════════════════════════════
# lazy backend access
# ═══════════════════════════════════════════════════════════════════
def _registry():
    from ..agent.tools import get_registry
    return get_registry()


def _store():
    return _registry().art.clause_store()


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\n", "<br>"))


def _layer_badge(layer: str) -> str:
    color = LAYER_COLORS.get(layer, "#8A8F98")
    return f'<span class="layer-badge" style="background:{color}">{_esc(layer)}</span>'


# ═══════════════════════════════════════════════════════════════════
# HTML renderers (payload → panel)
# ═══════════════════════════════════════════════════════════════════
def clause_cards_html(clause_ids: List[str], title: str = "") -> str:
    store = _store()
    if not clause_ids:
        return ('<div class="section-note">本輪未產生條文級證據。'
                '提問中包含症狀/方名/條文號可觸發取證。</div>')
    cards = [f'<div class="section-note">{title}</div>'] if title else []
    for cid in clause_ids[:24]:
        c = store.get(cid)
        if c is None:
            continue
        num = f"第{c.clause_number}條" if getattr(c, "clause_number", 0) else "附"
        cards.append(
            f'<div class="clause-card"><div class="meta">'
            f'{_layer_badge(getattr(c, "layer", "A") or "A")}'
            f'<span class="cid">{cid}</span>'
            f'<span class="ctag">{num}</span>'
            f'<span class="ctag">{_esc(c.six_channel or c.chapter or "")}</span>'
            f'</div><div class="ctext">{_esc(c.clean_text)}</div></div>')
    return f'<div class="panel-scroll">{"".join(cards)}</div>'


def hypotheses_html(payload: Optional[Dict]) -> str:
    if not payload or not payload.get("hypotheses"):
        return ('<div class="section-note">本輪未觸發多假設分析——'
                '描述症狀與脈象（如「惡寒發熱無汗，脈浮緊」）即可啟用。</div>')
    parts = []
    for i, h in enumerate(payload["hypotheses"], 1):
        rows = []
        if h.get("support"):
            rows.append(f'<div class="hyp-row"><b>支持</b>：{_esc("；".join(h["support"][:4]))}</div>')
        if h.get("against"):
            rows.append(f'<div class="hyp-row"><b>反證</b>：{_esc("；".join(h["against"][:2]))}</div>')
        if h.get("counter_evidence_would_be"):
            rows.append(f'<div class="hyp-row"><b>何證則削弱</b>：'
                        f'{_esc("；".join(h["counter_evidence_would_be"][:2]))}</div>')
        if h.get("missing_key_findings"):
            rows.append(f'<div class="hyp-row"><b>尚未確認</b>：'
                        f'{_esc("、".join(h["missing_key_findings"]))}</div>')
        if h.get("evidence"):
            chips = " ".join(f'<span class="cid">{e}</span>' for e in h["evidence"][:4])
            rows.append(f'<div class="hyp-row"><b>證據</b>：{chips}</div>')
        parts.append(
            f'<div class="hyp-card"><span class="conf-chip">置信 {_esc(h.get("confidence", ""))}'
            f' · {h.get("score", "")}</span><h4>假設{i} · {_esc(h["formula"])}'
            f'</h4>{"".join(rows)}</div>')
    if payload.get("needs_clarification") and payload.get("clarifying_questions"):
        qs = "".join(f"· {_esc(q)}<br>" for q in payload["clarifying_questions"])
        parts.append(f'<div class="ask-box"><b>🩺 鑒別追問</b>'
                     f'（{_esc(payload.get("clarification_reason", ""))}）<br>{qs}</div>')
    return f'<div class="panel-scroll">{"".join(parts)}</div>'


def consensus_html(adj: Optional[Dict], judgments: Optional[List[Dict]] = None) -> str:
    if not adj:
        return ('<div class="section-note">切換到「多智能體合議」模式後，'
                '此處顯示各專家獨立判斷與共識/分歧裁決。</div>')
    parts = []
    for j in judgments or []:
        parts.append(
            f'<div class="hyp-card"><span class="conf-chip">{j.get("confidence", "")}</span>'
            f'<h4>{_esc(j.get("agent", ""))}</h4>'
            f'<div class="hyp-row"><b>判斷</b>：{_esc(j.get("hypothesis", ""))}</div>'
            + (f'<div class="hyp-row"><b>支持</b>：{_esc("；".join(j.get("support", [])[:3]))}</div>'
               if j.get("support") else "")
            + (f'<div class="hyp-row"><b>證據</b>：'
               + " ".join(f'<span class="cid">{e}</span>' for e in j.get("evidence", [])[:4])
               + '</div>' if j.get("evidence") else "")
            + '</div>')
    box = ['<div class="consensus-box">']
    box.append(f'<h4>⚖️ 合議裁決 · 置信 {adj.get("final_confidence")} '
               f'（{_esc(adj.get("decision", ""))}）</h4>')
    if adj.get("dominant_hypothesis"):
        box.append(f'<div class="hyp-row"><b>主導假設</b>：{_esc(adj["dominant_hypothesis"])}</div>')
    for label, key in (("共識", "consensus"), ("分歧", "disagreements"),
                       ("需要補充", "must_verify")):
        for item in adj.get(key, []):
            box.append(f'<div class="hyp-row"><b>{label}</b>：{_esc(item)}</div>')
    sb = adj.get("score_breakdown") or {}
    if sb:
        box.append('<div class="hyp-row" style="font-size:.76rem;color:#8C5A60;">評分：'
                   + " · ".join(f"{k} {v}" for k, v in sb.items()) + '</div>')
    box.append('</div>')
    return f'<div class="panel-scroll">{"".join(parts)}{"".join(box)}</div>'


def citation_html(report: Optional[Dict], claims: Optional[Dict]) -> str:
    if not report:
        return '<div class="section-note">尚無核驗記錄。</div>'
    ok = report.get("ok")
    cls = "verdict-ok" if ok else "verdict-warn"
    head = (f'<div class="clause-card {cls}"><b>{"✅ 引用核驗通過" if ok else "⚠️ 引用核驗有警告"}</b>'
            f'<div class="hyp-row">已核實 {len(report.get("verified", []))} 條'
            f' · 越出本輪證據 {len(report.get("outside_evidence", []))} 條'
            f' · 未核實 {len(report.get("unsupported", []))} 條</div></div>')
    rows = []
    for c in (claims or {}).get("claims", [])[:40]:
        badge = _layer_badge(c.get("evidence_layer", "D"))
        ev = " ".join(f'<span class="cid">{e}</span>' for e in c.get("evidence", [])[:3])
        stype = c.get("support_type", "")
        color = {"direct": "#7BA886", "inferred": "#D8B26E",
                 "cited_low_overlap": "#D89A6E"}.get(stype, "#C96B72")
        rows.append(f'<tr><td>{badge}{_esc(c.get("claim", "")[:60])}</td>'
                    f'<td style="color:{color};font-weight:600">{stype}</td>'
                    f'<td>{ev or "—"}</td></tr>')
    table = ""
    if rows:
        rate = (claims or {}).get("claim_grounding_rate", 0)
        table = (f'<div class="section-note">句級證據綁定率 <b>{rate}</b>'
                 f'（{(claims or {}).get("n_grounded", 0)}/{(claims or {}).get("n_claims", 0)}）</div>'
                 '<table class="diff-table"><tr><th>Claim（層級標注）</th>'
                 '<th>支撐類型</th><th>證據</th></tr>' + "".join(rows) + '</table>')
    return f'<div class="panel-scroll">{head}{table}</div>'


def plan_html(out: Dict) -> str:
    plan = out.get("plan")
    if not plan:
        return ""
    rows = "".join(
        f'<tr><td><span class="cid">{t.get("id", "")}</span></td>'
        f'<td>{_esc(t.get("kind", ""))}</td><td>{_esc(t.get("question", "")[:46])}</td>'
        f'<td>{_esc("、".join(t.get("depends_on", [])) or "—")}</td>'
        f'<td>{_esc("、".join(t.get("tools_used", [])) or "—")}</td></tr>'
        for t in out.get("subtasks", []))
    crits = "".join(f"· {_esc(c)}<br>" for c in plan.get("success_criteria", []))
    unmet = (out.get("criteria_check") or {}).get("unmet") or []
    unmet_html = (f'<div class="ask-box">⚠️ 未覆蓋：{_esc("；".join(unmet))}</div>'
                  if unmet else '<div class="section-note">✅ 覆蓋標準全部滿足</div>')
    return ('<div class="consensus-box"><h4>🧭 任務圖（' + _esc(plan.get("planner", ""))
            + '）</h4><table class="diff-table"><tr><th>ID</th><th>類型</th><th>子任務</th>'
              '<th>依賴</th><th>工具</th></tr>' + rows + '</table>'
            f'<div class="section-note" style="margin-top:8px">成功標準：<br>{crits}</div>'
            + unmet_html + '</div>')


def stat_tiles(metrics: Dict[str, object]) -> str:
    tiles = "".join(
        f'<div class="stat-tile"><div class="v">{v}</div><div class="k">{_esc(k)}</div></div>'
        for k, v in metrics.items())
    return f'<div class="stat-grid">{tiles}</div>'


# ═══════════════════════════════════════════════════════════════════
# chat orchestration
# ═══════════════════════════════════════════════════════════════════
def _run_question(question: str, role_label: str, mode: str,
                  sessions: Dict) -> Tuple[Dict, Dict]:
    """Dispatch to the right agent stack; returns (payload, sessions)."""
    role = ROLES.get(role_label, "doctor")
    if mode == "多智能體合議":
        from ..agent.multi_agent import Council
        return Council().deliberate(question, role=role), sessions
    if mode == "複合編排":
        from ..agent.complex_agent import ComplexAgent
        return ComplexAgent().solve(question, role=role), sessions
    from ..agent.session import AgentSession
    key = f"session::{role}"
    if key not in sessions:
        sessions[key] = AgentSession(role=role)
    return sessions[key].ask(question, role=role), sessions


def chat_turn(message: str, history: List[Dict], role_label: str, mode: str,
              sessions: Dict, export_log: List[Dict]):
    message = (message or "").strip()
    if not message:
        return (history, "", sessions, export_log, gr.skip(), gr.skip(),
                gr.skip(), gr.skip(), gr.skip())
    t0 = time.time()
    try:
        out, sessions = _run_question(message, role_label, mode, sessions)
    except Exception as exc:                          # pragma: no cover
        out = {"answer": f"（運行異常：{type(exc).__name__}: {exc}）"}
    answer = out.get("answer") or out.get("message") or "（無回答）"
    history = list(history or [])
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": answer})

    ev_ids = out.get("evidence_clause_ids", []) or []
    evidence = clause_cards_html(ev_ids, title=f"本輪證據 {len(ev_ids)} 條（可回源）")
    hyp_payload = ({"hypotheses": out.get("hypotheses"),
                    "needs_clarification": bool(out.get("clarification")),
                    "clarifying_questions": (out.get("clarification") or {}).get("questions", []),
                    "clarification_reason": (out.get("clarification") or {}).get("reason", "")}
                   if out.get("hypotheses") else None)
    hyp = hypotheses_html(hyp_payload)
    cons = consensus_html(out.get("consensus"), out.get("judgments"))
    cite = citation_html(out.get("citation_report"), out.get("claims"))
    if out.get("plan"):
        cite = plan_html(out) + cite
    trace = (out.get("agent_trace") or out.get("orchestrator_trace")
             or out.get("council") or [])
    status = (f"模式 **{mode}** · 角色 **{role_label}** · 後端 `{out.get('backend', '—')}`"
              f" · 工具 {len(out.get('tools_used', []))} 次"
              f" · 證據 {len(ev_ids)} 條 · 用時 {time.time() - t0:.1f}s")
    if out.get("refused"):
        status += " · 🛡️ **安全守衛已攔截**"
    export_log = list(export_log or [])
    export_log.append({"time": time.strftime("%H:%M:%S"), "mode": mode,
                       "role": role_label, "question": message, "answer": answer,
                       "evidence_clause_ids": ev_ids,
                       "citation_report": out.get("citation_report"),
                       "claims": out.get("claims"),
                       "hypotheses": out.get("hypotheses"),
                       "consensus": out.get("consensus")})
    return (history, "", sessions, export_log, evidence, hyp, cons, cite,
            {"status": status, "trace": trace})


def export_conversation(export_log: List[Dict], fmt: str) -> Optional[str]:
    if not export_log:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tmp = Path(tempfile.mkdtemp(prefix="hermes_export_"))
    if fmt == "json":
        p = tmp / f"hermes_dialogue_{stamp}.json"
        p.write_text(json.dumps(export_log, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        return str(p)
    lines = [f"# {APP_TITLE} · 對話導出", "",
             f"> {BRAND_CN} · {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for i, t in enumerate(export_log, 1):
        lines += [f"## 第 {i} 輪 · {t['mode']} · {t['role']}",
                  "", f"**問**：{t['question']}", "", "**答**：", "",
                  t["answer"], ""]
        if t.get("evidence_clause_ids"):
            lines += ["**證據條文**：" + "、".join(t["evidence_clause_ids"]), ""]
        rep = t.get("citation_report") or {}
        if rep:
            lines += [f"**引用核驗**：verified={len(rep.get('verified', []))} "
                      f"outside={len(rep.get('outside_evidence', []))} "
                      f"unsupported={len(rep.get('unsupported', []))}", ""]
    p = tmp / f"hermes_dialogue_{stamp}.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


# ═══════════════════════════════════════════════════════════════════
# research tab
# ═══════════════════════════════════════════════════════════════════
def run_research(topic: str, rounds: int):
    topic = (topic or "").strip()
    if not topic:
        return ('<div class="section-note">請輸入研究主題，例如「桂枝湯類方的劑量演化」。</div>',
                None, None)
    from ..agent.research_loop import DeepResearcher
    d = DeepResearcher(max_rounds=int(rounds)).run(topic)
    qs = "".join(f"· {_esc(q)}<br>" for q in d.get("research_questions", []))
    cov = stat_tiles({k: v for k, v in d.get("coverage", {}).items()})
    finds = []
    for f in d.get("findings", []):
        ev = " ".join(f'<span class="cid">{e}</span>'
                      for e in f.get("verified_clause_ids", [])[:4])
        finds.append(f'<div class="clause-card"><div class="meta">'
                     f'{_layer_badge(f.get("dimension", ""))}'
                     f'<span class="ctag">{_esc(f.get("module", ""))}</span>'
                     f'{"✅" if f.get("citation_ok") else "⚠️"}</div>'
                     f'<div class="ctext" style="font-size:.9rem">{_esc(f.get("summary", ""))}</div>'
                     f'<div class="hyp-row">{ev}</div></div>')
    gaps = d.get("gap_report", [])
    gap_html = ("".join(f'<div class="ask-box"><b>缺口 · {_esc(g["dimension"])}</b>'
                        f'<br>{_esc(g["suggestion"])}</div>' for g in gaps)
                or '<div class="section-note">✅ 六維度全覆蓋，無缺口。</div>')
    html = (f'<div class="consensus-box"><h4>🔭 研究問題細化</h4>'
            f'<div class="hyp-row">{qs}</div></div>'
            f'{cov}<div class="panel-scroll">{"".join(finds)}</div>{gap_html}')
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tmp = Path(tempfile.mkdtemp(prefix="hermes_dossier_"))
    pj = tmp / f"dossier_{stamp}.json"
    pj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# 深度研究檔案 · {topic}", "", f"> {BRAND_CN} · 輪次 {d['n_rounds']}", "",
          "## 研究問題"] + [f"- {q}" for q in d.get("research_questions", [])] + ["", "## 發現"]
    for f in d.get("findings", []):
        md.append(f"### [{f['dimension']}] {f['module']}")
        md.append(f['summary'])
        if f.get("verified_clause_ids"):
            md.append("證據：" + "、".join(f["verified_clause_ids"]))
        md.append("")
    if gaps:
        md += ["## 研究缺口"] + [f"- {g['dimension']}：{g['suggestion']}" for g in gaps]
    pm = tmp / f"dossier_{stamp}.md"
    pm.write_text("\n".join(md), encoding="utf-8")
    return html, str(pm), str(pj)


# ═══════════════════════════════════════════════════════════════════
# tools tab handlers
# ═══════════════════════════════════════════════════════════════════
def tool_search(query, top_k, channel, expand):
    args = {"query": query or "", "top_k": int(top_k), "expand": bool(expand)}
    if channel:
        args["six_channel"] = channel
    out = _registry().call("shanghan_search", args)
    ids = [h.get("clause_id") for h in out.get("hits", []) if h.get("clause_id")]
    return clause_cards_html(ids, title=f"檢索「{query}」→ {len(ids)} 條")


def tool_holo(ref):
    reg = _registry()
    out = reg.call("shanghan_get_clause", {"ref": str(ref or "").strip()})
    if out.get("error"):
        return f'<div class="ask-box">⚠️ {_esc(out["error"])}</div>'
    c = out["clause"]
    parts = [clause_cards_html([c["clause_id"]], title="原文（A 層）")]
    var = reg.call("shanghan_variants", {"ref": c["clause_id"]})
    if var.get("variants"):
        rows = "".join(f'<tr><td>{_esc(v["book"])}</td><td>{v["similarity"]}</td>'
                       f'<td>{_esc("；".join(v.get("notable_differences", [])[:2]) or "用字基本一致")}</td></tr>'
                       for v in var["variants"][:4])
        parts.append('<div class="consensus-box"><h4>📜 版本異文（B 層）</h4>'
                     '<table class="diff-table"><tr><th>底本</th><th>相似度</th>'
                     '<th>主要差異</th></tr>' + rows + '</table></div>')
    div = reg.call("shanghan_divergence_atlas",
                   {"clause": c["clause_id"].split("_")[-1]})
    for row in (div.get("clauses") or [])[:1]:
        parts.append(f'<div class="consensus-box"><h4>🖋 注家（C 層）· '
                     f'{row.get("n_commentators", 0)} 家</h4><div class="hyp-row">'
                     f'{_esc("、".join(row.get("commentators", [])))}</div></div>')
    rel = out.get("relations") or []
    if rel:
        rows = "".join(f'<tr><td>{_esc(r.get("relation_type", ""))}</td>'
                       f'<td><span class="cid">{r.get("other_clause_id", r.get("clause_id", ""))}</span></td>'
                       f'<td>{_esc(str(r.get("description", r.get("text", "")))[:40])}</td></tr>'
                       for r in rel[:8])
        parts.append('<div class="consensus-box"><h4>🕸 關係圖譜</h4>'
                     '<table class="diff-table"><tr><th>關係</th><th>條文</th>'
                     '<th>說明</th></tr>' + rows + '</table></div>')
    return "".join(parts)


def tool_hypotheses(symptoms, pulse, channel, top_k):
    args = {"symptoms": symptoms or "", "pulse": pulse or "",
            "top_k": int(top_k)}
    if channel:
        args["six_channel"] = channel
    out = _registry().call("shanghan_hypotheses", args)
    if out.get("error"):
        return f'<div class="ask-box">⚠️ {_esc(out["error"])}</div>'
    return hypotheses_html(out)


def tool_differential(f1, f2, f3):
    formulas = [f for f in (f1, f2, f3) if f]
    if len(formulas) < 2:
        return '<div class="section-note">請至少選擇兩個方劑。</div>'
    out = _registry().call("shanghan_differential", {"formulas": formulas})
    if out.get("error"):
        cand = "、".join(out.get("candidates", []))
        return (f'<div class="ask-box">⚠️ {_esc(out["error"])}'
                + (f'<br>候選：{_esc(cand)}' if cand else "") + '</div>')
    d = out.get("differential", {})
    rows = "".join(f"<tr><td>{_esc(k.get('dimension', k.get('axis', '')))}</td>"
                   + "".join(f"<td>{_esc(str(k.get(f, k.get('values', {}).get(f, '—'))))}</td>"
                             for f in d.get("formulas", []))
                   + "</tr>"
                   for k in d.get("contrast_table", [])[:12]) if d.get("contrast_table") else ""
    disc = "".join(f"· {_esc(x)}<br>" for x in d.get("key_discriminators", []))
    ev = " ".join(f'<span class="cid">{e}</span>' for e in d.get("supporting_clauses", [])[:8])
    head = "".join(f"<th>{_esc(f)}</th>" for f in d.get("formulas", []))
    table = (f'<table class="diff-table"><tr><th>軸</th>{head}</tr>{rows}</table>'
             if rows else "")
    return (f'<div class="consensus-box"><h4>⚗️ {" vs ".join(d.get("formulas", []))}</h4>'
            f'<div class="hyp-row"><b>關鍵鑒別</b>：<br>{disc}</div>{table}'
            f'<div class="hyp-row" style="margin-top:8px"><b>證據</b>：{ev}</div></div>')


def tool_dose(formula, convert_expr):
    reg = _registry()
    parts = []
    if formula:
        out = reg.call("shanghan_dose", {"formula": formula})
        if out.get("error"):
            parts.append(f'<div class="ask-box">⚠️ {_esc(out["error"])}'
                         + (f'<br>候選：{_esc("、".join(out.get("candidates", [])))}'
                            if out.get("candidates") else "") + '</div>')
        else:
            r = out.get("ratio") or {}
            if r:
                parts.append(f'<div class="consensus-box"><h4>💊 {_esc(formula)} · '
                             f'藥量比（銖當量）</h4><div class="ctext">{_esc(r.get("ratio", ""))}'
                             f'</div><div class="hyp-row">三家折算總量(g)：'
                             f'{_esc(str(r.get("total_weight_g", "")))} '
                             f'<span class="cid">{r.get("clause_id", "")}</span></div></div>')
            edges = out.get("evolution_edges") or []
            if edges:
                rows = "".join(f'<tr><td>{_esc(e["base"])}</td><td>→</td>'
                               f'<td>{_esc(e["modified"])}</td>'
                               f'<td>{_esc(e.get("edge_kind", ""))}</td></tr>' for e in edges[:8])
                parts.append('<div class="consensus-box"><h4>🌱 家族劑量演化</h4>'
                             '<table class="diff-table">' + rows + '</table></div>')
    if convert_expr:
        out = reg.call("shanghan_dose_convert", {"dose": convert_expr})
        if out.get("error"):
            parts.append(f'<div class="ask-box">⚠️ {_esc(out["error"])}</div>')
        elif out.get("kind") == "weight":
            g = out.get("grams_by_school", {})
            parts.append(f'<div class="consensus-box"><h4>⚖️ 「{_esc(convert_expr)}」換算</h4>'
                         f'<div class="hyp-row">= {out.get("zhu")} 銖 = {out.get("liang")} 兩'
                         f'；考古 {g.get("kaogu")}g · 度量衡史 {g.get("duliangheng")}g'
                         f' · 明清 {g.get("zhezhuan")}g</div></div>')
        else:
            parts.append(f'<div class="consensus-box"><h4>⚖️ 「{_esc(convert_expr)}」換算</h4>'
                         f'<div class="hyp-row">{_esc(json.dumps(out, ensure_ascii=False)[:200])}'
                         '</div></div>')
    return "".join(parts) or '<div class="section-note">輸入方名或劑量表達式。</div>'


def tool_contra(formula, symptoms):
    if not formula:
        return '<div class="section-note">請選擇方劑。</div>'
    args = {"formula": formula}
    if symptoms:
        args["symptoms"] = symptoms
    out = _registry().call("shanghan_contraindication_check", args)
    if out.get("error"):
        return f'<div class="ask-box">⚠️ {_esc(out["error"])}</div>'
    parts = [f'<div class="consensus-box"><h4>🛡️ {_esc(out.get("formula", ""))} 禁忌檢查</h4>']
    for c in out.get("formula_contraindications", [])[:4]:
        parts.append(f'<div class="hyp-row"><b>原文禁例</b> '
                     f'<span class="cid">{c.get("clause_id", "")}</span> '
                     f'{_esc(str(c.get("condition", ""))[:60])}</div>')
    for c in out.get("symptom_conflicts", []):
        parts.append(f'<div class="hyp-row" style="color:#A94E57"><b>⚠️ 證候衝突</b>：'
                     f'所述「{_esc(c["presented"])}」與本方證之「{_esc(c["pattern_expects"])}」相反</div>')
    for b in out.get("therapy_law_bans", []):
        parts.append(f'<div class="hyp-row"><b>法度禁例</b>【{_esc(b["method"])}】'
                     f'{_esc(b["summary"][:40])}</div>')
    parts.append(f'<div class="section-note">{_esc(out.get("notice", ""))}</div></div>')
    return "".join(parts)


def _flags_html(flags: List[Dict]) -> str:
    out = []
    for f in flags or []:
        if f.get("kind") == "dose_conversion":
            out.append(f'<div class="section-note">⚖️ {_esc(f.get("note", ""))}</div>')
        else:
            out.append(f'<div class="ask-box">⚠️ {_esc(f.get("note", ""))}</div>')
    return "".join(out)


_CHANNEL_COLOR = {"直接原文": "#C96B72", "本體擴展": "#9C7BA8",
                  "圖譜關聯": "#7D8CC4", "現代映射": "#D89A6E",
                  "文獻旁證": "#8A8F98"}


def tool_omni(query, top_k, include_library):
    if not (query or "").strip():
        return '<div class="section-note">輸入古籍詞或現代疾病名。</div>'
    out = _registry().call("shanghan_omni_search",
                           {"query": query, "top_k": int(top_k),
                            "include_library": bool(include_library)})
    if out.get("error"):
        return f'<div class="ask-box">⚠️ {_esc(out["error"])}</div>'
    u = out.get("understanding", {})
    parts = [f'<div class="section-note">意圖 <b>{_esc(u.get("intent", ""))}</b>'
             f' · 用時 <b>{out.get("latency_ms")}</b> ms'
             f' · 命中池 {out.get("n_pool")} 條</div>']
    mp = out.get("modern_mapping")
    if mp:
        parts.append(
            f'<div class="consensus-box"><h4>🌉 跨時代映射 · {_esc(mp["modern"])}'
            f'（{mp["grade"]} 級·{_esc(mp["grade_note"])}）</h4>'
            f'<div class="hyp-row"><b>現代表型</b>：{_esc("、".join(mp["phenotypes"][:5]))}</div>'
            f'<div class="hyp-row"><b>病機語義</b>：{_esc("、".join(mp["tcm_semantics"][:4]))}</div>'
            f'<div class="hyp-row"><b>古籍候選詞</b>：{_esc("、".join(mp["classical_terms"]))}</div>'
            f'<div class="hyp-row"><b>治法方向</b>：{_esc("、".join(mp["methods_hint"]))}</div>'
            + (f'<div class="hyp-row"><b>標準詞表</b>：ICD-11 '
               f'<span class="cid">{_esc(mp["codes"]["icd11"]["code"] or "待核")}</span> '
               f'{_esc(mp["codes"]["icd11"]["title"])}'
               + "".join(f' · HPO <span class="cid">{h["id"]}</span> {_esc(h["label"])}'
                         for h in mp["codes"].get("hpo", [])[:2])
               + '</div>' if mp.get("codes") else "")
            + (f'<div class="ask-box">⚠️ {_esc(mp["safety_note"])}</div>'
               if mp.get("safety_note") else "")
            + f'<div class="section-note">{_esc(mp["disclaimer"])}'
            + (f'<br>{_esc(mp["codes"]["note"])}' if mp.get("codes") else "")
            + '</div></div>')
    if out.get("expanded_terms"):
        parts.append(f'<div class="section-note">本體擴展：'
                     f'{_esc("、".join(out["expanded_terms"][:8]))}</div>')
    store = _store()
    for h in out.get("hits", []):
        color = _CHANNEL_COLOR.get(h["evidence_type"], "#8A8F98")
        c = store.get(h["clause_id"])
        text = c.clean_text if c else h.get("text", "")
        parts.append(
            f'<div class="clause-card" style="border-left-color:{color}">'
            f'<div class="meta"><span class="layer-badge" style="background:'
            f'{color}">{_esc(h["evidence_type"])}</span>'
            f'<span class="cid">{h["clause_id"]}</span>'
            f'<span class="ctag">{_esc(h.get("six_channel", "") or "")}</span>'
            f'<span class="ctag">命中：{_esc("、".join(h["matched_terms"][:3]))}</span>'
            f'<span class="ctag">score {h["score"]}</span></div>'
            f'<div class="ctext">{_esc(text)}</div></div>')
    for h in out.get("library_hits", [])[:6]:
        parts.append(
            f'<div class="clause-card" style="border-left-color:#8A8F98">'
            f'<div class="meta"><span class="layer-badge" style="background:'
            f'#8A8F98">文獻旁證</span><span class="ctag">《{_esc(h["book"])}》'
            f'§{_esc(h["section"][:14])}</span>'
            + (f'<span class="cid">{_esc(h["pid"][-22:])}</span>'
               if h.get("pid") else "")
            + f'<span class="ctag">命中：{_esc(h["matched_term"])}</span></div>'
            f'<div class="ctext" style="font-size:.88rem">…{_esc(h["excerpt"])}…</div></div>')
    return f'<div class="panel-scroll">{"".join(parts)}</div>'


def tool_correspondence(symptoms, pulse, channel, modern):
    if not ((symptoms or "").strip() or (modern or "").strip()):
        return '<div class="section-note">輸入症狀（頓號/逗號分隔）或現代疾病名。</div>'
    args = {"top_k": 4}
    if (symptoms or "").strip():
        args["symptoms"] = symptoms
    if (pulse or "").strip():
        args["pulse"] = pulse
    if channel:
        args["six_channel"] = channel
    if (modern or "").strip():
        args["modern"] = modern.strip()
    out = _registry().call("shanghan_correspondence", args)
    if out.get("error"):
        return f'<div class="ask-box">⚠️ {_esc(out["error"])}</div>'
    parts = []
    mp = out.get("modern_mapping")
    if mp:
        parts.append(f'<div class="consensus-box"><h4>🌉 現代映射 · {_esc(mp["modern"])}'
                     f'（{mp["grade"]} 級）</h4><div class="hyp-row">'
                     f'{_esc("、".join(mp["classical_terms"]))}</div>'
                     f'<div class="section-note">{_esc(mp["disclaimer"])}</div></div>')
    syn = out.get("candidate_syndromes", [])
    if syn:
        rows = "".join(
            f'<tr><td>{_esc(s0["pathogenesis"])}</td><td>{s0["confidence"]}</td>'
            f'<td>{_esc("、".join((s0["matched"].get("required") or []) + (s0["matched"].get("supporting") or [])[:3]))}</td>'
            f'<td>{_esc("、".join(s0.get("missing", [])) or "—")}</td>'
            f'<td>{_esc(s0["method_label"])}</td></tr>' for s0 in syn[:3])
        parts.append('<div class="consensus-box"><h4>🧬 病機結構候選'
                     f'（{_layer_badge("D/E")}後世歸納，依據可見）</h4>'
                     '<table class="diff-table"><tr><th>病機</th><th>信度</th>'
                     '<th>命中線索</th><th>缺失</th><th>治法</th></tr>'
                     + rows + '</table></div>')
    for c in out.get("candidate_formulas", [])[:4]:
        d0 = c["score_breakdown"]
        rel = c["relation"]
        ev = " ".join(f'<span class="cid">{e}</span>' for e in c["evidence_clauses"][:4])
        dims = (f'症狀 {d0["symptom"]} · 病機 {d0["pathogenesis"]} · '
                f'治法 {d0["method"]} · 脈 {d0["pulse"]} · 證據 {d0["evidence"]}'
                + (f' · <span style="color:#A94E57">禁忌 −{d0["contraindication_penalty"]}</span>'
                   if d0["contraindication_penalty"] else ""))
        parts.append(
            f'<div class="hyp-card"><span class="conf-chip">總分 {c["total_score"]}</span>'
            f'<h4>{_esc(c["formula"])} · {_layer_badge(rel["grade"])}'
            f'{_esc(rel["relation"])}</h4>'
            f'<div class="hyp-row"><b>評分分解</b>：{dims}</div>'
            f'<div class="hyp-row"><b>分級依據</b>：{_esc(rel["basis"])}</div>'
            + (f'<div class="hyp-row"><b>命中病機</b>：'
               f'{_esc("、".join(c["matched_pathogenesis"]))}</div>'
               if c.get("matched_pathogenesis") else "")
            + (f'<div class="hyp-row" style="color:#A94E57"><b>反證/排除</b>：'
               f'{_esc("；".join(c.get("conflicts", []) + c.get("excluded_patterns_present", [])))}</div>'
               if c.get("conflicts") or c.get("excluded_patterns_present") else "")
            + f'<div class="hyp-row"><b>證據</b>：{ev}</div></div>')
    diff0 = out.get("differential")
    if diff0:
        parts.append(f'<div class="consensus-box"><h4>⚗️ 類方鑒別 · '
                     f'{" vs ".join(diff0["pair"])}</h4><div class="hyp-row">'
                     + "<br>".join(_esc(x) for x in diff0.get("key_discriminators", []))
                     + '</div></div>')
    qs = out.get("clarifying_questions", [])
    if qs:
        parts.append('<div class="ask-box"><b>🩺 鑒別追問</b><br>'
                     + "".join(f"· {_esc(q)}<br>" for q in qs) + '</div>')
    if out.get("coverage_note"):
        parts.append(f'<div class="ask-box">⚠️ {_esc(out["coverage_note"])}</div>')
    parts.append(f'<div class="section-note">{_esc(out.get("tongue_note", ""))}<br>'
                 f'{_esc(out.get("safety_boundary", ""))}</div>')
    return f'<div class="panel-scroll">{"".join(parts)}</div>'


def tool_herb(name):
    if not (name or "").strip():
        return '<div class="section-note">輸入藥名，如 桂枝 / 附子 / 阿膠。</div>'
    out = _registry().call("shanghan_herb", {"herb": name.strip()})
    if out.get("error"):
        cand = "、".join(out.get("candidates", []))
        return (f'<div class="ask-box">⚠️ {_esc(out["error"])}'
                + (f'<br>候選：{_esc(cand)}' if cand else "") + '</div>')
    seed, ce = out["seed_knowledge"], out["corpus_evidence"]
    rows = "".join(
        f'<tr><td>{_esc(r["formula"])}</td><td>{_esc(r["dose_processing"])}</td>'
        f'<td><span class="cid">{r["clause_id"]}</span></td></tr>'
        for r in ce.get("formulas", [])[:8])
    pairs = "、".join(f'{p["paired_with"]}（{p["n_formulas_together"]}方）'
                     for p in ce.get("frequent_pairs", [])[:5])
    procs = "、".join(f'{p["form"]}×{p["n"]}'
                     for p in ce.get("processing_forms", [])[:5])
    return (f'<div class="consensus-box"><h4>🌿 {_esc(out["herb"])} · 藥解知識卡</h4>'
            f'<div class="hyp-row">{_layer_badge("D")}<b>性味</b> {_esc(seed["nature_flavor"])}'
            f' ｜ <b>功效</b> {_esc("、".join(seed["functions"]) or "—")}'
            f' ｜ 類別 {_esc(seed["category"] or "—")}（本草通識）</div>'
            f'<div class="hyp-row">{_layer_badge("A")}<b>傷寒論內證</b>：'
            f'見於 {ce["n_formula_occurrences"]} 方'
            + (f'；炮製 {procs}' if procs else "") + '</div>'
            f'<table class="diff-table"><tr><th>方劑</th><th>劑量·炮製</th>'
            f'<th>條文</th></tr>{rows}</table>'
            + (f'<div class="hyp-row"><b>高頻配伍</b>：{_esc(pairs)}</div>' if pairs else "")
            + '</div>' + _flags_html(out.get("cautions", []))
            + f'<div class="section-note">{_esc(out.get("hint", ""))}</div>')


def _decoction_html(d: Dict) -> str:
    media = "、".join(m["text"] for m in d.get("media", [])[:2])
    steps = "".join(
        f'<tr><td>{i}</td><td>{_esc(s["method"])}</td><td>{_esc(s["target"])}</td>'
        f'<td class="ctext" style="font-size:.84rem">「{_esc(s["span"][:26])}」</td></tr>'
        for i, s in enumerate(d.get("steps", []), 1))
    sv = d.get("service", {})
    svc = "；".join((sv.get("per_dose", [])[:1] + sv.get("frequency", [])[:2]
                    + sv.get("temperature", [])[:1]))
    care = "；".join(sv.get("diet_and_care", [])[:4])
    stop = "；".join(sv.get("stop_rules", [])[:2])
    adj = "；".join(sv.get("adjustments", [])[:2])
    generic = "".join(f'<div class="section-note">（兜底通則 D層）'
                      f'{_esc(g["herb"])}：{_esc(g["rule"])}</div>'
                      for g in d.get("generic_rules", [])[:3])
    return (f'<div class="consensus-box"><h4>🫖 {_esc(d.get("formula", ""))} · 煎服法'
            f'（A 方後原文 <span class="cid">{d.get("clause_id", "")}</span>）</h4>'
            f'<div class="hyp-row"><b>{_esc(d.get("dosage_form", ""))}</b> · '
            f'{_esc(d.get("route", ""))}'
            + (f' ｜ 介質 {_esc(media)}' if media else "")
            + (f' ｜ 火候 {_esc("、".join(d.get("fire", [])[:1]))}' if d.get("fire") else "")
            + (f' ｜ 煮取 {_esc("、".join(d.get("boil_to", [])[:1]))}' if d.get("boil_to") else "")
            + '</div>'
            + (f'<table class="diff-table"><tr><th>#</th><th>操作</th><th>對象</th>'
               f'<th>原文依據</th></tr>{steps}</table>' if steps else "")
            + (f'<div class="hyp-row"><b>服法</b>：{_esc(svc)}</div>' if svc else "")
            + (f'<div class="hyp-row"><b>將息禁忌</b>：{_esc(care)}</div>' if care else "")
            + (f'<div class="hyp-row"><b>中病即止</b>：{_esc(stop)}</div>' if stop else "")
            + (f'<div class="hyp-row"><b>強羸加減</b>：{_esc(adj)}</div>' if adj else "")
            + '</div>' + generic + _flags_html(d.get("safety_flags", [])))


def tool_decoction(formula):
    if not (formula or "").strip():
        return '<div class="section-note">選擇或輸入方名。</div>'
    out = _registry().call("shanghan_decoction", {"formula": formula})
    if out.get("error"):
        cand = "、".join(out.get("candidates", []))
        return (f'<div class="ask-box">⚠️ {_esc(out["error"])}'
                + (f'<br>候選：{_esc(cand)}' if cand else "") + '</div>')
    return _decoction_html(out)


def tool_formula_card(formula):
    """方劑知識卡：組成+藥解+君臣佐使+配伍+病機治法+方義+煎服+安全+證據."""
    if not (formula or "").strip():
        return '<div class="section-note">選擇或輸入方名，生成完整方劑知識卡。</div>'
    out = _registry().call("shanghan_formula_explain", {"formula": formula})
    if out.get("error"):
        cand = "、".join(out.get("candidates", []))
        return (f'<div class="ask-box">⚠️ {_esc(out["error"])}'
                + (f'<br>候選：{_esc(cand)}' if cand else "") + '</div>')
    ev = out.get("evidence_trace", {})
    comp_rows = "".join(
        f'<tr><td class="ctext">{_esc(r["herb"])}</td>'
        f'<td>{_esc(r["dose_processing"])}</td>'
        f'<td>{_esc(r["nature"])}</td>'
        f'<td>{_esc("、".join(r["functions"][:3]) or "—")}</td></tr>'
        for r in out.get("composition", []))
    roles = out.get("roles", {})
    role_rows = "".join(
        f'<tr><td>{_esc(a["herb"])}</td><td><b>{_esc(a["role"])}</b></td>'
        f'<td>{_esc(a["basis"])}</td><td>{a.get("confidence", "")}</td></tr>'
        for a in roles.get("assignments", []))
    pair_rows = "".join(
        f'<div class="hyp-row"><b>{"×".join(p["pair"])}</b>：同見 '
        f'{p["n_formulas_together"]} 方'
        + (f'（如 {_esc("、".join(p["also_seen_in"][:2]))}）' if p.get("also_seen_in") else "")
        + f'；{_esc(p["synergy_note"])}</div>'
        for p in out.get("pairing", [])[:4])
    pt = out.get("pathogenesis_therapy", {})
    sup = " ".join(f'<span class="cid">{c}</span>'
                   for c in ev.get("supporting_clauses", [])[:5])
    parts = [
        f'<div class="consensus-box"><h4>📇 {_esc(out["formula"])} · 方劑知識卡'
        f'（{_esc(out.get("source", ""))}）</h4>'
        f'<div class="hyp-row">{_layer_badge("A")}<b>組成</b>（方後原文 '
        f'<span class="cid">{ev.get("block_clause_id", "")}</span>）</div>'
        f'<table class="diff-table"><tr><th>藥</th><th>劑量·炮製(A)</th>'
        f'<th>性味(D)</th><th>功效(D)</th></tr>{comp_rows}</table></div>',
        f'<div class="consensus-box"><h4>⚖️ 君臣佐使（{_esc(roles.get("layer", "")[:22])}…）</h4>'
        f'<table class="diff-table"><tr><th>藥</th><th>角色</th><th>推導依據</th>'
        f'<th>置信</th></tr>{role_rows}</table>'
        f'<div class="section-note">方法：{_esc(roles.get("method", ""))}</div></div>',
    ]
    if pair_rows:
        parts.append(f'<div class="consensus-box"><h4>🔗 配伍分析</h4>{pair_rows}</div>')
    parts.append(
        f'<div class="consensus-box"><h4>🧬 病機與治法（D 層歸納）</h4>'
        f'<div class="hyp-row"><b>方證</b>：{_esc(pt.get("core_pattern", "") or "—")}'
        f'；<b>核心證</b>：{_esc("、".join(pt.get("core_symptoms", [])[:5]) or "—")}</div>'
        f'<div class="hyp-row"><b>治法</b>：'
        f'{_esc("、".join(pt.get("therapeutic_methods", [])) or "—")}'
        f' ｜ <b>證據</b>：{sup or "—"}</div>'
        f'<div class="hyp-row"><b>方義</b>：{_esc(out.get("explanation", ""))}</div></div>')
    parts.append(_decoction_html(out.get("decoction", {})))
    mm = out.get("modern_mapping", {})
    parts.append(f'<div class="section-note">現代機制映射：{_esc(mm.get("note", ""))}</div>')
    return "".join(parts)


# ═══════════════════════════════════════════════════════════════════
# benchmarks tab
# ═══════════════════════════════════════════════════════════════════
def load_benchmarks():
    from .. import config
    p = config.SHANGHAN_DIR / "eval" / "eval_summary.json"
    if not p.exists():
        return ('<div class="section-note">評測尚未運行：點擊「重跑智能體基準」或在'
                ' CLI 執行 <code>python3 -m hermes_shanghan evaluate</code>。</div>')
    s = json.loads(p.read_text(encoding="utf-8")).get("suites", {})
    parts = []
    head = (s.get("agent") or {}).get("headline") or {}
    if head:
        parts.append('<div class="section-note"><b>智能體基準</b>（路由/接地/鑒別覆蓋/安全）</div>')
        parts.append(stat_tiles(head))
    cz = ((s.get("cloze") or {}).get("metrics") or {}).get("attainable") or {}
    if cz:
        parts.append('<div class="section-note"><b>遮方預測</b>（LOCO 自監督）</div>')
        parts.append(stat_tiles({k: cz[k] for k in ("top1", "top3", "mrr", "herb_f1")
                                 if k in cz}))
    gr_ = (s.get("grounding") or {}).get("metrics") or {}
    if gr_:
        parts.append('<div class="section-note"><b>證據接地率</b></div>')
        parts.append(stat_tiles(gr_))
    return "".join(parts)


def rerun_agent_bench():
    from ..eval.agent_bench import run_agent_benchmarks
    res = run_agent_benchmarks()
    return ('<div class="section-note"><b>智能體基準 · 即時重跑</b></div>'
            + stat_tiles(res["headline"]))


# ═══════════════════════════════════════════════════════════════════
# app assembly
# ═══════════════════════════════════════════════════════════════════
try:                                # keep module importable without gradio
    import gradio as gr
except ImportError:                 # pragma: no cover
    gr = None


def _theme():
    rose = gr.themes.Color(
        c50="#FDF8F8", c100="#FBEDEE", c200="#F7D8DA", c300="#F2C4C7",
        c400="#EBA9AD", c500="#DE8B8F", c600="#C96B72", c700="#A94E57",
        c800="#873B44", c900="#6B2E37", c950="#4A1E26", name="rose_quartz")
    lavender = gr.themes.Color(
        c50="#F8F8FD", c100="#EFEFFA", c200="#E1E2F4", c300="#CDCFEA",
        c400="#B0B3DC", c500="#9296CB", c600="#787CB8", c700="#62659E",
        c800="#4E5180", c900="#3F4267", c950="#2A2C45", name="serenity")
    return gr.themes.Soft(
        primary_hue=rose, secondary_hue=lavender, neutral_hue=gr.themes.colors.stone,
        radius_size=gr.themes.sizes.radius_lg,
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"])


def build_app():
    """Assemble and return the Gradio Blocks app（不啟動）."""
    if gr is None:                  # pragma: no cover
        raise ImportError("Gradio 未安裝：pip install 'hermes-shanghan[webui]' "
                          "或 pip install gradio")
    try:
        formulas = sorted(r.formula for r in _registry().art.formula_rules)
    except Exception:               # artifacts not built yet
        formulas = []
    channels = ["", "太陽病", "陽明病", "少陽病", "太陰病", "少陰病", "厥陰病"]

    # Gradio 6 moved theme/css/head to launch(); style_kwargs() supplies them
    with gr.Blocks(title=f"{APP_TITLE} · {BRAND_CN}") as app:
        gr.HTML(HERO)
        sessions = gr.State({})
        export_log = gr.State([])

        # ── Tab 1 · 對話研習 ────────────────────────────────────
        with gr.Tab("💬 對話研習"):
            with gr.Row():
                with gr.Column(scale=7):
                    chatbot = gr.Chatbot(label="智能體對話（每答皆過引用核驗）",
                                         height=520, elem_id="hermes-chat",
                                         placeholder="**傷寒·赫爾墨斯** 恭候垂詢——"
                                                     "方證、鑒別、劑量、注家、誤治皆可。")
                    with gr.Row():
                        msg = gr.Textbox(show_label=False, scale=8, lines=1,
                                         placeholder="如：病人惡寒發熱無汗身疼痛，脈浮緊，考慮什麼方？")
                        send = gr.Button("送出 ✦", variant="primary", scale=1)
                    with gr.Row():
                        role = gr.Radio(list(ROLES), value="醫師", label="角色（患者端硬隔離）")
                        mode = gr.Radio(list(MODES), value="單智能體", label="智能體模式")
                    with gr.Row():
                        clear = gr.Button("清空會話", size="sm")
                        exp_md = gr.Button("導出 Markdown ⬇", size="sm")
                        exp_js = gr.Button("導出 JSON ⬇", size="sm")
                    exp_file = gr.File(label="導出文件", visible=True, height=64)
                    gr.Examples(
                        examples=[
                            ["桂枝湯與麻黃湯如何鑒別？各自劑量比是多少？"],
                            ["少陰病寒化與熱化怎麼區分？分別有哪些主方和條文依據？"],
                            ["病人往來寒熱、胸脅苦滿、口苦，考慮什麼方？會不會誤下成壞病？"],
                            ["注家對第12條有何分歧？"],
                            ["我能不能喝桂枝湯？（患者角色示範安全攔截）"]],
                        inputs=[msg], label="示例問題")
                with gr.Column(scale=5):
                    status = gr.Markdown("等待提問——右側面板將展示證據與推理過程。")
                    with gr.Tab("📜 檢索原文"):
                        p_evidence = gr.HTML(clause_cards_html([]))
                    with gr.Tab("🔬 多假設"):
                        p_hyp = gr.HTML(hypotheses_html(None))
                    with gr.Tab("⚖️ 合議"):
                        p_cons = gr.HTML(consensus_html(None))
                    with gr.Tab("✅ 核驗"):
                        p_cite = gr.HTML('<div class="section-note">尚無核驗記錄。</div>')
                    with gr.Tab("🧭 軌跡"):
                        p_trace = gr.JSON(label="agent trace / council timeline")

            def _turn(message, history, role_label, mode_label, sess, log):
                (history, cleared, sess, log, ev, hyp, cons, cite,
                 meta) = chat_turn(message, history, role_label, mode_label,
                                   sess, log)
                return (history, cleared, sess, log, ev, hyp, cons, cite,
                        meta["trace"], meta["status"])

            outs = [chatbot, msg, sessions, export_log, p_evidence, p_hyp,
                    p_cons, p_cite, p_trace, status]
            send.click(_turn, [msg, chatbot, role, mode, sessions, export_log], outs)
            msg.submit(_turn, [msg, chatbot, role, mode, sessions, export_log], outs)
            clear.click(lambda: ([], {}, [], "會話已清空。"),
                        outputs=[chatbot, sessions, export_log, status])
            exp_md.click(lambda log: export_conversation(log, "md"),
                         [export_log], [exp_file])
            exp_js.click(lambda log: export_conversation(log, "json"),
                         [export_log], [exp_file])

        # ── Tab 2 · 深度研究 ────────────────────────────────────
        with gr.Tab("🔭 深度研究"):
            gr.Markdown("**DeepResearcher** · 研究問題細化 → 六維度取證 → 缺口報告；"
                        "檔案可導出直接服務論文。")
            with gr.Row():
                topic = gr.Textbox(label="研究主題", scale=6,
                                   placeholder="桂枝湯類方的劑量演化")
                rounds = gr.Slider(1, 5, value=3, step=1, label="最大輪次", scale=2)
                run_btn = gr.Button("啟動研究 ✦", variant="primary", scale=2)
            dossier_html = gr.HTML()
            with gr.Row():
                dossier_md = gr.File(label="檔案 Markdown", height=64)
                dossier_json = gr.File(label="檔案 JSON", height=64)
            run_btn.click(run_research, [topic, rounds],
                          [dossier_html, dossier_md, dossier_json])

        # ── Tab 3 · 方證工具台 ──────────────────────────────────
        with gr.Tab("⚗️ 方證工具台"):
            with gr.Tab("全景檢索"):
                gr.Markdown('<div class="section-note">字詞 BM25 + 本體同義擴展'
                            '（水腫→腫滿/溢飲）+ 條文圖譜 + 現代表型映射'
                            '（骨質疏鬆→骨痿/骨痹，帶等級與免責）+ 笈成全庫旁證'
                            '（可選）——每條命中標注證據類型與毫秒級用時</div>')
                with gr.Row():
                    o_q = gr.Textbox(label="檢索詞（古籍詞或現代疾病皆可）", scale=5,
                                     placeholder="骨質疏鬆 / 水腫 / 往來寒熱")
                    o_k = gr.Slider(4, 15, value=8, step=1, label="Top-K", scale=2)
                    o_lib = gr.Checkbox(label="含全庫旁證", scale=1)
                    o_btn = gr.Button("檢索 ✦", variant="primary", scale=1)
                o_out = gr.HTML()
                o_btn.click(tool_omni, [o_q, o_k, o_lib], [o_out])
            with gr.Tab("原文檢索"):
                with gr.Row():
                    s_q = gr.Textbox(label="檢索詞", scale=5, placeholder="往來寒熱")
                    s_k = gr.Slider(3, 15, value=6, step=1, label="Top-K", scale=2)
                    s_ch = gr.Dropdown(channels, label="六經過濾", scale=2)
                    s_ex = gr.Checkbox(label="關係擴展", scale=1)
                    s_btn = gr.Button("檢索", variant="primary", scale=1)
                s_out = gr.HTML()
                s_btn.click(tool_search, [s_q, s_k, s_ch, s_ex], [s_out])
            with gr.Tab("條文全息"):
                with gr.Row():
                    h_ref = gr.Textbox(label="條文號 / clause_id", scale=6,
                                       placeholder="12 或 SHL_SONGBEN_0012")
                    h_btn = gr.Button("查閱", variant="primary", scale=1)
                h_out = gr.HTML()
                h_btn.click(tool_holo, [h_ref], [h_out])
            with gr.Tab("方證對應"):
                gr.Markdown('<div class="section-note">八段式對應推理：症狀→'
                            '病機結構(D/E,依據可見)→治法→候選方多維評分（分解'
                            '透明）→關係分級（主之→A級,原文標記推導）→類方鑒別'
                            '→追問→邊界。支持現代疾病入口。</div>')
                with gr.Row():
                    co_sym = gr.Textbox(label="症狀", scale=4,
                                        placeholder="發熱、汗出、惡風")
                    co_pul = gr.Textbox(label="脈象", scale=2, placeholder="脈浮緩")
                    co_ch = gr.Dropdown(channels, label="六經", scale=2)
                    co_mod = gr.Textbox(label="或現代疾病", scale=2,
                                        placeholder="骨質疏鬆")
                    co_btn = gr.Button("對應分析 ✦", variant="primary", scale=1)
                co_out = gr.HTML()
                co_btn.click(tool_correspondence,
                             [co_sym, co_pul, co_ch, co_mod], [co_out])
            with gr.Tab("多假設匹配"):
                with gr.Row():
                    m_sym = gr.Textbox(label="症狀（頓號/逗號分隔）", scale=4,
                                       placeholder="惡寒、發熱、無汗、身疼痛")
                    m_pul = gr.Textbox(label="脈象", scale=2, placeholder="脈浮緊")
                    m_ch = gr.Dropdown(channels, label="六經", scale=2)
                    m_k = gr.Slider(2, 6, value=4, step=1, label="假設數", scale=1)
                    m_btn = gr.Button("分析", variant="primary", scale=1)
                m_out = gr.HTML()
                m_btn.click(tool_hypotheses, [m_sym, m_pul, m_ch, m_k], [m_out])
            with gr.Tab("方劑知識卡"):
                gr.Markdown('<div class="section-note">組成(A)→藥解(D)→君臣佐使'
                            '(D/E 透明推導)→配伍(A錨定共現)→病機治法(D)→方義→'
                            '煎服法(A方後原文)→安全審校→證據鏈</div>')
                with gr.Row():
                    fc_f = gr.Dropdown(formulas, label="方劑",
                                       allow_custom_value=True, scale=5)
                    fc_btn = gr.Button("生成知識卡 ✦", variant="primary", scale=1)
                fc_out = gr.HTML()
                fc_btn.click(tool_formula_card, [fc_f], [fc_out])
            with gr.Tab("藥解"):
                with gr.Row():
                    hb_n = gr.Textbox(label="藥名", scale=5,
                                      placeholder="桂枝 / 附子 / 阿膠")
                    hb_btn = gr.Button("藥解", variant="primary", scale=1)
                hb_out = gr.HTML()
                hb_btn.click(tool_herb, [hb_n], [hb_out])
            with gr.Tab("煎服法"):
                with gr.Row():
                    dc_f = gr.Dropdown(formulas, label="方劑",
                                       allow_custom_value=True, scale=5)
                    dc_btn = gr.Button("解析煎服法", variant="primary", scale=1)
                dc_out = gr.HTML()
                dc_btn.click(tool_decoction, [dc_f], [dc_out])
            with gr.Tab("方證鑒別"):
                with gr.Row():
                    d_f1 = gr.Dropdown(formulas, label="方一", allow_custom_value=True)
                    d_f2 = gr.Dropdown(formulas, label="方二", allow_custom_value=True)
                    d_f3 = gr.Dropdown([""] + formulas, label="方三（可選）",
                                       allow_custom_value=True)
                    d_btn = gr.Button("鑒別", variant="primary")
                d_out = gr.HTML()
                d_btn.click(tool_differential, [d_f1, d_f2, d_f3], [d_out])
            with gr.Tab("劑量計量"):
                with gr.Row():
                    do_f = gr.Dropdown([""] + formulas, label="方劑",
                                       allow_custom_value=True)
                    do_c = gr.Textbox(label="劑量換算（可選）", placeholder="三兩 / 半升")
                    do_btn = gr.Button("查詢", variant="primary")
                do_out = gr.HTML()
                do_btn.click(tool_dose, [do_f, do_c], [do_out])
            with gr.Tab("禁忌檢查"):
                with gr.Row():
                    c_f = gr.Dropdown(formulas, label="方劑", allow_custom_value=True)
                    c_s = gr.Textbox(label="病人證候（可選）", placeholder="無汗、煩躁")
                    c_btn = gr.Button("檢查", variant="primary")
                c_out = gr.HTML()
                c_btn.click(tool_contra, [c_f, c_s], [c_out])

        # ── Tab 4 · 評測基準 ────────────────────────────────────
        with gr.Tab("📊 評測基準"):
            gr.Markdown("四套件：遮方預測（LOCO）· 醫案回放 · 證據接地率 · 智能體基準"
                        "（路由/接地/鑒別覆蓋/安全）——全部零人工標註、確定性可復現。")
            with gr.Row():
                bench_load = gr.Button("載入評測結果", variant="primary")
                bench_rerun = gr.Button("重跑智能體基準（約1分鐘）")
            bench_out = gr.HTML(load_benchmarks())
            bench_load.click(load_benchmarks, [], [bench_out])
            bench_rerun.click(rerun_agent_bench, [], [bench_out])

        # ── Tab 5 · 關於 ────────────────────────────────────────
        with gr.Tab("🏛 關於"):
            gr.Markdown(f"""
### {BRAND_CN} · {BRAND_EN}

**傷寒·赫爾墨斯（Hermes-Shanghanlun）** 是面向《傷寒論》的證據回源智能體平台：
宋本 398 條原文為唯一 A 層證據，經六道審核閘門產出可回源規則庫；智能體的每一個
回答都經過 **引用核驗（clause_id 級）** 與 **句級證據綁定（claim 級）**。

| 證據層級 | 含義 |
|---|---|
| **A** | 原文直述（宋本條文，可逐字回源） |
| **B** | 版本異文（桂林古本 / 千金翼方對勘） |
| **C** | 注家解釋（九部注本對齊） |
| **D** | 後世歸納（跨條規則，錨定 A 層） |
| **E** | 模型推理（病機類術語一律降層標注） |

**安全承諾**：患者角色在能力面即被隔離——方證匹配、組成、劑量類工具對患者會話
不存在；危險徵象觸發紅旗分診，就醫提示先於一切模型調用。

> 本平台僅供學術研究、教學與醫師輔助參考，不構成醫療建議。
""")
        gr.HTML(FOOTER)
    return app


# ═══════════════════════════════════════════════════════════════════
# launchers
# ═══════════════════════════════════════════════════════════════════
def style_kwargs() -> Dict:
    """Rose-quartz styling, passed to launch() per the Gradio 6 API."""
    return {"theme": _theme(), "css": CSS, "head": HEAD}


def launch_webui(share: Optional[bool] = None, ngrok_token: Optional[str] = None,
                 port: int = 7860, inline: bool = False, quiet: bool = True):
    """Launch the studio.

    * ``ngrok_token`` 提供時經 pyngrok 建立公網隧道並打印訪問鏈接；
    * 否則在 Colab/無公網環境用 ``share=True``（gradio 官方鏈接）；
    * 本地默認僅開 127.0.0.1:port。
    Returns the (app, public_url) tuple.
    """
    app = build_app()
    public_url = None
    if ngrok_token:
        from pyngrok import ngrok                    # optional dependency
        ngrok.set_auth_token(ngrok_token.strip())
        public_url = ngrok.connect(port, "http").public_url
        print(f"🌐 ngrok 公網鏈接：{public_url}")
        share = False
    if share is None:
        share = _in_colab() and not ngrok_token
    app.launch(share=share, server_port=port, inline=inline, quiet=quiet,
               prevent_thread_lock=bool(ngrok_token) or inline,
               **style_kwargs())
    if public_url:
        print(f"🌐 訪問：{public_url}")
    return app, public_url


def _in_colab() -> bool:
    try:
        import google.colab                          # noqa: F401
        return True
    except ImportError:
        return False
