"""Redis 原子計數的登入速率限制。"""

import hashlib
import hmac

from redis import Redis

from .settings import settings

_SCRIPT = """
local ip_count = redis.call('INCR', KEYS[1])
if ip_count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
local account_count = redis.call('INCR', KEYS[2])
if account_count == 1 then redis.call('EXPIRE', KEYS[2], 300) end
return {ip_count, account_count}
"""


class LoginRateLimiter:
    def __init__(self, client: Redis):
        self.client = client

    def allow(self, address: str, email: str, signing_key: str) -> bool:
        ip_digest = hashlib.sha256(address.encode("utf-8")).hexdigest()
        account_digest = hmac.new(
            signing_key.encode("utf-8"), email.encode("utf-8"), hashlib.sha256,
        ).hexdigest()
        ip_count, account_count = self.client.eval(
            _SCRIPT, 2, f"login:ip:{ip_digest}", f"login:account:{account_digest}",
        )
        return ip_count <= 10 and account_count <= 5


_limiter = LoginRateLimiter(Redis.from_url(
    settings.redis_url, socket_connect_timeout=1, socket_timeout=1,
))


def get_login_limiter() -> LoginRateLimiter:
    return _limiter
