"""
Coordinator Agent for DeptOps AI
--------------------------------
Central Intelligence Engine.
Automatically detects user intent from file uploads, website URLs, or natural language prompts,
and routes to the appropriate specialist agent (Analytics, Knowledge, or Website Testing).
"""

import re
import logging
from config import get_llm, invoke_llm_with_retry

logger = logging.getLogger("CoordinatorAgent")

# File extension mappings
ANALYTICS_EXTS = {".csv", ".xlsx", ".xls"}
KNOWLEDGE_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md"}


def detect_file_type_intent(filename: str) -> str | None:
    """Detect agent intent based on uploaded file extension."""
    if not filename:
        return None
    ext = filename.lower()[filename.rfind("."):].strip() if "." in filename else ""
    if ext in ANALYTICS_EXTS:
        return "analytics"
    if ext in KNOWLEDGE_EXTS:
        return "knowledge"
    return None


def extract_url(text: str) -> str | None:
    """Extract http/https URL from prompt if present."""
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0) if match else None


def classify_intent_with_gemini(query: str) -> str:
    """Classify user query intent into 'analytics', 'knowledge', or 'website' using Gemini 2.5 Flash."""
    if extract_url(query):
        return "website"

    try:
        llm = get_llm(temperature=0.0)
        prompt = (
            f"You are the Coordinator Intelligence Router for DeptOps AI.\n"
            f"Classify the following user input into EXACTLY ONE category:\n"
            f"- 'analytics' (query asks about grades, marks, attendance, placements, CGPA, dataset statistics, charts, faculty, research counts)\n"
            f"- 'knowledge' (query asks about policies, regulations, syllabus, handbooks, NAAC criteria, document summaries, guidelines)\n"
            f"- 'website' (query asks to check, audit, test, or inspect a website or URL)\n\n"
            f"User input: \"{query}\"\n\n"
            f"Return ONLY the single word in lowercase without quotes or extra text."
        )
        res = invoke_llm_with_retry(llm, prompt)
        intent = (res.content if hasattr(res, "content") else str(res)).strip().lower()
        if intent in ("analytics", "knowledge", "website"):
            return intent
    except Exception as exc:
        logger.warning(f"Gemini intent classification fallback: {exc}")

    # Keyword fallback
    q_lower = query.lower()
    if any(k in q_lower for k in ("http", "www.", "website", "site", "url", "portal")):
        return "website"
    if any(k in q_lower for k in ("criterion", "policy", "regulation", "syllabus", "summarize", "document", "rule", "handbook")):
        return "knowledge"

    return "analytics"


def process_query(
    username: str,
    query: str,
    file_path: str | None = None,
    url: str | None = None,
) -> dict:
    """
    Central Coordinator routing handler.
    Auto-detects intent from file, URL, or natural language query,
    executes the appropriate agent, and updates unified chat history.
    """
    intent = None

    # 1. URL input -> Website Testing
    target_url = url or extract_url(query)
    if target_url:
        intent = "website"

    # 2. File upload -> Analytics or Knowledge
    elif file_path:
        intent = detect_file_type_intent(file_path)

    # 3. Prompt classification
    if not intent:
        intent = classify_intent_with_gemini(query)

    logger.info(f"Coordinator routed query '{query[:40]}' -> intent '{intent}' for user '{username}'")

    result = {}
    error = None

    try:
        if intent == "analytics":
            from agents.analytics_agent import run_analytics_agent
            result = run_analytics_agent(username=username, query=query, file_path=file_path)

        elif intent == "knowledge":
            from agents.knowledge_agent import run_knowledge_agent
            result = run_knowledge_agent(username=username, query=query)

        elif intent == "website":
            from agents.website_testing_agent import run_website_testing_agent
            url_to_test = target_url or query.strip()
            result = run_website_testing_agent(url=url_to_test, username=username)

        # Store in PostgreSQL chat history
        try:
            from db_storage import add_chat_message
            add_chat_message(username=username, role="user", message=query, agent_used=intent)
            answer_summary = result.get("answer") or result.get("ai_report") or "Query processed successfully."
            add_chat_message(username=username, role="assistant", message=answer_summary[:500], agent_used=intent)
        except Exception:
            pass

    except Exception as exc:
        logger.error(f"Error executing agent '{intent}': {exc}")
        error = str(exc)
        result = {"answer": f"Agent error: {exc}", "error": error}

    return {
        "query": query,
        "intent": intent,
        "file_path": file_path,
        "url": target_url,
        "result": result,
        "error": error,
    }
