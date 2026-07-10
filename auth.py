"""
auth.py — DeptOps AI Authentication
Backend: Neon PostgreSQL + bcrypt
"""

import os
import bcrypt
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def _init_db():
    with _get_conn() as conn:
        with conn.cursor() as cur:
            # User accounts
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hod_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    full_name VARCHAR(120),
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            # Analytics datasets — per user
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analytics_files (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) NOT NULL DEFAULT 'legacy',
                    filename VARCHAR(255) NOT NULL,
                    content BYTEA NOT NULL,
                    uploaded_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            # Knowledge documents — per user
            cur.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_files (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) NOT NULL DEFAULT 'legacy',
                    filename VARCHAR(255) NOT NULL,
                    content BYTEA NOT NULL,
                    uploaded_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            # TF-IDF index — per user
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tfidf_index (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) NOT NULL DEFAULT 'legacy',
                    index_json TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()

    # Add username column to existing tables if they were created before this change
    from db_storage import migrate_add_username_columns
    migrate_add_username_columns()


def _get_user(username: str):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, full_name, password_hash FROM hod_users WHERE username=%s",
                (username,),
            )
            return cur.fetchone()


def _create_user(username: str, full_name: str, password: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO hod_users (username, full_name, password_hash) VALUES (%s, %s, %s)",
                (username, full_name, hashed),
            )
        conn.commit()


def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def auth_gate():
    if not st.session_state.get("_db_ready"):
        try:
            _init_db()
            st.session_state._db_ready = True
        except Exception as e:
            st.error(f"Database connection failed: {e}\n\nCheck DATABASE_URL in environment variables.")
            st.stop()

    if st.session_state.get("authenticated"):
        return

    if "auth_page" not in st.session_state:
        st.session_state.auth_page = "signin"

    if st.session_state.auth_page == "signup":
        from signup import render_signup_page
        render_signup_page()
    else:
        from signin import render_signin_page
        render_signin_page()

    st.stop()
