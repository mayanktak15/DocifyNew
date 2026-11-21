# 🧠 ML Pipeline — FAISS + Embeddings + RAG

> Complete technical guide for the retrieval-augmented generation pipeline.

---

## 1. Pipeline Overview

```
User Query
    │
    ▼
┌─────────────────────┐
│  Rule-Based Matcher  │──→ Hardcoded response (fever, docify, etc.)
└─────────┬───────────┘
          │ No match
          ▼
┌─────────────────────┐
│   Text Preprocessing │──→ Lowercasing, whitespace normalization
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌────────┐  ┌──────────────┐
│ TF-IDF │  │ FAISS Search │
│ Scoring│  │ (Embedding)  │
└───┬────┘  └──────┬───────┘
    │              │
    ▼              ▼
┌─────────────────────────┐
│    Rank Fusion           │
│  score = w₁·kw + w₂·emb │
└─────────┬───────────────┘
          │
          ▼
    Top-K Documents
          │
          ▼
┌─────────────────────────┐
│   Context Assembly       │──→ Join docs, truncate to MAX_CONTEXT_CHARS
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│   LLM Provider Chain     │
│  Gemini → Ollama → HF   │
│  → FAQ fallback          │
└─────────┬───────────────┘
          │
          ▼
    Final Response
          │
          ▼
┌─────────────────────────┐
│  Redis Cache + DB Log    │
└─────────────────────────┘
```

---

## 2. Embedding Model

### 2.1 Model: `sentence-transformers/all-MiniLM-L6-v2`

| Property | Value |
|----------|-------|
| Dimensions | 384 |
| Max Sequence Length | 256 tokens |
| Model Size | ~80 MB |
| CPU Inference Time | ~20-50ms per query |
| Similarity Metric | Cosine (via normalized inner product) |

### 2.2 Lazy Loading Strategy

```python
class EmbeddingEngine:
    """Singleton pattern with lazy initialization"""
    _instance = None
    _model = None
    
    @classmethod
    def get_model(cls):
        if cls._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                cls._model = SentenceTransformer(
                    'sentence-transformers/all-MiniLM-L6-v2',
                    device='cpu'
                )
            except ImportError:
                return None  # AI deps not installed
        return cls._model
    
    @classmethod
    def embed(cls, texts: list[str]) -> np.ndarray | None:
        model = cls.get_model()
        if model is None:
            return None
        embeddings = model.encode(texts, normalize_embeddings=True)
        return np.asarray(embeddings, dtype='float32')
```

**Why lazy loading?**
- Model download happens only on first use (~80 MB)
- App boots in < 1 second without AI deps
- Memory allocated only when chatbot is actually used

### 2.3 Normalization

Embeddings are normalized (`normalize_embeddings=True`) so that:
- Inner product = cosine similarity
- FAISS `IndexFlatIP` can be used (faster than `IndexFlatL2` + normalization)
- Score range: [0, 1] where 1 = identical meaning

---

## 3. FAISS Vector Store

### 3.1 Index Type: `IndexFlatIP`

| Property | Value |
|----------|-------|
| Algorithm | Flat (brute-force) inner product |
| Complexity | O(n) per query |
| Accuracy | Exact (100%) |
| Suitable for | < 100K vectors |

**Why flat index?** For FAQ-scale data (50-500 documents), brute-force is faster than approximate methods because there's no overhead for tree/graph construction.

### 3.2 Index Build & Cache

```python
class FAQVectorStore:
    def load_or_build(self, docs: list[str]) -> bool:
        """
        1. Compute SHA256 hash of FAQ source + model name
        2. Check if cached index exists with matching hash
        3. If match → load from disk (< 5ms)
        4. If no match → embed all docs, build index, save to disk
        """
        source_hash = self._compute_hash()
        
        if self._try_load_cache(source_hash):
            return True  # Loaded in < 5ms
        
        # Build new index (~2-5 seconds for 50 docs)
        vectors = EmbeddingEngine.embed(docs)
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(np.ascontiguousarray(vectors))
        
        # Persist
        faiss.write_index(self.index, self.index_path)
        self._save_meta(source_hash, len(docs))
        return True
```

### 3.3 Hash-Based Cache Validation

```python
def _compute_hash(self) -> str:
    """SHA256 of FAQ file content + embedding model name"""
    hasher = hashlib.sha256()
    with open(FAQ_FILE_PATH, 'rb') as f:
        hasher.update(f.read())
    hasher.update(EMBEDDING_MODEL.encode('utf-8'))
    return hasher.hexdigest()
```

**Cache invalidation triggers:**
- FAQ file content changes → new hash → rebuild
- Embedding model changes → new hash → rebuild
- Manual: delete `instance/faq_faiss.idx` and `faq_faiss.json`
- Async: Celery task `rebuild_faiss_index.delay()`

### 3.4 Search

```python
def search(self, query: str, top_k: int = 3) -> list[tuple[int, float]]:
    query_vec = EmbeddingEngine.embed([query])  # Shape: (1, 384)
    
    # FAISS search returns (scores, indices) arrays
    scores, indices = self.index.search(
        np.ascontiguousarray(query_vec),
        top_k
    )
    
    return [
        (int(idx), float(score))
        for score, idx in zip(scores[0], indices[0])
        if idx != -1  # -1 means no result
    ]
```

### 3.5 Fallback When FAISS Unavailable

```python
# When faiss-cpu is not installed, fall back to NumPy
if not HAS_FAISS:
    # Store raw embeddings as NumPy array
    self.embeddings = vectors  # Shape: (n_docs, 384)
    
    # Search via matrix multiplication
    scores = self.embeddings @ query_vec.T  # Dot product
    top_indices = np.argsort(scores)[::-1][:top_k]
```

---

## 4. Keyword Scoring

### 4.1 TF-IDF (Primary)

```python
from sklearn.feature_extraction.text import TfidfVectorizer

def tfidf_scores(query: str, docs: list[str]) -> list[float]:
    vectorizer = TfidfVectorizer(stop_words='english')
    matrix = vectorizer.fit_transform(docs + [query])
    
    doc_vectors = matrix[:-1]    # All docs
    query_vector = matrix[-1]     # Last row = query
    
    # Cosine similarity via sparse matrix multiplication
    scores = (doc_vectors @ query_vector.T).toarray().ravel()
    return scores.tolist()
```

### 4.2 Simple Overlap (Fallback)

```python
def simple_overlap_scores(query: str, docs: list[str]) -> list[float]:
    """When scikit-learn is not available"""
    query_tokens = set(query.lower().split())
    scores = []
    for doc in docs:
        doc_tokens = set(doc.lower().split())
        overlap = len(query_tokens & doc_tokens)
        scores.append(overlap / max(len(doc_tokens), 1))
    return scores
```

---

## 5. Hybrid Rank Fusion

### 5.1 Score Combination

```python
# Default weights (configurable via env)
KEYWORD_WEIGHT = 0.6    # TF-IDF / overlap
EMBEDDING_WEIGHT = 0.4  # FAISS semantic

combined_score = (KEYWORD_WEIGHT * keyword_score) + (EMBEDDING_WEIGHT * embedding_score)
```

### 5.2 Why This Ratio?

| Weight Config | Best For |
|---------------|----------|
| kw=1.0, emb=0.0 | Exact keyword matching (FAQ-style) |
| kw=0.0, emb=1.0 | Pure semantic (paraphrase detection) |
| **kw=0.6, emb=0.4** | **Mixed FAQ + medical queries (default)** |
| kw=0.3, emb=0.7 | Conversational / varied phrasing |

The 0.6/0.4 default works well because:
- FAQ questions often use exact keywords ("medical certificate", "consultation fee")
- Semantic search catches paraphrases ("how much does it cost?" → "consultation fee")
- Keyword bias prevents semantic false positives on short queries

---

## 6. LLM Provider Chain

### 6.1 Provider Hierarchy

```
Priority 0: Rule-based matcher (zero latency, zero dependency)
    ↓ no match
Priority 1: Google Gemini API (best quality, requires API key + internet)
    ↓ exception
Priority 2: Ollama local server (good quality, requires Ollama running)
    ↓ exception
Priority 3: HuggingFace CPU (acceptable quality, slow on CPU)
    ↓ exception
Priority 4: FAQ text fallback (basic, always works)
```

### 6.2 Provider Comparison

| Provider | Latency | Quality | Cost | Requires |
|----------|---------|---------|------|----------|
| Gemini API | 500ms-2s | ★★★★★ | Per-token | API key + internet |
| Ollama | 1-5s | ★★★★ | Free | Ollama server running |
| HuggingFace CPU | 5-15s | ★★★ | Free | torch + transformers |
| FAQ fallback | < 1ms | ★★ | Free | Nothing |

### 6.3 Context Assembly

```python
def _assemble_context(docs: list[Document], max_chars: int = 1500) -> str:
    """Join retrieved documents into context string, respecting char limit"""
    chunks = []
    remaining = max_chars
    
    for doc in docs:
        content = doc.content.strip()
        if len(content) > remaining:
            content = content[:remaining].rstrip() + '...'
        chunks.append(content)
        remaining -= len(content)
        if remaining <= 0:
            break
    
    return '\n\n'.join(chunks)
```

---

## 7. Performance Characteristics

| Operation | Time | Memory |
|-----------|------|--------|
| Model loading (first time) | 2-5s | ~200 MB |
| Model loading (cached) | < 100ms | ~200 MB |
| FAISS index load from disk | < 5ms | ~1 MB (for 50 docs) |
| FAISS index build (50 docs) | 2-5s | ~1 MB |
| Single query embedding | 20-50ms | Negligible |
| FAISS search (50 docs) | < 1ms | Negligible |
| TF-IDF scoring (50 docs) | < 5ms | Negligible |
| Full RAG pipeline | 50-100ms | Negligible |
| + Gemini API | +500ms-2s | Negligible |
| + Redis cache hit | < 1ms | Negligible |

---

## 8. Async Index Rebuild (Celery)

```python
# tasks/embedding_tasks.py
from celery import shared_task
from chatbot.vectorstore import FAQVectorStore
from chatbot.data import load_faq_blocks

@shared_task(bind=True, max_retries=3)
def rebuild_faiss_index(self):
    """Rebuild FAISS index asynchronously when FAQ data changes"""
    try:
        redis_client.set('docify:faiss:status', 'building')
        
        docs = load_faq_blocks()
        store = FAQVectorStore()
        success = store.load_or_build(docs, force_rebuild=True)
        
        redis_client.set('docify:faiss:status', 'ready')
        return {'status': 'success', 'doc_count': len(docs)}
    except Exception as exc:
        redis_client.set('docify:faiss:status', 'error')
        self.retry(exc=exc, countdown=60)
```

---

## 9. Monitoring ML Pipeline

```python
# Metrics to track
metrics = {
    'chatbot_requests_total': Counter,
    'chatbot_cache_hits': Counter,
    'chatbot_cache_misses': Counter,
    'chatbot_response_time_ms': Histogram,
    'chatbot_provider_used': Counter (by provider),
    'faiss_search_time_ms': Histogram,
    'embedding_time_ms': Histogram,
    'faiss_index_doc_count': Gauge,
}
```

Log format for each chatbot request:
```json
{
    "timestamp": "2026-11-21T14:30:00Z",
    "query": "What is Docify?",
    "provider": "gemini",
    "cache_hit": false,
    "response_time_ms": 1250,
    "faiss_search_time_ms": 0.8,
    "top_doc_score": 0.87,
    "docs_retrieved": 3,
    "platform": "telegram"
}
```
