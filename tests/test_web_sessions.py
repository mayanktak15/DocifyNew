from app import create_app, db
from test_api import token
from test_core import client, register


def test_sign_out_all_scoped_to_account_and_does_not_revoke_api(client):
    register(client, 'first@example.com')
    api_token = token(client, 'first@example.com')
    second_browser = client.application.test_client()
    assert second_browser.post('/login', data={'email': 'first@example.com', 'password': 'strongpassword'}).status_code == 302
    other = client.application.test_client()
    register(other, 'other@example.com')
    assert second_browser.get('/dashboard').status_code == 200
    assert client.post('/profile/sign-out-all').status_code == 302
    assert client.get('/dashboard').status_code == 302
    assert second_browser.get('/dashboard').status_code == 302
    assert other.get('/dashboard').status_code == 200
    assert client.get('/api/v1/consultations', headers=api_token).status_code == 200
    assert client.post('/login', data={'email': 'first@example.com', 'password': 'strongpassword'}).status_code == 302
    assert client.get('/dashboard').status_code == 200


def test_legacy_cookie_cannot_access_private_features(client):
    register(client, 'legacy@example.com')
    with client.session_transaction() as session:
        session.pop('session_version')
    assert client.get('/dashboard').status_code == 302
    assert b'Log in' in client.get('/').data


def test_sign_out_all_requires_csrf():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        assert app.test_client().post('/profile/sign-out-all').status_code == 400
        db.drop_all()


def test_revoke_one_browser_checks_ownership(client):
    register(client, 'one@example.com')
    second = client.application.test_client()
    second.post('/login', data={'email': 'one@example.com', 'password': 'strongpassword'})
    with second.session_transaction() as state:
        session_id = state['browser_session']
    other = client.application.test_client()
    register(other, 'other@example.com')
    path = f'/profile/sessions/{session_id}/revoke'
    assert other.post(path).status_code == 404
    assert path.encode() in client.get('/profile').data
    assert client.post(path).status_code == 302
    assert second.get('/dashboard').status_code == 302
    assert client.get('/dashboard').status_code == 200
