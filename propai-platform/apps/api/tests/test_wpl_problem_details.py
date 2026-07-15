"""WP-L 게이트 — RFC 9457 problem+json 오류봉투(신규 C2R 표면 opt-in).

핵심 게이트(계획서 §4 WP-L):
- problem+json 스키마 검증: type·title·status 필수 존재(+미디어타입 application/problem+json).
- opt-in 스코프: 신규 C2R 표면(access/survey-coordinate/basis/design-runs/submission-bundle)에만
  적용되고, 그 밖 경로(예: /api/v1/design/{id}/mass)는 FastAPI 기본 봉투 그대로(무회귀).
- 기존 예외와 공존: ProblemException은 표면 무관 항상 problem+json, HTTPException/검증오류는
  C2R 표면일 때만 problem+json.

라이브 전체앱 부팅(asyncpg 엔진) 없이 검증하려고, register_problem_handlers를 얹은 최소 FastAPI 앱과
TestClient로 실제 핸들러 계약을 그대로 구동한다(WP-E/WP-I DB-less 관례 동형).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.core.problem_details import (
    PROBLEM_MEDIA_TYPE,
    ProblemDetail,
    ProblemException,
    build_problem,
    is_problem_surface,
    register_problem_handlers,
)


class _Body(BaseModel):
    name: str  # 필수 — 누락 시 RequestValidationError(422) 유발


def _make_app() -> FastAPI:
    app = FastAPI()
    register_problem_handlers(app)

    @app.get("/api/v1/design-runs/{run_id}/boom-problem")
    async def _boom_problem(run_id: str):
        raise ProblemException(
            status=409, title="Conflict", code="APPROVE_REJECTED",
            detail="이미 APPROVED 상태입니다.",
        )

    @app.get("/api/v1/design-runs/{run_id}/boom-http")
    async def _boom_http_surface(run_id: str):
        raise HTTPException(status_code=404, detail="run 없음")

    @app.get("/api/v1/other/boom-http")
    async def _boom_http_other():
        raise HTTPException(status_code=404, detail="run 없음")

    @app.post("/api/v1/design-runs/validate")
    async def _validate_surface(body: _Body):
        return {"ok": True}

    @app.post("/api/v1/other/validate")
    async def _validate_other(body: _Body):
        return {"ok": True}

    # design_v61 스코프아웃 확인용(문제표면 아님).
    @app.get("/api/v1/design/{pid}/mass")
    async def _design_mass(pid: str):
        raise HTTPException(status_code=404, detail="mass 없음")

    # submission-bundle 접미 매칭(문제표면).
    @app.post("/api/v1/design/{pid}/submission-bundle")
    async def _submission(pid: str):
        raise HTTPException(status_code=422, detail={"message": "필수시트 미충족", "missing": ["A0"]})

    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


# ── 1. problem+json 스키마 계약(type/title/status 필수) ──────────────────────
def test_problem_exception_renders_problem_json(client):
    r = client.get("/api/v1/design-runs/dr_x/boom-problem")
    assert r.status_code == 409
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = r.json()
    # RFC 9457 필수 3필드.
    assert body["type"] == "about:blank"
    assert body["title"] == "Conflict"
    assert body["status"] == 409
    assert body["detail"] == "이미 APPROVED 상태입니다."
    assert body["code"] == "APPROVE_REJECTED"
    assert body["instance"] == "/api/v1/design-runs/dr_x/boom-problem"


def test_problem_detail_model_requires_title_and_status():
    """ProblemDetail 스키마는 title·status가 필수(type은 기본값 about:blank)."""
    m = ProblemDetail(title="Conflict", status=409)
    assert m.type == "about:blank" and m.title == "Conflict" and m.status == 409
    with pytest.raises(ValidationError):
        ProblemDetail(status=409)  # title 누락 → 검증 실패
    with pytest.raises(ValidationError):
        ProblemDetail(title="X")   # status 누락 → 검증 실패


def test_build_problem_protects_reserved_members():
    """확장 멤버가 예약필드(type/title/status)를 덮어쓰지 못한다."""
    body = build_problem(status=409, title="Conflict",
                         extensions={"status": 999, "title": "HACK", "code": "X"})
    assert body["status"] == 409 and body["title"] == "Conflict" and body["code"] == "X"


# ── 2. opt-in 스코프(신규 표면만 problem+json, 그 밖은 기본 봉투) ─────────────
def test_http_exception_on_surface_is_problem_json(client):
    r = client.get("/api/v1/design-runs/dr_x/boom-http")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = r.json()
    assert body["status"] == 404 and body["title"] == "Not Found"
    assert body["detail"] == "run 없음"


def test_http_exception_off_surface_keeps_default_envelope(client):
    """★스코프아웃 무회귀 — 비-C2R 경로는 FastAPI 기본 {"detail": ...} 봉투 그대로."""
    r = client.get("/api/v1/other/boom-http")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "problem+json" not in r.headers["content-type"]
    assert r.json() == {"detail": "run 없음"}


def test_design_mass_is_scoped_out(client):
    """★design_v61의 다른 엔드포인트(/design/{id}/mass)는 스코프아웃(과대적용 방지)."""
    r = client.get("/api/v1/design/p1/mass")
    assert "problem+json" not in r.headers["content-type"]
    assert r.json() == {"detail": "mass 없음"}


def test_submission_bundle_suffix_is_problem_surface(client):
    """submission-bundle은 접미 매칭으로 문제표면 — dict detail이 확장멤버로 편입된다."""
    r = client.post("/api/v1/design/p1/submission-bundle")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = r.json()
    assert body["status"] == 422
    assert body["detail"] == "필수시트 미충족"
    assert body["missing"] == ["A0"]  # dict detail의 나머지 키가 확장멤버로 보존


def test_validation_error_on_surface_is_problem_json(client):
    r = client.post("/api/v1/design-runs/validate", json={})  # name 누락
    assert r.status_code == 422
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = r.json()
    assert body["status"] == 422 and body["code"] == "VALIDATION_ERROR"
    assert isinstance(body["errors"], list) and len(body["errors"]) >= 1


def test_validation_error_off_surface_keeps_default(client):
    """비-C2R 경로의 검증오류는 FastAPI 기본 422 봉투(detail 리스트) 그대로."""
    r = client.post("/api/v1/other/validate", json={})
    assert r.status_code == 422
    assert "problem+json" not in r.headers["content-type"]
    assert "detail" in r.json()


# ── 3. is_problem_surface 경계 판정 ──────────────────────────────────────────
@pytest.mark.parametrize("path,expected", [
    ("/api/v1/access/assess", True),
    ("/api/v1/survey/coordinate/contract", True),
    ("/api/v1/basis/assess", True),
    ("/api/v1/design-runs/dr_x/approve", True),
    ("/api/v1/design/p1/submission-bundle", True),
    ("/api/v1/design/p1/submission-bundle/", True),
    ("/api/v1/design/p1/mass", False),
    ("/api/v1/design/p1/drawings/save", False),
    ("/api/v1/feasibility/analyze", False),
    ("/", False),
])
def test_is_problem_surface_boundaries(path, expected):
    assert is_problem_surface(path) is expected
