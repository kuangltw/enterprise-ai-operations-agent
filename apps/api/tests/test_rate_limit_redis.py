"""實際 Redis 上的原子計數與過期設定驗證。"""

import os
import hashlib
import hmac
from uuid import uuid4

import pytest
from redis import Redis

from src.rate_limit import LoginRateLimiter
from src.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REDIS_TESTS") != "1", reason="需明確啟用本機 Redis 整合測試",
)


def test_redis_rejects_sixth_attempt():
    client = Redis.from_url(settings.redis_url)
    limiter = LoginRateLimiter(client)
    unique = uuid4().hex
    for _ in range(5):
        assert limiter.allow(unique, f"{unique}@example.invalid", "synthetic-key")
    assert not limiter.allow(unique, f"{unique}@example.invalid", "synthetic-key")
    ip_key = f"login:ip:{hashlib.sha256(unique.encode()).hexdigest()}"
    account_digest = hmac.new(b"synthetic-key", f"{unique}@example.invalid".encode(), hashlib.sha256).hexdigest()
    assert 0 < client.ttl(ip_key) <= 60
    assert 0 < client.ttl(f"login:account:{account_digest}") <= 300
