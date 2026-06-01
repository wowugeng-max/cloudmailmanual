from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Dict, List

from ..config import DB_PATH


def save_verification_query(email: str, detail: Dict[str, str]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO verification_queries (email, code, sender, subject, received_time, queried_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                detail.get("code", ""),
                detail.get("sender", ""),
                detail.get("subject", ""),
                detail.get("received_time", ""),
                now,
            ),
        )
        conn.commit()

def get_verification_query_history(page: int, page_size: int, email: str = "") -> Dict[str, object]:
    offset = (page - 1) * page_size
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if email:
            total = conn.execute(
                "SELECT COUNT(1) FROM verification_queries WHERE email=?",
                (email,),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT id, email, code, sender, subject, received_time, queried_at
                FROM verification_queries
                WHERE email=?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (email, page_size, offset),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(1) FROM verification_queries").fetchone()[0]
            rows = conn.execute(
                """
                SELECT id, email, code, sender, subject, received_time, queried_at
                FROM verification_queries
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()

    items = [dict(r) for r in rows]
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }

def delete_verification_query_history(ids: List[int] | None = None, email: str = "") -> int:
    ids = ids or []
    with sqlite3.connect(DB_PATH) as conn:
        deleted = 0
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            cur = conn.execute(
                f"DELETE FROM verification_queries WHERE id IN ({placeholders})",
                tuple(ids),
            )
            deleted += cur.rowcount
        if email:
            cur = conn.execute("DELETE FROM verification_queries WHERE email=?", (email,))
            deleted += cur.rowcount
        conn.commit()
        return int(deleted)
