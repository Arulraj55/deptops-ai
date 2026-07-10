"""Sign in page."""

import streamlit as st

from auth import _get_user, _verify
from auth_styles import AUTH_CSS


def render_signin_page():
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown('<div class="auth-logo">🎓 DeptOps AI</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="auth-title">Sign in</div>
    <div class="auth-sub">Enter your username and password.</div>
    """, unsafe_allow_html=True)

    with st.form("signin_form", border=False):
        username = st.text_input("Username", placeholder="Username")
        password = st.text_input("Password", type="password", placeholder="Password")
        
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("Please fill in all fields.")
            else:
                row = _get_user(username.strip())
                if row and _verify(password, row[2]):
                    st.session_state.authenticated = True
                    st.session_state.username = row[0]
                    st.session_state.full_name = row[1] or row[0]
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    st.markdown('<div class="auth-link">Don\'t have an account?</div>', unsafe_allow_html=True)
    if st.button("Create account", use_container_width=True, key="go_to_signup"):
        st.session_state.auth_page = "signup"
        st.rerun()
