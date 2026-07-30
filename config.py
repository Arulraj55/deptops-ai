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
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ── Storage (local temp dirs used for Chroma vector store and processing) ────
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
ANALYTICS_DATA_DIR: str = os.getenv("ANALYTICS_DATA_DIR", "./data/analytics")
DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", "./data/documents")


def get_llm(temperature: float = 0.2, streaming: bool = False, max_retries: int = 3, timeout: int = 60):
    """
    Returns a LangChain LLM instance.
    Checks:
    1. Official Google API (GEMINI_API_KEY) with gemini-2.5-flash (then fallbacks).
    2. OpenRouter (OPENROUTER_API_KEY) trying:
       - google/gemini-2.5-flash
       - google/gemini-2.0-flash-exp:free (free)
       - meta-llama/llama-3.3-70b-instruct
       - meta-llama/llama-3-8b-instruct:free (free fallback)
    """
    if GEMINI_API_KEY:
        # Try primary model
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

        # Try fallback Gemini models
        for fallback_model in ("gemini-2.0-flash", "gemini-1.5-flash"):
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=fallback_model,
                    google_api_key=GEMINI_API_KEY,
                    temperature=temperature,
                    max_retries=max_retries,
                    timeout=timeout,
                    streaming=streaming,
                )
            except Exception as e2:
                logger.warning(f"Fallback to {fallback_model} failed: {e2}")

    # OpenRouter fallback if OPENROUTER_API_KEY is present
    if OPENROUTER_API_KEY:
        # We will try a list of OpenRouter models in order of preference
        models_to_try = [
            "google/gemini-2.5-flash",
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct",
            "meta-llama/llama-3-8b-instruct:free",
        ]
        
        # Put the configured model at the front if it's not already there
        if OPENROUTER_MODEL and OPENROUTER_MODEL not in models_to_try:
            models_to_try.insert(0, OPENROUTER_MODEL)

        for model_name in models_to_try:
            try:
                from langchain_openai import ChatOpenAI
                logger.info(f"Attempting to initialize OpenRouter model: {model_name}")
                return ChatOpenAI(
                    model=model_name,
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
                logger.warning(f"Could not initialize ChatOpenAI for OpenRouter model {model_name}: {o_err}")

    raise ValueError(
        "Neither GEMINI_API_KEY (Google API) nor OPENROUTER_API_KEY (OpenRouter) is valid or configured. "
        "Please provide at least one valid key in your .env file."
    )


def invoke_llm_with_retry(llm, prompt_input, retries: int = 3, delay: float = 2.0):
    """
    Helper function to invoke LLM with retry mechanism for handling rate limits, 404, and transient errors.
    """
    for attempt in range(1, retries + 1):
        try:
            return llm.invoke(prompt_input)
        except Exception as e:
            err_str = str(e).lower()
            retryable = any(k in err_str for k in (
                "429", "rate", "resource_exhausted", "quota", "503", "overloaded",
                "500", "internal", "timeout", "timed out", "deadline",
            ))
            if retryable:
                logger.warning(f"LLM retryable error (attempt {attempt}/{retries}): {type(e).__name__}. Retrying in {delay}s...")
                if attempt == retries:
                    raise e
                time.sleep(delay)
                delay *= 2
            else:
                raise e
