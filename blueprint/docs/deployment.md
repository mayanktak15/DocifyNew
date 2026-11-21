# 🚀 Deployment Guide

---

## 1. Environment Variables

Create `.env` from the template:

```bash
cp .env.example .env
```

```env
# ===== Core =====
SECRET_KEY=your-long-random-secret-key-here
FLASK_ENV=production

# ===== Database (PostgreSQL) =====
DATABASE_URL=postgresql://docify:your_db_password@db:5432/docify
DB_PASSWORD=your_db_password

# ===== Redis =====
REDIS_URL=redis://redis:6379/0

# ===== Session & Security =====
SESSION_COOKIE_SECURE=true
ALLOWED_IPS=0.0.0.0/0
DISABLE_IP_FILTER=false

# ===== Chatbot =====
FAQ_FILE_PATH=data/faq.txt
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHATBOT_TOP_K=3
CHATBOT_MAX_CONTEXT_CHARS=1500
CHATBOT_WEIGHT_KEYWORD=0.6

# ===== LLM Providers =====
GEMINI_API_KEY=your_gemini_api_key
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2

# ===== Bot Tokens =====
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DISCORD_BOT_TOKEN=your_discord_bot_token
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# ===== Rate Limiting =====
RATELIMIT_DEFAULT=200 per day;50 per hour
RATELIMIT_ENABLED=true
```

---

## 2. Docker Compose (Production)

### 2.1 docker-compose.yml

```yaml
version: '3.9'

services:
  web:
    build:
      context: .
      args:
        INSTALL_FULL: "true"
    ports:
      - "5000:5000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql://docify:${DB_PASSWORD}@db:5432/docify
      REDIS_URL: redis://redis:6379/0
    volumes:
      - instance_data:/app/instance
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      start_period: 15s
      retries: 3
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure
        max_attempts: 5

  db:
    image: postgres:15-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: docify
      POSTGRES_USER: docify
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U docify"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data
    command: >
      redis-server
        --appendonly yes
        --maxmemory 256mb
        --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  worker:
    build:
      context: .
      args:
        INSTALL_FULL: "true"
    command: celery -A tasks worker --loglevel=info --concurrency=2
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql://docify:${DB_PASSWORD}@db:5432/docify
      REDIS_URL: redis://redis:6379/0
    restart: unless-stopped

  telegram-bot:
    build:
      context: .
      args:
        INSTALL_FULL: "true"
    command: python -m bots.telegram_bot
    depends_on:
      web:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      DATABASE_URL: postgresql://docify:${DB_PASSWORD}@db:5432/docify
      REDIS_URL: redis://redis:6379/0
    restart: unless-stopped

  discord-bot:
    build:
      context: .
      args:
        INSTALL_FULL: "true"
    command: python -m bots.discord_bot
    depends_on:
      web:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN}
      DATABASE_URL: postgresql://docify:${DB_PASSWORD}@db:5432/docify
      REDIS_URL: redis://redis:6379/0
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
  instance_data:
```

### 2.2 Dockerfile (Multi-Stage)

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
ARG INSTALL_FULL=false

RUN pip install --upgrade pip && \
    if [ "$INSTALL_FULL" = "true" ]; then \
        pip install --prefix=/install \
            -r requirements/base.txt \
            -r requirements/ai.txt \
            -r requirements/bot.txt; \
    else \
        pip install --prefix=/install -r requirements/base.txt; \
    fi

# Stage 2: Runner
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.11/site-packages:${PYTHONPATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /install
COPY . .

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser && \
    mkdir -p /app/instance && \
    chown -R appuser:appgroup /app

USER appuser
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)"

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "app:app"]
```

---

## 3. Deployment Commands

### 3.1 First-Time Setup

```bash
# 1. Clone and configure
git clone <repo-url> docify-v2
cd docify-v2
cp .env.example .env
# Edit .env with your values

# 2. Build and start
docker-compose up -d --build

# 3. Run database migrations
docker-compose exec web flask db upgrade

# 4. Verify all services
docker-compose ps
docker-compose exec web curl -s localhost:5000/health | python -m json.tool
docker-compose exec db pg_isready -U docify
docker-compose exec redis redis-cli ping
```

### 3.2 Updates and Redeployment

```bash
# Pull latest code
git pull origin main

# Rebuild and restart (zero-downtime with rolling updates)
docker-compose up -d --build --no-deps web worker

# Run any new migrations
docker-compose exec web flask db upgrade
```

### 3.3 Scaling

```bash
# Scale web workers
docker-compose up -d --scale web=4

# Scale Celery workers
docker-compose up -d --scale worker=3
```

---

## 4. Nginx Reverse Proxy

```nginx
upstream docify {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name docify.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name docify.example.com;

    ssl_certificate /etc/letsencrypt/live/docify.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/docify.example.com/privkey.pem;

    location / {
        proxy_pass http://docify;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Rate limit on chatbot
    location /chatbot {
        limit_req zone=chatbot burst=5 nodelay;
        proxy_pass http://docify;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Webhook endpoints
    location /webhook/ {
        proxy_pass http://docify;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 5. Monitoring & Logs

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f web
docker-compose logs -f worker
docker-compose logs -f telegram-bot

# PostgreSQL stats
docker-compose exec db psql -U docify -c "SELECT count(*) FROM users;"
docker-compose exec db psql -U docify -c "SELECT status, count(*) FROM consultations GROUP BY status;"

# Redis stats
docker-compose exec redis redis-cli info memory
docker-compose exec redis redis-cli dbsize

# Celery worker status
docker-compose exec worker celery -A tasks inspect active
docker-compose exec worker celery -A tasks inspect stats
```

---

## 6. Backup & Restore

```bash
# PostgreSQL backup
docker-compose exec db pg_dump -U docify -Fc docify > backup_$(date +%Y%m%d).dump

# PostgreSQL restore
docker-compose exec -T db pg_restore -U docify -d docify < backup_20261121.dump

# FAISS index backup (included in instance volume)
docker cp docify-v2-web-1:/app/instance/ ./instance_backup/

# Full volume backup
docker run --rm -v docify-v2_pgdata:/data -v $(pwd):/backup alpine \
    tar czf /backup/pgdata_backup.tar.gz /data
```
