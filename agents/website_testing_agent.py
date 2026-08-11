"""
Website Testing Agent for DeptOps AI
------------------------------------
Automated Real-Browser Website Crawler & Diagnostic Engine.

Uses Playwright Headless Browser to:
1. Discover all reachable internal pages (including JavaScript-rendered links and SPA routes).
2. Visit every discovered page and verify page open success.
3. Detect HTTP errors (4xx/5xx), broken pages, navigation timeouts, frontend JS runtime errors,
   and failed network/API requests.
4. Generate a clear report detailing total pages found, working pages, broken pages, and exact failure reasons.
"""

import io
import time
import socket
import ssl
import logging
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

from config import invoke_openrouter_free_models

logger = logging.getLogger("WebsiteTestingAgent")

MAX_CRAWL_PAGES = 50
PAGE_TIMEOUT_MS = 15000

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeptOpsAI-RealBrowserTester/3.0"


def check_dns(domain: str) -> bool:
    try:
        socket.gethostbyname(domain)
        return True
    except Exception:
        return False


def check_ssl(domain: str) -> dict:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                return {"valid": True, "issuer": cert.get("issuer", [])}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


def audit_single_page_with_playwright(browser, url: str, base_domain: str, timeout_ms: int = PAGE_TIMEOUT_MS) -> dict:
    """Visits a single page using a real Playwright browser context, tracking JS errors and network failures."""
    context = browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
    page = context.new_page()

    failure_reasons = []
    js_errors = []
    failed_network_requests = []
    status_code = None
    page_title = None
    discovered_links = set()

    # Listeners for JS runtime errors and console logs
    page.on("pageerror", lambda err: js_errors.append(f"Uncaught Exception: {str(err)}"))
    page.on("console", lambda msg: js_errors.append(f"Console Error: {msg.text}") if msg.type == "error" else None)

    # Listeners for failed network requests and HTTP 4xx/5xx sub-resources
    def handle_request_failed(req):
        err = req.failure.error_text if req.failure else "Network Request Failed"
        failed_network_requests.append(f"{req.method} {req.url} — {err}")

    def handle_response(resp):
        if resp.status >= 400 and not resp.url.startswith("data:"):
            failed_network_requests.append(f"HTTP {resp.status} on {resp.request.method} {resp.url}")

    page.on("requestfailed", handle_request_failed)
    page.on("response", handle_response)

    start_time = time.time()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        load_time_ms = int((time.time() - start_time) * 1000)
        if response:
            status_code = response.status
        else:
            status_code = 0
    except Exception as exc:
        load_time_ms = int((time.time() - start_time) * 1000)
        err_msg = str(exc)
        if "Timeout" in err_msg or "timeout" in err_msg:
            failure_reasons.append(f"Navigation Timeout: Page load exceeded {timeout_ms}ms limit")
        else:
            failure_reasons.append(f"Page Load Crash: {err_msg[:180]}")
        status_code = 0

    # Evaluate HTTP Status Code
    if status_code and status_code >= 400:
        failure_reasons.append(f"HTTP Error {status_code}: Main page returned HTTP status {status_code}")

    if status_code is not None and status_code < 400 and not failure_reasons:
        try:
            page_title = page.title()
        except Exception:
            page_title = "Untitled Page"

        # Extract reachable internal links & JS routes rendered in the DOM
        try:
            hrefs = page.eval_on_selector_all("a[href]", "elements => elements.map(e => e.getAttribute('href'))")
            for h in hrefs:
                if not h:
                    continue
                h_str = str(h).strip()
                if h_str.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                full_url = urljoin(url, h_str).split("#")[0].strip()
                parsed = urlparse(full_url)
                if parsed.scheme in ("http", "https"):
                    # Check if domain matches base domain
                    if parsed.netloc == base_domain or parsed.netloc == f"www.{base_domain}" or base_domain == f"www.{parsed.netloc}":
                        norm_url = full_url.rstrip("/") if len(parsed.path) > 1 else full_url
                        discovered_links.add(norm_url)
        except Exception as exc:
            logger.warning(f"Error extracting links from {url}: {exc}")

    # Append recorded frontend JS errors and failed network requests to failure reasons
    for js_err in js_errors:
        failure_reasons.append(f"Frontend JS Error: {js_err}")
    for net_err in failed_network_requests:
        failure_reasons.append(f"Failed Network/API Request: {net_err}")

    context.close()

    is_broken = len(failure_reasons) > 0

    return {
        "url": url,
        "status": status_code,
        "load_time_ms": load_time_ms,
        "title": page_title or "Untitled Page",
        "broken": is_broken,
        "failure_reasons": failure_reasons,
        "internal_links": list(discovered_links),
        "js_errors_count": len(js_errors),
        "failed_requests_count": len(failed_network_requests),
    }


def run_website_audit(target_url: str, max_pages: int = MAX_CRAWL_PAGES) -> dict:
    """Crawls all reachable internal pages of a website using Playwright real browser."""
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    parsed_target = urlparse(target_url)
    base_domain = parsed_target.netloc

    dns_ok = check_dns(base_domain)
    ssl_info = check_ssl(base_domain) if target_url.startswith("https://") else {"valid": False}

    pages = []
    working_pages = []
    broken_pages = []

    to_visit = [target_url]
    visited = set()

    logger.info(f"Starting real browser audit for {target_url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                while to_visit and len(visited) < max_pages:
                    curr_url = to_visit.pop(0)
                    parsed_curr = urlparse(curr_url)
                    norm_curr = curr_url.rstrip("/") if len(parsed_curr.path) > 1 else curr_url
                    if norm_curr in visited:
                        continue
                    visited.add(norm_curr)

                    audit_res = audit_single_page_with_playwright(browser, curr_url, base_domain)
                    pages.append(audit_res)

                    if audit_res["broken"]:
                        broken_pages.append(audit_res)
                    else:
                        working_pages.append(audit_res)

                    # Queue newly discovered internal links
                    for link in audit_res["internal_links"]:
                        parsed_link = urlparse(link)
                        norm_link = link.rstrip("/") if len(parsed_link.path) > 1 else link
                        if norm_link not in visited and norm_link not in [u.rstrip("/") for u in to_visit]:
                            to_visit.append(link)
            finally:
                browser.close()
    except Exception as exc:
        logger.error(f"Playwright browser crawling error: {exc}")

    total_found = len(pages)
    total_working = len(working_pages)
    total_broken = len(broken_pages)

    health_score = max(0, min(100, int((total_working / max(total_found, 1)) * 100)))

    scores = {
        "overall": health_score,
        "working_percentage": health_score,
        "performance": max(0, min(100, int(100 - (total_broken * 15)))),
        "reliability": health_score,
    }

    return {
        "url": target_url,
        "domain": base_domain,
        "dns_valid": dns_ok,
        "ssl_valid": ssl_info.get("valid", False),
        "total_pages_found": total_found,
        "total_working": total_working,
        "total_broken": total_broken,
        "working_pages": working_pages,
        "broken_pages": broken_pages,
        "all_pages": pages,
        "scores": scores,
    }


def generate_ai_website_report(summary: dict) -> str:
    url = summary["url"]
    scores = summary["scores"]
    total_found = summary["total_pages_found"]
    total_working = summary["total_working"]
    total_broken = summary["total_broken"]
    broken_pages = summary["broken_pages"]

    broken_summary_text = ""
    for bp in broken_pages[:10]:  # Highlight top broken pages
        reasons = "; ".join(bp.get("failure_reasons", []))
        broken_summary_text += f"- Page `{bp['url']}`: {reasons}\n"

    prompt = (
        f"You are the Senior Web Quality & NAAC Audit Inspector for DeptOps AI.\n"
        f"Analyze the real-browser website crawl results for `{url}`:\n\n"
        f"Key Metrics:\n"
        f"- Total Internal Pages Discovered & Crawled: {total_found}\n"
        f"- Working Pages: {total_working}\n"
        f"- Broken Pages: {total_broken}\n"
        f"- Health Score: {scores['overall']}/100\n"
        f"- SSL Valid: {summary.get('ssl_valid')}, DNS Valid: {summary.get('dns_valid')}\n\n"
        f"Broken Pages Breakdown:\n"
        f"{broken_summary_text if broken_summary_text else 'No broken pages found! All pages opened successfully.'}\n\n"
        f"Provide a clear executive summary report detailing:\n"
        f"1. Executive Audit Summary\n"
        f"2. Root Cause Analysis of Broken Pages, Frontend JS Errors, Timeouts, & Network Failures\n"
        f"3. Concrete Actionable Fixes for Developers to ensure 100% reachability & reliability."
    )

    try:
        return invoke_openrouter_free_models(prompt, temperature=0.2)
    except Exception as exc:
        logger.error(f"OpenRouter report generation fallback: {exc}")
        return (
            f"### 🌐 Website Audit Report — `{url}`\n\n"
            f"- **Total Reachable Pages Discovered:** {total_found}\n"
            f"- **Working Pages:** {total_working} 🟢\n"
            f"- **Broken Pages:** {total_broken} 🔴\n"
            f"- **Overall Health Score:** {scores['overall']}/100\n"
        )


def generate_website_pdf_report(url: str, summary: dict, ai_report: str) -> bytes:
    """Generates a downloadable PDF report detailing website crawl results."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18,
            leading=22, textColor=colors.HexColor('#0f9d8a'), spaceAfter=12
        )
        body_style = ParagraphStyle(
            'BodyStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, spaceAfter=8
        )

        scores = summary.get("scores", {})
        total_found = summary.get("total_pages_found", 0)
        total_working = summary.get("total_working", 0)
        total_broken = summary.get("total_broken", 0)

        elements = [
            Paragraph("🌐 DeptOps AI — Real-Browser Website Audit Report", title_style),
            Paragraph(f"<b>Target URL:</b> {url} | <b>Health Score:</b> {scores.get('overall', 0)}/100", body_style),
            Spacer(1, 10),
            Paragraph("<b>Crawl & Audit Metrics:</b>", styles['Heading2']),
            Spacer(1, 6),
        ]

        metrics_table = [
            ["Metric", "Value", "Status"],
            ["Total Internal Pages Found", str(total_found), "Scanned"],
            ["Working Pages", str(total_working), "Pass 🟢"],
            ["Broken Pages", str(total_broken), "Needs Fix 🔴" if total_broken > 0 else "Clean 🟢"],
            ["Overall Health Score", f"{scores.get('overall', 0)}%", "Good" if scores.get('overall', 0) >= 80 else "Attention Needed"],
        ]
        t = Table(metrics_table, colWidths=[180, 100, 140])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f9d8a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 14))

        if summary.get("broken_pages"):
            elements.append(Paragraph("<b>Broken Pages & Failure Reasons:</b>", styles['Heading2']))
            elements.append(Spacer(1, 6))
            broken_data = [["URL", "Status", "Failure Reasons"]]
            for bp in summary["broken_pages"]:
                reasons_str = "<br/>".join(bp.get("failure_reasons", []))
                broken_data.append([
                    Paragraph(bp["url"], body_style),
                    str(bp.get("status", "Error")),
                    Paragraph(reasons_str, body_style)
                ])
            bt = Table(broken_data, colWidths=[160, 60, 200])
            bt.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d9534f')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(bt)
            elements.append(Spacer(1, 14))

        elements.append(Paragraph("<b>AI Recommendations & Developer Fixes:</b>", styles['Heading2']))
        elements.append(Spacer(1, 6))

        # Safely split and sanitize lines for ReportLab Paragraph compatibility
        clean_report = ai_report.replace("<br>", "\n").replace("<br/>", "\n")
        for line in clean_report.split("\n"):
            line_str = line.strip()
            if not line_str:
                elements.append(Spacer(1, 4))
                continue
            # Escaping XML special characters so ReportLab doesn't fail on raw markdown/HTML tags
            safe_line = line_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            elements.append(Paragraph(safe_line, body_style))

        doc.build(elements)
        return buffer.getvalue()
    except Exception as exc:
        logger.error(f"Failed to generate website PDF report: {exc}")
        return f"PDF generation error: {exc}".encode("utf-8")


def run_website_testing_agent(url: str, username: str = "hod") -> dict:
    if not url.strip():
        return {"summary": {}, "ai_report": "Please enter a valid website URL.", "error": "no_url"}

    summary = run_website_audit(url)
    ai_report = generate_ai_website_report(summary)

    try:
        from db_storage import save_website_scan
        save_website_scan(
            username=username,
            url=url,
            overall_score=summary["scores"]["overall"],
            scores_dict=summary["scores"],
            report_text=ai_report
        )
    except Exception as exc:
        logger.warning(f"Could not persist scan history: {exc}")

    return {
        "summary": summary,
        "ai_report": ai_report,
        "scores": summary["scores"],
        "all_pages": summary["all_pages"],
        "working_pages": summary["working_pages"],
        "broken_pages": summary["broken_pages"],
        "total_pages_found": summary["total_pages_found"],
        "total_working": summary["total_working"],
        "total_broken": summary["total_broken"],
    }
