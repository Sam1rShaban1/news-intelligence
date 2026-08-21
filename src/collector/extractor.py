"""Article content extractor — newspaper4k primary, BeautifulSoup fallback."""

import logging
import warnings
from typing import Any

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from config.settings import settings
from src.collector.ssrf import safe_fetch

# The BS4 fallback parses article *HTML*. Some responses (XHTML / Atom-ish bodies)
# make BeautifulSoup emit XMLParsedAsHTMLWarning; we keep the HTML parser (switching
# to the XML parser would break ordinary HTML extraction), so silence just this warning.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=settings.http_timeout,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=False,
        )
    return _client


def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        _client.close()
        _client = None


def extract_with_newspaper(url: str) -> dict[str, Any] | None:
    """Try newspaper4k extraction. Returns None on failure."""
    try:
        import newspaper

        result = safe_fetch(url)
        article = newspaper.Article(url, language="en")
        article.set_html(result.body.decode("utf-8", "replace"))
        article.parse()

        text = article.text or ""
        if len(text.strip()) < 50:
            return None

        return {
            "title": article.title or "",
            "content": text,
            "author": ", ".join(article.authors) if article.authors else None,
            "published_date": article.publish_date,
            "summary": article.meta_description or "",
            "word_count": len(text.split()),
        }
    except Exception as e:
        logger.debug("newspaper4k failed for %s: %s", url, e)
        return None


def extract_with_bs4(url: str) -> dict[str, Any] | None:
    """BeautifulSoup fallback extraction."""
    try:
        result = safe_fetch(url)
        if result.status >= 400:
            logger.debug("BS4 fetch failed for %s: HTTP %s", url, result.status)
            return None
    except ValueError as e:
        logger.debug("BS4 fetch blocked for %s: %s", url, e)
        return None

    soup = BeautifulSoup(result.body.decode("utf-8", "replace"), "html.parser")

    # Title
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    # Main content: try <article>, then <main>, then largest <div>
    content_el = soup.find("article") or soup.find("main")
    if not content_el:
        paragraphs = soup.find_all("p")
        if not paragraphs:
            return None
        parent_counts: dict[Any, int] = {}
        for p in paragraphs:
            parent = p.parent
            parent_counts[parent] = parent_counts.get(parent, 0) + len(p.get_text())
        content_el = max(parent_counts, key=lambda k: parent_counts[k]) if parent_counts else None
        if content_el is None:
            return None

    paragraphs = content_el.find_all(["p", "h2", "h3", "li"])
    text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    if len(text.strip()) < 50:
        return None

    author = None
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author:
        author = meta_author.get("content")
    if not author:
        byline = soup.find(class_=lambda c: c and "author" in c.lower() if c else False)
        if byline:
            author = byline.get_text(strip=True)[:200]

    summary = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        summary = meta_desc.get("content", "")[:1000]

    return {
        "title": title[:500],
        "content": text,
        "author": author,
        "published_date": None,
        "summary": summary,
        "word_count": len(text.split()),
    }


def extract_article(url: str) -> dict[str, Any]:
    """
    Extract article content. Tries newspaper4k first, falls back to BS4.
    Returns dict with: title, content, author, published_date, summary, word_count.
    Raises RuntimeError if extraction fails.
    """
    result = extract_with_newspaper(url)
    if result:
        return result

    result = extract_with_bs4(url)
    if result:
        return result

    raise RuntimeError(f"Extraction failed for {url}")
