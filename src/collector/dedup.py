"""Deduplication helpers — URL and content hashing."""

import hashlib


def compute_url_hash(url: str) -> str:
    """Deterministic hash of a normalized URL."""
    normalized = url.strip().rstrip("/").lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def compute_content_hash(content: str) -> str:
    """Hash of article body text for cross-site duplicate detection."""
    cleaned = content.strip()
    return hashlib.sha256(cleaned.encode()).hexdigest()
