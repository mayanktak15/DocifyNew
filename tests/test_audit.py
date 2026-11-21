import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from app import AuditLog, create_app, db
from test_core import client, register


def test_authentication_events_do_not_store_credentials(client):
    register(client, 'audited@example.com')
    client.post('/logout')
    client.post('/login', data={'email': 'audited@example.com', 'password': 'strongpassword'})
    events = db.session.execute(db.select(AuditLog).order_by(AuditLog.id)).scalars().all()
    assert [event.action for event in events] == ['REGISTER', 'LOGOUT', 'LOGIN']
    assert all(event.changed_fields == [] for event in events)


def test_migrated_sqlite_audit_is_append_only(tmp_path):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "audit.db"}', 'RATELIMIT_ENABLED': False})
    result = app.test_cli_runner().invoke(args=['db', 'upgrade'])
    assert result.exit_code == 0, result.output
    with app.app_context():
        db.session.execute(text("INSERT INTO audit_log (action, record_type, record_id, changed_fields, created_at) VALUES ('TEST', 'user', 1, '[]', CURRENT_TIMESTAMP)"))
        db.session.commit()
        for statement in ("UPDATE audit_log SET action = 'CHANGED'", 'DELETE FROM audit_log'):
            with pytest.raises(DatabaseError):
                db.session.execute(text(statement))
                db.session.commit()
            db.session.rollback()
        assert db.session.execute(text('SELECT action FROM audit_log')).scalar_one() == 'TEST'


def test_access_audit_records_only_authorized_views(client):
    from app import User
    from test_api import token
    register(client, 'patient-view@example.com')
    patient = token(client, 'patient-view@example.com')
    item_id = client.post('/api/v1/consultations', headers=patient, json={'symptoms': 'Private details'}).json['id']
    assert client.get('/dashboard').status_code == 200
    assert client.get('/profile').status_code == 200
    assert client.get(f'/api/v1/consultations/{item_id}', headers=patient).status_code == 200
    client.post('/logout')
    register(client, 'clinician-view@example.com')
    clinician = token(client, 'clinician-view@example.com')
    user = db.session.execute(db.select(User).filter_by(email='clinician-view@example.com')).scalar_one()
    user.role = 'clinician'
    db.session.commit()
    assert client.get(f'/api/v1/consultations/{item_id}', headers=clinician).status_code == 404
    assert client.get('/clinician').status_code == 200
    assert client.post(f'/api/v1/consultations/{item_id}/claim', headers=clinician).status_code == 200
    assert client.get('/clinician').status_code == 200
    assert client.get('/api/v1/consultations', headers=clinician).status_code == 200
    views = db.session.execute(db.select(AuditLog).filter_by(action='VIEW').order_by(AuditLog.id)).scalars().all()
    assert [(event.actor_id, event.record_type, event.record_id) for event in views] == [(1, 'consultation', item_id), (1, 'user', 1), (1, 'consultation', item_id), (2, 'consultation', item_id), (2, 'consultation', item_id)]
    assert all(event.changed_fields == [] for event in views)
    assert 'Private details' not in str([event.changed_fields for event in views])


def test_api_list_audits_only_records_returned_on_page(client):
    from test_api import token
    register(client, 'pages@example.com')
    headers = token(client, 'pages@example.com')
    for symptoms in ('First record', 'Second record'):
        assert client.post('/api/v1/consultations', json={'symptoms': symptoms}, headers=headers).status_code == 201
    response = client.get('/api/v1/consultations?per_page=1&page=1', headers=headers)
    assert response.status_code == 200 and len(response.json['consultations']) == 1
    returned_id = response.json['consultations'][0]['id']
    views = db.session.execute(db.select(AuditLog).filter_by(action='VIEW', record_type='consultation')).scalars().all()
    assert [(event.actor_id, event.record_id) for event in views] == [(1, returned_id)]
