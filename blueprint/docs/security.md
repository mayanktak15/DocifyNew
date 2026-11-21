# 🔒 Security Guide

---

## 1. Defense-in-Depth Architecture

```
Internet → Nginx (TLS) → IP Filter → Rate Limiter → CSRF → Auth → Input Validation → ORM → DB
```

| Layer | Technology | Protection Against |
|-------|------------|-------------------|
| TLS | Nginx + Let's Encrypt | Man-in-the-middle, eavesdropping |
| IP Filter | Custom middleware | Unauthorized network access |
| Rate Limiter | Flask-Limiter + Redis | DDoS, brute force, abuse |
| CSRF | Flask-WTF tokens | Cross-site request forgery |
| Auth | Session + JWT | Unauthorized access |
| Input Validation | Form validation, type checking | Injection, XSS |
| ORM | SQLAlchemy parameterized queries | SQL injection |
| Headers | Custom middleware | Clickjacking, MIME sniffing |
| Cookies | HTTPOnly, SameSite, Secure | Session hijacking, CSRF |
| Audit | Event listeners | Accountability, forensics |

---

## 2. Authentication

### 2.1 Password Security

```python
# Hashing (registration)
from werkzeug.security import generate_password_hash, check_password_hash

password_hash = generate_password_hash(password, method='pbkdf2:sha256')
# Produces: pbkdf2:sha256:600000$salt$hash

# Verification (login)
is_valid = check_password_hash(stored_hash, provided_password)
```

- **Algorithm**: PBKDF2-SHA256 with 600,000 iterations
- **Salt**: Random per-password, stored in the hash string
- **Never**: Store plaintext, use MD5/SHA1, use unsalted hashes

### 2.2 Session Management

```python
# Configuration
SESSION_COOKIE_HTTPONLY = True     # JavaScript cannot read cookie
SESSION_COOKIE_SAMESITE = 'Lax'   # Prevents CSRF via cross-site requests
SESSION_COOKIE_SECURE = True      # Only sent over HTTPS (production)
WTF_CSRF_TIME_LIMIT = 3600       # CSRF tokens valid for 1 hour
```

### 2.3 JWT for API/Bots

```python
import jwt

def generate_token(user_id: int, secret: str, expires_in: int = 86400) -> str:
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, secret, algorithm='HS256')

def verify_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
```

---

## 3. CSRF Protection

### 3.1 HTML Forms

```html
<form method="POST" action="/dashboard">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <!-- form fields -->
</form>
```

### 3.2 AJAX Requests

```javascript
// Get CSRF token from meta tag or template variable
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

fetch('/chatbot', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
    },
    body: JSON.stringify({ message: 'Hello' })
});
```

---

## 4. Rate Limiting

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri='redis://redis:6379/0',    # Shared across workers
    default_limits=['200 per day', '50 per hour']
)

# Per-endpoint limits
@auth_bp.route('/register', methods=['POST'])
@limiter.limit('5 per minute')       # Prevent mass registration
def register(): ...

@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')      # Prevent brute force
def login(): ...

@chatbot_bp.route('/chatbot', methods=['POST'])
@limiter.limit('10 per minute')      # Prevent abuse
def chatbot(): ...
```

---

## 5. IP Allowlisting

```python
import ipaddress

def _is_ip_allowed(ip_str: str, allowed_ranges: list[str]) -> bool:
    try:
        client_ip = ipaddress.ip_address(ip_str)
        return any(
            client_ip in ipaddress.ip_network(cidr, strict=False)
            for cidr in allowed_ranges
        )
    except ValueError:
        return False

@app.before_request
def limit_remote_addr():
    if app.config.get('DISABLE_IP_FILTER'):
        return
    
    # Handle reverse proxy
    client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    client_ip = client_ip or request.remote_addr
    
    # Skip for health checks
    if request.endpoint in ('main.health',):
        return
    
    allowed = app.config.get('ALLOWED_IPS', [])
    if not _is_ip_allowed(client_ip, allowed):
        abort(403)
```

---

## 6. Security Headers

```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    
    # Content Security Policy (adjust for your CDN)
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "font-src 'self' https://cdn.jsdelivr.net;"
    )
    return response
```

---

## 7. Input Validation

```python
# Always validate and sanitize inputs
@dashboard_bp.route('/dashboard', methods=['POST'])
@login_required_page
def dashboard():
    symptoms = request.form.get('symptoms', '').strip()
    
    # Length check
    if not symptoms or len(symptoms) > 5000:
        flash('Invalid symptoms input.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    # HTML/script sanitization
    import bleach
    symptoms = bleach.clean(symptoms, tags=[], strip=True)
    
    consultation = Consultation(user_id=session['user_id'], symptoms=symptoms)
    db.session.add(consultation)
    db.session.commit()
```

---

## 8. Bot Security

| Measure | Implementation |
|---------|---------------|
| Token storage | Environment variables, never in code |
| User auth | JWT linked to Docify account |
| Telegram validation | Bot token verification |
| Twilio validation | Request signature verification |
| Discord validation | Gateway intents + permissions |
| Rate limiting | Per-user limits in Redis |
| Token expiry | 24-hour TTL on bot tokens |

---

## 9. Audit Logging

```python
# Every data mutation is logged automatically via SQLAlchemy event listeners

@event.listens_for(db.Session, 'after_flush')
def audit_changes(session, flush_context):
    for obj in session.new:
        log_audit('INSERT', obj)
    for obj in session.dirty:
        log_audit('UPDATE', obj)
    for obj in session.deleted:
        log_audit('HARD_DELETE', obj)

# Audit logs are immutable — no UPDATE/DELETE allowed on audit_logs table
# In PostgreSQL, enforce with a trigger:
# CREATE RULE no_update_audit AS ON UPDATE TO audit_logs DO INSTEAD NOTHING;
# CREATE RULE no_delete_audit AS ON DELETE TO audit_logs DO INSTEAD NOTHING;
```

---

## 10. Security Checklist

- [ ] SECRET_KEY is a long, random string (not the default)
- [ ] Database password is not "password" or "docify"
- [ ] CSRF tokens on all POST forms and AJAX calls
- [ ] Rate limiting enabled on login, register, chatbot
- [ ] SESSION_COOKIE_SECURE=true in production
- [ ] IP filtering configured (or explicitly disabled)
- [ ] All bot tokens in environment variables
- [ ] PostgreSQL not exposed to public network
- [ ] Redis not exposed to public network
- [ ] Nginx configured with TLS (Let's Encrypt)
- [ ] Non-root Docker user (appuser)
- [ ] No debug mode in production
- [ ] Audit logging enabled
- [ ] Backup strategy in place
