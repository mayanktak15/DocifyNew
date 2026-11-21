"""Optional local FAISS cache; hashes detect accidental corruption, not hostile edits."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def corpus_key(docs, model_name, model):
    import numpy as np
    # A deterministic probe also invalidates caches when local model weights change.
    probe = np.asarray(model.encode(['Docify FAQ embedding version'], normalize_embeddings=True), dtype='float32')
    payload = json.dumps({'questions': [d['question'] for d in docs], 'model': model_name}, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(payload + probe.tobytes()).hexdigest()


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix='.faq-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_or_build(docs, model, cache_dir, model_name):
    import faiss
    import numpy as np
    key = corpus_key(docs, model_name, model)
    directory = Path(cache_dir)
    index_path = directory / ('faq-' + key + '.faiss')
    digest_path = directory / ('faq-' + key + '.sha256')
    # Do not deserialize bytes unless the paired checksum matches.
    try:
        if index_path.stat().st_size > 32 * 1024 * 1024 or digest_path.stat().st_size > 128:
            raise ValueError('Invalid cache size')
        blob = index_path.read_bytes()
        expected = digest_path.read_text(encoding='ascii').strip()
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError('Invalid cache')
        index = faiss.deserialize_index(np.frombuffer(blob, dtype=np.uint8).copy())
        if not isinstance(index, faiss.IndexFlatIP) or index.ntotal != len(docs) or index.d != model.get_sentence_embedding_dimension():
            raise ValueError('Invalid cached index')
        return index
    except (OSError, ValueError, RuntimeError):
        pass
    embeddings = np.asarray(model.encode([d['question'] for d in docs], normalize_embeddings=True), dtype='float32')
    if embeddings.ndim != 2 or embeddings.shape[0] != len(docs) or embeddings.shape[1] != model.get_sentence_embedding_dimension():
        raise ValueError('Invalid embeddings')
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    # Caching is best effort: the in-memory index remains usable if storage fails.
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        blob = faiss.serialize_index(index).tobytes()
        atomic_write(index_path, blob)
        atomic_write(digest_path, hashlib.sha256(blob).hexdigest().encode('ascii'))
    except OSError:
        pass
    return index
