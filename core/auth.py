"""Application authentication and role-based access control.

Credentials are intentionally kept out of Git. Configure role-specific PBKDF2
hashes in Streamlit Secrets. The legacy APP_PASSWORD_HASH/SALT pair is retained
as an ADMIN fallback so the existing installation continues to work.
"""
from __future__ import annotations

import hashlib
import hmac

import streamlit as st

ROLES = {
    "ADMIN": "Administrator",
    "CHIEF_OFFICER": "Chief Officer / Master",
    "OFFICER": "Deck Officer",
    "READ_ONLY": "Read Only",
}


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value).strip()


def password_hash(password: str, salt_hex: str, iterations: int = 210_000) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def verify_password(password: str, role: str) -> bool:
    if role not in ROLES:
        return False
    role_hash = _secret(f"APP_{role}_PASSWORD_HASH")
    role_salt = _secret(f"APP_{role}_PASSWORD_SALT")
    if role == "ADMIN" and not (role_hash and role_salt):
        role_hash = _secret("APP_PASSWORD_HASH")
        role_salt = _secret("APP_PASSWORD_SALT")
    if not role_hash or not role_salt:
        return False
    try:
        actual = password_hash(password, role_salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, role_hash)


def configured_roles() -> list[str]:
    roles: list[str] = []
    for role in ROLES:
        if role == "ADMIN" and _secret("APP_PASSWORD_HASH") and _secret("APP_PASSWORD_SALT"):
            roles.append(role)
            continue
        if _secret(f"APP_{role}_PASSWORD_HASH") and _secret(f"APP_{role}_PASSWORD_SALT"):
            roles.append(role)
    return roles


def auth_is_configured() -> bool:
    return bool(configured_roles())


def current_role() -> str | None:
    role = st.session_state.get("user_role")
    return role if role in ROLES else None


def has_role(*allowed_roles: str) -> bool:
    return current_role() in allowed_roles


def require_login() -> bool:
    """Hard gate: unauthenticated users cannot render the application tabs."""
    if st.session_state.get("authenticated", False) and current_role():
        return True

    st.session_state["authenticated"] = False
    st.session_state.pop("user_role", None)
    st.title("🔐 OpenMooring — Access Control")

    if not auth_is_configured():
        st.error("Access control non configurato. Impostare almeno le credenziali Administrator nei Secrets di Streamlit.")
        st.stop()

    available = configured_roles()
    labels = [f"{role} — {ROLES[role]}" for role in available]
    selected_label = st.selectbox("Profilo di accesso", labels)
    selected_role = available[labels.index(selected_label)]

    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Accedi", use_container_width=True)

    if submitted:
        if verify_password(password, selected_role):
            st.session_state["authenticated"] = True
            st.session_state["user_role"] = selected_role
            st.rerun()
        st.error("Password non valida per il profilo selezionato.")

    # Do not allow app.py to continue to tabs or engineering controls.
    st.stop()


def logout_button() -> None:
    role = current_role()
    if role:
        st.sidebar.caption(f"👤 {ROLES[role]}")
    if st.sidebar.button("🔒 Logout", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state.pop("user_role", None)
        st.rerun()
