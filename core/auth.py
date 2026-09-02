"""Minimal application authentication with PBKDF2 password hashes.

Credentials are intentionally kept out of Git. Configure APP_PASSWORD_HASH and
APP_PASSWORD_SALT in Streamlit secrets. The password itself is never stored in
this repository.
"""
from __future__ import annotations

import hashlib
import hmac
import os

import streamlit as st


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value).strip()


def password_hash(password: str, salt_hex: str, iterations: int = 210_000) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def verify_password(password: str) -> bool:
    expected = _secret("APP_PASSWORD_HASH")
    salt = _secret("APP_PASSWORD_SALT")
    if not expected or not salt:
        return False
    try:
        actual = password_hash(password, salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def auth_is_configured() -> bool:
    return bool(_secret("APP_PASSWORD_HASH") and _secret("APP_PASSWORD_SALT"))


def require_login() -> bool:
    """Gate the application before any engineering data or UI is rendered."""
    if st.session_state.get("authenticated", False):
        return True

    st.title("🔐 OpenMooring — Access Control")
    if not auth_is_configured():
        st.error(
            "Access control non configurato. Impostare APP_PASSWORD_HASH e "
            "APP_PASSWORD_SALT nei Secrets di Streamlit prima di usare l'app."
        )
        st.stop()

    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Accedi", use_container_width=True)

    if submitted:
        if verify_password(password):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Password non valida.")
    return False


def logout_button() -> None:
    if st.sidebar.button("🔒 Logout", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()
