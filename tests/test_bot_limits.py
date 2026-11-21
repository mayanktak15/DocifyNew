import pytest
from bots.rate_limit import BotRateLimiter


def test_memory_rate_limit_is_per_sender_and_expires(monkeypatch):
    import bots.rate_limit as module
    monkeypatch.delenv('REDIS_URL', raising=False)
    current = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: current[0])
    limit = BotRateLimiter()
    assert all(limit.check('telegram', '123') == 'allowed' for _ in range(10))
    assert limit.check('telegram', '123') == 'limited'
    assert limit.check('telegram', '456') == 'allowed'
    assert limit.check('discord', '123') == 'allowed'
    current[0] += 60
    assert limit.check('telegram', '123') == 'allowed'


def test_redis_failure_fails_closed_and_hashes_identifier(monkeypatch):
    redis = pytest.importorskip('redis')
    monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')
    monkeypatch.delenv('BOT_RATE_KEY_SECRET', raising=False)
    monkeypatch.delenv('SECRET_KEY', raising=False)
    limit = BotRateLimiter()
    assert limit.check('whatsapp', '+15550000000') == 'unavailable'
    monkeypatch.setenv('SECRET_KEY', 'private-test-secret')
    class Client:
        def eval(self, script, numkeys, key, nonce):
            assert '+15550000000' not in key
            assert key.startswith('docify:bot-rate:')
            return 1
        def close(self):
            pass
    monkeypatch.setattr(redis.Redis, 'from_url', lambda *args, **kwargs: Client())
    assert limit.check('whatsapp', '+15550000000') == 'allowed'
    def fail(*args, **kwargs):
        raise OSError('offline')
    monkeypatch.setattr(redis.Redis, 'from_url', fail)
    assert limit.check('whatsapp', '+15550000000') == 'unavailable'
