"""
DeptOps AI — Streamlit Dashboard
Beautiful UI with proper separation of concerns.
All agent imports are lazy to avoid Streamlit cache issues.
"""

import sys
for _mod in list(sys.modules.keys()):
    if "agents." in _mod or _mod == "config":
        sys.modules.pop(_mod, None)

from pathlib import Path
try:
    import streamlit as st
except ImportError as e:
    raise ImportError("Streamlit is required. Install with 'pip install streamlit'") from e

import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError as e:
    raise ImportError("Plotly is required for visualizations. Install with 'pip install plotly'") from e

from config import OPENROUTER_MODEL, ANALYTICS_DATA_DIR, DOCUMENTS_DIR
from auth import auth_gate

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DeptOps AI", page_icon="🎓",
    layout="wide", initial_sidebar_state="expanded"
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
    --accent: #0f9d8a;
    --accent-2: #2f7cb8;
    --page-bg: var(--background-color);
    --surface: var(--secondary-background-color);
    --text: var(--text-color);
    --edge: rgba(127, 127, 127, 0.28);
    --nav-surface: rgba(255, 255, 255, 0.06);
    --nav-surface-strong: rgba(255, 255, 255, 0.12);
}

html, body, [class*="css"] {
    font-family: 'Manrope', sans-serif;
    color: var(--text);
}

.stApp {
    background:
        radial-gradient(circle at 12% 12%, rgba(15, 157, 138, 0.08), transparent 34%),
        radial-gradient(circle at 86% 10%, rgba(47, 124, 184, 0.06), transparent 34%),
        var(--page-bg);
}

.stApp > header, #MainMenu, footer,
[data-testid="stDeployButton"], .stDeployButton,
button[kind="header"], [data-testid="stHeader"], .stAppHeader {
    display: none !important;
}

.block-container {
    padding-top: 1.15rem !important;
    max-width: 1240px;
}

[data-testid="stSidebar"] .block-container {
    padding-top: 0.85rem !important;
}

[data-testid="stSidebarHeader"] {
    display: none !important;
}

.app-topbar-brand {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1.2;
}
.app-topbar-model {
    font-size: 0.74rem;
    opacity: 0.78;
    margin-top: 2px;
}
.app-topbar-user {
    text-align: right;
    font-size: 0.84rem;
    font-weight: 600;
    line-height: 1.25;
}
.app-topbar-user span {
    display: block;
    font-size: 0.72rem;
    font-weight: 500;
    opacity: 0.75;
}

.top-nav {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.1rem 0 0.45rem;
    margin-bottom: 0.8rem;
}
button[kind="primary"], button[kind="secondary"] {
    border-radius: 999px !important;
    padding: 0.62rem 1rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.01em;
    border: 1px solid transparent !important;
}
button[kind="primary"] {
    background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
    color: #ffffff !important;
    box-shadow: 0 12px 24px rgba(15, 157, 138, 0.18);
}
button[kind="secondary"] {
    background: rgba(127, 127, 127, 0.10) !important;
    color: var(--text) !important;
}
button[kind="primary"]:hover,
button[kind="secondary"]:hover {
    transform: translateY(-1px);
}
.profile-chip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    justify-content: center;
    border-radius: 11px;
    padding: 0.45rem 0.8rem;
    background: var(--surface);
    border: 1px solid var(--edge);
    height: 100%;
}
.profile-avatar {
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.9rem;
    color: #fff;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    flex: 0 0 auto;
}
.profile-meta {
    min-width: 0;
    text-align: left;
}
.profile-meta strong {
    display: block;
    font-size: 0.8rem;
    line-height: 1.1;
}
.profile-meta span {
    display: block;
    font-size: 0.65rem;
    opacity: 0.76;
    line-height: 1.1;
}
/* Global readability */
section[data-testid="stMain"],
section[data-testid="stMain"] * {
    color: var(--text);
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--edge) !important;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem !important;
}
[data-testid="stSidebar"] * {
    color: var(--text) !important;
}
[data-testid="stSidebar"] .sidebar-brand {
    display: flex;
    align-items: center;
    gap: 0.85rem;
    padding: 0.15rem 0 0.35rem;
    margin-bottom: 2rem;
}
[data-testid="stSidebar"] .sidebar-brand-mark {
    width: 2.7rem;
    height: 2.7rem;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #fff;
    font-size: 1.15rem;
    box-shadow: 0 10px 22px rgba(15, 157, 138, 0.18);
}
[data-testid="stSidebar"] .sidebar-brand-title {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1rem;
    font-weight: 800;
    line-height: 1.2;
}
[data-testid="stSidebar"] .sidebar-brand-subtitle {
    font-size: 0.76rem;
    opacity: 0.76;
    margin-top: 0.2rem;
}
[data-testid="stSidebar"] .sidebar-section {
    margin-top: 0.8rem;
    padding: 0.9rem 1rem 1rem;
    border: 1px solid var(--edge);
    border-radius: 18px;
    background: rgba(127, 127, 127, 0.06);
}
[data-testid="stSidebar"] .sidebar-gap {
    height: 0.6rem;
}
[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] .stCaption {
    opacity: 0.85;
}
[data-testid="stSidebar"] .stFileUploader {
    margin-top: 0.4rem;
}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    background: transparent !important;
    border: 1.5px dashed var(--edge) !important;
    border-radius: 14px !important;
    padding: 1rem !important;
}
[data-testid="stSidebar"] .stButton > button {
    border-radius: 14px !important;
    padding: 0.7rem 0.95rem !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: var(--surface);
    border: 1px solid var(--edge);
    border-radius: 16px;
    padding: 6px;
    margin-bottom: 1.5rem;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.9rem !important;
    color: var(--text) !important;
    border-radius: 10px !important;
    padding: 10px 18px !important;
    opacity: 0.9;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(127, 127, 127, 0.12) !important;
    opacity: 1;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
    color: #ffffff !important;
    opacity: 1;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

/* Hero */
.hero {
    background: linear-gradient(130deg, rgba(15,157,138,0.16), rgba(47,124,184,0.16));
    border: 1px solid var(--edge);
    border-radius: 24px;
    padding: 34px 38px;
    margin-bottom: 26px;
    color: var(--text);
    box-shadow: 0 10px 26px rgba(0,0,0,0.12);
    position: relative;
    overflow: hidden;
}
.hero::before,
.hero::after {
    content: '';
    position: absolute;
    border-radius: 50%;
    background: rgba(255,255,255,0.22);
}
.hero::before {
    top: -72px;
    right: -44px;
    width: 240px;
    height: 240px;
}
.hero::after {
    bottom: -76px;
    right: 112px;
    width: 170px;
    height: 170px;
}
.hero h1 {
    margin: 0 0 10px;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2.15rem;
    font-weight: 700;
}
.hero p {
    margin: 0;
    line-height: 1.7;
    opacity: 0.95;
}
.hero-pill {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    border: 1px solid var(--edge);
    background: rgba(255,255,255,0.3);
    font-size: 0.78rem;
    font-weight: 700;
    margin-bottom: 14px;
}

/* Cards */
.agent-card,
.step-card,
.data-card,
.chat-answer,
[data-testid="stMetric"],
.streamlit-expanderHeader {
    background: var(--surface) !important;
    border: 1px solid var(--edge) !important;
    color: var(--text) !important;
}

.agent-card {
    border-radius: 20px;
    padding: 26px 22px;
    text-align: center;
    transition: all 0.2s ease;
    box-shadow: 0 8px 22px rgba(0,0,0,0.12);
    height: 100%;
}
.agent-card:hover {
    transform: translateY(-5px);
}
.agent-icon {
    width: 60px;
    height: 60px;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.8rem;
    margin: 0 auto 16px;
}
.icon-blue  { background: linear-gradient(135deg,#d6eef9,#9cd2eb); }
.icon-amber { background: linear-gradient(135deg,#feeac6,#f7c772); }
.icon-green { background: linear-gradient(135deg,#cbf5e8,#88e4c6); }
.icon-purple{ background: linear-gradient(135deg,#dce2ff,#b3c3ff); }
.agent-card h3 {
    margin: 0 0 10px;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.04rem;
}
.agent-card p {
    opacity: 0.9;
}

.section-title {
    font-size: 1.14rem;
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    margin: 32px 0 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--edge);
    margin-left: 8px;
}

.stat-strip {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 20px;
}
.stat-pill {
    background: var(--surface);
    border: 1px solid var(--edge);
    border-radius: 12px;
    padding: 10px 18px;
    text-align: center;
    min-width: 90px;
}
.stat-pill .sp-val {
    font-size: 1.4rem;
    font-weight: 800;
    line-height: 1;
}
.stat-pill .sp-lbl {
    font-size: 0.7rem;
    opacity: 0.8;
    font-weight: 600;
    margin-top: 2px;
    text-transform: uppercase;
}

.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 14px;
}
.b-ana  { background: rgba(15,157,138,0.18); border: 1px solid var(--edge); }
.b-know { background: rgba(244,165,63,0.18); border: 1px solid var(--edge); }
.b-web  { background: rgba(47,124,184,0.18); border: 1px solid var(--edge); }

[data-testid="stMetric"] {
    border-radius: 14px;
    padding: 16px 20px !important;
}
[data-testid="stMetricLabel"] {
    text-transform: uppercase !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.6px !important;
}

/* Inputs and selectors must always inherit theme text */
.stTextInput input,
.stTextArea textarea,
.stSelectbox [data-baseweb="select"] > div,
.stSelectbox [data-baseweb="select"] input,
.stSelectbox [data-baseweb="select"] span {
    background: var(--surface) !important;
    color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important;
    border-color: var(--edge) !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    opacity: 0.7 !important;
}

.stButton > button {
    border-radius: 11px !important;
    font-weight: 600 !important;
    white-space: nowrap !important;
    padding-left: 0.2rem !important;
    padding-right: 0.2rem !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
    border: none !important;
    color: #ffffff !important;
}

.step-card {
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 12px;
    display: flex;
    gap: 14px;
    align-items: flex-start;
}
.step-num {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #ffffff;
    border-radius: 8px;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    flex-shrink: 0;
}
.step-text {
    line-height: 1.55;
}

.data-card {
    border-radius: 16px;
    padding: 20px;
}
.data-card h4 {
    margin: 0 0 12px;
    font-size: 0.95rem;
    font-family: 'Space Grotesk', sans-serif;
}
.data-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid var(--edge);
    font-size: 0.88rem;
}
.data-item:last-child {
    border-bottom: none;
}

[data-testid="stVerticalBlock"] > div {
    animation: reveal 0.3s ease-out;
}
@keyframes reveal {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
    .hero {
        padding: 26px 22px;
        border-radius: 18px;
    }
    .hero h1 {
        font-size: 1.72rem;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 9px 12px !important;
        font-size: 0.83rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ── Auth gate ───────────────────────────────────────────────────────────────────────────────
auth_gate()

# ── Helper functions ──────────────────────────────────────────────────────────

def load_df(path: str) -> pd.DataFrame:
    p = Path(path)
    return pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_excel(p)

def get_datasets() -> list[str]:
    d = Path(ANALYTICS_DATA_DIR)
    if not d.exists(): return []
    return [str(f) for f in sorted(d.iterdir())
            if f.suffix.lower() in (".csv",".xlsx",".xls") and not f.name.startswith(".")]

def get_doc_list() -> list[str]:
    d = Path(DOCUMENTS_DIR)
    if not d.exists(): return []
    return [f.name for f in sorted(d.iterdir())
            if f.suffix.lower() in (".pdf",".txt",".md") and not f.name.startswith(".")]

def get_chunk_count() -> int:
    try:
        import json
        p = Path(DOCUMENTS_DIR).parent / "chroma_db" / "tfidf_index.json"
        if not p.exists(): return 0
        return json.load(open(p)).get("N", 0)
    except: return 0

def compute_stats(df: pd.DataFrame) -> dict:
    stats = {}
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ","_") for c in df.columns]
    cols = df.columns.tolist()
    for rc in ("result","status","pass_fail"):
        if rc in cols:
            counts = df[rc].astype(str).str.strip().str.upper().value_counts()
            total = len(df)
            p = int(counts.get("PASS", counts.get("P",0)))
            f = int(counts.get("FAIL", counts.get("F",0)))
            stats.update({"total_students":total,"pass_count":p,"fail_count":f,
                "pass_percentage":round(p/total*100,2) if total else 0,
                "fail_percentage":round(f/total*100,2) if total else 0})
            break
    for ac in ("attendance","attendance_percentage","att_%"):
        if ac in cols:
            stats["avg_attendance"]=round(float(df[ac].mean()),2)
            stats["below_75_count"]=int((df[ac]<75).sum())
            stats["eligible_exam_count"]=int((df[ac]>=75).sum())
            break
    for gc in ("cgpa","gpa","aggregate"):
        if gc in cols:
            stats["avg_cgpa"]=round(float(df[gc].mean()),2)
            stats["placement_eligible"]=int((df[gc]>=6.0).sum())
            stats["placement_eligible_pct"]=round(stats["placement_eligible"]/len(df)*100,2)
            break
    for pc in ("placed","placement_status"):
        if pc in cols:
            pc_c = df[pc].astype(str).str.strip().str.upper().value_counts()
            placed=int(pc_c.get("YES",pc_c.get("Y",0)))
            total=stats.get("total_students",len(df))
            stats.update({"placed_count":placed,"total_students":total,
                "placement_rate_pct":round(placed/total*100,2) if total else 0})
            break
    skip={"total_marks","average_marks","cgpa","gpa","aggregate","attendance",
          "attendance_percentage","att_%","roll_no","student_id","id",
          "classes_held","classes_attended","semester"}
    num_cols=[c for c in df.select_dtypes(include="number").columns if c not in skip]
    if num_cols:
        avgs=df[num_cols].mean().round(2).to_dict()
        subj={k:v for k,v in avgs.items() if 0<=v<=100}
        if subj: stats["subject_averages"]=subj
    return stats

full_name = st.session_state.get("full_name", "HOD")
username = st.session_state.get("username", "hod")

if "nav_page" not in st.session_state:
    st.session_state.nav_page = "home"

def _logout():
    for k in ("authenticated", "username", "full_name"):
        st.session_state.pop(k, None)


def _set_nav(page: str):
    st.session_state.nav_page = page


def _profile_initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    if not parts:
        return "H"
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()

nav_cols = st.columns([1, 1, 1, 1, 1, 1, 2, 0.8])
nav_items = [
    ("🏠 Home", "home"),
    ("💬 Chat", "chat"),
    ("📊 Analytics", "analytics"),
    ("📚 Knowledge", "knowledge"),
    ("🌐 Website", "website"),
    ("ℹ️ About", "about"),
]
for idx, (label, page) in enumerate(nav_items):
    with nav_cols[idx]:
        st.button(
            label,
            key=f"nav_{page}",
            type="primary" if st.session_state.nav_page == page else "secondary",
            use_container_width=True,
            on_click=_set_nav,
            args=(page,),
        )

with nav_cols[6]:
    st.markdown(
        f"""
        <div class="profile-chip">
            <div class="profile-avatar">{_profile_initials(full_name)}</div>
            <div class="profile-meta">
                <strong>{full_name}</strong>
                <span>@{username}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with nav_cols[7]:
    st.button("Logout", key="logout_btn", use_container_width=True, on_click=_logout)

st.markdown('<div class="sidebar-gap"></div>', unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-mark">🎓</div>
            <div>
                <div class="sidebar-brand-title">DeptOps AI</div>
                <div class="sidebar-brand-subtitle">Academic ops workspace</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("**📂 Upload Dataset**")
        st.caption("CSV/Excel → Analytics Agent")
        up_csv = st.file_uploader("", type=["csv","xlsx","xls"], key="up_csv", label_visibility="collapsed")
        if up_csv:
            Path(ANALYTICS_DATA_DIR).mkdir(parents=True, exist_ok=True)
            (Path(ANALYTICS_DATA_DIR) / up_csv.name).write_bytes(up_csv.getbuffer())
            st.success(f"✅ {up_csv.name}")

    st.markdown('<div class="sidebar-gap"></div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**📄 Upload Document**")
        st.caption("PDF/TXT → Knowledge Base Agent")
        up_doc = st.file_uploader("", type=["pdf","txt"], key="up_doc", label_visibility="collapsed")
        if up_doc:
            Path(DOCUMENTS_DIR).mkdir(parents=True, exist_ok=True)
            (Path(DOCUMENTS_DIR) / up_doc.name).write_bytes(up_doc.getbuffer())
            st.success(f"✅ {up_doc.name} saved")
            st.info("👆 Click 'Re-index' below to make it searchable")

        docs = get_doc_list()
        if docs:
            st.caption(f"📚 Documents: {', '.join(docs)}")
        chunks = get_chunk_count()
        st.caption(f"🔢 Indexed chunks: {chunks}" if chunks else "⚠️ Not indexed yet")

        if st.button("🔄 Re-index Knowledge Base", use_container_width=True, type="secondary"):
            with st.spinner("Indexing documents..."):
                from agents.knowledge_agent import ingest_documents
                res = ingest_documents()
            if res["success"]:
                st.success(res["message"])
            else:
                st.error(res["message"])

    st.markdown('<div class="sidebar-gap"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("**🎯 Force Agent**")
        agent_choice = st.radio("Select Agent", ["🤖 Auto-detect","📊 Analytics","📚 Knowledge Base","🌐 Website Testing"],
                                index=0, label_visibility="collapsed")


# ── Navigation content ────────────────────────────────────────────────────────


# ════════════════════════════════════════════════════════════════
# HOME
# ════════════════════════════════════════════════════════════════
if st.session_state.nav_page == "home":
    st.markdown("""
<div class="hero">
    <span class="hero-pill">Academic Intelligence Workspace</span>
  <h1>🎓 DeptOps AI</h1>
  <p>Agentic AI Assistant for Academic Department Management<br>
  Powered by LangGraph · OpenRouter · Playwright · ChromaDB</p>
    <div class="stat-strip">
        <div class="stat-pill"><div class="sp-val">4</div><div class="sp-lbl">Agents</div></div>
        <div class="stat-pill"><div class="sp-val">1</div><div class="sp-lbl">Unified UI</div></div>
        <div class="stat-pill"><div class="sp-val">24/7</div><div class="sp-lbl">Assistant</div></div>
    </div>
</div>
""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""<div class="agent-card">
<div class="agent-icon icon-blue">📊</div>
<h3>Analytics Agent</h3>
<p>Upload CSV/Excel datasets. Ask about pass percentage, attendance, CGPA, placement stats, subject performance.</p>
</div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("""<div class="agent-card">
<div class="agent-icon icon-amber">📚</div>
<h3>Knowledge Base Agent</h3>
<p>Upload PDF/TXT documents (regulations, syllabus, handbooks). Ask policy questions — get answers from your docs.</p>
</div>""", unsafe_allow_html=True)
    with c3:
        st.markdown("""<div class="agent-card">
<div class="agent-icon icon-green">🌐</div>
<h3>Website Testing Agent</h3>
<p>Enter any department website URL. Checks broken links, slow pages, JS errors automatically.</p>
</div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-title">📌 Quick Start</div>', unsafe_allow_html=True)
    q1, q2 = st.columns(2)
    with q1:
        st.markdown("""
<div class="step-card">
    <div class="step-num">1</div>
    <div class="step-text"><strong>Upload your data</strong><br>Use the sidebar to add CSV/Excel datasets and PDF/TXT documents.</div>
</div>
<div class="step-card">
    <div class="step-num">2</div>
    <div class="step-text"><strong>Index documents</strong><br>Click <em>Re-index Knowledge Base</em> after uploading policy documents.</div>
</div>
<div class="step-card">
    <div class="step-num">3</div>
    <div class="step-text"><strong>Ask in natural language</strong><br>Use Chat for auto-routing or open a dedicated tab for focused work.</div>
</div>
        """, unsafe_allow_html=True)
    with q2:
        st.markdown("""
<div class="step-card">
    <div class="step-num">4</div>
    <div class="step-text"><strong>Track key outcomes</strong><br>Visual dashboards highlight pass rates, attendance risk, CGPA bands, and placement health.</div>
</div>
<div class="step-card">
    <div class="step-num">5</div>
    <div class="step-text"><strong>Run website audits</strong><br>Test department portals for broken links, performance issues, and JavaScript errors.</div>
</div>
<div class="step-card">
    <div class="step-num">6</div>
    <div class="step-text"><strong>Act faster</strong><br>Use findings and cited answers to make confident operational decisions.</div>
</div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">📁 Current Data</div>', unsafe_allow_html=True)
    d1, d2 = st.columns(2)
    with d1:
        datasets = get_datasets()
        if datasets:
            dataset_items = "".join([f'<div class="data-item">✅ {Path(d).name}</div>' for d in datasets])
            st.markdown(f'<div class="data-card"><h4>📊 Datasets Ready</h4>{dataset_items}</div>', unsafe_allow_html=True)
        else:
            st.warning("No datasets uploaded yet. Upload CSV/Excel from sidebar.")
    with d2:
        docs = get_doc_list()
        chunks = get_chunk_count()
        if docs:
            doc_items = "".join([f'<div class="data-item">✅ {d}</div>' for d in docs])
            st.markdown(
                f'<div class="data-card"><h4>📚 Documents Ready</h4>{doc_items}<div class="data-item">🔎 Indexed chunks: {chunks if chunks else 0}</div></div>',
                unsafe_allow_html=True
            )
            if not chunks:
                st.caption("⚠️ Not indexed yet — click Re-index")
        else:
            st.warning("No documents uploaded yet. Upload PDF/TXT from sidebar.")

# ════════════════════════════════════════════════════════════════
# CHAT
# ════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "chat":
    st.markdown('<div class="section-title">💬 Ask DeptOps AI</div>', unsafe_allow_html=True)

    with st.container(border=True):
        query = st.text_area("What would you like to know?", height=120, key="chat_q",
            placeholder="Examples:\n• What is the pass percentage of students?\n• What is the minimum attendance required?\n• Which subject has the lowest average marks?")
        
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            all_ds = get_datasets()
            ds_opts = ["Auto"] + [Path(d).name for d in all_ds]
            chosen_ds = st.selectbox("📂 Target Dataset", ds_opts, key="chat_ds",
                                     help="For analytics queries — selects which file to analyze")
            fp = None
            if chosen_ds != "Auto":
                fp = next((d for d in all_ds if Path(d).name == chosen_ds), None)
        with c2:
            url_in = st.text_input("🌐 Website URL", placeholder="https://...", key="chat_url",
                                   help="For website testing only")
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            submit_chat = st.button("Ask 🚀", type="primary", use_container_width=True, key="chat_go")

    if submit_chat:
        if not query.strip():
            st.warning("Please enter a question.")
        else:
            fmap = {"📊 Analytics":"analytics","📚 Knowledge Base":"knowledge","🌐 Website Testing":"website"}
            forced = fmap.get(agent_choice)
            with st.spinner("Thinking..."):
                try:
                    if forced == "analytics":
                        from agents.analytics_agent import run_analytics_agent
                        r = run_analytics_agent(query, file_path=fp)
                        final = {"intent":"analytics","result":r,"error":r.get("error")}
                    elif forced == "knowledge":
                        from agents.knowledge_agent import run_knowledge_agent
                        r = run_knowledge_agent(query)
                        final = {"intent":"knowledge","result":r,"error":r.get("error")}
                    elif forced == "website":
                        from agents.website_testing_agent import run_website_testing_agent
                        r = run_website_testing_agent(url_in or "")
                        final = {"intent":"website","result":r,"error":r.get("error")}
                    else:
                        from agents.coordinator_agent import process_query
                        final = process_query(query=query, file_path=fp, url=url_in or None)
                except Exception as e:
                    msg = str(e)
                    if "429" in msg or "rate" in msg.lower():
                        st.warning("⏳ LLM rate-limited. Showing computed results instead.")
                    else:
                        st.error(f"Error: {msg}")
                    final = None

            if final is None:
                st.stop()

            intent = final.get("intent","unknown")
            result = final.get("result",{})
            bmap = {"analytics":("b-ana","📊 Analytics Agent"),
                    "knowledge":("b-know","📚 Knowledge Agent"),
                    "website":("b-web","🌐 Website Testing Agent")}
            bcls, blabel = bmap.get(intent,("b-know","🤖 Agent"))
            st.markdown(f'<span class="badge {bcls}">{blabel}</span>', unsafe_allow_html=True)

            if intent == "analytics":
                with st.container(border=True):
                    st.markdown(result.get("answer","No answer."))
                stats = result.get("stats",{})
                if stats and any(k in stats for k in ("pass_count","avg_attendance","avg_cgpa")):
                    cols = st.columns(4)
                    kvs = [("Total", stats.get("total_students","—")),
                           ("Pass %", f"{stats.get('pass_percentage','—')}%"),
                           ("Attendance", f"{stats.get('avg_attendance','—')}%"),
                           ("CGPA", stats.get("avg_cgpa","—"))]
                    for c,(l,v) in zip(cols,kvs): c.metric(l,v)
                if result.get("file_used"):
                    st.caption(f"📂 Source: `{Path(result['file_used']).name}`")

            elif intent == "knowledge":
                with st.container(border=True):
                    st.markdown(result.get("answer","No answer."))
                if result.get("sources"):
                    st.caption("📎 Sources: " + ", ".join(result["sources"]))

            elif intent == "website":
                st.markdown(result.get("ai_report","No report."))
                s = result.get("summary",{})
                if s:
                    c1,c2,c3 = st.columns(3)
                    c1.metric("Pages",s.get("total_pages",0))
                    c2.metric("🔴 Broken",s.get("broken_count",0))
                    c3.metric("🟡 Slow",s.get("slow_count",0))

# ════════════════════════════════════════════════════════════════
# ANALYTICS DASHBOARD
# ════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "analytics":
    st.markdown('<div class="section-title">📊 Analytics Dashboard</div>', unsafe_allow_html=True)

    all_ds = get_datasets()
    if not all_ds:
        st.info("📂 No datasets found. Upload a CSV or Excel file from the sidebar.")
    else:
        ds_names = [Path(d).name for d in all_ds]
        chosen_name = st.selectbox("Select dataset", ds_names, key="ana_ds")
        chosen_path = all_ds[ds_names.index(chosen_name)]

        try:
            df = load_df(chosen_path)
        except Exception as e:
            st.error(f"Could not load: {e}")
            st.stop()

        c_info1, c_info2, c_info3 = st.columns(3)
        c_info1.metric("Rows", df.shape[0])
        c_info2.metric("Columns", df.shape[1])
        c_info3.metric("File", chosen_name)

        with st.expander("📋 Preview Data", expanded=False):
            st.dataframe(df.head(20), use_container_width=True)

        stats = compute_stats(df)
        df_n = df.copy()
        df_n.columns = [str(c).strip().lower().replace(" ","_") for c in df_n.columns]

        # ── Academic data detected
        if stats:
            kpis = []
            if "total_students" in stats:     kpis.append(("👥 Students", stats["total_students"]))
            if "pass_percentage" in stats:    kpis.append(("✅ Pass %", f"{stats['pass_percentage']}%"))
            if "fail_percentage" in stats:    kpis.append(("❌ Fail %", f"{stats['fail_percentage']}%"))
            if "avg_attendance" in stats:     kpis.append(("📅 Avg Attendance", f"{stats['avg_attendance']}%"))
            if "avg_cgpa" in stats:           kpis.append(("🎓 Avg CGPA", stats["avg_cgpa"]))
            if "placement_eligible" in stats: kpis.append(("💼 Placement Eligible", stats["placement_eligible"]))
            if "placed_count" in stats:       kpis.append(("🏢 Placed", stats["placed_count"]))
            if "placement_rate_pct" in stats: kpis.append(("📈 Placement Rate", f"{stats['placement_rate_pct']}%"))

            if kpis:
                st.markdown("#### 📌 Key Metrics")
                for i in range(0, len(kpis), 4):
                    chunk = kpis[i:i+4]
                    for col,(lbl,val) in zip(st.columns(len(chunk)), chunk):
                        col.metric(lbl, val)
                st.divider()

            cc1, cc2 = st.columns(2)
            # Pass/Fail pie
            if "pass_count" in stats and stats["pass_count"] + stats["fail_count"] > 0:
                with cc1:
                    fig = go.Figure(go.Pie(
                        labels=["Pass","Fail"], values=[stats["pass_count"],stats["fail_count"]],
                        marker_colors=["#2ecc71","#e74c3c"], hole=0.45,
                        textinfo="label+percent"))
                    fig.update_layout(title="Pass vs Fail", height=320, showlegend=True,
                                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)

            # Attendance histogram
            for ac in ("attendance","attendance_percentage","att_%"):
                if ac in df_n.columns:
                    with cc2:
                        fig2 = px.histogram(df_n, x=ac, nbins=15,
                                            title="Attendance Distribution",
                                            color_discrete_sequence=["#3498db"],
                                            labels={ac:"Attendance %"})
                        fig2.add_vline(x=75, line_dash="dash", line_color="#e74c3c",
                                       annotation_text="75% threshold", annotation_font_color="#e74c3c")
                        fig2.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0)",
                                           plot_bgcolor="rgba(0,0,0,0)")
                        st.plotly_chart(fig2, use_container_width=True)
                    break

            # Subject averages
            if "subject_averages" in stats:
                sa = stats["subject_averages"]
                colors = ["#2ecc71" if v>=60 else "#f39c12" if v>=45 else "#e74c3c" for v in sa.values()]
                fig3 = px.bar(x=[k.replace("_"," ").title() for k in sa.keys()], y=list(sa.values()),
                              title="Subject-wise Average Marks",
                              labels={"x":"Subject","y":"Average Marks"})
                fig3.update_traces(marker_color=colors)
                fig3.add_hline(y=40, line_dash="dash", line_color="#e74c3c",
                               annotation_text="Pass mark (40)")
                fig3.update_layout(height=380, paper_bgcolor="rgba(0,0,0,0)",
                                   plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig3, use_container_width=True)

            # CGPA distribution
            for gc in ("cgpa","gpa","aggregate"):
                if gc in df_n.columns:
                    c_g1, c_g2 = st.columns(2)
                    with c_g1:
                        fig4 = px.histogram(df_n, x=gc, nbins=20, title="CGPA Distribution",
                                            color_discrete_sequence=["#9b59b6"])
                        fig4.add_vline(x=6.0, line_dash="dash", line_color="#e67e22",
                                       annotation_text="Placement min (6.0)")
                        fig4.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)",
                                           plot_bgcolor="rgba(0,0,0,0)")
                        st.plotly_chart(fig4, use_container_width=True)

                    # CGPA buckets pie
                    with c_g2:
                        buckets = {"< 5.0": int((df_n[gc]<5).sum()),
                                   "5.0–6.0": int(((df_n[gc]>=5)&(df_n[gc]<6)).sum()),
                                   "6.0–7.5": int(((df_n[gc]>=6)&(df_n[gc]<7.5)).sum()),
                                   "7.5–9.0": int(((df_n[gc]>=7.5)&(df_n[gc]<9)).sum()),
                                   "9.0+": int((df_n[gc]>=9).sum())}
                        fig_b = px.pie(names=list(buckets.keys()), values=list(buckets.values()),
                                       title="CGPA Brackets",
                                       color_discrete_sequence=px.colors.sequential.Blues_r)
                        fig_b.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)")
                        st.plotly_chart(fig_b, use_container_width=True)
                    break

            # Placement pie
            if "placed" in df_n.columns:
                pc = df_n["placed"].astype(str).str.upper().value_counts().reset_index()
                pc.columns=["Status","Count"]
                fig5 = px.pie(pc, names="Status", values="Count", title="Placement Status",
                              color_discrete_sequence=["#2ecc71","#e74c3c"])
                fig5.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig5, use_container_width=True)

        # ── Non-academic / generic data
        else:
            st.info("ℹ️ No academic columns detected (result, attendance, CGPA, placement). "
                    "Showing generic statistics.")
            num_df = df_n.select_dtypes(include="number")
            if not num_df.empty:
                st.markdown("#### Statistical Summary")
                st.dataframe(num_df.describe().round(2), use_container_width=True)
                st.markdown("#### Column Distributions")
                for col in num_df.columns[:6]:
                    fig = px.histogram(df_n, x=col, nbins=30, title=f"{col}",
                                       color_discrete_sequence=["#3498db"])
                    fig.update_layout(height=250, paper_bgcolor="rgba(0,0,0,0)",
                                      plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(df.head(50), use_container_width=True)

        # Stats table always shown
        num_df = df.select_dtypes(include="number")
        if not num_df.empty:
            with st.expander("📋 Full Statistical Summary"):
                st.dataframe(num_df.describe().round(2), use_container_width=True)

# ════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "knowledge":
    st.markdown('<div class="section-title">📚 Knowledge Base</div>', unsafe_allow_html=True)

    docs = get_doc_list()
    chunks = get_chunk_count()

    if not docs:
        st.warning("No documents uploaded yet. Upload PDF or TXT files from the sidebar.")
    else:
        st.success(f"**{len(docs)} document(s) available:** {', '.join(docs)}")
        if not chunks:
            st.warning("⚠️ Documents not indexed yet. Click 'Re-index Knowledge Base' in the sidebar.")
        else:
            st.info(f"✅ Knowledge base ready — {chunks} chunks indexed from {len(docs)} document(s)")

    st.markdown("#### 🔍 Ask a Question")
    kb_query = st.text_input("Question about your documents", key="kb_q",
                              placeholder="e.g. What is the minimum attendance required?  |  What is the fee structure?")

    if st.button("Search 🔍", type="primary", key="kb_go"):
        if not kb_query.strip():
            st.warning("Please enter a question.")
        elif not chunks:
            st.error("Knowledge base is empty. Upload documents and click Re-index first.")
        else:
            with st.spinner("Searching knowledge base..."):
                from agents.knowledge_agent import run_knowledge_agent
                r = run_knowledge_agent(kb_query)

            st.markdown('<span class="badge b-know">📚 Knowledge Agent</span>', unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown(r.get("answer","No answer found."))
            if r.get("sources"):
                st.caption("📎 Sources: " + ", ".join(r["sources"]))

    st.divider()
    st.markdown("#### 💡 What can you ask?")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
- *What is the minimum attendance to sit for exams?*
- *What is the pass mark for end-semester exams?*
- *What is the grading system?*
- *What are the placement eligibility criteria?*
        """)
    with c2:
        st.markdown("""
- *What is the fee structure?*
- *How many credits are required to graduate?*
- *What is the revaluation procedure?*
- *What happens if a student has arrears?*
        """)

# ════════════════════════════════════════════════════════════════
# WEBSITE TESTER
# ════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "website":
    st.markdown('<div class="section-title">🌐 Website & Portal Tester</div>', unsafe_allow_html=True)
    st.markdown("Automatically checks your department website for broken links, slow pages, and JS errors.")

    web_url = st.text_input("Website URL", placeholder="https://cs.university.edu", key="web_url")

    if st.button("Run Tests 🔍", type="primary", key="run_web"):
        if not web_url.strip():
            st.warning("Please enter a URL.")
        else:
            with st.spinner(f"Testing {web_url}... (may take 30–60 seconds)"):
                from agents.website_testing_agent import run_website_testing_agent
                res = run_website_testing_agent(web_url.strip())

            if res.get("error") and not res.get("summary"):
                st.error(f"Could not test: {res['error']}")
            else:
                s = res["summary"]
                st.markdown("#### 📊 Test Summary")
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Pages Checked", s.get("total_pages",0))
                c2.metric("🔴 Broken", s.get("broken_count",0))
                c3.metric("🟡 Slow (>3s)", s.get("slow_count",0))
                c4.metric("⚠️ JS Errors", len(s.get("pages_with_console_errors",[])))

                overall = "🟢 Healthy" if s.get("broken_count",0)==0 and s.get("slow_count",0)==0 else "🔴 Issues Found"
                st.markdown(f"**Overall Status:** {overall}")

                st.divider()
                st.markdown("#### 📋 Report")
                st.markdown(res.get("ai_report",""))

                if s.get("all_pages"):
                    st.divider()
                    st.markdown("#### 🗂 Page-by-Page Results")
                    rows = [{"URL": p["url"],
                             "HTTP Status": p.get("status","—"),
                             "Load Time (ms)": p.get("load_time_ms","—"),
                             "Title": (p.get("title") or "")[:50],
                             "H1": "✅" if p.get("has_h1") else "❌",
                             "Result": "🔴 Broken" if p.get("broken") else "🟢 OK"}
                            for p in s["all_pages"]]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=300)

# ════════════════════════════════════════════════════════════════
# ABOUT
# ════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "about":
    st.markdown('<div class="section-title">ℹ️ About DeptOps AI</div>', unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("""
### What is DeptOps AI?
DeptOps AI is an **agentic AI platform** built for Heads of Departments (HODs) to manage academic operations efficiently from one place.

### Architecture
```
Your Query
    │
    ▼
Coordinator Agent
    ├── 📊 Analytics Agent
    │     Pandas + LLM
    ├── 📚 Knowledge Agent
    │     TF-IDF RAG + LLM
    └── 🌐 Website Agent
          Playwright + Report
```
        """)
    with c2:
        st.markdown("""
### Agents
| Agent | Technology | Purpose |
|-------|-----------|---------|
| 📊 Analytics | Pandas + Plotly | Data analysis |
| 📚 Knowledge | TF-IDF RAG | Policy Q&A |
| 🌐 Website | Playwright | Web testing |
| 🧠 Coordinator | Keyword routing | Auto-routing |

### Tech Stack
- **Python 3.11+**
- **LangChain + LangGraph**
- **OpenRouter** (LLM API)
- **Playwright** (web testing)
- **Streamlit** (UI)
- **TF-IDF** (document search)

</div>

### PDF Upload — How it works
When you upload a PDF:
1. It's saved to `data/documents/`
2. Click **Re-index Knowledge Base**
3. The PDF is parsed and split into chunks
4. Each chunk is indexed using TF-IDF
5. When you ask a question, relevant chunks are retrieved and answered
        """)
