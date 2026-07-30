"""
db_storage.py — Per-user persistent file & history storage backed by Neon PostgreSQL.

Every file (analytics CSV/Excel, knowledge PDF/TXT/DOCX/MD), reports, scan history,
and chat messages are scoped to the logged-in user via a username column.
"""

import os
import json
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "")


def _conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def migrate_add_username_columns() -> None:
    """Safely ensure all username columns exist across tables."""
    stmts = [
        "ALTER TABLE analytics_files ADD COLUMN IF NOT EXISTS username VARCHAR(80) NOT NULL DEFAULT 'legacy'",
        "ALTER TABLE knowledge_files ADD COLUMN IF NOT EXISTS username VARCHAR(80) NOT NULL DEFAULT 'legacy'",
        "ALTER TABLE tfidf_index ADD COLUMN IF NOT EXISTS username VARCHAR(80) NOT NULL DEFAULT 'legacy'",
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
    """Return list of {filename, uploaded_at} for this user, sorted by most recently uploaded first."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT filename, uploaded_at FROM analytics_files WHERE username = %s ORDER BY uploaded_at DESC, id DESC",
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


# ── Website Scan History ──────────────────────────────────────────────────────

def save_website_scan(username: str, url: str, overall_score: int, scores_dict: dict, report_text: str) -> None:
    """Save website testing scan result."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                """INSERT INTO website_scan_history (username, url, overall_score, scores_json, report_text)
                   VALUES (%s, %s, %s, %s, %s)""",
                (username, url, overall_score, json.dumps(scores_dict), report_text)
            )
        con.commit()


def get_latest_website_scan(username: str, url: str | None = None) -> dict | None:
    """Fetch the latest scan record for user."""
    with _conn() as con:
        with con.cursor() as cur:
            if url:
                cur.execute(
                    "SELECT url, overall_score, scores_json, report_text, created_at FROM website_scan_history WHERE username = %s AND url = %s ORDER BY id DESC LIMIT 1",
                    (username, url)
                )
            else:
                cur.execute(
                    "SELECT url, overall_score, scores_json, report_text, created_at FROM website_scan_history WHERE username = %s ORDER BY id DESC LIMIT 1",
                    (username,)
                )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "url": row[0],
        "overall_score": row[1],
        "scores": json.loads(row[2]) if row[2] else {},
        "report": row[3],
        "created_at": row[4],
    }


# ── Unified Chat History ──────────────────────────────────────────────────────

def add_chat_message(username: str, role: str, message: str, agent_used: str = "coordinator") -> None:
    """Store chat message in PostgreSQL."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (username, role, message, agent_used) VALUES (%s, %s, %s, %s)",
                (username, role, message, agent_used)
            )
        con.commit()


def get_chat_history(username: str, limit: int = 50) -> list[dict]:
    """Retrieve chat history for the user."""
    with _conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT role, message, agent_used, created_at FROM chat_history WHERE username = %s ORDER BY id ASC LIMIT %s",
                (username, limit)
            )
            rows = cur.fetchall()
    return [{"role": r[0], "message": r[1], "agent_used": r[2], "created_at": r[3]} for r in rows]
