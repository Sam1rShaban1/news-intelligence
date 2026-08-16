"""Export a multilingual sentiment model to ONNX for CPU inference.

This is a BUILD-time helper, NOT a runtime dependency. Run it where PyTorch,
transformers and optimum are installed (e.g. a separate venv on the laptop),
then bake the resulting ./models directory into the image so the worker can
load /app/models/sentiment.onnx + sentiment_tokenizer.json at runtime.

    python -m venv .venv && . .venv/bin/activate
    pip install "torch" "transformers" "optimum[exporters]"
    python scripts/export_sentiment_onnx.py

The exported model follows cardiffnlp/twitter-xlm-roberta-base-sentiment-latest
label order: [negative, neutral, positive] (mapped to neg/neutral/pos at runtime).
"""

from pathlib import Path

from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer

MODEL_ID = "cardiffnlp/twitter-xlm-roberta-base-sentiment-latest"
OUT = Path("models")


def main() -> None:
    OUT.mkdir(exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    tokenizer.save_pretrained(OUT)  # writes sentiment_tokenizer.json

    model = ORTModelForSequenceClassification.from_pretrained(MODEL_ID, export=True)
    model.save_pretrained(OUT)  # writes model.onnx (+ config)

    # Normalize the ONNX filename the runtime expects.
    onnx_file = OUT / "model.onnx"
    if onnx_file.exists():
        onnx_file.rename(OUT / "sentiment.onnx")

    print(f"Exported ONNX sentiment model + tokenizer into {OUT.resolve()}")


if __name__ == "__main__":
    main()
