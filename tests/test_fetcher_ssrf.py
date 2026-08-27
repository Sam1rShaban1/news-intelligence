"""Feed-discovery SSRF routing (no real network).

Confirms that article discovery goes through the SSRF-guarded ``safe_fetch``
(not a raw httpx client with follow_redirects), so a feed URL that resolves to a
public host but redirects to an internal/cloud-metadata address cannot be
pivoted. Also confirms ``is_safe_url`` now fails closed on unresolvable hosts.
"""

import types
from unittest import mock

import pytest

from src.collector import fetcher
from src.collector.fetcher import discover_articles
from src.collector.ssrf import is_safe_url


def test_is_safe_url_fails_closed_on_unresolvable():
    # is_safe_url lives in ssrf.py and uses ssrf.socket.getaddrinfo.
    with mock.patch(
        "src.collector.ssrf.socket.getaddrinfo", side_effect=OSError("no DNS")
    ):
        assert is_safe_url("http://definitely-not-real.example/") is False


def test_discover_articles_refuses_unsafe_source():
    # 169.254.169.254 is the cloud metadata IP: is_safe_url blocks it for real.
    src = types.SimpleNamespace(name="x", url="http://169.254.169.254/", rss_url=None)
    assert discover_articles(src) == []


def test_discover_articles_routes_through_safe_fetch():
    src = types.SimpleNamespace(
        name="bbc", url="http://example.com", rss_url="http://example.com/rss"
    )
    rss_xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        '<item><link>http://example.com/a1</link><title>A1</title></channel></rss>'
    )
    with mock.patch.object(fetcher, "is_safe_url", return_value=True), mock.patch.object(
        fetcher, "safe_fetch"
    ) as sf:
        sf.return_value = types.SimpleNamespace(
            status=200,
            headers=[("content-type", "application/rss+xml")],
            body=rss_xml.encode(),
            final_url="http://example.com/rss",
        )
        entries = discover_articles(src)
    assert len(entries) == 1
    assert entries[0]["url"] == "http://example.com/a1"
    sf.assert_called_once()


def test_discover_articles_safe_fetch_blocked_returns_empty():
    src = types.SimpleNamespace(
        name="x", url="http://example.com", rss_url="http://example.com/rss"
    )
    with mock.patch.object(fetcher, "is_safe_url", return_value=True), mock.patch.object(
        fetcher, "safe_fetch", side_effect=ValueError("blocked")
    ):
        assert discover_articles(src) == []
