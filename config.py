"""
Central configuration for DeptOps AI.
Reads settings from environment variables / .env file.
Configured for Gemini 2.5 Flash.
"""

import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("DeptOpsAI")

# ── Gemini 2.5 Flash ─────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Fallback OpenRouter settings if user still provides them
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ── Storage (local temp dirs used for Chroma vector store and processing) ────
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
ANALYTICS_DATA_DIR: str = os.getenv("ANALYTICS_DATA_DIR", "./data/analytics")
DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", "./data/documents")


def get_llm(temperature: float = 0.2, streaming: bool = False, max_retries: int = 3, timeout: int = 30):
    """
    Returns a LangChain LLM instance for Gemini 2.5 Flash with retries, timeout, and error handling.
    Falls back gracefully if configured.
    """
    if GEMINI_API_KEY:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            
            return ChatGoogleGenerativeAI(
                model=GEMINI_MODEL,
                google_api_key=GEMINI_API_KEY,
                temperature=temperature,
                max_retries=max_retries,
                timeout=timeout,
                streaming=streaming,
            )
        except Exception as exc:
            logger.warning(f"Could not initialize ChatGoogleGenerativeAI with model {GEMINI_MODEL}: {exc}")
            # Try fallback model identifier 'gemini-2.0-flash' or 'gemini-1.5-flash'
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=GEMINI_API_KEY,
                    temperature=temperature,
                    max_retries=max_retries,
                    timeout=timeout,
                    streaming=streaming,
                )
            except Exception as e2:
                logger.error(f"Fallback to gemini-2.0-flash failed: {e2}")

    # OpenRouter fallback if OPENROUTER_API_KEY is present
    if OPENROUTER_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=OPENROUTER_MODEL,
                openai_api_key=OPENROUTER_API_KEY,
                openai_api_base=OPENROUTER_BASE_URL,
                temperature=temperature,
                timeout=timeout,
                streaming=streaming,
                default_headers={
                    "HTTP-Referer": "https://deptops-ai.onrender.com",
                    "X-Title": "DeptOps AI",
                },
            )
        except Exception as o_err:
            logger.warning(f"Could not initialize ChatOpenAI for OpenRouter: {o_err}")

    raise ValueError(
        "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set in environment variables / .env file. "
        "Please add your GEMINI_API_KEY to .env."
    )


def invoke_llm_with_retry(llm, prompt_input, retries: int = 3, delay: float = 2.0):
    """
    Helper function to invoke LLM with retry mechanism for handling rate limits (429/503).
    """
    for attempt in range(1, retries + 1):
        try:
            return llm.invoke(prompt_input)
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ("429", "rate", "resource_exhausted", "quota", "503", "overloaded")):
                logger.warning(f"LLM rate limit/overload hit (attempt {attempt}/{retries}). Retrying in {delay}s...")
                if attempt == retries:
                    raise e
                time.sleep(delay)
                delay *= 2
            else:
                raise e
