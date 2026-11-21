# Docify

Docify is a Flask prototype built from the documents in [`blueprint/`](blueprint/). It includes patient accounts, a consultation dashboard and clinician review workspace, a JWT API, a platform FAQ assistant, and optional infrastructure and messaging adapters.

**This is not a live medical service.** Requests are stored in the prototype, but no clinician is automatically assigned or notified. The assistant provides platform information and limited general health guidance. Do not use real patient information until the outstanding clinical, privacy, security and operational work is complete.

## Local setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env
# Edit SECRET_KEY to a long random value before use.
flask --app app.py db upgrade
flask --app app.py run
```

Open http://127.0.0.1:5000. SQLite data is stored under `instance/`. Run tests with `python -m pytest`. The Twilio signature test is skipped unless the optional bot dependencies are installed.

## Consultation export

From the dashboard, use **Download CSV** to export your own non-deleted consultations, including clinician notes and prescriptions. The download is limited to 5,000 records and records an audit event; it does not include the profile, chat history, or deleted records. Formula-like text is prefixed with an apostrophe to reduce spreadsheet formula injection risk. The downloaded file contains sensitive information, so store and share it carefully.

## Clinician workflow

Create a normal account, then grant it clinician access with the local administrative command:

```sh
flask --app app.py set-clinician clinician@example.com --reviewer ADMIN_ID --reference REVIEW_ID
```

Use the identifier of the administrator who checked the clinician’s identity and license, and the reference for that completed review. Production requires both values. Existing clinician accounts need a recorded review before they regain production clinician access. Local development accepts the command without these options.

The account can open `/clinician` to claim an available request and review it. Unclaimed requests show only an ID, date and priority; clinical details are visible only to the patient and assigned clinician. A claim moves the request into review, and patients can edit only their own pending requests. The assigned clinician can return an in-review request to the queue for another clinician to claim. Completed and cancelled requests cannot be returned to the queue. Administrators can assign or reassign an active request with `flask --app app.py assign-consultation REQUEST_ID clinician@example.com`. This command does not verify a clinician's identity. To remove access, run `flask --app app.py remove-clinician clinician@example.com`. The command returns that clinician's non-deleted in-review requests to the queue and creates in-app patient notifications in the same transaction. Completed and cancelled requests retain their historical assignment, but the former clinician cannot access them through the clinician workflow. PostgreSQL role-change concurrency has not been tested against a live server.

Profile lists active browser sessions and lets users sign out one browser or all browsers. Each session expires one hour after sign-in. Accounts signed in before the browser-session migration must sign in again.

## API

Issue a token using `POST /api/v1/auth/token` with JSON `{"email":"...","password":"..."}`. Send it as `Authorization: Bearer <token>` to:

- `GET`, `POST /api/v1/consultations` to list or create consultations.
- `GET`, `PATCH`, `DELETE /api/v1/consultations/<id>` to view, review, or soft-delete a consultation. Review is clinician-only; deletion is owner-only.
- `GET /api/v1/consultations/available` and `POST /api/v1/consultations/<id>/claim` let clinicians find and claim available requests.
- `POST /api/v1/consultations/<id>/release` returns an assigned in-review request to the queue.
- `GET /api/v1/notifications` and `POST /api/v1/notifications/<id>/read` provide patient-owned in-app updates.
- `POST /api/v1/chat` with `{"message":"..."}` to query the FAQ assistant.
- `GET /api/v1/chat/history` and `DELETE /api/v1/chat/history/<id>` to view or delete your saved chat entries.
- `GET /api/v1/health` is public.

Tokens expire after 24 hours. `POST /api/v1/auth/revoke` revokes the current bearer token; `POST /api/v1/auth/revoke-all` revokes all API tokens for that account. The profile page also offers account-wide API token revocation without ending the web session. Users can change their password there after providing the current password; a successful change signs out every browser and revokes all API tokens. Previously issued tokens from before this migration are invalid and must be reissued. Run `flask --app app.py purge-revoked-tokens` periodically to remove expired individual revocation records. Session-based web forms use CSRF tokens; the API uses bearer tokens rather than cookies. The profile page can also sign out all browser sessions for the account without revoking API tokens. Signed session cookies expire one hour after issuance; existing browser sessions from before the session-version migration must sign in again. Standard logout clears only the current browser cookie; use sign out all browsers to invalidate copied cookies.

## Knowledge and AI

Messages sent while signed in are stored in chat history. Users can view and delete individual entries from the navigation or API; deletion removes the entry from the active database, but existing backups may retain it. Anonymous web messages are not saved. There is no automatic retention policy. An administrator can review a bounded batch and then explicitly delete it from the active database:

```sh
flask --app app.py purge-chat-history --older-than-days 90 --batch-size 500
flask --app app.py purge-chat-history --older-than-days 90 --batch-size 500 --execute
```

The first command is a dry run; the second deletes up to the batch limit and writes a content-free audit event per entry. Repeat as needed. Select a retention period appropriate to your requirements; the example is not a recommendation. Existing backups are unaffected, and PostgreSQL concurrency has not been tested against a live server.

The FAQ page and assistant share platform questions and a small collection of sourced general-health questions in `data/general_health.json`. These are included in the same FAISS index. Local TF-IDF retrieval works with the base installation. With `requirements/ai.txt`, a locally available sentence-transformer model and `DOCIFY_SEMANTIC_SEARCH=true`, retrieval combines keyword and semantic similarity. The FAISS index uses `DOCIFY_FAISS_DIR` (default `instance/faiss`) and checks its SHA-256 digest before loading. Keep this directory writable only by the application. Model and corpus changes generate a new index.

Optional providers paraphrase the selected public FAQ. The provider prompt contains its curated question and answer. Raw user messages and stored medical records stay outside that prompt. Set `GEMINI_MODEL` and `GEMINI_API_KEY`, `OLLAMA_URL` and `OLLAMA_MODEL`, or a local sequence-to-sequence model in `HF_MODEL_PATH`. The assistant tries the configured providers in that order and falls back to the curated answer. Fever and cold or chills questions receive short, locally defined responses based on NHS guidance, with a prompt to seek age-specific care for children. General-health matches return the curated answer directly. Questions outside the indexed collection use the local fallback; FAISS cannot answer arbitrary questions without relevant indexed content. Set `DOCIFY_FAQ_CACHE=true` with Redis to cache FAQ replies for five minutes.

## Docker Compose

With Docker Compose installed, set a long `SECRET_KEY` and a URL-safe random `POSTGRES_PASSWORD` in `.env`, then run:

```sh
docker compose up -d db redis
docker compose run --rm web flask --app app.py db upgrade
docker compose up -d web worker scheduler
```

The web port is bound to localhost. PostgreSQL and Redis are not published on the host. Compose uses Redis for rate-limit storage and the Celery broker, and PostgreSQL for records. Compose also enables Redis-backed browser sessions and answer caching. The scheduler queues email delivery once per minute. Set `SMTP_HOST`, `SMTP_FROM`, and optional SMTP credentials in the worker environment to enable delivery over implicit TLS. Patients can opt in through Profile. The worker sends a generic dashboard update and retries pending deliveries on later runs. A crash after SMTP acceptance can cause a duplicate email.

## Database backups

A PostgreSQL archive utility and recovery-drill instructions are in [docs/backups.md](docs/backups.md). The utility verifies that the archive table of contents is readable; a local PostgreSQL 18 restore drill recovered a synthetic consultation. Backups are not encrypted or scheduled by the utility.

## Health and readiness

`GET /health` and `GET /api/v1/health` check database connectivity. `GET /ready` checks the database, whether the migration revision matches the project, and the configured rate-limit store. It returns HTTP 503 when a required check fails; a development in-memory rate limiter is reported as `local`. The endpoint does not check Celery workers, bot connections, model availability, or external delivery. The Compose web health check uses `/ready`. Local integration checks used PostgreSQL 18 and Redis 8. The Compose stack still needs a Docker-host smoke test.

## Production configuration guard

`DOCIFY_ENV=production` enables startup checks for a non-default secret of at least 32 bytes, PostgreSQL, Redis-backed rate limits, secure HTTP-only cookies, CSRF protection, and disabled debug mode. Set `SESSION_COOKIE_SECURE=true` only when serving through HTTPS, and set `FLASK_DEBUG=0`. Generate a strong random secret; the guard checks length and known defaults but cannot verify randomness. Compose passes `DOCIFY_ENV` through and remains in development mode by default. These checks do not replace TLS, infrastructure validation, security review, or the other work required before using real patient data.

## Messaging adapters

Install `requirements/bot.txt` to run `python -m bots.telegram_bot` or `python -m bots.discord_bot` after setting the appropriate token. The optional Compose `bots` profile runs these processes. Use Profile to generate a single-use pairing code for one platform. In a private conversation, use `/link CODE`, then `/consult DESCRIPTION`, `/status` or `/unlink`. A code expires after five minutes and a linked session lasts 24 hours. Account-wide API token revocation also invalidates linked sessions. Pairing requires Redis. The bot processes must share the same database, Redis service and secret as the web app. Each platform limits each sender to ten requests per minute. Standalone development can use an in-process limiter by leaving REDIS_URL unset.

The WhatsApp webhook requires `TWILIO_AUTH_TOKEN` and the exact externally visible `TWILIO_WEBHOOK_URL`. It verifies Twilio's signature before responding and fails closed when unconfigured. External bot services and credentials have not been tested end to end.

## Remaining work

- Verify clinician identity and review the medical workflows.
- Expand audit coverage to all required changes and other record access, protect the audit store from privileged administrators, and implement deployment-specific encryption and security/privacy controls.
- Validate provider responses with the intended production models and the clinical review team.
- Verify live bot accounts, SMTP delivery, deployment monitoring, TLS, off-host backups and recovery procedures.
- Perform end-to-end infrastructure, accessibility, clinical safety and security testing before any real-world use.

The audit log records actor, action, record ID and field names for selected application changes and successful authentication events without duplicating clinical text. It also records successful profile views and consultation details shown in the dashboard, clinician queue and consultation API; list views record each returned consultation. Database migrations install append-only triggers that block updates and deletes on SQLite and PostgreSQL (and PostgreSQL truncation). These triggers do not prevent a privileged database owner from altering the schema, and the log does not capture every database mutation, denied access attempt, or record access. Chat-history views and deletions are audited without storing message contents. A PostgreSQL 18 restore drill verified that the audit trigger rejects updates. Local rate limiting uses in-memory storage unless a shared backend is configured. `ALLOWED_IPS` filters the direct peer only and does not trust forwarded headers.

The token endpoint also issues a seven-day refresh token. Send it as a bearer token to `POST /api/v1/auth/refresh` to receive a fresh pair. Each refresh token works once. Account-wide revocation invalidates both token types. Revoking an individual access token affects only that token.

The CI Compose smoke job builds the web image, applies migrations, waits for readiness and round-trips a Celery task. Compose rotates container logs and stores Redis snapshots in a named volume.

For a public TLS deployment, configure DNS for `DOCIFY_DOMAIN`, open ports 80 and 443, and start Compose with `-f docker-compose.yml -f deploy/compose.tls.yml`. The override enables production settings and the Caddy reverse proxy. The deployment host must provide the required secrets and database migrations.
