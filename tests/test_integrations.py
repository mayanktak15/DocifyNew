import os
import pytest
from app import User, db
from bots import accounts
from chatbot import providers
from test_core import client, register


def test_provider_failover_only_sends_faq(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test')
    monkeypatch.setenv('GEMINI_MODEL', 'test')
    monkeypatch.setenv('OLLAMA_URL', 'http://localhost')
    calls = []
    def post(url, payload, headers=None):
        calls.append(payload)
        if headers:
            raise OSError()
        return {'response': 'Open your profile.'}
    monkeypatch.setattr(providers, 'post', post)
    assert providers.generate({'question': 'Where are settings?', 'answer': 'Open Profile.'})['provider'] == 'ollama'
    assert len(calls) == 2


def test_pairing_is_single_use_private_and_revocable(client, monkeypatch):
    if os.getenv('DOCIFY_TEST_REDIS'):
        import redis
        connection = redis.Redis.from_url(os.environ['DOCIFY_TEST_REDIS'], decode_responses=True)
    else:
        connection = pytest.importorskip('fakeredis').FakeRedis(decode_responses=True)
    monkeypatch.setattr(accounts, 'store', lambda: connection)
    register(client, 'paired@example.com')
    user = db.session.get(User, 1)
    code = accounts.pairing_code('telegram', user)
    def run(sender, cmd, arg=''):
        return accounts.private_command('telegram', sender, cmd, arg)
    assert 'linked for' in run('one', 'link', code)
    assert 'expired' in run('two', 'link', code)
    assert 'saved' in run('one', 'consult', 'Example request')
    assert 'pending' in run('one', 'status')
    assert 'Generate' in run('two', 'status')
    user.token_version += 1
    db.session.commit()
    assert 'Generate' in run('one', 'status')


def test_email_updates_persist_and_send_only_generic_message(client, monkeypatch):
    pytest.importorskip('celery')
    import smtplib
    import app
    from app import Consultation, Notification, notify_patient
    from tasks import deliver_updates
    register(client, 'mail@example.com')
    client.post('/profile/email-updates', data={'updates': 'on'})
    item = Consultation(user_id=1, symptoms='private fixture')
    db.session.add(item)
    db.session.flush()
    notify_patient(1, item.id, 'sensitive update')
    db.session.commit()
    monkeypatch.setenv('SMTP_HOST', 'local.test')
    monkeypatch.setenv('SMTP_FROM', 'dashboard@example.com')
    monkeypatch.delenv('SMTP_USER', raising=False)
    monkeypatch.setattr(app, 'create_app', lambda: client.application)
    messages = []
    class Mail:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message): messages.append(message)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', Mail)
    assert deliver_updates() == 1
    assert deliver_updates() == 0
    assert str(messages[0]['To']) == 'mail@example.com'
    assert 'private fixture' not in str(messages[0])
    assert 'sensitive update' not in str(messages[0])
    assert db.session.scalar(db.select(Notification)).emailed_at is not None
