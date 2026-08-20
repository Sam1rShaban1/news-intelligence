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


def _load_model():
    """Lazy-load GLiNER2 ONNX model (heavy, only load once)."""
    global _model
    if _model is not None:
        return _model

    try:
        from gliner2_onnx import GLiNER2ONNXRuntime

        logger.info("Loading GLiNER2 ONNX multilingual model: %s", settings.gliner_model)
        _model = GLiNER2ONNXRuntime.from_pretrained(settings.gliner_model)
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
