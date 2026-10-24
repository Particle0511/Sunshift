import html
import io
import json
import logging
import math
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Internal Module Imports
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
except ImportError:
    def indian_number(x):
        return f"{x:,.0f}"

    def inr(x):
        return f"₹{x:,.0f}"

logger = logging.getLogger("sunshift")

# =====================================================================================
# Page Configuration
# =====================================================================================
st.set_page_config(
    page_title="Sunshift | AI Workload Grid Optimizer",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================================
# State Initialization
# =====================================================================================
PRIORITY_DEFAULTS = {"cost": 70, "carb": 80, "wat": 60}
for _k, _v in PRIORITY_DEFAULTS.items():
    st.session_state.setdefault(f"{_k}_sld", _v)
    st.session_state.setdefault(f"{_k}_num", _v)

for _k, _v in {"busy": False, "run": None, "error": None, "pending_inputs": None}.items():
    st.session_state.setdefault(_k, _v)

def sync_prio(key: str, from_widget: str):
    if from_widget == "num":
        st.session_state[f"{key}_sld"] = st.session_state[f"{key}_num"]
    else:
        st.session_state[f"{key}_num"] = st.session_state[f"{key}_sld"]


# =====================================================================================
# Design System & Styling
# =====================================================================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inria+Serif:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;500;600;700&display=swap');

:root {
  --bg: #F8F6F0;
  --surface: #FFFFFF;
  --surface-2: #FAF8F3;
  --surface-3: #F1ECE0;
  --ink: #1A1713;
  --ink-2: #4D463C;
  --muted: #7D7569;
  --line: #E6DFCE;
  --line-2: #EFE9DC;
  --amber: #B76A00;
  --amber-d: #8C4E00;
  --amber-l: #FBF0DA;
  --green: #257849;
  --green-l: #E3F2E9;
  --red: #B53225;
  --red-l: #FCEAE8;
  --char: #1A211E;
  --tl-header-w: 135px;
  --shadow-xs: 0 1px 2px rgba(26,23,19,.04);
  --shadow-s: 0 2px 8px rgba(26,23,19,.06), 0 0 1px rgba(26,23,19,.06);
  --shadow-m: 0 6px 20px rgba(26,23,19,.08), 0 0 1px rgba(26,23,19,.06);
  --radius-s: 8px;
  --radius-m: 12px;
  --radius-l: 16px;
}

/* Base resets & typography */
.stApp { background-color: var(--bg); }
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp div[data-baseweb="select"], .sx {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: var(--ink);
}
.sx-serif { font-family: 'Inria Serif', Georgia, serif !important; }

/* Main layout constraints */
.block-container {
  padding-top: 1.25rem !important;
  padding-bottom: 3.5rem !important;
  max-width: 1440px !important;
}
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }

.stApp h1, .stApp h2, .stApp h3 {
  font-family: 'Inria Serif', Georgia, serif;
  color: var(--ink);
  letter-spacing: -0.015em;
}

/* Hide components script iframe */
iframe[title*="components.html"], iframe[srcdoc*="_autoSelectAttached"] {
  position: fixed !important;
  width: 0 !important;
  height: 0 !important;
  opacity: 0 !important;
  pointer-events: none !important;
  border: none !important;
  top: -100px !important;
  left: -100px !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* Sidebar Styling */
section[data-testid="stSidebar"] {
  background-color: var(--surface) !important;
  border-right: 1px solid var(--line) !important;
  box-shadow: 2px 0 12px rgba(26,23,19,.03);
}
section[data-testid="stSidebar"] .block-container {
  padding: 1.5rem 1.2rem 3rem !important;
}

/* Sidebar Section Headers */
.sx-sb-sec {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 18px 0 8px;
}
.sx-sb-sec:first-child { margin-top: 0; }
.sx-sb-sec span.n {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--char);
  color: #FAF7F0;
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.sx-sb-sec b {
  font-family: 'Inter', system-ui, sans-serif !important;
  font-size: 12px;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--ink);
  font-weight: 700;
}
.sx-sb-sec i {
  flex: 1;
  height: 1px;
  background: var(--line-2);
}

/* Navigation bar */
.sx-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 8px 0 18px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 20px;
}
.sx-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sx-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--amber);
  position: relative;
  flex: none;
  box-shadow: 0 2px 6px rgba(183,106,0,.3);
}
.sx-mark:after {
  content: "";
  position: absolute;
  inset: 7px;
  border-radius: 50%;
  background: var(--bg);
}
.sx-word {
  font-family: 'Inria Serif', Georgia, serif;
  font-size: 26px;
  font-weight: 700;
  color: var(--ink);
  line-height: 1;
}
.sx-tag {
  font-size: 13px;
  color: var(--ink-2);
  padding-left: 14px;
  border-left: 1px solid var(--line);
  line-height: 1.25;
}
.sx-nav-r {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

/* Badges & Chips */
.sx-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-2);
  white-space: nowrap;
}
.sx-chip.green { background: var(--green-l); border-color: #BBDDC7; color: var(--green); }
.sx-chip.amber { background: var(--amber-l); border-color: #ECD29C; color: var(--amber-d); }
.sx-chip.red { background: var(--red-l); border-color: #F6CAC4; color: var(--red); }
.sx-chip.dark { background: rgba(248,246,240,.12); border-color: rgba(248,246,240,.20); color: #F8F6F0; }
.sx-chip.dark.green { background: rgba(37,120,73,.25); border-color: rgba(37,120,73,.5); color: #AEE0C2; }
.sx-chip.dark.red { background: rgba(181,50,37,.25); border-color: rgba(181,50,37,.5); color: #F8B4AD; }
.sx-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; display: inline-block; }

/* Compact sidebar number inputs */
section[data-testid="stSidebar"] div[data-baseweb="input"] {
  height: 34px !important;
  min-height: 34px !important;
  font-size: 13px !important;
}
section[data-testid="stSidebar"] div[data-baseweb="input"] input {
  padding: 2px 6px !important;
  font-weight: 600;
  text-align: center;
}

/* Widgets Styling */
[data-testid="stWidgetLabel"] p, .stApp label p {
  font-family: 'Inter', system-ui, sans-serif !important;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  margin-bottom: 3px;
}
div[data-baseweb="input"], div[data-baseweb="select"] > div {
  background: var(--surface-2) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-s) !important;
  transition: all 0.15s ease;
}
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within {
  border-color: var(--amber) !important;
  box-shadow: 0 0 0 3px rgba(183,106,0,.15);
}
div[data-baseweb="input"] input { font-variant-numeric: tabular-nums; }
[data-testid="stThumbValue"], [data-testid="stSliderThumbValue"], [data-testid="stTickBar"] { display: none !important; }

div[role="radiogroup"] {
  gap: 0 !important;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  overflow: hidden;
  background: var(--surface-2);
}
div[role="radiogroup"] > label {
  flex: 1;
  justify-content: center;
  margin: 0 !important;
  padding: 7px 0;
  cursor: pointer;
  transition: background 0.15s;
}
div[role="radiogroup"] > label > div:first-child { display: none; }
div[role="radiogroup"] > label:has(input:checked) {
  background: var(--char);
}
div[role="radiogroup"] > label p {
  font-family: 'Inter', system-ui, sans-serif !important;
  font-size: 13.5px !important;
  font-weight: 600 !important;
}
div[role="radiogroup"] > label:has(input:checked) p {
  color: #FAF7F0 !important;
}

button[kind="primary"], button[data-testid="stBaseButton-primary"] {
  background: var(--amber) !important;
  color: #fff !important;
  border: 1px solid var(--amber-d) !important;
  border-radius: var(--radius-s) !important;
  font-weight: 600 !important;
  min-height: 44px;
  transition: all 0.18s ease;
}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
  background: var(--amber-d) !important;
  box-shadow: 0 4px 12px rgba(183,106,0,.25);
  transform: translateY(-1px);
}
button[kind="primary"]:disabled, button[data-testid="stBaseButton-primary"]:disabled {
  opacity: .5;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

[data-testid="stDownloadButton"] button {
  background: var(--surface) !important;
  color: var(--ink) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-s) !important;
  font-weight: 600;
  transition: all 0.15s ease;
}
[data-testid="stDownloadButton"] button:hover {
  background: var(--surface-2) !important;
  border-color: var(--ink-2) !important;
}

/* Tabs */
[data-baseweb="tab"] {
  font-weight: 600;
  color: var(--ink-2);
  font-size: 14px;
  padding: 10px 16px;
}
[data-baseweb="tab"][aria-selected="true"] { color: var(--ink); }
div[data-baseweb="tab-highlight"] { background-color: var(--amber) !important; height: 3px !important; }
div[data-baseweb="tab-border"] { background-color: var(--line) !important; }

[data-testid="stExpander"] {
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-m) !important;
  background: var(--surface);
  box-shadow: var(--shadow-xs);
}

/* Unified Card System */
.sx-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-l);
  padding: 22px 24px;
  margin: 0 0 16px;
  box-shadow: var(--shadow-s);
}
.sx-h {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.sx-h h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.sx-h span {
  font-size: 12px;
  color: var(--muted);
}
.sx-cap {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.5;
  margin-top: 10px;
}
.sx-note {
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.5;
  margin: 4px 0 6px;
}

/* Sidebar Priority split bar */
.sx-split {
  display: flex;
  height: 6px;
  border-radius: 99px;
  overflow: hidden;
  margin: 10px 0 6px;
  background: var(--line-2);
}
.sx-split div { height: 100%; transition: width 0.25s ease; }

/* Executive Hero Card (Two-Tier Balanced Layout) */
.sx-hero {
  background: linear-gradient(145deg, #1A211E 0%, #131715 100%);
  color: #F8F6F0;
  border-radius: var(--radius-l);
  padding: 24px 26px;
  margin-bottom: 20px;
  border: 1px solid rgba(248,246,240,.14);
  box-shadow: var(--shadow-m);
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.sx-hero-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.sx-hero-l {
  flex: 1 1 320px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sx-eyebrow {
  font-size: 12px;
  letter-spacing: .14em;
  text-transform: uppercase;
  font-weight: 700;
  color: #E6BA6E;
}
.sx-hero h2 {
  font-family: 'Inria Serif', Georgia, serif;
  font-size: clamp(24px, 2.4vw, 34px);
  line-height: 1.15;
  margin: 0;
  color: #FCF9F2;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.sx-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.sx-hero-r {
  flex: 1 1 450px;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(130px, 1fr));
  gap: 10px;
}

/* Two-Tier Divider & Executive Rationale */
.sx-hero-div {
  height: 1px;
  background: rgba(248, 246, 240, 0.1);
  width: 100%;
}
.sx-hero-bottom {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sx-brief-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.sx-brief-badge {
  font-size: 11px;
  letter-spacing: .12em;
  text-transform: uppercase;
  font-weight: 700;
  color: #E6BA6E;
}
.sx-brief-meta {
  font-size: 12px;
  color: #C5BCAB;
}
.sx-hero-bottom p {
  margin: 0;
  color: #DDD6C8;
  font-size: 14px;
  line-height: 1.6;
}

/* Snug, Compact KPI Cards (Zero Dead Space) */
.sx-kpi-card {
  background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: var(--radius-m);
  padding: 15px 15px 13px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,.15);
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.sx-kpi-card:hover {
  border-color: rgba(255,255,255,.24);
  transform: translateY(-1px);
}
.sx-kpi-top {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.sx-kpi-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}
.sx-kpi-icon-box {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.sx-kpi-icon-box svg {
  width: 22px;
  height: 22px;
}
.sx-kpi-icon-box.volt {
  background: radial-gradient(circle, rgba(255, 179, 0, 0.16) 0%, rgba(255, 179, 0, 0.04) 100%);
  border: 1px solid rgba(255, 179, 0, 0.3);
}
.sx-kpi-icon-box.leaf {
  background: radial-gradient(circle, rgba(0, 200, 83, 0.16) 0%, rgba(0, 200, 83, 0.04) 100%);
  border: 1px solid rgba(0, 200, 83, 0.3);
}
.sx-kpi-icon-box.water {
  background: radial-gradient(circle, rgba(0, 176, 255, 0.16) 0%, rgba(0, 176, 255, 0.04) 100%);
  border: 1px solid rgba(0, 176, 255, 0.3);
}
.sx-kpi-card .l {
  font-family: 'Inter', system-ui, sans-serif !important;
  font-size: 11.5px;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: #D6CFBF;
  font-weight: 700;
  line-height: 1.2;
}
.sx-kpi-card .v {
  font-family: 'Inria Serif', Georgia, serif;
  font-size: clamp(23px, 2.1vw, 28px);
  font-weight: 700;
  line-height: 1.05;
  white-space: nowrap;
  color: #FFFFFF;
  margin: 2px 0 1px;
}
.sx-kpi-card .s {
  font-size: 11.5px;
  color: #C0B7A8;
  margin-bottom: 4px;
}
.sx-kpi-pill {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  font-size: 11px;
  font-weight: 700;
  padding: 2.5px 8px;
  border-radius: 999px;
  letter-spacing: 0.02em;
  margin-bottom: 2px;
}
.sx-kpi-pill.g {
  background: rgba(46,125,78,.25);
  border: 1px solid rgba(78,186,120,.5);
  color: #A3E4BC;
}
.sx-kpi-pill.r {
  background: rgba(181,50,37,.25);
  border: 1px solid rgba(240,110,95,.5);
  color: #F8B4AD;
}
.sx-kpi-pill.n {
  background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.18);
  color: #CFC7BA;
}
.sx-kpi-div {
  height: 1px;
  background: rgba(255,255,255,.09);
  margin: 6px 0 5px;
}
.sx-kpi-cmp {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.sx-kpi-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 12px;
  color: #A8A092;
  font-variant-numeric: tabular-nums;
}
.sx-kpi-row b {
  font-weight: 600;
  color: #E2DBD0;
}
.sx-kpi-row.rec {
  color: #C0B7A8;
}
.sx-kpi-row.rec b {
  color: #FFFFFF;
  font-weight: 700;
}

/* Callouts & Notices */
.sx-call {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: var(--radius-m);
  padding: 10px 14px;
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink);
}
.sx-call b { font-weight: 600; }
.sx-call .ic {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  flex: none;
  margin-top: 1px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--muted);
}
.sx-call.warn { background: #FEF7EA; border-color: #EED7A2; }
.sx-call.warn .ic { background: var(--amber); }
.sx-call.bad { background: var(--red-l); border-color: #F4C7C2; }
.sx-call.bad .ic { background: var(--red); }
.sx-call.ok { background: var(--green-l); border-color: #C1E1CB; }
.sx-call.ok .ic { background: var(--green); }

/* Comparison Table */
.sx-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
}
.sx-table th {
  font-size: 10.5px;
  letter-spacing: .11em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 700;
  text-align: left;
  padding: 0 12px 10px;
}
.sx-table td {
  padding: 10px 12px;
  border-top: 1px solid var(--line-2);
  vertical-align: middle;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.sx-table tr:hover td { background: rgba(239,233,217,.4); }
.sx-table td.k { color: var(--ink-2); font-weight: 500; min-width: 130px; }
.sx-table td.r, .sx-table th.r { background: rgba(251,240,217,.4); }
.sx-table th.r { color: var(--amber-d); border-top: 2px solid var(--amber); padding-top: 10px; }
.sx-table .big { font-family: 'Inria Serif', Georgia, serif; font-size: 18px; font-weight: 700; }
.sx-table .sub { display: block; font-size: 11.5px; color: var(--muted); margin-top: 1px; }
.sx-table .g { color: var(--green); font-weight: 700; }
.sx-table .rd { color: var(--red); font-weight: 700; }
.sx-table .n { color: var(--ink-2); font-weight: 600; }
.sx-scroll { overflow-x: auto; }

/* Timeline Alignment */
.sx-tl { position: relative; margin: 30px 6px 6px; }
.sx-row {
  display: grid;
  grid-template-columns: var(--tl-header-w) 1fr;
  gap: 12px;
  align-items: center;
  margin-bottom: 9px;
}
.sx-row .t {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.25;
}
.sx-row .t small { display: block; font-weight: 400; color: var(--muted); }
.sx-track {
  position: relative;
  height: 28px;
  border-radius: 6px;
  background: repeating-linear-gradient(135deg, #F2ECE0, #F2ECE0 6px, #EAE2D2 6px, #EAE2D2 12px);
  overflow: hidden;
  border: 1px solid var(--line);
}
.sx-band { position: absolute; top: 0; bottom: 0; }
.sx-band.solar { background: rgba(231,178,76,.32); }
.sx-band.peak { background: rgba(181,50,37,.18); }
.sx-run { position: absolute; top: 4px; bottom: 4px; border-radius: 4px; background: var(--char); }
.sx-axis {
  position: relative;
  height: 26px;
  margin-left: calc(var(--tl-header-w) + 12px);
}
.sx-tick {
  position: absolute;
  top: 0;
  font-size: 10.5px;
  color: var(--ink-2);
  transform: translateX(-50%);
  white-space: nowrap;
  text-align: center;
  line-height: 1.2;
}
.sx-tick:before {
  content: "";
  display: block;
  width: 1px;
  height: 4px;
  background: var(--line);
  margin: 0 auto 3px;
}
.sx-mk {
  position: absolute;
  top: -24px;
  bottom: 26px;
  width: 0;
  border-left: 2px solid var(--red);
  z-index: 2;
}
.sx-mk span {
  position: absolute;
  top: -2px;
  transform: translateX(-100%);
  padding-right: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--red);
  white-space: nowrap;
}
.sx-mk.now { border-left: 2px dashed rgba(77,70,60,.6); }
.sx-mk.now span { transform: none; padding: 0 0 0 6px; color: var(--ink-2); }
.sx-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  font-size: 11.5px;
  color: var(--ink-2);
  margin-top: 8px;
}
.sx-legend i {
  display: inline-block;
  width: 11px;
  height: 11px;
  border-radius: 3px;
  margin-right: 5px;
  vertical-align: -1px;
}

/* Trust / Source rows */
.sx-trow {
  display: grid;
  grid-template-columns: minmax(140px, 1.1fr) 2fr auto;
  gap: 6px 16px;
  padding: 11px 0;
  border-top: 1px solid var(--line-2);
  align-items: start;
  font-size: 13px;
}
.sx-trow:first-of-type { border-top: 0; }
.sx-trow .n { font-weight: 600; text-transform: capitalize; }
.sx-trow .d { color: var(--ink-2); line-height: 1.5; }
.sx-trow .d small { display: block; color: var(--muted); margin-top: 1px; }
.sx-sub {
  font-size: 10.5px;
  letter-spacing: .13em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--muted);
  margin: 20px 0 6px;
}

/* Empty & Skeleton states */
.sx-empty { padding: 40px 36px; }
.sx-empty h2 { margin: 0 0 8px; font-size: 28px; }
.sx-steps {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin: 24px 0 8px;
}
.sx-step {
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 18px 20px;
  background: var(--surface-2);
  font-size: 13px;
  color: var(--ink-2);
  line-height: 1.5;
  box-shadow: var(--shadow-xs);
}
.sx-step b { display: block; color: var(--ink); margin: 6px 0 4px; font-size: 14px; }
.sx-step span { font-size: 10.5px; font-weight: 700; color: var(--amber-d); letter-spacing: .12em; }
.sx-skel {
  border-radius: var(--radius-m);
  background: linear-gradient(90deg, #EFE8D9 0%, #FAF5EB 50%, #EFE8D9 100%);
  background-size: 200% 100%;
  animation: sx-sh 1.5s ease-in-out infinite;
}
@keyframes sx-sh { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }
@media (prefers-reduced-motion: reduce) { .sx-skel { animation: none; background: #EFE8D9; } }

@media (max-width: 960px) {
  :root { --tl-header-w: 100px; }
  .sx-hero-r { grid-template-columns: 1fr; }
  .sx-steps { grid-template-columns: 1fr; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Auto-select all text on input focus so user can immediately type a new number
components.html(
    """
    <script>
    (function() {
        const parentDoc = window.parent.document;
        if (!parentDoc._autoSelectAttached) {
            parentDoc._autoSelectAttached = true;
            parentDoc.addEventListener('focusin', function(e) {
                if (e.target && e.target.tagName === 'INPUT' && (e.target.type === 'number' || e.target.type === 'text')) {
                    setTimeout(function() {
                        try {
                            if (parentDoc.activeElement === e.target) {
                                e.target.select();
                            }
                        } catch (err) {}
                    }, 40);
                }
            }, true);
        }
    })();
    </script>
    """,
    height=0,
    width=0
)


# =====================================================================================
# Helpers
# =====================================================================================
def H(s: str) -> str:
    """Collapse an HTML snippet to one line so Markdown never renders a code block."""
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

    days = horizon_h / 24
    step = 1 if days <= 7 else 2 if days <= 14 else 5
    ticks, first_midnight = "", ((24 - now_dt.hour) % 24) or 24
    h, idx = first_midnight, 0
    while h < horizon_h:
        if idx % step == 0:
            d = now_dt + timedelta(hours=h)
            ticks += f"<div class='sx-tick' style='left:{pct(h):.3f}%'>{d.strftime('%a')}<br>{d.strftime('%d %b')}</div>"
        h, idx = h + 24, idx + 1

    offset = "calc(var(--tl-header-w) + 12px)"
    return (f"<div class='sx-tl'>"
            f"<div class='sx-mk now' style='left:calc({offset} + (100% - {offset}) * 0)'><span>Now</span></div>"
            f"<div class='sx-mk' style='left:calc({offset} + (100% - {offset}) * 1)'><span>{esc(deadline_label)}</span></div>"
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
# Engines Initialization
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
# Computation
# =====================================================================================
FALLBACK_META = {"confidence_label": "High", "finish_day": 1, "n_gpus": 48}


def narrate(usual: dict, rec: dict, weights: dict, meta: dict) -> str:
    try:
        return explainer.generate_reason(usual, rec, weights=weights, meta=meta)
    except TypeError:
        return explainer.generate_reason(usual, rec)


def compute_run(inp: dict) -> dict:
    weights_in = inp["weights"]
    results = optimizer.find_best_placement(
        inp["gpu_hours"], inp["deadline"], weights_in, inp["is_flexible"],
        usual_region=inp["usual_choice"], domestic_only=inp["data_india"]
    )
    usual, rec = results["usual"], results["recommended"]
    meta_real = results.get("meta") or {}
    meta = results.get("meta") or {**FALLBACK_META, "deadline_days": inp["deadline"], "forecast_timestamp": datetime.now()}
    savings = ResultsComparator.calculate_savings(usual, rec)

    # Pre-generate explanation during compute step so the UI never flickers
    try:
        reason_text = narrate(usual, rec, weights_in, meta)
    except Exception as exc:
        logger.exception("Narration generation failed")
        reason_text = f"Workload dynamically routed to {rec['region']} to optimize grid cost, carbon intensity, and cooling efficiency."

    run = {
        "inputs": inp, "results": results, "usual": usual, "rec": rec, "meta": meta,
        "meta_real": meta_real, "savings": savings, "pause": None, "reason": reason_text,
        "errors": {}, "computed_at": datetime.now()
    }

    if inp["is_pausable"]:
        try:
            pause_optimizer.penalty_hours = inp["checkpoint_penalty"] / 60.0
            test_start = datetime.strptime(rec["start_time"], "%Y-%m-%d %H:%M")
            deadline_h = meta_real.get("deadline_hours") or inp["deadline"] * 24
            remaining_h = max(1, int(deadline_h - rec.get("hours_from_now", 0)))
            rates = pause_optimizer._generate_synthetic_rates(test_start, remaining_h)
            est_job_hours = max(1, math.ceil(inp["gpu_hours"] / meta.get("n_gpus", 48)))
            straight_plan = pause_optimizer.get_straight_through_plan(est_job_hours, rates)
            pause_plan = pause_optimizer.get_pausable_plan(est_job_hours, rates)
            helped = pause_plan["total_cost"] < straight_plan["total_cost"]
            chosen = pause_plan if helped else straight_plan
            run["pause"] = {
                "straight": straight_plan, "pausable": pause_plan, "chosen": chosen,
                "helped": helped, "job_hours": est_job_hours, "remaining_h": remaining_h,
                "start": test_start, "penalty_h": inp["checkpoint_penalty"] / 60.0,
                "cron": pause_optimizer.generate_cron_snippet(chosen.get("blocks", []))
            }
        except Exception as exc:
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


# =====================================================================================
# Top Header Bar
# =====================================================================================
def render_top_header(run):
    chips = "<span class='sx-chip'>National Grid</span><span class='sx-chip'>5 Indian Regions</span>"
    if run:
        ts = run["meta_real"].get("forecast_timestamp")
        if isinstance(ts, datetime):
            chips += f"<span class='sx-chip amber'><span class='sx-dot'></span>Forecast Sync: {esc(ts.strftime('%d %b, %I:%M %p'))}</span>"
        else:
            chips += "<span class='sx-chip green'><span class='sx-dot'></span>Optimization Ready</span>"
    return H(f"""<div class='sx-nav'>
        <div class='sx-brand'>
            <div class='sx-mark'></div>
            <div class='sx-word'>Sunshift</div>
            <div class='sx-tag'>Temporal & Spatial AI Workload Placement</div>
        </div>
        <div class='sx-nav-r'>{chips}</div>
    </div>""")


st.markdown(render_top_header(st.session_state.run), unsafe_allow_html=True)


# =====================================================================================
# Sidebar: Workload Configuration (Sticky, Accessible, No Empty Gaps)
# =====================================================================================
with st.sidebar:
    html_block("<div class='sx-sb-sec'><span class='n'>1</span><b>Workload Profile</b><i></i></div>")
    gpu_hours = st.number_input(
        "GPU hours required",
        value=10000,
        step=1000,
        min_value=1,
        max_value=5_000_000,
        help="Total productive GPU-hours the workload needs (e.g. 64 GPUs × 150 hours = 9,600)."
    )
    deadline = st.number_input(
        "Deadline (days from now)",
        value=5,
        min_value=1,
        max_value=30,
        help="Workload must complete within this many days. Supported window: 1 to 30 days."
    )

    html_block("<div class='sx-sb-sec'><span class='n'>2</span><b>Execution Strategy</b><i></i></div>")
    job_type = st.radio(
        "Job urgency",
        ["Flexible", "Urgent"],
        horizontal=True,
        help="Flexible schedules look ahead up to 72 hours for solar & low-tariff windows. Urgent starts immediately."
    )
    is_flexible = (job_type == "Flexible")
    is_pausable = st.toggle(
        "Pause & resume capable",
        value=False,
        help="Enable if your ML framework saves checkpoints. Sunshift will segment execution around expensive peak hours."
    )
    checkpoint_penalty = 15
    if is_pausable:
        chk_c1, chk_c2 = st.columns([2.1, 1.2])
        with chk_c1:
            st.markdown("<div style='font-family:Inter,system-ui,sans-serif;font-size:13.5px;font-weight:600;color:var(--ink);padding-top:7px;'>Checkpoint overhead</div>", unsafe_allow_html=True)
        with chk_c2:
            checkpoint_penalty = st.number_input(
                "Checkpoint overhead",
                min_value=1,
                max_value=120,
                value=15,
                step=1,
                label_visibility="collapsed",
                help="Time lost in minutes saving and reloading checkpoints per pause."
            )
        html_block("<div class='sx-note' style='margin-top:-2px'>Minutes lost per pause/resume cycle.</div>")

    html_block("<div class='sx-sb-sec'><span class='n'>3</span><b>Data & Placement</b><i></i></div>")
    usual_choice = st.selectbox(
        "Baseline data centre",
        ["Mumbai", "Delhi NCR", "Bengaluru", "Chennai", "Hyderabad"],
        help="Current location. Recommendations are scored and compared against running now in this region."
    )
    data_india = st.toggle("Sovereignty: India only", value=True, help="Restricts compute exclusively to Indian state grids.")

    html_block("<div class='sx-sb-sec'><span class='n'>4</span><b>Optimization Priorities (0 - 100)</b><i></i></div>")
    
    PRIO_ITEMS = [
        ("cost", "Electricity cost", "Weight given to financial savings from time-of-day tariffs."),
        ("carb", "Grid carbon (CO₂)", "Weight given to avoiding carbon-heavy peak grid hours and high CEA factors."),
        ("wat", "Water stress protection", "Weight given to minimizing cooling water in severely water-stressed regions (WRI index).")
    ]

    for key, label, tip in PRIO_ITEMS:
        c_lbl, c_val = st.columns([2.3, 1.1])
        with c_lbl:
            st.markdown(f"<div style='font-family:Inter,system-ui,sans-serif;font-size:13.5px;font-weight:600;color:var(--ink);padding-top:7px;'>{label}</div>", unsafe_allow_html=True)
        with c_val:
            st.number_input(
                label,
                min_value=0,
                max_value=100,
                step=5,
                key=f"{key}_num",
                on_change=sync_prio,
                args=(key, "num"),
                label_visibility="collapsed"
            )
        st.slider(
            label,
            min_value=0,
            max_value=100,
            key=f"{key}_sld",
            on_change=sync_prio,
            args=(key, "sld"),
            label_visibility="collapsed",
            help=tip
        )

    p_cost = int(st.session_state.cost_sld)
    p_carb = int(st.session_state.carb_sld)
    p_wat = int(st.session_state.wat_sld)

    total_weight = p_cost + p_carb + p_wat
    weights = {
        "cost": p_cost / total_weight if total_weight > 0 else 1 / 3,
        "carbon": p_carb / total_weight if total_weight > 0 else 1 / 3,
        "water": p_wat / total_weight if total_weight > 0 else 1 / 3
    }

    html_block(f"""<div class='sx-split' role='img' aria-label='Priority weights visual split'>
        <div style='width:{weights['cost'] * 100:.1f}%;background:var(--amber)' title='Cost: {weights['cost']*100:.0f}%'></div>
        <div style='width:{weights['carbon'] * 100:.1f}%;background:var(--char)' title='Carbon: {weights['carbon']*100:.0f}%'></div>
        <div style='width:{weights['water'] * 100:.1f}%;background:#4E8765' title='Water: {weights['water']*100:.0f}%'></div>
    </div>
    <div class='sx-note'>Split: <b>{weights['cost']*100:.0f}%</b> Cost · <b>{weights['carbon']*100:.0f}%</b> Carbon · <b>{weights['water']*100:.0f}%</b> Water</div>""")

    if total_weight == 0:
        callout("warn", "All priorities set to 0. Balanced equally.")

    st.write("")
    run_clicked = st.button(
        " Find Best Place & Time",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.busy
    )

current_inputs = {
    "gpu_hours": int(gpu_hours),
    "deadline": int(deadline),
    "is_flexible": is_flexible,
    "is_pausable": is_pausable,
    "checkpoint_penalty": int(checkpoint_penalty),
    "usual_choice": usual_choice,
    "data_india": data_india,
    "weights": weights,
    "slider_values": (p_cost, p_carb, p_wat)
}

if run_clicked and not st.session_state.busy:
    st.session_state.pending_inputs = current_inputs
    st.session_state.busy = True
    st.session_state.error = None
    st.rerun()


# =====================================================================================
# Main Dashboard Renderers
# =====================================================================================
def render_empty():
    html_block("""<div class='sx-card sx-empty'>
        <div class='sx-eyebrow'>Grid Optimization Engine Ready</div>
        <h2 class='sx-serif'>Select workload parameters to calculate optimal spatial & temporal placement.</h2>
        <div class='sx-cap' style='margin-top:0;font-size:14.5px;color:var(--ink-2);max-width:860px'>
            Sunshift optimizes large-scale AI jobs by matching compute windows against localized time-of-day tariffs (ToD), Central Electricity Authority (CEA) carbon intensity factors, localized WRI water stress indices, and hourly weather forecasts across India.
        </div>
        <div class='sx-steps'>
            <div class='sx-step'>
                <span>STEP 1</span>
                <b>1. Configure Workload</b>
                Specify total GPU hours, completion deadline, and checkpoint pause tolerance in the sidebar.
            </div>
            <div class='sx-step'>
                <span>STEP 2</span>
                <b>2. Balance Strategic Weights</b>
                Tune the multi-objective balance between electricity cost, carbon intensity, and cooling water consumption.
            </div>
            <div class='sx-step'>
                <span>STEP 3</span>
                <b>3. Deploy & Export</b>
                Inspect time-of-day timeline, delta savings, ready-to-apply Kubernetes manifests, and SEBI BRSR ESG compliance audit trails.
            </div>
        </div>
    </div>""")


def render_loading():
    html_block("""<div class='sx-card' role='status' aria-live='polite'>
        <div class='sx-eyebrow'>Solving Multi-Variable Objective</div>
        <div class='sx-serif' style='font-size:24px;font-weight:700;margin:6px 0 16px'>Analyzing regional tariffs, PUE thermal scaling & weather forecasts…</div>
        <div class='sx-skel' style='height:140px;margin-bottom:14px'></div>
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'>
            <div class='sx-skel' style='height:200px'></div>
            <div class='sx-skel' style='height:200px'></div>
        </div>
    </div>""")


def render_error(msg):
    callout("bad", "<b>Optimization solver error.</b> Verify inputs and retry. If the issue persists, review console logs.")
    with st.expander("Technical trace"):
        st.code(msg)


# =====================================================================================
# Graphic Assets (Faceted Gradient Vectors matching design system)
# =====================================================================================
SVG_VOLT = """<svg width="24" height="24" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="voltBody" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFD54F"/>
      <stop offset="45%" stop-color="#FFA000"/>
      <stop offset="100%" stop-color="#E65100"/>
    </linearGradient>
    <linearGradient id="voltHighlight" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFF9C4" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#FFB300" stop-opacity="0.2"/>
    </linearGradient>
    <filter id="voltGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#FF8F00" flood-opacity="0.4"/>
    </filter>
  </defs>
  <path d="M19 2L7 16H15L11 30L25 14H17L19 2Z" fill="url(#voltBody)" filter="url(#voltGlow)"/>
  <path d="M19 2L7 16H15L13.5 21L17 14H23L19 2Z" fill="url(#voltHighlight)"/>
</svg>"""

SVG_LEAF = """<svg width="24" height="24" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="leafGrad1" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#69F0AE"/>
      <stop offset="50%" stop-color="#00C853"/>
      <stop offset="100%" stop-color="#00692C"/>
    </linearGradient>
    <linearGradient id="leafGrad2" x1="1" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#B9F6CA"/>
      <stop offset="50%" stop-color="#00E676"/>
      <stop offset="100%" stop-color="#007E33"/>
    </linearGradient>
    <filter id="leafGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#00C853" flood-opacity="0.35"/>
    </filter>
  </defs>
  <path d="M16 2C16 2 6 8.5 6 18C6 24 10.5 29 16 29C21.5 29 26 24 26 18C26 8.5 16 2 16 2Z" fill="url(#leafGrad1)" filter="url(#leafGlow)"/>
  <path d="M16 2C16 2 6.5 8.5 6.5 18C6.5 23.5 10.8 29 16 29V2Z" fill="url(#leafGrad2)"/>
  <path d="M16 4V28M16 10L8 16M16 16L9.5 22M16 10L24 16M16 16L22.5 22" stroke="#10251A" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

SVG_WATER = """<svg width="24" height="24" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="watOuter" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#40C4FF"/>
      <stop offset="40%" stop-color="#0091EA"/>
      <stop offset="100%" stop-color="#01579B"/>
    </linearGradient>
    <linearGradient id="watInner" x1="1" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#84FFFF"/>
      <stop offset="50%" stop-color="#00E5FF"/>
      <stop offset="100%" stop-color="#0288D1"/>
    </linearGradient>
    <filter id="watGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#00B0FF" flood-opacity="0.4"/>
    </filter>
  </defs>
  <path d="M16 2C16 2 6 12 6 19C6 24.5 10.5 29 16 29C21.5 29 26 24.5 26 19C26 12 16 2 16 2Z" fill="url(#watOuter)" filter="url(#watGlow)"/>
  <path d="M16 7.5C16 7.5 10 15 10 19.5C10 23 12.7 26 16 26C19.3 26 22 23 22 19.5C22 15 18 11.5 16 7.5Z" fill="#141917"/>
  <path d="M16 9C16 9 11.5 15.5 11.5 19C11.5 21.5 13.5 24 16 24C18.5 24 20.5 21.5 20.5 19C20.5 16 18 12.5 16 9Z" fill="url(#watInner)"/>
</svg>"""

def kpi_card_html(icon_svg, icon_class, label, saved, usual_val, fmt, better_txt, worse_txt, rec_val, usual_region, rec_region):
    exact = abs(saved) / usual_val * 100 if usual_val else 0
    if saved > 0:
        tone, text, arrow, badge_txt = "g", better_txt, "↓", f"↓ {pct_text(exact)} saved"
    elif saved < 0:
        tone, text, arrow, badge_txt = "r", worse_txt, "↑", f"↑ {pct_text(exact)} more"
    else:
        tone, text, arrow, badge_txt = "n", "no change", "—", "0% difference"

    return (
        f"<div class='sx-kpi-card'>"
        f"  <div class='sx-kpi-top'>"
        f"    <div class='sx-kpi-header'>"
        f"      <div class='sx-kpi-icon-box {icon_class}'>{icon_svg}</div>"
        f"      <div class='l'>{label}</div>"
        f"    </div>"
        f"    <div class='v'>{fmt(abs(saved))}</div>"
        f"    <div class='s'>{text}</div>"
        f"    <div class='sx-kpi-pill {tone}'>{badge_txt}</div>"
        f"  </div>"
        f"  <div class='sx-kpi-bottom'>"
        f"    <div class='sx-kpi-div'></div>"
        f"    <div class='sx-kpi-cmp'>"
        f"      <div class='sx-kpi-row'><span>Baseline ({esc(usual_region)}):</span> <b>{fmt(usual_val)}</b></div>"
        f"      <div class='sx-kpi-row rec'><span>Optimal ({esc(rec_region)}):</span> <b>{fmt(rec_val)}</b></div>"
        f"    </div>"
        f"  </div>"
        f"</div>"
    )

def render_results(run, cur):
    usual, rec, meta_real, savings, inp = run["usual"], run["rec"], run["meta_real"], run["savings"], run["inputs"]
    start_dt = datetime.strptime(rec["start_time"], "%Y-%m-%d %H:%M")
    try:
        start_str = describe_start(start_dt)
    except Exception:
        start_str = f"{'today' if start_dt.date() == datetime.now().date() else 'tomorrow'} at {start_dt.strftime('%I %p').lstrip('0')}"
    pause = run["pause"]

    # ---- Notices Ribbon
    notices = []
    if cur != inp:
        stale = {k: v for k, v in cur.items() if k != "slider_values"} != {k: v for k, v in inp.items() if k != "slider_values"}
        if stale:
            notices.append(("warn", "<b>Inputs changed in sidebar:</b> Click <b> Find Best Place & Time</b> to re-evaluate."))

    if meta_real.get("n_gpus_scaled"):
        notices.append(("info", f"<b>Cluster auto-scaled:</b> A {inp['deadline']}-day deadline required scaling the cluster model to {meta_real.get('n_gpus')} GPUs."))

    if meta_real.get("inputs_capped"):
        notices.append(("warn", "Workload exceeded boundary limits and was clamped to 5,000,000 GPU hours / 30-day window."))

    if meta_real.get("deadline_met") is False:
        notices.append(("bad", "<b>Deadline constraint violated:</b> No valid regional window completed within the requested deadline."))

    pcts = {
        "cost": (savings["cost_saved_inr"], usual["cost_inr"], "electricity cost"),
        "carbon": (savings["carbon_saved_kg"], usual["carbon_kg"], "carbon emissions"),
        "water": (savings["water_saved_liters"], usual["water_liters"], "cooling water")
    }
    worse = [(n, abs(s) / u * 100) for s, u, n in pcts.values() if s < 0 and u and abs(s) / u * 100 >= 1]
    if worse:
        names = " and ".join(f"{n} (+{round(p)}%)" for n, p in worse)
        notices.append(("warn", f"<b>Prioritization trade-off:</b> Recommendation increases {names} to satisfy your weighted preference (Cost {inp['weights']['cost']*100:.0f}%, Carbon {inp['weights']['carbon']*100:.0f}%, Water {inp['weights']['water']*100:.0f}%)."))
    elif all(abs(s) / u * 100 < 1 for s, u, _ in pcts.values() if u):
        notices.append(("info", "<b>Baseline is already near-optimal:</b> The current data center is competitive under these weights."))

    for n_kind, n_txt in notices:
        callout(n_kind, n_txt)

    # ---- Executive Hero Card (Answers 90% of questions immediately)
    chips = []
    if meta_real.get("finish_day") is not None:
        met = meta_real.get("deadline_met")
        label = f"Finishes day {meta_real['finish_day']} of {meta_real.get('deadline_days', inp['deadline'])}"
        chips.append(f"<span class='sx-chip dark {'green' if met is not False else 'red'}'>{label}{' · Deadline met' if met else ''}</span>")
    if meta_real.get("confidence_label"):
        chips.append(f"<span class='sx-chip dark'>Confidence: {esc(meta_real['confidence_label'])}</span>")
    if pause and pause["helped"]:
        chips.append(f"<span class='sx-chip dark'>Pause-and-resume · {esc(pause['pausable'].get('pauses', '?'))} pause(s)</span>")

    conf_reason = ""
    if meta_real.get("confidence") is not None and meta_real.get("n_scenarios"):
        conf_reason = f" Maintains superior ranking in {meta_real['confidence'] * 100:.0f}% of {meta_real['n_scenarios']} simulated weather variances."

    tiles_html = (
        kpi_card_html(SVG_VOLT, "volt", "Electricity Cost", savings["cost_saved_inr"], usual["cost_inr"], inr, "net financial savings", "above baseline cost", rec["cost_inr"], usual["region"], rec["region"]) +
        kpi_card_html(SVG_LEAF, "leaf", "Carbon (CO₂)", savings["carbon_saved_kg"], usual["carbon_kg"], lambda v: f"{indian_number(v)} kg", "emissions avoided", "above baseline emissions", rec["carbon_kg"], usual["region"], rec["region"]) +
        kpi_card_html(SVG_WATER, "water", "Cooling Water", savings["water_saved_liters"], usual["water_liters"], lambda v: f"{indian_number(v)} L", "water conserved", "additional cooling water", rec["water_liters"], usual["region"], rec["region"])
    )

    hero_html = H(f"""<div class='sx-hero'>
        <div class='sx-hero-top'>
            <div class='sx-hero-l'>
                <div class='sx-eyebrow'>Optimal Placement Recommendation</div>
                <h2>Route to {esc(rec['region'])},<br>{esc(start_str)}.</h2>
                <div class='sx-chips'>{''.join(chips)}</div>
            </div>
            <div class='sx-hero-r'>{tiles_html}</div>
        </div>
        <div class='sx-hero-div'></div>
        <div class='sx-hero-bottom'>
            <div class='sx-brief-head'>
                <span class='sx-brief-badge'>EXECUTIVE SUMMARY</span>
                <span class='sx-brief-meta'>{esc(conf_reason)} Baseline: starting now in {esc(usual['region'])}.</span>
            </div>
            <p>{esc(run['reason'])}</p>
        </div>
    </div>""")
    st.markdown(hero_html, unsafe_allow_html=True)

    # ---- Structured Full-Width Tabs Workspace (Clean, Organized, Zero Empty Space)
    tab_timeline, tab_compare, tab_devops, tab_audit, tab_trust = st.tabs([
        " Temporal Schedule",
        " Regional Comparison",
        " DevOps Handoff",
        " ESG / BRSR Audit",
        " Data Trust & Methodology"
    ])

    # 1. Timeline Tab
    with tab_timeline:
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
                rows.append(("Straight run", f"{pause['job_hours']}h continuous", [(hfn + s, hfn + e) for s, e in parsed_s] if parsed_s else [(hfn, hfn + dur)]))
                if parsed_p:
                    rows.append(("Pause-and-resume", f"{len(parsed_p)} run blocks", [(hfn + s, hfn + e) for s, e in parsed_p]))
            else:
                rows.append(("Recommended run", f"{rec['region']} · {dur:.0f}h duration", [(hfn, hfn + dur)]))

            deadline_dt = now_dt + timedelta(hours=deadline_h)
            legend = ["<span><i style='background:var(--char)'></i>Run</span>"]
            if tariff_fn():
                legend += [
                    "<span><i style='background:rgba(231,178,76,.55)'></i>Solar tariff discount</span>",
                    "<span><i style='background:rgba(181,50,37,.35)'></i>Evening peak surcharge</span>"
                ]
            legend += ["<span><i style='background:#E8E2D4'></i>Idle / paused</span>", "<span><i style='background:var(--red)'></i>Job deadline</span>"]
            slack = deadline_h - (hfn + dur)

            timeline_markup = build_timeline(now_dt, deadline_h, rows, 'Deadline: ' + deadline_dt.strftime('%d %b'))
            html_block(f"""<div class='sx-card'>
                <div class='sx-h'>
                    <h3>Temporal Window & Grid Time-of-Day Tariffs</h3>
                    <span>Starts {esc(fmt_start(start_dt))} · Finishes {esc(fmt_start(now_dt + timedelta(hours=hfn + dur)))} ({max(slack, 0):.0f}h before deadline)</span>
                </div>
                {timeline_markup}
                <div class='sx-legend'>{''.join(legend)}</div>
                <div class='sx-cap'>Hourly tariffs indexed to state electricity regulatory commission ToD tables. {'Pause execution avoids evening grid stress.' if pause else ''}</div>
            </div>""")

            if inp["is_pausable"]:
                if run["errors"].get("pause"):
                    callout("bad", "<b>Pause-and-resume solver encountered an error.</b> Continuous recommendation remains verified.")
                elif pause:
                    s_cost, p_cost = pause["straight"]["total_cost"], pause["pausable"]["total_cost"]
                    lab, tone = signed_pct(s_cost, p_cost)
                    verdict = (
                        f"Checkpoint pausing saves approximately <b>{lab.replace('−', '')}</b> with {esc(pause['pausable'].get('pauses', '?'))} scheduled pauses."
                        if pause["helped"] else "Continuous execution is cheaper than incurring checkpoint overhead for this specific tariff window."
                    )
                    html_block(f"""<div class='sx-card'>
                        <div class='sx-h'>
                            <h3>Checkpoint Pause-and-Resume Analysis</h3>
                            <span>{pause['job_hours']}h compute · {inp['checkpoint_penalty']} min overhead per checkpoint</span>
                        </div>
                        <div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px'>
                            <div class='sx-step'>
                                <span>CONTINUOUS RUN</span>
                                <b class='sx-serif' style='font-size:22px'>{s_cost:,.0f}</b>
                                tariff cost index
                            </div>
                            <div class='sx-step'>
                                <span>SEGMENTED RUN</span>
                                <b class='sx-serif' style='font-size:22px'>{p_cost:,.0f}</b>
                                tariff cost index
                            </div>
                            <div class='sx-step'>
                                <span>DIFFERENCE</span>
                                <b class='sx-serif' style='font-size:22px'>
                                    <span class="{'sx-chip green' if pause['helped'] else 'sx-chip'}">{lab}</span>
                                </b>
                                cost delta
                            </div>
                        </div>
                        <div class='sx-cap'>{verdict}</div>
                    </div>""")
                    with st.expander("Inspect raw checkpoint intervals"):
                        st.code(json.dumps(pause["pausable"].get("blocks"), default=str, indent=2), language="json")

    # 2. Regional Comparison Tab
    with tab_compare:
        col_tbl, col_cht = st.columns([1.3, 1.2], gap="large")

        with col_tbl:
            def row(label, u_html, r_html, chg_html):
                return f"<tr><td class='k'>{label}</td><td>{u_html}</td><td class='r'>{r_html}</td><td>{chg_html}</td></tr>"

            def metric_row(label, u, r, fmt, abs_fmt):
                lab, tone = signed_pct(u, r)
                diff = r - u
                sub = f"<span class='sub'>{'−' if diff < 0 else '+'}{abs_fmt(abs(diff))}</span>" if abs(diff) >= 0.5 else ""
                return row(label, f"<span class='big'>{fmt(u)}</span>", f"<span class='big'>{fmt(r)}</span>", f"<span class='{tone}'>{lab}</span>{sub}")

            body = row("Location", esc(usual["region"]), f"<b>{esc(rec['region'])}</b>", "")
            body += row("Start Time", "Immediate (Now)", esc(start_str), "")
            body += metric_row("Electricity Cost", usual["cost_inr"], rec["cost_inr"], inr, inr)
            body += metric_row("Carbon (CO₂)", usual["carbon_kg"], rec["carbon_kg"], lambda v: f"{indian_number(v)} kg", lambda v: f"{indian_number(v)} kg")
            body += metric_row("Cooling Water (Est.)", usual["water_liters"], rec["water_liters"], lambda v: f"{indian_number(v)} L", lambda v: f"{indian_number(v)} L")

            if usual.get("avg_rate") is not None and rec.get("avg_rate") is not None:
                lab, tone = signed_pct(usual["avg_rate"], rec["avg_rate"])
                body += row("Effective Tariff Rate", f"₹{usual['avg_rate']:.2f}/kWh", f"₹{rec['avg_rate']:.2f}/kWh", f"<span class='{tone}'>{lab}</span>")

            if usual.get("solar_hours_pct") is not None and rec.get("solar_hours_pct") is not None:
                body += row("Solar-Window Utilization", f"{usual['solar_hours_pct']:.0f}%", f"{rec['solar_hours_pct']:.0f}%", "")

            if usual.get("grid_factor") is not None and rec.get("grid_factor") is not None:
                body += row("Grid Carbon Factor", f"{usual['grid_factor']:.2f} kg/kWh", f"{rec['grid_factor']:.2f} kg/kWh", "")

            wsi = getattr(getattr(optimizer, "physics", None), "water_stress", None)
            if isinstance(wsi, dict) and usual["region"] in wsi and rec["region"] in wsi:
                body += row("Regional Water Stress (WRI)", f"{wsi[usual['region']]:.1f}", f"{wsi[rec['region']]:.1f}", "")

            html_block(f"""<div class='sx-card'>
                <div class='sx-h'>
                    <h3>Baseline vs Recommendation</h3>
                    <span>Detailed resource delta</span>
                </div>
                <div class='sx-scroll'>
                    <table class='sx-table'>
                        <thead><tr><th>Metric</th><th>Usual Plan</th><th class='r'>Recommended</th><th>Delta</th></tr></thead>
                        <tbody>{body}</tbody>
                    </table>
                </div>
            </div>""")

        with col_cht:
            with st.container(border=True):
                html_block("<div class='sx-h'><h3>Comparative Impact & Rankings</h3><span>Visual Analytics</span></div>")
                t_impact, t_rank = st.tabs(["Impact Relative to Usual", "All Region Scores"])

                with t_impact:
                    names = ["Cost", "Carbon", "Water"]
                    vals = [r / u * 100 if u else 100 for u, r in (
                        (usual["cost_inr"], rec["cost_inr"]),
                        (usual["carbon_kg"], rec["carbon_kg"]),
                        (usual["water_liters"], rec["water_liters"])
                    )]
                    colors = ["#257849" if v < 99.5 else "#B53225" if v > 100.5 else "#7D7569" for v in vals]
                    fig = go.Figure(go.Bar(
                        y=names, x=vals, orientation="h", marker_color=colors,
                        text=[f"{v:.0f}%" for v in vals], textposition="outside",
                        cliponaxis=False, hoverinfo="skip"
                    ))
                    fig.add_vline(
                        x=100, line_width=1.5, line_dash="dash", line_color="#7D7569",
                        annotation_text="Baseline = 100%", annotation_position="top",
                        annotation_font=dict(size=11, color="#7D7569")
                    )
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=10, r=45, t=28, b=10), height=260,
                        xaxis=dict(visible=False, range=[0, max(max(vals), 100) * 1.25]),
                        yaxis=dict(autorange="reversed", tickfont=dict(size=12, color="#1A1713")),
                        font=dict(family="Inter", color="#1A1713"), showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                    html_block("<div class='sx-cap' style='margin-top:2px'>Values under 100% represent resource reductions compared to starting immediately at the baseline location.</div>")

                with t_rank:
                    rows_all = run["results"].get("all_options") or []
                    if rows_all and all("score" in r_ and "region" in r_ for r_ in rows_all):
                        df_all = pd.DataFrame(rows_all)
                        best = df_all.loc[df_all.groupby("region")["score"].idxmin()].sort_values("score").reset_index(drop=True)
                        fig2 = go.Figure(go.Bar(
                            y=best["region"], x=best["score"], orientation="h",
                            text=best["score"].round().astype(int), textposition="outside",
                            cliponaxis=False, hoverinfo="skip",
                            marker_color=["#B76A00" if r_ == rec["region"] else "#DFD6C2" for r_ in best["region"]]
                        ))
                        fig2.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=10, r=40, t=10, b=10), height=260,
                            xaxis=dict(visible=False, range=[0, float(best["score"].max()) * 1.2]),
                            yaxis=dict(autorange="reversed", tickfont=dict(size=12, color="#1A1713")),
                            font=dict(family="Inter", color="#1A1713"), showlegend=False
                        )
                        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
                        html_block("<div class='sx-cap' style='margin-top:2px'>Composite penalty score per region under current priority weights (lower score is superior).</div>")
                    else:
                        st.markdown("<div class='sx-cap'>Regional score distribution unavailable for this run.</div>", unsafe_allow_html=True)

    # 3. DevOps Handoff Tab
    with tab_devops:
        html_block("<div class='sx-card'><div class='sx-h'><h3>Automated Kubernetes & GitOps Handoff</h3><span>Cluster Deployment</span></div><p class='sx-note'>Directly apply to your target cluster or submit to GitOps repo. Verified against region topology.</p></div>")
        callout("info", "<b>Deployment specification:</b> Ready to apply via <code>kubectl</code>. Cluster resource availability should be confirmed prior to deployment.")
        if run["errors"].get("k8s") or run.get("k8s") is None:
            callout("bad", "Kubernetes payload generation failed.")
        else:
            payload = run["k8s"]
            is_json = True
            try:
                json.loads(payload)
            except Exception:
                is_json = False
            st.code(payload, language="json" if is_json else "yaml")
            st.download_button(
                "Download Kubernetes manifest",
                data=payload,
                file_name=f"sunshift_manifest_{rec['region'].lower().replace(' ', '_')}.{'json' if is_json else 'yaml'}",
                mime="application/json" if is_json else "text/yaml",
                key="dl_k8s"
            )
        if pause and run.get("pause") and pause.get("cron"):
            html_block("<div class='sx-sub'>Automated Slurm / Cron Dispatch Script</div>")
            st.code(pause["cron"], language="bash")

    # 4. ESG / BRSR Audit Tab
    with tab_audit:
        html_block("<div class='sx-card'><div class='sx-h'><h3>SEBI Business Responsibility and Sustainability Reporting (BRSR)</h3><span>ESG Audit Trail</span></div><p class='sx-note'>Model calculations structured for corporate ESG disclosures under SEBI BRSR (Principal 6: Energy & GHG emissions). These are deterministic model estimates.</p></div>")
        if run.get("csv") is None:
            callout("bad", "Audit CSV generation failed.")
        else:
            csv_data = run["csv"]
            st.download_button(
                "Download ESG / BRSR Compliance CSV",
                data=csv_data,
                file_name=f"sunshift_brsr_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                key="dl_csv"
            )
            with st.expander("Preview CSV audit record"):
                try:
                    df_preview = pd.read_csv(io.StringIO(csv_data if isinstance(csv_data, str) else csv_data.decode("utf-8")))
                    st.dataframe(df_preview, use_container_width=True, hide_index=True)
                except Exception:
                    st.code(csv_data if isinstance(csv_data, str) else csv_data.decode("utf-8", "ignore"))

    # 5. Data Trust & Methodology Tab
    with tab_trust:
        report = run.get("trust")
        if not report:
            callout("bad", "Data trust audit report could not be generated.")
        else:
            if meta_real.get("ml_hours_share") is not None:
                share = meta_real["ml_hours_share"]
                html_block(f"<div class='sx-note' style='font-size:13px'>Forecast telemetry: <b>{(1 - share) * 100:.0f}%</b> from Open-Meteo cache, <b>{share * 100:.0f}%</b> synthesized by Sunshift ML forecaster.</div>")

            html_block("<div class='sx-sub'>Active Data Quality Flags</div>")
            for flag in report.get("active_flags", []):
                callout(trust_level(flag), esc(clean_flag(flag)))

            html_block("<div class='sx-sub'>Data Sources & Authority</div>")
            rows_html = "".join(
                f"<div class='sx-trow'><div class='n'>{esc(k.replace('_', ' '))}</div>"
                f"<div class='d'>{esc(v.get('source', ''))} ({esc(v.get('date', ''))}) · {esc(v.get('unit', ''))}<small>{esc(v.get('caveat', ''))}</small></div>"
                f"<div>{type_badge(v.get('type', 'unspecified'))}</div></div>"
                for k, v in report.get("sources", {}).items()
            )
            html_block(f"<div class='sx-card' style='padding:6px 20px'>{rows_html}</div>")

            html_block("<div class='sx-sub'>Hardware & Physical Modeling Assumptions</div>")
            a_html = "".join(
                f"<div class='sx-trow'><div class='n'>{esc(k.replace('_', ' '))}</div>"
                f"<div class='d'>{esc(v.get('value', ''))} {esc(v.get('unit', ''))}<small>{esc(v.get('notes', ''))}</small></div>"
                f"<div><span class='sx-chip amber'>Assumption</span></div></div>"
                for k, v in report.get("assumptions", {}).items()
            )
            html_block(f"<div class='sx-card' style='padding:6px 20px'>{a_html}</div>")

            html_block("<div class='sx-sub'>Model Limitations & Disclaimers</div>")
            for text in report.get("disclaimers", {}).values():
                html_block(f"<div class='sx-note' style='font-size:13px'>• {esc(text)}</div>")

        with st.expander("Methodology Glossary"):
            st.markdown(
                "- **PUE (Power Usage Effectiveness):** Total data center energy consumed divided by direct IT load. Modeled dynamically using wet-bulb temperature scaling.\n"
                "- **CEA Grid Factor:** Central Electricity Authority baseline CO₂ emissions per kWh for the regional grid.\n"
                "- **WRI Water Stress Index:** World Resources Institute localized baseline water stress scoring scarcity in the river basin.\n"
                "- **Checkpoint Overhead:** Productivity minutes lost writing and validating GPU memory checkpoints to persistent storage during pauses."
            )

    html_block(f"<div class='sx-cap' style='text-align:right;margin-top:20px'>Calculated at {esc(run['computed_at'].strftime('%d %b %Y, %I:%M %p'))} · All calculations are model estimates.</div>")


# =====================================================================================
# Main Execution Pipeline
# =====================================================================================
if st.session_state.busy:
    render_loading()
    try:
        st.session_state.run = compute_run(st.session_state.pending_inputs)
        st.session_state.error = None
    except Exception as exc:
        logger.exception("Optimization failed")
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
