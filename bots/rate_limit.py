"""Per-sender bot rate limiting; Redis is shared, memory is development-only."""
from collections import OrderedDict, deque
import hashlib
import hmac
import os
import threading
import time
import uuid

SCRIPT = '''
local t = redis.call('TIME')
local now = t[1] * 1000000 + t[2]
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - 60000000)
if redis.call('ZCARD', KEYS[1]) >= 10 then return 0 end
redis.call('ZADD', KEYS[1], now, ARGV[1])
redis.call('EXPIRE', KEYS[1], 61)
return 1
'''


class BotRateLimiter:
    def __init__(self):
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def check(self, platform, user_id):
        if not user_id:
            return 'unavailable'
        url = os.getenv('REDIS_URL', '').strip()
        if url:
            secret = os.getenv('BOT_RATE_KEY_SECRET') or os.getenv('SECRET_KEY')
            if not secret:
                return 'unavailable'
            key_id = hmac.new(secret.encode(), f'{platform}:{user_id}'.encode(), hashlib.sha256).hexdigest()
            try:
                import redis
                client = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
                try:
                    result = client.eval(SCRIPT, 1, 'docify:bot-rate:' + key_id, uuid.uuid4().hex)
                    return 'allowed' if result == 1 else 'limited'
                finally:
                    client.close()
            except Exception:
                return 'unavailable'
        key = (platform, str(user_id))
        with self._lock:
            current = time.monotonic()
            queue = self._entries.pop(key, deque())
            while queue and queue[0] <= current - 60:
                queue.popleft()
            allowed = len(queue) < 10
            if allowed:
                queue.append(current)
            self._entries[key] = queue
            while len(self._entries) > 10000:
                self._entries.popitem(last=False)
            return 'allowed' if allowed else 'limited'


bot_limiter = BotRateLimiter()
