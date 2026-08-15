"""Named Entity Recognition using GLiNER2 ONNX (multilingual, no PyTorch)."""

import logging

from config.settings import settings

logger = logging.getLogger(__name__)

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
