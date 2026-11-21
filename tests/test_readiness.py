import pytest
from app import create_app, db


def migrated_app(tmp_path, **overrides):
    config = {'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "ready.db"}', 'RATELIMIT_STORAGE_URI': 'memory://'}
    config.update(overrides)
    app = create_app(config)
    result = app.test_cli_runner().invoke(args=['db', 'upgrade'])
    assert result.exit_code == 0, result.output
    return app


def test_readiness_requires_current_schema(tmp_path):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "ready.db"}', 'RATELIMIT_STORAGE_URI': 'memory://'})
    assert app.test_client().get('/ready').status_code == 503
    result = app.test_cli_runner().invoke(args=['db', 'upgrade'])
    assert result.exit_code == 0
    response = app.test_client().get('/ready')
    assert response.status_code == 200
    assert response.json['components'] == {'database': 'up', 'schema': 'current', 'rate_limit_store': 'local'}
    with app.app_context():
        db.session.execute(db.text("UPDATE alembic_version SET version_num = 'old'"))
        db.session.commit()
    assert app.test_client().get('/ready').json['components']['schema'] == 'outdated'


def test_readiness_reports_redis_down_without_leaking_url(tmp_path, monkeypatch):
    redis = pytest.importorskip('redis')
    app = migrated_app(tmp_path, RATELIMIT_STORAGE_URI='redis://user:secret@example.test:6379/1')
    def unavailable(*args, **kwargs):
        raise OSError('secret connection failed')
    monkeypatch.setattr(redis.Redis, 'from_url', unavailable)
    response = app.test_client().get('/ready')
    assert response.status_code == 503
    assert response.json['components']['rate_limit_store'] == 'down'
    assert b'secret' not in response.data
