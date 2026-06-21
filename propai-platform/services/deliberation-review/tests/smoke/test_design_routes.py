"""INC-DL3 — 설계 라이프사이클 라우트: 인증·경로검증(라우터 등록·도달성). 데이터 로직은 design/store 테스트가 커버."""
import uuid

from app.api import deps


def test_design_process_requires_token(client, monkeypatch):
    # API_TOKEN 설정 시 무토큰 거부(401). 404가 아닌 401 = 라우터 등록·도달 확인.
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.post("/api/v1/design/process", json={"pnu": "1111010100100000031"})
    assert resp.status_code == 401


def test_get_design_run_requires_token(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.get(f"/api/v1/design/process/{uuid.uuid4()}")
    assert resp.status_code == 401


def test_project_design_rejects_malformed_id(client):
    # 경로 UUID 형식오류 → FastAPI 자동 422(핸들러 진입 전).
    resp = client.get("/api/v1/projects/not-a-uuid/design")
    assert resp.status_code == 422
