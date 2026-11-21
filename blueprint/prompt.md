# 🤖 Master Prompt — Build Docify v2

> Give this entire prompt to an AI coding agent (or use it yourself) to scaffold the complete project.

---

## Prompt

```
You are a senior full-stack Python engineer. Build a production-grade medical consultation
and AI chatbot platform called "Docify v2" with the following specifications:

## PROJECT OVERVIEW
Docify v2 is a secure, scalable medical consultation platform with an intelligent RAG-based
chatbot. Users register, submit symptom consultations, and interact with an AI medical
assistant. Doctors review consultations and provide notes/prescriptions. The chatbot uses
a 4-stage hierarchical provider architecture with graceful failover.

## TECH STACK
- **Backend Framework**: Flask 3.x with Application Factory Pattern
- **Database**: PostgreSQL 15+ (primary), SQLite fallback for dev
- **Cache & Message Broker**: Redis 7+ (caching, session store, Celery broker)
- **ORM**: SQLAlchemy 2.x with Flask-SQLAlchemy + Flask-Migrate (Alembic)
- **ML/AI Pipeline**:
  - Sentence Transformers (all-MiniLM-L6-v2) for embeddings
  - FAISS-CPU for vector similarity search
  - scikit-learn TF-IDF for keyword scoring
  - Hybrid Rank Fusion (configurable keyword/embedding weights)
- **LLM Providers** (hierarchical failover):
  1. Google Gemini API (gemini-1.5-flash)
  2. Local Ollama server (llama2/mistral)
  3. Local HuggingFace CPU inference
  4. Zero-dependency rule-based FAQ fallback
- **Bot Integration**:
  - Telegram Bot (python-telegram-bot)
  - WhatsApp Bot (Twilio API)
  - Discord Bot (discord.py)
- **Task Queue**: Celery with Redis backend
- **Auth**: Session-based with JWT tokens for API/bot access
- **Security**: CSRF protection, rate limiting, IP allowlisting, security headers
- **Frontend**: Bootstrap 5 with glassmorphism UI, Jinja2 templates
- **Testing**: pytest with fixtures, coverage reports
- **Deployment**: Docker Compose (Flask + PostgreSQL + Redis + Celery Worker)

## FOLDER STRUCTURE
```
docify-v2/
├── app.py                              # Entrypoint
├── docker-compose.yml                  # Multi-service orchestration
├── Dockerfile                          # Multi-stage build
├── .env.example                        # Environment template
├── requirements/
│   ├── base.txt                        # Core Flask dependencies
│   ├── ai.txt                          # ML/AI stack (torch, faiss, etc.)
│   ├── bot.txt                         # Bot frameworks
│   └── dev.txt                         # Testing tools
├── app/
│   ├── __init__.py                     # create_app() factory
│   ├── config.py                       # BaseConfig, DevConfig, ProdConfig
│   ├── extensions.py                   # db, migrate, cache, csrf, limiter, celery
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                     # User model with medical profile
│   │   ├── consultation.py             # Consultation with soft deletes + audit
│   │   ├── chat_history.py             # Persistent chat logs per user
│   │   └── audit_log.py               # Immutable audit trail table
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── main.py                     # Home, FAQ, health check
│   │   ├── auth.py                     # Register, login, logout, JWT issue
│   │   ├── dashboard.py               # CRUD consultations, profile, pagination
│   │   ├── chatbot.py                  # /chatbot POST endpoint
│   │   ├── api.py                      # /api/v1/* REST endpoints (JWT-protected)
│   │   └── errors.py                   # Custom error handlers (403, 404, 500)
│   ├── services/
│   │   ├── chatbot_service.py          # Redis-cached chatbot orchestrator
│   │   ├── consultation_service.py     # Business logic for consultations
│   │   └── notification_service.py     # Email/push notification dispatcher
│   ├── middleware/
│   │   ├── ip_filter.py                # CIDR-based IP allowlisting
│   │   └── security_headers.py         # X-Content-Type-Options, X-Frame-Options
│   ├── utils/
│   │   ├── auth.py                     # login_required decorators, JWT helpers
│   │   ├── db.py                       # safe_commit wrappers
│   │   └── csv_export.py              # Export user data to CSV
│   └── templates/                      # Bootstrap 5 Jinja2 templates
│       ├── base.html
│       ├── index.html
│       ├── login.html
│       ├── register.html
│       ├── dash.html
│       ├── profile.html
│       ├── faq.html
│       └── error_*.html
├── chatbot/
│   ├── __init__.py                     # Exports get_response()
│   ├── config.py                       # FAQ_FILE_PATH, EMBEDDING_MODEL, TOP_K, etc.
│   ├── data.py                         # Load + parse FAQ text into blocks
│   ├── types.py                        # Document dataclass
│   ├── embeddings.py                   # SentenceTransformer wrapper (lazy load)
│   ├── vectorstore.py                  # FAISS index build/load/search
│   ├── keyword.py                      # TF-IDF + simple overlap scoring
│   ├── retriever.py                    # HybridRetriever (rank fusion)
│   ├── responder.py                    # LLM provider chain (Gemini→Ollama→HF→FAQ)
│   ├── prompts.py                      # SYSTEM_INSTRUCTION, RAG_PROMPT_TEMPLATE
│   └── fallback.py                     # Rule-based responses + fuzzy FAQ match
├── bots/
│   ├── __init__.py
│   ├── telegram_bot.py                 # Telegram bot with /start, /ask, /consult
│   ├── whatsapp_bot.py                 # Twilio WhatsApp webhook handler
│   ├── discord_bot.py                  # Discord bot with slash commands
│   └── bot_auth.py                     # JWT verification for bot users
├── tasks/
│   ├── __init__.py                     # Celery app setup
│   ├── embedding_tasks.py             # Async FAISS index rebuild
│   └── notification_tasks.py          # Async email/notification dispatch
├── migrations/                         # Alembic migration scripts (auto-generated)
├── tests/
│   ├── conftest.py                     # Fixtures (app, client, db, test user)
│   ├── test_app.py                     # Route/endpoint tests
│   ├── test_chatbot.py                 # Chatbot module unit tests
│   ├── test_models.py                  # Model CRUD + audit tests
│   └── test_bots.py                    # Bot command handler tests
├── data/
│   └── faq.txt                         # FAQ knowledge base (48+ entries)
└── instance/                           # Runtime data (FAISS index, local DB)
    ├── faq_faiss.idx
    └── faq_faiss.json
```

## DATABASE SCHEMA (PostgreSQL)

### users
- id: SERIAL PRIMARY KEY
- name: VARCHAR(100) NOT NULL
- phone: VARCHAR(15) NOT NULL
- email: VARCHAR(120) UNIQUE NOT NULL
- password_hash: VARCHAR(200) NOT NULL
- age: INTEGER
- gender: VARCHAR(10)
- blood_group: VARCHAR(5)
- medical_history: TEXT
- allergies: TEXT
- is_active: BOOLEAN DEFAULT true
- created_at: TIMESTAMP DEFAULT NOW()
- updated_at: TIMESTAMP DEFAULT NOW()

### consultations
- id: SERIAL PRIMARY KEY
- user_id: INTEGER REFERENCES users(id) ON DELETE CASCADE
- symptoms: TEXT NOT NULL
- status: VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending','in_review','completed','cancelled'))
- priority: VARCHAR(10) DEFAULT 'normal' CHECK (priority IN ('low','normal','high','urgent'))
- doctor_notes: TEXT
- prescription: TEXT
- is_deleted: BOOLEAN DEFAULT false
- created_at: TIMESTAMP DEFAULT NOW()
- updated_at: TIMESTAMP DEFAULT NOW()

### chat_history
- id: SERIAL PRIMARY KEY
- user_id: INTEGER REFERENCES users(id)
- query: TEXT NOT NULL
- response: TEXT NOT NULL
- provider: VARCHAR(20) (gemini/ollama/huggingface/fallback)
- response_time_ms: INTEGER
- created_at: TIMESTAMP DEFAULT NOW()

### audit_logs
- id: SERIAL PRIMARY KEY
- table_name: VARCHAR(50) NOT NULL
- record_id: INTEGER NOT NULL
- action: VARCHAR(20) NOT NULL (INSERT/UPDATE/SOFT_DELETE/HARD_DELETE)
- changed_fields: JSONB
- old_values: JSONB
- new_values: JSONB
- performed_by: INTEGER REFERENCES users(id)
- created_at: TIMESTAMP DEFAULT NOW()

## REDIS CACHING STRATEGY
- Chatbot responses: `chatbot:{hash(query+symptoms)}` → TTL 300s
- User sessions: `session:{session_id}` → TTL 3600s
- Rate limit counters: `ratelimit:{ip}:{endpoint}` → TTL per rule
- FAQ embeddings ready flag: `faiss:ready` → no TTL (flag)
- Bot user tokens: `bot:token:{user_id}` → TTL 86400s

## CHATBOT RAG PIPELINE
1. User sends query via web/bot
2. Rule-based matcher checks for hardcoded patterns (fever, docify, etc.)
3. If no rule match → HybridRetriever:
   a. TF-IDF keyword scoring (scikit-learn, fallback to token overlap)
   b. FAISS semantic vector search (sentence-transformers embeddings)
   c. Rank fusion: score = (weight_keyword × keyword_score) + (weight_embedding × embedding_score)
4. Top-K documents retrieved as context
5. Response generation chain:
   a. Try Gemini API → b. Try Ollama → c. Try local HF → d. Rule-based FAQ fallback
6. Response cached in Redis, chat logged to PostgreSQL

## BOT INTEGRATION REQUIREMENTS

### Telegram Bot
- Commands: /start, /help, /ask <question>, /consult <symptoms>, /status
- Inline keyboard for FAQ quick replies
- User linking: Telegram user_id ↔ Docify user (via /link <email> <token>)
- Rate limit: 10 messages/minute per user

### WhatsApp Bot (Twilio)
- Webhook at /webhook/whatsapp
- Same chatbot pipeline as web
- Template messages for consultation status updates
- Media support for prescription PDFs

### Discord Bot
- Slash commands: /ask, /consult, /faq
- Embed-formatted responses with color coding by priority
- DM-based private consultations

## SECURITY REQUIREMENTS
- Password hashing: pbkdf2:sha256 (via Werkzeug)
- Session cookies: HTTPOnly, SameSite=Lax, Secure in production
- CSRF protection on all POST forms (Flask-WTF)
- Rate limiting: 200/day, 50/hour default; 10/min on chatbot; 5/min on register
- IP allowlisting middleware with X-Forwarded-For support
- Security headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- JWT tokens for API/bot with RS256 or HS256 signing
- Input sanitization on all user inputs

## DOCKER COMPOSE SERVICES
```yaml
services:
  web:         # Flask + Gunicorn (port 5000)
  db:          # PostgreSQL 15 (port 5432)
  redis:       # Redis 7 (port 6379)
  worker:      # Celery worker
  telegram:    # Telegram bot process
  discord:     # Discord bot process
```

## IMPLEMENTATION RULES
1. Use Flask Application Factory Pattern (create_app)
2. All database models use SQLAlchemy 2.x declarative style
3. FAISS index is persisted to disk with SHA256 hash validation
4. All AI dependencies are optional — app MUST work with zero AI packages
5. Lazy-load heavy ML models (sentence-transformers) on first use
6. Soft deletes on consultations (is_deleted flag + audit logging)
7. SQLAlchemy event listeners for automatic audit logging on flush
8. All environment config via .env with sane defaults
9. Full pytest suite with in-memory SQLite for tests
10. Type hints on all function signatures

Build the complete project with all files, working code, and proper error handling.
Prioritize graceful degradation — every component should work independently
even when optional dependencies or services are unavailable.
```

---

## Usage Notes

- **For AI agents**: Paste the entire prompt above into ChatGPT, Claude, Gemini, or Cursor to generate the full project.
- **For developers**: Use this as your spec sheet and build manually following the [`workflow.md`](workflow.md) steps.
- The prompt is intentionally detailed — it produces a complete, runnable project on the first pass.
