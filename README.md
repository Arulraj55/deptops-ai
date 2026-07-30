# DeptOps AI

An agentic AI assistant for academic department management and NAAC preparation.

## Features

| Agent | What it does |
| --- | --- |
| Analytics Agent | Analyzes student results, attendance, placement data |
| Knowledge Agent | RAG-based Q&A over institutional documents (PDF, DOCX, TXT, MD) |
| Website Testing Agent | Automated website health checks, broken links, SEO, security, accessibility |
| Coordinator Agent | Auto-routes queries to the right specialist agent |

## Quick Start

### 1. Clone and set up environment

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure API keys

```bash
copy .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

## LLM Provider

DeptOps AI uses OpenRouter only. Add `OPENROUTER_API_KEY` to `.env`.
Model selection lives in `config.py`, not `.env`.

The app discovers the current zero-cost OpenRouter models at runtime and fans
prompts out to a free-model panel. If discovery is unavailable, it falls back to
the `OPENROUTER_FREE_MODELS` list in `config.py`.

### 3. Generate sample data (optional)

```bash
python scripts/generate_sample_data.py
python scripts/create_sample_doc.py
```

### 4. Run the app

```bash
streamlit run app.py
```

## Project Structure

```text
DeptOps AI/
├── app.py
├── auth.py
├── auth_styles.py
├── config.py
├── requirements.txt
├── agents/
│   ├── coordinator_agent.py
│   ├── analytics_agent.py
│   ├── knowledge_agent.py
│   └── website_testing_agent.py
├── data/
│   ├── analytics/
│   ├── documents/
│   └── chroma_db/
├── scripts/
│   ├── generate_sample_data.py
│   └── create_sample_doc.py
├── signin.py
├── signup.py
└── README.md
```

## Tech Stack

- Python 3.11+
- LangGraph
- LangChain
- ChromaDB
- Playwright
- Pandas
- Plotly
- Streamlit
