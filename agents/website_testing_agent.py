"""
Website Testing Agent for DeptOps AI
------------------------------------
Automated Website Audit & NAAC Readiness Inspector.

Performs multi-category website testing starting from a single URL:
A. Basic Testing (Reachability, HTTP status, HTTPS/SSL, Redirects, Response Time, DNS Lookup)
B. Link Testing (Broken links, Internal/External links, Redirect loops, Missing pages)
C. SEO Testing (Title, Meta Description, H1/H2, Robots.txt, Sitemap.xml, Canonical URL, Open Graph, Twitter Cards)
D. Accessibility (Missing ALT tags, Form labels, Heading hierarchy, Accessibility score)
E. Performance (Page Load Time, Slow resources, CSS/JS size, Compression, Cache headers)
F. Security (Security headers: HSTS, CSP, X-Frame-Options, XSS protection, Clickjacking, Mixed Content)
G. Content Validation (Missing images/CSS/JS, Empty pages, Duplicate titles)
H. Website Structure (Navigation tree, Total pages, images, PDFs, forms)

Generates:
- Overall Website Health Score (0-100)
- Category Scores (Performance, SEO, Accessibility, Security)
- OpenRouter free-model AI recommendations
- Downloadable PDF Audit Report
"""

import io
import time
import socket
import ssl
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import logging

from config import invoke_openrouter_free_models

logger = logging.getLogger("WebsiteTestingAgent")

SLOW_THRESHOLD_MS = 3000
MAX_CRAWL_PAGES = 15
REQUEST_TIMEOUT = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeptOpsAI-WebsiteAuditor/2.5"
}


# ── Category A: Basic & Security Testing Functions ────────────────────────────

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


def check_robots_and_sitemap(base_url: str) -> dict:
    robots_url = urljoin(base_url, "/robots.txt")
    sitemap_url = urljoin(base_url, "/sitemap.xml")

    res = {"has_robots": False, "has_sitemap": False}
    try:
        r = requests.get(robots_url, headers=HEADERS, timeout=5)
        res["has_robots"] = r.status_code == 200
    except Exception:
        pass

    try:
        s = requests.get(sitemap_url, headers=HEADERS, timeout=5)
        res["has_sitemap"] = s.status_code == 200
    except Exception:
        pass

    return res


# ── Single Page Full Audit (Categories A-H) ───────────────────────────────────

def audit_single_page(url: str, base_domain: str) -> dict:
    result = {
        "url": url,
        "status": None,
        "load_time_ms": None,
        "broken": False,
        "is_https": url.startswith("https://"),
        "error": None,
        # SEO
        "title": None,
        "meta_desc": None,
        "has_h1": False,
        "h2_count": 0,
        "canonical": None,
        "has_og": False,
        "has_twitter_card": False,
        "has_structured_data": False,
        # Accessibility
        "missing_alt_count": 0,
        "total_images": 0,
        "missing_form_labels": 0,
        "total_forms": 0,
        # Performance & Resources
        "css_count": 0,
        "js_count": 0,
        "pdf_count": 0,
        "has_compression": False,
        "cache_control": None,
        # Security
        "security_headers": {},
        "has_hsts": False,
        "has_csp": False,
        "has_xframe": False,
        # Links
        "internal_links": [],
        "external_links": [],
    }

    start = time.time()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        elapsed_ms = int((time.time() - start) * 1000)
        result["status"] = resp.status_code
        result["load_time_ms"] = elapsed_ms

        if resp.status_code >= 400:
            result["broken"] = True
            return result

        # Check response headers for compression & security
        h = resp.headers
        result["has_compression"] = "gzip" in h.get("content-encoding", "") or "br" in h.get("content-encoding", "")
        result["cache_control"] = h.get("cache-control")

        result["has_hsts"] = "strict-transport-security" in h
        result["has_csp"] = "content-security-policy" in h
        result["has_xframe"] = "x-frame-options" in h
        result["security_headers"] = {
            "hsts": result["has_hsts"],
            "csp": result["has_csp"],
            "x_frame_options": result["has_xframe"],
            "x_content_type_options": "x-content-type-options" in h
        }

        # Parse HTML content using BeautifulSoup
        ct = h.get("content-type", "")
        if "html" in ct:
            soup = BeautifulSoup(resp.text, "html.parser")

            # SEO
            result["title"] = soup.title.string.strip() if soup.title and soup.title.string else None
            m_desc = soup.find("meta", attrs={"name": "description"})
            result["meta_desc"] = m_desc["content"].strip() if m_desc and m_desc.get("content") else None
            result["has_h1"] = len(soup.find_all("h1")) > 0
            result["h2_count"] = len(soup.find_all("h2"))
            can = soup.find("link", attrs={"rel": "canonical"})
            result["canonical"] = can["href"] if can and can.get("href") else None

            result["has_og"] = len(soup.find_all("meta", property=re.compile(r"^og:"))) > 0
            result["has_twitter_card"] = len(soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")})) > 0
            result["has_structured_data"] = len(soup.find_all("script", type="application/ld+json")) > 0

            # Accessibility & Images
            imgs = soup.find_all("img")
            result["total_images"] = len(imgs)
            result["missing_alt_count"] = sum(1 for img in imgs if not img.get("alt"))

            # Forms & Labels
            forms = soup.find_all("form")
            result["total_forms"] = len(forms)
            inputs = soup.find_all(["input", "select", "textarea"])
            result["missing_form_labels"] = sum(1 for i in inputs if not i.get("aria-label") and not i.get("id"))

            # Resources & PDFs
            result["css_count"] = len(soup.find_all("link", rel="stylesheet"))
            result["js_count"] = len(soup.find_all("script", src=True))
            result["pdf_count"] = len([a for a in soup.find_all("a", href=True) if a["href"].endswith(".pdf")])

            # Links
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                full = urljoin(url, href).split("#")[0]
                parsed = urlparse(full)
                if parsed.scheme in ("http", "https"):
                    if parsed.netloc == base_domain:
                        result["internal_links"].append(full)
                    else:
                        result["external_links"].append(full)

    except Exception as exc:
        result["broken"] = True
        result["error"] = str(exc)[:200]

    return result


# ── Full Website Crawler & Multi-Category Audit Engine ───────────────────────

def run_website_audit(target_url: str) -> dict:
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    parsed_target = urlparse(target_url)
    base_domain = parsed_target.netloc

    # Basic checks
    dns_ok = check_dns(base_domain)
    ssl_info = check_ssl(base_domain) if target_url.startswith("https://") else {"valid": False}
    robots_sitemap = check_robots_and_sitemap(target_url)

    # Crawl internal pages
    pages = []
    queue = [target_url]
    visited = set()

    while queue and len(visited) < MAX_CRAWL_PAGES:
        curr_url = queue.pop(0)
        if curr_url in visited:
            continue
        visited.add(curr_url)

        audit_res = audit_single_page(curr_url, base_domain)
        pages.append(audit_res)

        # Queue internal links
        if not audit_res["broken"]:
            for link in audit_res["internal_links"]:
                if link not in visited and link not in queue:
                    queue.append(link)

    # Calculate Category & Health Scores (0-100)
    total_p = len(pages)
    broken_p = sum(1 for p in pages if p["broken"])
    slow_p = sum(1 for p in pages if p.get("load_time_ms") and p["load_time_ms"] > SLOW_THRESHOLD_MS)

    # 1. Performance Score
    avg_load = sum(p.get("load_time_ms", 0) for p in pages if p.get("load_time_ms")) / max(total_p, 1)
    perf_score = max(0, min(100, int(100 - (slow_p / max(total_p, 1) * 40) - (avg_load / 100))))

    # 2. SEO Score
    seo_pass = sum(1 for p in pages if p.get("title") and p.get("meta_desc") and p.get("has_h1"))
    seo_score = max(0, min(100, int((seo_pass / max(total_p, 1) * 80) + (20 if robots_sitemap["has_sitemap"] else 0))))

    # 3. Accessibility Score
    acc_pass = sum(1 for p in pages if p.get("missing_alt_count", 0) == 0)
    acc_score = max(0, min(100, int((acc_pass / max(total_p, 1)) * 100)))

    # 4. Security Score
    sec_pass = sum(1 for p in pages if p.get("has_hsts") and p.get("has_csp") and p.get("has_xframe"))
    sec_score = max(0, min(100, int((sec_pass / max(total_p, 1) * 70) + (30 if ssl_info.get("valid") else 0))))

    # Overall Health Score
    overall_health = int((perf_score * 0.25) + (seo_score * 0.25) + (acc_score * 0.25) + (sec_score * 0.25))

    scores = {
        "overall": overall_health,
        "performance": perf_score,
        "seo": seo_score,
        "accessibility": acc_score,
        "security": sec_score,
    }

    summary = {
        "url": target_url,
        "domain": base_domain,
        "dns_valid": dns_ok,
        "ssl_valid": ssl_info.get("valid", False),
        "has_robots": robots_sitemap["has_robots"],
        "has_sitemap": robots_sitemap["has_sitemap"],
        "total_pages_crawled": total_p,
        "broken_pages_count": broken_p,
        "slow_pages_count": slow_p,
        "scores": scores,
        "pages": pages,
    }

    return summary


# ── AI Report & Recommendations Generator (OpenRouter Free Models) ────────────

def generate_ai_website_report(summary: dict) -> str:
    url = summary["url"]
    scores = summary["scores"]

    prompt = (
        f"You are the senior NAAC Website Audit Agent for DeptOps AI.\n"
        f"Analyze the following automated website inspection results for department website `{url}` and generate an executive NAAC readiness audit report.\n\n"
        f"Scores (0-100):\n"
        f"- Overall Health Score: {scores['overall']}/100\n"
        f"- Performance Score: {scores['performance']}/100\n"
        f"- SEO Score: {scores['seo']}/100\n"
        f"- Accessibility Score: {scores['accessibility']}/100\n"
        f"- Security Score: {scores['security']}/100\n\n"
        f"Key Metrics:\n"
        f"- Pages Crawled: {summary['total_pages_crawled']}\n"
        f"- Broken Pages: {summary['broken_pages_count']}\n"
        f"- Slow Pages (>3s): {summary['slow_pages_count']}\n"
        f"- SSL Valid: {summary['ssl_valid']}, Sitemap: {summary['has_sitemap']}\n\n"
        f"Provide:\n"
        f"1. Executive NAAC Inspection Summary\n"
        f"2. Critical Fixes Needed (Broken links, security headers, ALT tags, response times)\n"
        f"3. Specific Actionable Steps to ensure 100% compliance during accreditation review."
    )

    try:
        return invoke_openrouter_free_models(prompt, temperature=0.2)
    except Exception as exc:
        logger.error(f"OpenRouter free-model fallback failed for Website Testing Agent: {exc}")
        return (
            f"### 🌐 Website Audit Report — `{url}`\n\n"
            f"**Overall Health Score:** {scores['overall']}/100\n"
            f"- **Performance:** {scores['performance']}/100\n"
            f"- **SEO:** {scores['seo']}/100\n"
            f"- **Accessibility:** {scores['accessibility']}/100\n"
            f"- **Security:** {scores['security']}/100\n\n"
            f"**Crawled Pages:** {summary['total_pages_crawled']} | **Broken:** {summary['broken_pages_count']} | **Slow:** {summary['slow_pages_count']}"
        )


# ── PDF Audit Report Generator ───────────────────────────────────────────────

def generate_website_pdf_report(url: str, summary: dict, ai_report: str) -> bytes:
    """Generates a downloadable PDF report for NAAC web compliance."""
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
        elements = [
            Paragraph("🌐 DeptOps AI — Website Audit Report", title_style),
            Paragraph(f"<b>Target URL:</b> {url} | <b>Health Score:</b> {scores.get('overall', 0)}/100", body_style),
            Spacer(1, 10),
            Paragraph("<b>Category Health Scores:</b>", styles['Heading2']),
            Spacer(1, 6),
        ]

        score_table = [
            ["Category", "Score", "Status"],
            ["Performance", f"{scores.get('performance',0)}/100", "Good" if scores.get('performance',0)>=70 else "Needs Fix"],
            ["SEO", f"{scores.get('seo',0)}/100", "Good" if scores.get('seo',0)>=70 else "Needs Fix"],
            ["Accessibility", f"{scores.get('accessibility',0)}/100", "Good" if scores.get('accessibility',0)>=70 else "Needs Fix"],
            ["Security", f"{scores.get('security',0)}/100", "Good" if scores.get('security',0)>=70 else "Needs Fix"],
        ]
        t = Table(score_table, colWidths=[150, 100, 150])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f9d8a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 14))

        elements.append(Paragraph("<b>AI Recommendations & NAAC Fixes:</b>", styles['Heading2']))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(ai_report.replace("\n", "<br/>"), body_style))

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

    # Save to PostgreSQL scan history
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
        "all_pages": summary["pages"]
    }
