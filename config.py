"""
Central configuration for DeptOps AI.
Reads settings from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter ───────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ── Storage (local temp dirs used only for in-memory processing) ─────────────
# On Render these are ephemeral /tmp paths — all persistent data goes to Neon DB
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "/tmp/deptops/chroma_db")
ANALYTICS_DATA_DIR: str = os.getenv("ANALYTICS_DATA_DIR", "/tmp/deptops/analytics")
DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", "/tmp/deptops/documents")


def get_llm(temperature: float = 0.2):
    """
    Returns a LangChain ChatOpenAI instance pointed at OpenRouter.
    """
    from langchain_openai import ChatOpenAI

    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. "
            "Copy .env.example to .env and add your key."
        )

    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base=OPENROUTER_BASE_URL,
        temperature=temperature,
        default_headers={
            "HTTP-Referer": "https://deptops-ai.onrender.com",
            "X-Title": "DeptOps AI",
        },
    )
