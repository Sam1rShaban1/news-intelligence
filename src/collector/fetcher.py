"""Article fetcher — discovers new articles from RSS feeds and web pages."""

import logging
from datetime import datetime, timezone
from typing import Any

import feedparser
from bs4 import BeautifulSoup

from config.settings import settings
from src.collector.ssrf import is_safe_url, safe_fetch

logger = logging.getLogger(__name__)


def _fetch_text(url: str) -> str | None:
    """Fetch `url` and return its body decoded as text.

    Uses the SSRF-guarded ``safe_fetch``: the connection is pinned to a
    pre-resolved, blocklist-checked IP and *every* redirect hop is re-validated,
    which defeats DNS-rebinding and redirect-based SSRF (e.g. to cloud metadata
    endpoints at 169.254.169.254). Returns ``None`` on any network error, a
    blocked/unsafe host, or a non-2xx status.
    """
    try:
        result = safe_fetch(
            url,
            timeout=settings.http_timeout,
            user_agent=settings.user_agent,
        )
    except (ValueError, OSError) as e:
        logger.warning("Blocked/unsafe fetch %s: %s", url, e)
        return None
    if result.status >= 400:
        logger.warning("Fetch %s returned status %s", url, result.status)
        return None
    charset = "utf-8"
    for key, value in result.headers:
        if key.lower() == "content-type" and "charset=" in value:
            charset = value.split("charset=")[-1].split(";")[0].strip()
    try:
        return result.body.decode(charset, "replace")
    except (LookupError, UnicodeDecodeError):
        return result.body.decode("utf-8", "replace")


def fetch_rss_entries(rss_url: str, source_url: str) -> list[dict[str, Any]]:
    """Parse an RSS feed and return raw article dicts."""
    text = _fetch_text(rss_url)
    if not text:
        return []

    feed = feedparser.parse(text)
    entries = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if not link:
            continue
        # Make absolute
        if link.startswith("/"):
            link = source_url.rstrip("/") + link

        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

        entries.append(
            {
                "url": link,
                "title": entry.get("title", ""),
                "published_date": published,
                "author": entry.get("author"),
                "summary": entry.get("summary", "")[:1000] if entry.get("summary") else None,
            }
        )
    return entries


def fetch_sitemap_urls(source_url: str, sitemap_path: str = "/sitemap.xml") -> list[str]:
    """Try to discover article URLs from a sitemap.xml."""
    sitemap_url = source_url.rstrip("/") + sitemap_path
    text = _fetch_text(sitemap_url)
    if not text:
        return []

    soup = BeautifulSoup(text, "lxml-xml")
    urls = []
    for loc in soup.find_all("loc"):
        url = loc.get_text(strip=True)
        if url and any(seg in url.lower() for seg in ("/article", "/news", "/story", "/post")):
            urls.append(url)
    return urls[:50]  # cap at 50


def discover_articles(source: Any) -> list[dict[str, Any]]:
    """
    Discover articles for a source.
    Priority: RSS → Sitemap → Homepage fallback.
    Returns list of dicts with keys: url, title, published_date, author, summary.

    The initial ``is_safe_url`` check rejects misconfigured/bad operator-supplied
    URLs up front; every subsequent network fetch goes through the SSRF-guarded
    ``safe_fetch`` (see ``_fetch_text``), which also defeats redirect-based SSRF.
    """
    entries: list[dict[str, Any]] = []

    if not is_safe_url(source.url) or (source.rss_url and not is_safe_url(source.rss_url)):
        logger.warning("Refusing to fetch unsafe source URL for %s", source.name)
        return []

    # 1. RSS feed
    if source.rss_url:
        entries = fetch_rss_entries(source.rss_url, source.url)
        if entries:
            logger.info("RSS found %d entries for %s", len(entries), source.name)
            return entries

    # 2. Sitemap fallback
    sitemap_urls = fetch_sitemap_urls(source.url)
    if sitemap_urls:
        logger.info("Sitemap found %d URLs for %s", len(sitemap_urls), source.name)
        return [{"url": u, "title": "", "published_date": None, "author": None, "summary": None}
                for u in sitemap_urls]

    # 3. Homepage scrape fallback
    return _scrape_homepage(source.url)


def _scrape_homepage(source_url: str) -> list[dict[str, Any]]:
    """Last-resort: scrape homepage for article-like links."""
    text = _fetch_text(source_url)
    if not text:
        return []

    soup = BeautifulSoup(text, "html.parser")
    seen = set()
    articles = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("/"):
            href = source_url.rstrip("/") + href

        # Heuristic: skip short paths, anchors, assets
        path = href.split(source_url)[-1] if source_url in href else href
        if len(path) < 10:
            continue
        if any(
            skip in href.lower()
            for skip in ("/tag/", "/author/", "/page/", ".jpg", ".png", "#")
        ):
            continue

        if href not in seen:
            seen.add(href)
            articles.append(
                {"url": href, "title": a_tag.get_text(strip=True)[:200], "published_date": None,
                 "author": None, "summary": None}
            )

    return articles[:30]
