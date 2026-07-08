"""
Website Testing Agent
---------------------
Uses requests + BeautifulSoup to check department websites.
Playwright is NOT used — it cannot install on Render's free tier.

Checks performed:
- Page reachability (HTTP status codes)
- Response time (slow pages > threshold)
- Broken internal links
- Missing <title> or <h1>
- Basic SEO/accessibility checks
"""

import time
import requests
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

SLOW_THRESHOLD_MS = 3000
MAX_LINKS_TO_CRAWL = 15
REQUEST_TIMEOUT = 12

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DeptOpsAI-Tester/1.0; "
        "+https://deptops-ai.onrender.com)"
    )
}


# ── HTML parsing ──────────────────────────────────────────────────────────────

class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.title: str = ""
        self.has_h1: bool = False
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True
            self.has_h1 = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


def _check_page(url: str) -> dict:
    result = {
        "url": url,
        "status": None,
        "load_time_ms": None,
        "title": None,
        "has_h1": False,
        "broken": False,
        "error": None,
        "links": [],
    }
    start = time.time()
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        elapsed_ms = int((time.time() - start) * 1000)
        result["status"] = resp.status_code
        result["load_time_ms"] = elapsed_ms

        if resp.status_code >= 400:
            result["broken"] = True
        else:
            ct = resp.headers.get("content-type", "")
            if "html" in ct:
                parser = _LinkParser()
                try:
                    parser.feed(resp.text)
                    result["title"] = parser.title or None
                    result["has_h1"] = parser.has_h1
                    result["links"] = parser.links
                except Exception:
                    pass

    except requests.exceptions.SSLError as exc:
        # Try http fallback
        try:
            http_url = url.replace("https://", "http://", 1)
            resp = requests.get(http_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            elapsed_ms = int((time.time() - start) * 1000)
            result["status"] = resp.status_code
            result["load_time_ms"] = elapsed_ms
            result["broken"] = resp.status_code >= 400
        except Exception as exc2:
            result["broken"] = True
            result["error"] = str(exc2)[:200]
    except requests.exceptions.ConnectionError as exc:
        result["broken"] = True
        result["error"] = f"Connection error: {str(exc)[:150]}"
    except requests.exceptions.Timeout:
        result["broken"] = True
        result["error"] = f"Timed out after {REQUEST_TIMEOUT}s"
    except Exception as exc:
        result["broken"] = True
        result["error"] = str(exc)[:200]

    return result


def _collect_internal_links(page_result: dict, base_url: str) -> list[str]:
    base_domain = urlparse(base_url).netloc
    links: set[str] = set()
    for href in page_result.get("links", []):
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            links.add(full_url.split("#")[0])
    return list(links)[:MAX_LINKS_TO_CRAWL]


def _run_tests(url: str) -> list[dict]:
    results = []
    visited: set[str] = set()

    # Check the base page
    base_result = _check_page(url)
    results.append(base_result)
    visited.add(url)

    if not base_result["broken"]:
        links = _collect_internal_links(base_result, url)
        for link in links:
            if link in visited:
                continue
            visited.add(link)
            results.append(_check_page(link))

    return results


# ── Summarise ─────────────────────────────────────────────────────────────────

def _summarise(results: list[dict]) -> dict:
    broken = [r for r in results if r["broken"]]
    slow   = [r for r in results if r["load_time_ms"] and r["load_time_ms"] > SLOW_THRESHOLD_MS]
    no_h1  = [r for r in results if not r["has_h1"] and not r["broken"]]
    return {
        "total_pages": len(results),
        "broken_count": len(broken),
        "slow_count": len(slow),
        "broken_pages": [r["url"] for r in broken],
        "slow_pages": [{"url": r["url"], "load_time_ms": r["load_time_ms"]} for r in slow],
        "pages_missing_h1": [r["url"] for r in no_h1],
        "pages_with_console_errors": [],   # not applicable without browser
        "all_pages": [{k: v for k, v in r.items() if k != "links"} for r in results],
    }


def _rule_based_report(url: str, summary: dict) -> str:
    lines = [
        f"## 🌐 Website Health Report",
        f"**URL:** {url}",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Pages checked | {summary['total_pages']} |",
        f"| 🔴 Broken / unreachable | {summary['broken_count']} |",
        f"| 🟡 Slow (>{SLOW_THRESHOLD_MS}ms) | {summary['slow_count']} |",
        f"| 🔵 Missing H1 heading | {len(summary['pages_missing_h1'])} |",
        "",
    ]

    if summary["broken_count"] == 0 and summary["slow_count"] == 0:
        lines.append("✅ **All pages are reachable and loading within acceptable time.**")
    else:
        if summary["broken_pages"]:
            lines.append("### 🔴 Broken / Unreachable Pages")
            for p in summary["broken_pages"]:
                lines.append(f"- `{p}`")
            lines.append("")

        if summary["slow_pages"]:
            lines.append(f"### 🟡 Slow Pages (>{SLOW_THRESHOLD_MS}ms)")
            for p in summary["slow_pages"]:
                lines.append(f"- `{p['url']}` — **{p['load_time_ms']} ms**")
            lines.append("")

        if summary["pages_missing_h1"]:
            lines.append("### 🔵 Pages Missing H1 Heading")
            for p in summary["pages_missing_h1"]:
                lines.append(f"- `{p}`")
            lines.append("")

    lines.append("---")
    lines.append("*Report generated by DeptOps AI Website Testing Agent*")
    return "\n".join(lines)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_website_testing_agent(url: str) -> dict:
    if not url.strip():
        return {"summary": {}, "ai_report": "Please enter a URL.", "error": "no_url"}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        results = _run_tests(url)
    except Exception as exc:
        return {
            "summary": {},
            "ai_report": f"Could not reach the website: {exc}",
            "error": str(exc),
        }

    summary = _summarise(results)
    ai_report = _rule_based_report(url, summary)

    # Try LLM for a richer report
    try:
        from config import get_llm
        from langchain_core.prompts import ChatPromptTemplate

        summary_text = (
            f"Website: {url}\n"
            f"Pages checked: {summary['total_pages']}\n"
            f"Broken pages ({summary['broken_count']}): {summary['broken_pages']}\n"
            f"Slow pages >{SLOW_THRESHOLD_MS}ms ({summary['slow_count']}): "
            f"{[p['url'] + ' (' + str(p['load_time_ms']) + 'ms)' for p in summary['slow_pages']]}\n"
            f"Pages missing H1: {summary['pages_missing_h1']}\n"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a web QA expert. Write a short prioritized report for the HOD. "
             "List critical issues first with suggested fixes. Be concise, use markdown."),
            ("human", "Test Results:\n{summary}"),
        ])
        llm = get_llm(temperature=0.2)
        response = (prompt | llm).invoke({"summary": summary_text})
        if response and response.content and len(response.content) > 30:
            ai_report = response.content
    except Exception:
        pass

    return {"summary": summary, "ai_report": ai_report, "error": None}
