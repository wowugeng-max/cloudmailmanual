from __future__ import annotations

import sqlite3
from typing import Dict

from ..config import DB_PATH, DEFAULT_MAX_GENERATE
from .mail_profiles import get_mail_profile_by_id


def get_max_generate_limit() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            )
            """
        )
        row = conn.execute("SELECT v FROM app_settings WHERE k='max_generate_limit'").fetchone()
        if row and str(row[0]).isdigit() and int(row[0]) > 0:
            return int(row[0])

        conn.execute(
            "INSERT OR REPLACE INTO app_settings (k, v) VALUES ('max_generate_limit', ?)",
            (str(DEFAULT_MAX_GENERATE),),
        )
        conn.commit()
        return DEFAULT_MAX_GENERATE

def set_max_generate_limit(value: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (k, v) VALUES ('max_generate_limit', ?)",
            (str(value),),
        )
        conn.commit()

def get_domain_suffix_settings(profile_id: str = "") -> Dict[str, object]:
    profile = get_mail_profile_by_id(profile_id)
    return {
        "options": profile.get("domain_suffix_options", []),
        "default": profile.get("default_domain_suffix", ""),
    }
