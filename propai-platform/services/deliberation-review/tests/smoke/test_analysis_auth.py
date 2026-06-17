"""P2 — /analyze 인증: API_TOKEN 설정 시 베어러 요구(401), 미설정 시 개방."""
from app.api import deps

_PAYLOAD = {"pnu": "1111010100100000002", "application_date": "2026-01-01", "drawing": {"scale_text": "1:100"}}


def test_analyze_rejects_without_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.post("/api/v1/analyze", json=_PAYLOAD)
    assert resp.status_code == 401


def test_analyze_rejects_wrong_token(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.post("/api/v1/analyze", json=_PAYLOAD, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_get_run_rejects_without_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.get("/api/v1/analyze/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401
