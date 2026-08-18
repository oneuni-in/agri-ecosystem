"""A-U4 W1 — local embeddings.

WHY LOCAL. The module rule is that this module must never send user PII to
external model APIs. A visitor's question is exactly the kind of text that
can carry PII ("my field near <village>, my neighbour said..."), and RAG
needs that question embedded before anything is retrieved. Sending it to a
hosted embedding service would put raw questions in a third party's logs
before a single safety check had run.

fastembed runs BAAI/bge-small-en-v1.5 as ONNX on the CPU, in our process:
~50MB, no torch, no network. The only call that leaves our infrastructure is
the final answer call to Anthropic, and by then the question has passed the
scope guard and the regulated-domain refusals.

The model is loaded LAZILY and cached, because importing this module must
stay cheap: `main.py` imports every module's router at boot, and a
multi-hundred-millisecond model load on an API that has the assistant flag
OFF would be a startup cost paid by every deployment for nothing.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from settings import get_settings

from .models import EMBEDDING_DIMS

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

__all__ = ["embed_query", "embed_passages", "embedding_available"]

_lock = threading.Lock()
_model: Any | None = None


def _load() -> Any:
    """Load once, under a lock. Returns None if fastembed is unavailable so
    callers degrade to "no retrieval" rather than 500 — an assistant that
    cannot retrieve must say it has nothing, not crash the API."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            from fastembed import TextEmbedding
        except Exception:  # noqa: BLE001 - optional at import time
            return None
        settings = get_settings()
        model = TextEmbedding(model_name=settings.ai_embedding_model)
        _model = model
        return _model


def embedding_available() -> bool:
    return _load() is not None


def _check_width(vector: list[float]) -> list[float]:
    """A width mismatch means the configured model is not the model the
    schema was built for. That is a deployment error, and it must be loud:
    silently storing 512 floats in a vector(384) column fails later, further
    away, and looks like a retrieval bug."""
    if len(vector) != EMBEDDING_DIMS:
        raise RuntimeError(
            f"embedding width {len(vector)} != schema width {EMBEDDING_DIMS}; "
            "ai_embedding_model and migration 0047 disagree"
        )
    return vector


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed corpus passages for ingest."""
    model = _load()
    if model is None or not texts:
        return []
    return [_check_width(list(map(float, v))) for v in model.embed(texts)]


def embed_query(text: str) -> list[float] | None:
    """Embed one visitor question. None when embeddings are unavailable —
    the caller then answers "I don't have sources for that" rather than
    retrieving nothing and pretending it looked."""
    model = _load()
    if model is None or not text.strip():
        return None
    vectors = list(model.embed([text]))
    if not vectors:
        return None
    return _check_width(list(map(float, vectors[0])))
