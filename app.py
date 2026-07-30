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
        return [row["filename"] for row in db_storage.list_analytics_files(user)]
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def get_doc_list(user: str) -> list[str]:
    try:
        return db_storage.list_knowledge_files(user)
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def get_chunk_count(user: str) -> int:
    try:
        raw = db_storage.load_tfidf_index(user)
        if not raw:
            return 0
        idx = json.loads(raw)
        return len(idx.get("chunks", []))
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
            db_storage.save_analytics_file(username, up_csv.name, up_csv.getbuffer().tobytes())
            st.success(f"✅ Saved `{up_csv.name}`")
            get_datasets.clear()
            st.session_state["_last_uploaded_csv"] = up_csv.name
            st.session_state.nav_page = "analytics"
            st.rerun()

    st.markdown('<div style="height: 8px;"></div>', unsafe_allow_html=True)

    # 2. Document Upload
    with st.container(border=True):
        st.markdown("**📚 Upload Document**")
        st.caption("PDF / DOCX / TXT / MD → Knowledge Base")
        up_doc = st.file_uploader("", type=["pdf", "docx", "txt", "md"], key="up_doc", label_visibility="collapsed")
        if up_doc and st.session_state.get("_last_uploaded_doc") != up_doc.name:
            db_storage.save_knowledge_file(username, up_doc.name, up_doc.getbuffer().tobytes())
            st.success(f"✅ Saved `{up_doc.name}`")
            get_doc_list.clear()
            st.session_state["_last_uploaded_doc"] = up_doc.name
            st.session_state.nav_page = "knowledge"
            st.rerun()

        docs = get_doc_list(username)
        chunks = get_chunk_count(username)
        if docs:
            st.caption(f"📚 Documents ({len(docs)}): {', '.join(docs)}")
        st.caption(f"🔢 Indexed Chunks: {chunks}" if chunks else "⚠️ Click Re-index to enable RAG")

        if st.button("🔄 Re-index Knowledge Base", use_container_width=True, type="secondary"):
            with st.spinner("Indexing documents..."):
                from agents.knowledge_agent import ingest_documents
                res = ingest_documents(username)
                get_chunk_count.clear()
            if res["success"]:
                st.success(res["message"])
            else:
                st.error(res["message"])


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
                time_step = 0.2
                progress_bar.progress(p, text=f"Auditing web pages... ({p}%)")
            from agents.website_testing_agent import run_website_testing_agent
            web_res = run_website_testing_agent(quick_url.strip(), username=username)
            progress_bar.progress(100, text="Audit Complete!")

        st.session_state.web_page_result = web_res
        st.session_state.nav_page = "website"
        st.rerun()


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
            from agents.analytics_agent import ask_analytics_agent, generate_excel_summary, generate_pdf_report
            res = ask_analytics_agent(username, query="Full dataset statistical summary and NAAC insights", filename=sel_ds)

        df = res.get("dataframe")
        stats = res.get("stats", {})
        charts = res.get("charts", [])

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
            with st.spinner("OpenRouter free-model panel analyzing dataset..."):
                nl_res = ask_analytics_agent(username, query=nl_q.strip(), filename=sel_ds)
                st.session_state["ana_nl_answer"] = nl_res.get("answer", "")
                st.session_state["ana_nl_q_last"] = nl_q.strip()

        if "ana_nl_answer" in st.session_state:
            st.markdown(f"#### 🤖 Answer to: *\"{st.session_state.get('ana_nl_q_last', '')}\"*")
            with st.container(border=True):
                st.markdown(st.session_state["ana_nl_answer"])

        st.divider()
        st.markdown("### 📥 Download Reports & Summaries")
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            if df is not None:
                excel_bytes = generate_excel_summary(df, stats)
                st.download_button("📥 Download Excel Summary", data=excel_bytes, file_name=f"{sel_ds}_summary.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with d_col2:
            if df is not None:
                pdf_bytes = generate_pdf_report(username, sel_ds, res.get("answer", ""), stats)
                st.download_button("📥 Download NAAC PDF Report", data=pdf_bytes, file_name=f"{sel_ds}_NAAC_report.pdf",
                                   mime="application/pdf", use_container_width=True)

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
                    from agents.analytics_agent import compare_datasets
                    cmp_res = compare_datasets(username, ds1, ds2)
                with st.container(border=True):
                    st.markdown(cmp_res)


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
            from agents.knowledge_agent import ask_knowledge_agent
            kb_res = ask_knowledge_agent(username, kb_q.strip())

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
    c_num = st.selectbox("Select NAAC Criterion to Summarize", list(range(1, 8)), format_func=lambda x: f"Criterion {x}")
    if st.button("Generate Criterion Summary 📝", key="go_crit_sum", type="primary"):
        with st.spinner(f"Generating summary for Criterion {c_num}..."):
            from agents.knowledge_agent import generate_criterion_summary
            crit_text = generate_criterion_summary(username, c_num)
        with st.container(border=True):
            st.markdown(crit_text)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 4: DEDICATED WEBSITE TESTING AGENT
# ═════════════════════════════════════════════════════════════════════════════
elif st.session_state.nav_page == "website":
    st.markdown('<div style="font-size:1.4rem; font-weight:800; margin-bottom:12px;">🌐 Website Testing & NAAC Audit Agent</div>', unsafe_allow_html=True)
    st.markdown("Automated 8-Tier Website Inspection (Basic, Links, SEO, Accessibility, Performance, Security, Content, Structure).")

    with st.container(border=True):
        w_url = st.text_input("Department Website URL", placeholder="https://cs.university.edu", key="web_page_url")
        btn_run_web = st.button("Run Full Automated Audit 🚀", type="primary", key="go_web_audit")

    if btn_run_web and w_url.strip():
        with st.spinner(f"Crawling & auditing {w_url}..."):
            prog = st.progress(0, text="Initializing crawler...")
            for val in range(25, 100, 25):
                prog.progress(val, text=f"Inspecting pages and security headers... ({val}%)")
            from agents.website_testing_agent import run_website_testing_agent
            web_res = run_website_testing_agent(w_url.strip(), username=username)
            prog.progress(100, text="Audit Complete!")
            st.session_state.web_page_result = web_res

    if "web_page_result" in st.session_state:
        w_res = st.session_state.web_page_result
        summary = w_res.get("summary", {})
        scores = w_res.get("scores", {})

        st.markdown("### 🏆 Health Scores Dashboard")
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        sc1.markdown(f'<div class="score-card"><div class="score-val">{scores.get("overall",0)}</div><div class="score-lbl">Overall Health</div></div>', unsafe_allow_html=True)
        sc2.markdown(f'<div class="score-card"><div class="score-val">{scores.get("performance",0)}</div><div class="score-lbl">Performance</div></div>', unsafe_allow_html=True)
        sc3.markdown(f'<div class="score-card"><div class="score-val">{scores.get("seo",0)}</div><div class="score-lbl">SEO Score</div></div>', unsafe_allow_html=True)
        sc4.markdown(f'<div class="score-card"><div class="score-val">{scores.get("accessibility",0)}</div><div class="score-lbl">Accessibility</div></div>', unsafe_allow_html=True)
        sc5.markdown(f'<div class="score-card"><div class="score-val">{scores.get("security",0)}</div><div class="score-lbl">Security</div></div>', unsafe_allow_html=True)

        st.divider()
        st.markdown("### 🤖 OpenRouter AI NAAC Recommendations & Fixes")
        with st.container(border=True):
            st.markdown(w_res.get("ai_report", ""))

        if w_res.get("all_pages"):
            st.divider()
            st.markdown("### 🗂 Page-by-Page Audit Table")
            rows = [
                {
                    "URL": p["url"],
                    "Status": p.get("status", "—"),
                    "Load Time (ms)": p.get("load_time_ms", "—"),
                    "Title": (p.get("title") or "Missing Title")[:40],
                    "H1 Heading": "✅ Present" if p.get("has_h1") else "❌ Missing",
                    "Missing ALT Tags": p.get("missing_alt_count", 0),
                    "SSL/HTTPS": "🔒 Yes" if p.get("is_https") else "⚠️ No",
                    "Result": "🔴 Broken" if p.get("broken") else "🟢 OK"
                }
                for p in w_res["all_pages"]
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, height=280)

        st.divider()
        from agents.website_testing_agent import generate_website_pdf_report
        pdf_bytes = generate_website_pdf_report(w_url.strip(), summary, w_res.get("ai_report", ""))
        st.download_button("📥 Download PDF Web Audit Report", data=pdf_bytes, file_name=f"Website_Audit_Report.pdf", mime="application/pdf", use_container_width=True)
