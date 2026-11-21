from app import AuditLog, ChatHistory, create_app, db
from test_core import client, register
from test_api import token


def test_chat_history_scoped_deleted_and_audited(client):
    register(client, 'chat1@example.com')
    first = token(client, 'chat1@example.com')
    assert client.post('/api/v1/chat', headers=first, json={'message': 'Private question'}).status_code == 200
    entries = client.get('/api/v1/chat/history', headers=first).json['entries']
    assert len(entries) == 1 and entries[0]['query'] == 'Private question'
    entry_id = entries[0]['id']
    assert b'Private question' in client.get('/chat-history').data
    client.post('/logout')
    register(client, 'chat2@example.com')
    second = token(client, 'chat2@example.com')
    assert client.get('/api/v1/chat/history', headers=second).json['entries'] == []
    assert client.delete(f'/api/v1/chat/history/{entry_id}', headers=second).status_code == 404
    assert client.post(f'/chat-history/{entry_id}/delete').status_code == 404
    assert client.delete(f'/api/v1/chat/history/{entry_id}', headers=first).status_code == 200
    assert client.get('/api/v1/chat/history', headers=first).json['entries'] == []
    assert db.session.get(ChatHistory, entry_id) is None
    events = db.session.execute(db.select(AuditLog).filter_by(record_type='chat_history').order_by(AuditLog.id)).scalars().all()
    assert [(event.action, event.actor_id) for event in events] == [('VIEW', 1), ('VIEW', 1), ('HARD_DELETE', 1)]
    assert all(event.changed_fields == [] for event in events)


def test_history_delete_requires_csrf():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        assert app.test_client().post('/chat-history/1/delete').status_code == 400
        db.drop_all()
