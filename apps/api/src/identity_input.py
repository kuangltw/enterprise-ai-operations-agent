"""初始建帳與管理 API 共用的身分輸入規則。"""

import re


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized) or len(normalized) > 255:
        raise ValueError("Email 格式不符規定")
    return normalized


def validate_new_password(password: str) -> None:
    if len(password) < 12 or len(password.encode("utf-8")) > 1024:
        raise ValueError("密碼長度不符規定")
