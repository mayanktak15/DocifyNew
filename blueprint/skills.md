# 🛠️ Skills & Tech Stack Reference

> Required skills and knowledge areas to build and maintain Docify v2.

---

## 1. Core Backend Skills

### Python 3.11+
- Type hints, dataclasses, `@lru_cache`, `functools.wraps`
- Context managers, generators, decorators
- Virtual environment management (`venv`, `pip`)

### Flask 3.x
- Application Factory Pattern (`create_app()`)
- Blueprints for modular route organization
- Jinja2 templating with template inheritance
- Flask extensions ecosystem:
  - `Flask-SQLAlchemy` — ORM integration
  - `Flask-Migrate` — Alembic-based schema migrations
  - `Flask-WTF` — CSRF protection
  - `Flask-Caching` — Redis cache backend
  - `Flask-Limiter` — IP-based rate limiting
- Request/response lifecycle hooks (`before_request`, `after_request`)
- Error handler registration

### SQLAlchemy 2.x
- Declarative model definitions with relationships
- Event listeners (`after_flush`) for audit logging
- Session management (`safe_commit`, rollback patterns)
- Query building with filters, pagination, ordering
- Schema inspection for change tracking

---

## 2. Database Skills

### PostgreSQL 15+
- Table design: primary keys, foreign keys, constraints, CHECK constraints
- JSONB columns for flexible audit data
- Indexing strategies (B-tree, GIN for JSONB)
- Connection pooling (PgBouncer or SQLAlchemy pool)
- Alembic migrations: `flask db init/migrate/upgrade/downgrade`
- Backup and restore (`pg_dump`, `pg_restore`)

### Redis 7+
- Key-value caching patterns with TTL
- Hash, List, Set data structures
- Pub/Sub for real-time events
- Use as:
  - Response cache (`chatbot:{hash}`)
  - Session store (`session:{id}`)
  - Rate limit backend
  - Celery message broker
  - Bot token store
- Redis CLI operations and monitoring
- Connection via `redis-py` or `Flask-Caching[redis]`

### SQLite (Development/Testing)
- In-memory databases for pytest (`sqlite:///:memory:`)
- Schema compatibility with PostgreSQL models
- PRAGMA operations, WAL mode

---

## 3. ML/AI Pipeline Skills

### Sentence Transformers
- Model loading: `SentenceTransformer('all-MiniLM-L6-v2', device='cpu')`
- Text encoding with normalized embeddings
- Lazy loading patterns to avoid startup overhead
- Understanding embedding dimensions (384-dim for MiniLM)

### FAISS (Facebook AI Similarity Search)
- `IndexFlatIP` — Inner Product index (cosine similarity with normalized vectors)
- Index build: `index.add(vectors)` with contiguous arrays
- Index persistence: `faiss.write_index()` / `faiss.read_index()`
- Search: `index.search(query_vector, top_k)` returning scores + indices
- Hash-based cache invalidation (SHA256 of source data + model name)
- Graceful fallback to NumPy dot-product when FAISS unavailable

### scikit-learn
- `TfidfVectorizer` with English stop words
- Sparse matrix multiplication for keyword scoring
- Cosine similarity computation

### Hybrid Retrieval & Rank Fusion
- Combining keyword (TF-IDF) and semantic (FAISS) scores
- Configurable weight parameters: `score = w_kw × kw_score + w_emb × emb_score`
- Top-K selection with score thresholding

### RAG (Retrieval-Augmented Generation)
- Context assembly from retrieved documents
- Prompt engineering with system instructions
- Max context character limits to avoid token overflow
- Multi-provider LLM chain with failover:
  1. **Google Gemini API** (`google-generativeai` SDK)
  2. **Ollama** (local REST API at `localhost:11434`)
  3. **HuggingFace Transformers** (CPU inference)
  4. **Rule-based fallback** (zero dependency)

---

## 4. Bot Development Skills

### Telegram Bot (`python-telegram-bot`)
- BotFather setup and token management
- Command handlers (`/start`, `/ask`, `/help`)
- Message handlers with filters
- Inline keyboards and callback queries
- Webhook vs. long-polling modes
- User state management (ConversationHandler)

### WhatsApp Bot (Twilio)
- Twilio account + WhatsApp sandbox setup
- Webhook endpoint for incoming messages
- `twilio` Python SDK for sending responses
- Template message approval process
- Media message handling (prescriptions as PDFs)

### Discord Bot (`discord.py`)
- Bot token and gateway intents
- Slash command registration with `app_commands`
- Embed messages with color-coded fields
- DM handling for private consultations
- Guild vs. DM context routing

### Bot Auth & User Linking
- JWT token generation and validation
- Linking external platform IDs to internal user accounts
- Rate limiting per bot user
- Secure token exchange flow

---

## 5. DevOps & Deployment Skills

### Docker
- Multi-stage Dockerfile (builder → runner)
- Non-root user security hardening
- Health check definitions
- Build arguments for conditional dependency install
- Layer caching optimization

### Docker Compose
- Multi-service orchestration:
  - `web` (Flask + Gunicorn)
  - `db` (PostgreSQL)
  - `redis` (Redis)
  - `worker` (Celery)
  - `telegram` / `discord` (bot processes)
- Volume mounting for persistent data
- Service dependencies and health checks
- Environment variable management

### Gunicorn
- Worker configuration (`--workers`, `--threads`)
- Binding and socket options
- Graceful shutdown and reload

### Celery
- Task definition and decoration
- Redis as broker and result backend
- Worker startup and concurrency
- Periodic tasks with Celery Beat

### CI/CD
- GitHub Actions for lint + test + build + deploy
- Automated pytest on push/PR
- Docker image build and push to registry

---

## 6. Security Skills

### Authentication & Authorization
- Password hashing with `werkzeug.security` (pbkdf2:sha256)
- Flask session management (server-side)
- JWT token creation/verification (PyJWT or Flask-JWT-Extended)
- Role-based access patterns

### Web Security
- CSRF protection (Flask-WTF tokens in forms + AJAX headers)
- Rate limiting strategies (per IP, per endpoint, per user)
- IP allowlisting with CIDR notation (`ipaddress` module)
- Security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- Cookie security flags (HTTPOnly, SameSite, Secure)
- Input validation and sanitization

---

## 7. Testing Skills

### pytest
- Fixture design (`app`, `client`, `db`, `test_user`)
- Application factory configuration override for testing
- In-memory database setup and teardown
- JSON endpoint testing with `client.post()` / `client.get()`

### Test Categories
- **Unit tests**: Model CRUD, chatbot module functions
- **Integration tests**: Route endpoints, database interactions
- **Bot tests**: Command handler mock testing
- **ML tests**: Embedding generation, FAISS search, retriever output

---

## 8. Frontend Skills (Minimal)

### Bootstrap 5
- Grid system, cards, modals, forms
- Glassmorphism CSS styling
- Responsive design breakpoints

### JavaScript
- Fetch API for AJAX chatbot requests
- CSRF token injection in request headers
- DOM manipulation for dynamic chat UI
- Event listener management (avoid duplicate handlers)

### Jinja2
- Template inheritance (`{% extends 'base.html' %}`)
- Control structures, filters, macros
- Context variable injection from Flask routes
