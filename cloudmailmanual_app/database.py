from __future__ import annotations

import sqlite3

from .config import DB_PATH, DEFAULT_MAX_GENERATE


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                app_password TEXT NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                birthday TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                used_at TEXT,
                platforms TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT,
                sender TEXT,
                subject TEXT,
                received_time TEXT,
                queried_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (k, v) VALUES ('max_generate_limit', ?)",
            (str(DEFAULT_MAX_GENERATE),),
        )

        cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        if "used" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN used INTEGER NOT NULL DEFAULT 0")
        if "used_at" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN used_at TEXT")
        if "platforms" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN platforms TEXT NOT NULL DEFAULT ''")

        conn.commit()
