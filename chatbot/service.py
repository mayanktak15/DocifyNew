"""Retrieve verified platform facts; never turn FAQ matching into medical advice."""
from functools import lru_cache
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import threading

DATA = Path(__file__).resolve().parent.parent / 'data' / 'faq.json'
STOP = {'a', 'an', 'and', 'are', 'can', 'do', 'for', 'how', 'i', 'in', 'is', 'my', 'of', 'on', 'the', 'to', 'what', 'where', 'with', 'you'}
EMERGENCY = ('chest pain', 'difficulty breathing', 'cannot breathe', "can't breathe", 'stroke', 'suicide', 'suicidal', 'overdose', 'severe bleeding')
GENERAL = 'I can help you navigate Docify. For health concerns, please speak with a qualified clinician. Seek urgent help for severe or worsening symptoms.'
_lock = threading.Lock()


def tokens(text):
    return set(re.findall(r'[a-z0-9]+', text.lower())) - STOP


@lru_cache(maxsize=1)
def documents():
    with DATA.open(encoding='utf-8') as stream:
        platform = json.load(stream)
    with (DATA.parent / 'general_health.json').open(encoding='utf-8') as stream:
        return platform + json.load(stream)


def keyword_scores(query, docs):
    """TF-IDF cosine scores using only the standard library."""
    terms = tokens(query)
    if not terms or not docs:
        return [0.0] * len(docs)
    vectors = [Counter(re.findall(r'[a-z0-9]+', doc['question'].lower())) for doc in docs]
    vocabulary = set().union(*(set(v) for v in vectors), terms) - STOP
    idf = {word: math.log((len(docs) + 1) / (1 + sum(word in v for v in vectors))) + 1 for word in vocabulary}
    q = {word: idf[word] for word in terms if word in idf}
    qnorm = math.sqrt(sum(value * value for value in q.values()))
    scores = []
    for counts in vectors:
        weights = {word: count * idf[word] for word, count in counts.items() if word in idf}
        norm = math.sqrt(sum(value * value for value in weights.values()))
        dot = sum(weight * weights.get(word, 0) for word, weight in q.items())
        scores.append(dot / (qnorm * norm) if qnorm and norm else 0.0)
    return scores


@lru_cache(maxsize=1)
def semantic_model():
    if os.getenv('DOCIFY_SEMANTIC_SEARCH', '').lower() != 'true':
        return None
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(os.getenv('DOCIFY_EMBEDDING_MODEL', 'all-MiniLM-L6-v2'), local_files_only=True)
    except Exception:
        return None


@lru_cache(maxsize=1)
def semantic_index():
    model = semantic_model()
    if model is None:
        return None
    try:
        from .vectorstore import load_or_build
        cache_dir = os.getenv('DOCIFY_FAISS_DIR', str(DATA.parent.parent / 'instance' / 'faiss'))
        model_name = os.getenv('DOCIFY_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        return load_or_build(documents(), model, cache_dir, model_name)
    except Exception:
        return None


def ranked_documents(query, limit=3):
    docs = documents()
    keyword = keyword_scores(query, docs)
    scores = keyword
    semantic = None
    try:
        with _lock:
            index, model = semantic_index(), semantic_model()
            if index is not None and model is not None:
                import numpy as np
                vector = np.asarray(model.encode([query], normalize_embeddings=True), dtype='float32')
                values, indices = index.search(vector, len(docs))
                semantic = [0.0] * len(docs)
                for i, score in zip(indices[0], values[0]):
                    if i >= 0:
                        semantic[int(i)] = max(0.0, float(score))
                weight = min(1.0, max(0.0, float(os.getenv('DOCIFY_KEYWORD_WEIGHT', '0.6'))))
                scores = [weight * k + (1 - weight) * s for k, s in zip(keyword, semantic)]
    except Exception:
        scores = keyword
    terms = tokens(query)
    ordered = sorted(range(len(docs)), key=scores.__getitem__, reverse=True)
    return [docs[i] for i in ordered if (scores[i] >= 0.2 and terms & tokens(docs[i]['question']))
            or (semantic is not None and semantic[i] >= 0.70)][:limit]


def retrieve(query):
    return next(iter(ranked_documents(query, 1)), None)


def respond(message):
    normalized = message.lower()
    if any(term in normalized for term in EMERGENCY):
        return {'reply': 'If this may be an emergency, contact local emergency services now or seek immediate in-person help.', 'provider': 'fallback'}
    if re.search(r"\b(cold|chills|shivering|shivery)\b", normalized):
        return {'reply': (
            'Do you mean you feel cold or shivery, or that you have a cold with symptoms such as a runny nose or cough? '
            'If you feel shivery, check your temperature if you can. Rest and drink fluids. '
            'Seek medical advice if you are getting worse or are concerned, especially for a baby or child. '
            'Get urgent help for severe symptoms. '
            'More information: https://www.nhs.uk/conditions/common-cold/'
        ), 'provider': 'health_guidance'}
    if re.search(r"\b(fever|feverish|high temperature)\b", normalized):
        return {'reply': (
            'I’m sorry you’re feeling unwell. If you can, check your temperature, rest and drink fluids. '
            'Seek medical advice promptly if the fever is getting worse or is not improving. '
            'If this concerns a baby or child, contact a clinician for age-specific advice. '
            'For serious symptoms, seek urgent medical help. '
            'For adult fever guidance, see https://www.nhs.uk/symptoms/fever-in-adults/'
        ), 'provider': 'health_guidance'}
    matches = ranked_documents(message)
    if matches:
        if matches[0].get('category') == 'general_health':
            return {'reply': matches[0]['answer'], 'provider': 'health_guidance'}
        match = dict(matches[0], related=[doc['answer'] for doc in matches[1:]])
        from .providers import generate
        if os.getenv('DOCIFY_FAQ_CACHE', '').lower() == 'true':
            from .response_cache import cached_answer
            return cached_answer(match, generate)
        return generate(match)
    return {'reply': GENERAL, 'provider': 'fallback'}
