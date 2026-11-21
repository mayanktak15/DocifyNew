import csv
import io
from app import AuditLog, create_app, db
from test_core import client, register


def test_export_is_owner_only_excludes_deleted_and_escapes_formula(client):
    register(client, 'exporter@example.com')
    client.post('/dashboard', data={'symptoms': ' =1+1', 'priority': 'normal'})
    client.post('/dashboard', data={'symptoms': 'Removed record', 'priority': 'normal'})
    client.post('/consultations/2/delete')
    client.post('/logout')
    register(client, 'another@example.com')
    client.post('/dashboard', data={'symptoms': 'Other patient details', 'priority': 'normal'})
    client.post('/logout')
    client.post('/login', data={'email': 'exporter@example.com', 'password': 'strongpassword'})
    response = client.post('/consultations/export')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'attachment' in response.headers['Content-Disposition']
    rows = list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))
    assert len(rows) == 1 and rows[0]['symptoms'] == "'=1+1"
    assert 'Other patient details' not in response.get_data(as_text=True)
    assert 'Removed record' not in response.get_data(as_text=True)
    events = db.session.execute(db.select(AuditLog).filter_by(action='EXPORT')).scalars().all()
    assert {(event.record_type, event.record_id, event.actor_id) for event in events} == {('user', 1, 1), ('consultation', 1, 1)}
    assert '1+1' not in str([event.changed_fields for event in events])


def test_export_requires_auth_and_csrf():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        client = app.test_client()
        assert client.post('/consultations/export').status_code == 400
        app.config['WTF_CSRF_ENABLED'] = False
        assert client.post('/consultations/export').status_code == 302
        db.drop_all()


def test_spreadsheet_formula_prefixes():
    from app.utils.csv_export import spreadsheet_cell
    for text in ('=1+1', '+123', '-42', '@SUM(A1)', '\tcontent', '\rcontent', '  =SUM(A1)'):
        assert spreadsheet_cell(text).startswith("'")
    assert spreadsheet_cell('ordinary text') == 'ordinary text'
