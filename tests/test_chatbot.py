from test_core import client
from chatbot.service import respond, retrieve


def test_faq_retrieval_and_fallback():
    assert 'dashboard' in respond('How do I submit a consultation?')['reply'].lower()
    assert respond('How do I log out?')['provider'] == 'faq'
    assert retrieve('quasar nebula unrelated') is None
    assert respond('quasar nebula unrelated')['provider'] == 'fallback'


def test_emergencies_take_precedence_over_faq():
    result = respond('How do I submit a consultation for chest pain?')
    assert 'emergency' in result['reply'].lower()
    assert result['provider'] == 'fallback'


def test_api_chat_requires_auth(client):
    assert client.post('/api/v1/chat', json={'message': 'hello'}).status_code == 401


def test_fever_question_gets_relevant_guidance_before_faq():
    for question in ('fever', 'i am feeling fever', 'How do I submit a consultation for fever?'):
        reply = respond(question)
        assert reply['provider'] == 'health_guidance'
        assert 'temperature' in reply['reply'] and 'fluids' in reply['reply']
    assert respond('fever and chest pain')['provider'] == 'fallback'


def test_cold_question_clarifies_and_emergencies_take_precedence():
    for question in ('i am feeling cold', 'I have a cold', 'I have chills'):
        reply = respond(question)
        assert reply['provider'] == 'health_guidance'
        assert 'shivery' in reply['reply'] and 'temperature' in reply['reply']
    assert respond('cold and difficulty breathing')['provider'] == 'fallback'


def test_general_health_question_returns_sourced_answer():
    result = respond('How can I sleep better?')
    assert result['provider'] == 'health_guidance'
    assert 'nhs.uk' in result['reply']
    assert 'caffeine' in result['reply']
