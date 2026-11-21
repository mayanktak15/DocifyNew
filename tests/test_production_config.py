import pytest
from app import create_app, validate_configuration


def valid():
    return {'DOCIFY_ENV': 'production', 'SECRET_KEY': 'a-specific-test-secret-with-32-plus-bytes',
            'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg://user:secret@localhost/docify',
            'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/1', 'SESSION_COOKIE_SECURE': True,
            'SESSION_COOKIE_HTTPONLY': True, 'SESSION_COOKIE_SAMESITE': 'Lax',
            'WTF_CSRF_ENABLED': True, 'RATELIMIT_ENABLED': True, 'DEBUG': False}


@pytest.mark.parametrize('field,value', [
    ('SECRET_KEY', 'short'),
    ('SECRET_KEY', 'change-me-to-a-long-random-secret'),
    ('SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db'),
    ('RATELIMIT_STORAGE_URI', 'memory://'),
    ('RATELIMIT_STORAGE_URI', 'redis://'),
    ('SESSION_COOKIE_SECURE', False),
    ('SESSION_COOKIE_HTTPONLY', False),
    ('SESSION_COOKIE_SAMESITE', None),
    ('WTF_CSRF_ENABLED', False),
    ('RATELIMIT_ENABLED', False),
    ('DEBUG', True),
])
def test_production_rejects_unsafe_config(field, value, monkeypatch):
    monkeypatch.delenv('FLASK_DEBUG', raising=False)
    config = valid()
    config[field] = value
    with pytest.raises(RuntimeError, match='Invalid production configuration'):
        validate_configuration(config)


def test_production_requires_explicit_safe_settings(monkeypatch):
    monkeypatch.delenv('FLASK_DEBUG', raising=False)
    validate_configuration(valid())
    monkeypatch.setenv('FLASK_DEBUG', '1')
    with pytest.raises(RuntimeError, match='Debug mode'):
        validate_configuration(valid())
    monkeypatch.delenv('FLASK_DEBUG')
    with pytest.raises(RuntimeError, match='Invalid production configuration'):
        create_app({'DOCIFY_ENV': 'production', 'SECRET_KEY': 'short'})


def test_unknown_environment_is_rejected():
    with pytest.raises(RuntimeError, match='DOCIFY_ENV'):
        validate_configuration({'DOCIFY_ENV': 'prodution'})


def test_factory_accepts_safe_production_configuration(monkeypatch):
    monkeypatch.delenv('FLASK_DEBUG', raising=False)
    app = create_app(valid())
    assert app.config['DOCIFY_ENV'] == 'production'
    assert app.config['SESSION_COOKIE_SECURE'] is True
