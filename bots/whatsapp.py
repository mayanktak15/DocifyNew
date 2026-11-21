"""Twilio webhook; the configured public URL is used for signature validation."""
import os
from flask import Blueprint, abort, request
from app import limiter
from chatbot import respond
from bots.rate_limit import bot_limiter

webhook = Blueprint('whatsapp', __name__)


@webhook.post('/webhook/whatsapp')
@limiter.exempt
def whatsapp():
    token = os.environ.get('TWILIO_AUTH_TOKEN')
    public_url = os.environ.get('TWILIO_WEBHOOK_URL')
    if not token or not public_url:
        abort(503)
    try:
        from twilio.request_validator import RequestValidator
        from twilio.twiml.messaging_response import MessagingResponse
    except ImportError:
        abort(503)
    if not RequestValidator(token).validate(public_url, request.form, request.headers.get('X-Twilio-Signature', '')):
        abort(403)
    result = bot_limiter.check('whatsapp', request.form.get('From', ''))
    if result == 'unavailable':
        abort(503)
    if result == 'limited':
        abort(429)
    message = request.form.get('Body', '').strip()
    command, _, argument = message.partition(' ')
    if command in ('/link', '/consult', '/status', '/unlink'):
        from bots.accounts import private_command
        try:
            answer = private_command('whatsapp', request.form['From'], command[1:], argument)
        except Exception:
            abort(503)
    else:
        answer = respond(message[:1000])['reply'] if message else 'Send a question about the Docify prototype.'
    response = MessagingResponse()
    response.message(answer + '\n\nDocify is a prototype. Do not send personal health details. For emergencies, contact local emergency services.')
    return str(response), 200, {'Content-Type': 'application/xml'}
