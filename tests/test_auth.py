"""API-key auth gate is opt-in via NEWS_API_KEY."""

from fastapi.testclient import TestClient

from config.settings import settings
from src.api.main import app


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_auth_enforced_when_key_set(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "topsecret")
    with TestClient(app) as c:
        assert c.get("/sources").status_code == 401
        assert c.get("/sources", headers={"X-API-Key": "wrong"}).status_code == 401
        assert c.get("/sources", headers={"X-API-Key": "topsecret"}).status_code == 200


def test_no_auth_when_key_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    assert client.get("/sources").status_code == 200
