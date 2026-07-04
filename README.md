# 🎓 DeptOps AI

An **Agentic AI Assistant** for Academic Department Management.

## Features

| Agent | What it does |
|-------|-------------|
| 📊 **Analytics Agent** | Analyzes student results, attendance, placement data |
| 📚 **Knowledge Agent** | RAG-based Q&A over institutional documents (PDF, DOCX, TXT) |
| 🌐 **Website Testing Agent** | Automated website health checks (broken links, slow pages) |
| 🧠 **Coordinator Agent** | Auto-routes queries using LangGraph |

## Quick Start

### 1. Clone & setup environment

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure API keys

```bash
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY or OPENROUTER_API_KEY
```

### 3. Generate sample data (optional)

```bash
python scripts/generate_sample_data.py
python scripts/create_sample_doc.py
```

### 4. Run the app

```bash
streamlit run app.py
```

## LLM Providers

Set `LLM_PROVIDER` in `.env`:

- `gemini` — Google Gemini API (fast, free tier available)
- `openrouter` — Access GPT-4o, Claude, Llama, etc. via OpenRouter

## Project Structure

```
DeptOps AI/
├── app.py                     # Streamlit dashboard
├── config.py                  # Central config + LLM factory
├── requirements.txt
├── agents/
│   ├── coordinator_agent.py   # LangGraph routing
│   ├── analytics_agent.py     # Pandas + LLM analysis
│   ├── knowledge_agent.py     # RAG with ChromaDB
│   └── website_testing_agent.py  # Playwright tests
├── data/
│   ├── analytics/             # Upload CSV/Excel datasets here
│   ├── documents/             # Upload PDF/DOCX/TXT documents here
│   └── chroma_db/             # Auto-created vector store
└── scripts/
    ├── generate_sample_data.py
    └── create_sample_doc.py
```

## Tech Stack

- **Python 3.11+**
- **LangGraph** — Agent orchestration
- **LangChain** — LLM abstraction layer
- **ChromaDB** — Vector store for RAG
- **Playwright** — Website testing
- **Pandas** — Data analysis
- **Plotly** — Charts
- **Streamlit** — Web UI

## 📂 Folder Overview

```
DeptOps AI/
├── app.py                # Streamlit dashboard
├── auth.py               # Authentication logic (SQLite)
├── auth_styles.py        # CSS for auth pages
├── config.py             # LLM configuration
├── requirements.txt
├── agents/               # LangGraph agents (analytics, knowledge, website testing, coordinator)
├── data/                 # Uploaded datasets & documents
│   ├── analytics/
│   ├── documents/
│   └── chroma_db/
├── scripts/              # Helper scripts for sample data
├── signin.py             # Sign‑in UI
├── signup.py             # Sign‑up UI
└── README.md             # Project overview
```
