"""D5 — doctor·reports/build 인증: API_TOKEN 설정 시 베어러 요구(401), 미설정 시 개방(200).

★배경(보안): /api/v1/doctor(키 보유 핑거프린트 노출)·/api/v1/reports/build(임의 연산 DoS 표면)가
무인증이었다. analyze와 동일한 require_token을 적용해, 토큰 설정 시 무토큰 접근을 401로 차단한다.
"""
from app.api import deps

_BUILD_BODY = {"items": [], "snapshot_id": "snap-1", "model_version": "v1"}


def test_doctor_rejects_without_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.get("/api/v1/doctor")
    assert resp.status_code == 401


def test_doctor_accepts_valid_token(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.get("/api/v1/doctor", headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_doctor_open_when_token_unset(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "")
    resp = client.get("/api/v1/doctor")
    assert resp.status_code == 200  # 미설정 = 개방(dev 후방호환)


def test_reports_build_rejects_without_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.post("/api/v1/reports/build", json=_BUILD_BODY)
    assert resp.status_code == 401  # 인증이 본문 처리보다 먼저(무인증 연산 차단)


def test_reports_build_open_when_token_unset(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "")
    resp = client.post("/api/v1/reports/build", json=_BUILD_BODY)
    assert resp.status_code == 200  # 미설정 = 개방(빈 items는 정상 빌드)
