import html
import io
import json
import logging
import math
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Internal Module Imports (unchanged)
from src.formatting import describe_start
from src.core.optimizer import WorkloadOptimizer
from src.core.comparator import ResultsComparator
from src.agent.explainer import ReasonExplainer
from src.core.data_trust import DataTrustManager
from src.core.exporter import AuditExporter
from src.core.handoff import DevOpsHandoff
from src.core.pausable_optimizer import PausableOptimizer

try:
    from src.formatting import indian_number, inr
except ImportError:  # older formatting module
    def indian_number(x):
        return f"{x:,.0f}"

    def inr(x):
        return f"₹{x:,.0f}"

logger = logging.getLogger("sunshift")

st.set_page_config(page_title="Sunshift", layout="wide", initial_sidebar_state="collapsed")

# =====================================================================================
# State
# =====================================================================================
PRIORITY_DEFAULTS = {"cost": 70, "carb": 80, "wat": 60}
for _k, _v in PRIORITY_DEFAULTS.items():
    st.session_state.setdefault(f"{_k}_sld", _v)
    st.session_state.setdefault(f"{_k}_num", _v)
for _k, _v in {"busy": False, "run": None, "error": None, "pending_inputs": None}.items():
    st.session_state.setdefault(_k, _v)


def sync_widgets(src_key: str, dst_key: str):
    """Keep a slider and its number box in step (runs before the rerun)."""
    st.session_state[dst_key] = st.session_state[src_key]


# =====================================================================================
# Styling
# =====================================================================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inria+Serif:wght@400;700&family=Inter:wght@400;500;600&display=swap');
:root{
  --bg:#F6F1E7; --surface:#FFFDF8; --surface-2:#FAF5EA; --ink:#211D18; --ink-2:#5A5348; --muted:#8B8376;
  --line:#E5DCCB; --line-2:#EFE8D8; --amber:#B76A00; --amber-d:#975800; --amber-l:#F5E6C8;
  --green:#3E7A56; --green-l:#E4EFE7; --red:#B03A2E; --red-l:#F7E4E0; --char:#262019;
}
.stApp{background:var(--bg);}
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li, .stApp td, .stApp th,
.stApp div[data-baseweb="select"], .sx{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;}
.sx-serif{font-family:'Inria Serif',Georgia,serif !important;}
.block-container{padding-top:1rem;padding-bottom:3rem;max-width:1400px;}
#MainMenu, footer, header[data-testid="stHeader"]{visibility:hidden;height:0;}
.stApp h1,.stApp h2,.stApp h3{font-family:'Inria Serif',Georgia,serif;color:var(--ink);}

/* ---------- top bar ---------- */
.sx-nav{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding:14px 4px 16px;border-bottom:1px solid var(--line);margin-bottom:22px;}
.sx-brand{display:flex;align-items:center;gap:12px;}
.sx-mark{width:26px;height:26px;border-radius:7px;background:var(--amber);position:relative;flex:none;}
.sx-mark:after{content:"";position:absolute;inset:7px;border-radius:50%;background:var(--bg);}
.sx-word{font-family:'Inria Serif',Georgia,serif;font-size:25px;font-weight:700;color:var(--ink);line-height:1;}
.sx-tag{font-size:13px;color:var(--ink-2);padding-left:14px;border-left:1px solid var(--line);}
.sx-nav-r{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}

/* ---------- chips ---------- */
.sx-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;
  border:1px solid var(--line);background:var(--surface);color:var(--ink-2);white-space:nowrap;}
.sx-chip.green{background:var(--green-l);border-color:#C7DDCE;color:var(--green);}
.sx-chip.amber{background:var(--amber-l);border-color:#E9D2A4;color:var(--amber-d);}
.sx-chip.red{background:var(--red-l);border-color:#EBC5BE;color:var(--red);}
.sx-chip.dark{background:rgba(246,241,231,.10);border-color:rgba(246,241,231,.22);color:#F6F1E7;}
.sx-chip.dark.green{background:rgba(120,190,150,.16);border-color:rgba(120,190,150,.4);color:#BFE3CD;}
.sx-chip.dark.red{background:rgba(220,110,95,.16);border-color:rgba(220,110,95,.45);color:#F2B8AE;}
.sx-dot{width:7px;height:7px;border-radius:50%;background:currentColor;display:inline-block;}

/* ---------- input panel (bordered container, matched through an invisible marker) ---------- */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sx-panel):not(:has(div[data-testid="stVerticalBlockBorderWrapper"] .sx-panel)){
  background:var(--surface);border:1px solid var(--line) !important;border-radius:16px;padding:8px 10px 12px;}
.sx-sec{display:flex;align-items:center;gap:10px;margin:18px 0 6px;}
.sx-sec:first-child{margin-top:6px;}
.sx-sec b{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink);font-weight:600;}
.sx-sec i{flex:1;height:1px;background:var(--line);}
.sx-sec span.n{width:20px;height:20px;border-radius:50%;background:var(--ink);color:var(--bg);font-size:11px;font-weight:600;
  display:inline-flex;align-items:center;justify-content:center;}
.sx-note{font-size:12.5px;color:var(--ink-2);line-height:1.45;margin:2px 0 8px;}
.sx-prio{font-size:13px;font-weight:600;color:var(--ink);margin:10px 0 0;display:flex;justify-content:space-between;}
.sx-prio em{font-style:normal;font-weight:500;color:var(--muted);font-variant-numeric:tabular-nums;}
.sx-split{display:flex;height:8px;border-radius:99px;overflow:hidden;margin:12px 0 4px;background:var(--line-2);}
.sx-split div{height:100%;}

/* ---------- widgets ---------- */
[data-testid="stWidgetLabel"] p, .stApp label p{font-size:13px;font-weight:600;color:var(--ink);}
div[data-baseweb="input"], div[data-baseweb="select"] > div{background:var(--surface-2) !important;border:1px solid var(--line) !important;border-radius:10px !important;}
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within{border-color:var(--amber) !important;box-shadow:0 0 0 3px rgba(183,106,0,.18);}
div[data-baseweb="input"] input{font-variant-numeric:tabular-nums;}
[data-testid="stThumbValue"], [data-testid="stSliderThumbValue"], [data-testid="stTickBar"]{display:none !important;}
div[role="radiogroup"]{gap:0 !important;width:100%;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface-2);}
div[role="radiogroup"] > label{flex:1;justify-content:center;margin:0 !important;padding:9px 0;cursor:pointer;}
div[role="radiogroup"] > label > div:first-child{display:none;}
div[role="radiogroup"] > label:has(input:checked){background:var(--ink);}
div[role="radiogroup"] > label:has(input:checked) p{color:var(--bg) !important;}
button[kind="primary"], button[data-testid="stBaseButton-primary"]{background:var(--amber) !important;color:#fff !important;border:1px solid var(--amber-d) !important;
  border-radius:10px !important;font-weight:600 !important;min-height:46px;transition:background .15s ease;}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover{background:var(--amber-d) !important;}
button[kind="primary"]:disabled, button[data-testid="stBaseButton-primary"]:disabled{opacity:.55;cursor:not-allowed;}
[data-testid="stDownloadButton"] button{background:var(--surface) !important;color:var(--ink) !important;border:1px solid var(--ink) !important;border-radius:10px !important;font-weight:600;}
[data-testid="stDownloadButton"] button:hover{background:var(--ink) !important;color:var(--bg) !important;}
button:focus-visible, input:focus-visible, [role="tab"]:focus-visible, summary:focus-visible{outline:2px solid var(--amber) !important;outline-offset:2px;}
button[data-baseweb="tab"]{font-weight:600;color:var(--ink-2);}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--ink);}
div[data-baseweb="tab-highlight"]{background-color:var(--amber) !important;}
div[data-baseweb="tab-border"]{background-color:var(--line) !important;}
[data-testid="stExpander"]{border:1px solid var(--line) !important;border-radius:12px !important;background:var(--surface);}
[data-testid="stCode"], .stCodeBlock{border:1px solid var(--line);border-radius:12px;}

/* ---------- cards ---------- */
.sx-card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin:0 0 16px;}
.sx-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px;}
.sx-h h3{margin:0;font-size:19px;font-weight:700;}
.sx-h span{font-size:12.5px;color:var(--muted);}
.sx-cap{font-size:12.5px;color:var(--ink-2);line-height:1.5;margin-top:10px;}

/* ---------- hero ---------- */
.sx-hero{background:var(--char);color:#F6F1E7;border-radius:18px;padding:28px;display:flex;flex-wrap:wrap;gap:28px;margin-bottom:16px;}
.sx-hero-l{flex:1 1 360px;min-width:0;display:flex;flex-direction:column;gap:14px;}
.sx-eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;font-weight:600;color:#E9B866;}
.sx-hero h2{font-family:'Inria Serif',Georgia,serif;font-size:clamp(28px,3.1vw,40px);line-height:1.1;margin:0;color:#FBF7EE;font-weight:700;}
.sx-hero p{margin:0;color:#D9D2C3;font-size:14.5px;line-height:1.55;}
.sx-hero small{color:#A59D8E;font-size:12px;}
.sx-chips{display:flex;gap:8px;flex-wrap:wrap;}
.sx-hero-r{flex:1 1 420px;min-width:0;display:grid;grid-template-columns:repeat(3,minmax(120px,1fr));gap:0;align-self:stretch;}
.sx-kpi{padding:2px 18px;border-left:1px solid rgba(246,241,231,.16);display:flex;flex-direction:column;gap:6px;justify-content:center;}
.sx-kpi:first-child{border-left:0;padding-left:0;}
.sx-kpi .l{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#A59D8E;font-weight:600;}
.sx-kpi .v{font-family:'Inria Serif',Georgia,serif;font-size:clamp(24px,2.3vw,31px);font-weight:700;line-height:1.05;white-space:nowrap;color:#FBF7EE;}
.sx-kpi .s{font-size:12.5px;color:#D9D2C3;}
.sx-kpi .p{font-size:12.5px;font-weight:600;}
.sx-kpi .p.g{color:#8FD0A9;} .sx-kpi .p.r{color:#F2A598;} .sx-kpi .p.n{color:#B8B0A0;}
.sx-kpi .f{font-size:11.5px;color:#8F8878;font-variant-numeric:tabular-nums;}

/* ---------- callouts ---------- */
.sx-call{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--line);background:var(--surface);border-radius:12px;padding:11px 14px;margin:0 0 12px;font-size:13.5px;line-height:1.5;color:var(--ink);}
.sx-call b{font-weight:600;}
.sx-call .ic{width:18px;height:18px;border-radius:50%;flex:none;margin-top:1px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;background:var(--muted);}
.sx-call.warn{background:var(--amber-l);border-color:#E9D2A4;} .sx-call.warn .ic{background:var(--amber);}
.sx-call.bad{background:var(--red-l);border-color:#EBC5BE;} .sx-call.bad .ic{background:var(--red);}
.sx-call.ok{background:var(--green-l);border-color:#C7DDCE;} .sx-call.ok .ic{background:var(--green);}

/* ---------- table ---------- */
.sx-table{width:100%;border-collapse:collapse;font-size:14px;}
.sx-table th{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;text-align:left;padding:0 10px 10px;}
.sx-table td{padding:12px 10px;border-top:1px solid var(--line-2);vertical-align:top;font-variant-numeric:tabular-nums;color:var(--ink);}
.sx-table td.k{color:var(--ink-2);font-weight:500;}
.sx-table td.r, .sx-table th.r{background:var(--surface-2);}
.sx-table th.r{color:var(--amber-d);border-top:2px solid var(--amber);padding-top:10px;}
.sx-table .big{font-family:'Inria Serif',Georgia,serif;font-size:19px;font-weight:700;}
.sx-table .sub{display:block;font-size:12px;color:var(--muted);margin-top:2px;}
.sx-table .g{color:var(--green);font-weight:600;} .sx-table .rd{color:var(--red);font-weight:600;} .sx-table .n{color:var(--ink-2);font-weight:600;}
.sx-scroll{overflow-x:auto;}

/* ---------- timeline ---------- */
.sx-tl{position:relative;margin:34px 6px 6px;}
.sx-row{display:grid;grid-template-columns:132px 1fr;gap:12px;align-items:center;margin-bottom:10px;}
.sx-row .t{font-size:12.5px;font-weight:600;color:var(--ink);line-height:1.25;}
.sx-row .t small{display:block;font-weight:400;color:var(--muted);}
.sx-track{position:relative;height:30px;border-radius:8px;background:repeating-linear-gradient(135deg,#F1EADB,#F1EADB 6px,#EBE2D0 6px,#EBE2D0 12px);overflow:hidden;border:1px solid var(--line);}
.sx-band{position:absolute;top:0;bottom:0;}
.sx-band.solar{background:rgba(231,178,76,.34);} .sx-band.peak{background:rgba(176,58,46,.20);}
.sx-run{position:absolute;top:5px;bottom:5px;border-radius:5px;background:var(--char);}
.sx-axis{position:relative;height:30px;margin-left:144px;}
.sx-tick{position:absolute;top:0;font-size:11px;color:var(--ink-2);transform:translateX(-50%);white-space:nowrap;text-align:center;line-height:1.2;}
.sx-tick:before{content:"";display:block;width:1px;height:6px;background:var(--line);margin:0 auto 3px;}
.sx-mk{position:absolute;top:-24px;bottom:30px;width:0;border-left:2px solid var(--red);}
.sx-mk span{position:absolute;top:-2px;transform:translateX(-100%);padding-right:6px;font-size:11px;font-weight:600;color:var(--red);white-space:nowrap;}
.sx-mk.now{border-left:2px dashed var(--ink-2);} .sx-mk.now span{transform:none;padding:0 0 0 6px;color:var(--ink-2);}
.sx-legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12px;color:var(--ink-2);margin-top:8px;}
.sx-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px;}

/* ---------- trust ---------- */
.sx-trow{display:grid;grid-template-columns:minmax(150px,1.1fr) 2fr auto;gap:6px 16px;padding:12px 0;border-top:1px solid var(--line-2);align-items:start;font-size:13.5px;}
.sx-trow:first-of-type{border-top:0;}
.sx-trow .n{font-weight:600;text-transform:capitalize;} .sx-trow .d{color:var(--ink-2);line-height:1.5;} .sx-trow .d small{display:block;color:var(--muted);}
.sx-sub{font-size:11px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;color:var(--muted);margin:20px 0 6px;}

/* ---------- empty + loading ---------- */
.sx-empty{padding:34px 30px;}
.sx-empty h2{margin:0 0 6px;font-size:28px;}
.sx-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:20px 0 6px;}
.sx-step{border:1px solid var(--line);border-radius:12px;padding:14px;background:var(--surface-2);font-size:13.5px;color:var(--ink-2);line-height:1.45;}
.sx-step b{display:block;color:var(--ink);margin:4px 0 2px;}
.sx-step span{font-size:11px;font-weight:600;color:var(--amber-d);letter-spacing:.1em;}
.sx-skel{border-radius:14px;background:linear-gradient(90deg,#EFE8D8,#F8F3E8,#EFE8D8);background-size:200% 100%;animation:sx-sh 1.4s ease-in-out infinite;}
@keyframes sx-sh{0%{background-position:200% 0}100%{background-position:-200% 0}}
@media (prefers-reduced-motion: reduce){ .sx-skel{animation:none;} }
@media (max-width:900px){ .sx-row{grid-template-columns:96px 1fr;} .sx-axis{margin-left:108px;} .sx-hero-r{grid-template-columns:1fr;} .sx-kpi{border-left:0;padding:10px 0;border-top:1px solid rgba(246,241,231,.16);} .sx-kpi:first-child{border-top:0;} }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# =====================================================================================
# Helpers
# =====================================================================================
def H(s: str) -> str:
    """Collapse an HTML snippet to one line so Markdown never turns it into a code block."""
    return " ".join(line.strip() for line in s.splitlines() if line.strip())


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def html_block(s: str):
    st.markdown(H(s), unsafe_allow_html=True)


def callout(kind: str, text: str):
    icon = {"info": "i", "warn": "!", "bad": "!", "ok": "✓"}.get(kind, "i")
    html_block(f"<div class='sx-call {kind if kind != 'info' else ''}'><span class='ic'>{icon}</span><div>{text}</div></div>")


def pct_text(exact_pct: float) -> str:
    if exact_pct <= 0:
        return "0%"
    return "<1%" if exact_pct < 1 else f"{round(exact_pct)}%"


def signed_pct(usual_val, rec_val):
    """(label, tone) for 'recommended vs usual'. Negative = lower than usual."""
    if not usual_val:
        return "—", "n"
    d = (rec_val - usual_val) / usual_val * 100
    if abs(d) < 0.5:
        return "0%", "n"
    return f"{'−' if d < 0 else '+'}{abs(round(d))}%", ("g" if d < 0 else "rd")


def fmt_start(dt: datetime) -> str:
    return dt.strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def parse_dt(value):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def as_hours(v, base: datetime):
    """number -> hours; datetime / date string -> hours since `base`; anything else -> None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, datetime):
        return (v - base).total_seconds() / 3600
    if isinstance(v, str):
        dt = parse_dt(v)
        return (dt - base).total_seconds() / 3600 if dt else None
    return None


def parse_blocks(blocks, base: datetime, horizon_h: float, expected_run_h: float, penalty_h: float):
    """
    Turn a plan's blocks into [(start_h, end_h)] relative to the plan start.
    Only returns a schedule whose total run time matches the job length, so a wrongly
    interpreted block format can never be drawn as if it were real.
    """
    def attempt(as_duration: bool):
        out = []
        for b in blocks or []:
            s = e = None
            if isinstance(b, dict):
                low = {str(k).lower(): v for k, v in b.items()}
                s = next((low[k] for k in ("start", "start_hour", "start_idx", "start_offset", "begin", "start_time") if k in low), None)
                e = next((low[k] for k in ("end", "end_hour", "end_idx", "end_offset", "stop", "end_time") if k in low), None)
                dur = next((low[k] for k in ("duration", "hours", "length", "run_hours", "duration_hours") if k in low), None)
                if e is None and dur is not None:
                    e, as_dur = dur, True
                else:
                    as_dur = False
            elif isinstance(b, (list, tuple)) and len(b) >= 2:
                s, e, as_dur = b[0], b[1], as_duration
            else:
                return None
            sh, eh = as_hours(s, base), as_hours(e, base)
            if sh is None or eh is None:
                return None
            if as_dur:
                eh = sh + eh
            if not (0 <= sh < eh <= horizon_h + 1):
                return None
            out.append((sh, eh))
        return sorted(out) if out else None

    for mode in (False, True):
        parsed = attempt(mode)
        if parsed:
            total = sum(e - s for s, e in parsed)
            if expected_run_h * 0.9 <= total <= expected_run_h * 1.15 + len(parsed) * penalty_h + 1:
                return parsed
    return None


def tariff_fn():
    phys = getattr(optimizer, "physics", None)
    return getattr(phys, "get_tod_multiplier", None)


def build_timeline(now_dt, horizon_h, rows, deadline_label):
    """rows: [(title, subtitle, [(start_h, end_h)])] on a shared axis measured in hours from `now_dt`."""
    horizon_h = max(1, int(round(horizon_h)))
    pct = lambda h: max(0.0, min(100.0, h / horizon_h * 100))
    tod = tariff_fn()

    bands = ""
    if tod:
        slots = [tod((now_dt + timedelta(hours=i)).hour) for i in range(horizon_h)]
        i = 0
        while i < len(slots):
            j = i
            while j < len(slots) and slots[j] == slots[i]:
                j += 1
            if slots[i] in ("solar", "peak"):
                bands += f"<div class='sx-band {slots[i]}' style='left:{pct(i):.3f}%;width:{pct(j) - pct(i):.3f}%'></div>"
            i = j

    track_rows = ""
    for title, sub, segs in rows:
        runs = "".join(
            f"<div class='sx-run' title='{esc(fmt_start(now_dt + timedelta(hours=s)))} → {esc(fmt_start(now_dt + timedelta(hours=e)))}' "
            f"style='left:{pct(s):.3f}%;width:{max(pct(e) - pct(s), 0.6):.3f}%'></div>" for s, e in segs)
        track_rows += f"<div class='sx-row'><div class='t'>{esc(title)}<small>{esc(sub)}</small></div><div class='sx-track'>{bands}{runs}</div></div>"

    # day ticks
    days = horizon_h / 24
    step = 1 if days <= 7 else 2 if days <= 14 else 5
    ticks, first_midnight = "", ((24 - now_dt.hour) % 24) or 24
    h, idx = first_midnight, 0
    while h < horizon_h:
        if idx % step == 0:
            d = now_dt + timedelta(hours=h)
            ticks += f"<div class='sx-tick' style='left:{pct(h):.3f}%'>{d.strftime('%a')}<br>{d.strftime('%d %b')}</div>"
        h, idx = h + 24, idx + 1

    return (f"<div class='sx-tl'><div class='sx-mk now' style='left:calc(144px + (100% - 144px) * 0)'><span>Now</span></div>"
            f"<div class='sx-mk' style='left:calc(144px + (100% - 144px) * 1)'><span>{esc(deadline_label)}</span></div>"
            f"{track_rows}<div class='sx-axis'>{ticks}</div></div>")


def trust_level(text: str):
    t = str(text)
    if t.startswith("⚠"):
        return "warn"
    if t.startswith("✅"):
        return "ok"
    return "info"


def clean_flag(text: str) -> str:
    return str(text).replace("⚠️", "").replace("✅", "").replace("ℹ️", "").replace("⚠", "").strip()


def type_badge(kind: str) -> str:
    k = str(kind).lower()
    tone = "green" if "live" in k else "amber" if ("cache" in k or "model" in k or "estimat" in k) else ""
    return f"<span class='sx-chip {tone}'>{esc(kind)}</span>"


# =====================================================================================
# Engines
# =====================================================================================
@st.cache_resource
def load_engines():
    return WorkloadOptimizer(), ReasonExplainer(), DataTrustManager(), PausableOptimizer()


try:
    optimizer, explainer, trust_manager, pause_optimizer = load_engines()
except (FileNotFoundError, RuntimeError) as _err:
    st.error(f"Sunshift could not start: {_err}")
    st.stop()


# =====================================================================================
# Computation (one request per click; the result is kept in session state)
# =====================================================================================
FALLBACK_META = {"confidence_label": "High", "finish_day": 1, "n_gpus": 48}


def compute_run(inp: dict) -> dict:
    weights_in = inp["weights"]
    results = optimizer.find_best_placement(inp["gpu_hours"], inp["deadline"], weights_in, inp["is_flexible"],
                                            usual_region=inp["usual_choice"], domestic_only=inp["data_india"])
    usual, rec = results["usual"], results["recommended"]
    meta_real = results.get("meta") or {}
    meta = results.get("meta") or {**FALLBACK_META, "deadline_days": inp["deadline"], "forecast_timestamp": datetime.now()}
    savings = ResultsComparator.calculate_savings(usual, rec)
    run = {"inputs": inp, "results": results, "usual": usual, "rec": rec, "meta": meta, "meta_real": meta_real,
           "savings": savings, "pause": None, "reason": None, "errors": {}, "computed_at": datetime.now()}

    if inp["is_pausable"]:
        try:
            pause_optimizer.penalty_hours = inp["checkpoint_penalty"] / 60.0
            test_start = datetime.strptime(rec["start_time"], "%Y-%m-%d %H:%M")
            deadline_h = meta_real.get("deadline_hours") or inp["deadline"] * 24
            # plan only the hours that remain between the recommended start and the deadline
            remaining_h = max(1, int(deadline_h - rec.get("hours_from_now", 0)))
            rates = pause_optimizer._generate_synthetic_rates(test_start, remaining_h)
            est_job_hours = max(1, math.ceil(inp["gpu_hours"] / meta.get("n_gpus", 48)))
            straight_plan = pause_optimizer.get_straight_through_plan(est_job_hours, rates)
            pause_plan = pause_optimizer.get_pausable_plan(est_job_hours, rates)
            helped = pause_plan["total_cost"] < straight_plan["total_cost"]
            chosen = pause_plan if helped else straight_plan
            run["pause"] = {"straight": straight_plan, "pausable": pause_plan, "chosen": chosen, "helped": helped,
                            "job_hours": est_job_hours, "remaining_h": remaining_h, "start": test_start,
                            "penalty_h": inp["checkpoint_penalty"] / 60.0,
                            "cron": pause_optimizer.generate_cron_snippet(chosen.get("blocks", []))}
        except Exception as exc:  # the continuous result is still valid
            logger.exception("Pause-and-resume planning failed")
            run["errors"]["pause"] = f"{type(exc).__name__}: {exc}"

    for name, fn in (
        ("trust", lambda: trust_manager.generate_trust_report(meta)),
        ("k8s", lambda: DevOpsHandoff.generate_k8s_payload(usual, rec, inp["is_flexible"], meta)),
        ("csv", lambda: AuditExporter.generate_csv(usual, rec, meta, savings, inp["gpu_hours"], inp["deadline"], inp["is_flexible"])),
    ):
        try:
            run[name] = fn()
        except Exception as exc:
            logger.exception("%s generation failed", name)
            run[name] = None
            run["errors"][name] = f"{type(exc).__name__}: {exc}"
    return run


def narrate(run: dict) -> str:
    try:
        return explainer.generate_reason(run["usual"], run["rec"], weights=run["inputs"]["weights"], meta=run["meta"])
    except TypeError:  # older explainer signature
        return explainer.generate_reason(run["usual"], run["rec"])


# =====================================================================================
# Header
# =====================================================================================
def header_html(run):
    chips = "<span class='sx-chip'>India</span><span class='sx-chip'>5 regions</span>"
    if run:
        ts = run["meta_real"].get("forecast_timestamp")
        if isinstance(ts, datetime):
            chips += f"<span class='sx-chip amber'><span class='sx-dot'></span>Forecast data: {esc(ts.strftime('%d %b, %I:%M %p'))}</span>"
    return H(f"""<div class='sx-nav'><div class='sx-brand'><div class='sx-mark'></div><div class='sx-word'>Sunshift</div>
        <div class='sx-tag'>Where and when to run flexible AI workloads</div></div><div class='sx-nav-r'>{chips}</div></div>""")


st.markdown(header_html(st.session_state.run), unsafe_allow_html=True)

# =====================================================================================
# Layout
# =====================================================================================
left_col, right_col = st.columns([1, 2.65], gap="large")

with left_col:
    with st.container(border=True):
        html_block("<span class='sx-panel'></span><div class='sx-sec'><span class='n'>1</span><b>Workload</b><i></i></div>")
        gpu_hours = st.number_input("GPU hours required", value=10000, step=1000, min_value=1, max_value=5_000_000,
                                    help="Total productive GPU-hours the job needs (for example 8 GPUs for 100 hours = 800). Supported range: 1 to 5,000,000.")
        deadline = st.number_input("Deadline (days from now)", value=5, min_value=1, max_value=30,
                                   help="The job must finish within this many days. Supported range: 1 to 30 days.")

        html_block("<div class='sx-sec'><span class='n'>2</span><b>Execution</b><i></i></div>")
        job_type = st.radio("Job type", ["Flexible", "Urgent"], horizontal=True,
                            help="Flexible lets Sunshift look up to 72 hours ahead for a better window. Urgent starts immediately and only chooses the place.")
        is_flexible = job_type == "Flexible"
        is_pausable = st.toggle("Pause and resume", value=False,
                                help="Only for jobs that save checkpoints and can resume. Sunshift will plan run blocks around cheaper hours.")
        checkpoint_penalty = 15
        if is_pausable:
            checkpoint_penalty = st.number_input("Checkpoint overhead (minutes per pause)", value=15, min_value=1, max_value=60,
                                                 help="Time lost saving and reloading a checkpoint each time the job pauses and resumes.")
            html_block("<div class='sx-note'>Your job must support checkpointing and resumption. The pause plan uses Sunshift's built-in hourly tariff profile.</div>")

        html_block("<div class='sx-sec'><span class='n'>3</span><b>Placement</b><i></i></div>")
        usual_choice = st.selectbox("Current data centre (the baseline)", ["Mumbai", "Delhi NCR", "Bengaluru", "Chennai", "Hyderabad"],
                                    help="Results are compared against starting now in this location.")
        data_india = st.toggle("Data must stay in India", value=True,
                               help="Restricts placement to the supported Indian regions.")

        html_block("<div class='sx-sec'><span class='n'>4</span><b>What matters most</b><i></i></div>")
        for key, label, tip in (("cost", "Save money", "Weight given to electricity cost."),
                                ("carb", "Cut carbon", "Weight given to estimated CO2 emissions."),
                                ("wat", "Protect water", "Weight given to estimated cooling water in water-stressed regions.")):
            html_block(f"<div class='sx-prio'>{label}<em>{st.session_state[f'{key}_sld']} / 100</em></div>")
            sc, nc = st.columns([3, 1.3])
            sc.slider(label, 0, 100, key=f"{key}_sld", on_change=sync_widgets, args=(f"{key}_sld", f"{key}_num"),
                      label_visibility="collapsed", help=tip)
            nc.number_input(f"{label} (0 to 100)", 0, 100, key=f"{key}_num", on_change=sync_widgets,
                            args=(f"{key}_num", f"{key}_sld"), label_visibility="collapsed")

        w_cost, w_carbon, w_water = (int(st.session_state.cost_sld), int(st.session_state.carb_sld), int(st.session_state.wat_sld))
        total_weight = w_cost + w_carbon + w_water
        weights = {"cost": w_cost / total_weight if total_weight > 0 else 1 / 3,
                   "carbon": w_carbon / total_weight if total_weight > 0 else 1 / 3,
                   "water": w_water / total_weight if total_weight > 0 else 1 / 3}
        html_block(f"""<div class='sx-split' role='img' aria-label='Priority split'>
            <div style='width:{weights['cost'] * 100:.1f}%;background:var(--amber)'></div>
            <div style='width:{weights['carbon'] * 100:.1f}%;background:var(--char)'></div>
            <div style='width:{weights['water'] * 100:.1f}%;background:#7FA58C'></div></div>
            <div class='sx-note'>Effective split: money {weights['cost'] * 100:.0f}% · carbon {weights['carbon'] * 100:.0f}% · water {weights['water'] * 100:.0f}%</div>""")
        if total_weight == 0:
            callout("warn", "All priorities are 0, so cost, carbon and water are weighted equally.")

        st.write("")
        run_clicked = st.button("Find best place and time", type="primary", use_container_width=True,
                                disabled=st.session_state.busy)

current_inputs = {"gpu_hours": int(gpu_hours), "deadline": int(deadline), "is_flexible": is_flexible, "is_pausable": is_pausable,
                  "checkpoint_penalty": int(checkpoint_penalty), "usual_choice": usual_choice, "data_india": data_india,
                  "weights": weights, "slider_values": (w_cost, w_carbon, w_water)}
if run_clicked and not st.session_state.busy:
    st.session_state.pending_inputs = current_inputs
    st.session_state.busy = True
    st.session_state.error = None
    st.rerun()


# =====================================================================================
# Right side renderers
# =====================================================================================
def render_empty():
    html_block("""<div class='sx-card sx-empty'><div class='sx-eyebrow' style='color:var(--amber-d)'>Ready when you are</div>
        <h2 class='sx-serif'>Describe a job, get a place and a time.</h2>
        <div class='sx-cap' style='margin-top:0;font-size:14px'>Sunshift compares Indian regions and start times using electricity tariffs, published grid carbon factors,
        regional water stress and weather forecasts, then recommends where and when the job should run.</div>
        <div class='sx-steps'><div class='sx-step'><span>STEP 1</span><b>Describe the job</b>GPU hours, deadline, and whether it can pause.</div>
        <div class='sx-step'><span>STEP 2</span><b>Set your priorities</b>Balance money, carbon and water.</div>
        <div class='sx-step'><span>STEP 3</span><b>Find best place and time</b>Review the estimate, its data sources and the handoff.</div></div></div>""")


def render_loading():
    html_block("""<div class='sx-card' role='status' aria-live='polite'><div class='sx-eyebrow' style='color:var(--amber-d)'>Working</div>
        <div class='sx-serif' style='font-size:24px;font-weight:700;margin:4px 0 14px'>Analysing tariffs, forecasts and schedules…</div>
        <div class='sx-skel' style='height:120px;margin-bottom:12px'></div><div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'>
        <div class='sx-skel' style='height:150px'></div><div class='sx-skel' style='height:150px'></div></div></div>""")


def render_error(msg):
    callout("bad", f"<b>Sunshift could not complete this request.</b> Adjust the inputs and try again. If it keeps failing, check the terminal log.")
    with st.expander("Technical details"):
        st.code(msg)


def kpi_tile(label, saved, usual_val, fmt, better, worse, rec_val):
    exact = abs(saved) / usual_val * 100 if usual_val else 0
    if saved > 0:
        tone, text, arrow = "g", better, "&#8595;"
    elif saved < 0:
        tone, text, arrow = "r", worse, "&#8593;"
    else:
        tone, text, arrow = "n", "no change", ""
    pct = f"{arrow} {pct_text(exact)}" if saved else "no difference"
    return (f"<div class='sx-kpi'><div class='l'>{label}</div><div class='v'>{fmt(abs(saved))}</div>"
            f"<div class='s'>{text}</div><div class='p {tone}'>{pct}</div>"
            f"<div class='f'>{fmt(usual_val)} → {fmt(rec_val)}</div></div>")


def render_results(run, cur):
    usual, rec, meta_real, savings, inp = run["usual"], run["rec"], run["meta_real"], run["savings"], run["inputs"]
    start_dt = datetime.strptime(rec["start_time"], "%Y-%m-%d %H:%M")
    try:
        start_str = describe_start(start_dt)
    except Exception:
        start_str = f"{'today' if start_dt.date() == datetime.now().date() else 'tomorrow'} at {start_dt.strftime('%I %p').lstrip('0')}"
    pause = run["pause"]

    # ---- notices
    if cur != inp:
        stale = {k: v for k, v in cur.items() if k != "slider_values"} != {k: v for k, v in inp.items() if k != "slider_values"}
        if stale:
            callout("warn", "<b>Inputs changed since this result.</b> Press <b>Find best place and time</b> to update it.")
    if meta_real.get("n_gpus_scaled"):
        callout("info", f"<b>Deadline constraint.</b> Your {inp['deadline']}-day deadline is too tight for the default GPU cluster. "
                        f"Sunshift scaled the simulated cluster to {meta_real.get('n_gpus')} GPUs so the deadline can be met.")
    if meta_real.get("inputs_capped"):
        callout("warn", "Your inputs exceeded the supported limits and were capped (5,000,000 GPU hours, 30 days).")
    if meta_real.get("deadline_met") is False:
        callout("bad", "<b>Deadline not met.</b> No option in the search window finishes before your deadline.")

    pcts = {"cost": (savings["cost_saved_inr"], usual["cost_inr"], "electricity cost"),
            "carbon": (savings["carbon_saved_kg"], usual["carbon_kg"], "carbon"),
            "water": (savings["water_saved_liters"], usual["water_liters"], "cooling water")}
    worse = [(n, abs(s) / u * 100) for s, u, n in pcts.values() if s < 0 and u and abs(s) / u * 100 >= 1]
    if worse:
        names = " and ".join(f"{n} (+{round(p)}%)" for n, p in worse)
        callout("warn", f"<b>Trade-off.</b> Compared with the usual plan, this recommendation raises {names}. "
                        f"It still scores best for your priorities (money {inp['weights']['cost'] * 100:.0f}%, carbon {inp['weights']['carbon'] * 100:.0f}%, water {inp['weights']['water'] * 100:.0f}%).")
    elif all(abs(s) / u * 100 < 1 for s, u, _ in pcts.values() if u):
        callout("info", "<b>Savings are negligible.</b> The usual plan is already close to the best option for these priorities.")

    # ---- hero
    chips = []
    if meta_real.get("finish_day") is not None:
        met = meta_real.get("deadline_met")
        label = f"Finishes day {meta_real['finish_day']} of {meta_real.get('deadline_days', inp['deadline'])}"
        chips.append(f"<span class='sx-chip dark {'green' if met is not False else 'red'}'>{label}{' · deadline met' if met else ''}</span>")
    if meta_real.get("confidence_label"):
        chips.append(f"<span class='sx-chip dark'>Confidence: {esc(meta_real['confidence_label'])}</span>")
    if pause and pause["helped"]:
        chips.append(f"<span class='sx-chip dark'>Pause-and-resume plan · {esc(pause['pausable'].get('pauses', '?'))} pauses</span>")
    conf_reason = ""
    if meta_real.get("confidence") is not None and meta_real.get("n_scenarios"):
        conf_reason = f" The choice stays near-best in {meta_real['confidence'] * 100:.0f}% of {meta_real['n_scenarios']} simulated weather scenarios."
    hero_slot = st.empty()

    def hero(reason_html):
        tiles = (kpi_tile("Electricity cost", savings["cost_saved_inr"], usual["cost_inr"], inr, "saved vs usual", "more than usual", rec["cost_inr"])
                 + kpi_tile("Carbon (CO2)", savings["carbon_saved_kg"], usual["carbon_kg"], lambda v: f"{indian_number(v)} kg", "less than usual", "more than usual", rec["carbon_kg"])
                 + kpi_tile("Cooling water", savings["water_saved_liters"], usual["water_liters"], lambda v: f"{indian_number(v)} L", "less than usual", "more than usual", rec["water_liters"]))
        return H(f"""<div class='sx-hero'><div class='sx-hero-l'><div class='sx-eyebrow'>Recommendation</div>
            <h2>Run it in {esc(rec['region'])},<br>{esc(start_str)}.</h2><p>{reason_html}</p>
            <div class='sx-chips'>{''.join(chips)}</div>
            <small>Every number is an estimate, not a measurement.{esc(conf_reason)} Baseline: starting now in {esc(usual['region'])}.</small></div>
            <div class='sx-hero-r'>{tiles}</div></div>""")

    if run["reason"] is None:
        hero_slot.markdown(hero("<span style='color:#E9B866'>Writing the explanation…</span>"), unsafe_allow_html=True)
        run["reason"] = narrate(run)
    hero_slot.markdown(hero(esc(run["reason"])), unsafe_allow_html=True)

    # ---- schedule timeline (real calculated schedule)
    hfn = rec.get("hours_from_now")
    dur = meta_real.get("duration_hours")
    finish_dt = parse_dt(rec.get("finish_time"))
    if dur is None and finish_dt:
        dur = (finish_dt - start_dt).total_seconds() / 3600
    deadline_h = meta_real.get("deadline_hours") or inp["deadline"] * 24
    if hfn is not None and dur:
        now_dt = start_dt - timedelta(hours=hfn)
        rows = []
        if pause:
            parsed_s = parse_blocks(pause["straight"].get("blocks"), pause["start"], pause["remaining_h"], pause["job_hours"], 0)
            parsed_p = parse_blocks(pause["pausable"].get("blocks"), pause["start"], pause["remaining_h"], pause["job_hours"], pause["penalty_h"])
            rows.append(("Straight through", f"{pause['job_hours']} h of work", [(hfn + s, hfn + e) for s, e in parsed_s] if parsed_s else [(hfn, hfn + dur)]))
            if parsed_p:
                rows.append(("Pause and resume", f"{len(parsed_p)} run blocks", [(hfn + s, hfn + e) for s, e in parsed_p]))
        else:
            rows.append(("Recommended run", f"{rec['region']} · {dur:.0f} h", [(hfn, hfn + dur)]))
        deadline_dt = now_dt + timedelta(hours=deadline_h)
        legend = ["<span><i style='background:var(--char)'></i>Run</span>"]
        if tariff_fn():
            legend += ["<span><i style='background:rgba(231,178,76,.55)'></i>Solar-tariff window</span>",
                       "<span><i style='background:rgba(176,58,46,.35)'></i>Evening peak window</span>"]
        legend += ["<span><i style='background:#E7DEC9'></i>Idle / paused</span>", "<span><i style='background:var(--red)'></i>Deadline</span>"]
        slack = deadline_h - (hfn + dur)
        html_block(f"""<div class='sx-card'><div class='sx-h'><h3>When it runs</h3><span>Starts {esc(fmt_start(start_dt))} · finishes {esc(fmt_start(now_dt + timedelta(hours=hfn + dur)))}
            · {max(slack, 0):.0f} h before the deadline</span></div>
            {build_timeline(now_dt, deadline_h, rows, 'Deadline ' + deadline_dt.strftime('%d %b'))}
            <div class='sx-legend'>{''.join(legend)}</div>
            <div class='sx-cap'>Tariff windows are the ones used by the model. {'The pause plan comes from the pause planner; see the comparison below.' if pause else ''}</div></div>""")
        if pause and not parse_blocks(pause["pausable"].get("blocks"), pause["start"], pause["remaining_h"], pause["job_hours"], pause["penalty_h"]):
            callout("info", "The pause plan's run blocks could not be drawn in a recognised format. The plan itself is unchanged; its raw blocks are listed under <b>Pause-and-resume plan</b>.")

    # ---- comparison
    c_tab, c_chart = st.columns([1.55, 1], gap="medium")
    with c_tab:
        def row(label, u_html, r_html, chg_html):
            return f"<tr><td class='k'>{label}</td><td>{u_html}</td><td class='r'>{r_html}</td><td>{chg_html}</td></tr>"

        def metric_row(label, u, r, fmt, abs_fmt):
            lab, tone = signed_pct(u, r)
            diff = r - u
            sub = f"<span class='sub'>{'−' if diff < 0 else '+'}{abs_fmt(abs(diff))}</span>" if abs(diff) >= 0.5 else ""
            return row(label, f"<span class='big'>{fmt(u)}</span>", f"<span class='big'>{fmt(r)}</span>", f"<span class='{tone}'>{lab}</span>{sub}")

        body = row("Location", esc(usual["region"]), f"<b>{esc(rec['region'])}</b>", "")
        body += row("Start", "Now", esc(start_str), "")
        body += metric_row("Electricity cost", usual["cost_inr"], rec["cost_inr"], inr, inr)
        body += metric_row("Carbon (CO2)", usual["carbon_kg"], rec["carbon_kg"], lambda v: f"{indian_number(v)} kg", lambda v: f"{indian_number(v)} kg")
        body += metric_row("Cooling water (estimated)", usual["water_liters"], rec["water_liters"], lambda v: f"{indian_number(v)} L", lambda v: f"{indian_number(v)} L")
        if usual.get("avg_rate") is not None and rec.get("avg_rate") is not None:
            lab, tone = signed_pct(usual["avg_rate"], rec["avg_rate"])
            body += row("Average tariff", f"₹{usual['avg_rate']:.2f}/kWh", f"₹{rec['avg_rate']:.2f}/kWh", f"<span class='{tone}'>{lab}</span>")
        if usual.get("solar_hours_pct") is not None and rec.get("solar_hours_pct") is not None:
            body += row("Run hours in solar-tariff window", f"{usual['solar_hours_pct']:.0f}%", f"{rec['solar_hours_pct']:.0f}%", "")
        if usual.get("grid_factor") is not None and rec.get("grid_factor") is not None:
            body += row("Grid carbon factor <span class='sub'>published factor, not live</span>", f"{usual['grid_factor']:.2f} kg/kWh", f"{rec['grid_factor']:.2f} kg/kWh", "")
        wsi = getattr(getattr(optimizer, "physics", None), "water_stress", None)
        if isinstance(wsi, dict) and usual["region"] in wsi and rec["region"] in wsi:
            body += row("Regional water stress <span class='sub'>index of local scarcity, not water used</span>", f"{wsi[usual['region']]:.1f}", f"{wsi[rec['region']]:.1f}", "")
        html_block(f"""<div class='sx-card'><div class='sx-h'><h3>Usual plan vs recommendation</h3><span>Change = recommended relative to usual</span></div>
            <div class='sx-scroll'><table class='sx-table'><thead><tr><th></th><th>Usual choice</th><th class='r'>Recommended</th><th>Change</th></tr></thead><tbody>{body}</tbody></table></div></div>""")

    with c_chart:
        st.markdown("<div class='sx-card' style='padding-bottom:6px'><div class='sx-h'><h3>Impact at a glance</h3></div>", unsafe_allow_html=True)
        t_impact, t_rank = st.tabs(["Vs usual", "Region ranking"])
        with t_impact:
            names = ["Electricity cost", "Carbon", "Cooling water"]
            vals = [r / u * 100 if u else 100 for u, r in ((usual["cost_inr"], rec["cost_inr"]), (usual["carbon_kg"], rec["carbon_kg"]),
                                                          (usual["water_liters"], rec["water_liters"]))]
            colors = ["#3E7A56" if v < 99.5 else "#B03A2E" if v > 100.5 else "#9A9283" for v in vals]
            fig = go.Figure(go.Bar(y=names, x=vals, orientation="h", marker_color=colors, text=[f"{v:.0f}%" for v in vals],
                                   textposition="outside", cliponaxis=False, hoverinfo="skip"))
            fig.add_vline(x=100, line_width=1.5, line_dash="dot", line_color="#5A5348",
                          annotation_text="usual = 100%", annotation_position="top", annotation_font=dict(size=11, color="#5A5348"))
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=40, t=26, b=0), height=220,
                              xaxis=dict(visible=False, range=[0, max(max(vals), 100) * 1.25]),
                              yaxis=dict(autorange="reversed", tickfont=dict(size=13, color="#211D18")), font=dict(color="#211D18"), showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown("<div class='sx-cap' style='margin-top:0'>Recommended as a share of the usual plan. Below 100% means lower than usual.</div>", unsafe_allow_html=True)
        with t_rank:
            rows_all = run["results"].get("all_options") or []
            if rows_all and all("score" in r_ and "region" in r_ for r_ in rows_all):
                df_all = pd.DataFrame(rows_all)
                best = df_all.loc[df_all.groupby("region")["score"].idxmin()].sort_values("score").reset_index(drop=True)
                fig2 = go.Figure(go.Bar(y=best["region"], x=best["score"], orientation="h", text=best["score"].round().astype(int),
                                        textposition="outside", cliponaxis=False, hoverinfo="skip",
                                        marker_color=["#B76A00" if r_ == rec["region"] else "#D8CFBC" for r_ in best["region"]]))
                fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=36, t=6, b=0), height=220,
                                   xaxis=dict(visible=False, range=[0, float(best["score"].max()) * 1.2]),
                                   yaxis=dict(autorange="reversed", tickfont=dict(size=13, color="#211D18")), showlegend=False)
                st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
                st.markdown("<div class='sx-cap' style='margin-top:0'>Best option per region. Lower is better. Scores are relative within this run, not absolute measurements.</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='sx-cap'>Region scores are not available for this run.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ---- pause-and-resume comparison
    if inp["is_pausable"]:
        if run["errors"].get("pause"):
            callout("bad", "<b>Pause-and-resume planning failed.</b> The continuous recommendation above is unaffected.")
        elif pause:
            s_cost, p_cost = pause["straight"]["total_cost"], pause["pausable"]["total_cost"]
            lab, tone = signed_pct(s_cost, p_cost)
            verdict = (f"Pausing is estimated to cost <b>{lab.replace('−', '')} less</b> than running straight through, with {esc(pause['pausable'].get('pauses', '?'))} pause(s)."
                       if pause["helped"] else "Pausing found <b>no saving</b> over running straight through for this job, so straight-through is kept.")
            html_block(f"""<div class='sx-card'><div class='sx-h'><h3>Pause-and-resume plan</h3><span>{pause['job_hours']} h of work · {inp['checkpoint_penalty']} min checkpoint overhead</span></div>
                <div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px'>
                <div class='sx-step'><span>STRAIGHT THROUGH</span><b class='sx-serif' style='font-size:22px'>{s_cost:,.0f}</b>plan cost units</div>
                <div class='sx-step'><span>PAUSE AND RESUME</span><b class='sx-serif' style='font-size:22px'>{p_cost:,.0f}</b>plan cost units</div>
                <div class='sx-step'><span>DIFFERENCE</span><b class='sx-serif' style='font-size:22px'><span class="{ 'sx-chip green' if pause['helped'] else 'sx-chip' }">{lab}</span></b>pause vs straight</div></div>
                <div class='sx-cap'>{verdict} Costs come from the pause planner's built-in hourly tariff profile, so compare the two plans with each other; do not read them as a quote.</div></div>""")
            with st.expander("Raw plan blocks"):
                st.code(json.dumps(pause["pausable"].get("blocks"), default=str, indent=2), language="json")

    # ---- enterprise tabs
    st.markdown("<h3 class='sx-serif' style='font-size:20px;margin:26px 0 6px'>Handoff, export and data trust</h3>", unsafe_allow_html=True)
    tab_handoff, tab_export, tab_trust = st.tabs(["DevOps handoff", "Audit export", "Data trust and methodology"])

    with tab_handoff:
        callout("info", "<b>Handoff specification, not a deployed workload.</b> Sunshift has not created anything in a cluster. It does not verify cluster capacity or schedule execution; your DevOps team applies and tests this specification.")
        if run["errors"].get("k8s") or run.get("k8s") is None:
            callout("bad", "The Kubernetes specification could not be generated for this run.")
        else:
            payload = run["k8s"]
            is_json = True
            try:
                json.loads(payload)
            except Exception:
                is_json = False
            st.code(payload, language="json" if is_json else "yaml")
            st.download_button("Download specification", data=payload, file_name=f"sunshift_handoff.{'json' if is_json else 'yaml'}",
                               mime="application/json" if is_json else "text/yaml", key="dl_k8s")
        if pause and run.get("pause") and pause.get("cron"):
            html_block("<div class='sx-sub'>Slurm / cron execution schedule</div>")
            st.code(pause["cron"], language="bash")

    with tab_export:
        html_block("<div class='sx-note' style='font-size:13.5px'>The estimates and assumptions for this run as a CSV audit trail, for use in sustainability reporting such as BRSR. These are model estimates, not verified measurements.</div>")
        if run.get("csv") is None:
            callout("bad", "The audit export could not be generated for this run.")
        else:
            csv_data = run["csv"]
            st.download_button("Download BRSR audit report (CSV)", data=csv_data,
                               file_name=f"sunshift_esg_export_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv", key="dl_csv")
            with st.expander("Preview the export"):
                try:
                    st.dataframe(pd.read_csv(io.StringIO(csv_data if isinstance(csv_data, str) else csv_data.decode("utf-8"))),
                                 use_container_width=True, hide_index=True)
                except Exception:
                    st.code(csv_data if isinstance(csv_data, str) else csv_data.decode("utf-8", "ignore"))

    with tab_trust:
        report = run.get("trust")
        if not report:
            callout("bad", "The data-trust report could not be generated for this run.")
        else:
            if meta_real.get("ml_hours_share") is not None:
                share = meta_real["ml_hours_share"]
                html_block(f"<div class='sx-note' style='font-size:13.5px'>Forecast hours used in this run: <b>{(1 - share) * 100:.0f}%</b> from the cached Open-Meteo forecast, <b>{share * 100:.0f}%</b> estimated by Sunshift's model.</div>")
            html_block("<div class='sx-sub'>Active flags</div>")
            for flag in report.get("active_flags", []):
                callout(trust_level(flag), esc(clean_flag(flag)))
            html_block("<div class='sx-sub'>Data sources</div>")
            rows_html = "".join(
                f"<div class='sx-trow'><div class='n'>{esc(k.replace('_', ' '))}</div><div class='d'>{esc(v.get('source', ''))}"
                f" ({esc(v.get('date', ''))}) · {esc(v.get('unit', ''))}<small>{esc(v.get('caveat', ''))}</small></div><div>{type_badge(v.get('type', 'unspecified'))}</div></div>"
                for k, v in report.get("sources", {}).items())
            html_block(f"<div class='sx-card' style='padding:6px 20px'>{rows_html}</div>")
            html_block("<div class='sx-sub'>Hardware and model assumptions</div>")
            a_html = "".join(
                f"<div class='sx-trow'><div class='n'>{esc(k.replace('_', ' '))}</div><div class='d'>{esc(v.get('value', ''))} {esc(v.get('unit', ''))}<small>{esc(v.get('notes', ''))}</small></div><div><span class='sx-chip amber'>Assumption</span></div></div>"
                for k, v in report.get("assumptions", {}).items())
            html_block(f"<div class='sx-card' style='padding:6px 20px'>{a_html}</div>")
            html_block("<div class='sx-sub'>Limitations</div>")
            for text in report.get("disclaimers", {}).values():
                html_block(f"<div class='sx-note' style='font-size:13.5px'>• {esc(text)}</div>")

    with st.expander("Glossary"):
        st.markdown(
            "- **PUE (power usage effectiveness):** total facility power divided by IT power. Hotter weather means more cooling energy, so a higher PUE.\n"
            "- **Grid carbon factor:** published average kg of CO2 per kWh for a region's grid. It is not a live measurement.\n"
            "- **Regional water stress:** how scarce water already is in a region. It is not the amount of water a job uses.\n"
            "- **Checkpoint overhead:** time lost saving and reloading job state each time a job pauses and resumes.\n"
            "- **Confidence:** how often the recommendation stays near the best in simulated weather scenarios.")
    html_block(f"<div class='sx-cap' style='text-align:right'>Calculated {esc(run['computed_at'].strftime('%d %b %Y, %I:%M %p'))}. All figures are estimates.</div>")



with right_col:
    if st.session_state.busy:
        render_loading()
        try:
            st.session_state.run = compute_run(st.session_state.pending_inputs)
            st.session_state.error = None
        except Exception as exc:
            logger.exception("Optimisation failed")
            st.session_state.error = f"{type(exc).__name__}: {exc}"
        finally:
            st.session_state.busy = False
        st.rerun()
    elif st.session_state.error:
        render_error(st.session_state.error)
    elif st.session_state.run:
        render_results(st.session_state.run, current_inputs)
    else:
        render_empty()