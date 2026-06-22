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


def test_require_token_accepts_valid(monkeypatch):
    # positive — 올바른 Bearer는 통과(예외 없음). 인증이 전부 거부로 깨지면 실패.
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    deps.require_token("Bearer secret-token")  # raise 없으면 통과


def test_require_token_open_when_unset(monkeypatch):
    # 개방 모드 — API_TOKEN 미설정 시 무토큰도 통과(독스트링 계약).
    monkeypatch.setattr(deps.settings, "API_TOKEN", "")
    deps.require_token(None)  # raise 없으면 통과


def test_require_token_rejects_wrong_scheme(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    with pytest.raises(HTTPException):
        deps.require_token("Basic secret-token")  # scheme 불일치 거부


def test_get_tenant_id_parses_hex_and_hyphen():
    # #8a — BFF가 보낸 X-Tenant-Id(hex 또는 하이픈 UUID) 파싱. 미설정=None(후방호환).
    import uuid
    u = uuid.uuid4()
    assert deps.get_tenant_id(u.hex) == u            # 하이픈 없는 hex(_tenant 출력) 수용
    assert deps.get_tenant_id(str(u)) == u           # 하이픈 UUID 수용
    assert deps.get_tenant_id(None) is None          # 미설정 → 격리 미적용(레거시)


def test_get_tenant_id_rejects_malformed():
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        deps.get_tenant_id("not-a-uuid")  # 형식 오류 400


def test_get_project_id_parses_hex_and_hyphen():
    # 프로젝트 귀속 — BFF가 보낸 X-Project-Id(hex 또는 하이픈 UUID) 파싱. 미설정=None(프로젝트 미귀속).
    import uuid
    u = uuid.uuid4()
    assert deps.get_project_id(u.hex) == u            # 하이픈 없는 hex 수용
    assert deps.get_project_id(str(u)) == u           # 하이픈 UUID 수용
    assert deps.get_project_id(None) is None          # 미설정 → 프로젝트 미귀속(직접/레거시)


def test_get_project_id_rejects_malformed():
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        deps.get_project_id("not-a-uuid")  # 형식 오류 400
