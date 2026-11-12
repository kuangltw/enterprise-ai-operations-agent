"""登入、工作階段撤銷與目前使用者查詢。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from redis.exceptions import RedisError

from .db import engine
from .passwords import hash_password, verify_password
from .rate_limit import LoginRateLimiter, get_login_limiter
from .settings import settings
from .tokens import issue_access_token, verify_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["身分驗證"])
_DUMMY_HASH = hash_password("synthetic-dummy-password")


class AuthError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime


class MeResponse(BaseModel):
    id: UUID
    email: str


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    session_id: UUID
    email: str


def get_db() -> Iterator[Session]:
    with Session(engine) as db:
        yield db


def get_signing_key() -> str:
    key = settings.jwt_signing_key
    if not key or key.startswith("change-") or len(key.encode("utf-8")) < 32:
        raise AuthError(503, "AUTH_UNAVAILABLE", "身分驗證服務尚未就緒")
    return key


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    signing_key: str = Depends(get_signing_key),
) -> Principal:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token:
        raise AuthError(401, "UNAUTHENTICATED", "請先登入")
    claims = verify_access_token(token, signing_key)
    if claims is None:
        raise AuthError(401, "UNAUTHENTICATED", "登入憑證無效")
    row = db.execute(text("""
        SELECT u.id, u.email FROM users AS u
        JOIN sessions AS s ON s.user_id = u.id
        WHERE u.id = :user_id AND u.status = 'active'
          AND s.id = :session_id AND s.revoked_at IS NULL
          AND s.expires_at > :now
    """), {"user_id": str(claims.user_id), "session_id": str(claims.session_id),
           "now": datetime.now(timezone.utc)}).mappings().first()
    if row is None:
        raise AuthError(401, "UNAUTHENTICATED", "登入工作階段已失效")
    return Principal(claims.user_id, claims.session_id, row["email"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db),
          signing_key: str = Depends(get_signing_key),
          limiter: LoginRateLimiter = Depends(get_login_limiter)) -> TokenResponse:
    email = body.email.strip().lower()
    address = request.client.host if request.client else "unknown"
    try:
        allowed = limiter.allow(address, email, signing_key)
    except RedisError as exc:
        raise AuthError(503, "AUTH_UNAVAILABLE", "身分驗證服務尚未就緒") from exc
    if not allowed:
        raise AuthError(429, "LOGIN_RATE_LIMITED", "登入嘗試過於頻繁")
    if not email or " " in email or "@" not in email:
        raise AuthError(401, "INVALID_CREDENTIALS", "帳號或密碼錯誤")
    rows = db.execute(text("""
        SELECT id, password_hash, status FROM users
        WHERE lower(email) = :email LIMIT 2
    """), {"email": email}).mappings().all()
    stored_hash = rows[0]["password_hash"] if len(rows) == 1 else _DUMMY_HASH
    if not verify_password(body.password, stored_hash) or len(rows) != 1 or rows[0]["status"] != "active":
        raise AuthError(401, "INVALID_CREDENTIALS", "帳號或密碼錯誤")

    user_id = UUID(str(rows[0]["id"]))
    session_id = uuid4()
    issued = issue_access_token(user_id, session_id, signing_key)
    db.execute(text("""
        INSERT INTO sessions (id, user_id, expires_at)
        VALUES (:id, :user_id, :expires_at)
    """), {"id": str(session_id), "user_id": str(user_id),
           "expires_at": issued.expires_at})
    db.commit()
    return TokenResponse(access_token=issued.token, expires_at=issued.expires_at)


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_current_user)) -> MeResponse:
    return MeResponse(id=principal.user_id, email=principal.email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(principal: Principal = Depends(get_current_user),
           db: Session = Depends(get_db)) -> None:
    db.execute(text("""
        UPDATE sessions SET revoked_at = :now
        WHERE id = :session_id AND user_id = :user_id AND revoked_at IS NULL
    """), {"now": datetime.now(timezone.utc), "session_id": str(principal.session_id),
           "user_id": str(principal.user_id)})
    db.commit()
