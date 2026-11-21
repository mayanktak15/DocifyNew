from app import AuditLog, User, db
from test_core import client, register


def token(client, email):
    response = client.post('/api/v1/auth/token', json={'email': email, 'password': 'strongpassword'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json['token']}


def test_api_authorization_review_and_audit(client):
    register(client, 'patient@example.com')
    patient = token(client, 'patient@example.com')
    response = client.post('/api/v1/consultations', json={'symptoms': 'Private symptoms'}, headers=patient)
    assert response.status_code == 201
    item_id = response.json['id']
    assert client.patch(f'/api/v1/consultations/{item_id}', json={'status': 'completed'}, headers=patient).status_code == 403
    assert client.get('/clinician').status_code == 403
    client.post('/logout')
    register(client, 'other@example.com')
    other = token(client, 'other@example.com')
    assert client.get(f'/api/v1/consultations/{item_id}', headers=other).status_code == 404
    assert client.delete(f'/api/v1/consultations/{item_id}', headers=other).status_code == 404
    clinician = db.session.execute(db.select(User).filter_by(email='other@example.com')).scalar_one()
    clinician.role = 'clinician'
    db.session.commit()
    assert client.get(f'/api/v1/consultations/{item_id}', headers=other).status_code == 404
    assert client.post(f'/api/v1/consultations/{item_id}/claim', headers=other).status_code == 200
    assert client.post(f'/api/v1/consultations/{item_id}/claim', headers=other).status_code == 409
    response = client.patch(f'/api/v1/consultations/{item_id}', json={'status': 'completed', 'doctor_notes': 'Reviewed'}, headers=other)
    assert response.status_code == 200
    assert client.get(f'/api/v1/consultations/{item_id}', headers=patient).json['doctor_notes'] == 'Reviewed'
    assert client.delete(f'/api/v1/consultations/{item_id}', headers=other).status_code == 403
    logs = db.session.execute(db.select(AuditLog).filter_by(record_type='consultation').where(AuditLog.action != 'VIEW').order_by(AuditLog.id)).scalars().all()
    assert [(log.action, log.actor_id) for log in logs] == [('INSERT', 1), ('CLAIM', 2), ('UPDATE', 2)]
    assert 'Private symptoms' not in str([log.changed_fields for log in logs])
    assert client.delete(f'/api/v1/consultations/{item_id}', headers=patient).status_code == 200
    assert client.get(f'/api/v1/consultations/{item_id}', headers=other).status_code == 404


def test_api_tokens_and_validation(client):
    assert client.get('/api/v1/consultations').status_code == 401
    assert client.get('/api/v1/consultations', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    register(client, 'patient@example.com')
    headers = token(client, 'patient@example.com')
    assert client.post('/api/v1/consultations', json={'symptoms': '', 'priority': 'normal'}, headers=headers).status_code == 400
    assert client.get('/api/v1/consultations?per_page=101', headers=headers).status_code == 400
    assert client.get('/api/v1/health').json['status'] == 'healthy'


def test_assignment_limits_access_and_rejects_competing_claim(client):
    register(client, 'owner@example.com')
    owner = token(client, 'owner@example.com')
    item_id = client.post('/api/v1/consultations', headers=owner, json={'symptoms': 'Sensitive private text'}).json['id']
    client.post('/logout')
    register(client, 'clinician1@example.com')
    one = token(client, 'clinician1@example.com')
    db.session.execute(db.select(User).filter_by(email='clinician1@example.com')).scalar_one().role = 'clinician'
    db.session.commit()
    available = client.get('/api/v1/consultations/available', headers=one).json['consultations']
    assert available[0]['id'] == item_id
    assert 'Sensitive private text' not in str(available)
    assert client.get(f'/api/v1/consultations/{item_id}', headers=one).status_code == 404
    assert client.post(f'/api/v1/consultations/{item_id}/claim', headers=one).status_code == 200
    assert client.patch(f'/api/v1/consultations/{item_id}', headers=one, json={'status': 'pending'}).status_code == 400
    client.post('/logout')
    register(client, 'clinician2@example.com')
    two = token(client, 'clinician2@example.com')
    db.session.execute(db.select(User).filter_by(email='clinician2@example.com')).scalar_one().role = 'clinician'
    db.session.commit()
    assert client.get(f'/api/v1/consultations/{item_id}', headers=two).status_code == 404
    assert client.post(f'/api/v1/consultations/{item_id}/claim', headers=two).status_code == 409
    assert client.patch(f'/api/v1/consultations/{item_id}', headers=two, json={'status': 'completed'}).status_code == 404
    assert client.get('/api/v1/consultations', headers=two).json['consultations'] == []


def test_release_reassignment_and_patient_notifications(client):
    register(client, 'patient3@example.com')
    patient = token(client, 'patient3@example.com')
    item_id = client.post('/api/v1/consultations', headers=patient, json={'symptoms': 'Private description'}).json['id']
    client.post('/logout')
    register(client, 'doctor3@example.com')
    doctor = token(client, 'doctor3@example.com')
    db.session.execute(db.select(User).filter_by(email='doctor3@example.com')).scalar_one().role = 'clinician'
    db.session.commit()
    assert client.post(f'/api/v1/consultations/{item_id}/claim', headers=doctor).status_code == 200
    assert client.post(f'/api/v1/consultations/{item_id}/release', headers=doctor).status_code == 200
    assert client.get(f'/api/v1/consultations/{item_id}', headers=doctor).status_code == 404
    assert client.post(f'/api/v1/consultations/{item_id}/release', headers=doctor).status_code == 409
    notes = client.get('/api/v1/notifications', headers=patient).json['notifications']
    assert len(notes) == 2
    assert 'Private description' not in str(notes)
    assert client.post(f'/api/v1/notifications/{notes[0]["id"]}/read', headers=doctor).status_code == 404
    assert client.post(f'/api/v1/notifications/{notes[0]["id"]}/read', headers=patient).status_code == 200
    assert client.get('/api/v1/notifications', headers=patient).json['notifications'][0]['read_at'] is not None
    client.post('/logout')
    register(client, 'doctor4@example.com')
    replacement = token(client, 'doctor4@example.com')
    db.session.execute(db.select(User).filter_by(email='doctor4@example.com')).scalar_one().role = 'clinician'
    db.session.commit()
    assert client.post(f'/api/v1/consultations/{item_id}/claim', headers=replacement).status_code == 200
    assert client.patch(f'/api/v1/consultations/{item_id}', headers=doctor, json={'status': 'completed'}).status_code == 404
    assert client.patch(f'/api/v1/consultations/{item_id}', headers=replacement, json={'status': 'completed'}).status_code == 200
    assert client.post(f'/api/v1/consultations/{item_id}/release', headers=replacement).status_code == 409
    assert len(client.get('/api/v1/notifications', headers=patient).json['notifications']) == 4
