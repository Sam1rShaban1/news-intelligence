"""Article fetcher — discovers new articles from RSS feeds and web pages."""

import logging
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)

# Reusable client with connection pooling
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=settings.http_timeout,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _client


def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        _client.close()
        _client = None


def fetch_rss_entries(rss_url: str, source_url: str) -> list[dict[str, Any]]:
    """Parse an RSS feed and return raw article dicts."""
    client = _get_client()
    try:
        resp = client.get(rss_url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch RSS %s: %s", rss_url, e)
        return []

    feed = feedparser.parse(resp.text)
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
    client = _get_client()
    sitemap_url = source_url.rstrip("/") + sitemap_path
    try:
        resp = client.get(sitemap_url)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []

    soup = BeautifulSoup(resp.text, "lxml-xml")
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
    """
    entries: list[dict[str, Any]] = []

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
    client = _get_client()
    try:
        resp = client.get(source_url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("Homepage scrape failed for %s: %s", source_url, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
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
