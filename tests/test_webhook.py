from test_core import client

def test_whatsapp_fails_closed_without_credentials(client, monkeypatch):
    monkeypatch.delenv('TWILIO_AUTH_TOKEN', raising=False)
    monkeypatch.delenv('TWILIO_WEBHOOK_URL', raising=False)
    assert client.post('/webhook/whatsapp', data={'Body': 'hello'}).status_code == 503


def test_whatsapp_validates_signature(client, monkeypatch):
    import pytest
    RequestValidator = pytest.importorskip('twilio.request_validator').RequestValidator
    url = 'https://example.org/webhook/whatsapp'
    token = 'test-secret'
    form = {'Body': 'How do I log out?', 'From': 'whatsapp:+10000000000'}
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', token)
    monkeypatch.setenv('TWILIO_WEBHOOK_URL', url)
    assert client.post('/webhook/whatsapp', data=form).status_code == 403
    signature = RequestValidator(token).compute_signature(url, form)
    result = client.post('/webhook/whatsapp', data=form, headers={'X-Twilio-Signature': signature})
    assert result.status_code == 200
    assert b'Log out' in result.data
