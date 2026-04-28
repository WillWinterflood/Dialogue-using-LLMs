"""
src/embedder.py

Lazy-loaded sentence embedding model for semantic memory retrieval.

Why a separate module?
  Both the write path (state_manager._persist_turn_memory) and the read path
  (memory_retrieval._retrieve_memories) need to embed text.  Putting the model
  in a singleton here means it is loaded once and reused, rather than
  re-initialised on every call or duplicated across modules.

Model choice — all-MiniLM-L6-v2:
  22 MB, runs comfortably on CPU alongside the main GPU model.
  Produces 384-dimensional embeddings with strong semantic coverage for
  short dialogue and summary text.  See:
    Reimers & Gurevych (2019) "Sentence-BERT: Sentence Embeddings using
    Siamese BERT-Networks", EMNLP 2019.
"""
import numpy as np

_model = None  # Populated on first call to embed()

def _get_model():
    global _model
    if _model is not None:
        return _model if _model is not False else None

    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        # sentence-transformers not installed — mark unavailable so we don't
        # retry on every call.  All callers check for None and fall back.
        _model = False

    return _model if _model is not False else None


def embed(text):
    """Return a normalised numpy embedding vector, or None if unavailable."""
    model = _get_model()
    if model is None:
        return None
    try:
        return model.encode(str(text or ""), normalize_embeddings=True)
    except Exception:
        return None


def cosine_similarity(a, b):
    """Cosine similarity between two array-like vectors.  Returns 0.0 on failure.

    Because embed() uses normalize_embeddings=True the vectors are already
    unit-length, so this is just a dot product — but the explicit normalisation
    step guards against stored embeddings that were computed without that flag.
    """
    try:
        a = np.array(a, dtype=float)
        b = np.array(b, dtype=float)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    except Exception:
        return 0.0
