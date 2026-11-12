"""JWT 簽發與驗證安全邊界。"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from src.tokens import issue_access_token, verify_access_token

SECRET = "synthetic-test-only-" * 3


def test_token_round_trip_and_wrong_key():
    user_id, session_id = uuid4(), uuid4()
    issued = issue_access_token(user_id, session_id, SECRET)

    claims = verify_access_token(issued.token, SECRET)
    assert claims is not None
    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.expires_at == issued.expires_at
    assert verify_access_token(issued.token, "different-test-key-" * 3) is None


def test_expired_token_is_rejected():
    expired = jwt.encode(
        {"iss": "agent-api", "aud": "agent-web", "sub": str(uuid4()),
         "jti": str(uuid4()), "iat": datetime.now(timezone.utc) - timedelta(hours=1),
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        SECRET, algorithm="HS256",
    )
    assert verify_access_token(expired, SECRET) is None


def test_other_algorithm_and_missing_session_id_are_rejected():
    now = datetime.now(timezone.utc)
    payload = {"iss": "agent-api", "aud": "agent-web", "sub": str(uuid4()),
               "jti": str(uuid4()), "iat": now, "exp": now + timedelta(minutes=15)}
    other_algorithm = jwt.encode(payload, SECRET, algorithm="HS384")
    assert verify_access_token(other_algorithm, SECRET) is None

    del payload["jti"]
    missing_session = jwt.encode(payload, SECRET, algorithm="HS256")
    assert verify_access_token(missing_session, SECRET) is None


def test_weak_signing_key_is_rejected():
    try:
        issue_access_token(uuid4(), uuid4(), "short")
    except ValueError:
        pass
    else:
        raise AssertionError("弱簽章金鑰必須拒絕")
