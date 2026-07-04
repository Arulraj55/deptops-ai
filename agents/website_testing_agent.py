"""
Website Testing Agent
---------------------
Uses Playwright to automatically verify department websites/portals.

Checks performed:
- Page reachability (HTTP status codes)
- Broken internal links
- Slow-loading pages (> threshold ms)
- Basic title / heading presence
- Console errors on the page

AI report is generated from LLM if available; falls back to a
rule-based report if the LLM is rate-limited or unavailable.
"""

import asyncio
import time
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page, BrowserContext


SLOW_THRESHOLD_MS = 3000
MAX_LINKS_TO_CRAWL = 20


# ── Core Playwright logic ────────────────────────────────────────────────────

async def _check_page(page: Page, url: str) -> dict:
    result = {
        "url": url,
        "status": None,
        "load_time_ms": None,
        "title": None,
        "has_h1": False,
        "console_errors": [],
        "broken": False,
        "error": None,
    }
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    start = time.time()
    try:
        response = await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        elapsed_ms = int((time.time() - start) * 1000)
        result["status"] = response.status if response else None
        result["load_time_ms"] = elapsed_ms
        result["title"] = await page.title()
        result["has_h1"] = await page.locator("h1").count() > 0
        result["console_errors"] = console_errors[:5]
        if response and response.status >= 400:
            result["broken"] = True
    except Exception as exc:
        result["broken"] = True
        result["error"] = str(exc)[:300]

    return result


async def _collect_links(page: Page, base_url: str) -> list[str]:
    base_domain = urlparse(base_url).netloc
    anchors = await page.locator("a[href]").all()
    links: set[str] = set()
    for anchor in anchors:
        href = await anchor.get_attribute("href")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            links.add(full_url.split("#")[0])
    return list(links)[:MAX_LINKS_TO_CRAWL]


async def _run_tests(url: str) -> list[dict]:
    results = []
    visited: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx: BrowserContext = await browser.new_context(user_agent="DeptOpsAI-Tester/1.0")

        page = await ctx.new_page()
        base_result = await _check_page(page, url)
        results.append(base_result)
        visited.add(url)

        if not base_result["broken"]:
            links = await _collect_links(page, url)
            for link in links:
                if link in visited:
                    continue
                visited.add(link)
                lp = await ctx.new_page()
                results.append(await _check_page(lp, link))
                await lp.close()

        await browser.close()
    return results


# ── Summarise ────────────────────────────────────────────────────────────────

def _summarise(results: list[dict]) -> dict:
    broken  = [r for r in results if r["broken"]]
    slow    = [r for r in results if r["load_time_ms"] and r["load_time_ms"] > SLOW_THRESHOLD_MS]
    no_h1   = [r for r in results if not r["has_h1"] and not r["broken"]]
    errs    = [r for r in results if r["console_errors"]]
    return {
        "total_pages": len(results),
        "broken_count": len(broken),
        "slow_count": len(slow),
        "broken_pages": [r["url"] for r in broken],
        "slow_pages": [{"url": r["url"], "load_time_ms": r["load_time_ms"]} for r in slow],
        "pages_missing_h1": [r["url"] for r in no_h1],
        "pages_with_console_errors": [{"url": r["url"], "errors": r["console_errors"]} for r in errs],
        "all_pages": results,
    }


def _rule_based_report(url: str, summary: dict) -> str:
    """Generate a plain-text report without using the LLM."""
    lines = [
        f"## Website Health Report: {url}",
        f"",
        f"**Pages checked:** {summary['total_pages']}",
        f"**Broken pages:** {summary['broken_count']}",
        f"**Slow pages (>{SLOW_THRESHOLD_MS}ms):** {summary['slow_count']}",
        f"**Pages with JS errors:** {len(summary['pages_with_console_errors'])}",
        "",
    ]

    if summary["broken_count"] == 0 and summary["slow_count"] == 0:
        lines.append("✅ **All pages are reachable and loading within acceptable time.**")
    else:
        if summary["broken_pages"]:
            lines.append("### 🔴 Critical — Broken / Unreachable Pages")
            for p in summary["broken_pages"]:
                lines.append(f"- {p}")
            lines.append("")

        if summary["slow_pages"]:
            lines.append(f"### 🟡 Performance — Slow Pages (>{SLOW_THRESHOLD_MS}ms)")
            for p in summary["slow_pages"]:
                lines.append(f"- {p['url']} — {p['load_time_ms']} ms")
            lines.append("")

        if summary["pages_missing_h1"]:
            lines.append("### 🔵 SEO/Accessibility — Pages Missing H1 Heading")
            for p in summary["pages_missing_h1"]:
                lines.append(f"- {p}")
            lines.append("")

        if summary["pages_with_console_errors"]:
            lines.append("### ⚠️ JavaScript Console Errors")
            for p in summary["pages_with_console_errors"]:
                lines.append(f"- {p['url']}: {'; '.join(p['errors'][:2])}")
            lines.append("")

    lines.append("*Report generated by DeptOps AI Website Testing Agent.*")
    return "\n".join(lines)


# ── Main Entry Point ─────────────────────────────────────────────────────────

def run_website_testing_agent(url: str) -> dict:
    """
    Test a department website. Returns summary metrics + an AI (or rule-based) report.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        results = asyncio.run(_run_tests(url))
    except Exception as exc:
        return {
            "summary": {},
            "ai_report": f"Could not reach the website: {exc}",
            "error": str(exc),
        }

    summary = _summarise(results)

    # Always start with rule-based report — shown if LLM unavailable
    ai_report = _rule_based_report(url, summary)

    # Try to get a better LLM report — silently skip on any error (rate limit etc.)
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
             "List critical issues first. Suggest fixes. Be concise."),
            ("human", "Test Results:\n{summary}"),
        ])
        llm = get_llm(temperature=0.2)
        response = (prompt | llm).invoke({"summary": summary_text})
        if response and response.content and len(response.content) > 20:
            ai_report = response.content
    except Exception:
        pass  # rule-based report already set above

    return {"summary": summary, "ai_report": ai_report, "error": None}
