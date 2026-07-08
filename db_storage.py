"""
db_storage.py — Persistent file storage backed by Neon PostgreSQL.

All uploaded files (CSV, Excel, PDF, TXT) and the TF-IDF index are stored
in the database so they survive Render restarts and redeploys.

Public API
----------
Analytics:
    save_analytics_file(filename, content_bytes)
    list_analytics_files() -> list[dict]  # [{id, filename, uploaded_at}]
    load_analytics_file(filename) -> bytes | None
    delete_analytics_file(filename)

Knowledge:
    save_knowledge_file(filename, content_bytes)
    list_knowledge_files() -> list[str]
    load_knowledge_file(filename) -> bytes | None
    delete_knowledge_file(filename)

TF-IDF index:
    save_tfidf_index(index_json_str)
    load_tfidf_index() -> str | None
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "")


def _conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# ── Analytics files ───────────────────────────────────────────────────────────

def save_analytics_file(filename: str, content: bytes) -> None:
    """Insert or replace an analytics file by filename."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM analytics_files WHERE filename = %s", (filename,))
            cur.execute(
                "INSERT INTO analytics_files (filename, content) VALUES (%s, %s)",
                (filename, psycopg2.Binary(content)),
            )
        con.commit()


def list_analytics_files() -> list[dict]:
    """Return list of {filename, uploaded_at} sorted by name."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("SELECT filename, uploaded_at FROM analytics_files ORDER BY filename")
            rows = cur.fetchall()
    return [{"filename": r[0], "uploaded_at": r[1]} for r in rows]


def load_analytics_file(filename: str) -> bytes | None:
    """Return raw bytes for a stored analytics file, or None if not found."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("SELECT content FROM analytics_files WHERE filename = %s", (filename,))
            row = cur.fetchone()
    return bytes(row[0]) if row else None


def delete_analytics_file(filename: str) -> None:
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM analytics_files WHERE filename = %s", (filename,))
        con.commit()


# ── Knowledge files ───────────────────────────────────────────────────────────

def save_knowledge_file(filename: str, content: bytes) -> None:
    """Insert or replace a knowledge document by filename."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM knowledge_files WHERE filename = %s", (filename,))
            cur.execute(
                "INSERT INTO knowledge_files (filename, content) VALUES (%s, %s)",
                (filename, psycopg2.Binary(content)),
            )
        con.commit()


def list_knowledge_files() -> list[str]:
    """Return sorted list of document filenames."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("SELECT filename FROM knowledge_files ORDER BY filename")
            rows = cur.fetchall()
    return [r[0] for r in rows]


def load_knowledge_file(filename: str) -> bytes | None:
    """Return raw bytes for a stored knowledge document, or None if not found."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("SELECT content FROM knowledge_files WHERE filename = %s", (filename,))
            row = cur.fetchone()
    return bytes(row[0]) if row else None


def delete_knowledge_file(filename: str) -> None:
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM knowledge_files WHERE filename = %s", (filename,))
        con.commit()


# ── TF-IDF index ──────────────────────────────────────────────────────────────

def save_tfidf_index(index_json: str) -> None:
    """Upsert the single TF-IDF index row."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM tfidf_index")
            cur.execute("INSERT INTO tfidf_index (index_json) VALUES (%s)", (index_json,))
        con.commit()


def load_tfidf_index() -> str | None:
    """Return the stored JSON string, or None if not built yet."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("SELECT index_json FROM tfidf_index ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
    return row[0] if row else None
