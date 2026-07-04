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
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

# ── Storage ──────────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
ANALYTICS_DATA_DIR: str = os.getenv("ANALYTICS_DATA_DIR", "./data/analytics")
DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", "./data/documents")


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
            "HTTP-Referer": "https://deptops-ai.local",
            "X-Title": "DeptOps AI",
        },
    )
