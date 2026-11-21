from datetime import timedelta
import uuid
import jwt

from app import RevokedToken, db, now
from test_core import client, register
from test_api import token


def test_individual_and_all_token_revocation(client):
    register(client, 'one@example.com')
    first = token(client, 'one@example.com')
    second = token(client, 'one@example.com')
    client.post('/logout')
    register(client, 'two@example.com')
    other = token(client, 'two@example.com')
    assert client.post('/api/v1/auth/revoke', headers=first).status_code == 200
    assert client.get('/api/v1/consultations', headers=first).status_code == 401
    assert client.get('/api/v1/consultations', headers=second).status_code == 200
    assert client.get('/api/v1/consultations', headers=other).status_code == 200
    stored = db.session.execute(db.select(RevokedToken)).scalar_one()
    assert first['Authorization'].split()[1] not in stored.jti_hash
    assert client.post('/api/v1/auth/revoke-all', headers=second).status_code == 200
    assert client.get('/api/v1/consultations', headers=second).status_code == 401
    assert client.get('/api/v1/consultations', headers=other).status_code == 200
    assert client.get('/api/v1/consultations', headers=token(client, 'one@example.com')).status_code == 200


def test_expired_legacy_and_web_revocation(client):
    register(client, 'web@example.com')
    headers = token(client, 'web@example.com')
    secret = client.application.config['SECRET_KEY']
    issued = now() - timedelta(hours=2)
    expired = jwt.encode({'sub': '1', 'iat': issued, 'exp': issued + timedelta(hours=1), 'jti': uuid.uuid4().hex, 'ver': 0}, secret, algorithm='HS256')
    legacy = jwt.encode({'sub': '1', 'iat': now(), 'exp': now() + timedelta(hours=1)}, secret, algorithm='HS256')
    for value in (expired, legacy):
        assert client.get('/api/v1/consultations', headers={'Authorization': 'Bearer ' + value}).status_code == 401
    assert client.post('/profile/revoke-api-tokens').status_code == 302
    assert client.get('/api/v1/consultations', headers=headers).status_code == 401
    assert client.get('/dashboard').status_code == 200


def test_purge_only_expired_revocations(client):
    register(client, 'purge@example.com')
    db.session.add_all([
        RevokedToken(jti_hash='a' * 64, user_id=1, expires_at=now() - timedelta(hours=1)),
        RevokedToken(jti_hash='b' * 64, user_id=1, expires_at=now() + timedelta(hours=1)),
    ])
    db.session.commit()
    result = client.application.test_cli_runner().invoke(args=['purge-revoked-tokens'])
    assert result.exit_code == 0
    assert [item.jti_hash for item in db.session.execute(db.select(RevokedToken)).scalars()] == ['b' * 64]


def test_refresh_rotation_and_scope(client):
    register(client, 'rotate@example.com')
    pair = client.post('/api/v1/auth/token', json={'email': 'rotate@example.com', 'password': 'strongpassword'}).json
    refresh = {'Authorization': 'Bearer ' + pair['refresh_token']}
    assert client.get('/api/v1/consultations', headers=refresh).status_code == 401
    assert client.post('/api/v1/auth/refresh', headers={'Authorization': 'Bearer ' + pair['token']}).status_code == 401
    rotated = client.post('/api/v1/auth/refresh', headers=refresh)
    assert rotated.status_code == 200 and rotated.json['refresh_token'] != pair['refresh_token']
    assert client.post('/api/v1/auth/refresh', headers=refresh).status_code == 401
    client.post('/profile/revoke-api-tokens')
    assert client.post('/api/v1/auth/refresh', headers={'Authorization': 'Bearer ' + rotated.json['refresh_token']}).status_code == 401
