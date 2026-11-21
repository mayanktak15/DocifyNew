# 📝 RAG Prompt Template

> The prompt template used to inject retrieved context into LLM queries.

---

## Template

```
Context:
{context}

User Query: {question}
{symptoms_section}

Provide your response according to the system rules and template:
```

---

## Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `{context}` | HybridRetriever output | Top-K FAQ documents, joined with `\n\n`, max 1500 chars |
| `{question}` | User input | The raw user query |
| `{symptoms_section}` | Latest consultation or empty | `\nUser Symptoms: {symptoms}` or empty string |

---

## Example — Filled Template

```
Context:
**1. What is Docfiy?**
Docfiy is an online healthcare platform that connects users with certified doctors for quick,
reliable consultations, prescriptions, and medical certificates — all from the comfort of your home.

**2. How does an online consultation work on Docfiy?**
Simply submit your symptoms on the website. Based on your inputs, a qualified doctor will review
your case and respond via chat or call with medical advice, a prescription (if needed), or a
medical certificate.

User Query: How do I get a consultation?

Provide your response according to the system rules and template:
```

---

## Expected LLM Output

```
**Answer**: To get a consultation on Docify, simply log in to your account, navigate to the
dashboard, and submit your symptoms through the consultation form. A qualified doctor will
review your case and respond with medical advice.

**Additional Info**: Most responses are received within 10-30 minutes. You can also use the
chatbot for quick questions or book a video/voice consultation for more detailed discussions.
```

---

## Context Assembly Logic

```python
def _assemble_context(docs: list[Document], max_chars: int = 1500) -> str:
    """
    Join retrieved documents into a context string.
    
    Rules:
    1. Documents are ordered by rank fusion score (highest first)
    2. Total context is capped at MAX_CONTEXT_CHARS (default 1500)
    3. If a document exceeds remaining space, it's truncated with '...'
    4. Documents are separated by double newlines
    """
    chunks = []
    remaining = max_chars
    
    for doc in docs:
        content = doc.content.strip()
        if not content:
            continue
        if len(content) > remaining:
            content = content[:remaining].rstrip() + '...'
        chunks.append(content)
        remaining -= len(content)
        if remaining <= 0:
            break
    
    return '\n\n'.join(chunks)
```

---

## Symptoms Injection

```python
# Only injected when user has an active consultation
symptoms_section = ""
if symptoms:
    symptoms_section = f"\nUser Symptoms: {symptoms}"

# In bot context, symptoms come from the /consult command
# In web context, symptoms come from the user's latest consultation
```
