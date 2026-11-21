"""Dependency checks for the web process; never disclose connection strings."""
from pathlib import Path
from alembic.script import ScriptDirectory
from sqlalchemy import text
from flask import current_app
from app import db


def check_database():
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        db.session.rollback()
        return {'database': 'down', 'schema': 'unknown'}
    try:
        versions = set(db.session.execute(text('SELECT version_num FROM alembic_version')).scalars())
        migrations = Path(current_app.root_path).parent / 'migrations'
        expected = set(ScriptDirectory(str(migrations)).get_heads())
        return {'database': 'up', 'schema': 'current' if versions == expected and expected else 'outdated'}
    except Exception:
        db.session.rollback()
        return {'database': 'up', 'schema': 'unknown'}


def check_rate_limit_store():
    if not current_app.config.get('RATELIMIT_ENABLED', True):
        return 'disabled'
    address = current_app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
    if address == 'memory://':
        return 'local'
    if not isinstance(address, str) or not address.startswith(('redis://', 'rediss://')):
        return 'unsupported'
    connection = None
    try:
        import redis
        connection = redis.Redis.from_url(address, socket_connect_timeout=1, socket_timeout=1)
        return 'up' if connection.ping() else 'down'
    except Exception:
        return 'down'
    finally:
        if connection is not None:
            connection.close()


def readiness():
    components = check_database()
    components['rate_limit_store'] = check_rate_limit_store()
    ready = components['database'] == 'up' and components['schema'] == 'current' and components['rate_limit_store'] in ('up', 'local')
    return {'status': 'ready' if ready else 'not_ready', 'components': components}, 200 if ready else 503
