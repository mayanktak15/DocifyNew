# 🗄️ Database Design — PostgreSQL + Redis

---

## 1. PostgreSQL Schema

### 1.1 Users Table

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(15) NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(200) NOT NULL,
    age INTEGER CHECK (age > 0 AND age < 150),
    gender VARCHAR(10) CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say')),
    blood_group VARCHAR(5) CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    medical_history TEXT,
    allergies TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Bot platform linking
    telegram_id BIGINT UNIQUE,
    discord_id BIGINT UNIQUE,
    whatsapp_phone VARCHAR(15) UNIQUE,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_telegram ON users(telegram_id) WHERE telegram_id IS NOT NULL;
CREATE INDEX idx_users_discord ON users(discord_id) WHERE discord_id IS NOT NULL;
```

### 1.2 Consultations Table

```sql
CREATE TABLE consultations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symptoms TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_review', 'completed', 'cancelled')),
    priority VARCHAR(10) NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    doctor_notes TEXT,
    prescription TEXT,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_consultations_user_active ON consultations(user_id, is_deleted)
    WHERE is_deleted = false;
CREATE INDEX idx_consultations_status ON consultations(status)
    WHERE is_deleted = false;
CREATE INDEX idx_consultations_created ON consultations(created_at DESC);
```

### 1.3 Chat History Table

```sql
CREATE TABLE chat_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    provider VARCHAR(20) NOT NULL DEFAULT 'fallback',
    response_time_ms INTEGER,
    platform VARCHAR(20) DEFAULT 'web',  -- web, telegram, whatsapp, discord
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_chat_user_time ON chat_history(user_id, created_at DESC);
CREATE INDEX idx_chat_provider ON chat_history(provider);
```

### 1.4 Audit Logs Table

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    record_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL
        CHECK (action IN ('INSERT', 'UPDATE', 'SOFT_DELETE', 'HARD_DELETE')),
    changed_fields JSONB,
    old_values JSONB,
    new_values JSONB,
    performed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_audit_table_record ON audit_logs(table_name, record_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action);
-- GIN index for JSONB queries
CREATE INDEX idx_audit_changed_fields ON audit_logs USING GIN (changed_fields);
```

### 1.5 Auto-Update Trigger

```sql
-- Function to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER consultations_updated_at
    BEFORE UPDATE ON consultations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

---

## 2. SQLAlchemy Model Mapping

```python
# app/models/user.py
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    blood_group = db.Column(db.String(5))
    medical_history = db.Column(db.Text)
    allergies = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    telegram_id = db.Column(db.BigInteger, unique=True)
    discord_id = db.Column(db.BigInteger, unique=True)
    whatsapp_phone = db.Column(db.String(15), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    consultations = db.relationship('Consultation', backref='user', lazy='dynamic',
                                     cascade='all, delete-orphan')
    chat_logs = db.relationship('ChatHistory', backref='user', lazy='dynamic')
```

---

## 3. Redis Caching Strategy

### 3.1 Key Namespace Design

```
docify:cache:chatbot:{md5_hash}      → Chatbot response string         (TTL: 300s)
docify:session:{session_id}          → Session data (JSON)              (TTL: 3600s)
docify:ratelimit:{ip}:{endpoint}     → Counter                         (TTL: per rule)
docify:bot:telegram:{telegram_id}    → User ID                         (TTL: 86400s)
docify:bot:discord:{discord_id}      → User ID                         (TTL: 86400s)
docify:bot:token:{user_id}           → JWT token                       (TTL: 86400s)
docify:faiss:status                  → "ready" | "building"            (no TTL)
docify:user:profile:{user_id}        → User profile JSON               (TTL: 600s)
```

### 3.2 Flask-Caching Configuration

```python
# app/config.py
class ProdConfig(BaseConfig):
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_KEY_PREFIX = 'docify:cache:'
```

### 3.3 Cache Usage Patterns

```python
# Pattern 1: Response caching
def get_chatbot_response(query, symptoms=None):
    cache_key = f"chatbot:{hashlib.md5((query + (symptoms or '')).encode()).hexdigest()}"
    
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    response = chatbot_engine.get_response(query, symptoms)
    cache.set(cache_key, response, timeout=300)
    return response

# Pattern 2: Cache invalidation
def invalidate_chatbot_cache():
    """Call when FAQ data changes"""
    # Pattern: use Redis SCAN to find and delete matching keys
    import redis
    r = redis.from_url(app.config['REDIS_URL'])
    for key in r.scan_iter('docify:cache:chatbot:*'):
        r.delete(key)

# Pattern 3: Graceful fallback
def cache_get_with_fallback(key):
    try:
        return cache.get(key)
    except Exception:
        return None  # Redis down — skip cache, compute fresh
```

### 3.4 Connection Configuration

```python
# docker-compose.yml environment
REDIS_URL=redis://redis:6379/0

# Redis configuration (redis.conf)
maxmemory 256mb
maxmemory-policy allkeys-lru
appendonly yes
```

---

## 4. Migration Strategy (SQLite → PostgreSQL)

### 4.1 For Development

```python
# app/config.py
class DevConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/docify.db'
    CACHE_TYPE = 'SimpleCache'  # No Redis needed in dev

class ProdConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
    CACHE_TYPE = 'RedisCache'
```

### 4.2 Data Migration Script

```python
# scripts/migrate_sqlite_to_postgres.py
"""One-time migration from SQLite to PostgreSQL"""

import sqlite3
import psycopg2

def migrate():
    sqlite_conn = sqlite3.connect('instance/docify.db')
    pg_conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    # Migrate users
    users = sqlite_conn.execute('SELECT * FROM user').fetchall()
    for user in users:
        pg_conn.execute(
            'INSERT INTO users (id, name, phone, email, password_hash, ...) VALUES (%s, ...)',
            user
        )
    
    # Migrate consultations
    # ... similar pattern
    
    pg_conn.commit()
```

---

## 5. Backup Strategy

```bash
# Daily PostgreSQL backup (cron job)
0 2 * * * pg_dump -Fc docify > /backups/docify_$(date +\%Y\%m\%d).dump

# Restore from backup
pg_restore -d docify /backups/docify_20261121.dump

# Redis backup (automatic with appendonly)
# RDB snapshots: every 15 min if 1+ key changed
save 900 1
save 300 10
save 60 10000
```
