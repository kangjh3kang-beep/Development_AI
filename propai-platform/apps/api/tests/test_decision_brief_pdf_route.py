"""Stage1 통합 의사결정 PDF 라우트(POST /{project_id}/decision-brief/pdf) 통합 테스트.

경량 TestClient(전체 앱·실 DB·공공API 비의존) — test_cost_router 패턴을 복제해, 인증·DB·
DecisionBriefService.build·과금 게이트를 의존성 override/monkeypatch 로 대체하고 라우트
계약(테넌트 격리 404 · use_llm 한도초과 402 · 성공 시 Content-Disposition attachment+
application/pdf+%PDF 바디)만 결정론적으로 검증한다(라이브 DB/배포는 deploy-pending).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# enforce_llm_quota 가 쓰는 get_db 는 라우터의 get_db 와 모듈 경로가 다르다(app.core.database vs
# apps.api.database.session). 두 심볼 모두 override 해야 FastAPI 의존성 주입이 실 DB 없이 가짜
# 세션으로 해소된다(경로는 conftest.py 가 sys.path 에 이미 등록).
from app.core.database import get_db as core_get_db
from apps.api.auth.jwt_handler import get_current_user
from apps.api.database.session import get_db as router_get_db
from apps.api.routers import projects as projects_router

PROJECT_ID = str(uuid4())
TENANT_ID = str(uuid4())
USER_ID = str(uuid4())


class _User:
    """get_current_user override 스텁(실 JWT·DB 불요)."""

    id = USER_ID
    tenant_id = TENANT_ID
    role = "user"
    is_active = True


class _FakeProject:
    """_get_project_or_404 가 돌려줄 프로젝트 스텁(주소 SSOT만 필요)."""

    id = PROJECT_ID
    tenant_id = TENANT_ID
    address = "서울특별시 강남구 역삼동 123"
    parcels: list = []


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """db.execute() → scalar_one_or_none() 만 지원하는 최소 비동기 세션 가짜."""

    def __init__(self, project):
        self._project = project

    async def execute(self, *_a, **_k):
        return _ScalarResult(self._project)


def _build_app(*, project) -> FastAPI:
    app = FastAPI()
    app.include_router(projects_router.router, prefix="/api/v1/projects")
    app.dependency_overrides[get_current_user] = lambda: _User()
    app.dependency_overrides[router_get_db] = lambda: _FakeDB(project)
    app.dependency_overrides[core_get_db] = lambda: _FakeDB(project)
    return app


# ── 1) 타테넌트/없는 프로젝트 → 404(테넌트 격리·_get_project_or_404) ──

def test_pdf_route_other_tenant_404():
    app = _build_app(project=None)  # 조회 결과 없음 = 타테넌트/삭제/부재
    client = TestClient(app)
    resp = client.post(f"/api/v1/projects/{PROJECT_ID}/decision-brief/pdf", json={})
    assert resp.status_code == 404
    assert "찾을 수 없습니다" in resp.json()["detail"]


# ── 2) use_llm=True + 한도 초과 → 402(enforce_llm_quota 우회 차단) ──

def test_pdf_route_llm_quota_exceeded_402(monkeypatch):
    from app.core import request_context
    from app.services.billing import billing_service

    # enforce_llm_quota 는 request_context 의 user_id 가 있어야 게이트가 작동한다(없으면 통과).
    request_context.set_current_user_id(USER_ID)
    # 과금 한도 초과를 강제(실 DB 조회 대체) — 차단되면 402.
    async def _blocked(_db, _uid):
        return True

    async def _team_over(_db, _uid):
        return False

    monkeypatch.setattr(billing_service, "is_blocked", _blocked)
    monkeypatch.setattr(billing_service, "team_limit_exceeded", _team_over)
    # build 가 호출되기 전에 402 로 차단돼야 한다(우회 차단). build 가 불리면 테스트 실패시킨다.
    async def _must_not_build(self, **_k):  # pragma: no cover
        raise AssertionError("402 차단 전에 build 가 호출되면 안 된다")

    monkeypatch.setattr(
        "app.services.land_intelligence.decision_brief_service.DecisionBriefService.build",
        _must_not_build,
    )
    try:
        app = _build_app(project=_FakeProject())
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/projects/{PROJECT_ID}/decision-brief/pdf",
            json={"use_llm": True},
        )
        assert resp.status_code == 402
        assert "한도" in resp.json()["detail"]
    finally:
        request_context.set_current_user_id(None)


# ── 3) 성공 → application/pdf + Content-Disposition attachment(decision_brief_) + %PDF ──

def test_pdf_route_success_headers_and_body(monkeypatch):
    # build 는 PDF 빌더가 graceful 렌더 가능한 최소 브리프를 반환(실 엔진·DB 불요).
    async def _fake_build(self, **_k):
        return {
            "address": "서울특별시 강남구 역삼동 123",
            "parcel_count": 1,
            "parts": [],
            "verdict": {"decision": "HOLD", "confidence": "low",
                        "reasons": [], "blockers": [], "go_nogo": None, "gate": "PASS"},
            "meta": {"deploy_pending": True},
        }

    monkeypatch.setattr(
        "app.services.land_intelligence.decision_brief_service.DecisionBriefService.build",
        _fake_build,
    )
    app = _build_app(project=_FakeProject())
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/projects/{PROJECT_ID}/decision-brief/pdf", json={},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd
    # 백엔드 파일명 구분자(언더스코어) 통일 — 프론트 anchor.download 와 동일 규칙.
    assert f"decision_brief_{PROJECT_ID}.pdf" in cd
    assert resp.content.startswith(b"%PDF")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
