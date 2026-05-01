from __future__ import annotations

import functools
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from flask import session, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = "cloudmailmanual.db"
CONFIG_PATH = Path(__file__).parent / "config.json"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db() -> None:
    """Create users table and seed default admin if none exists."""
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

    # Seed default admin if no users exist
    if not get_user_count():
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")

        # Also check config.json for admin credentials
        try:
            import json
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg_user = cfg.get("admin_username", "")
            cfg_pass = cfg.get("admin_password", "")
            if cfg_user and cfg_pass:
                admin_user = cfg_user
                admin_pass = cfg_pass
        except Exception:
            pass

        create_user(admin_user, admin_pass, is_admin=True)


def get_user_count() -> int:
    with _get_db() as conn:
        row = conn.execute("SELECT COUNT(1) FROM users").fetchone()
        return int(row[0]) if row else 0


def get_user(username: str) -> Optional[sqlite3.Row]:
    with _get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def create_user(username: str, password: str, is_admin: bool = False) -> bool:
    try:
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
                (
                    username,
                    generate_password_hash(password, method="pbkdf2:sha256"),
                    1 if is_admin else 0,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(username: str, password: str) -> bool:
    user = get_user(username)
    if not user:
        return False
    return check_password_hash(user["password_hash"], password)


def login_user(username: str) -> None:
    session["user"] = username
    session.permanent = True


def logout_user() -> None:
    session.pop("user", None)


def get_current_user() -> Optional[str]:
    return session.get("user")


def login_required(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            if request.is_json or request.path.startswith("/api/"):
                from flask import jsonify
                return jsonify({"ok": False, "error": "Unauthorized"}), 401
            return redirect(url_for("login_page", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    """Change password for a user. Returns (success, message)."""
    if not verify_user(username, old_password):
        return False, "原密码错误"
    if len(new_password) < 6:
        return False, "新密码至少 6 位"
    with _get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (generate_password_hash(new_password, method="pbkdf2:sha256"), username),
        )
        conn.commit()
    return True, "密码修改成功"
