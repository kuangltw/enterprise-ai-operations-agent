"""僅簽發短效使用者 JWT；租戶與權限須於請求時查詢資料庫。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

_ISSUER = "agent-api"
_AUDIENCE = "agent-web"
_LIFETIME = timedelta(minutes=15)


@dataclass(frozen=True)
class IssuedToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    session_id: UUID
    expires_at: datetime


def issue_access_token(user_id: UUID, session_id: UUID, signing_key: str) -> IssuedToken:
    """由可信任的登入流程提供使用者與工作階段 ID。"""
    if len(signing_key.encode("utf-8")) < 32:
        raise ValueError("JWT 簽章金鑰長度不足")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = now + _LIFETIME
    payload = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "sub": str(user_id),
        "jti": str(session_id),
        "iat": now,
        "exp": expires_at,
    }
    return IssuedToken(jwt.encode(payload, signing_key, algorithm="HS256"), expires_at)


def verify_access_token(token: str, signing_key: str) -> TokenClaims | None:
    """固定演算法與必要宣告；驗證成功仍須檢查使用者及 Session 狀態。"""
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["HS256"],
            audience=_AUDIENCE,
            issuer=_ISSUER,
            options={"require": ["iss", "aud", "sub", "jti", "iat", "exp"]},
        )
        return TokenClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc),
        )
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        return None
