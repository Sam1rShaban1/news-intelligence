"""Analysis orchestrator — sentiment stage (runs in the main worker).

NER + knowledge-graph building runs in the separate `ner` service. This module
only computes VADER sentiment and stores it, then marks the article
`sentiment_done` so the ner service can pick it up.
"""

import logging

from src.db.models.article import Article
from src.db.session import SessionLocal
from src.nlp.language import detect_language
from src.nlp.sentiment import analyze_sentiment

logger = logging.getLogger(__name__)


def analyze_article(article: Article) -> dict:
    """Run the sentiment stage on an extracted article.

    Language is re-detected here (not just trusted from extraction) so mislabels
    self-heal whenever the article is (re-)analyzed.
    """
    text = article.content or article.summary or article.title or ""
    lang = detect_language(article.title or article.content) or "en"
    return {"language": lang, "sentiment": analyze_sentiment(text, lang)}


def store_results(article_id: int, results: dict) -> None:
    """Persist sentiment + language results and move the article to `sentiment_done`."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            if results.get("language"):
                article.language = results["language"]
            article.sentiment_score = results["sentiment"]["score"]
            article.sentiment_label = results["sentiment"]["label"]
        session.commit()
