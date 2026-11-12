"""使用 scrypt 儲存密碼；資料庫只保存帶參數與隨機鹽值的雜湊。"""

import base64
import binascii
import hashlib
import hmac
import secrets

_N = 1 << 15
_R = 8
_P = 3
_MAX_MEMORY = 64 * 1024 * 1024
_MAX_PASSWORD_BYTES = 1024


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise TypeError("密碼必須是文字")
    encoded = password.encode("utf-8")
    if not encoded or len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError("密碼長度不符規定")
    return encoded


def hash_password(password: str) -> str:
    """以每次新產生的鹽值雜湊密碼。"""
    password_bytes = _password_bytes(password)
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password_bytes, salt=salt, n=_N, r=_R, p=_P,
        maxmem=_MAX_MEMORY, dklen=32,
    )
    salt_text = base64.b64encode(salt).decode("ascii")
    hash_text = base64.b64encode(derived).decode("ascii")
    return f"scrypt${_N}${_R}${_P}${salt_text}${hash_text}"


def verify_password(password: str, stored_hash: str) -> bool:
    """拒絕損壞或未知參數的儲存值，避免不可信參數耗盡資源。"""
    if not isinstance(stored_hash, str):
        return False
    parts = stored_hash.split("$")
    if len(parts) != 6 or parts[:4] != ["scrypt", str(_N), str(_R), str(_P)]:
        return False
    try:
        password_bytes = _password_bytes(password)
        salt = base64.b64decode(parts[4], validate=True)
        expected = base64.b64decode(parts[5], validate=True)
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.scrypt(
            password_bytes, salt=salt, n=_N, r=_R, p=_P,
            maxmem=_MAX_MEMORY, dklen=32,
        )
    except (ValueError, TypeError, binascii.Error):
        return False
    return hmac.compare_digest(actual, expected)
