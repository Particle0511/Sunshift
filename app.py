from src.formatting import describe_start
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import textwrap
from src.core.optimizer import WorkloadOptimizer
from src.core.comparator import ResultsComparator
from src.agent.explainer import ReasonExplainer

st.set_page_config(page_title="Sunshift", layout="wide", initial_sidebar_state="expanded")


if "w_cost" not in st.session_state: st.session_state.w_cost = 70
if "w_carbon" not in st.session_state: st.session_state.w_carbon = 80
if "w_water" not in st.session_state: st.session_state.w_water = 60

def sync_cost_sld(): st.session_state.w_cost = st.session_state.cost_sld
def sync_cost_num(): st.session_state.w_cost = st.session_state.cost_num
def sync_carb_sld(): st.session_state.w_carbon = st.session_state.carb_sld
def sync_carb_num(): st.session_state.w_carbon = st.session_state.carb_num
def sync_wat_sld(): st.session_state.w_water = st.session_state.wat_sld
def sync_wat_num(): st.session_state.w_water = st.session_state.wat_num


def get_delta_html(usual_val, rec_val):
    if usual_val <= 0: return "<span style='color:#64748b; font-weight:600;'>0% -</span>"
    pct = round(((usual_val - rec_val) / usual_val) * 100)
    if pct > 0: return f"<span style='color:#16a34a; font-weight:700;'>-{pct}% ↓</span>"
    elif pct < 0: return f"<span style='color:#dc2626; font-weight:700;'>+{abs(pct)}% ↑</span>"
    else: return "<span style='color:#64748b; font-weight:600;'>0% -</span>"

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inria+Serif:wght@300;400;700&display=swap');

    html, body, [class*="css"], [class*="st-"] { font-family: 'Inria Serif', serif !important; }
    #MainMenu, footer, header { visibility: hidden; }

    .top-nav {
        background-color: #171b26;
        color: white;
        padding: 10px 20px;
        font-size: 20px;
        font-weight: 700;
        margin-top: -60px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
    }

    /* Premium Light Beige/Grey styling strictly for the left input container */
    [data-testid="stColumn"]:first-of-type > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #f9f8f6;
        border: 1px solid #e5e5e4;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }

    .hero-card {
        background-color: #171b26;
        color: white;
        padding: 30px;
        border-radius: 4px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
    }

    /* Pulsing Animation for the Recommended Badge */
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.6; }
        100% { opacity: 1; }
    }
    .pulse-badge {
        color: #ef4444;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        margin-bottom: 15px;
        animation: pulse 2s infinite ease-in-out;
    }

    div.stButton > button:first-child {
        background-color: #c52233;
        color: white;
        font-weight: bold;
        border-radius: 4px;
        border: none;
        padding: 10px;
        transition: 0.3s;
    }
    div.stButton > button:hover { background-color: #a11b29; color: white; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(197,34,51,0.3); }

    .lbl { font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px; text-transform: uppercase; }
    .val-main { font-size: 22px; font-weight: 700; color: #0f172a; }
    .val-sub { font-size: 13px; color: #64748b; }
    
    .priority-lbl { font-size: 13px; font-weight: 700; color: #0f172a; margin-bottom: -10px; }
</style>

<div class="top-nav">
    <div><span style="color:#c52233;">■</span> Sunshift</div>
    <div style="font-size: 14px; color: #94a3b8; font-weight: 400; padding-top:4px; font-family: sans-serif;">INDIA</div>
</div>
""", unsafe_allow_html=True)

@st.cache_resource
def load_engines():
    return WorkloadOptimizer(), ReasonExplainer()

optimizer, explainer = load_engines()

left_col, right_col = st.columns([1, 2.5], gap="large")

with left_col:
    with st.container(border=True):
        st.markdown("<div class='lbl'>YOUR JOB(HOURS)</div>", unsafe_allow_html=True)
        gpu_hours = st.number_input("GPU HOURS", value=10000, step=1000, min_value=1, label_visibility="collapsed", help="Total computational hours required to complete this AI workload.")

        st.write("")
        st.markdown("<div class='lbl'>DEADLINE(DAYS)</div>", unsafe_allow_html=True)
        deadline = st.number_input("DEADLINE (days)", value=5, min_value=1, label_visibility="collapsed", help="Maximum allowable days before the job must be finished.")

        st.write("")
        st.markdown("<div class='lbl'>JOB TYPE</div>", unsafe_allow_html=True)
        is_flexible = st.radio("JOB TYPE", ["Flexible", "Urgent"], horizontal=True, label_visibility="collapsed", help="Flexible allows Sunshift to scan up to 72 hours ahead for optimal climate windows. Urgent forces an immediate start.") == "Flexible"

        st.write("")
        st.markdown("<div class='lbl'>CURRENT DATA CENTER (USUAL)</div>", unsafe_allow_html=True)
        usual_choice = st.selectbox("USUAL", ["Mumbai", "Delhi NCR", "Bengaluru", "Chennai", "Hyderabad"], label_visibility="collapsed", help="Your default baseline data center for comparison.")

        st.write("")
        st.markdown("<div class='lbl'>DATA MUST STAY IN INDIA</div>", unsafe_allow_html=True)
        data_india = st.radio("DATA MUST STAY IN INDIA", ["Yes", "No"], horizontal=True, label_visibility="collapsed", help="Regulatory toggle. 'Yes' restricts placement strictly to domestic Indian grid regions.")

        st.markdown("<hr style='margin: 20px 0; border-color: #e5e5e4;'>", unsafe_allow_html=True)
        st.markdown("<div class='lbl'>WHAT MATTERS MOST</div>", unsafe_allow_html=True)

        st.markdown("<div class='priority-lbl'>Save money</div>", unsafe_allow_html=True)
        sc1, nc1 = st.columns([3, 1.2])
        sc1.slider("Cost", 0, 100, key="cost_sld", value=st.session_state.w_cost, on_change=sync_cost_sld, label_visibility="collapsed")
        nc1.number_input("CostNum", 0, 100, key="cost_num", value=st.session_state.w_cost, on_change=sync_cost_num, label_visibility="collapsed")

        st.markdown("<div class='priority-lbl'>Cut carbon</div>", unsafe_allow_html=True)
        sc2, nc2 = st.columns([3, 1.2])
        sc2.slider("Carbon", 0, 100, key="carb_sld", value=st.session_state.w_carbon, on_change=sync_carb_sld, label_visibility="collapsed")
        nc2.number_input("CarbonNum", 0, 100, key="carb_num", value=st.session_state.w_carbon, on_change=sync_carb_num, label_visibility="collapsed")

        st.markdown("<div class='priority-lbl'>Protect water</div>", unsafe_allow_html=True)
        sc3, nc3 = st.columns([3, 1.2])
        sc3.slider("Water", 0, 100, key="wat_sld", value=st.session_state.w_water, on_change=sync_wat_sld, label_visibility="collapsed")
        nc3.number_input("WaterNum", 0, 100, key="wat_num", value=st.session_state.w_water, on_change=sync_wat_num, label_visibility="collapsed")

        total_weight = st.session_state.w_cost + st.session_state.w_carbon + st.session_state.w_water
        weights = {
            "cost": st.session_state.w_cost / total_weight if total_weight > 0 else 0.33,
            "carbon": st.session_state.w_carbon / total_weight if total_weight > 0 else 0.33,
            "water": st.session_state.w_water / total_weight if total_weight > 0 else 0.33
        }

        st.write("")
        run_optimization = st.button("Find best place and time", use_container_width=True)

with right_col:
    if run_optimization:
        with st.spinner("Analyzing grid tariffs and climate forecasts..."):
            results = optimizer.find_best_placement(gpu_hours, deadline, weights, is_flexible, usual_region=usual_choice)
            usual = results["usual"]
            rec = results["recommended"]
            meta = results.get("meta", {"confidence_label": "High", "finish_day": 1, "deadline_days": deadline})
            savings = ResultsComparator.calculate_savings(usual, rec)
            reason = explainer.generate_reason(usual, rec)

        start_dt = datetime.strptime(rec['start_time'], "%Y-%m-%d %H:%M")
        try:
            start_str = describe_start(start_dt)
        except:
            start_str = f"{'today' if start_dt.date() == datetime.now().date() else 'tomorrow'} at {start_dt.strftime('%I %p').lstrip('0')}"

        with st.container(border=True):
            html_card = (
                "<div class='hero-card'>"
                "<div style='width: 55%;'>"
                "<div class='pulse-badge'>RECOMMENDED</div>"
                f"<div style='font-size: 38px; font-weight: 700; margin-bottom: 20px; line-height: 1.2;'>Run it in {rec['region']},<br>{start_str}.</div>"
                f"<div style='color: #94a3b8; font-size: 16px; margin-bottom: 20px; line-height: 1.5;'>{reason}</div>"
                f"<div style='font-size:12px; color:#64748b; font-family: sans-serif;'>Every number is an estimate. Confidence: {meta['confidence_label']}. Est. completion: Day {meta['finish_day']} (Deadline: {meta['deadline_days']} Days).</div>"
                "</div>"
                "<div style='width: 40%; border-left: 1px solid #334155; padding-left: 30px; display: flex; flex-direction: column; justify-content: center; font-family: sans-serif;'>"
                "<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; gap: 10px;'>"
                f"<div style='font-size: 26px; font-weight: 700; white-space:nowrap;'>₹{savings['cost_saved_inr']:,.0f}</div>"
                f"<div style='font-size:12px; color:#94a3b8; text-align:right; white-space:nowrap;'>saved on electricity / {savings['cost_pct']}%</div>"
                "</div>"
                "<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; gap: 10px;'>"
                f"<div style='font-size: 26px; font-weight: 700; white-space:nowrap;'>{savings['carbon_saved_kg']:,.0f}</div>"
                f"<div style='font-size:12px; color:#94a3b8; text-align:right; white-space:nowrap;'>less carbon / {savings['carbon_pct']}%</div>"
                "</div>"
                "<div style='display:flex; justify-content:space-between; align-items:center; gap: 10px;'>"
                f"<div style='font-size: 26px; font-weight: 700; white-space:nowrap;'>{savings['water_saved_liters']:,.0f}</div>"
                f"<div style='font-size:12px; color:#94a3b8; text-align:right; white-space:nowrap;'>less cooling water / {savings['water_pct']}%</div>"
                "</div>"
                "</div>"
                "</div>"
            )
            st.markdown(html_card, unsafe_allow_html=True)

            c_table, c_graph = st.columns([1.5, 1.1], gap="large")

            with c_table:
             
                cost_delta_ui = get_delta_html(usual['cost_inr'], rec['cost_inr'])
                carb_delta_ui = get_delta_html(usual['carbon_kg'], rec['carbon_kg'])
                wat_delta_ui = get_delta_html(usual['water_liters'], rec['water_liters'])

                html_table = (
                    "<div style='display: grid; grid-template-columns: 1.2fr 1.3fr 1.3fr 0.6fr; gap: 15px; align-items: center; margin-top:10px;'>"
                    "<div></div>"
                    f"<div style='text-align: center; background-color: #f1f5f9; padding: 12px 8px; border-radius: 8px;'><div class='lbl'>USUAL CHOICE</div><div class='val-main'>{usual['region']}</div><div class='val-sub' style='margin-top:2px;'>Start Now</div></div>"
                    f"<div style='text-align: center; background-color: #fef2f2; padding: 12px 8px; border-radius: 8px;'><div class='lbl' style='color:#c52233;'>RECOMMENDED</div><div class='val-main'>{rec['region']}</div><div class='val-sub' style='margin-top:2px;'>{start_str}</div></div>"
                    "<div style='text-align: right; padding-bottom:5px;'><div class='lbl'>CHANGE</div></div>"
                    
                    "<div style='grid-column: 1 / -1; border-top: 1px solid #cbd5e1; margin: 10px 0 5px 0;'></div>"
                    
                    "<div class='val-sub'>Electricity cost</div>"
                    f"<div class='val-main' style='text-align:center; white-space:nowrap;'>₹{usual['cost_inr']:,.0f}</div>"
                    f"<div class='val-main' style='text-align:center; white-space:nowrap;'>₹{rec['cost_inr']:,.0f}</div>"
                    f"<div style='text-align:right; font-family:sans-serif;'>{cost_delta_ui}</div>"
                    
                    "<div style='grid-column: 1 / -1; border-top: 1px solid #e2e8f0; margin: 5px 0;'></div>"
                    
                    "<div class='val-sub'>Carbon</div>"
                    f"<div style='text-align:center; white-space:nowrap;'><span class='val-main'>{usual['carbon_kg']:,.0f}</span> <span class='val-sub'>kg CO₂</span></div>"
                    f"<div style='text-align:center; white-space:nowrap;'><span class='val-main'>{rec['carbon_kg']:,.0f}</span> <span class='val-sub'>kg CO₂</span></div>"
                    f"<div style='text-align:right; font-family:sans-serif;'>{carb_delta_ui}</div>"
                    
                    "<div style='grid-column: 1 / -1; border-top: 1px solid #e2e8f0; margin: 5px 0;'></div>"
                    
                    "<div class='val-sub'>Cooling water</div>"
                    f"<div style='text-align:center; white-space:nowrap;'><span class='val-main'>{usual['water_liters']:,.0f}</span> <span class='val-sub'>liters</span></div>"
                    f"<div style='text-align:center; white-space:nowrap;'><span class='val-main'>{rec['water_liters']:,.0f}</span> <span class='val-sub'>liters</span></div>"
                    f"<div style='text-align:right; font-family:sans-serif;'>{wat_delta_ui}</div>"
                    
                    "<div style='grid-column: 1 / -1; border-top: 1px solid #e2e8f0; margin: 5px 0;'></div>"
                    "</div>"
                )
                st.markdown(html_table, unsafe_allow_html=True)

            with c_graph:
                st.markdown("<div style='font-size:18px; margin-bottom:10px; font-weight:700; color:#0f172a;'>Impact Comparison</div>", unsafe_allow_html=True)

             
                categories = ['Cost', 'Carbon', 'Water']
                
                max_cost = max(usual['cost_inr'], rec['cost_inr'], 1)
                max_carb = max(usual['carbon_kg'], rec['carbon_kg'], 1)
                max_wat = max(usual['water_liters'], rec['water_liters'], 1)

                u_vals = [(usual['cost_inr'] / max_cost) * 100, (usual['carbon_kg'] / max_carb) * 100, (usual['water_liters'] / max_wat) * 100]
                r_vals = [(rec['cost_inr'] / max_cost) * 100, (rec['carbon_kg'] / max_carb) * 100, (rec['water_liters'] / max_wat) * 100]

                fig = go.Figure(data=[
                    go.Bar(name=f"Usual: {usual['region']}", x=categories, y=u_vals, marker_color='#94a3b8'),
                    go.Bar(name=f"Rec: {rec['region']}", x=categories, y=r_vals, marker_color='#c52233')
                ])
                
                fig.update_layout(
                    barmode='group',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=280,
                    yaxis=dict(showgrid=True, gridcolor='#f1f5f9', visible=False),
                    xaxis=dict(tickfont=dict(family="Inria Serif", size=14, color="#0f172a")),
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5, font=dict(family="Inria Serif", size=13))
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    else:
        st.info("Adjust your job parameters on the left and click **Find best place and time**.")