# 🏗️ Docify Blueprint — Build Guide

> **Purpose**: This folder contains everything needed to rebuild a Docify-like medical consultation + AI chatbot platform from scratch, upgraded with **PostgreSQL**, **Redis**, **FAISS ML**, and production-grade bot integration.

---

## 📂 Folder Structure

```
blueprint/
├── README.md                          ← You are here
├── prompt.md                          ← Master AI prompt to generate the entire project
├── skills.md                          ← Developer skills & tech stack reference
├── workflow.md                        ← Step-by-step implementation workflow
│
├── system-design/
│   ├── hld.md                         ← High-Level Design (architecture overview)
│   ├── lld.md                         ← Low-Level Design (class/module level)
│   └── system-design.md              ← Full system design document
│
├── docs/
│   ├── bot-integration.md             ← Telegram/WhatsApp/Discord bot integration
│   ├── database-design.md             ← PostgreSQL schema + Redis caching strategy
│   ├── ml-pipeline.md                 ← FAISS + embeddings + RAG pipeline
│   ├── api-reference.md               ← REST API endpoint documentation
│   ├── deployment.md                  ← Docker, Compose, CI/CD, production guide
│   └── security.md                    ← Auth, CSRF, rate limiting, IP filtering
│
└── prompts/
    ├── chatbot-system-prompt.md       ← System instructions for the medical chatbot
    └── rag-prompt-template.md         ← RAG prompt template for context injection
```

---

## 🚀 Quick Start

1. **Read** [`prompt.md`](prompt.md) — the master prompt to give an AI agent to scaffold the full project
2. **Study** [`system-design/hld.md`](system-design/hld.md) for the big picture
3. **Follow** [`workflow.md`](workflow.md) step-by-step to build it
4. **Reference** [`skills.md`](skills.md) for required tech knowledge
5. **Deep-dive** into `docs/` and `system-design/lld.md` for implementation details

---

## 🔄 What Changed from Original Docify

| Aspect | Original Docify | New Blueprint |
|--------|----------------|---------------|
| **Database** | SQLite | PostgreSQL + Redis cache |
| **Caching** | Flask-Caching (SimpleCache) | Redis with TTL policies |
| **Vector Store** | FAISS file-based | FAISS with Redis metadata + persistent index |
| **Bot Integration** | Web-only chatbot | Telegram + WhatsApp + Discord bots |
| **Auth** | Session-based | JWT + Session hybrid |
| **Deployment** | Single Dockerfile | Docker Compose (multi-service) |
| **Queue** | None | Celery + Redis for async tasks |
| **Monitoring** | Basic logging | Structured logging + health checks + metrics |
