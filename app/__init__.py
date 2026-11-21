import os
import ipaddress
import secrets
from io import BytesIO
from urllib.parse import urlsplit
from functools import wraps
from datetime import datetime, timezone, timedelta

from flask import current_app, Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
import click
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import CheckConstraint
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=['200 per day', '50 per hour'])


def now():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(15), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='patient', server_default='patient')
    token_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    email_updates = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    reviewed_by = db.Column(db.String(100))
    verification_ref = db.Column(db.String(120))
    verified_at = db.Column(db.DateTime(timezone=True))

    @property
    def clinician_access(self):
        return self.role == 'clinician' and (
            current_app.config['DOCIFY_ENV'] != 'production' or self.verified_at is not None
        )

    age = db.Column(db.Integer)
    gender = db.Column(db.String(30))
    blood_group = db.Column(db.String(5))
    medical_history = db.Column(db.Text)
    allergies = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class BrowserSession(db.Model):
    id = db.Column(db.String(48), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    browser = db.Column(db.String(180), nullable=False)


class Consultation(db.Model):
    __table_args__ = (CheckConstraint("status IN ('pending','in_review','completed','cancelled')"), CheckConstraint("priority IN ('low','normal','high','urgent')"))
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    symptoms = db.Column(db.Text, nullable=False)
    clinician_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    priority = db.Column(db.String(10), default='normal', nullable=False)
    doctor_notes = db.Column(db.Text)
    prescription = db.Column(db.Text)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    query = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    provider = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(30), nullable=False)
    record_type = db.Column(db.String(30), nullable=False)
    record_id = db.Column(db.Integer, nullable=False)
    changed_fields = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class RevokedToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jti_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultation.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    read_at = db.Column(db.DateTime(timezone=True))
    email_pending = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)
    emailed_at = db.Column(db.DateTime(timezone=True))


def notify_patient(user_id, consultation_id, message):
    db.session.add(Notification(user_id=user_id, consultation_id=consultation_id, message=message, email_pending=db.session.get(User, user_id).email_updates))


def audit(actor_id, action, record_type, record_id, fields):
    # Record field names only; avoid duplicating sensitive medical information.
    db.session.add(AuditLog(actor_id=actor_id, action=action, record_type=record_type, record_id=record_id, changed_fields=fields))


def audit_access(actor_id, record_type, record_ids):
    """Record access before responding, without storing clinical content."""
    ids = list(record_ids)
    for record_id in ids:
        audit(actor_id, 'VIEW', record_type, record_id, [])
    if ids:
        db.session.commit()


def lock_clinician(user_id):
    # PostgreSQL row locks serialize review and assignment with role removal.
    return db.session.execute(db.select(User.id).where(
        User.id == user_id, User.role == 'clinician'
    ).with_for_update()).scalar_one_or_none() is not None


def claim_consultation(item_id, clinician_id):
    """Claim one pending request atomically, without overwriting another claim."""
    if not lock_clinician(clinician_id):
        db.session.rollback()
        return False
    result = db.session.execute(
        db.update(Consultation)
        .where(Consultation.id == item_id, Consultation.clinician_id.is_(None),
               Consultation.is_deleted.is_(False), Consultation.status.in_(('pending', 'in_review')),
               Consultation.user_id != clinician_id)
        .values(clinician_id=clinician_id, status='in_review', updated_at=now())
    )
    if result.rowcount != 1:
        db.session.rollback()
        return False
    item = db.session.get(Consultation, item_id)
    audit(clinician_id, 'CLAIM', 'consultation', item_id, ['clinician_id', 'status'])
    notify_patient(item.user_id, item_id, 'A clinician has claimed your consultation in the prototype.')
    db.session.commit()
    return True


def release_consultation(item_id, clinician_id):
    if not lock_clinician(clinician_id):
        db.session.rollback()
        return False
    result = db.session.execute(db.update(Consultation).where(
        Consultation.id == item_id, Consultation.clinician_id == clinician_id,
        Consultation.is_deleted.is_(False), Consultation.status == 'in_review'
    ).values(clinician_id=None, updated_at=now()))
    if result.rowcount != 1:
        db.session.rollback()
        return False
    item = db.session.get(Consultation, item_id)
    audit(clinician_id, 'RELEASE', 'consultation', item_id, ['clinician_id'])
    notify_patient(item.user_id, item_id, 'Your consultation is awaiting another clinician in the prototype.')
    db.session.commit()
    return True


def save_review(item_id, clinician_id, changes):
    if not lock_clinician(clinician_id):
        db.session.rollback()
        return False
    # Verify ownership as part of the write so a released/reassigned record
    # cannot be changed by a stale clinician request.
    result = db.session.execute(db.update(Consultation).where(
        Consultation.id == item_id, Consultation.clinician_id == clinician_id,
        Consultation.is_deleted.is_(False)
    ).values(**changes, updated_at=now()))
    if result.rowcount != 1:
        db.session.rollback()
        return False
    item = db.session.get(Consultation, item_id)
    audit(clinician_id, 'UPDATE', 'consultation', item_id, sorted(changes))
    notify_patient(item.user_id, item_id, 'Your consultation has been updated in the prototype.')
    db.session.commit()
    return True


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('user_id') or not db.session.get(User, session['user_id']):
            session.clear()
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped


def validate_configuration(config):
    """Fail closed when explicit production configuration is unsafe."""
    environment = config.get('DOCIFY_ENV', 'development')
    if environment not in ('development', 'production'):
        raise RuntimeError('DOCIFY_ENV must be development or production')
    if environment != 'production':
        return
    problems = []
    secret = config.get('SECRET_KEY')
    if not isinstance(secret, str) or len(secret.encode('utf-8')) < 32 or secret in {
        'development-only-change-me-before-deployment-1234', 'change-me-to-a-long-random-secret'
    }:
        problems.append('SECRET_KEY must be a unique, non-default secret of at least 32 bytes')
    database = str(config.get('SQLALCHEMY_DATABASE_URI', ''))
    if not database.startswith(('postgresql://', 'postgresql+psycopg://')):
        problems.append('DATABASE_URL must use PostgreSQL')
    try:
        redis_url = urlsplit(str(config.get('RATELIMIT_STORAGE_URI', '')))
        if redis_url.scheme not in ('redis', 'rediss') or not redis_url.hostname:
            raise ValueError('Invalid Redis address')
    except ValueError:
        problems.append('RATELIMIT_STORAGE_URI must use shared Redis storage')
    if not config.get('SESSION_COOKIE_SECURE') or not config.get('SESSION_COOKIE_HTTPONLY') or config.get('SESSION_COOKIE_SAMESITE') not in ('Lax', 'Strict'):
        problems.append('Session cookies must use Secure, HTTPOnly and SameSite')
    if not config.get('WTF_CSRF_ENABLED', True) or not config.get('RATELIMIT_ENABLED', True):
        problems.append('CSRF protection and rate limiting must be enabled')
    if config.get('DEBUG') or os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes', 'on'):
        problems.append('Debug mode must be disabled')
    if problems:
        raise RuntimeError('Invalid production configuration: ' + '; '.join(problems))


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY', 'development-only-change-me-before-deployment-1234'), SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///docify.db'), SQLALCHEMY_TRACK_MODIFICATIONS=False, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', '').lower() == 'true', RATELIMIT_STORAGE_URI=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'))
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql+psycopg://', 1)
    elif app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgresql://', 'postgresql+psycopg://', 1)
    app.config['DOCIFY_ENV'] = os.environ.get('DOCIFY_ENV', 'development').lower()
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)
    app.config['SESSION_REFRESH_EACH_REQUEST'] = False
    if test_config:
        app.config.update(test_config)
    validate_configuration(app.config)
    if app.config["DOCIFY_ENV"] == "production":
        from app.request_log import configure
        configure(app)
    os.makedirs(app.instance_path, exist_ok=True)
    if os.getenv('DOCIFY_REDIS_SESSIONS', '').lower() == 'true':
        from flask_session import Session
        import redis
        app.config.update(SESSION_TYPE='redis', SESSION_KEY_PREFIX='docify:session:',
                          SESSION_REDIS=redis.Redis.from_url(os.environ['REDIS_URL'], socket_timeout=2))
        Session(app)
    db.init_app(app)
    Migrate(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.api import api
    app.register_blueprint(api, url_prefix='/api/v1')
    csrf.exempt(api)  # API endpoints authenticate with explicit bearer tokens, not cookies.
    from bots.whatsapp import webhook
    app.register_blueprint(webhook)
    csrf.exempt(webhook)  # Twilio requests are authenticated by signature.

    @app.cli.command('purge-chat-history')
    @click.option('--older-than-days', required=True, type=click.IntRange(1, 36500), help='Delete entries strictly older than this many days.')
    @click.option('--batch-size', default=500, show_default=True, type=click.IntRange(1, 10000))
    @click.option('--execute', is_flag=True, help='Actually delete the selected entries; the default is a dry run.')
    def purge_chat_history(older_than_days, batch_size, execute):
        """Review or delete a bounded batch of old chat entries."""
        from sqlalchemy import func
        cutoff = now() - timedelta(days=older_than_days)
        if not execute:
            total = db.session.execute(db.select(func.count()).select_from(ChatHistory).where(
                ChatHistory.created_at < cutoff)).scalar_one()
            click.echo(f'Dry run: {total} eligible; up to {min(total, batch_size)} would be deleted. No changes made.')
            return
        entries = db.session.execute(db.select(ChatHistory).where(ChatHistory.created_at < cutoff)
            .order_by(ChatHistory.created_at, ChatHistory.id).limit(batch_size)
            .with_for_update(skip_locked=True)).scalars().all()
        for entry in entries:
            audit(None, 'HARD_DELETE', 'chat_history', entry.id, [])
            db.session.delete(entry)
        db.session.commit()
        click.echo(f'Deleted {len(entries)} chat entries from the active database.')

    @app.cli.command('purge-revoked-tokens')
    def purge_revoked_tokens():
        """Remove token revocations after their tokens have expired."""
        result = db.session.execute(db.delete(RevokedToken).where(RevokedToken.expires_at < now()))
        db.session.commit()
        click.echo(f'Removed {result.rowcount} expired token revocations.')

    @app.cli.command('set-clinician')
    @click.argument('email')
    @click.option('--reviewer', help='Identifier of the administrator who checked the credentials.')
    @click.option('--reference', help='Reference to the completed identity and license review.')
    def set_clinician(email, reviewer, reference):
        """Grant clinician access to an existing account locally."""
        user = db.session.execute(db.select(User).filter_by(email=email.strip().lower())).scalar_one_or_none()
        if not user:
            raise click.ClickException('User not found')
        reviewer = (reviewer or '').strip()
        reference = (reference or '').strip()
        if reviewer or reference or app.config['DOCIFY_ENV'] == 'production':
            if not (0 < len(reviewer) <= 100 and 0 < len(reference) <= 120):
                raise click.ClickException('Supply --reviewer and --reference for a completed credential review.')
            user.reviewed_by = reviewer
            user.verification_ref = reference
            user.verified_at = now()
            audit(None, 'CREDENTIAL_REVIEW', 'user', user.id, ['reviewed_by', 'verification_ref', 'verified_at'])
        user.role = 'clinician'
        audit(None, 'ROLE_CHANGE', 'user', user.id, ['role'])
        db.session.commit()
        click.echo('Clinician role granted.')

    @app.cli.command('assign-consultation')
    @click.argument('consultation_id', type=int)
    @click.argument('clinician_email')
    def assign_consultation(consultation_id, clinician_email):
        """Assign an active consultation to a clinician."""
        clinician = db.session.execute(db.select(User).where(
            User.email == clinician_email.strip().lower()).with_for_update()).scalar_one_or_none()
        if not clinician or not clinician.clinician_access:
            raise click.ClickException('Clinician not found')
        item = db.session.execute(db.select(Consultation).where(
            Consultation.id == consultation_id).with_for_update()).scalar_one_or_none()
        if not item or item.is_deleted or item.status not in ('pending', 'in_review') or item.user_id == clinician.id:
            raise click.ClickException('Consultation cannot be assigned')
        if item.clinician_id == clinician.id:
            click.echo('Consultation is already assigned to this clinician.')
            return
        item.clinician_id = clinician.id
        item.status = 'in_review'
        audit(None, 'ASSIGN', 'consultation', item.id, ['clinician_id', 'status'])
        notify_patient(item.user_id, item.id, 'Your consultation has been assigned to a clinician in the prototype.')
        db.session.commit()
        click.echo('Consultation assigned.')

    @app.cli.command('remove-clinician')
    @click.argument('email')
    def remove_clinician(email):
        """Remove clinician access and return active assignments to the queue."""
        user = db.session.execute(db.select(User).where(
            User.email == email.strip().lower()).with_for_update()).scalar_one_or_none()
        if not user:
            raise click.ClickException('User not found')
        if user.role != 'clinician':
            click.echo('Account is not a clinician; no changes made.')
            return
        items = db.session.execute(db.select(Consultation).filter_by(
            clinician_id=user.id, is_deleted=False, status='in_review')).scalars().all()
        for item in items:
            item.clinician_id = None
            audit(None, 'RELEASE', 'consultation', item.id, ['clinician_id'])
            notify_patient(item.user_id, item.id, 'Your consultation is awaiting another clinician in the prototype.')
        user.reviewed_by = user.verification_ref = user.verified_at = None
        user.role = 'patient'
        audit(None, 'ROLE_CHANGE', 'user', user.id, ['role'])
        db.session.commit()
        click.echo(f'Clinician access removed; {len(items)} active consultation(s) returned to the queue.')

    def start_browser_session(user, version):
        session_id = secrets.token_hex(24)
        db.session.execute(db.delete(BrowserSession).where(
            BrowserSession.user_id == user.id, BrowserSession.expires_at <= now()))
        db.session.add(BrowserSession(id=session_id, user_id=user.id,
            browser=request.user_agent.string[:180] or 'Unknown browser',
            expires_at=now() + app.permanent_session_lifetime))
        db.session.commit()
        session.clear()
        session.update(user_id=user.id, session_version=version, browser_session=session_id)
        session.permanent = True
        if hasattr(app.session_interface, 'regenerate'):
            app.session_interface.regenerate(session)

    @app.before_request
    def validate_web_session():
        user_id = session.get('user_id')
        if user_id is not None:
            user = db.session.get(User, user_id) if type(user_id) is int else None
            session_id = session.get('browser_session')
            active = session_id and db.session.scalar(db.select(BrowserSession.id).where(
                BrowserSession.id == session_id, BrowserSession.user_id == user_id,
                BrowserSession.expires_at > now()))
            if not active or not user or type(session.get('session_version')) is not int or session['session_version'] != user.session_version:
                session.clear()

    @app.before_request
    def filter_ip():
        # Only trust the direct peer address. Proxy forwarding requires explicit
        # deployment-specific trusted-proxy configuration, never raw headers.
        ranges = os.environ.get('ALLOWED_IPS', '').strip()
        if ranges and request.endpoint not in ('health', 'api.health', 'ready'):
            try:
                address = ipaddress.ip_address(request.remote_addr or '')
                if not any(address in ipaddress.ip_network(cidr.strip(), strict=False) for cidr in ranges.split(',')):
                    abort(403)
            except ValueError:
                abort(403)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        return response

    @app.context_processor
    def current_user():
        return {'current_user': db.session.get(User, session.get('user_id')) if session.get('user_id') else None}

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/ready')
    @limiter.exempt
    def ready():
        from app.readiness import readiness
        result, status = readiness()
        return jsonify(result), status

    @app.get('/health')
    def health():
        from sqlalchemy import text
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='healthy', database='up')
        except Exception:
            db.session.rollback()
            return jsonify(status='unhealthy', database='down'), 503

    @app.route('/register', methods=['GET', 'POST'])
    @limiter.limit('5 per minute')
    def register():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            password = request.form.get('password', '')
            if not name or len(name) > 100 or '@' not in email or len(email) > 120 or not phone or len(phone) > 15 or len(password) < 8 or len(password) > 128:
                flash('Please provide a name, valid email, phone, and password of at least 8 characters.', 'error')
            elif db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none():
                flash('An account with that email already exists.', 'error')
            else:
                user = User(name=name, email=email, phone=phone, password_hash=generate_password_hash(password, method='pbkdf2:sha256'))
                db.session.add(user)
                db.session.flush()
                audit(user.id, 'REGISTER', 'user', user.id, [])
                start_browser_session(user, user.session_version)
                return redirect(url_for('dashboard'))
        return render_template('auth.html', mode='register')

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('10 per minute')
    def login():
        if request.method == 'POST':
            user = db.session.execute(db.select(User).filter_by(email=request.form.get('email', '').strip().lower())).scalar_one_or_none()
            if user and check_password_hash(user.password_hash, request.form.get('password', '')):
                verified_version = user.session_version
                audit(user.id, 'LOGIN', 'user', user.id, [])
                start_browser_session(user, verified_version)
                return redirect(url_for('dashboard'))
            flash('Invalid email or password.', 'error')
        return render_template('auth.html', mode='login')

    @app.post('/logout')
    def logout():
        if session.get('user_id'):
            db.session.execute(db.delete(BrowserSession).where(BrowserSession.id == session['browser_session']))
            audit(session['user_id'], 'LOGOUT', 'user', session['user_id'], [])
            db.session.commit()
        session.clear()
        return redirect(url_for('index'))

    @app.route('/dashboard', methods=['GET', 'POST'])
    @login_required
    def dashboard():
        if request.method == 'POST':
            symptoms = request.form.get('symptoms', '').strip()
            priority = request.form.get('priority', 'normal')
            if not symptoms or len(symptoms) > 5000 or priority not in ('low', 'normal', 'high', 'urgent'):
                flash('Please provide symptoms (up to 5,000 characters) and a valid priority.', 'error')
            else:
                item = Consultation(user_id=session['user_id'], symptoms=symptoms, priority=priority)
                db.session.add(item)
                db.session.flush()
                audit(session['user_id'], 'INSERT', 'consultation', item.id, ['symptoms', 'priority'])
                db.session.commit()
                flash('Your consultation was saved.', 'success')
                return redirect(url_for('dashboard'))
        page = request.args.get('page', 1, type=int)
        consultations = db.paginate(db.select(Consultation).filter_by(user_id=session['user_id'], is_deleted=False).order_by(Consultation.created_at.desc()), page=max(page, 1), per_page=10, error_out=False)
        audit_access(session['user_id'], 'consultation', (item.id for item in consultations.items))
        return render_template('dashboard.html', consultations=consultations)

    @app.post('/consultations/export')
    @login_required
    @limiter.limit('5 per minute')
    def export_consultations():
        from app.utils.csv_export import consultation_csv
        # Bound memory use and audit volume; never silently truncate the export.
        items = db.session.execute(db.select(Consultation).filter_by(
            user_id=session['user_id'], is_deleted=False
        ).order_by(Consultation.id).limit(5001)).scalars().all()
        if len(items) > 5000:
            flash('This export is limited to 5,000 consultations.', 'error')
            return redirect(url_for('dashboard'))
        content = consultation_csv(items)
        audit(session['user_id'], 'EXPORT', 'user', session['user_id'], ['consultations'])
        for item in items:
            audit(session['user_id'], 'EXPORT', 'consultation', item.id, [])
        db.session.commit()
        return send_file(BytesIO(content), mimetype='text/csv', as_attachment=True,
                         download_name='docify-consultations.csv', max_age=0)

    @app.post('/consultations/<int:consultation_id>/edit')
    @login_required
    def edit_consultation(consultation_id):
        item = db.session.get(Consultation, consultation_id)
        if not item or item.user_id != session['user_id'] or item.is_deleted:
            abort(404)
        if item.status != 'pending':
            flash('Only pending consultations can be edited.', 'error')
            return redirect(url_for('dashboard'))
        symptoms = request.form.get('symptoms', '').strip()
        priority = request.form.get('priority', '')
        if not symptoms or len(symptoms) > 5000 or priority not in ('low', 'normal', 'high', 'urgent'):
            flash('Please check the symptoms and priority.', 'error')
        else:
            item.symptoms, item.priority = symptoms, priority
            audit(session['user_id'], 'UPDATE', 'consultation', item.id, ['symptoms', 'priority'])
            db.session.commit()
            flash('Consultation updated.', 'success')
        return redirect(url_for('dashboard'))

    @app.post('/consultations/<int:consultation_id>/delete')
    @login_required
    def delete_consultation(consultation_id):
        item = db.session.get(Consultation, consultation_id)
        if not item or item.user_id != session['user_id'] or item.is_deleted:
            abort(404)
        item.is_deleted = True
        audit(session['user_id'], 'SOFT_DELETE', 'consultation', item.id, ['is_deleted'])
        db.session.commit()
        flash('Consultation removed.', 'success')
        return redirect(url_for('dashboard'))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        user = db.session.get(User, session['user_id'])
        if request.method == 'POST':
            age = request.form.get('age', '').strip()
            if age and (not age.isdigit() or not 0 <= int(age) <= 120):
                flash('Please enter a valid age.', 'error')
            else:
                user.age = int(age) if age else None
                user.gender = request.form.get('gender', '').strip()[:30]
                user.blood_group = request.form.get('blood_group', '').strip()[:5]
                user.allergies = request.form.get('allergies', '').strip()[:5000]
                user.medical_history = request.form.get('medical_history', '').strip()[:5000]
                audit(user.id, 'UPDATE', 'user', user.id, ['age', 'gender', 'blood_group', 'allergies', 'medical_history'])
                db.session.commit()
                flash('Profile updated.', 'success')
                return redirect(url_for('profile'))
        audit_access(user.id, 'user', [user.id])
        browsers = db.session.scalars(db.select(BrowserSession).where(
            BrowserSession.user_id == user.id, BrowserSession.expires_at > now()
        ).order_by(BrowserSession.created_at.desc())).all()
        return render_template('profile.html', user=user, browsers=browsers)

    @app.get('/clinician')
    @login_required
    def clinician_queue():
        if not db.session.get(User, session['user_id']).clinician_access:
            abort(403)
        page = max(request.args.get('page', 1, type=int), 1)
        items = db.paginate(db.select(Consultation).filter_by(is_deleted=False, clinician_id=session['user_id']).order_by(Consultation.created_at.desc()), page=page, per_page=10, error_out=False)
        available = db.session.execute(db.select(Consultation.id, Consultation.created_at, Consultation.priority).where(Consultation.is_deleted.is_(False), Consultation.clinician_id.is_(None), Consultation.status.in_(('pending', 'in_review')), Consultation.user_id != session['user_id']).order_by(Consultation.created_at).limit(50)).all()
        audit_access(session['user_id'], 'consultation', (item.id for item in items.items))
        return render_template('clinician.html', consultations=items, available=available)

    @app.post('/clinician/<int:consultation_id>/claim')
    @login_required
    def clinician_claim(consultation_id):
        if not db.session.get(User, session['user_id']).clinician_access:
            abort(403)
        if claim_consultation(consultation_id, session['user_id']):
            flash('Consultation assigned to you.', 'success')
        else:
            flash('Consultation is no longer available.', 'error')
        return redirect(url_for('clinician_queue'))

    @app.post('/clinician/<int:consultation_id>/release')
    @login_required
    def clinician_release(consultation_id):
        if not db.session.get(User, session['user_id']).clinician_access:
            abort(403)
        if release_consultation(consultation_id, session['user_id']):
            flash('Request returned to the available queue.', 'success')
        else:
            flash('This request cannot be released.', 'error')
        return redirect(url_for('clinician_queue'))

    @app.post('/clinician/<int:consultation_id>')
    @login_required
    def clinician_review(consultation_id):
        if not db.session.get(User, session['user_id']).clinician_access:
            abort(403)
        item = db.session.get(Consultation, consultation_id)
        if not item or item.is_deleted or item.clinician_id != session['user_id']:
            abort(404)
        status = request.form.get('status', '')
        notes = request.form.get('doctor_notes', '').strip()
        prescription = request.form.get('prescription', '').strip()
        if status not in ('in_review', 'completed', 'cancelled') or len(notes) > 5000 or len(prescription) > 5000:
            flash('Please check the review fields.', 'error')
        else:
            if save_review(item.id, session['user_id'], {'status': status, 'doctor_notes': notes, 'prescription': prescription}):
                flash('Review saved.', 'success')
            else:
                flash('This request is no longer assigned to you.', 'error')
        return redirect(url_for('clinician_queue'))

    @app.post('/profile/password')
    @login_required
    @limiter.limit('5 per minute')
    def change_password():
        user = db.session.get(User, session['user_id'])
        current = request.form.get('current_password', '')
        new = request.form.get('new_password', '')
        confirmation = request.form.get('confirm_password', '')
        if len(current) > 128 or not check_password_hash(user.password_hash, current):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('profile'))
        if not 8 <= len(new) <= 128 or new != confirmation:
            flash('New passwords must match and contain 8 to 128 characters.', 'error')
            return redirect(url_for('profile'))
        if current == new:
            flash('Choose a new password that differs from the current password.', 'error')
            return redirect(url_for('profile'))
        old_hash = user.password_hash
        new_hash = generate_password_hash(new, method='pbkdf2:sha256')
        result = db.session.execute(db.update(User).where(
            User.id == user.id, User.password_hash == old_hash,
            User.session_version == session['session_version']
        ).values(password_hash=new_hash, token_version=User.token_version + 1,
                 session_version=User.session_version + 1))
        if result.rowcount != 1:
            db.session.rollback()
            session.clear()
            flash('Your session has changed. Please sign in again.', 'error')
            return redirect(url_for('login'))
        db.session.execute(db.delete(BrowserSession).where(BrowserSession.user_id == user.id))
        audit(user.id, 'PASSWORD_CHANGE', 'user', user.id, ['password_hash', 'token_version', 'session_version'])
        db.session.commit()
        session.clear()
        flash('Password changed. Please sign in again.', 'success')
        return redirect(url_for('login'))

    @app.post('/profile/email-updates')
    @login_required
    def email_preferences():
        user = db.session.get(User, session['user_id'])
        user.email_updates = request.form.get('updates') == 'on'
        if not user.email_updates:
            db.session.execute(db.update(Notification).where(Notification.user_id == user.id).values(email_pending=False))
        audit(user.id, 'UPDATE', 'user', user.id, ['email_updates'])
        db.session.commit()
        flash('Email preference saved.', 'success')
        return redirect(url_for('profile'))

    @app.post('/profile/link-bot')
    @login_required
    @limiter.limit('5 per minute')
    def link_bot():
        from bots.accounts import PLATFORMS, pairing_code
        platform = request.form.get('platform')
        if platform not in PLATFORMS:
            abort(400)
        user = db.session.get(User, session['user_id'])
        try:
            code = pairing_code(platform, user)
        except Exception:
            flash('Pairing service unavailable.', 'error')
            return redirect(url_for('profile'))
        return render_template('pair.html', platform=platform, code=code)

    @app.post('/profile/sessions/<session_id>/revoke')
    @login_required
    def revoke_browser(session_id):
        user_id = session['user_id']
        removed = db.session.execute(db.delete(BrowserSession).where(
            BrowserSession.id == session_id, BrowserSession.user_id == user_id))
        if not removed.rowcount:
            abort(404)
        audit(user_id, 'REVOKE_SESSION', 'user', user_id, [])
        db.session.commit()
        if session_id == session['browser_session']:
            session.clear()
            return redirect(url_for('login'))
        return redirect(url_for('profile'))

    @app.post('/profile/sign-out-all')
    @login_required
    def sign_out_all():
        user_id = session['user_id']
        db.session.execute(db.update(User).where(User.id == user_id).values(session_version=User.session_version + 1))
        db.session.execute(db.delete(BrowserSession).where(BrowserSession.user_id == user_id))
        audit(user_id, 'REVOKE_SESSIONS', 'user', user_id, ['session_version'])
        db.session.commit()
        session.clear()
        flash('All browser sessions have been signed out.', 'success')
        return redirect(url_for('login'))

    @app.post('/profile/revoke-api-tokens')
    @login_required
    def revoke_api_tokens():
        user_id = session['user_id']
        db.session.execute(db.update(User).where(User.id == user_id).values(token_version=User.token_version + 1))
        audit(user_id, 'REVOKE_TOKENS', 'user', user_id, ['token_version'])
        db.session.commit()
        flash('All API tokens for your account have been revoked.', 'success')
        return redirect(url_for('profile'))

    @app.get('/chat-history')
    @login_required
    def chat_history():
        page = max(request.args.get('page', 1, type=int), 1)
        items = db.paginate(db.select(ChatHistory).filter_by(user_id=session['user_id']).order_by(
            ChatHistory.created_at.desc(), ChatHistory.id.desc()), page=page, per_page=20, error_out=False)
        audit_access(session['user_id'], 'chat_history', (item.id for item in items.items))
        return render_template('chat_history.html', entries=items)

    @app.post('/chat-history/<int:entry_id>/delete')
    @login_required
    def delete_chat_history(entry_id):
        item = db.session.get(ChatHistory, entry_id)
        if not item or item.user_id != session['user_id']:
            abort(404)
        audit(session['user_id'], 'HARD_DELETE', 'chat_history', item.id, [])
        db.session.delete(item)
        db.session.commit()
        flash('Chat entry deleted.', 'success')
        return redirect(url_for('chat_history'))

    @app.get('/notifications')
    @login_required
    def notifications():
        page = max(request.args.get('page', 1, type=int), 1)
        items = db.paginate(db.select(Notification).filter_by(user_id=session['user_id']).order_by(Notification.created_at.desc()), page=page, per_page=20, error_out=False)
        return render_template('notifications.html', notifications=items)

    @app.post('/notifications/<int:notification_id>/read')
    @login_required
    def notification_read(notification_id):
        item = db.session.get(Notification, notification_id)
        if not item or item.user_id != session['user_id']:
            abort(404)
        if item.read_at is None:
            item.read_at = now()
            db.session.commit()
        return redirect(url_for('notifications'))

    @app.get('/faq')
    def faq():
        from chatbot.service import documents
        return render_template('faq.html', entries=documents())

    @app.post('/chatbot')
    @limiter.limit('10 per minute')
    def chatbot():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Expected a JSON object.'), 400
        message = data.get('message', '')
        if not isinstance(message, str) or not message.strip() or len(message) > 5000:
            return jsonify(error='Please provide a message of up to 5,000 characters.'), 400
        message = message.strip()
        from chatbot import respond
        result = respond(message)
        reply = result['reply']
        if session.get('user_id') and db.session.get(User, session['user_id']):
            db.session.add(ChatHistory(user_id=session['user_id'], query=message, response=reply, provider=result['provider']))
            db.session.commit()
        return jsonify(result)

    return app
