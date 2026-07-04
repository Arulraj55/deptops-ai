"""Sign up page."""

import streamlit as st

from auth import _create_user, _get_user
from auth_styles import AUTH_CSS


def render_signup_page():
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown('<div class="auth-logo">🎓 DeptOps AI</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="auth-title">Sign up</div>
    <div class="auth-sub">Create your account to get started.</div>
    """, unsafe_allow_html=True)

    with st.form("signup_form", border=False):
        full_name = st.text_input("Full name", placeholder="Your name")
        username = st.text_input("Username", placeholder="Username")
        password = st.text_input("Password", type="password", placeholder="Min. 6 characters")
        confirm = st.text_input("Confirm password", type="password", placeholder="Repeat password")
        
        submitted = st.form_submit_button("Sign up", type="primary", use_container_width=True)

        if submitted:
            user = username.strip()
            if not full_name or not user or not password:
                st.error("All fields are required.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif _get_user(user):
                st.error("Username already taken.")
            else:
                try:
                    _create_user(user, full_name.strip(), password)
                    # Automatically log the user in
                    st.session_state.authenticated = True
                    st.session_state.username = user
                    st.session_state.full_name = full_name.strip()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not create account: {e}")

    st.markdown('<div class="auth-link">Already have an account?</div>', unsafe_allow_html=True)
    if st.button("Sign in", use_container_width=True, key="go_to_signin"):
        st.session_state.auth_page = "signin"
        st.rerun()
