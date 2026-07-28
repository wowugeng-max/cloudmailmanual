from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple

from ..config import DB_PATH


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_accounts_history(page: int, page_size: int, email_query: str = "") -> Dict[str, object]:
    offset = (page - 1) * page_size
    email_query = str(email_query or "").strip()
    where_sql = ""
    params: tuple[object, ...] = ()
    if email_query:
        where_sql = "WHERE lower(email) LIKE lower(?) ESCAPE '\\'"
        params = (f"%{_escape_like(email_query)}%",)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(f"SELECT COUNT(1) FROM accounts {where_sql}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, email, password, app_password, profile_id, name, age, birthday, created_at,
                   used, used_at, platforms
            FROM accounts
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
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

def mark_account_used(email: str, used: bool = True, platform: str = "") -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, used, platforms FROM accounts WHERE email=? ORDER BY id DESC LIMIT 1",
            (email,),
        ).fetchone()
        if not row:
            return False

        account_id = int(row[0])
        existing_platforms = str(row[2] or "")
        platform_list = [p.strip() for p in existing_platforms.split(",") if p.strip()]

        if platform:
            p = platform.strip()
            if p and p not in platform_list:
                platform_list.append(p)

        used_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if used else None
        conn.execute(
            """
            UPDATE accounts
            SET used=?, used_at=?, platforms=?
            WHERE id=?
            """,
            (
                1 if used else 0,
                used_at,
                ", ".join(platform_list),
                account_id,
            ),
        )
        conn.commit()
        return True

def bulk_delete_accounts(
    mode: str,
    keep_latest: int = 0,
    delete_count: int = 0,
    ids: List[int] | None = None,
) -> Tuple[int, int]:
    """批量删除本地 accounts 记录。

    Returns:
        (deleted_rows, remaining_rows)
    """
    with sqlite3.connect(DB_PATH) as conn:
        total = int(conn.execute("SELECT COUNT(1) FROM accounts").fetchone()[0])
        deleted = 0

        if mode == "all":
            conn.execute("DELETE FROM accounts")
            deleted = total
        elif mode == "selected":
            selected_ids = sorted({int(x) for x in (ids or []) if int(x) > 0})
            if selected_ids:
                placeholders = ",".join(["?"] * len(selected_ids))
                cur = conn.execute(
                    f"DELETE FROM accounts WHERE id IN ({placeholders})",
                    tuple(selected_ids),
                )
                deleted = int(cur.rowcount)
        elif mode == "keep_latest":
            keep_latest = max(0, int(keep_latest or 0))
            if keep_latest < total:
                conn.execute(
                    """
                    DELETE FROM accounts
                    WHERE id NOT IN (
                        SELECT id FROM accounts
                        ORDER BY id DESC
                        LIMIT ?
                    )
                    """,
                    (keep_latest,),
                )
                deleted = total - keep_latest
        elif mode == "delete_oldest":
            delete_count = max(0, int(delete_count or 0))
            if delete_count > 0:
                conn.execute(
                    """
                    DELETE FROM accounts
                    WHERE id IN (
                        SELECT id FROM accounts
                        ORDER BY id ASC
                        LIMIT ?
                    )
                    """,
                    (delete_count,),
                )
                deleted = min(delete_count, total)
        else:
            raise ValueError("mode 必须是 all / keep_latest / delete_oldest / selected")

        conn.commit()
        remaining = int(conn.execute("SELECT COUNT(1) FROM accounts").fetchone()[0])

    return deleted, remaining

def save_accounts(rows: List[Dict[str, str | int]]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO accounts (email, password, app_password, profile_id, name, age, birthday, created_at, used, used_at, platforms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, '')
            """,
            [
                (
                    str(r.get("email", "")),
                    str(r.get("password", "")),
                    str(r.get("app_password", "")),
                    str(r.get("profile_id", "")),
                    str(r.get("name", "")),
                    int(r.get("age", 0) or 0),
                    str(r.get("birthday", "")),
                    now,
                )
                for r in rows
            ],
        )
        conn.commit()

def save_accounts_with_meta(rows: List[Dict[str, object]]) -> Tuple[int, int]:
    imported = 0
    skipped = 0

    def _to_int(v: object, default: int = 0) -> int:
        try:
            return int(v)  # type: ignore[arg-type]
        except Exception:
            return default

    def _norm_time(v: object) -> str | None:
        s = str(v or "").strip()
        return s or None

    with sqlite3.connect(DB_PATH) as conn:
        for r in rows:
            email = str(r.get("email", "") or "").strip()
            if not email or "@" not in email:
                skipped += 1
                continue

            exists = conn.execute(
                "SELECT 1 FROM accounts WHERE email=? LIMIT 1",
                (email,),
            ).fetchone()
            if exists:
                skipped += 1
                continue

            password = str(r.get("password", "") or "").strip()
            app_password = str(r.get("app_password", "") or "").strip()
            profile_id = str(r.get("profile_id", "") or "").strip()
            name = str(r.get("name", "") or "").strip() or "Unknown"
            age = _to_int(r.get("age", 0), 0)
            birthday = str(r.get("birthday", "") or "").strip() or "1970-01-01"
            created_at = _norm_time(r.get("created_at")) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            used = 1 if str(r.get("used", "0")).strip() in {"1", "true", "True", "yes", "YES", "已使用", "正在使用"} else 0
            used_at = _norm_time(r.get("used_at"))
            platforms = str(r.get("platforms", "") or "").strip()

            conn.execute(
                """
                INSERT INTO accounts (email, password, app_password, profile_id, name, age, birthday, created_at, used, used_at, platforms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email, password, app_password, profile_id, name, age, birthday, created_at, used, used_at, platforms),
            )
            imported += 1

        conn.commit()

    return imported, skipped
