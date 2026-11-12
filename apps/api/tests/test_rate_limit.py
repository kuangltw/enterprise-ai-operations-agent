"""登入速率限制在帳號及來源兩個範圍內運作。"""

from redis.exceptions import ConnectionError

from src.rate_limit import LoginRateLimiter


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.keys = []

    def eval(self, script, count, *keys):
        assert count == 2
        assert "EXPIRE" in script
        self.keys.extend(keys)
        for key in keys:
            self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key] for key in keys]


def test_account_limit_blocks_sixth_attempt_without_storing_email():
    fake = FakeRedis()
    limiter = LoginRateLimiter(fake)
    for _ in range(5):
        assert limiter.allow("127.0.0.1", "test@example.invalid", "synthetic-key")
    assert not limiter.allow("127.0.0.1", "test@example.invalid", "synthetic-key")
    assert all("test@example.invalid" not in key for key in fake.keys)


def test_ip_limit_blocks_eleventh_distinct_account():
    limiter = LoginRateLimiter(FakeRedis())
    for index in range(10):
        assert limiter.allow("127.0.0.1", f"user{index}@example.invalid", "synthetic-key")
    assert not limiter.allow("127.0.0.1", "user10@example.invalid", "synthetic-key")


def test_redis_errors_are_not_treated_as_permission():
    class BrokenRedis:
        def eval(self, *_):
            raise ConnectionError("synthetic outage")

    try:
        LoginRateLimiter(BrokenRedis()).allow("127.0.0.1", "test@example.invalid", "synthetic-key")
    except ConnectionError:
        pass
    else:
        raise AssertionError("Redis 錯誤不得變成允許登入")
