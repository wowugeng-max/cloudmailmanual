from __future__ import annotations

import csv
import io
import json
import random
import secrets
import sqlite3
import string
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, jsonify, render_template_string, request, send_file

from cloud_mail_client import CloudMailClient

app = Flask(__name__)

DB_PATH = "cloudmailmanual.db"
DEFAULT_MAX_GENERATE = 50
CONFIG_PATH = Path(__file__).parent / "config.json"


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


def get_domain_suffix_settings() -> Dict[str, object]:
    default_options: List[str] = []
    default_suffix = ""

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    admin_email = str(cfg.get("cloud_mail_admin_email", "") or "").strip().lower()
    admin_domain = admin_email.split("@")[-1] if "@" in admin_email else ""

    options_raw = cfg.get("domain_suffix_options", [])
    options: List[str] = []
    if isinstance(options_raw, list):
        for x in options_raw:
            s = str(x or "").strip().lower().strip(".")
            if s and "." in s and s not in options:
                options.append(s)

    cfg_default = str(cfg.get("default_domain_suffix", "") or "").strip().lower().strip(".")
    if cfg_default and "." in cfg_default:
        default_suffix = cfg_default

    if admin_domain and admin_domain not in options:
        options.insert(0, admin_domain)

    if not options and admin_domain:
        options = [admin_domain]

    if not default_suffix:
        default_suffix = options[0] if options else ""

    return {
        "options": options,
        "default": default_suffix,
    }


def get_accounts_history(page: int, page_size: int) -> Dict[str, object]:
    offset = (page - 1) * page_size
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(1) FROM accounts").fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, email, password, app_password, name, age, birthday, created_at,
                   used, used_at, platforms
            FROM accounts
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


def bulk_delete_accounts(mode: str, keep_latest: int = 0, delete_count: int = 0) -> Tuple[int, int]:
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
            raise ValueError("mode 必须是 all / keep_latest / delete_oldest")

        conn.commit()
        remaining = int(conn.execute("SELECT COUNT(1) FROM accounts").fetchone()[0])

    return deleted, remaining


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


def save_accounts(rows: List[Dict[str, str | int]]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO accounts (email, password, app_password, name, age, birthday, created_at, used, used_at, platforms)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, '')
            """,
            [
                (
                    str(r.get("email", "")),
                    str(r.get("password", "")),
                    str(r.get("app_password", "")),
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
            name = str(r.get("name", "") or "").strip() or "Unknown"
            age = _to_int(r.get("age", 0), 0)
            birthday = str(r.get("birthday", "") or "").strip() or "1970-01-01"
            created_at = _norm_time(r.get("created_at")) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            used = 1 if str(r.get("used", "0")).strip() in {"1", "true", "True", "yes", "YES", "已使用", "正在使用"} else 0
            used_at = _norm_time(r.get("used_at"))
            platforms = str(r.get("platforms", "") or "").strip()

            conn.execute(
                """
                INSERT INTO accounts (email, password, app_password, name, age, birthday, created_at, used, used_at, platforms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email, password, app_password, name, age, birthday, created_at, used, used_at, platforms),
            )
            imported += 1

        conn.commit()

    return imported, skipped


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


def generate_profile() -> Dict[str, str | int]:
    first_names = [
        "James", "Robert", "John", "Michael", "David", "William", "Richard",
        "Mary", "Jennifer", "Linda", "Elizabeth", "Susan", "Jessica", "Sarah",
        "Emily", "Emma", "Olivia", "Sophia", "Liam", "Noah", "Oliver", "Ethan",
    ]
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Martin",
    ]

    today = date.today()
    age = random.randint(18, 55)
    start = today.replace(year=today.year - age - 1) + timedelta(days=1)
    end = today.replace(year=today.year - age)
    birthday = start + timedelta(days=random.randint(0, (end - start).days))

    return {
        "name": f"{random.choice(first_names)} {random.choice(last_names)}",
        "age": age,
        "birthday": birthday.isoformat(),
    }


def generate_app_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def batch_register(count: int, domain_suffix: str = "") -> List[Dict[str, str | int]]:
    client = CloudMailClient()
    results: List[Dict[str, str | int]] = []
    for _ in range(count):
        email, password, _ = client.create_temp_email(domain_suffix=domain_suffix)
        profile = generate_profile()
        results.append(
            {
                "email": email,
                "password": password,
                "app_password": generate_app_password(12),
                "name": profile["name"],
                "age": profile["age"],
                "birthday": profile["birthday"],
            }
        )
    return results


def _build_domain_body_candidates(industry: str = "general") -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
    base_prefixes = [
        "smart", "next", "prime", "urban", "cloud", "nova", "rapid", "green", "bright", "alpha",
        "blue", "gold", "meta", "micro", "auto", "vital", "global", "fresh", "quick", "stellar",
    ]
    base_cores = [
        "mail", "tech", "data", "labs", "works", "flow", "logic", "hub", "zone", "link",
        "point", "base", "stack", "forge", "nova", "net", "signal", "boost", "pulse", "craft",
    ]
    base_suffixes = [
        "pro", "online", "group", "digital", "center", "studio", "systems", "ai", "world", "space",
        "direct", "solutions", "network", "plus", "core", "team", "service", "media", "hq", "one",
    ]

    industry_map = {
        "tech": {
            "prefixes": ["cloud", "byte", "quant", "neuro", "cyber", "vector", "core", "data"],
            "cores": ["stack", "compute", "signal", "matrix", "kernel", "logic", "node", "engine"],
            "suffixes": ["labs", "tech", "systems", "ai", "works", "dev", "ops", "soft"],
        },
        "ecommerce": {
            "prefixes": ["shop", "deal", "cart", "easy", "smart", "quick", "buy", "best"],
            "cores": ["market", "store", "mall", "sale", "goods", "price", "order", "retail"],
            "suffixes": ["hub", "online", "plus", "direct", "zone", "center", "mart", "world"],
        },
        "media": {
            "prefixes": ["news", "story", "daily", "fresh", "trend", "buzz", "topic", "live"],
            "cores": ["media", "press", "stream", "voice", "view", "times", "post", "focus"],
            "suffixes": ["now", "network", "studio", "channel", "world", "hub", "today", "space"],
        },
        "tools": {
            "prefixes": ["tool", "build", "maker", "fix", "fast", "pro", "task", "util"],
            "cores": ["kit", "works", "suite", "helper", "craft", "forge", "desk", "lab"],
            "suffixes": ["pro", "plus", "center", "base", "flow", "hub", "one", "team"],
        },
        "mail": {
            "prefixes": ["mail", "inbox", "post", "prime", "secure", "swift", "verify", "token"],
            "cores": ["mail", "inbox", "mx", "code", "verify", "pass", "auth", "message"],
            "suffixes": ["mail", "box", "post", "hub", "center", "works", "service", "direct"],
        },
    }

    picked = industry_map.get(industry, None)
    if picked:
        prefixes = base_prefixes + picked["prefixes"]
        cores = base_cores + picked["cores"]
        suffixes = base_suffixes + picked["suffixes"]
    else:
        prefixes = base_prefixes
        cores = base_cores
        suffixes = base_suffixes

    short_parts = [
        "go", "my", "up", "on", "get", "try", "top", "fast", "new", "best",
    ]
    vowels = ["a", "e", "i", "o", "u"]
    return prefixes, cores, suffixes, short_parts, vowels


def generate_domain_bodies(
    count: int,
    industry: str = "general",
    avoid_digits: bool = False,
    require_digits: bool = False,
    allow_hyphen: bool = True,
) -> List[str]:
    prefixes, cores, suffixes, short_parts, vowels = _build_domain_body_candidates(industry)

    # 为了提升 .com 可注册概率：加入“好记但不常见”的可读伪词和短尾巴
    brand_roots = [
        "nexa", "verio", "pulza", "maily", "inbix", "zenqo", "orvix", "qinor", "levra", "noviq",
        "virel", "orbix", "mailo", "trivo", "kivra", "velto", "dovra", "zynex", "ravio", "lumix",
    ]
    brand_tails = ["hq", "lab", "base", "core", "zone", "hub", "works", "center", "plus", "one"]

    def rand_digits() -> str:
        if avoid_digits:
            return ""
        if require_digits:
            return str(random.randint(2, 9999))
        if random.random() < 0.72:
            return ""
        return str(random.randint(2, 9999))

    def sanitize(name: str) -> str:
        s = "".join(ch for ch in name.lower() if ch.isalnum() or ch == "-")
        if not allow_hyphen:
            s = s.replace("-", "")
        s = s.strip("-")
        while "--" in s:
            s = s.replace("--", "-")
        if len(s) < 4:
            s += random.choice(cores)
        return s[:30]

    generated: List[str] = []
    seen = set()

    max_round = max(800, count * 60)
    for _ in range(max_round):
        style = random.randint(1, 10)
        if style == 1:
            body = f"{random.choice(prefixes)}{random.choice(cores)}{rand_digits()}"
        elif style == 2:
            body = f"{random.choice(cores)}{random.choice(suffixes)}{rand_digits()}"
        elif style == 3:
            body = f"{random.choice(prefixes)}-{random.choice(cores)}{rand_digits()}" if allow_hyphen else f"{random.choice(prefixes)}{random.choice(cores)}{rand_digits()}"
        elif style == 4:
            body = f"{random.choice(short_parts)}{random.choice(cores)}{rand_digits()}"
        elif style == 5:
            body = f"{random.choice(prefixes)}{random.choice(vowels)}{random.choice(cores)}{rand_digits() if require_digits else ''}"
        elif style == 6:
            body = f"{random.choice(cores)}-{random.choice(suffixes)}{rand_digits()}" if allow_hyphen else f"{random.choice(cores)}{random.choice(suffixes)}{rand_digits()}"
        elif style == 7:
            body = f"{random.choice(prefixes)}{random.choice(cores)}{random.choice(suffixes)}{rand_digits() if require_digits else ''}"
        elif style == 8:
            body = f"{random.choice(brand_roots)}{random.choice(cores)}{random.choice(brand_tails)}"
        elif style == 9:
            body = f"{random.choice(brand_roots)}{random.choice(brand_tails)}{rand_digits() if not avoid_digits else ''}"
        else:
            # 邮件业务风格下提高“可记忆 + 非高占用裸词”比例
            if industry == "mail":
                mail_cores = ["mail", "inbox", "mx", "verify", "code", "auth"]
                body = f"{random.choice(brand_roots)}{random.choice(mail_cores)}{random.choice(brand_tails)}"
            else:
                body = f"{random.choice(brand_roots)}{random.choice(cores)}{random.choice(brand_tails)}"

        body = sanitize(body)
        if not body:
            continue
        if require_digits and not any(ch.isdigit() for ch in body):
            continue
        if avoid_digits and any(ch.isdigit() for ch in body):
            continue

        if body not in seen:
            seen.add(body)
            generated.append(body)
            if len(generated) >= count:
                break

    return generated


def generate_third_level_subdomains(
    domain_bodies: List[str],
    count: int,
    industry: str = "general",
    avoid_digits: bool = False,
) -> List[str]:
    lead_parts_map = {
        "general": ["app", "api", "mail", "auth", "cdn", "img", "m", "go", "id", "user"],
        "tech": ["api", "dev", "edge", "node", "git", "docs", "app", "auth", "ops", "cloud"],
        "ecommerce": ["shop", "pay", "order", "cart", "deal", "promo", "img", "m", "user", "app"],
        "media": ["news", "live", "video", "stream", "post", "topic", "img", "cdn", "m", "app"],
        "tools": ["tool", "desk", "work", "task", "kit", "api", "app", "sync", "docs", "go"],
        "mail": ["mail", "mx", "smtp", "inbox", "verify", "code", "auth", "token", "secure", "post"],
    }
    mid_parts = ["svc", "core", "hub", "data", "edge", "sys", "cloud", "web", "net", "center"]

    first_pool = lead_parts_map.get(industry, lead_parts_map["general"])

    def maybe_num(token: str) -> str:
        if avoid_digits:
            return token
        if random.random() < 0.25:
            return f"{token}{random.randint(1, 99)}"
        return token

    result: List[str] = []
    for body in domain_bodies[: max(0, count)]:
        a = maybe_num(random.choice(first_pool))
        b = maybe_num(random.choice(mid_parts))
        # 按你的要求：基于当前主体，且不带真实域名后缀（如 .com）
        sub = f"{a}.{b}.{body}"
        result.append(sub)

    return result


HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cloud Mail 批量注册</title>
  <style>
    :root {
      --bg:#0b1020; --card:#141b34; --text:#e8ecff; --muted:#a8b0d3;
      --primary:#6b8cff; --ok:#19c37d; --danger:#ff6b6b; --warning:#ffb020;
    }
    body { margin:0; font-family:Inter,Segoe UI,Arial,sans-serif; background:linear-gradient(135deg,#0b1020,#111a3a); color:var(--text); }
    .wrap { max-width:1200px; margin:32px auto; padding:0 16px 24px; }
    .topbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
    .brand { font-size:24px; font-weight:700; letter-spacing:.2px; }
    .sub { color:var(--muted); font-size:13px; }
    .grid { display:grid; grid-template-columns:1fr; gap:14px; }
    .tabs { display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap; }
    .tab-btn { background:#23305a; color:#d9e2ff; border:1px solid rgba(255,255,255,.12); }
    .tab-btn.active { background:var(--primary); color:#fff; }
    .tab-pane { display:none; }
    .tab-pane.active { display:block; }
    .card { background:rgba(20,27,52,.92); border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:18px; box-shadow:0 10px 30px rgba(0,0,0,.32); }
    h1, h2 { margin:0 0 6px; }
    h1 { font-size:26px; }
    h2 { font-size:18px; }
    p { margin:0 0 14px; color:var(--muted); }
    .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    input, select {
      width:220px; padding:9px 11px; border-radius:9px;
      border:1px solid rgba(255,255,255,.16); background:#0f1530; color:var(--text);
    }
    #count { width:120px; }
    button { padding:9px 13px; border:0; border-radius:9px; cursor:pointer; color:white; background:var(--primary); font-weight:600; }
    button:disabled { opacity:.6; cursor:not-allowed; }
    .btn-secondary { background:#2f3b67; }
    .btn-danger { background:#a83333; }
    .btn-warning { background:#855d14; }
    .status { margin-top:10px; color:var(--muted); }
    .status.ok { color:var(--ok); }
    .status.err { color:var(--danger); }
    table { width:100%; border-collapse:collapse; margin-top:14px; font-size:13px; }
    #historyTable tr.in-use-row td { background: rgba(25, 195, 125, 0.14); }
    th, td { border-bottom:1px solid rgba(255,255,255,.10); text-align:left; padding:9px 7px; }
    th { color:#cdd6ff; font-weight:700; position:sticky; top:0; background:#1a2347; }
    .tools { margin-top:10px; }
    .section-title { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
    table.copy-table td[data-copy] { cursor: copy; user-select: none; }
    table.copy-table td[data-copy]:hover { background: rgba(107, 140, 255, 0.16); }
    #copyToast {
      position: fixed;
      right: 16px;
      bottom: 16px;
      background: rgba(25, 195, 125, 0.95);
      color: #fff;
      padding: 10px 12px;
      border-radius: 8px;
      font-size: 13px;
      display: none;
      z-index: 9999;
      box-shadow: 0 8px 20px rgba(0,0,0,.35);
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div id="copyToast"></div>
    <div class="topbar">
      <div>
        <div class="brand">Cloud Mail Console</div>
        <div class="sub">批量创建、验证码查询、历史管理（SQLite 持久化）</div>
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" id="tabBtn-register" onclick="switchTab('register')">批量注册</button>
      <button class="tab-btn" id="tabBtn-query-history" onclick="switchTab('query-history')">查询邮箱验证码和账号历史</button>
      <button class="tab-btn" id="tabBtn-query-log" onclick="switchTab('query-log')">验证码查询历史</button>
      <button class="tab-btn" id="tabBtn-query-only" onclick="switchTab('query-only')">查询邮箱验证码</button>
      <button class="tab-btn" id="tabBtn-domain-body" onclick="switchTab('domain-body')">生成域名主体</button>
    </div>

    <div class="grid">
    <div class="tab-pane active" id="tab-register">
    <div class="card">
      <h1>批量注册</h1>
      <p>输入数量，一键创建邮箱并生成资料（邮箱密码、应用密码、姓名、年龄、生日）。</p>
      <div class="row">
        <label for="count">数量：</label>
        <input id="count" type="number" min="1" max="200" value="5" />
        <label for="registerDomainSuffix">邮箱后缀：</label>
        <select id="registerDomainSuffix" style="width:260px;"></select>
        <button id="startBtn" onclick="startRegister()">开始注册</button>
        <button id="downloadBtn" class="btn-secondary" onclick="downloadCsv()" disabled>下载 CSV</button>
      </div>
      <div class="row" style="margin-top:10px;">
        <label for="maxGenerateLimit">一次最大生成数量：</label>
        <input id="maxGenerateLimit" type="number" min="1" max="500" value="50" />
        <button id="saveLimitBtn" class="btn-secondary" onclick="saveMaxLimit()">保存限制</button>
      </div>
      <div id="status" class="status"></div>
      <div class="tools">
        <table id="resultTable" class="copy-table" style="display:none;">
          <thead>
            <tr>
              <th>#</th>
              <th>邮箱</th>
              <th>邮箱密码</th>
              <th>应用密码</th>
              <th>姓名</th>
              <th>年龄</th>
              <th>生日</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
    </div>

    <div class="tab-pane" id="tab-query-history">
    <div class="card">
      <h2>查询邮箱验证码</h2>
      <p>输入已创建邮箱，点击查询验证码。</p>
      <div class="row">
        <input id="queryEmail" type="email" placeholder="例如: test@example.com" />
        <input id="queryPlatform" type="text" placeholder="平台名（如 Grok / OpenAI）" />
        <button id="queryBtn" onclick="queryCode()">查询验证码</button>
      </div>
      <div id="queryStatus" class="status"></div>
      <div class="tools">
        <table id="queryResultTable" class="copy-table" style="display:none; margin-top:10px;">
          <thead>
            <tr>
              <th>验证码</th>
              <th>发件人</th>
              <th>主题</th>
              <th>收件时间</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>


    <div class="card">
      <div class="section-title">
        <h2>历史记录</h2>
      </div>
      <p>查看已生成账号记录（支持分页）并批量清理，防止数据过多。</p>

      <div class="row">
        <label for="historyPageSize">每页：</label>
        <input id="historyPageSize" type="number" min="5" max="200" value="20" />
        <button class="btn-secondary" onclick="loadHistory(1)">刷新</button>
        <button class="btn-secondary" onclick="exportAccountsHistoryCsv()">导出账号历史 CSV</button>
        <button class="btn-secondary" onclick="triggerImportAccountsCsv()">导入账号历史 CSV</button>
        <input id="importAccountsFile" type="file" accept=".csv,text/csv" style="display:none;" onchange="importAccountsCsvChanged(event)" />
      </div>

      <div class="row" style="margin-top:10px;">
        <label for="deleteMode">批量删除：</label>
        <select id="deleteMode" onchange="onDeleteModeChange()">
          <option value="delete_oldest">删除最旧 N 条</option>
          <option value="keep_latest">仅保留最新 N 条</option>
          <option value="all">删除全部</option>
        </select>
        <input id="deleteValue" type="number" min="1" value="100" placeholder="数量" />
        <button id="deleteBtn" class="btn-danger" onclick="bulkDeleteAccounts()">执行删除</button>
      </div>

      <div id="historyStatus" class="status"></div>
      <div class="tools">
        <table id="historyTable" class="copy-table" style="display:none; margin-top:10px;">
          <thead>
            <tr>
              <th>ID</th>
              <th>邮箱</th>
              <th>邮箱密码</th>
              <th>应用密码</th>
              <th>姓名</th>
              <th>年龄</th>
              <th>生日</th>
              <th>状态</th>
              <th>平台</th>
              <th>使用时间</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="row" style="margin-top:10px;">
        <button id="prevHistoryBtn" class="btn-secondary" onclick="prevHistoryPage()">上一页</button>
        <button id="nextHistoryBtn" class="btn-secondary" onclick="nextHistoryPage()">下一页</button>
      </div>
    </div>
    </div>

    <div class="tab-pane" id="tab-query-log">
      <div class="card">
        <div class="section-title">
          <h2>验证码查询历史</h2>
        </div>
        <p>查看验证码查询记录（支持分页）。</p>
        <div class="row">
          <label for="queryHistoryPageSize">每页：</label>
          <input id="queryHistoryPageSize" type="number" min="5" max="200" value="20" />
          <input id="queryHistoryEmailFilter" type="email" placeholder="按邮箱筛选（可选）" />
          <button class="btn-secondary" onclick="loadQueryHistory(1)">刷新</button>
        </div>
        <div class="row" style="margin-top:10px;">
          <input id="queryHistoryDeleteIds" type="text" placeholder="删除ID（逗号分隔）" />
          <button id="deleteQuerySelectedBtn" class="btn-warning" onclick="deleteSelectedQueryHistory()">删除选中ID</button>
          <button id="deleteQueryByEmailBtn" class="btn-danger" onclick="deleteQueryHistoryByEmail()">按邮箱删除</button>
        </div>
        <div id="queryHistoryStatus" class="status"></div>
        <div class="tools">
          <table id="queryHistoryTable" class="copy-table" style="display:none; margin-top:10px;">
            <thead>
              <tr>
                <th><input type="checkbox" id="queryHistoryCheckAll" onclick="toggleAllQueryHistoryChecks(this)" /></th>
                <th>ID</th>
                <th>邮箱</th>
                <th>验证码</th>
                <th>发件人</th>
                <th>主题</th>
                <th>收件时间</th>
                <th>查询时间</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
        <div class="row" style="margin-top:10px;">
          <button id="prevQueryHistoryBtn" class="btn-secondary" onclick="prevQueryHistoryPage()">上一页</button>
          <button id="nextQueryHistoryBtn" class="btn-secondary" onclick="nextQueryHistoryPage()">下一页</button>
        </div>
      </div>
    </div>

    <div class="tab-pane" id="tab-query-only">
      <div class="card">
        <h2>查询邮箱验证码（独立模式）</h2>
        <p>仅做验证码查询，不展示历史管理模块。</p>
        <div class="row">
          <input id="queryOnlyEmail" type="email" placeholder="例如: test@example.com" />
          <input id="queryOnlyPlatform" type="text" placeholder="平台名（如 Grok / OpenAI）" />
          <button id="queryOnlyBtn" onclick="queryCodeOnly()">查询验证码</button>
        </div>
        <div id="queryOnlyStatus" class="status"></div>
        <div class="tools">
          <table id="queryOnlyResultTable" class="copy-table" style="display:none; margin-top:10px;">
            <thead>
              <tr>
                <th>验证码</th>
                <th>发件人</th>
                <th>主题</th>
                <th>收件时间</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="tab-pane" id="tab-domain-body">
      <div class="card">
        <h2>生成真实风格的域名主体</h2>
        <p>批量生成用于注册时更自然的域名前缀（不含后缀，如 .com）。点击任意单元格可复制。</p>
        <div class="row">
          <label for="domainBodyCount">数量：</label>
          <input id="domainBodyCount" type="number" min="1" max="500" value="30" />
          <label for="domainBodyIndustry">行业风格：</label>
          <select id="domainBodyIndustry" style="width:180px;">
            <option value="general">通用</option>
            <option value="tech">科技</option>
            <option value="ecommerce">电商</option>
            <option value="media">媒体</option>
            <option value="tools">工具</option>
            <option value="mail">邮件业务</option>
          </select>
          <button id="domainBodyBtn" onclick="generateDomainBodies()">生成</button>
        </div>
        <div class="row" style="margin-top:8px;">
          <label style="display:flex;align-items:center;gap:6px;width:auto;">
            <input id="domainBodyAvoidDigits" type="checkbox" style="width:auto;" />
            避免数字
          </label>
          <label style="display:flex;align-items:center;gap:6px;width:auto;">
            <input id="domainBodyRequireDigits" type="checkbox" style="width:auto;" />
            必含数字
          </label>
          <label style="display:flex;align-items:center;gap:6px;width:auto;">
            <input id="domainBodyAllowHyphen" type="checkbox" style="width:auto;" checked />
            允许连字符 (-)
          </label>
          <label style="display:flex;align-items:center;gap:6px;width:auto;">
            <input id="domainBodyRecommendSubdomain" type="checkbox" style="width:auto;" checked />
            生成三级子域推荐
          </label>
        </div>
        <div id="domainBodyStatus" class="status"></div>
        <div class="tools">
          <table id="domainBodyTable" class="copy-table" style="display:none; margin-top:10px;">
            <thead>
              <tr>
                <th>#</th>
                <th>域名主体</th>
                <th>三级子域推荐</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>
    </div>
  </div>

<script>
let latestRows = [];
let historyPage = 1;
let historyTotalPages = 1;
let queryHistoryPage = 1;
let queryHistoryTotalPages = 1;
let currentInUseEmail = '';

async function loadMaxLimit() {
  try {
    const res = await fetch('/api/settings/max-generate-limit');
    const data = await res.json();
    if (res.ok && data.ok) {
      document.getElementById('maxGenerateLimit').value = data.max_generate_limit;
      document.getElementById('count').max = data.max_generate_limit;
    }
  } catch (_) {}
}

async function loadDomainSuffixOptions() {
  const select = document.getElementById('registerDomainSuffix');
  if (!select) return;

  try {
    const res = await fetch('/api/settings/domain-suffix-options');
    const data = await res.json();
    if (!res.ok || !data.ok) return;

    select.innerHTML = '';
    (data.options || []).forEach((opt) => {
      const option = document.createElement('option');
      option.value = opt;
      option.textContent = opt;
      if (opt === data.default) option.selected = true;
      select.appendChild(option);
    });
  } catch (_) {}
}

async function saveMaxLimit() {
  const status = document.getElementById('status');
  const value = Number(document.getElementById('maxGenerateLimit').value || 0);
  if (!value || value < 1 || value > 500) {
    status.className = 'status err';
    status.textContent = '一次最大生成数量必须在 1-500';
    return;
  }

  try {
    const res = await fetch('/api/settings/max-generate-limit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '保存失败');
    }
    document.getElementById('count').max = data.max_generate_limit;
    status.className = 'status ok';
    status.textContent = `一次最大生成数量已更新为 ${data.max_generate_limit}`;
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  }
}

async function startRegister() {
  const count = Number(document.getElementById('count').value || 0);
  const domainSuffix = String(document.getElementById('registerDomainSuffix').value || '').trim();
  const status = document.getElementById('status');
  const btn = document.getElementById('startBtn');
  const downloadBtn = document.getElementById('downloadBtn');

  if (!count || count < 1) {
    status.className = 'status err';
    status.textContent = '请输入大于 0 的数量';
    return;
  }

  if (domainSuffix && !domainSuffix.includes('.')) {
    status.className = 'status err';
    status.textContent = '邮箱后缀格式不正确，例如 mailyplus.com';
    return;
  }

  btn.disabled = true;
  downloadBtn.disabled = true;
  status.className = 'status';
  status.textContent = '正在注册，请稍候...';

  try {
    const res = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count, domain_suffix: domainSuffix })
    });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || '注册失败');
    }

    latestRows = data.data || [];
    renderTable(latestRows);
    status.className = 'status ok';
    status.textContent = `完成：成功生成 ${latestRows.length} 条`;
    downloadBtn.disabled = latestRows.length === 0;
    loadHistory(1);
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  } finally {
    btn.disabled = false;
  }
}

async function queryCodeCommon(email, platform, statusEl, btnEl, tableEl, refreshAccountHistory = false) {
  const status = statusEl;
  const btn = btnEl;
  const table = tableEl;
  const tbody = table.querySelector('tbody');

  tbody.innerHTML = '';
  table.style.display = 'none';

  if (!email || !email.includes('@')) {
    status.className = 'status err';
    status.textContent = '请输入有效邮箱地址';
    return;
  }

  btn.disabled = true;
  status.className = 'status';
  status.textContent = '正在查询验证码...';

  try {
    const res = await fetch('/api/query-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, platform })
    });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || '查询失败');
    }

    if (data.code) {
      status.className = 'status ok';
      status.textContent = `邮箱 ${email} 已查询到验证码`;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td data-copy="${data.code || ''}">${data.code || ''}</td>
        <td data-copy="${data.sender || ''}">${data.sender || ''}</td>
        <td data-copy="${data.subject || ''}">${data.subject || ''}</td>
        <td data-copy="${data.received_time || ''}">${data.received_time || ''}</td>
      `;
      tbody.appendChild(tr);
      table.style.display = 'table';
      bindCopyHandlers();
      loadQueryHistory(1);
      if (refreshAccountHistory) loadHistory(historyPage);
    } else {
      status.className = 'status';
      status.textContent = `邮箱 ${email} 暂未查询到验证码`;
      if (refreshAccountHistory) loadHistory(historyPage);
    }
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  } finally {
    btn.disabled = false;
  }
}

async function queryCode() {
  const email = String(document.getElementById('queryEmail').value || '').trim();
  const platform = String(document.getElementById('queryPlatform').value || '').trim();
  await queryCodeCommon(
    email,
    platform,
    document.getElementById('queryStatus'),
    document.getElementById('queryBtn'),
    document.getElementById('queryResultTable'),
    true,
  );
}

async function queryCodeOnly() {
  const email = String(document.getElementById('queryOnlyEmail').value || '').trim();
  const platform = String(document.getElementById('queryOnlyPlatform').value || '').trim();
  await queryCodeCommon(
    email,
    platform,
    document.getElementById('queryOnlyStatus'),
    document.getElementById('queryOnlyBtn'),
    document.getElementById('queryOnlyResultTable'),
    false,
  );
}

async function generateDomainBodies() {
  const count = Number(document.getElementById('domainBodyCount').value || 0);
  const industry = String(document.getElementById('domainBodyIndustry').value || 'general');
  const avoidDigits = !!document.getElementById('domainBodyAvoidDigits').checked;
  const requireDigits = !!document.getElementById('domainBodyRequireDigits').checked;
  const allowHyphen = !!document.getElementById('domainBodyAllowHyphen').checked;
  const recommendSubdomain = !!document.getElementById('domainBodyRecommendSubdomain').checked;

  const status = document.getElementById('domainBodyStatus');
  const btn = document.getElementById('domainBodyBtn');
  const table = document.getElementById('domainBodyTable');
  const tbody = table.querySelector('tbody');

  if (!count || count < 1 || count > 500) {
    status.className = 'status err';
    status.textContent = '数量必须在 1-500';
    return;
  }

  if (avoidDigits && requireDigits) {
    status.className = 'status err';
    status.textContent = '“避免数字”和“必含数字”不能同时开启';
    return;
  }

  btn.disabled = true;
  status.className = 'status';
  status.textContent = '正在生成...';
  table.style.display = 'none';
  tbody.innerHTML = '';

  try {
    const res = await fetch('/api/domain-bodies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        count,
        industry,
        avoid_digits: avoidDigits,
        require_digits: requireDigits,
        allow_hyphen: allowHyphen,
        recommend_subdomain: recommendSubdomain,
      })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '生成失败');
    }

    const items = data.items || [];
    const subdomains = data.subdomains || [];

    items.forEach((name, idx) => {
      const sub = subdomains[idx] || '';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td data-copy="${idx + 1}">${idx + 1}</td>
        <td data-copy="${name || ''}">${name || ''}</td>
        <td data-copy="${sub}">${sub}</td>
      `;
      tbody.appendChild(tr);
    });

    table.style.display = items.length ? 'table' : 'none';
    bindCopyHandlers();
    status.className = 'status ok';
    status.textContent = `完成：已生成 ${items.length} 条${recommendSubdomain ? '，并附带三级子域推荐' : ''}`;
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  } finally {
    btn.disabled = false;
  }
}

function renderTable(rows) {
  const table = document.getElementById('resultTable');
  const tbody = table.querySelector('tbody');
  tbody.innerHTML = '';

  rows.forEach((r, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td data-copy="${idx + 1}">${idx + 1}</td>
      <td data-copy="${r.email || ''}">${r.email || ''}</td>
      <td data-copy="${r.password || ''}">${r.password || ''}</td>
      <td data-copy="${r.app_password || ''}">${r.app_password || ''}</td>
      <td data-copy="${r.name || ''}">${r.name || ''}</td>
      <td data-copy="${r.age || ''}">${r.age || ''}</td>
      <td data-copy="${r.birthday || ''}">${r.birthday || ''}</td>
    `;
    tbody.appendChild(tr);
  });

  table.style.display = rows.length ? 'table' : 'none';
  bindCopyHandlers();
}

function onDeleteModeChange() {
  const mode = document.getElementById('deleteMode').value;
  const valueInput = document.getElementById('deleteValue');
  if (mode === 'all') {
    valueInput.disabled = true;
    valueInput.value = '';
    valueInput.placeholder = '无需输入';
  } else if (mode === 'keep_latest') {
    valueInput.disabled = false;
    valueInput.placeholder = '保留数量';
    if (!valueInput.value) valueInput.value = '100';
  } else {
    valueInput.disabled = false;
    valueInput.placeholder = '删除数量';
    if (!valueInput.value) valueInput.value = '100';
  }
}

async function bulkDeleteAccounts() {
  const mode = document.getElementById('deleteMode').value;
  const valueRaw = document.getElementById('deleteValue').value;
  const status = document.getElementById('historyStatus');
  const btn = document.getElementById('deleteBtn');

  let value = Number(valueRaw || 0);
  if (mode !== 'all' && (!value || value < 1)) {
    status.className = 'status err';
    status.textContent = '请填写大于 0 的数量';
    return;
  }

  const confirmText = mode === 'all'
    ? '确认删除全部历史记录吗？此操作不可恢复。'
    : '确认执行批量删除吗？此操作不可恢复。';
  if (!window.confirm(confirmText)) {
    return;
  }

  btn.disabled = true;
  status.className = 'status';
  status.textContent = '正在删除...';

  try {
    const payload = { mode };
    if (mode === 'keep_latest') payload.keep_latest = value;
    if (mode === 'delete_oldest') payload.delete_count = value;

    const res = await fetch('/api/history/accounts/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || '删除失败');
    }

    status.className = 'status ok';
    status.textContent = `已删除 ${data.deleted} 条，剩余 ${data.remaining} 条`;
    loadHistory(1);
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  } finally {
    btn.disabled = false;
  }
}

async function loadHistory(page) {
  const pageSize = Number(document.getElementById('historyPageSize').value || 20);
  const status = document.getElementById('historyStatus');
  const table = document.getElementById('historyTable');
  const tbody = table.querySelector('tbody');

  if (!pageSize || pageSize < 5 || pageSize > 200) {
    status.className = 'status err';
    status.textContent = '每页数量必须在 5-200';
    return;
  }

  try {
    const res = await fetch(`/api/history/accounts?page=${page}&page_size=${pageSize}`);
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '加载历史失败');
    }

    historyPage = data.page;
    historyTotalPages = data.total_pages || 1;

    tbody.innerHTML = '';
    (data.items || []).forEach((r) => {
      const tr = document.createElement('tr');
      const isInUse = !!r.used || (currentInUseEmail && String(r.email || '').toLowerCase() === currentInUseEmail.toLowerCase());
      if (isInUse) tr.classList.add('in-use-row');

      tr.innerHTML = `
        <td data-copy="${r.id || ''}">${r.id || ''}</td>
        <td data-copy="${r.email || ''}">${r.email || ''}</td>
        <td data-copy="${r.password || ''}">${r.password || ''}</td>
        <td data-copy="${r.app_password || ''}">${r.app_password || ''}</td>
        <td data-copy="${r.name || ''}">${r.name || ''}</td>
        <td data-copy="${r.age || ''}">${r.age || ''}</td>
        <td data-copy="${r.birthday || ''}">${r.birthday || ''}</td>
        <td data-copy="${isInUse ? '正在使用' : '未使用'}">${isInUse ? '正在使用' : '未使用'}</td>
        <td data-copy="${r.platforms || ''}">${r.platforms || ''}</td>
        <td data-copy="${r.used_at || ''}">${r.used_at || ''}</td>
        <td data-copy="${r.created_at || ''}">${r.created_at || ''}</td>
        <td>
          <button class="${isInUse ? 'btn-secondary' : 'btn-warning'}" onclick="setUsed('${(r.email || '').replace(/'/g, "\\'")}', ${isInUse ? 'false' : 'true'})">
            ${isInUse ? '改为未使用' : '标记正在使用'}
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    table.style.display = (data.items || []).length ? 'table' : 'none';
    bindCopyHandlers();
    status.className = 'status';
    status.textContent = `第 ${historyPage} / ${historyTotalPages} 页，共 ${data.total} 条`;
    document.getElementById('prevHistoryBtn').disabled = historyPage <= 1;
    document.getElementById('nextHistoryBtn').disabled = historyPage >= historyTotalPages;
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  }
}

async function setUsed(email, used) {
  let platform = '';
  if (used) {
    platform = prompt('请输入平台名（可留空）', '') || '';
  }

  try {
    const res = await fetch('/api/accounts/set-used', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, used, platform: String(platform).trim() })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '状态更新失败');
    }

    if (used) {
      currentInUseEmail = email;
    } else if (currentInUseEmail && currentInUseEmail.toLowerCase() === String(email).toLowerCase()) {
      currentInUseEmail = '';
    }

    showCopyToast(`${email} 已更新为${used ? '正在使用' : '未使用'}`);
    loadHistory(historyPage);
  } catch (e) {
    alert(`状态更新失败：${e.message || e}`);
  }
}

function prevHistoryPage() {
  if (historyPage > 1) loadHistory(historyPage - 1);
}

function nextHistoryPage() {
  if (historyPage < historyTotalPages) loadHistory(historyPage + 1);
}

async function loadQueryHistory(page) {
  const pageSize = Number(document.getElementById('queryHistoryPageSize').value || 20);
  const status = document.getElementById('queryHistoryStatus');
  const table = document.getElementById('queryHistoryTable');
  const tbody = table.querySelector('tbody');

  if (!pageSize || pageSize < 5 || pageSize > 200) {
    status.className = 'status err';
    status.textContent = '每页数量必须在 5-200';
    return;
  }

  try {
    const emailFilter = String(document.getElementById('queryHistoryEmailFilter').value || '').trim();
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (emailFilter) query.set('email', emailFilter);

    const res = await fetch(`/api/history/query-code?${query.toString()}`);
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '加载验证码查询历史失败');
    }

    queryHistoryPage = data.page;
    queryHistoryTotalPages = data.total_pages || 1;

    tbody.innerHTML = '';
    (data.items || []).forEach((r) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><input type="checkbox" class="query-history-check" value="${r.id || ''}" /></td>
        <td data-copy="${r.id || ''}">${r.id || ''}</td>
        <td data-copy="${r.email || ''}">${r.email || ''}</td>
        <td data-copy="${r.code || ''}">${r.code || ''}</td>
        <td data-copy="${r.sender || ''}">${r.sender || ''}</td>
        <td data-copy="${r.subject || ''}">${r.subject || ''}</td>
        <td data-copy="${r.received_time || ''}">${r.received_time || ''}</td>
        <td data-copy="${r.queried_at || ''}">${r.queried_at || ''}</td>
      `;
      tbody.appendChild(tr);
    });

    table.style.display = (data.items || []).length ? 'table' : 'none';
    bindCopyHandlers();
    status.className = 'status';
    status.textContent = `第 ${queryHistoryPage} / ${queryHistoryTotalPages} 页，共 ${data.total} 条`;
    document.getElementById('prevQueryHistoryBtn').disabled = queryHistoryPage <= 1;
    document.getElementById('nextQueryHistoryBtn').disabled = queryHistoryPage >= queryHistoryTotalPages;
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  }
}

function prevQueryHistoryPage() {
  if (queryHistoryPage > 1) loadQueryHistory(queryHistoryPage - 1);
}

function nextQueryHistoryPage() {
  if (queryHistoryPage < queryHistoryTotalPages) loadQueryHistory(queryHistoryPage + 1);
}

function toggleAllQueryHistoryChecks(el) {
  const checked = !!el.checked;
  document.querySelectorAll('.query-history-check').forEach((c) => {
    c.checked = checked;
  });
}

function getSelectedQueryHistoryIds() {
  return Array.from(document.querySelectorAll('.query-history-check:checked'))
    .map((c) => Number(c.value || 0))
    .filter((n) => Number.isInteger(n) && n > 0);
}

async function deleteSelectedQueryHistory() {
  const idsText = String(document.getElementById('queryHistoryDeleteIds').value || '').trim();
  let ids = getSelectedQueryHistoryIds();
  if (!ids.length && idsText) {
    ids = idsText.split(',').map((x) => Number(String(x).trim())).filter((n) => Number.isInteger(n) && n > 0);
  }

  const status = document.getElementById('queryHistoryStatus');
  const btn = document.getElementById('deleteQuerySelectedBtn');

  if (!ids.length) {
    status.className = 'status err';
    status.textContent = '请先勾选记录或输入要删除的ID';
    return;
  }

  if (!window.confirm(`确认删除 ${ids.length} 条查询历史吗？`)) return;

  btn.disabled = true;
  try {
    const res = await fetch('/api/history/query-code/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '删除失败');
    }

    status.className = 'status ok';
    status.textContent = `已删除 ${data.deleted} 条记录`;
    document.getElementById('queryHistoryDeleteIds').value = '';
    loadQueryHistory(1);
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  } finally {
    btn.disabled = false;
  }
}

async function deleteQueryHistoryByEmail() {
  const email = String(document.getElementById('queryHistoryEmailFilter').value || '').trim();
  const status = document.getElementById('queryHistoryStatus');
  const btn = document.getElementById('deleteQueryByEmailBtn');

  if (!email || !email.includes('@')) {
    status.className = 'status err';
    status.textContent = '请先输入有效邮箱再按邮箱删除';
    return;
  }

  if (!window.confirm(`确认删除邮箱 ${email} 的全部查询历史吗？`)) return;

  btn.disabled = true;
  try {
    const res = await fetch('/api/history/query-code/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '删除失败');
    }

    status.className = 'status ok';
    status.textContent = `已删除 ${data.deleted} 条记录`;
    loadQueryHistory(1);
  } catch (e) {
    status.className = 'status err';
    status.textContent = `失败：${e.message || e}`;
  } finally {
    btn.disabled = false;
  }
}

function showCopyToast(text) {
  const toast = document.getElementById('copyToast');
  if (!toast) return;
  toast.textContent = text;
  toast.style.display = 'block';
  clearTimeout(window.__copyToastTimer);
  window.__copyToastTimer = setTimeout(() => {
    toast.style.display = 'none';
  }, 1200);
}

async function copyText(value) {
  const v = String(value || '').trim();
  if (!v) return;
  try {
    await navigator.clipboard.writeText(v);
    showCopyToast(`已复制：${v}`);
  } catch (_) {
    const ta = document.createElement('textarea');
    ta.value = v;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showCopyToast(`已复制：${v}`);
  }
}

function bindCopyHandlers() {
  document.querySelectorAll('table.copy-table td[data-copy]').forEach((td) => {
    td.onclick = () => copyText(td.getAttribute('data-copy') || td.textContent || '');
  });
}

function downloadCsv() {
  if (!latestRows.length) return;
  const qs = encodeURIComponent(JSON.stringify(latestRows));
  window.location.href = `/api/export.csv?rows=${qs}`;
}

function exportAccountsHistoryCsv() {
  window.location.href = '/api/history/accounts/export.csv';
}

function triggerImportAccountsCsv() {
  const input = document.getElementById('importAccountsFile');
  if (input) input.click();
}

async function importAccountsCsvChanged(event) {
  const status = document.getElementById('historyStatus');
  const file = event?.target?.files?.[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  status.className = 'status';
  status.textContent = '正在导入账号历史...';

  try {
    const res = await fetch('/api/history/accounts/import.csv', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || '导入失败');
    }

    status.className = 'status ok';
    status.textContent = `导入完成：成功 ${data.imported} 条，跳过 ${data.skipped} 条`;
    loadHistory(1);
  } catch (e) {
    status.className = 'status err';
    status.textContent = `导入失败：${e.message || e}`;
  } finally {
    event.target.value = '';
  }
}

function switchTab(tabName) {
  const map = {
    register: 'tab-register',
    'query-history': 'tab-query-history',
    'query-log': 'tab-query-log',
    'query-only': 'tab-query-only',
    'domain-body': 'tab-domain-body',
  };

  document.querySelectorAll('.tab-pane').forEach((el) => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach((el) => el.classList.remove('active'));

  const paneId = map[tabName];
  const pane = document.getElementById(paneId);
  const btn = document.getElementById(`tabBtn-${tabName}`);
  if (pane) pane.classList.add('active');
  if (btn) btn.classList.add('active');
}

window.addEventListener('load', () => {
  loadMaxLimit();
  loadDomainSuffixOptions();
  onDeleteModeChange();
  loadHistory(1);
  loadQueryHistory(1);
  bindCopyHandlers();
  switchTab('register');
});
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML)


@app.post("/api/register")
def api_register():
    payload = request.get_json(silent=True) or {}
    count = int(payload.get("count", 0) or 0)
    domain_suffix = str(payload.get("domain_suffix", "") or "").strip().lower().strip(".")
    max_limit = get_max_generate_limit()
    if count < 1 or count > max_limit:
        return jsonify({"ok": False, "error": f"count 必须在 1-{max_limit}"}), 400
    if domain_suffix:
        if "." not in domain_suffix:
            return jsonify({"ok": False, "error": "domain_suffix 格式不正确，例如 mailyplus.com"}), 400
        if not all(ch.isalnum() or ch in {"-", "."} for ch in domain_suffix):
            return jsonify({"ok": False, "error": "domain_suffix 仅支持字母、数字、- 和 ."}), 400

    try:
        rows = batch_register(count, domain_suffix=domain_suffix)
        save_accounts(rows)
        return jsonify({
            "ok": True,
            "data": rows,
            "max_generate_limit": max_limit,
            "domain_suffix": domain_suffix,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/settings/max-generate-limit")
def api_get_max_generate_limit():
    return jsonify({"ok": True, "max_generate_limit": get_max_generate_limit()})


@app.get("/api/settings/domain-suffix-options")
def api_get_domain_suffix_options():
    settings = get_domain_suffix_settings()
    return jsonify({"ok": True, "options": settings["options"], "default": settings["default"]})


@app.post("/api/settings/max-generate-limit")
def api_set_max_generate_limit():
    payload = request.get_json(silent=True) or {}
    value = int(payload.get("value", 0) or 0)
    if value < 1 or value > 500:
        return jsonify({"ok": False, "error": "value 必须在 1-500"}), 400
    set_max_generate_limit(value)
    return jsonify({"ok": True, "max_generate_limit": value})


@app.get("/api/history/accounts")
def api_history_accounts():
    page = int(request.args.get("page", 1) or 1)
    page_size = int(request.args.get("page_size", 20) or 20)
    if page < 1:
        page = 1
    if page_size < 5:
        page_size = 5
    if page_size > 200:
        page_size = 200

    data = get_accounts_history(page=page, page_size=page_size)
    return jsonify({"ok": True, **data})


@app.post("/api/history/accounts/bulk-delete")
def api_history_accounts_bulk_delete():
    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode", "")).strip()

    keep_latest = int(payload.get("keep_latest", 0) or 0)
    delete_count = int(payload.get("delete_count", 0) or 0)

    if mode not in {"all", "keep_latest", "delete_oldest"}:
        return jsonify({"ok": False, "error": "mode 必须是 all / keep_latest / delete_oldest"}), 400

    if mode == "keep_latest" and keep_latest < 0:
        return jsonify({"ok": False, "error": "keep_latest 不能小于 0"}), 400
    if mode == "delete_oldest" and delete_count < 1:
        return jsonify({"ok": False, "error": "delete_count 必须大于 0"}), 400

    try:
        deleted, remaining = bulk_delete_accounts(
            mode=mode,
            keep_latest=keep_latest,
            delete_count=delete_count,
        )
        return jsonify({"ok": True, "deleted": deleted, "remaining": remaining, "mode": mode})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/history/query-code")
def api_history_query_code():
    page = int(request.args.get("page", 1) or 1)
    page_size = int(request.args.get("page_size", 20) or 20)
    email = str(request.args.get("email", "")).strip()
    if page < 1:
        page = 1
    if page_size < 5:
        page_size = 5
    if page_size > 200:
        page_size = 200

    data = get_verification_query_history(page=page, page_size=page_size, email=email)
    return jsonify({"ok": True, **data})


@app.post("/api/history/query-code/delete")
def api_delete_history_query_code():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip()
    ids_raw = payload.get("ids", [])
    ids: List[int] = []
    if isinstance(ids_raw, list):
        for x in ids_raw:
            try:
                n = int(x)
                if n > 0:
                    ids.append(n)
            except Exception:
                pass

    if not email and not ids:
        return jsonify({"ok": False, "error": "请传 email 或 ids"}), 400

    deleted = delete_verification_query_history(ids=ids, email=email)
    return jsonify({"ok": True, "deleted": deleted})


@app.post("/api/query-code")
def api_query_code():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "请输入有效邮箱"}), 400

    platform = str(payload.get("platform", "")).strip()

    try:
        client = CloudMailClient()
        detail = client.query_verification_detail(email)
        if not detail:
            empty_detail = {
                "code": "",
                "sender": "",
                "subject": "",
                "received_time": "",
            }
            # 未查到验证码：优先视为未使用，不做“已使用”自动标记
            mark_account_used(email, used=False, platform="")

            return jsonify({
                "ok": True,
                "email": email,
                "saved": False,
                "auto_marked_used": False,
                "mark_platform": "",
                **empty_detail,
            })

        normalized_detail = {
            "code": str(detail.get("code", "")),
            "sender": str(detail.get("sender", "")),
            "subject": str(detail.get("subject", "")),
            "received_time": str(detail.get("received_time", "")),
        }
        save_verification_query(email, normalized_detail)

        auto_platform = platform or normalized_detail.get("sender", "") or "验证码查询"
        mark_account_used(email, used=True, platform=auto_platform)

        return jsonify({
            "ok": True,
            "email": email,
            "saved": True,
            "auto_marked_used": True,
            "mark_platform": auto_platform,
            **normalized_detail,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/accounts/set-used")
def api_set_used():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip()
    platform = str(payload.get("platform", "")).strip()
    used = bool(payload.get("used", False))

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "请输入有效邮箱"}), 400

    updated = mark_account_used(email=email, used=used, platform=platform if used else "")
    if not updated:
        return jsonify({"ok": False, "error": "未找到该邮箱记录"}), 404

    return jsonify({"ok": True, "email": email, "used": used, "platform": platform})


@app.post("/api/domain-bodies")
def api_domain_bodies():
    payload = request.get_json(silent=True) or {}
    count = int(payload.get("count", 0) or 0)
    industry = str(payload.get("industry", "general") or "general").strip().lower()
    avoid_digits = bool(payload.get("avoid_digits", False))
    require_digits = bool(payload.get("require_digits", False))
    allow_hyphen = bool(payload.get("allow_hyphen", True))
    recommend_subdomain = bool(payload.get("recommend_subdomain", True))

    if count < 1 or count > 500:
        return jsonify({"ok": False, "error": "count 必须在 1-500"}), 400
    if industry not in {"general", "tech", "ecommerce", "media", "tools", "mail"}:
        return jsonify({"ok": False, "error": "industry 必须是 general/tech/ecommerce/media/tools/mail"}), 400
    if avoid_digits and require_digits:
        return jsonify({"ok": False, "error": "avoid_digits 与 require_digits 不能同时为 true"}), 400

    items = generate_domain_bodies(
        count=count,
        industry=industry,
        avoid_digits=avoid_digits,
        require_digits=require_digits,
        allow_hyphen=allow_hyphen,
    )
    subdomains = generate_third_level_subdomains(
        domain_bodies=items,
        count=len(items),
        industry=industry,
        avoid_digits=avoid_digits,
    ) if recommend_subdomain else []

    return jsonify({
        "ok": True,
        "items": items,
        "subdomains": subdomains,
        "count": len(items),
        "options": {
            "industry": industry,
            "avoid_digits": avoid_digits,
            "require_digits": require_digits,
            "allow_hyphen": allow_hyphen,
            "recommend_subdomain": recommend_subdomain,
        },
    })


@app.get("/api/export.csv")
def api_export_csv():
    rows_raw = request.args.get("rows", "[]")
    try:
        rows = json.loads(rows_raw)
    except Exception:
        rows = []

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["email", "password", "app_password", "name", "age", "birthday"])
    for item in rows:
        writer.writerow(
            [
                item.get("email", ""),
                item.get("password", ""),
                item.get("app_password", ""),
                item.get("name", ""),
                item.get("age", ""),
                item.get("birthday", ""),
            ]
        )

    data = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name="cloud_mail_accounts.csv",
    )


@app.get("/api/history/accounts/export.csv")
def api_export_accounts_history_csv():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT email, password, app_password, name, age, birthday,
                   created_at, used, used_at, platforms
            FROM accounts
            ORDER BY id DESC
            """
        ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "email", "password", "app_password", "name", "age", "birthday",
        "created_at", "used", "used_at", "platforms",
    ])
    for r in rows:
        d = dict(r)
        writer.writerow([
            d.get("email", ""),
            d.get("password", ""),
            d.get("app_password", ""),
            d.get("name", ""),
            d.get("age", ""),
            d.get("birthday", ""),
            d.get("created_at", ""),
            d.get("used", 0),
            d.get("used_at", ""),
            d.get("platforms", ""),
        ])

    data = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name="cloud_mail_accounts_history.csv",
    )


@app.post("/api/history/accounts/import.csv")
def api_import_accounts_history_csv():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "请上传 CSV 文件"}), 400

    try:
        raw = f.read()
        text = raw.decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(r) for r in reader if isinstance(r, dict)]
        imported, skipped = save_accounts_with_meta(rows)
        return jsonify({"ok": True, "imported": imported, "skipped": skipped})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
