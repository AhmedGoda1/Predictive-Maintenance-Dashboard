"""Login: who is using the dashboard decides what they see.

    admin        the full dashboard (fleet, asset detail, live data, dispatching work orders)
    maintenance  only the work orders that are still open

Accounts live in the app's secrets (on Streamlit Cloud: Manage app → Settings → Secrets; locally:
.streamlit/secrets.toml, which is not committed):

    [users.alice]
    password = "pbkdf2_sha256$600000$...$..."     # from: python scripts/hash_password.py
    role = "admin"

    [users.tech]
    password = "pbkdf2_sha256$600000$...$..."
    role = "maintenance"

A plain-text password is accepted too, but a hash keeps the password out of anyone's sight who can read the
secrets. Without any [users] the dashboard asks for no login and everyone is admin, as before; the sidebar
says so.
"""
import hashlib
import hmac
import secrets
import time

import streamlit as st

ROLES = ("admin", "maintenance")
HASH_PREFIX = "pbkdf2_sha256"
ITERATIONS = 600_000


def hash_password(password: str, iterations: int = ITERATIONS, salt: str = None) -> str:
    """A string to put in the secrets instead of the password: pbkdf2_sha256$<iterations>$<salt>$<hex digest>."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"{HASH_PREFIX}${iterations}${salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    """Compares a typed password with a stored hash (or plain-text password) in constant time."""
    if not isinstance(stored, str) or not stored:
        return False
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == HASH_PREFIX:
        try:
            iterations = int(parts[1])
        except ValueError:
            return False
        return hmac.compare_digest(hash_password(password, iterations, parts[2]).encode(), stored.encode())
    return hmac.compare_digest(password.encode(), stored.encode())


def configured_users() -> dict:
    """{username: {"password": ..., "role": ...}} from the secrets; empty when none are configured."""
    try:
        users = st.secrets.get("users") or {}
    except Exception:                    # no secrets file at all (local runs, tests)
        return {}
    return {str(name): dict(entry) for name, entry in users.items() if hasattr(entry, "get")}


def authenticate(username: str, password: str, users: dict):
    """The user's role when the name and password match an account with a known role, else None."""
    entry = users.get((username or "").strip())
    if entry is None or entry.get("role") not in ROLES:
        check_password(password or "", hash_password("", 1))        # same work whether the name exists or not
        return None
    return entry["role"] if check_password(password or "", entry.get("password")) else None


def current_user():
    """{"name", "role"} of whoever is logged in, or None."""
    return st.session_state.get("auth_user")


def require_login() -> dict:
    """Returns the logged-in user; otherwise shows the login form and stops the script.

    With no accounts configured everyone is an admin, so a fresh checkout still opens straight away.
    """
    users = configured_users()
    if not users:
        return {"name": None, "role": "admin"}
    user = current_user()
    if user and user["name"] in users and users[user["name"]].get("role") == user["role"]:
        return user                       # still a valid account (secrets can change while a session is open)
    st.session_state.pop("auth_user", None)
    _login_form(users)
    st.stop()


def _login_form(users: dict) -> None:
    _, middle, _ = st.columns([1, 1.2, 1])
    with middle:
        st.title("🛠️ Maintenance Portal")
        with st.form("login"):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", width="stretch")
        if submitted:
            role = authenticate(username, password, users)
            if role is None:
                time.sleep(1)             # slows down guessing
                st.error("Wrong username or password.")
            else:
                st.session_state["auth_user"] = {"name": username.strip(), "role": role}
                st.session_state.pop("login_password", None)
                st.rerun()


def sidebar(user: dict) -> None:
    """Who is logged in, and the logout button."""
    if user["name"] is None:
        st.sidebar.caption("🔓 No login is configured, so everyone sees everything. Add accounts under [users] "
                           "in the app's secrets to require one (see docs/LOGIN.md).")
        return
    st.sidebar.caption(f"Logged in as **{user['name']}** ({user['role']})")
    if st.sidebar.button("Log out", key="logout", width="stretch"):
        for key in ("auth_user", "view", "selected_asset"):
            st.session_state.pop(key, None)
        st.rerun()
