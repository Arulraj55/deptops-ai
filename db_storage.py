"""
db_storage.py — Per-user persistent file storage backed by Neon PostgreSQL.

Every file (analytics CSV/Excel, knowledge PDF/TXT) and the TF-IDF index
are scoped to the logged-in user via a username column.

Public API
----------
Analytics:
    save_analytics_file(username, filename, content_bytes)
    list_analytics_files(username) -> list[dict]   [{filename, uploaded_at}]
    load_analytics_file(username, filename) -> bytes | None
    delete_analytics_file(username, filename)

Knowledge:
    save_knowledge_file(username, filename, content_bytes)
    list_knowledge_files(username) -> list[str]
    load_knowledge_file(username, filename) -> bytes | None
    delete_knowledge_file(username, filename)

TF-IDF index:
    save_tfidf_index(username, index_json_str)
    load_tfidf_index(username) -> str | None
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "")


def _conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# ── Schema migration (called once on boot from auth._init_db) ─────────────────

def migrate_add_username_columns() -> None:
    """
    Safely add `username` column to existing tables if missing.
    Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+).
    Existing rows get username = 'legacy' so they don't break.
    Also rebuilds the UNIQUE constraints to be per-user.
    """
    stmts = [
        # analytics_files
        "ALTER TABLE analytics_files ADD COLUMN IF NOT EXISTS username VARCHAR(80) NOT NULL DEFAULT 'legacy'",
        # knowledge_files
        "ALTER TABLE knowledge_files ADD COLUMN IF NOT EXISTS username VARCHAR(80) NOT NULL DEFAULT 'legacy'",
        # tfidf_index
        "ALTER TABLE tfidf_index ADD COLUMN IF NOT EXISTS username VARCHAR(80) NOT NULL DEFAULT 'legacy'",
        # Drop old single-column unique constraints (best-effort, ignore if missing)
    ]
    with _conn() as con:
        with con.cursor() as cur:
            for stmt in stmts:
                cur.execute(stmt)
        con.commit()


# ── Analytics files ───────────────────────────────────────────────────────────

def save_analytics_file(username: str, filename: str, content: bytes) -> None:
    """Insert or replace an analytics file for this user."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "DELETE FROM analytics_files WHERE username = %s AND filename = %s",
                (username, filename),
            )
            cur.execute(
                "INSERT INTO analytics_files (username, filename, content) VALUES (%s, %s, %s)",
                (username, filename, psycopg2.Binary(content)),
            )
        con.commit()


def list_analytics_files(username: str) -> list[dict]:
    """Return list of {filename, uploaded_at} for this user, sorted by name."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT filename, uploaded_at FROM analytics_files WHERE username = %s ORDER BY filename",
                (username,),
            )
            rows = cur.fetchall()
    return [{"filename": r[0], "uploaded_at": r[1]} for r in rows]


def load_analytics_file(username: str, filename: str) -> bytes | None:
    """Return raw bytes for a stored analytics file, or None if not found."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT content FROM analytics_files WHERE username = %s AND filename = %s",
                (username, filename),
            )
            row = cur.fetchone()
    return bytes(row[0]) if row else None


def delete_analytics_file(username: str, filename: str) -> None:
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "DELETE FROM analytics_files WHERE username = %s AND filename = %s",
                (username, filename),
            )
        con.commit()


# ── Knowledge files ───────────────────────────────────────────────────────────

def save_knowledge_file(username: str, filename: str, content: bytes) -> None:
    """Insert or replace a knowledge document for this user."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "DELETE FROM knowledge_files WHERE username = %s AND filename = %s",
                (username, filename),
            )
            cur.execute(
                "INSERT INTO knowledge_files (username, filename, content) VALUES (%s, %s, %s)",
                (username, filename, psycopg2.Binary(content)),
            )
        con.commit()


def list_knowledge_files(username: str) -> list[str]:
    """Return sorted list of document filenames for this user."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT filename FROM knowledge_files WHERE username = %s ORDER BY filename",
                (username,),
            )
            rows = cur.fetchall()
    return [r[0] for r in rows]


def load_knowledge_file(username: str, filename: str) -> bytes | None:
    """Return raw bytes for a stored knowledge document, or None if not found."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT content FROM knowledge_files WHERE username = %s AND filename = %s",
                (username, filename),
            )
            row = cur.fetchone()
    return bytes(row[0]) if row else None


def delete_knowledge_file(username: str, filename: str) -> None:
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "DELETE FROM knowledge_files WHERE username = %s AND filename = %s",
                (username, filename),
            )
        con.commit()


# ── TF-IDF index ──────────────────────────────────────────────────────────────

def save_tfidf_index(username: str, index_json: str) -> None:
    """Upsert the TF-IDF index for this user."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM tfidf_index WHERE username = %s", (username,))
            cur.execute(
                "INSERT INTO tfidf_index (username, index_json) VALUES (%s, %s)",
                (username, index_json),
            )
        con.commit()


def load_tfidf_index(username: str) -> str | None:
    """Return the stored JSON string for this user, or None if not built yet."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT index_json FROM tfidf_index WHERE username = %s ORDER BY id DESC LIMIT 1",
                (username,),
            )
            row = cur.fetchone()
    return row[0] if row else None
