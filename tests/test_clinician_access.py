from app import AuditLog, Consultation, User, db
from test_core import client, register
from test_api import token


def test_remove_clinician_releases_active_assignments_and_notifies(client):
    register(client, 'patient-role@example.com')
    patient = token(client, 'patient-role@example.com')
    pending = client.post('/api/v1/consultations', headers=patient, json={'symptoms': 'Private'}).json['id']
    done = client.post('/api/v1/consultations', headers=patient, json={'symptoms': 'Other'}).json['id']
    client.post('/logout')
    register(client, 'doctor-role@example.com')
    doctor = token(client, 'doctor-role@example.com')
    runner = client.application.test_cli_runner()
    assert runner.invoke(args=['set-clinician', 'doctor-role@example.com']).exit_code == 0
    assert client.post(f'/api/v1/consultations/{pending}/claim', headers=doctor).status_code == 200
    assert client.post(f'/api/v1/consultations/{done}/claim', headers=doctor).status_code == 200
    assert client.patch(f'/api/v1/consultations/{done}', headers=doctor, json={'status': 'completed'}).status_code == 200
    result = runner.invoke(args=['remove-clinician', 'doctor-role@example.com'])
    assert result.exit_code == 0 and '1 active consultation' in result.output
    assert db.session.get(User, 2).role == 'patient'
    assert db.session.get(Consultation, pending).clinician_id is None
    assert db.session.get(Consultation, pending).status == 'in_review'
    assert db.session.get(Consultation, done).clinician_id == 2
    assert client.get('/clinician').status_code == 403
    assert client.get(f'/api/v1/consultations/{done}', headers=doctor).status_code == 404
    assert client.post(f'/api/v1/consultations/{pending}/claim', headers=doctor).status_code == 403
    assert any('awaiting another clinician' in n['message'] for n in client.get('/api/v1/notifications', headers=patient).json['notifications'])
    assert db.session.execute(db.select(AuditLog).filter_by(action='RELEASE', record_id=pending)).scalar_one().actor_id is None
    assert 'no changes made' in runner.invoke(args=['remove-clinician', 'doctor-role@example.com']).output
    assert runner.invoke(args=['remove-clinician', 'missing@example.com']).exit_code != 0


def test_administrator_assigns_and_reassigns(client):
    register(client, 'assignment-patient@example.com')
    patient = token(client, 'assignment-patient@example.com')
    item_id = client.post('/api/v1/consultations', headers=patient, json={'symptoms': 'Example'}).json['id']
    client.post('/logout')
    register(client, 'assignment-doctor@example.com')
    runner = client.application.test_cli_runner()
    assert runner.invoke(args=['assign-consultation', str(item_id), 'assignment-doctor@example.com']).exit_code != 0
    assert runner.invoke(args=['set-clinician', 'assignment-doctor@example.com']).exit_code == 0
    assert runner.invoke(args=['assign-consultation', str(item_id), 'assignment-doctor@example.com']).exit_code == 0
    item = db.session.get(Consultation, item_id)
    db.session.refresh(item)
    assert item.clinician_id == 2 and item.status == 'in_review'
    assert db.session.execute(db.select(AuditLog).filter_by(action='ASSIGN', record_id=item_id)).scalar_one().actor_id is None
    assert 'already assigned' in runner.invoke(args=['assign-consultation', str(item_id), 'assignment-doctor@example.com']).output


def test_production_requires_review_for_existing_clinicians(client):
    email = 'review@example.com'
    register(client, email)
    headers = token(client, email)
    runner = client.application.test_cli_runner()
    grant = ['set-clinician', email]
    assert runner.invoke(args=grant).exit_code == 0
    client.application.config['DOCIFY_ENV'] = 'production'
    assert client.get('/clinician').status_code == 403
    assert client.get('/api/v1/consultations/available', headers=headers).status_code == 403
    assert runner.invoke(args=grant).exit_code != 0
    assert runner.invoke(args=grant + ['--reviewer', 'admin', '--reference', 'review-123']).exit_code == 0
    assert client.get('/clinician').status_code == 200
    assert client.get('/api/v1/consultations/available', headers=headers).status_code == 200
    assert runner.invoke(args=['remove-clinician', email]).exit_code == 0
    user = db.session.execute(db.select(User).filter_by(email=email)).scalar_one()
    assert (user.reviewed_by, user.verification_ref, user.verified_at) == (None, None, None)
