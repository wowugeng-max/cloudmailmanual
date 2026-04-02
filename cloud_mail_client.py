from __future__ import annotations

import json
import random
import re
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _load_config() -> Dict[str, Any]:
    cfg_path = Path(__file__).parent / "config.json"
    if not cfg_path.exists():
        raise Exception("未找到 config.json，请先从 config.example.json 复制并填写")
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


class CloudMailClient:
    def __init__(self) -> None:
        self.conf = _load_config()
        self.base = str(self.conf.get("cloud_mail_api_base", "")).rstrip("/")
        self.admin_email = str(self.conf.get("cloud_mail_admin_email", ""))
        self.admin_password = str(self.conf.get("cloud_mail_admin_password", ""))
        self.role_name = str(self.conf.get("cloud_mail_role_name", ""))
        self.proxy = str(self.conf.get("proxy", ""))

        if not self.base or not self.admin_email or not self.admin_password:
            raise Exception("请在 config.json 配置 cloud_mail_api_base/cloud_mail_admin_email/cloud_mail_admin_password")

        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.8, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": "cloudmailmanual/1.0", "Accept": "application/json"})
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}

        self._token: str = ""
        self._token_ts: float = 0
        self._used_local_parts: set[str] = set()

    def _gen_token(self, force: bool = False) -> str:
        if not force and self._token and (time.time() - self._token_ts < 600):
            return self._token

        url = f"{self.base}/api/public/genToken"
        payload = {"email": self.admin_email, "password": self.admin_password}
        res = self.session.post(url, json=payload, timeout=20, verify=False)
        if res.status_code != 200:
            raise Exception(f"genToken HTTP {res.status_code}: {res.text[:200]}")
        data = res.json()
        if data.get("code") != 200:
            raise Exception(f"genToken 失败: {data}")
        token = (data.get("data") or {}).get("token")
        if not token:
            raise Exception("genToken 未返回 token")
        self._token = str(token)
        self._token_ts = time.time()
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self._gen_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _generate_password(length: int = 14) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%"
        pwd = [
            random.choice(string.ascii_uppercase),
            random.choice(string.ascii_lowercase),
            random.choice(string.digits),
            random.choice("!@#$%"),
        ]
        pwd += [random.choice(chars) for _ in range(max(0, length - 4))]
        random.shuffle(pwd)
        return "".join(pwd)

    def _email_list(self, to_email: str, size: int = 20) -> List[Dict[str, Any]]:
        url = f"{self.base}/api/public/emailList"
        payload = {
            "toEmail": to_email,
            "type": 0,
            "isDel": 0,
            "timeSort": "desc",
            "num": 1,
            "size": size,
        }

        res = self.session.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=20,
            verify=False,
        )
        if res.status_code == 401:
            res = self.session.post(
                url,
                json=payload,
                headers={**self._headers(), "Authorization": self._gen_token(force=True)},
                timeout=20,
                verify=False,
            )

        if res.status_code != 200:
            return []

        data = res.json()
        if data.get("code") != 200:
            return []

        rows = data.get("data")
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
        return []

    @staticmethod
    def extract_verification_code(content: str, *, allow_digits: bool = True) -> Optional[str]:
        if not content:
            return None

        # 1) 先匹配 Grok 常见格式：XXX-XXX
        m = re.search(r"(?<![A-Z0-9-])([A-Z0-9]{3}-[A-Z0-9]{3})(?![A-Z0-9-])", content)
        if m:
            return m.group(1)

        # 2) 再匹配连续 6 位字母数字（如 6PN6XW）
        m = re.search(r"(?<![A-Z0-9])([A-Z0-9]{6})(?![A-Z0-9])", content)
        if m:
            code = m.group(1)
            # 纯数字是否允许由调用方决定
            if allow_digits or not code.isdigit():
                return code

        # 3) 带标签语义
        m = re.search(
            r"(?:verification code|验证码|your code)[:\s]*[<>\s]*([A-Z0-9-]{6,7})\b",
            content,
            re.IGNORECASE,
        )
        if m:
            code = m.group(1)
            if allow_digits or not code.replace("-", "").isdigit():
                return code

        if allow_digits:
            for code in re.findall(r">\s*(\d{6})\s*<", content):
                if code != "177010":
                    return code
            for code in re.findall(r"(?<![&#\d])(\d{6})(?![&#\d])", content):
                if code != "177010":
                    return code

        return None

    def query_verification_detail(self, email: str) -> Optional[Dict[str, Any]]:
        """
        查询邮箱验证码详情。
        按 timeSort=desc 返回的顺序扫描，因此优先命中“最新邮件”中的验证码。

        规则：优先从 subject 提取（且优先字母数字混合码），再回退正文。
        """
        rows = self._email_list(to_email=email, size=50)
        for row in rows:
            subject = str(row.get("subject") or "")
            text = str(row.get("text") or "")
            html = str(row.get("content") or "")

            # 先查主题：先不允许纯数字，再允许纯数字
            code = self.extract_verification_code(subject, allow_digits=False)
            if not code:
                code = self.extract_verification_code(subject, allow_digits=True)

            # 主题没有再查正文（同样先偏好非纯数字）
            if not code:
                code = self.extract_verification_code(text, allow_digits=False)
            if not code:
                code = self.extract_verification_code(html, allow_digits=False)
            if not code:
                code = self.extract_verification_code(text, allow_digits=True)
            if not code:
                code = self.extract_verification_code(html, allow_digits=True)

            if code:
                return {
                    "code": code,
                    "sender": str(row.get("sendEmail") or row.get("sendName") or ""),
                    "subject": subject,
                    "received_time": str(row.get("createTime") or ""),
                }
        return None

    def query_verification_code(self, email: str) -> Optional[str]:
        detail = self.query_verification_detail(email)
        return str(detail.get("code")) if detail else None

    @staticmethod
    def _generate_natural_local_part() -> str:
        # 扩展名字池，适合长期批量使用，降低重复率
        first_names = [
            "alex", "aaron", "adam", "adrian", "alan", "albert", "andrew", "anthony",
            "ben", "brandon", "brian", "bruce", "caleb", "cameron", "charles", "chris",
            "daniel", "david", "derek", "edward", "elijah", "ethan", "evan", "frank",
            "gabriel", "george", "henry", "ian", "jack", "jacob", "james", "jason",
            "jeremy", "john", "jonathan", "jordan", "joseph", "justin", "kevin", "leo",
            "liam", "logan", "lucas", "mason", "matthew", "michael", "nathan", "nicholas",
            "noah", "oliver", "owen", "patrick", "peter", "ray", "richard", "robert",
            "ryan", "sam", "samuel", "scott", "steven", "thomas", "tony", "victor",
            "william", "zack", "amy", "anna", "ava", "bella", "chloe", "claire",
            "diana", "ella", "emily", "emma", "eva", "grace", "hannah", "isabella",
            "jane", "jessica", "julia", "kate", "katie", "lily", "linda", "lucy",
            "mia", "natalie", "nina", "olivia", "rachel", "rose", "sarah", "sophia",
            "stella", "susan", "victoria", "violet", "zoe", "yuki", "mei", "xin",
        ]
        last_names = [
            "smith", "johnson", "williams", "brown", "jones", "miller", "davis", "wilson",
            "anderson", "thomas", "taylor", "moore", "martin", "lee", "walker", "hall",
            "allen", "young", "hernandez", "king", "wright", "lopez", "hill", "scott",
            "green", "adams", "baker", "nelson", "carter", "mitchell", "perez", "roberts",
            "turner", "phillips", "campbell", "parker", "evans", "edwards", "collins", "stewart",
            "sanchez", "morris", "rogers", "reed", "cook", "morgan", "bell", "murphy",
            "bailey", "rivera", "cooper", "richardson", "cox", "howard", "ward", "torres",
            "peterson", "gray", "ramirez", "james", "watson", "brooks", "kelly", "sanders",
            "price", "bennett", "wood", "barnes", "ross", "henderson", "coleman", "jenkins",
            "perry", "powell", "long", "patterson", "hughes", "flores", "washington", "butler",
            "simmons", "foster", "gonzales", "bryant", "alexander", "russell", "griffin", "diaz",
            "hayes", "myers", "ford", "hamilton", "graham", "sullivan", "wallace", "woods",
            "wang", "zhang", "liu", "chen", "yang", "huang", "zhao", "wu", "zhou", "xu",
            "sun", "ma", "zhu", "hu", "guo", "lin", "he", "gao", "liang", "luo",
        ]

        first = random.choice(first_names)
        last = random.choice(last_names)

        style = random.choice(["dot", "plain", "underscore", "hyphen"])
        if style == "dot":
            base = f"{first}.{last}"
        elif style == "underscore":
            base = f"{first}_{last}"
        elif style == "hyphen":
            base = f"{first}-{last}"
        else:
            base = f"{first}{last}"

        # 低概率加入中间名首字母，提升多样性
        if random.random() < 0.2:
            middle = random.choice(string.ascii_lowercase)
            joiner = random.choice(["", ".", "_"])
            base = f"{first}{joiner}{middle}{joiner}{last}"

        # 更像真实用户：65% 不加数字，35% 加 2~4 位数字
        if random.random() < 0.35:
            digits_len = random.choice([2, 3, 4])
            digits = "".join(random.choices(string.digits, k=digits_len))
            if random.random() < 0.5:
                base = f"{base}{digits}"
            else:
                base = f"{base}{random.choice(['.', '_'])}{digits}"

        return base[:64]

    def _next_unique_local_part(self, max_retry: int = 30) -> str:
        # 进程内去重缓存：同一次运行不重复
        for _ in range(max_retry):
            candidate = self._generate_natural_local_part()
            if candidate not in self._used_local_parts:
                self._used_local_parts.add(candidate)
                return candidate

        # 极端情况下兜底：追加时间戳后缀再入缓存
        fallback = f"{self._generate_natural_local_part()}_{int(time.time() * 1000) % 1000000}"
        self._used_local_parts.add(fallback)
        return fallback[:64]

    def create_temp_email(self) -> Tuple[str, str, Optional[str]]:
        domain = self.admin_email.split("@")[-1] if "@" in self.admin_email else ""
        if not domain:
            raise Exception("管理员邮箱格式不正确")

        local = self._next_unique_local_part()
        email = f"{local}@{domain}"
        password = self._generate_password()

        url = f"{self.base}/api/public/addUser"
        user_obj: Dict[str, Any] = {"email": email, "password": password}
        if self.role_name:
            user_obj["roleName"] = self.role_name

        res = self.session.post(
            url,
            json={"list": [user_obj]},
            headers=self._headers(),
            timeout=20,
            verify=False,
        )
        if res.status_code == 401:
            res = self.session.post(
                url,
                json={"list": [user_obj]},
                headers={**self._headers(), "Authorization": self._gen_token(force=True)},
                timeout=20,
                verify=False,
            )

        if res.status_code != 200:
            raise Exception(f"addUser HTTP {res.status_code}: {res.text[:200]}")

        data = res.json()
        if data.get("code") != 200:
            # 常见重复场景：邮箱已存在。这里自动重试一次新的邮箱名。
            if "exist" in str(data).lower() or "已存在" in str(data):
                return self.create_temp_email()
            raise Exception(f"addUser 失败: {data}")

        return email, password, None
