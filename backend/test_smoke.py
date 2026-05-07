"""Smoke tests verifying the app starts and both cricket + football routes exist.

These do NOT call external APIs — they only prove that:
- The FastAPI app assembles without import errors
- Routers are mounted at the expected prefixes
- Football health endpoint responds independently of API key config
- Cricket match-list handler returns correct shape (mocked upstream)
"""

from unittest.mock import patch

from starlette.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_root_health() -> None:
    """GET / returns the top-level health check."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_docs_available() -> None:
    """Swagger UI is reachable."""
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_football_health() -> None:
    """GET /api/football/health works with no auth, no upstream call."""
    resp = client.get("/api/football/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["provider"] == "api-football"


def test_cricket_routes_exist() -> None:
    """GET /api/matches without required 'date' param → 422 (not 404)."""
    resp = client.get("/api/matches")
    assert resp.status_code == 422  # validation error, route exists


@patch("backend.main.fetch_live_data_for_series")
def test_cricket_match_list_returns_correct_shape(mock_fetch) -> None:
    """GET /api/matches with mocked upstream returns expected cricket fields."""
    mock_fetch.return_value = [
        {
            "matchId": 101,
            "team1": {"teamName": "India"},
            "team2": {"teamName": "Australia"},
            "venueInfo": {"ground": "Wankhede Stadium"},
            "status": "Preview",
            "startDate": "1715299200000",
        },
    ]

    resp = client.get("/api/matches?date=2025-05-10")
    assert resp.status_code == 200

    body = resp.json()
    assert "matches" in body
    assert len(body["matches"]) == 1

    match = body["matches"][0]
    assert match["match_number"] == 0
    assert match["match_id"] == 101
    assert match["teams"] == ["India", "Australia"]
    assert match["venue"] == "Wankhede Stadium"
    assert "start_time" in match
