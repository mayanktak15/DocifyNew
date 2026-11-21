# 📋 Implementation Workflow

> Step-by-step guide to build Docify v2 from scratch. Each phase builds on the previous one. Estimated total: **5-7 days** for a solo developer.

---

## Phase 0: Environment Setup (Day 1 — 2 hours)

### 0.1 Project Scaffolding
```bash
mkdir docify-v2 && cd docify-v2
python -m venv .venv && source .venv/bin/activate
pip install -U pip
```

### 0.2 Create Folder Structure
```bash
mkdir -p app/{models,routes,services,middleware,utils,templates,static}
mkdir -p chatbot bots tasks tests data migrations instance
mkdir -p requirements
touch app/__init__.py app/config.py app/extensions.py
touch chatbot/__init__.py bots/__init__.py tasks/__init__.py tests/__init__.py
```

### 0.3 Configuration Files
- [ ] Create `.env.example` with all environment variables
- [ ] Create `requirements/base.txt` (Flask, SQLAlchemy, Redis, etc.)
- [ ] Create `requirements/ai.txt` (torch, sentence-transformers, faiss-cpu)
- [ ] Create `requirements/bot.txt` (python-telegram-bot, discord.py, twilio)
- [ ] Create `requirements/dev.txt` (pytest, pytest-cov)
- [ ] Create `requirements.txt` that includes all requirement files

### 0.4 Docker Setup
- [ ] Write multi-stage `Dockerfile`
- [ ] Write `docker-compose.yml` with web, db, redis, worker services
- [ ] Test `docker-compose up db redis` to verify infrastructure

---

## Phase 1: Core Flask App + PostgreSQL (Day 1 — 4 hours)

### 1.1 Configuration
- [ ] `app/config.py` — BaseConfig, DevConfig, ProdConfig classes
  - PostgreSQL URI from `DATABASE_URL` env var
  - Redis URL from `REDIS_URL` env var
  - Session, CSRF, rate limit settings

### 1.2 Extensions
- [ ] `app/extensions.py` — Initialize db, migrate, cache, csrf, limiter, celery
  - Configure Flask-Caching to use Redis backend
  - Configure Flask-Limiter to use Redis storage

### 1.3 Models
- [ ] `app/models/user.py` — User model with medical profile fields
- [ ] `app/models/consultation.py` — Consultation with soft delete, audit hooks
- [ ] `app/models/chat_history.py` — Persistent chat log per user
- [ ] `app/models/audit_log.py` — Immutable audit trail with JSONB fields
- [ ] Wire up SQLAlchemy event listeners for automatic audit logging

### 1.4 Application Factory
- [ ] `app/__init__.py` — `create_app()` with:
  - Extension initialization
  - Blueprint registration
  - Middleware registration
  - Database table creation

### 1.5 Database Migration
```bash
flask db init
flask db migrate -m "Initial schema"
flask db upgrade
```

### Checkpoint ✅
```bash
python -c "from app import create_app; app = create_app(); print('Factory OK')"
```

---

## Phase 2: Auth + Dashboard Routes (Day 2 — 4 hours)

### 2.1 Utility Functions
- [ ] `app/utils/auth.py` — `login_required_page`, `login_required_json`, `get_current_user`
- [ ] `app/utils/db.py` — `safe_commit`, `safe_commit_json` wrappers

### 2.2 Auth Routes
- [ ] `app/routes/auth.py` — Register, Login, Logout
  - Password hashing with pbkdf2:sha256
  - Rate limiting: 5/min on register, 10/min on login
  - Session management on login/logout

### 2.3 Dashboard Routes
- [ ] `app/routes/dashboard.py` — CRUD for consultations
  - Create consultation (POST form)
  - List with pagination (filter `is_deleted=False`)
  - Update consultation
  - Soft delete consultation
  - Profile view/edit
  - Status update (for doctor role)

### 2.4 Templates
- [ ] `base.html` — Bootstrap 5 layout with navbar, glassmorphism
- [ ] `index.html` — Landing page
- [ ] `login.html` / `register.html` — Auth forms with CSRF tokens
- [ ] `dash.html` — Dashboard with consultation cards + pagination
- [ ] `profile.html` — Medical profile form
- [ ] `faq.html` — FAQ accordion

### Checkpoint ✅
```bash
pytest tests/test_app.py -v  # Auth flow + CRUD tests pass
```

---

## Phase 3: Chatbot RAG Pipeline (Day 3 — 6 hours)

### 3.1 Data Layer
- [ ] `chatbot/config.py` — Configuration constants from env
- [ ] `chatbot/types.py` — `Document` dataclass
- [ ] `chatbot/data.py` — Load FAQ text, parse into blocks
- [ ] `data/faq.txt` — Populate with 48+ medical FAQ entries

### 3.2 Embedding & Vector Store
- [ ] `chatbot/embeddings.py` — Lazy-load SentenceTransformer, `embed_texts()`
- [ ] `chatbot/vectorstore.py` — `FAQVectorStore` class:
  - Build FAISS index from embeddings
  - Cache index to disk with SHA256 hash validation
  - Load from cache on startup (< 5ms)
  - Fallback to NumPy when FAISS unavailable
  - Search returning `(index, score)` tuples

### 3.3 Keyword Scoring
- [ ] `chatbot/keyword.py` — TF-IDF scores (scikit-learn) + simple overlap fallback

### 3.4 Hybrid Retriever
- [ ] `chatbot/retriever.py` — `HybridRetriever` class:
  - Combine keyword + embedding scores with configurable weights
  - Return top-K `Document` objects

### 3.5 Response Generation
- [ ] `chatbot/prompts.py` — System instruction + RAG prompt template
- [ ] `chatbot/fallback.py` — Rule-based responses + fuzzy FAQ matching
- [ ] `chatbot/responder.py` — Provider chain:
  1. Rule-based check → 2. Gemini API → 3. Ollama → 4. HF CPU → 5. FAQ fallback

### 3.6 Service Layer
- [ ] `chatbot/service.py` — `ChatbotService` class with lazy retriever init
- [ ] `app/services/chatbot_service.py` — Redis-cached wrapper
- [ ] `app/routes/chatbot.py` — `/chatbot` POST endpoint with rate limiting

### Checkpoint ✅
```bash
pytest tests/test_chatbot.py -v   # Chatbot unit tests
curl -X POST localhost:5000/chatbot -H "Content-Type: application/json" -d '{"message":"What is Docify?"}'
```

---

## Phase 4: Redis Integration (Day 4 — 3 hours)

### 4.1 Redis Cache Backend
- [ ] Update `app/extensions.py` to use `RedisCache` backend
- [ ] Configure connection via `REDIS_URL` env var
- [ ] Implement chatbot response caching with key: `chatbot:{hash(query+symptoms)}`
- [ ] Set TTL to 300 seconds (configurable)

### 4.2 Session Store
- [ ] Install `Flask-Session` with Redis backend
- [ ] Server-side session storage with configurable TTL

### 4.3 Rate Limit Storage
- [ ] Configure `Flask-Limiter` to use Redis storage URI
- [ ] Shared rate limit counters across Gunicorn workers

### 4.4 Health Check
- [ ] Add Redis ping to `/health` endpoint
- [ ] Graceful degradation if Redis is down (fallback to in-memory cache)

### Checkpoint ✅
```bash
docker-compose up redis -d
python -c "import redis; r = redis.Redis(); print(r.ping())"
```

---

## Phase 5: Bot Integration (Day 5 — 6 hours)

### 5.1 Bot Authentication
- [ ] `bots/bot_auth.py` — JWT token generation/verification for bot users
- [ ] User linking: external platform ID ↔ Docify user account
- [ ] Token storage in Redis with TTL

### 5.2 Telegram Bot
- [ ] `bots/telegram_bot.py`:
  - `/start` — Welcome message + link instructions
  - `/ask <question>` — Query chatbot pipeline
  - `/consult <symptoms>` — Create consultation
  - `/status` — Check consultation status
  - `/help` — Command reference
  - Inline keyboards for FAQ quick replies
  - Rate limiting: 10 msg/min per user

### 5.3 WhatsApp Bot
- [ ] `bots/whatsapp_bot.py`:
  - Twilio webhook at `/webhook/whatsapp`
  - Parse incoming message, route through chatbot
  - Send structured response via Twilio API
  - Template messages for status updates

### 5.4 Discord Bot
- [ ] `bots/discord_bot.py`:
  - Slash commands: `/ask`, `/consult`, `/faq`
  - Embed-formatted responses
  - DM-based private consultations
  - Guild permission checks

### 5.5 Docker Integration
- [ ] Add `telegram` and `discord` services to `docker-compose.yml`
- [ ] Environment variables for bot tokens

### Checkpoint ✅
```bash
# Test Telegram locally
python bots/telegram_bot.py  # Send /start to your bot

# Test Discord
python bots/discord_bot.py   # Use /ask in your server
```

---

## Phase 6: Celery Async Tasks (Day 5 — 2 hours)

### 6.1 Celery Setup
- [ ] `tasks/__init__.py` — Celery app with Redis broker
- [ ] Wire Celery into Flask app context

### 6.2 Task Definitions
- [ ] `tasks/embedding_tasks.py`:
  - `rebuild_faiss_index.delay()` — Async index rebuild when FAQ changes
- [ ] `tasks/notification_tasks.py`:
  - `send_consultation_update.delay(user_id, status)` — Email/push notifications
  - `send_bot_notification.delay(platform, user_id, message)` — Cross-platform notify

### 6.3 Docker Worker
- [ ] Add `worker` service to `docker-compose.yml`
- [ ] Configure Celery concurrency and task routing

### Checkpoint ✅
```bash
docker-compose up worker -d
celery -A tasks inspect active
```

---

## Phase 7: API Layer (Day 6 — 3 hours)

### 7.1 REST API
- [ ] `app/routes/api.py` — `/api/v1/*` endpoints:
  - `POST /api/v1/auth/token` — Issue JWT
  - `GET /api/v1/consultations` — List user's consultations
  - `POST /api/v1/consultations` — Create consultation
  - `GET /api/v1/consultations/:id` — Get single consultation
  - `POST /api/v1/chat` — Chatbot query (JSON response)
  - `GET /api/v1/health` — Health check with component status

### 7.2 JWT Middleware
- [ ] Token validation decorator for API routes
- [ ] Refresh token support

### Checkpoint ✅
```bash
# Get token
TOKEN=$(curl -s -X POST localhost:5000/api/v1/auth/token -d '{"email":"test@example.com","password":"pass"}' | jq -r .token)

# Use token
curl -H "Authorization: Bearer $TOKEN" localhost:5000/api/v1/consultations
```

---

## Phase 8: Testing & Security Hardening (Day 6 — 3 hours)

### 8.1 Test Suite
- [ ] `tests/conftest.py` — Fixtures with in-memory SQLite
- [ ] `tests/test_app.py` — Health, auth flow, CRUD, chatbot endpoint
- [ ] `tests/test_chatbot.py` — Module-level chatbot tests
- [ ] `tests/test_models.py` — Model creation, soft delete, audit logs
- [ ] `tests/test_bots.py` — Bot command handler mocks

### 8.2 Security Audit
- [ ] Verify all POST routes have CSRF protection
- [ ] Verify rate limits on sensitive endpoints
- [ ] Verify IP filter middleware works with X-Forwarded-For
- [ ] Verify security headers on all responses
- [ ] Verify password hashing strength
- [ ] Verify no SQL injection vectors
- [ ] Verify JWT token expiry and validation

### Checkpoint ✅
```bash
pytest --cov=app --cov=chatbot --cov=bots -v
```

---

## Phase 9: Production Deployment (Day 7 — 4 hours)

### 9.1 Docker Compose Production
```bash
docker-compose -f docker-compose.yml up -d --build
```

### 9.2 Verify All Services
- [ ] PostgreSQL accepting connections
- [ ] Redis responding to PING
- [ ] Flask serving on port 5000
- [ ] Celery worker processing tasks
- [ ] Telegram bot responding to commands
- [ ] Discord bot online in guild

### 9.3 Monitoring
- [ ] Structured JSON logging with timestamps
- [ ] `/health` endpoint with per-component status
- [ ] Docker health checks on all services
- [ ] Log rotation configuration

### 9.4 Backup Strategy
- [ ] PostgreSQL: `pg_dump` cron job
- [ ] FAISS index: included in Docker volume
- [ ] Redis: RDB snapshots enabled

### Final Checkpoint ✅
```bash
# Full system test
curl localhost:5000/health                                    # Web OK
docker-compose exec db pg_isready                             # DB OK
docker-compose exec redis redis-cli ping                     # Redis OK
docker-compose exec worker celery -A tasks inspect active    # Worker OK
```

---

## 🎉 Done!

Your Docify v2 is now running with:
- ✅ PostgreSQL persistent storage
- ✅ Redis caching and session management
- ✅ FAISS-powered semantic search
- ✅ 4-stage LLM provider failover
- ✅ Telegram + WhatsApp + Discord bot integration
- ✅ Celery async task processing
- ✅ Full test suite with coverage
- ✅ Docker Compose production deployment
