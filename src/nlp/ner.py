"""Named Entity Recognition using GLiNER2 ONNX (multilingual, no PyTorch)."""

import logging

import transformers
from config.settings import settings

logger = logging.getLogger(__name__)

# gliner2_onnx loads its tokenizer via transformers.AutoTokenizer.from_pretrained
# without fix_mistral_regex, which emits a warning for the underlying Mistral
# tokenizer and can mis-tokenize. Patch it once (idempotent) so the flag is set.
_orig_tokenizer_from_pretrained = getattr(transformers.AutoTokenizer, "_news_intel_orig", None)
if _orig_tokenizer_from_pretrained is None:
    _orig_tokenizer_from_pretrained = transformers.AutoTokenizer.from_pretrained
    transformers.AutoTokenizer._news_intel_orig = _orig_tokenizer_from_pretrained

    def _tokenizer_from_pretrained(pretrained_model_name_or_path, *args, **kwargs):
        kwargs.setdefault("fix_mistral_regex", True)
        return _orig_tokenizer_from_pretrained(pretrained_model_name_or_path, *args, **kwargs)

    transformers.AutoTokenizer.from_pretrained = _tokenizer_from_pretrained

# GLiNER label mapping — map model labels to our standard labels
LABEL_MAP = {
    "person": "PER",
    "persons": "PER",
    "PER": "PER",
    "organization": "ORG",
    "organizations": "ORG",
    "ORG": "ORG",
    "location": "LOC",
    "locations": "LOC",
    "LOC": "LOC",
    "city": "LOC",
    "country": "LOC",
    "misc": "MISC",
    "MISC": "MISC",
    "date": "DATE",
    "event": "EVENT",
}

# Labels to ask GLiNER to detect
DEFAULT_LABELS = ["person", "organization", "location", "city", "country", "event"]

_model = None


def _resolve_model_dir() -> str:
    """Return a local path to the pinned GLiNER2 model snapshot.

    Uses ``huggingface_hub.snapshot_download`` with the pinned ``revision`` so the
    exact model commit is fetched (reproducible, supply-chain safe). Falls back to
    the bare repo id if ``huggingface_hub`` isn't installed (e.g. the Pi target,
    where NER is disabled anyway).
    """
    repo = settings.gliner_model
    revision = settings.gliner_model_revision or None
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        logger.warning("huggingface_hub unavailable; loading %s without a pinned revision", repo)
        return repo
    return snapshot_download(repo_id=repo, revision=revision)


def _verify_model_sha(model_dir: str) -> None:
    """Verify the model against ``gliner_model_sha256`` if it is set.

    Compares the expected sha256 against every ``.onnx`` file in the snapshot and
    passes if any match. Raises ``ValueError`` on mismatch (fail closed).
    """
    import hashlib
    from pathlib import Path

    expected = settings.gliner_model_sha256.strip()
    if not expected:
        return
    onnx_files = list(Path(model_dir).rglob("*.onnx"))
    if not onnx_files:
        logger.warning("No .onnx files in %s; skipping sha verification", model_dir)
        return
    for path in onnx_files:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() == expected:
            logger.info("GLiNER2 model sha256 verified (%s)", path.name)
            return
    raise ValueError(
        f"GLiNER2 model sha256 mismatch: expected {expected} but none of "
        f"{[p.name for p in onnx_files]} matched"
    )


def _load_model():
    """Lazy-load GLiNER2 ONNX model (heavy, only load once)."""
    global _model
    if _model is not None:
        return _model

    try:
        from gliner2_onnx import GLiNER2ONNXRuntime

        model_dir = _resolve_model_dir()
        _verify_model_sha(model_dir)
        logger.info("Loading GLiNER2 ONNX multilingual model from %s", model_dir)
        _model = GLiNER2ONNXRuntime.from_pretrained(model_dir)
        logger.info("GLiNER2 ONNX model loaded")
    except Exception as e:
        logger.error("Failed to load GLiNER2 ONNX: %s", e)
        _model = None

    return _model


def extract_entities(
    text: str, labels: list[str] | None = None, threshold: float = 0.3
) -> list[dict]:
    """
    Extract named entities from text.
    Returns list of dicts: {text, label, start, end, confidence}
    """
    if not text or not text.strip():
        return []

    model = _load_model()
    if model is None:
        return []

    labels = labels or DEFAULT_LABELS

    try:
        # GLiNER expects plain text, limit length for performance
        input_text = text[:5000]
        predictions = model.extract_entities(input_text, labels, threshold=threshold)

        results = []
        for ent in predictions:
            label = LABEL_MAP.get(ent.label.lower(), ent.label.upper())
            results.append({
                "text": ent.text,
                "label": label,
                "start": ent.start,
                "end": ent.end,
                "confidence": round(ent.score, 4),
            })

        return results

    except Exception as e:
        logger.warning("GLiNER2 extraction failed: %s", e)
        return []


def is_available() -> bool:
    """Check if GLiNER2 model is loaded."""
    return _load_model() is not None
