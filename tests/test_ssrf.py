"""SSRF guard unit tests (no database required)."""

import pytest

from src.collector.ssrf import is_safe_url, safe_fetch


def test_non_http_schemes_rejected():
    assert is_safe_url("ftp://example.com/x") is False
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("gopher://127.0.0.1:6379") is False


def test_credentials_rejected():
    assert is_safe_url("http://user:pass@example.com/") is False


def test_loopback_and_private_blocked():
    assert is_safe_url("http://localhost/") is False
    assert is_safe_url("http://127.0.0.1/") is False
    assert is_safe_url("http://10.0.0.5/") is False
    assert is_safe_url("http://192.168.1.1/") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False


def test_safe_fetch_blocks_internal_hosts():
    with pytest.raises(ValueError):
        safe_fetch("http://127.0.0.1:1/")
    with pytest.raises(ValueError):
        safe_fetch("http://10.0.0.1/")


def test_safe_fetch_rejects_non_http():
    with pytest.raises(ValueError):
        safe_fetch("ftp://example.com/")
