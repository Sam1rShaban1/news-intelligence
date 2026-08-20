"""Text embeddings for semantic (nearest-neighbour) search.

On the VPS tier a real multilingual model is used (fastembed / sentence-transformers,
downloads its weights on first use, mirroring the NER model). When neither library is
installed (e.g. the Pi build, or tests), a deterministic character/word-hashing encoder
produces real 384-dim unit vectors so the semantic-search pipeline still works end to
end — it just uses a weaker signal. Swap the encoder via `get_embedder()`.
"""

import hashlib
import logging
import math
import re

logger = logging.getLogger(__name__)

EMBED_DIM = 384


class _HashingEmbedder:
    """Deterministic, dependency-free multilingual-ish encoder (baseline)."""

    dim = EMBED_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = re.findall(r"\w+", (text or "").lower())
        if not tokens:
            tokens = [text[i : i + 3] for i in range(len(text or "") - 2)]
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            vec[idx] += 1.0 if (h >> 9) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


class _FastEmbed:
    dim = EMBED_DIM

    def __init__(self, model) -> None:
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        out = self.model.encode(texts)
        return [list(map(float, v)) for v in np.asarray(out)]


class _SentenceTransformer:
    dim = EMBED_DIM

    def __init__(self, model) -> None:
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        out = self.model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in np.asarray(out)]


def get_embedder():
    """Return the best available embedder (real model preferred, hashing fallback)."""
    try:
        from fastembed import SentenceEmbedding

        logger.info("Using fastembed for article embeddings")
        return _FastEmbed(SentenceEmbedding(model_name="intfloat/multilingual-e5-small"))
    except Exception as e:  # pragma: no cover - depends on installed extras
        logger.debug("fastembed unavailable: %s", e)
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("Using sentence-transformers for article embeddings")
        return _SentenceTransformer(
            SentenceTransformer("intfloat/multilingual-e5-small")
        )
    except Exception as e:  # pragma: no cover - depends on installed extras
        logger.debug("sentence-transformers unavailable: %s", e)
    logger.info("Using deterministic hashing embedder (no ML extras installed)")
    return _HashingEmbedder()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
