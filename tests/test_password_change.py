from app import AuditLog, User, db, create_app
from test_api import token
from test_core import client, register


def form(current, new, confirm=None):
    return {'current_password': current, 'new_password': new, 'confirm_password': new if confirm is None else confirm}


def test_change_password_revokes_sessions_and_tokens(client):
    register(client, 'person@example.com')
    api = token(client, 'person@example.com')
    second = client.application.test_client()
    second.post('/login', data={'email': 'person@example.com', 'password': 'strongpassword'})
    other = client.application.test_client()
    register(other, 'other@example.com')
    assert client.post('/profile/password', data=form('strongpassword', 'newstrongpassword')).status_code == 302
    assert client.get('/dashboard').status_code == 302
    assert second.get('/dashboard').status_code == 302
    assert other.get('/dashboard').status_code == 200
    assert client.get('/api/v1/consultations', headers=api).status_code == 401
    assert b'Invalid email or password' in client.post('/login', data={'email': 'person@example.com', 'password': 'strongpassword'}).data
    assert client.post('/login', data={'email': 'person@example.com', 'password': 'newstrongpassword'}).status_code == 302
    user = db.session.execute(db.select(User).filter_by(email='person@example.com')).scalar_one()
    assert 'newstrongpassword' not in user.password_hash
    logs = db.session.execute(db.select(AuditLog).filter_by(action='PASSWORD_CHANGE')).scalars().all()
    assert len(logs) == 1 and 'newstrongpassword' not in str(logs[0].changed_fields)


def test_invalid_password_changes_do_not_revoke_access(client):
    register(client, 'person@example.com')
    api = token(client, 'person@example.com')
    for data in (form('wrong', 'newstrongpassword'), form('strongpassword', 'short'), form('strongpassword', 'strongpassword'), form('strongpassword', 'newstrongpassword', 'different')):
        assert client.post('/profile/password', data=data).status_code == 302
        assert client.get('/dashboard').status_code == 200
        assert client.get('/api/v1/consultations', headers=api).status_code == 200
    assert db.session.execute(db.select(AuditLog).filter_by(action='PASSWORD_CHANGE')).scalar_one_or_none() is None


def test_password_change_requires_csrf():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        assert app.test_client().post('/profile/password').status_code == 400
        db.drop_all()
