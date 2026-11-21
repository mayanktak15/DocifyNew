# 🏗️ High-Level Design (HLD) — Docify v2

---

## 1. System Overview

Docify v2 is a **medical consultation platform** with an **AI-powered chatbot** that provides health guidance through a web interface and messaging bots (Telegram, WhatsApp, Discord). The system uses a **RAG (Retrieval-Augmented Generation)** pipeline with FAISS vector search for intelligent responses with graceful multi-provider LLM failover.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENTS                                       │
│                                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │  Web UI  │  │ Telegram Bot │  │ WhatsApp Bot │  │ Discord Bot   │   │
│  │(Browser) │  │              │  │   (Twilio)   │  │               │   │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘   │
│       │               │                 │                   │           │
└───────┼───────────────┼─────────────────┼───────────────────┼───────────┘
        │               │                 │                   │
        ▼               ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        LOAD BALANCER / REVERSE PROXY                    │
│                              (Nginx / Traefik)                          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                               │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Flask + Gunicorn (WSGI)                      │    │
│  │                                                                 │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │  Auth    │  │Dashboard │  │ Chatbot  │  │  REST API    │   │    │
│  │  │ Routes  │  │ Routes   │  │  Route   │  │  /api/v1/*   │   │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │    │
│  │       │              │              │               │           │    │
│  │       ▼              ▼              ▼               ▼           │    │
│  │  ┌──────────────────────────────────────────────────────────┐   │    │
│  │  │                   SERVICE LAYER                          │   │    │
│  │  │  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │   │    │
│  │  │  │Consultation │  │   Chatbot    │  │ Notification  │  │   │    │
│  │  │  │  Service    │  │   Service    │  │   Service     │  │   │    │
│  │  │  └─────────────┘  └──────┬───────┘  └───────────────┘  │   │    │
│  │  └──────────────────────────┼──────────────────────────────┘   │    │
│  └─────────────────────────────┼──────────────────────────────────┘    │
│                                │                                        │
│  ┌─────────────────────────────┼──────────────────────────────────┐    │
│  │               CHATBOT / RAG ENGINE                             │    │
│  │                             │                                   │    │
│  │  ┌──────────────────────────▼──────────────────────────────┐   │    │
│  │  │              Hybrid Retriever                            │   │    │
│  │  │  ┌─────────────────┐    ┌────────────────────────────┐  │   │    │
│  │  │  │  TF-IDF Keyword │    │  FAISS Semantic Search     │  │   │    │
│  │  │  │   Scoring       │    │  (all-MiniLM-L6-v2)       │  │   │    │
│  │  │  └─────────────────┘    └────────────────────────────┘  │   │    │
│  │  └─────────────────────────────────────────────────────────┘   │    │
│  │                             │                                   │    │
│  │  ┌──────────────────────────▼──────────────────────────────┐   │    │
│  │  │          LLM Provider Chain (Failover)                   │   │    │
│  │  │  Gemini → Ollama → HuggingFace CPU → Rule-based FAQ    │   │    │
│  │  └─────────────────────────────────────────────────────────┘   │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                     CELERY WORKERS                             │    │
│  │  ┌─────────────────┐  ┌──────────────────┐                    │    │
│  │  │  Embedding       │  │  Notification    │                    │    │
│  │  │  Rebuild Tasks  │  │  Dispatch Tasks  │                    │    │
│  │  └─────────────────┘  └──────────────────┘                    │    │
│  └────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼──────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│  PostgreSQL    │    │     Redis        │    │   FAISS Index      │
│  ───────────── │    │  ─────────────── │    │  ──────────────    │
│  • Users       │    │  • Response      │    │  • faq_faiss.idx   │
│  • Consults    │    │    Cache (TTL)   │    │  • faq_faiss.json  │
│  • Chat Logs   │    │  • Sessions      │    │  • Metadata hash   │
│  • Audit Logs  │    │  • Rate Limits   │    │                    │
│                │    │  • Celery Broker  │    │  Persistent on     │
│  Port: 5432    │    │  • Bot Tokens    │    │  disk (instance/)  │
└────────────────┘    │                  │    └────────────────────┘
                      │  Port: 6379      │
                      └──────────────────┘
```

---

## 3. Component Descriptions

### 3.1 Client Layer
| Component | Protocol | Description |
|-----------|----------|-------------|
| Web UI | HTTP/HTTPS | Bootstrap 5 frontend served by Flask (Jinja2 templates) |
| Telegram Bot | Telegram API | Long-polling or webhook-based bot process |
| WhatsApp Bot | Twilio Webhooks | HTTP webhook at `/webhook/whatsapp` |
| Discord Bot | Discord Gateway | WebSocket connection via `discord.py` |

### 3.2 Application Layer
- **Flask + Gunicorn**: WSGI server with pre-forked workers (4 workers, 2 threads)
- **Blueprint Architecture**: Modular route organization (auth, dashboard, chatbot, api, errors)
- **Middleware Pipeline**: IP filter → Security headers → Route handler → Response

### 3.3 Service Layer
- **Consultation Service**: CRUD operations with soft deletes and audit logging
- **Chatbot Service**: Redis-cached orchestrator that delegates to the RAG engine
- **Notification Service**: Dispatches email/push/bot notifications via Celery tasks

### 3.4 RAG Engine
- **Hybrid Retriever**: Combines TF-IDF keyword scores + FAISS semantic scores via rank fusion
- **LLM Provider Chain**: Gemini API → Ollama → HuggingFace → Rule-based (graceful degradation)
- **Vector Store**: FAISS IndexFlatIP with disk persistence and hash-based cache validation

### 3.5 Data Layer
| Store | Purpose | Persistence |
|-------|---------|-------------|
| PostgreSQL | Users, consultations, chat history, audit logs | Durable (volumes) |
| Redis | Cache, sessions, rate limits, Celery broker | Ephemeral with RDB snapshots |
| FAISS Index | Embedding vectors for semantic search | Disk file (instance/) |

---

## 4. Key Design Decisions

### 4.1 Why PostgreSQL over SQLite?
- **Concurrent access**: Multiple Gunicorn workers + Celery + bots need simultaneous writes
- **JSONB support**: Flexible audit log storage without schema changes
- **Scalability**: Connection pooling, replication, partitioning when needed
- **CHECK constraints**: Database-level validation for status/priority enums

### 4.2 Why Redis?
- **Sub-millisecond cache reads**: Chatbot responses are expensive to compute
- **Shared state**: Rate limits and sessions work correctly across Gunicorn workers
- **Celery broker**: No need for a separate RabbitMQ installation
- **Bot tokens**: Fast lookup for JWT token verification

### 4.3 Why FAISS over pgvector?
- **Speed**: FAISS is 10-100x faster for in-memory vector search at small scale (< 10K vectors)
- **No DB coupling**: FAISS operates independently — if PostgreSQL is down, chatbot still works
- **CPU optimized**: IndexFlatIP with normalized vectors = exact cosine similarity
- **Disk persistence**: Index survives container restarts without rebuilding

### 4.4 Why 4-Stage LLM Failover?
- **Reliability**: Platform works even when all external APIs are down
- **Cost control**: Local inference has zero API cost
- **Latency**: Rule-based responses are sub-millisecond
- **Offline**: System is fully functional without internet

---

## 5. Data Flow

### 5.1 Web Chatbot Flow
```
User → Browser → POST /chatbot → IP Filter → Rate Limiter → CSRF Check
  → ChatbotService → Redis Cache Check
    → [MISS] → RAG Engine → HybridRetriever → LLM Provider Chain → Response
    → [HIT] → Cached Response
  → Log to chat_history (PostgreSQL) → JSON Response → Browser
```

### 5.2 Bot Chatbot Flow
```
User → Telegram/Discord → Bot Process → JWT Auth → ChatbotService
  → Same RAG pipeline as web
  → Log to chat_history → Format for platform → Bot Response
```

### 5.3 Consultation Flow
```
User → Dashboard Form → POST /dashboard → Auth Check → Create Consultation
  → PostgreSQL INSERT → Audit Log (after_flush) → Celery Task (notification)
  → Redirect to Dashboard
```

---

## 6. Scalability Strategy

| Level | Strategy |
|-------|----------|
| **L1** (< 100 users) | Single Docker Compose stack |
| **L2** (100-1K users) | Multiple Gunicorn workers + Redis cluster |
| **L3** (1K-10K users) | Horizontal app scaling behind load balancer |
| **L4** (10K+ users) | PostgreSQL read replicas + FAISS sharding + dedicated worker pool |

---

## 7. Failure Modes & Recovery

| Failure | Impact | Recovery |
|---------|--------|----------|
| PostgreSQL down | No auth, no CRUD | App shows error; chatbot still works (FAQ fallback) |
| Redis down | No cache, no rate limits | Fallback to in-memory cache; rate limits disabled |
| Gemini API down | No premium LLM responses | Auto-failover to Ollama → HF → rule-based |
| FAISS index corrupt | No semantic search | Rebuild from FAQ source; keyword search still works |
| Celery worker down | No async tasks | Tasks queue in Redis; process when worker returns |
| Bot process crash | Bot offline | Docker restart policy auto-recovers |
