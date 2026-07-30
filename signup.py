"""
Sign up page for DeptOps AI.
Allows HOD / Department Coordinators to create an account.
"""

import streamlit as st
from auth import _get_user, _create_user
from auth_styles import AUTH_CSS


def render_signup_page():
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown('<div class="auth-logo">🎓 DeptOps AI</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="auth-title">Create Account</div>
    <div class="auth-sub">Register as Head of Department or Coordinator</div>
    """, unsafe_allow_html=True)

    with st.form("signup_form", border=False):
        full_name = st.text_input("Full Name", placeholder="e.g. Dr. A. Sharma")
        username = st.text_input("Username", placeholder="e.g. hod_cs")
        password = st.text_input("Password", type="password", placeholder="Choose password")
        confirm_password = st.text_input("Confirm Password", type="password", placeholder="Repeat password")

        submitted = st.form_submit_button("Sign up", type="primary", use_container_width=True)

        if submitted:
            if not full_name or not username or not password or not confirm_password:
                st.error("Please fill in all fields.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            elif len(password) < 4:
                st.error("Password should be at least 4 characters long.")
            else:
                existing = _get_user(username.strip())
                if existing:
                    st.error("Username already taken. Please choose another username.")
                else:
                    try:
                        _create_user(username.strip(), full_name.strip(), password)
                        st.success("Account created successfully! Auto-signing in...")
                        st.session_state.authenticated = True
                        st.session_state.username = username.strip()
                        st.session_state.full_name = full_name.strip()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Account creation failed: {exc}")

    st.markdown('<div class="auth-link">Already have an account?</div>', unsafe_allow_html=True)
    if st.button("Sign in", use_container_width=True, key="go_to_signin"):
        st.session_state.auth_page = "signin"
        st.rerun()
