from app import create_app, db


def test_allowlist_uses_direct_peer_not_forwarded_header(monkeypatch):
    monkeypatch.setenv('ALLOWED_IPS', '192.0.2.0/24')
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        client = app.test_client()
        assert client.get('/', headers={'X-Forwarded-For': '192.0.2.5'}).status_code == 403
        assert client.get('/', environ_base={'REMOTE_ADDR': '192.0.2.5'}).status_code == 200
        assert client.get('/health').status_code == 200
        db.drop_all()
