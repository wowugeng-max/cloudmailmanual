from __future__ import annotations

import random
import secrets
import string
from datetime import date, timedelta
from typing import Dict, List

from cloud_mail_client import CloudMailClient


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

def batch_register(count: int, domain_suffix: str = "", profile_id: str = "") -> List[Dict[str, str | int]]:
    client = CloudMailClient(profile_id=profile_id)
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
