# 📡 API Reference

> REST API endpoints for Docify v2. All `/api/v1/*` endpoints require JWT authentication unless noted.

---

## Authentication

### Issue JWT Token

```http
POST /api/v1/auth/token
Content-Type: application/json

{
    "email": "user@example.com",
    "password": "SecurePassword123"
}
```

**Response** `200 OK`:
```json
{
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_in": 86400,
    "user": {
        "id": 1,
        "name": "John Doe",
        "email": "user@example.com"
    }
}
```

**Error** `401`:
```json
{ "error": "Invalid email or password" }
```

### Using the Token

Include in all API requests:
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

## Consultations

### List Consultations

```http
GET /api/v1/consultations?page=1&per_page=10&status=pending
Authorization: Bearer <token>
```

**Response** `200 OK`:
```json
{
    "consultations": [
        {
            "id": 1,
            "symptoms": "Headache and mild fever",
            "status": "pending",
            "priority": "normal",
            "doctor_notes": null,
            "prescription": null,
            "created_at": "2026-11-21T10:30:00Z",
            "updated_at": "2026-11-21T10:30:00Z"
        }
    ],
    "pagination": {
        "page": 1,
        "per_page": 10,
        "total": 1,
        "pages": 1
    }
}
```

### Create Consultation

```http
POST /api/v1/consultations
Authorization: Bearer <token>
Content-Type: application/json

{
    "symptoms": "Persistent cough for 3 days with mild fever",
    "priority": "high"
}
```

**Response** `201 Created`:
```json
{
    "id": 2,
    "symptoms": "Persistent cough for 3 days with mild fever",
    "status": "pending",
    "priority": "high",
    "created_at": "2026-11-21T14:30:00Z"
}
```

### Get Single Consultation

```http
GET /api/v1/consultations/2
Authorization: Bearer <token>
```

**Response** `200 OK`:
```json
{
    "id": 2,
    "symptoms": "Persistent cough for 3 days with mild fever",
    "status": "in_review",
    "priority": "high",
    "doctor_notes": "Likely viral infection. Rest recommended.",
    "prescription": "Paracetamol 500mg twice daily for 3 days",
    "created_at": "2026-11-21T14:30:00Z",
    "updated_at": "2026-11-21T15:00:00Z"
}
```

### Update Consultation Status

```http
PATCH /api/v1/consultations/2
Authorization: Bearer <token>
Content-Type: application/json

{
    "status": "completed",
    "doctor_notes": "Viral infection confirmed. Recovery expected in 5 days.",
    "prescription": "Paracetamol 500mg, Cetirizine 10mg"
}
```

**Response** `200 OK`:
```json
{
    "id": 2,
    "status": "completed",
    "message": "Consultation updated successfully"
}
```

### Delete Consultation (Soft Delete)

```http
DELETE /api/v1/consultations/2
Authorization: Bearer <token>
```

**Response** `200 OK`:
```json
{
    "success": true,
    "message": "Consultation soft-deleted"
}
```

---

## Chatbot

### Send Message

```http
POST /api/v1/chat
Authorization: Bearer <token>
Content-Type: application/json

{
    "message": "What is Docify Online?",
    "symptoms": "headache"
}
```

**Response** `200 OK`:
```json
{
    "reply": "**Answer**: Docify Online is a platform for medical consultations...\n**Additional Info**: ...",
    "provider": "gemini",
    "cached": false,
    "response_time_ms": 1250
}
```

### Rate Limit
- 10 requests per minute per user
- Returns `429 Too Many Requests` when exceeded

---

## Health Check

### System Health (No Auth Required)

```http
GET /api/v1/health
```

**Response** `200 OK`:
```json
{
    "status": "healthy",
    "components": {
        "database": {
            "status": "up",
            "type": "postgresql",
            "latency_ms": 2
        },
        "redis": {
            "status": "up",
            "latency_ms": 1
        },
        "faiss_index": {
            "status": "loaded",
            "doc_count": 48,
            "model": "all-MiniLM-L6-v2"
        },
        "celery": {
            "status": "up",
            "active_tasks": 0
        }
    },
    "version": "2.0.0"
}
```

---

## Web Chatbot Endpoint

### POST /chatbot (Web — CSRF Protected)

```http
POST /chatbot
Content-Type: application/json
X-CSRFToken: <csrf_token>

{
    "message": "How do I submit a consultation?"
}
```

**Response** `200 OK`:
```json
{
    "reply": "To submit a consultation form: log in, open the dashboard, and fill in your symptoms."
}
```

---

## Error Responses

All errors follow a consistent format:

| Status | Meaning | Body |
|--------|---------|------|
| 400 | Bad Request | `{"error": "Please provide a message."}` |
| 401 | Unauthorized | `{"error": "Invalid or expired token"}` |
| 403 | Forbidden | `{"error": "Forbidden"}` |
| 404 | Not Found | `{"error": "Not Found"}` |
| 429 | Rate Limited | `{"error": "Rate limit exceeded. Try again later."}` |
| 500 | Server Error | `{"error": "Internal Server Error"}` |
