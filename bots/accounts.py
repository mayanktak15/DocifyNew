"""Short-lived private bot access via one-time account pairing codes."""
import hashlib
import hmac
import os
import secrets
from functools import lru_cache

from flask import current_app
from app import Consultation, User, audit, create_app, db

PLATFORMS = ('telegram', 'discord', 'whatsapp')


def store():
    import redis
    address = os.environ.get('REDIS_URL')
    if not address:
        raise RuntimeError('Redis is required for account linking')
    return redis.Redis.from_url(address, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)


def key(kind, platform, value):
    digest = hmac.new(current_app.config['SECRET_KEY'].encode(), str(value).encode(), hashlib.sha256).hexdigest()
    return f'docify:bot:{kind}:{platform}:{digest}'


def pairing_code(platform, user):
    code = secrets.token_urlsafe(20)
    with store() as client:
        client.set(key('code', platform, code), f'{user.id}:{user.token_version}', ex=300)
    return code


def private_command(platform, sender, command, argument):
    if not sender or platform not in PLATFORMS:
        return 'Sender unavailable.'
    with store() as client:
        link = key('link', platform, sender)
        if command == 'link':
            # Redeem and bind atomically, so two users cannot use one code.
            script = """local v=redis.call('GET',KEYS[1]); if not v then return 0 end
            redis.call('SET',KEYS[2],v,'EX',86400); redis.call('DEL',KEYS[1]); return 1"""
            linked = client.eval(script, 2, key('code', platform, argument.strip()), link)
            return 'Account linked for 24 hours.' if linked else 'Invalid or expired pairing code.'
        if command == 'unlink':
            client.delete(link)
            return 'Account disconnected.'
        binding = client.get(link)
        if binding:
            uid, version = map(int, binding.split(':'))
            user = db.session.get(User, uid)
            if user and user.token_version == version:
                if command == 'status':
                    item = db.session.scalar(db.select(Consultation).filter_by(user_id=uid, is_deleted=False).order_by(Consultation.id.desc()).limit(1))
                    if item:
                        audit(uid, 'VIEW', 'consultation', item.id, [])
                        db.session.commit()
                        return f'Request #{item.id}: {item.status}.'
                    return 'No consultations found.'
                if command == 'consult':
                    if not 1 <= len(argument.strip()) <= 5000:
                        return 'Provide a description of 1 to 5,000 characters.'
                    item = Consultation(user_id=uid, symptoms=argument.strip())
                    db.session.add(item)
                    db.session.flush()
                    audit(uid, 'INSERT', 'consultation', item.id, ['symptoms'])
                    db.session.commit()
                    return f'Request #{item.id} saved.'
        return 'Generate a pairing code in Profile and use /link CODE in this private conversation.'


@lru_cache(maxsize=1)
def bot_app():
    return create_app()


def dispatch(platform, sender, command, argument):
    try:
        with bot_app().app_context():
            return private_command(platform, sender, command, argument)
    except Exception:
        return 'Account service unavailable. Check your dashboard before retrying.'
