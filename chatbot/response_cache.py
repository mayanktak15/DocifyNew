"""Cache answers to matched public FAQ documents for five minutes."""
import hashlib
import json
import os


def cached_answer(doc, generate):
    config = [os.getenv(name) for name in ('GEMINI_MODEL', 'OLLAMA_MODEL', 'HF_MODEL_PATH')]
    key = 'docify:faq:v1:' + hashlib.sha256(json.dumps([doc, config], sort_keys=True).encode()).hexdigest()
    client = None
    try:
        import redis
        client = redis.Redis.from_url(os.environ['REDIS_URL'], socket_timeout=1, socket_connect_timeout=1)
        value = client.get(key)
        if value:
            answer = json.loads(value)
            if isinstance(answer.get('reply'), str) and isinstance(answer.get('provider'), str):
                return dict(answer, cached=True)
    except Exception:
        pass
    finally:
        if client is not None:
            client.close()
    answer = generate(doc)
    if client is not None:
        try:
            client.setex(key, 300, json.dumps(answer))
        except Exception:
            pass
        finally:
            client.close()
    return dict(answer, cached=False)
