"""인허가 서류 패키지 라우트(/permits/package/*) 통합 테스트.

경량 TestClient(전체 앱·실 DB·공공API 비의존) — test_decision_brief_pdf_route 패턴 복제.
permit_package_service 가 라우터·프론트 소비처 0인 dead code 였던 것을 배선한 계약을 잠근다.

- GET /package/checklist: 200 + 체크리스트·예상기간 병합 JSON(정적 기준표 결정론)
- POST /package/pdf: 200 + application/pdf + attachment + %PDF 실바이트(무목업)
- 미지원 유형: 400 (파일 다운로드 계약 — 200+error JSON 금지)
- track_permit_status 는 실 상태원천(세움터/DB) 없이 입력 단계를 되돌려주는 계산기라
  배선하지 않음 — 라우트 부재(404)를 회귀 잠금(가짜 '상태추적' API 노출 금지).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.auth.jwt_handler import get_current_user
from apps.api.routers import permits as permits_router


class _User:
    """get_current_user override 스텁(실 JWT·DB 불요). admin 은 permits read 권한 보유."""

    id = "test-user"
    tenant_id = "test-tenant"
    role = "admin"
    is_active = True


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(permits_router.router, prefix="/api/v1/permits")
    app.dependency_overrides[get_current_user] = lambda: _User()
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


# ── 1) GET /package/checklist — 200 + 병합 JSON(체크리스트+기간) ──


def test_checklist_200_merged_json(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/permits/package/checklist",
        params={"permit_type": "건축허가", "region": "서울"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # 체크리스트(정적 기준표): 건축허가 총 12건 · 필수 7건
    assert data["permit_type"] == "건축허가"
    assert data["checklist"]["total_items"] == 12
    assert data["checklist"]["required_items"] == 7
    # 예상기간: 서울 건축허가 영업일 25일 → 달력일 35일
    assert data["duration"]["business_days"] == 25
    assert data["duration"]["calendar_days"] == 35
    # 무목업 정직 고지(참고치 명시)가 응답에 포함돼야 한다
    assert "참고치" in data["duration_basis"]


def test_checklist_conditional_items_applied(client: TestClient) -> None:
    """대지면적 200㎡ 이상이면 조경계획서(BA-08)가 적용으로 바뀌어야 한다."""
    resp = client.get(
        "/api/v1/permits/package/checklist",
        params={"permit_type": "건축허가", "building_area_sqm": 300},
    )
    assert resp.status_code == 200
    items = resp.json()["checklist"]["items"]
    landscaping = next(i for i in items if i["id"] == "BA-08")
    assert landscaping["applicable"] is True


def test_checklist_invalid_type_400(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/permits/package/checklist", params={"permit_type": "존재하지않는유형"}
    )
    assert resp.status_code == 400
    assert "지원하지 않는 인허가 유형" in resp.json()["detail"]


# ── 2) POST /package/pdf — 파일 다운로드 계약(application/pdf + attachment + %PDF) ──


def test_pdf_200_content_type_and_body(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/permits/package/pdf",
        json={"permit_type": "건축허가", "region": "서울", "project_id": "PROJ-001"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd
    assert "permit_package_PROJ-001.pdf" in cd
    assert resp.content.startswith(b"%PDF")


def test_pdf_invalid_type_400_not_200_error_json(client: TestClient) -> None:
    """실패는 4xx — 200 에 error JSON 을 담아 blob 다운로드를 오염시키면 안 된다."""
    resp = client.post(
        "/api/v1/permits/package/pdf", json={"permit_type": "존재하지않는유형"}
    )
    assert resp.status_code == 400
    assert "application/pdf" not in resp.headers.get("content-type", "")


def test_pdf_filename_sanitized(client: TestClient) -> None:
    """경로조작·헤더 깨짐 문자가 섞인 project_id 는 안전문자로 치환돼야 한다."""
    resp = client.post(
        "/api/v1/permits/package/pdf",
        json={"permit_type": "사용승인", "project_id": '../evil"name'},
    )
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert ".." not in cd.split("filename=")[-1]
    assert resp.content.startswith(b"%PDF")


# ── 3) track_permit_status 미배선 회귀 잠금(무목업 — 가짜 상태추적 API 금지) ──


def test_track_status_route_not_wired(client: TestClient) -> None:
    """/package/status 류 라우트는 존재하면 안 된다(실 상태원천 없는 계산기 노출 금지).

    진짜 상태조회는 GET /permits/submissions/{id}/status(SeumterPermitService·DB)가 담당.
    """
    assert client.get("/api/v1/permits/package/status").status_code == 404
    assert client.post("/api/v1/permits/package/status", json={}).status_code == 404
    assert client.get(
        "/api/v1/permits/package/track", params={"current_stage": "검토중"}
    ).status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
