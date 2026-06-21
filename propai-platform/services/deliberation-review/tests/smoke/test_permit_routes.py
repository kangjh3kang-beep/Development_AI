"""INC-PD4 — 프로세스 라우트: 인증·경로검증(라우터 등록·도달성). 데이터 로직은 store/executor 테스트가 커버."""
import uuid

from app.api import deps


def test_permit_process_requires_token(client, monkeypatch):
    # API_TOKEN 설정 시 무토큰 거부(401). 404가 아닌 401 = 라우터 등록·도달 확인.
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.post("/api/v1/permit/process", json={"pnu": "1111010100100000022"})
    assert resp.status_code == 401


def test_get_permit_run_requires_token(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.get(f"/api/v1/permit/process/{uuid.uuid4()}")
    assert resp.status_code == 401


def test_project_permit_rejects_malformed_id(client):
    # 경로 UUID 형식오류 → FastAPI 자동 422(핸들러 진입 전). 라우트 존재·검증 동작 확인.
    resp = client.get("/api/v1/projects/not-a-uuid/permit")
    assert resp.status_code == 422
