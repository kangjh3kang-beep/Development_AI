"""프로젝트 스코프 per-field 읽기 엔드포인트 — 인증·경로검증(라우터 등록·도달성 입증).

데이터 집계·테넌트 격리·run_count·절단 로직은 store 테스트(test_analysis_store.py::
test_get_project_field_data_aggregates_and_isolates)가 실DB로 엄밀 커버. 여기선 HTTP 표면(인증/검증)만 —
이 repo는 라우트 표면=client 픽스처, 데이터 로직=db 픽스처로 분리(혼용 시 교차 이벤트루프 풀 충돌).
"""
import uuid

from app.api import deps


def test_project_fields_requires_token(client, monkeypatch):
    # API_TOKEN 설정 시 무토큰 거부(401). 404가 아닌 401 = 라우터 등록·도달 확인.
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.get(f"/api/v1/projects/{uuid.uuid4()}/fields")
    assert resp.status_code == 401


def test_project_fields_rejects_malformed_id(client):
    # 경로 UUID 형식오류 → FastAPI 자동 422(핸들러 진입 전). 라우트 존재·검증 동작 확인.
    resp = client.get("/api/v1/projects/not-a-uuid/fields")
    assert resp.status_code == 422
