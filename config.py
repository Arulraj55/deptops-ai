"""
Central configuration for DeptOps AI.

The app uses OpenRouter only. Model choices are owned here, not in .env.
The .env file should provide credentials and infrastructure settings only.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("DeptOpsAI")


class OpenRouterFreeDailyLimitError(RuntimeError):
    """Raised when OpenRouter reports the account-level free-model daily limit is exhausted."""


# OpenRouter credentials and endpoint. Models are intentionally not read from .env.
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Config-owned fallback list used when OpenRouter's model endpoint is unavailable.
# Keep only zero-cost routers/models here.
OPENROUTER_FREE_MODELS: tuple[str, ...] = (
    "openrouter/free",
    "google/gemma-3-27b-it:free",
    "google/gemma-3-12b-it:free",
    "google/gemma-3-4b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen3-235b-a22b:free",
    "qwen/qwen3-30b-a3b:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-r1:free",
    "nousresearch/deephermes-3-llama-3-8b-preview:free",
)

# Try free models in this config/discovery order. The first successful answer is used.
OPENROUTER_MAX_FREE_MODELS: int = 25
OPENROUTER_MODEL_DISCOVERY_TIMEOUT: int = 10

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# Storage (local temp dirs used for Chroma vector store and processing)
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
ANALYTICS_DATA_DIR: str = os.getenv("ANALYTICS_DATA_DIR", "./data/analytics")
DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", "./data/documents")


def _openrouter_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://deptops-ai.onrender.com",
        "X-Title": "DeptOps AI",
    }
    if OPENROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"
    return headers


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def discover_openrouter_free_models(limit: int = OPENROUTER_MAX_FREE_MODELS) -> list[str]:
    """
    Ask OpenRouter for the current zero-cost chat models, falling back to this
    config file's free list if discovery fails.
    """
    fallback = list(OPENROUTER_FREE_MODELS[:limit])
    try:
        models_url = f"{OPENROUTER_BASE_URL.rstrip('/')}/models"
        response = requests.get(
            models_url,
            headers=_openrouter_headers(),
            timeout=OPENROUTER_MODEL_DISCOVERY_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
    except Exception as exc:
        logger.warning("OpenRouter free model discovery failed; using configured fallback list: %s", exc)
        return fallback

    free_models: list[str] = []
    for model in data:
        model_id = model.get("id", "")
        pricing = model.get("pricing") or {}
        prompt_price = str(pricing.get("prompt", "")).strip()
        completion_price = str(pricing.get("completion", "")).strip()
        output_modalities = (model.get("architecture") or {}).get("output_modalities") or []

        is_free = (
            model_id == "openrouter/free"
            or model_id.endswith(":free")
            or (prompt_price in {"0", "0.0", "0.000000"} and completion_price in {"0", "0.0", "0.000000"})
        )
        can_chat = not output_modalities or "text" in output_modalities

        if is_free and can_chat:
            free_models.append(model_id)

    ordered = _dedupe(("openrouter/free", *free_models, *OPENROUTER_FREE_MODELS))
    selected = ordered[:limit]
    logger.info("Using %s OpenRouter free models: %s", len(selected), ", ".join(selected))
    return selected or fallback


def _build_openrouter_llm(model_name: str, temperature: float, streaming: bool, timeout: int):
    from langchain_openai import ChatOpenAI

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


def get_openrouter_free_llms(
    temperature: float = 0.2,
    streaming: bool = False,
    timeout: int = 60,
    limit: int = OPENROUTER_MAX_FREE_MODELS,
):
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured. DeptOps AI uses OpenRouter only.")

    return [
        _build_openrouter_llm(model_name, temperature=temperature, streaming=streaming, timeout=timeout)
        for model_name in discover_openrouter_free_models(limit=limit)
    ]


def get_llm(temperature: float = 0.2, streaming: bool = False, max_retries: int = 3, timeout: int = 60):
    """
    Backwards-compatible single-model helper for older call sites.
    Prefer invoke_openrouter_free_models for AI answers so free models are tried in order.
    """
    del max_retries
    return get_openrouter_free_llms(temperature=temperature, streaming=streaming, timeout=timeout, limit=1)[0]


def _prompt_to_messages(prompt_input) -> list[dict[str, str]]:
    if isinstance(prompt_input, str):
        return [{"role": "user", "content": prompt_input}]
    if isinstance(prompt_input, list):
        return prompt_input
    if hasattr(prompt_input, "to_messages"):
        messages = []
        for msg in prompt_input.to_messages():
            role = getattr(msg, "type", "user")
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            messages.append({"role": role, "content": str(getattr(msg, "content", msg))})
        return messages
    return [{"role": "user", "content": str(prompt_input)}]


def _invoke_openrouter_chat_completion(
    model_name: str,
    prompt_input,
    temperature: float,
    timeout: int,
) -> str:
    response = requests.post(
        f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
        headers=_openrouter_headers(),
        json={
            "model": model_name,
            "messages": _prompt_to_messages(prompt_input),
            "temperature": temperature,
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        if response.status_code == 429 and "free-models-per-day" in response.text:
            raise OpenRouterFreeDailyLimitError(
                "OpenRouter free daily model limit is exhausted for this API key. "
                "Wait for the daily reset or add credits in OpenRouter to unlock more free-model requests."
            )
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")

    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices returned: {str(payload)[:500]}")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "").strip()


def invoke_llm_with_retry(llm, prompt_input, retries: int = 3, delay: float = 2.0):
    """
    Invoke one LLM with retry handling for rate limits and transient OpenRouter/provider errors.
    """
    for attempt in range(1, retries + 1):
        try:
            return llm.invoke(prompt_input)
        except Exception as exc:
            err_str = str(exc).lower()
            retryable = any(k in err_str for k in (
                "429", "rate", "resource_exhausted", "quota", "503", "overloaded",
                "500", "internal", "timeout", "timed out", "deadline",
            ))
            if retryable and attempt < retries:
                logger.warning(
                    "OpenRouter retryable error (attempt %s/%s): %s. Retrying in %.1fs...",
                    attempt,
                    retries,
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
                continue
            raise


def invoke_openrouter_free_models(
    prompt_input,
    temperature: float = 0.2,
    retries: int = 2,
    timeout: int = 60,
    limit: int = OPENROUTER_MAX_FREE_MODELS,
) -> str:
    """
    Try OpenRouter free models in order and return the first successful answer.
    This keeps all model choices in config/discovery without calling every model.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured. DeptOps AI uses OpenRouter only.")

    model_names = discover_openrouter_free_models(limit=limit)
    failures: list[tuple[str, str]] = []

    for model_name in model_names:
        delay = 1.0
        for attempt in range(1, retries + 1):
            try:
                logger.info("Trying OpenRouter free model: %s", model_name)
                content = _invoke_openrouter_chat_completion(
                    model_name=model_name,
                    prompt_input=prompt_input,
                    temperature=temperature,
                    timeout=timeout,
                )
                if content:
                    logger.info("OpenRouter free model answered: %s", model_name)
                    return content
                failures.append((model_name, "empty response"))
                break
            except Exception as exc:
                if isinstance(exc, OpenRouterFreeDailyLimitError):
                    raise
                err_str = str(exc).lower()
                retryable = any(k in err_str for k in (
                    "429", "rate", "quota", "503", "overloaded", "500",
                    "internal", "timeout", "timed out", "deadline",
                ))
                if retryable and attempt < retries:
                    logger.warning(
                        "OpenRouter model retryable error (%s, attempt %s/%s): %s",
                        model_name,
                        attempt,
                        retries,
                        exc,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                failures.append((model_name, str(exc)[:180]))
                logger.warning("OpenRouter free model failed (%s): %s", model_name, exc)
                break

    failure_text = "; ".join(f"{model}: {err}" for model, err in failures[:5])
    raise RuntimeError(f"All OpenRouter free model attempts failed. {failure_text}")
