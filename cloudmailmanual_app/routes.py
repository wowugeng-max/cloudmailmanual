from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import List

from flask import jsonify, redirect, render_template, request, send_file, url_for

from auth import change_password, get_current_user, login_required, login_user, logout_user, verify_user
from cloud_mail_client import CloudMailClient

from .config import DB_PATH
from .repositories.accounts import (
    bulk_delete_accounts,
    get_accounts_history,
    mark_account_used,
    save_accounts,
    save_accounts_with_meta,
)
from .repositories.mail_profiles import get_mail_profiles_config, save_mail_profiles_config
from .repositories.settings import (
    get_domain_suffix_settings,
    get_max_generate_limit,
    set_max_generate_limit,
)
from .repositories.verification import (
    delete_verification_query_history,
    get_verification_query_history,
    save_verification_query,
)
from .repositories.verification_rules import (
    PRESET_METADATA,
    get_verification_code_rules,
    save_verification_code_rules,
    validate_verification_code_rules,
)
from .services.domains import generate_domain_bodies, generate_third_level_subdomains
from .services.registration import batch_register


def register_routes(app):
    @app.get("/")
    @login_required
    def index():
        return render_template("index.html")
    
    
    @app.post("/api/register")
    @login_required
    def api_register():
        payload = request.get_json(silent=True) or {}
        count = int(payload.get("count", 0) or 0)
        domain_suffix = str(payload.get("domain_suffix", "") or "").strip().lower().strip(".")
        profile_id = str(payload.get("profile_id", "") or "").strip()
        max_limit = get_max_generate_limit()
        if count < 1 or count > max_limit:
            return jsonify({"ok": False, "error": f"count 必须在 1-{max_limit}"}), 400
        if domain_suffix:
            if "." not in domain_suffix:
                return jsonify({"ok": False, "error": "domain_suffix 格式不正确，例如 mailyplus.com"}), 400
            if not all(ch.isalnum() or ch in {"-", "."} for ch in domain_suffix):
                return jsonify({"ok": False, "error": "domain_suffix 仅支持字母、数字、- 和 ."}), 400
    
        try:
            rows = batch_register(count, domain_suffix=domain_suffix, profile_id=profile_id)
            save_accounts(rows)
            return jsonify({
                "ok": True,
                "data": rows,
                "max_generate_limit": max_limit,
                "domain_suffix": domain_suffix,
                "profile_id": profile_id,
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    
    
    @app.get("/api/settings/max-generate-limit")
    @login_required
    def api_get_max_generate_limit():
        return jsonify({"ok": True, "max_generate_limit": get_max_generate_limit()})
    
    
    @app.get("/api/settings/domain-suffix-options")
    @login_required
    def api_get_domain_suffix_options():
        profile_id = str(request.args.get("profile_id", "") or "").strip()
        settings = get_domain_suffix_settings(profile_id=profile_id)
        return jsonify({"ok": True, "options": settings["options"], "default": settings["default"]})


    @app.get("/api/settings/mail-profiles")
    @login_required
    def api_get_mail_profiles():
        data = get_mail_profiles_config()
        return jsonify({"ok": True, **data})


    @app.post("/api/settings/mail-profiles")
    @login_required
    def api_save_mail_profiles():
        payload = request.get_json(silent=True) or {}
        profiles_raw = payload.get("profiles", [])
        active_profile_id = str(payload.get("active_profile_id", "") or "").strip()
        if not isinstance(profiles_raw, list):
            return jsonify({"ok": False, "error": "profiles 必须是数组"}), 400
        try:
            data = save_mail_profiles_config(profiles_raw, active_profile_id=active_profile_id)
            return jsonify({"ok": True, **data})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400


    @app.get("/api/settings/verification-code-rules")
    @login_required
    def api_get_verification_code_rules():
        rules = get_verification_code_rules()
        return jsonify({"ok": True, "available_presets": PRESET_METADATA, **rules})


    @app.post("/api/settings/verification-code-rules")
    @login_required
    def api_save_verification_code_rules():
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "请求体必须是对象"}), 400

        try:
            validate_verification_code_rules(payload)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        rules = save_verification_code_rules(payload)
        return jsonify({"ok": True, **rules})


    @app.post("/api/settings/verification-code-rules/test")
    @login_required
    def api_test_verification_code_rules():
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "请求体必须是对象"}), 400

        content = payload.get("content", "")
        if not isinstance(content, str):
            return jsonify({"ok": False, "error": "content 必须是字符串"}), 400
        if len(content) > 100000:
            return jsonify({"ok": False, "error": "测试内容最多 100000 个字符"}), 400

        try:
            rules = validate_verification_code_rules(payload)
            code = CloudMailClient.extract_verification_code(content, rules=rules)
            return jsonify({"ok": True, "code": code or ""})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    
    
    @app.post("/api/settings/max-generate-limit")
    @login_required
    def api_set_max_generate_limit():
        payload = request.get_json(silent=True) or {}
        value = int(payload.get("value", 0) or 0)
        if value < 1 or value > 500:
            return jsonify({"ok": False, "error": "value 必须在 1-500"}), 400
        set_max_generate_limit(value)
        return jsonify({"ok": True, "max_generate_limit": value})
    
    
    @app.get("/api/history/accounts")
    @login_required
    def api_history_accounts():
        page = int(request.args.get("page", 1) or 1)
        page_size = int(request.args.get("page_size", 20) or 20)
        email_query = str(request.args.get("email_query", "") or "").strip()
        if page < 1:
            page = 1
        if page_size < 5:
            page_size = 5
        if page_size > 200:
            page_size = 200
    
        data = get_accounts_history(page=page, page_size=page_size, email_query=email_query)
        return jsonify({"ok": True, **data})
    
    
    @app.post("/api/history/accounts/bulk-delete")
    @login_required
    def api_history_accounts_bulk_delete():
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode", "")).strip()
    
        keep_latest = int(payload.get("keep_latest", 0) or 0)
        delete_count = int(payload.get("delete_count", 0) or 0)
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
    
        if mode not in {"all", "keep_latest", "delete_oldest", "selected"}:
            return jsonify({"ok": False, "error": "mode 必须是 all / keep_latest / delete_oldest / selected"}), 400
    
        if mode == "keep_latest" and keep_latest < 0:
            return jsonify({"ok": False, "error": "keep_latest 不能小于 0"}), 400
        if mode == "delete_oldest" and delete_count < 1:
            return jsonify({"ok": False, "error": "delete_count 必须大于 0"}), 400
        if mode == "selected" and not ids:
            return jsonify({"ok": False, "error": "请先勾选要删除的账号"}), 400
    
        try:
            deleted, remaining = bulk_delete_accounts(
                mode=mode,
                keep_latest=keep_latest,
                delete_count=delete_count,
                ids=ids,
            )
            return jsonify({"ok": True, "deleted": deleted, "remaining": remaining, "mode": mode})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    
    
    @app.get("/api/history/query-code")
    @login_required
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
    @login_required
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
    @login_required
    def api_query_code():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip()
        if not email or "@" not in email:
            return jsonify({"ok": False, "error": "请输入有效邮箱"}), 400
    
        platform = str(payload.get("platform", "")).strip()
        profile_id = str(payload.get("profile_id", "") or "").strip()

        try:
            client = CloudMailClient(profile_id=profile_id)
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
    @login_required
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
    @login_required
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
    @login_required
    def api_export_csv():
        rows_raw = request.args.get("rows", "[]")
        try:
            rows = json.loads(rows_raw)
        except Exception:
            rows = []
    
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["email", "password", "app_password", "profile_id", "name", "age", "birthday"])
        for item in rows:
            writer.writerow(
                [
                    item.get("email", ""),
                    item.get("password", ""),
                    item.get("app_password", ""),
                    item.get("profile_id", ""),
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
    @login_required
    def api_export_accounts_history_csv():
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT email, password, app_password, profile_id, name, age, birthday,
                       created_at, used, used_at, platforms
                FROM accounts
                ORDER BY id DESC
                """
            ).fetchall()
    
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "email", "password", "app_password", "profile_id", "name", "age", "birthday",
            "created_at", "used", "used_at", "platforms",
        ])
        for r in rows:
            d = dict(r)
            writer.writerow([
                d.get("email", ""),
                d.get("password", ""),
                d.get("app_password", ""),
                d.get("profile_id", ""),
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
    @login_required
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
    
    
    @app.get("/login")
    def login_page():
        if get_current_user():
            return redirect(url_for("index"))
        error = request.args.get("error", "")
        return render_template("login.html", error=error)
    
    
    @app.post("/login")
    def login_handler():
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        if verify_user(username, password):
            login_user(username)
            nxt = request.args.get("next", "")
            if nxt and nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("index"))
        return redirect(url_for("login_page", error="用户名或密码错误"))
    
    
    @app.get("/logout")
    def logout():
        logout_user()
        return redirect(url_for("login_page"))
    
    
    @app.post("/api/change-password")
    @login_required
    def api_change_password():
        payload = request.get_json(silent=True) or {}
        username = get_current_user()
        old_pwd = str(payload.get("old_password", "") or "")
        new_pwd = str(payload.get("new_password", "") or "")
        ok, msg = change_password(username, old_pwd, new_pwd)
        return jsonify({"ok": ok, "message": msg})
    
    
    @app.get("/api/me")
    @login_required
    def api_me():
        return jsonify({"ok": True, "username": get_current_user()})
