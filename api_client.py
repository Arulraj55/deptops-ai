"""
api_client.py — lightweight HTTP client for DeptOps AI FastAPI backend

The Streamlit frontend uses this client to call the FastAPI endpoints instead
of importing agents or DB helpers directly. Base URL is configurable via
BACKEND_URL env var and defaults to http://localhost:8000
"""

from __future__ import annotations

import os
import requests
from typing import Any, Dict, List, Optional

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _url(path: str) -> str:
    return f"{BACKEND_URL}{path}"


def init_db() -> Dict[str, Any]:
    return requests.post(_url("/auth/init")).json()


def signin(username: str, password: str) -> Dict[str, Any]:
    resp = requests.post(_url("/auth/signin"), data={"username": username, "password": password})
    resp.raise_for_status()
    return resp.json()


def signup(username: str, full_name: str, password: str) -> Dict[str, Any]:
    resp = requests.post(_url("/auth/signup"), data={"username": username, "full_name": full_name, "password": password})
    resp.raise_for_status()
    return resp.json()


def upload_analytics(username: str, filename: str, content: bytes) -> Dict[str, Any]:
    files = {"file": (filename, content)}
    data = {"username": username}
    resp = requests.post(_url("/files/analytics/upload"), data=data, files=files)
    resp.raise_for_status()
    return resp.json()


def list_analytics(username: str) -> List[Dict[str, Any]]:
    resp = requests.get(_url("/files/analytics/list"), params={"username": username})
    resp.raise_for_status()
    return resp.json()


def upload_knowledge(username: str, filename: str, content: bytes) -> Dict[str, Any]:
    files = {"file": (filename, content)}
    data = {"username": username}
    resp = requests.post(_url("/files/knowledge/upload"), data=data, files=files)
    resp.raise_for_status()
    return resp.json()


def list_knowledge(username: str) -> List[str]:
    resp = requests.get(_url("/files/knowledge/list"), params={"username": username})
    resp.raise_for_status()
    return resp.json()


def chunk_count(username: str) -> int:
    resp = requests.get(_url("/files/knowledge/chunk-count"), params={"username": username})
    resp.raise_for_status()
    data = resp.json()
    return int(data.get("count", 0))


def reindex(username: str) -> Dict[str, Any]:
    resp = requests.post(_url("/knowledge/reindex"), data={"username": username})
    resp.raise_for_status()
    return resp.json()


def ask_knowledge(username: str, query: str) -> Dict[str, Any]:
    resp = requests.post(_url("/knowledge/ask"), json={"username": username, "query": query})
    resp.raise_for_status()
    return resp.json()


def criterion_summary(username: str, criterion_number: int) -> Dict[str, Any]:
    resp = requests.post(_url("/knowledge/criterion-summary"), json={"username": username, "criterion_number": criterion_number})
    resp.raise_for_status()
    return resp.json()


def ask_analytics(username: str, query: str, filename: Optional[str] = None) -> Dict[str, Any]:
    payload = {"username": username, "query": query}
    if filename:
        payload["filename"] = filename
    resp = requests.post(_url("/analytics/ask"), json=payload)
    resp.raise_for_status()
    return resp.json()


def analytics_full(username: str, filename: str) -> Dict[str, Any]:
    resp = requests.post(_url("/analytics/full"), json={"username": username, "filename": filename})
    resp.raise_for_status()
    return resp.json()


def compare_datasets(username: str, ds1: str, ds2: str) -> Dict[str, Any]:
    resp = requests.post(_url("/analytics/compare"), json={"username": username, "ds1": ds1, "ds2": ds2})
    resp.raise_for_status()
    return resp.json()


def excel_report(username: str, filename: str) -> bytes:
    resp = requests.post(_url("/analytics/excel-report"), json={"username": username, "filename": filename})
    resp.raise_for_status()
    return resp.content


def pdf_report(username: str, filename: str) -> bytes:
    resp = requests.post(_url("/analytics/pdf-report"), json={"username": username, "filename": filename})
    resp.raise_for_status()
    return resp.content


def website_audit(url: str, username: str = "hod") -> Dict[str, Any]:
    resp = requests.post(_url("/website/audit"), json={"url": url, "username": username})
    resp.raise_for_status()
    return resp.json()


def website_pdf_report(url: str, username: str = "hod") -> bytes:
    resp = requests.post(_url("/website/pdf-report"), json={"url": url, "username": username})
    resp.raise_for_status()
    return resp.content
