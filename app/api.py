"""Bearer-token API. Tokens are never accepted from browser cookies."""
from datetime import datetime, timedelta, timezone
import hashlib
import uuid
from functools import wraps

import jwt
from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash
from sqlalchemy.exc import IntegrityError
from app import ChatHistory, Consultation, Notification, RevokedToken, User, audit, audit_access, claim_consultation, release_consultation, save_review, db, limiter, now

api = Blueprint('api', __name__)
STATUSES = ('pending', 'in_review', 'completed', 'cancelled')
PRIORITIES = ('low', 'normal', 'high', 'urgent')


def authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify(error='Invalid or expired token'), 401
        try:
            payload = jwt.decode(auth[7:], current_app.config['SECRET_KEY'], algorithms=['HS256'], options={'require': ['sub', 'iat', 'exp', 'jti', 'ver']})
            required_kind = 'refresh' if request.endpoint == 'api.refresh' else 'access'
            if payload.get('kind', 'access') != required_kind:
                raise ValueError('Wrong token type')
            g.user = db.session.get(User, int(payload['sub']))
            if not g.user or type(payload['ver']) is not int or payload['ver'] != g.user.token_version or not isinstance(payload['jti'], str) or len(payload['jti']) != 32:
                raise ValueError('Invalid user or token')
            digest = hashlib.sha256(payload['jti'].encode()).hexdigest()
            if db.session.execute(db.select(RevokedToken.id).filter_by(jti_hash=digest)).scalar_one_or_none() is not None:
                raise ValueError('Revoked token')
            g.token_payload = payload
            g.token_hash = digest
        except (jwt.InvalidTokenError, ValueError, TypeError):
            return jsonify(error='Invalid or expired token'), 401
        return fn(*args, **kwargs)
    return wrapper


def serialize(item):
    return {key: getattr(item, key) for key in ('id', 'symptoms', 'status', 'priority', 'doctor_notes', 'prescription')} | {'created_at': item.created_at.isoformat(), 'updated_at': item.updated_at.isoformat()}


def accessible(item):
    return item and not item.is_deleted and (item.user_id == g.user.id or (g.user.clinician_access and item.clinician_id == g.user.id))


@api.post('/auth/token')
@limiter.limit('10 per minute')
def token():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('email'), str) or not isinstance(data.get('password'), str):
        return jsonify(error='Invalid email or password'), 401
    user = db.session.execute(db.select(User).filter_by(email=data['email'].strip().lower())).scalar_one_or_none()
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify(error='Invalid email or password'), 401
    verified_version = user.token_version
    audit(user.id, 'ISSUE_TOKEN', 'user', user.id, [])
    db.session.commit()
    return token_pair(user, verified_version)


def token_pair(user, version):
    issued = now()
    def encode(kind, days):
        return jwt.encode({'sub': str(user.id), 'iat': issued, 'exp': issued + timedelta(days=days),
                           'jti': uuid.uuid4().hex, 'ver': version, 'kind': kind},
                          current_app.config['SECRET_KEY'], algorithm='HS256')
    return jsonify(token=encode('access', 1), refresh_token=encode('refresh', 7), expires_in=86400,
                   user={'id': user.id, 'name': user.name, 'email': user.email, 'role': user.role})


@api.post('/auth/refresh')
@authenticated
def refresh():
    version = g.token_payload['ver']
    db.session.add(RevokedToken(jti_hash=g.token_hash, user_id=g.user.id,
                                expires_at=datetime.fromtimestamp(g.token_payload['exp'], tz=timezone.utc)))
    audit(g.user.id, 'REFRESH_TOKEN', 'user', g.user.id, [])
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='Refresh token already used'), 401
    return token_pair(g.user, version)


@api.post('/auth/revoke')
@authenticated
def revoke_token():
    db.session.add(RevokedToken(jti_hash=g.token_hash, user_id=g.user.id,
                                expires_at=datetime.fromtimestamp(g.token_payload['exp'], tz=timezone.utc)))
    audit(g.user.id, 'REVOKE_TOKEN', 'user', g.user.id, [])
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return jsonify(success=True)


@api.post('/auth/revoke-all')
@authenticated
def revoke_all_tokens():
    user_id = g.user.id
    db.session.execute(db.update(User).where(User.id == user_id).values(token_version=User.token_version + 1))
    audit(user_id, 'REVOKE_TOKENS', 'user', user_id, ['token_version'])
    db.session.commit()
    return jsonify(success=True)


@api.route('/consultations', methods=['GET', 'POST'])
@authenticated
def consultations():
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Expected a JSON object'), 400
        symptoms, priority = data.get('symptoms'), data.get('priority', 'normal')
        if not isinstance(symptoms, str) or not symptoms.strip() or len(symptoms) > 5000 or priority not in PRIORITIES:
            return jsonify(error='Invalid symptoms or priority'), 400
        item = Consultation(user_id=g.user.id, symptoms=symptoms.strip(), priority=priority)
        db.session.add(item)
        db.session.flush()
        audit(g.user.id, 'INSERT', 'consultation', item.id, ['symptoms', 'priority'])
        db.session.commit()
        return jsonify(serialize(item)), 201
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    if page < 1 or per_page < 1 or per_page > 100:
        return jsonify(error='Invalid pagination'), 400
    query = db.select(Consultation).filter_by(is_deleted=False)
    if g.user.clinician_access:
        query = query.where((Consultation.user_id == g.user.id) | (Consultation.clinician_id == g.user.id))
    else:
        query = query.filter_by(user_id=g.user.id)
    status = request.args.get('status')
    if status:
        if status not in STATUSES:
            return jsonify(error='Invalid status'), 400
        query = query.filter_by(status=status)
    result = db.paginate(query.order_by(Consultation.created_at.desc()), page=page, per_page=per_page, error_out=False)
    audit_access(g.user.id, 'consultation', (item.id for item in result.items))
    return jsonify(consultations=[serialize(item) for item in result.items], pagination={'page': page, 'per_page': per_page, 'total': result.total, 'pages': result.pages})


@api.route('/consultations/<int:item_id>', methods=['GET', 'PATCH', 'DELETE'])
@authenticated
def consultation(item_id):
    item = db.session.get(Consultation, item_id)
    if not accessible(item):
        return jsonify(error='Not found'), 404
    if request.method == 'GET':
        audit_access(g.user.id, 'consultation', [item.id])
        return jsonify(serialize(item))
    if request.method == 'DELETE':
        if item.user_id != g.user.id:
            return jsonify(error='Forbidden'), 403
        item.is_deleted = True
        audit(g.user.id, 'SOFT_DELETE', 'consultation', item.id, ['is_deleted'])
        db.session.commit()
        return jsonify(success=True)
    if not g.user.clinician_access or item.clinician_id != g.user.id:
        return jsonify(error='Forbidden'), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data or set(data) - {'status', 'doctor_notes', 'prescription'}:
        return jsonify(error='Invalid review fields'), 400
    if 'status' in data and data['status'] not in ('in_review', 'completed', 'cancelled'):
        return jsonify(error='Invalid status'), 400
    for field in ('doctor_notes', 'prescription'):
        if field in data and (not isinstance(data[field], str) or len(data[field]) > 5000):
            return jsonify(error='Invalid review fields'), 400
    changes = {field: value.strip() if isinstance(value, str) else value for field, value in data.items()}
    if not save_review(item.id, g.user.id, changes):
        return jsonify(error='Consultation is no longer assigned to you'), 409
    return jsonify(serialize(db.session.get(Consultation, item_id)))


@api.get('/health')
def health():
    from sqlalchemy import text
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify(status='healthy', components={'database': {'status': 'up'}})
    except Exception:
        db.session.rollback()
        return jsonify(status='unhealthy', components={'database': {'status': 'down'}}), 503


@api.post('/chat')
@limiter.limit('10 per minute')
@authenticated
def chat():
    from app import ChatHistory
    from chatbot import respond
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('message'), str) or not data['message'].strip() or len(data['message']) > 5000:
        return jsonify(error='Please provide a message of up to 5,000 characters.'), 400
    message = data['message'].strip()
    result = respond(message)
    db.session.add(ChatHistory(user_id=g.user.id, query=message, response=result['reply'], provider=result['provider']))
    db.session.commit()
    return jsonify(result)


@api.post('/consultations/<int:item_id>/claim')
@authenticated
def claim(item_id):
    if not g.user.clinician_access:
        return jsonify(error='Forbidden'), 403
    if not claim_consultation(item_id, g.user.id):
        return jsonify(error='Consultation is not available'), 409
    return jsonify(success=True)


@api.get('/consultations/available')
@authenticated
def available():
    if not g.user.clinician_access:
        return jsonify(error='Forbidden'), 403
    rows = db.session.execute(db.select(Consultation.id, Consultation.created_at, Consultation.priority).where(Consultation.is_deleted.is_(False), Consultation.clinician_id.is_(None), Consultation.status.in_(('pending', 'in_review')), Consultation.user_id != g.user.id).order_by(Consultation.created_at).limit(50)).all()
    return jsonify(consultations=[{'id': row.id, 'created_at': row.created_at.isoformat(), 'priority': row.priority} for row in rows])


@api.post('/consultations/<int:item_id>/release')
@authenticated
def release(item_id):
    if not g.user.clinician_access:
        return jsonify(error='Forbidden'), 403
    if not release_consultation(item_id, g.user.id):
        return jsonify(error='Consultation cannot be released'), 409
    return jsonify(success=True)


@api.get('/notifications')
@authenticated
def notifications():
    page = request.args.get('page', 1, type=int)
    if page < 1:
        return jsonify(error='Invalid page'), 400
    result = db.paginate(db.select(Notification).filter_by(user_id=g.user.id).order_by(Notification.created_at.desc()), page=page, per_page=20, error_out=False)
    return jsonify(notifications=[{'id': item.id, 'consultation_id': item.consultation_id, 'message': item.message, 'created_at': item.created_at.isoformat(), 'read_at': item.read_at.isoformat() if item.read_at else None} for item in result.items], pagination={'page': page, 'pages': result.pages, 'total': result.total})


@api.post('/notifications/<int:notification_id>/read')
@authenticated
def notification_read(notification_id):
    item = db.session.get(Notification, notification_id)
    if not item or item.user_id != g.user.id:
        return jsonify(error='Not found'), 404
    if item.read_at is None:
        item.read_at = now()
        db.session.commit()
    return jsonify(success=True)


@api.get('/chat/history')
@authenticated
def chat_history():
    page = request.args.get('page', 1, type=int)
    if page < 1:
        return jsonify(error='Invalid page'), 400
    items = db.paginate(db.select(ChatHistory).filter_by(user_id=g.user.id).order_by(
        ChatHistory.created_at.desc(), ChatHistory.id.desc()), page=page, per_page=20, error_out=False)
    audit_access(g.user.id, 'chat_history', (item.id for item in items.items))
    return jsonify(entries=[{'id': item.id, 'query': item.query, 'response': item.response, 'provider': item.provider, 'created_at': item.created_at.isoformat()} for item in items.items], pagination={'page': page, 'pages': items.pages, 'total': items.total})


@api.delete('/chat/history/<int:entry_id>')
@authenticated
def delete_chat_history(entry_id):
    item = db.session.get(ChatHistory, entry_id)
    if not item or item.user_id != g.user.id:
        return jsonify(error='Not found'), 404
    audit(g.user.id, 'HARD_DELETE', 'chat_history', item.id, [])
    db.session.delete(item)
    db.session.commit()
    return jsonify(success=True)
