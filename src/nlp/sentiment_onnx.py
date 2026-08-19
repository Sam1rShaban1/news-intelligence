"""Multilingual transformer sentiment via ONNX (Phase 8).

Loads a small ONNX sentiment classifier + tokenizer from a local path
(default /app/models/sentiment.onnx + sentiment_tokenizer.json). Returns None
when the model is unavailable so callers transparently fall back to the
lexicon (mk/sq/tr) / VADER (en) paths. Keeps the heavy ML off the fetch/extract
worker and CPU-friendly via onnxruntime.
"""

import logging
import math
import os

from config.settings import settings

logger = logging.getLogger(__name__)

# cardiffnlp/twitter-xlm-roberta-base-sentiment-latest label order.
_RAW_LABELS = ["negative", "neutral", "positive"]
_LABEL_MAP = {"negative": "neg", "neutral": "neutral", "positive": "pos"}

_session = None
_tokenizer = None
_loaded = False


def _load() -> tuple:
    global _session, _tokenizer, _loaded
    if _loaded:
        return _session, _tokenizer

    model_path = settings.sentiment_model_path
    tok_path = os.path.join(os.path.dirname(model_path), "sentiment_tokenizer.json")
    _loaded = True

    if not (os.path.exists(model_path) and os.path.exists(tok_path)):
        logger.info(
            "Sentiment ONNX model not found at %s — transformer disabled (using fallback).",
            model_path,
        )
        _session, _tokenizer = None, None
        return _session, _tokenizer

    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        # Cap intra-op threads so ORT doesn't oversubscribe the Pi's few cores
        # (avoids contention with the fetch/extract workers running alongside).
        so = ort.SessionOptions()
        so.intra_op_num_threads = min(os.cpu_count() or 1, 4)
        so.inter_op_num_threads = 1
        _session = ort.InferenceSession(
            model_path, sess_options=so, providers=["CPUExecutionProvider"]
        )
        _tokenizer = Tokenizer.from_file(tok_path)
    except Exception as e:  # pragma: no cover - environment dependent
        logger.warning("Failed to load sentiment ONNX model: %s", e)
        _session, _tokenizer = None, None
    return _session, _tokenizer


def transformer_sentiment(text: str) -> dict | None:
    """Return {score, label, method, confidence} or None if unavailable."""
    session, tokenizer = _load()
    if session is None or tokenizer is None or not text or not text.strip():
        return None

    try:
        enc = tokenizer.encode(
            text, max_length=512, truncation=True, add_special_tokens=True
        )
        feeds = {}
        for inp in session.get_inputs():
            name = inp.name.lower()
            if "input" in name or "ids" in name:
                feeds[inp.name] = [list(enc.ids)]
            elif "attention" in name:
                feeds[inp.name] = [list(enc.attention_mask)]
            elif "token_type" in name:
                feeds[inp.name] = [[0] * len(enc.ids)]
            else:
                feeds[inp.name] = [list(enc.ids)]

        logits = session.run(None, feeds)[0][0]
        exps = [math.exp(x - max(logits)) for x in logits]
        probs = [e / sum(exps) for e in exps]
        idx = int(max(range(len(probs)), key=lambda i: probs[i]))
        raw = _RAW_LABELS[idx] if idx < len(_RAW_LABELS) else "neutral"
        label = _LABEL_MAP.get(raw, "neutral")
        conf = float(probs[idx])
        signed = conf if label == "pos" else (-conf if label == "neg" else 0.0)
        return {
            "score": round(signed, 4),
            "label": label,
            "method": "transformer",
            "confidence": round(conf, 4),
        }
    except Exception as e:  # pragma: no cover - model/format dependent
        logger.warning("Transformer sentiment inference failed: %s", e)
        return None
