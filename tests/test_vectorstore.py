import pytest
np = pytest.importorskip('numpy')
pytest.importorskip('faiss')
from chatbot.vectorstore import load_or_build
from chatbot.service import keyword_scores


class Model:
    def __init__(self, revision=1):
        self.batches = []
        self.revision = revision

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, texts, normalize_embeddings=True):
        self.batches.append(list(texts))
        vectors = np.asarray([[len(text), sum(map(ord, text)) % 127, self.revision] for text in texts], dtype='float32')
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def test_tfidf_ranks_matching_question():
    docs = [{'question': 'How do I update my profile?'}, {'question': 'How do I submit a consultation?'}]
    scores = keyword_scores('update profile', docs)
    assert scores[0] > scores[1]
    assert keyword_scores('the and', docs) == [0.0, 0.0]


def test_index_reuses_cache_and_rebuilds_for_corruption_and_changes(tmp_path):
    docs = [{'question': 'How do I log in?'}, {'question': 'How do I log out?'}]
    model = Model()
    index = load_or_build(docs, model, tmp_path, 'test-model')
    assert index.ntotal == 2 and len(model.batches) == 2
    index = load_or_build(docs, model, tmp_path, 'test-model')
    assert index.ntotal == 2 and len(model.batches) == 3
    index_path = next(tmp_path.glob('*.faiss'))
    index_path.write_bytes(b'corrupt')
    index = load_or_build(docs, model, tmp_path, 'test-model')
    assert index.ntotal == 2 and len(model.batches) == 5
    changed = docs + [{'question': 'How do I get help?'}]
    assert load_or_build(changed, model, tmp_path, 'test-model').ntotal == 3
    assert len(list(tmp_path.glob('*.faiss'))) == 2
    updated = Model(revision=2)
    assert load_or_build(docs, updated, tmp_path, 'test-model').ntotal == 2
    assert len(list(tmp_path.glob('*.faiss'))) == 3


def test_index_works_when_cache_is_unwritable(tmp_path):
    file_path = tmp_path / 'not-a-directory'
    file_path.write_text('x')
    assert load_or_build([{'question': 'Question?'}], Model(), file_path, 'test').ntotal == 1


def test_chat_retrieval_uses_semantic_matches_without_shared_words(monkeypatch):
    from chatbot import service
    docs = [{'question': 'How do I log out?', 'answer': 'Use the log out button.'}]
    class SemanticModel:
        def encode(self, texts, normalize_embeddings=True):
            return np.asarray([[1.0, 0.0]], dtype='float32')
    import faiss
    index = faiss.IndexFlatIP(2)
    index.add(np.asarray([[1.0, 0.0]], dtype='float32'))
    monkeypatch.setattr(service, 'documents', lambda: docs)
    monkeypatch.setattr(service, 'semantic_model', lambda: SemanticModel())
    monkeypatch.setattr(service, 'semantic_index', lambda: index)
    assert service.respond('sign off')['reply'] == 'Use the log out button.'
    monkeypatch.setattr(service, 'semantic_index', lambda: None)
    assert service.respond('sign off')['provider'] == 'fallback'
