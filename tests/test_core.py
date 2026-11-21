import pytest
from app import create_app, db, Consultation, User


@pytest.fixture
def client():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'WTF_CSRF_ENABLED': False, 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


def register(client, email):
    return client.post('/register', data={'name': 'Test User', 'phone': '1234567890', 'email': email, 'password': 'strongpassword'})


def test_account_consultation_and_isolation(client):
    assert register(client, 'first@example.com').status_code == 302
    assert client.post('/dashboard', data={'symptoms': 'Headache', 'priority': 'normal'}).status_code == 302
    assert b'Headache' in client.get('/dashboard').data
    client.post('/logout')
    register(client, 'second@example.com')
    assert b'Headache' not in client.get('/dashboard').data
    assert client.post('/consultations/1/delete').status_code == 404
    client.post('/logout')
    client.post('/login', data={'email': 'first@example.com', 'password': 'strongpassword'})
    assert client.post('/consultations/1/delete').status_code == 302
    assert b'Headache' not in client.get('/dashboard').data
    assert db.session.get(Consultation, 1).is_deleted
    assert db.session.get(User, 1).password_hash != 'strongpassword'


def test_chat_and_validation(client):
    assert client.post('/chatbot', json={'message': ''}).status_code == 400
    result = client.post('/chatbot', json={'message': 'chest pain'})
    assert result.status_code == 200
    assert 'emergency' in result.json['reply']
    assert client.get('/health').json['database'] == 'up'


def test_csrf_is_enforced():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        assert app.test_client().post('/register', data={}).status_code == 400
        db.drop_all()


def test_edit_only_own_pending_consultation(client):
    register(client, 'owner@example.com')
    client.post('/dashboard', data={'symptoms': 'Before', 'priority': 'normal'})
    assert client.post('/consultations/1/edit', data={'symptoms': 'After', 'priority': 'high'}).status_code == 302
    assert b'After' in client.get('/dashboard').data
    item = db.session.get(Consultation, 1)
    item.status = 'in_review'
    db.session.commit()
    client.post('/consultations/1/edit', data={'symptoms': 'Blocked', 'priority': 'normal'})
    assert db.session.get(Consultation, 1).symptoms == 'After'
    client.post('/logout')
    register(client, 'stranger@example.com')
    assert client.post('/consultations/1/edit', data={'symptoms': 'Forbidden', 'priority': 'normal'}).status_code == 404
