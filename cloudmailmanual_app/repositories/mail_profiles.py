from __future__ import annotations

import uuid
from typing import Any, Dict, List

from ..config import CONFIG_PATH
from .config_store import read_config, update_config

LEGACY_MAIL_KEYS = {
    "cloud_mail_api_base",
    "cloud_mail_admin_email",
    "cloud_mail_admin_password",
    "cloud_mail_role_name",
    "proxy",
    "domain_suffix_options",
    "default_domain_suffix",
}


def _read_config() -> Dict[str, Any]:
    return read_config(CONFIG_PATH, tolerate_non_object=True)


def _normalize_domain_list(value: Any) -> List[str]:
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    items: List[str] = []
    for item in raw_items:
        domain = str(item or "").strip().lower().strip(".")
        if domain and "." in domain and domain not in items:
            items.append(domain)
    return items


def _normalize_profile(raw: Dict[str, Any], fallback_id: str = "") -> Dict[str, Any]:
    profile_id = str(raw.get("id") or fallback_id or uuid.uuid4().hex[:12]).strip()
    admin_email = str(raw.get("cloud_mail_admin_email", "") or "").strip()
    name = str(raw.get("name", "") or "").strip() or admin_email or profile_id
    options = _normalize_domain_list(raw.get("domain_suffix_options", []))
    admin_domain = admin_email.split("@")[-1].lower() if "@" in admin_email else ""
    if admin_domain and admin_domain not in options:
        options.insert(0, admin_domain)

    default_suffix = str(raw.get("default_domain_suffix", "") or "").strip().lower().strip(".")
    if not default_suffix and options:
        default_suffix = options[0]

    return {
        "id": profile_id,
        "name": name,
        "cloud_mail_api_base": str(raw.get("cloud_mail_api_base", "") or "").strip().rstrip("/"),
        "cloud_mail_admin_email": admin_email,
        "cloud_mail_admin_password": str(raw.get("cloud_mail_admin_password", "") or ""),
        "cloud_mail_role_name": str(raw.get("cloud_mail_role_name", "") or "").strip(),
        "proxy": str(raw.get("proxy", "") or "").strip(),
        "domain_suffix_options": options,
        "default_domain_suffix": default_suffix,
    }


def _legacy_profile(config: Dict[str, Any]) -> Dict[str, Any] | None:
    if not any(config.get(key) for key in LEGACY_MAIL_KEYS):
        return None
    return _normalize_profile(
        {
            "id": "default",
            "name": str(config.get("cloud_mail_admin_email", "") or "默认配置"),
            **{key: config.get(key, "") for key in LEGACY_MAIL_KEYS},
        },
        fallback_id="default",
    )


def _validate_profiles(profiles: List[Dict[str, Any]], active_profile_id: str = "") -> Dict[str, object]:
    normalized: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    errors: List[str] = []

    for idx, raw in enumerate(profiles, start=1):
        profile = _normalize_profile(raw, fallback_id=f"profile-{idx}")
        if not profile["id"]:
            profile["id"] = uuid.uuid4().hex[:12]
        if profile["id"] in seen_ids:
            profile["id"] = f"{profile['id']}-{uuid.uuid4().hex[:6]}"
        seen_ids.add(str(profile["id"]))

        label = str(profile["name"] or profile["id"])
        if not profile["cloud_mail_api_base"]:
            errors.append(f"{label}: Cloud Mail API 地址不能为空")
        if not profile["cloud_mail_admin_email"] or "@" not in str(profile["cloud_mail_admin_email"]):
            errors.append(f"{label}: 管理员邮箱格式不正确")
        if not profile["cloud_mail_admin_password"]:
            errors.append(f"{label}: 管理员密码不能为空")
        normalized.append(profile)

    if not normalized:
        errors.append("至少需要保留一个邮箱配置")

    active = str(active_profile_id or "").strip()
    ids = {str(p["id"]) for p in normalized}
    if active not in ids and normalized:
        active = str(normalized[0]["id"])

    return {
        "profiles": normalized,
        "active_profile_id": active,
        "errors": errors,
    }


def get_mail_profiles_config() -> Dict[str, object]:
    config = _read_config()
    raw_profiles = config.get("mail_profiles")

    if isinstance(raw_profiles, list) and raw_profiles:
        profiles = [p for p in raw_profiles if isinstance(p, dict)]
        active = str(config.get("active_mail_profile_id", "") or "").strip()
        result = _validate_profiles(profiles, active_profile_id=active)
        return {
            "profiles": result["profiles"],
            "active_profile_id": result["active_profile_id"],
        }

    legacy = _legacy_profile(config)
    if legacy:
        return {
            "profiles": [legacy],
            "active_profile_id": legacy["id"],
        }

    return {
        "profiles": [],
        "active_profile_id": "",
    }


def save_mail_profiles_config(profiles: List[Dict[str, Any]], active_profile_id: str = "") -> Dict[str, object]:
    result = _validate_profiles(profiles, active_profile_id=active_profile_id)
    errors = result["errors"]
    if errors:
        raise ValueError("；".join(str(e) for e in errors))

    def apply_update(config: Dict[str, Any]) -> None:
        for key in LEGACY_MAIL_KEYS:
            config.pop(key, None)
        config["mail_profiles"] = result["profiles"]
        config["active_mail_profile_id"] = result["active_profile_id"]

    update_config(CONFIG_PATH, apply_update)

    return {
        "profiles": result["profiles"],
        "active_profile_id": result["active_profile_id"],
    }


def get_mail_profile_by_id(profile_id: str = "") -> Dict[str, Any]:
    data = get_mail_profiles_config()
    profiles = data["profiles"]
    if not isinstance(profiles, list) or not profiles:
        raise Exception("未找到邮箱配置，请先在配置页面添加 Cloud Mail 配置")

    wanted = str(profile_id or data.get("active_profile_id") or "").strip()
    for profile in profiles:
        if isinstance(profile, dict) and str(profile.get("id", "")) == wanted:
            return profile

    first = profiles[0]
    if isinstance(first, dict):
        return first
    raise Exception("邮箱配置格式不正确")
