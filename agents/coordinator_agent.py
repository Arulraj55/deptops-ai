"""
Coordinator Agent
-----------------
Routes HOD queries to the correct specialist agent using keyword matching.
No LangGraph / LLM used for routing — pure keyword scoring.
This makes routing instant, offline, and 100% rate-limit proof.

Routing priority (keyword score):
  highest score → Analytics Agent
  highest score → Knowledge Agent
  highest score → Website Testing Agent
  tie           → Analytics (most common use case)
"""

from __future__ import annotations
import re


# ── Keyword patterns ──────────────────────────────────────────────────────────

_ANA = re.compile(
    r"\b(pass|fail|result|attendance|marks|grade|cgpa|gpa|placement|score|"
    r"performance|subject|exam|student|rank|percentage|dataset|csv|excel|"
    r"analytics|statistics|analysis|faculty|average|topper|highest|lowest|"
    r"dropout|semester|division|distinction|aggregate)\b",
    re.IGNORECASE,
)

_KNOW = re.compile(
    r"\b(regulation|policy|syllabus|rule|guideline|handbook|document|"
    r"eligibility|criteria|procedure|fee|leave|exam.pattern|curriculum|"
    r"credit|course|circular|notice|ordinance|academic|minimum|required|"
    r"allowed|permit|shortage|backlog|arrear|revaluation|supplementary)\b",
    re.IGNORECASE,
)

_WEB = re.compile(
    r"\b(website|portal|url|link|http|https|broken|down|slow|web|site|"
    r"navigate|load|test|check|verify|page|access|online|server)\b",
    re.IGNORECASE,
)


def classify_intent(query: str) -> str:
    """Classify query into analytics / knowledge / website using LLM with fallback to keyword scoring."""
    # Website check: if URL present, always website
    if re.search(r"https?://\S+", query):
        return "website"

    # Try LLM classification for accurate intent routing
    try:
        from config import get_llm
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Classify the query into one of three categories:\n"
                       "- 'analytics' (asking for stats, percentages, numbers, grades, attendance from a dataset)\n"
                       "- 'knowledge' (asking for rules, regulations, syllabus, policies, procedures)\n"
                       "- 'website' (asking to check a link or website)\n"
                       "Return ONLY the category name in lowercase without any other text."),
            ("human", "{query}")
        ])
        llm = get_llm(temperature=0.0)
        resp = (prompt | llm).invoke({"query": query})
        if resp and resp.content:
            intent = resp.content.strip().lower()
            if intent in ["analytics", "knowledge", "website"]:
                return intent
    except Exception:
        pass

    # Fallback to keyword scoring
    a = len(_ANA.findall(query))
    k = len(_KNOW.findall(query))
    w = len(_WEB.findall(query))

    if w > 0 and w >= a and w >= k:
        return "website"
    if k > a:
        return "knowledge"
    if a > 0:
        return "analytics"
    if k > 0:
        return "knowledge"
    # Default
    return "analytics"


# ── Main Entry Point ──────────────────────────────────────────────────────────

def process_query(
    username: str,
    query: str,
    file_path: str | None = None,
    url: str | None = None,
) -> dict:
    """
    Route the query to the right agent and return its result.
    All exceptions are caught — never crashes the UI.
    """
    intent = classify_intent(query)

    # Override: if URL provided explicitly, force website
    if url and url.strip():
        intent = "website"

    result: dict = {}
    error: str | None = None

    try:
        if intent == "analytics":
            from agents.analytics_agent import run_analytics_agent
            result = run_analytics_agent(username=username, query=query, file_path=file_path)

        elif intent == "knowledge":
            from agents.knowledge_agent import run_knowledge_agent
            result = run_knowledge_agent(username=username, query=query)

        elif intent == "website":
            from agents.website_testing_agent import run_website_testing_agent
            target_url = url or _extract_url(query) or ""
            result = run_website_testing_agent(url=target_url)

        error = result.get("error")

    except Exception as exc:
        error = str(exc)
        result = {"answer": f"Agent error: {exc}", "stats": {}, "sources": [], "summary": {}, "ai_report": ""}

    return {
        "query": query,
        "intent": intent,
        "file_path": file_path,
        "url": url,
        "result": result,
        "error": error,
    }


def _extract_url(query: str) -> str | None:
    """Extract a URL from a query string if present."""
    m = re.search(r"https?://\S+", query)
    return m.group(0) if m else None
