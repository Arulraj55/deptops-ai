"""
DeptOps AI — Streamlit Dashboard
Agentic AI Assistant for NAAC Department Preparation
Powered by OpenRouter free models
"""

from pathlib import Path
import io
import json
import logging
import streamlit as st
import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError as e:
    raise ImportError("Plotly is required for visualizations. Install with 'pip install plotly'") from e

from auth import auth_gate
import db_storage
from api_client import (
    upload_analytics,
    list_analytics,
    upload_knowledge,
    list_knowledge,
    chunk_count as api_chunk_count,
    reindex as api_reindex,
    ask_analytics as api_ask_analytics,
    analytics_full as api_analytics_full,
    excel_report as api_excel_report,
    pdf_report as api_pdf_report,
    ask_knowledge as api_ask_knowledge,
    criterion_summary as api_criterion_summary,
    website_audit as api_website_audit,
    website_pdf_report as api_website_pdf_report,
    compare_datasets,
)

logger = logging.getLogger("DeptOpsAI-App")

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DeptOps AI — NAAC Department Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Modern CSS Theme ─────────────────────────────────────────────────────────
st.markdown("""
<style>
:root {
    --accent: #0f9d8a;
    --accent-2: #2f7cb8;
    --page-bg: var(--background-color);
    --surface: var(--secondary-background-color);
    --text: var(--text-color);
    --edge: rgba(127, 127, 127, 0.25);
}

html, body, [class*="css"] {
    font-family: system-ui, -apple-system, 'Space Grotesk', 'Segoe UI', sans-serif;
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
    padding-top: 1.1rem !important;
    max-width: 1280px;
}

/* Navigation buttons */
button[kind="primary"], button[kind="secondary"] {
    border-radius: 999px !important;
    padding: 0.6rem 1rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.01em;
    border: 1px solid transparent !important;
}
button[kind="primary"] {
    background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
    color: #ffffff !important;
    box-shadow: 0 10px 20px rgba(15, 157, 138, 0.2);
}
button[kind="secondary"] {
    background: rgba(127, 127, 127, 0.10) !important;
    color: var(--text) !important;
}

/* User Profile Chip */
.profile-chip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    justify-content: center;
    border-radius: 12px;
    padding: 0.4rem 0.8rem;
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
    font-size: 0.85rem;
    color: #fff;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
}

/* Sidebar Branding */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--edge) !important;
}
[data-testid="stSidebar"] .sidebar-brand {
    display: flex;
    align-items: center;
    gap: 0.85rem;
    padding: 0.2rem 0 0.5rem;
    margin-bottom: 1.5rem;
}
[data-testid="stSidebar"] .sidebar-brand-mark {
    width: 2.6rem;
    height: 2.6rem;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #fff;
    font-size: 1.2rem;
}

/* Hero Cards */
.hero {
    background: linear-gradient(130deg, rgba(15,157,138,0.15), rgba(47,124,184,0.15));
    border: 1px solid var(--edge);
    border-radius: 20px;
    padding: 28px 32px;
    margin-bottom: 22px;
}
.hero h1 {
    margin: 0 0 8px;
    font-size: 2rem;
    font-weight: 800;
}
.hero p {
    margin: 0;
    opacity: 0.9;
    line-height: 1.6;
}

/* Badges */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-bottom: 10px;
}
.b-ana  { background: rgba(15,157,138,0.2); border: 1px solid var(--edge); }
.b-know { background: rgba(244,165,63,0.2); border: 1px solid var(--edge); }
.b-web  { background: rgba(47,124,184,0.2); border: 1px solid var(--edge); }

/* Score Cards */
.score-card {
    background: var(--surface);
    border: 1px solid var(--edge);
    border-radius: 16px;
    padding: 16px;
    text-align: center;
}
.score-val {
    font-size: 1.8rem;
    font-weight: 800;
    color: var(--accent);
}
.score-lbl {
    font-size: 0.75rem;
    opacity: 0.8;
    text-transform: uppercase;
    font-weight: 700;
    margin-top: 4px;
}
</style>
""", unsafe_allow_html=True)

# ── Auth Gate ─────────────────────────────────────────────────────────────────
auth_gate()

# ── User Context ──────────────────────────────────────────────────────────────
full_name = st.session_state.get("full_name", "HOD")
username = st.session_state.get("username", "hod")

if "nav_page" not in st.session_state:
    st.session_state.nav_page = "coordinator"


def _logout():
    for k in ("authenticated", "username", "full_name"):
        st.session_state.pop(k, None)


def _set_nav(page: str):
    st.session_state.nav_page = page


def _profile_initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper() if parts else "H"


# Cached DB Helpers
@st.cache_data(ttl=30, show_spinner=False)
def get_datasets(user: str) -> list[str]:
    try:
        rows = list_analytics(user)
        # `list_analytics` returns list of dicts with filename keys or simple list
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return [r.get("filename") for r in rows]
        return list(rows or [])
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def get_doc_list(user: str) -> list[str]:
    try:
        return list_knowledge(user)
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def get_chunk_count(user: str) -> int:
    try:
        return api_chunk_count(user)
    except Exception:
        return 0


# ── Top Navigation Bar ────────────────────────────────────────────────────────
nav_cols = st.columns([1.2, 1.2, 1.2, 1.2, 2.2, 0.8])
nav_items = [
    ("🧠 Coordinator", "coordinator"),
    ("📊 Analytics", "analytics"),
    ("📚 Knowledge", "knowledge"),
    ("🌐 Website Testing", "website"),
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

with nav_cols[4]:
    st.markdown(
        f"""
        <div class="profile-chip">
            <div class="profile-avatar">{_profile_initials(full_name)}</div>
            <div>
                <strong style="font-size: 0.8rem; display: block;">{full_name}</strong>
                <span style="font-size: 0.68rem; opacity: 0.75; display: block;">@{username}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with nav_cols[5]:
    st.button("Logout", key="logout_btn", use_container_width=True, on_click=_logout)

st.markdown('<div style="height: 12px;"></div>', unsafe_allow_html=True)


# ── Sidebar File & URL Upload Cards ─────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-mark">🎓</div>
            <div>
                <div style="font-weight: 800; font-size: 1.05rem;">DeptOps AI</div>
                <div style="font-size: 0.75rem; opacity: 0.8;">NAAC Accreditation Suite</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. Dataset Upload
    with st.container(border=True):
        st.markdown("**📊 Upload Dataset**")
        st.caption("Excel / CSV → Analytics Agent")
        up_csv = st.file_uploader("", type=["csv", "xlsx", "xls"], key="up_csv", label_visibility="collapsed")
        if up_csv and st.session_state.get("_last_uploaded_csv") != up_csv.name:
            try:
                upload_analytics(username, up_csv.name, up_csv.getbuffer().tobytes())
                st.success(f"✅ Saved `{up_csv.name}`")
                get_datasets.clear()
                st.session_state["_last_uploaded_csv"] = up_csv.name
                st.session_state.nav_page = "analytics"
                st.rerun()
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    st.markdown('<div style="height: 8px;"></div>', unsafe_allow_html=True)

    # 2. Document Upload
    with st.container(border=True):
        st.markdown("**📚 Upload Document**")
        st.caption("PDF / DOCX / TXT / MD → Knowledge Base")
        up_doc = st.file_uploader("", type=["pdf", "docx", "txt", "md"], key="up_doc", label_visibility="collapsed")
        if up_doc and st.session_state.get("_last_uploaded_doc") != up_doc.name:
            try:
                upload_knowledge(username, up_doc.name, up_doc.getbuffer().tobytes())
                st.success(f"✅ Saved `{up_doc.name}`")
                get_doc_list.clear()
                st.session_state["_last_uploaded_doc"] = up_doc.name
                st.session_state.nav_page = "knowledge"
                st.rerun()
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

        docs = get_doc_list(username)
        chunks = get_chunk_count(username)
        if docs:
            st.caption(f"📚 Documents ({len(docs)}): {', '.join(docs)}")
        st.caption(f"🔢 Indexed Chunks: {chunks}" if chunks else "⚠️ Click Re-index to enable RAG")

        if st.button("🔄 Re-index Knowledge Base", use_container_width=True, type="secondary"):
            with st.spinner("Indexing documents..."):
                try:
                    res = api_reindex(username)
                    get_chunk_count.clear()
                    if res.get("success"):
                        st.success(res.get("message", "Re-index complete"))
                    else:
                        st.error(res.get("message", "Re-index failed"))
                except Exception as exc:
                    st.error(f"Re-index failed: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 1: CENTRAL COORDINATOR HUB
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.nav_page == "coordinator":
    st.markdown("""
    <div class="hero">
        <span style="font-size:0.75rem; font-weight:700; background:rgba(255,255,255,0.25); padding:4px 12px; border-radius:12px;">Central Intelligence Engine</span>
        <h1>🎓 DeptOps AI Coordinator</h1>
        <p>AI Assistant for NAAC Department Inspection Preparation.<br>
        Upload files in the sidebar or paste website URLs — Coordinator automatically invokes the right specialist agent.</p>
    </div>
    """, unsafe_allow_html=True)

    # URL Quick Input Card
    with st.container(border=True):
        st.markdown("### 🌐 Quick Website Audit Input")
        col_u1, col_u2 = st.columns([3, 1])
        with col_u1:
            quick_url = st.text_input("Enter Department Website URL", placeholder="https://cs.university.edu", key="quick_url", label_visibility="collapsed")
        with col_u2:
            btn_quick_web = st.button("Analyze Website 🔍", type="primary", use_container_width=True, key="go_quick_web")

    if btn_quick_web and quick_url.strip():
        with st.spinner(f"Crawling and auditing {quick_url}..."):
            progress_bar = st.progress(0, text="Initializing crawl...")
            for p in range(20, 100, 20):
                progress_bar.progress(p, text=f"Auditing web pages... ({p}%)")
            try:
                web_res = api_website_audit(quick_url.strip(), username=username)
                progress_bar.progress(100, text="Audit Complete!")
                st.session_state.web_page_result = web_res
                st.session_state.nav_page = "website"
                st.rerun()
            except Exception as exc:
                st.error(f"Website audit failed: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 2: DEDICATED ANALYTICS AGENT
# ═════════════════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "analytics":
    st.markdown('<div style="font-size:1.4rem; font-weight:800; margin-bottom:12px;">📊 Academic Data Analytics Agent</div>', unsafe_allow_html=True)

    all_ds = get_datasets(username)
    if not all_ds:
        st.warning("📂 No datasets found. Upload an Excel or CSV file from the sidebar.")
    else:
        sel_ds = st.selectbox("📂 Select Academic Dataset to Analyze", all_ds, key="ana_page_ds")

        with st.spinner("Analyzing dataset dimensions & stats..."):
            try:
                res = api_analytics_full(username, sel_ds)
            except Exception as exc:
                st.error(f"Analytics failed: {exc}")
                res = {}

        # Build a dataframe preview from the lightweight preview payload
        preview = res.get("preview", [])
        df = pd.DataFrame(preview) if preview else None
        stats = res.get("stats", {})
        chart_data = res.get("chart_data", [])

        # Convert chart_data to plotly figures for display
        charts = []
        try:
            for ch in chart_data:
                t = ch.get("type")
                if t == "bar":
                    fig = px.bar(x=ch.get("x", []), y=ch.get("y", []), labels={"x": ch.get("x_label"), "y": ch.get("y_label")}, title=ch.get("title"))
                elif t == "pie":
                    fig = px.pie(names=ch.get("labels", []), values=ch.get("values", []), title=ch.get("title"))
                elif t == "line":
                    fig = px.line(x=ch.get("x", []), y=ch.get("y", []), labels={"x": ch.get("x_label"), "y": ch.get("y_label")}, title=ch.get("title"))
                elif t == "histogram":
                    fig = px.histogram(x=ch.get("values", []), nbins=20, title=ch.get("title"))
                elif t == "scatter":
                    fig = px.scatter(x=ch.get("x", []), y=ch.get("y", []), labels={"x": ch.get("x_label"), "y": ch.get("y_label")}, title=ch.get("title"))
                else:
                    continue
                charts.append({"fig": fig})
        except Exception:
            charts = []

        # Metadata Header
        if df is not None:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Records", len(df))
            m2.metric("Total Columns", len(df.columns))
            m3.metric("Numeric Columns", len(stats.get("col_types", {}).get("numerical", [])))
            m4.metric("Categorical Columns", len(stats.get("col_types", {}).get("categorical", [])))

            with st.expander("📋 Data Table Preview (First 20 Rows)", expanded=False):
                st.dataframe(df.head(20), use_container_width=True)

        st.divider()
        st.markdown("### 📊 Automated Multi-Chart Visualizations")

        if charts:
            for i in range(0, len(charts), 2):
                row_cols = st.columns(2)
                for j, ch in enumerate(charts[i:i+2]):
                    with row_cols[j]:
                        st.plotly_chart(ch["fig"], use_container_width=True)
        else:
            st.info("No numeric columns available for visualization.")

        st.divider()
        st.markdown("### 💬 Ask OpenRouter AI Natural Language Questions")
        nl_q = st.text_input("Ask a question about this dataset (e.g. 'How many students in CSE department?', 'Highest CGPA', 'Compare placements'):", key="ana_nl_q")
        if st.button("Analyze with OpenRouter AI ⚡", type="primary", key="go_ana_nl") and nl_q.strip():
            with st.spinner("OpenRouter free model analyzing dataset..."):
                try:
                    nl_res = api_ask_analytics(username, nl_q.strip(), sel_ds)
                    st.session_state["ana_nl_answer"] = nl_res.get("answer", "")
                    st.session_state["ana_nl_q_last"] = nl_q.strip()
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")

        if "ana_nl_answer" in st.session_state:
            st.markdown(f"#### 🤖 Answer to: *\"{st.session_state.get('ana_nl_q_last', '')}\"*")
            with st.container(border=True):
                st.markdown(st.session_state["ana_nl_answer"])

        st.divider()
        st.markdown("### 📥 Download Reports & Summaries")
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            if df is not None:
                try:
                    excel_bytes = api_excel_report(username, sel_ds)
                    st.download_button("📥 Download Excel Summary", data=excel_bytes, file_name=f"{sel_ds}_summary.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                except Exception as exc:
                    st.error(f"Failed to generate Excel: {exc}")
        with d_col2:
            if df is not None:
                try:
                    pdf_bytes = api_pdf_report(username, sel_ds)
                    st.download_button("📥 Download NAAC PDF Report", data=pdf_bytes, file_name=f"{sel_ds}_NAAC_report.pdf",
                                       mime="application/pdf", use_container_width=True)
                except Exception as exc:
                    st.error(f"Failed to generate PDF: {exc}")

        if len(all_ds) >= 2:
            st.divider()
            st.markdown("### ⚖️ Compare Two Academic Datasets")
            col_ds1, col_ds2 = st.columns(2)
            with col_ds1:
                ds1 = st.selectbox("Select Primary Dataset", all_ds, key="cmp_ds1")
            with col_ds2:
                ds2 = st.selectbox("Select Comparison Dataset", [d for d in all_ds if d != ds1], key="cmp_ds2")
            if st.button("Compare Datasets ⚖️", key="go_ds_cmp", type="primary"):
                with st.spinner(f"Comparing `{ds1}` vs `{ds2}`..."):
                    try:
                        cmp_res = compare_datasets(username, ds1, ds2)
                    except Exception as exc:
                        cmp_res = f"Comparison failed: {exc}"
                with st.container(border=True):
                    st.markdown(cmp_res.get("result") if isinstance(cmp_res, dict) else cmp_res)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 3: DEDICATED KNOWLEDGE AGENT
# ═════════════════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "knowledge":
    st.markdown('<div style="font-size:1.4rem; font-weight:800; margin-bottom:12px;">📚 Knowledge Base RAG Agent</div>', unsafe_allow_html=True)

    docs = get_doc_list(username)
    chunks = get_chunk_count(username)

    if not docs:
        st.warning("No documents uploaded yet. Upload PDF, DOCX, TXT, or MD files from the sidebar.")
    else:
        st.success(f"**Available Documents ({len(docs)}):** {', '.join(docs)} | **Indexed Chunks:** {chunks}")

    st.markdown("### 🔍 RAG Document Question Answering")
    kb_q = st.text_input("Enter question about departmental policies, regulations, or handbooks:", placeholder="e.g. What is the minimum attendance percentage to appear for end semester exams?", key="kb_page_q")

    if st.button("Search & Answer 🔍", type="primary", key="go_kb_q") and kb_q.strip():
        with st.spinner("Searching document vector store with OpenRouter free-model RAG..."):
            try:
                kb_res = api_ask_knowledge(username, kb_q.strip())
            except Exception as exc:
                kb_res = {"answer": f"Knowledge query failed: {exc}", "sources": [], "confidence_score": None}

        with st.container(border=True):
            st.markdown(kb_res.get("answer", ""))

        c_meta1, c_meta2 = st.columns(2)
        with c_meta1:
            if kb_res.get("sources"):
                st.info(f"📎 **Sources Used:** {', '.join(kb_res['sources'])}")
        with c_meta2:
            if kb_res.get("confidence_score"):
                st.success(f"🎯 **RAG Confidence Score:** {kb_res['confidence_score']}%")

    st.divider()
    st.markdown("### 📜 NAAC Criterion Summarizer")
    criterion_names = {
        1: "Curricular Aspects",
        2: "Teaching-Learning and Evaluation",
        3: "Research, Innovations and Extension",
        4: "Infrastructure and Learning Resources",
        5: "Student Support and Progression",
        6: "Governance, Leadership and Management",
        7: "Institutional Values and Best Practices",
    }
    c_num = st.selectbox(
        "Select NAAC Criterion",
        list(criterion_names.keys()),
        format_func=lambda x: f"Criterion {x}: {criterion_names[x]}",
        key="criterion_select",
    )
    if st.button("Generate Summary 📝", key="go_crit_sum", type="primary"):
        with st.spinner(f"Generating summary for Criterion {c_num}..."):
            try:
                res = api_criterion_summary(username, c_num)
                st.session_state["criterion_summary"] = res.get("summary") if isinstance(res, dict) else res
            except Exception as exc:
                st.session_state["criterion_summary"] = f"Failed to generate summary: {exc}"
            st.session_state["criterion_summary_title"] = f"Criterion {c_num}: {criterion_names[c_num]}"

    if st.session_state.get("criterion_summary"):
        with st.container(border=True):
            st.markdown(f"#### {st.session_state.get('criterion_summary_title', 'Criterion Summary')}")
            st.markdown(st.session_state["criterion_summary"])


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 4: DEDICATED WEBSITE TESTING AGENT
# ═════════════════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "website":
    st.markdown('<div style="font-size:1.4rem; font-weight:800; margin-bottom:12px;">🌐 Real-Browser Website Diagnostic Agent</div>', unsafe_allow_html=True)
    st.markdown("Automated Playwright Real-Browser Crawler & Failure Inspector (JS Routes, HTTP Errors, Timeouts, JS Errors, Failed API/Network Requests).")

    with st.container(border=True):
        w_url = st.text_input("Department Website URL", placeholder="https://cs.university.edu", key="web_page_url")
        btn_run_web = st.button("Run Real-Browser Audit 🚀", type="primary", key="go_web_audit")

    if btn_run_web and w_url.strip():
        with st.spinner(f"Launching real headless browser & crawling reachable pages for {w_url}..."):
            prog = st.progress(0, text="Launching Playwright Chromium browser...")
            for val in range(20, 100, 20):
                prog.progress(val, text=f"Discovering & inspecting JS routes and network requests... ({val}%)")
            try:
                web_res = api_website_audit(w_url.strip(), username=username)
                prog.progress(100, text="Audit Complete!")
                st.session_state.web_page_result = web_res
            except Exception as exc:
                st.error(f"Website audit failed: {exc}")

    if "web_page_result" in st.session_state:
        w_res = st.session_state.web_page_result
        summary = w_res.get("summary", {})
        scores = w_res.get("scores", {})

        total_found = w_res.get("total_pages_found", summary.get("total_pages_found", 0))
        total_working = w_res.get("total_working", summary.get("total_working", 0))
        total_broken = w_res.get("total_broken", summary.get("total_broken", 0))

        st.markdown("### 🏆 Real-Browser Crawl Health Dashboard")
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.markdown(f'<div class="score-card"><div class="score-val">{total_found}</div><div class="score-lbl">Total Pages Found</div></div>', unsafe_allow_html=True)
        sc2.markdown(f'<div class="score-card"><div class="score-val" style="color:#2e7d32;">{total_working}</div><div class="score-lbl">Working Pages 🟢</div></div>', unsafe_allow_html=True)
        sc3.markdown(f'<div class="score-card"><div class="score-val" style="color:#c62828;">{total_broken}</div><div class="score-lbl">Broken Pages 🔴</div></div>', unsafe_allow_html=True)
        sc4.markdown(f'<div class="score-card"><div class="score-val">{scores.get("overall",0)}%</div><div class="score-lbl">Health Score</div></div>', unsafe_allow_html=True)

        st.divider()

        # Broken Pages Breakdown Section
        st.markdown(f"### 🔴 Broken Pages & Failure Reasons ({total_broken})")
        broken_list = w_res.get("broken_pages", summary.get("broken_pages", []))
        if not broken_list:
            st.success("🎉 No broken pages detected! All reachable internal pages loaded successfully without errors.")
        else:
            for idx, bp in enumerate(broken_list, 1):
                with st.expander(f"❌ {idx}. {bp['url']} (HTTP {bp.get('status', 'Error')})", expanded=True):
                    st.markdown(f"**URL:** [{bp['url']}]({bp['url']})")
                    st.markdown(f"**Load Time:** `{bp.get('load_time_ms', '—')} ms`")
                    st.markdown("**Failure Reasons Detected:**")
                    for reason in bp.get("failure_reasons", []):
                        st.markdown(f"- ⚠️ `{reason}`")

        st.divider()

        # Working Pages Section
        st.markdown(f"### 🟢 Working Internal Pages ({total_working})")
        working_list = w_res.get("working_pages", summary.get("working_pages", []))
        if working_list:
            work_df_data = [
                {
                    "Page Title": p.get("title", "Untitled"),
                    "URL": p["url"],
                    "Status": f"HTTP {p.get('status', 200)}",
                    "Load Time (ms)": p.get("load_time_ms", 0),
                    "JS Errors": p.get("js_errors_count", 0),
                    "Failed Network Requests": p.get("failed_requests_count", 0),
                }
                for p in working_list
            ]
            st.dataframe(pd.DataFrame(work_df_data), use_container_width=True, height=220)

        st.divider()
        st.markdown("### 🤖 OpenRouter AI Recommendations & Developer Fixes")
        with st.container(border=True):
            st.markdown(w_res.get("ai_report", ""))

        st.divider()
        target_u = w_res.get("summary", {}).get("url") or st.session_state.get("web_page_url", "Website")
        try:
            pdf_bytes = api_website_pdf_report(target_u, username=username)
            st.download_button("📥 Download Comprehensive PDF Web Audit Report", data=pdf_bytes, file_name=f"Real_Browser_Website_Audit_Report.pdf", mime="application/pdf", use_container_width=True)
        except Exception:
            # Fallback: no downloadable report available
            pass

