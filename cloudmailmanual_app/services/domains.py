from __future__ import annotations

import random
from typing import List, Tuple


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
