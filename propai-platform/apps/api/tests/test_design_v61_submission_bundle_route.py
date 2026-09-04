"""WP-F POST /{project_id}/submission-bundle 라우트 통합 테스트.

경량 TestClient(design_v61.router만 마운트 — test_decision_brief_pdf_route.py 패턴 준용).
인증(무인증 401)·소유권(타테넌트 403)·성공(200 zip+매니페스트 무결)·필수시트 누락(422+목록)·
기존 generate-full-set 엔드포인트 무회귀(sheet_manifest 필드는 additive)를 검증한다.
"""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.auth.auth_service import get_current_user
from apps.api.database.session import get_db

PROJECT_ID = str(uuid4())
TENANT_ID = str(uuid4())
OTHER_TENANT_ID = str(uuid4())


def _build_app() -> FastAPI:
    """design_v61 라우터만 마운트한 경량 앱(전체 main.py 미부팅 — 무거운 의존성 회피)."""
    from app.routers.design_v61 import router

    app = FastAPI()
    app.include_router(router)
    return app


class _ScalarFirstResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDB:
    """_assert_project_owned가 쓰는 db.execute(text(...)).first() 만 지원하는 최소 가짜 세션."""

    def __init__(self, tenant_id: str | None):
        self._tenant_id = tenant_id

    async def execute(self, *_a, **_k):
        row = (self._tenant_id,) if self._tenant_id is not None else None
        return _ScalarFirstResult(row)


def _override_auth(app: FastAPI, *, tenant_id: str = TENANT_ID) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        tenant_id=tenant_id, id="test-user",
    )


# ── 1) 인증·소유권 ────────────────────────────────────────────────────


def test_submission_bundle_requires_auth_401():
    """get_current_user override 없이 호출하면(인증 헤더 부재) 401."""
    app = _build_app()
    client = TestClient(app)
    resp = client.post(f"/api/v1/design/{PROJECT_ID}/submission-bundle", json={})
    assert resp.status_code == 401


def test_submission_bundle_other_tenant_403():
    """프로젝트 소유 tenant와 다른 사용자가 호출하면 403(IDOR 방지)."""
    app = _build_app()
    _override_auth(app, tenant_id=TENANT_ID)
    app.dependency_overrides[get_db] = lambda: _FakeDB(tenant_id=OTHER_TENANT_ID)
    client = TestClient(app)
    resp = client.post(f"/api/v1/design/{PROJECT_ID}/submission-bundle", json={})
    assert resp.status_code == 403


# ── 2) 성공 경로 ──────────────────────────────────────────────────────


def test_submission_bundle_success_returns_valid_zip_with_manifest():
    """인증·소유 프로젝트(비UUID 데모ID — db 미접근)로 정상 호출 시 200 + 유효 zip."""
    app = _build_app()
    _override_auth(app)
    app.dependency_overrides[get_db] = lambda: None  # 비UUID project_id는 db 미접근
    client = TestClient(app)
    resp = client.post(
        "/api/v1/design/demo-project-1/submission-bundle",
        json={"issue_date": "2026-07-15", "scale": "1:100"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert "submission_bundle.zip" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        import json

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["file_count"] == len(manifest["files"])
        # 필수시트 5종 모두 present=True(성공 = 필수시트 100%) — sheets 목록으로 판정.
        required_present = {s["code"] for s in manifest["sheets"] if s["required"] and s["present"]}
        assert {"B-01", "B-02-STD", "B-03", "B-04-F", "B-04-S"} <= required_present
        # 파일별 sha256 전수 대조(라우트 산출물도 매니페스트 계약을 지킴)
        import hashlib

        for entry in manifest["files"]:
            actual = hashlib.sha256(zf.read(entry["arcname"])).hexdigest()
            assert actual == entry["sha256"]


def test_submission_bundle_default_options_include_report_and_boq():
    """기본옵션(include_report/include_boq=True)이면 report.pdf·boq.xlsx도 zip에 동봉."""
    app = _build_app()
    _override_auth(app)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)
    resp = client.post("/api/v1/design/demo-project-2/submission-bundle", json={})
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "report/report.pdf" in names
        assert "boq/boq.xlsx" in names
        assert zf.read("report/report.pdf").startswith(b"%PDF")


def test_submission_bundle_include_report_and_boq_false_omits_them():
    """include_report=False·include_boq=False면 해당 파트가 zip에서 정직하게 빠진다."""
    app = _build_app()
    _override_auth(app)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)
    resp = client.post(
        "/api/v1/design/demo-project-3/submission-bundle",
        json={"include_report": False, "include_boq": False, "include_dxf": False},
    )
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "report/report.pdf" not in names
        assert "boq/boq.xlsx" not in names
        assert not any(n.endswith(".dxf") for n in names)
        # 필수 SVG 시트는 여전히 포함(부가물만 빠짐 — 산출 거부 아님)
        assert any(n.startswith("drawings/") and n.endswith(".svg") for n in names)


def test_submission_bundle_issue_date_not_server_now():
    """issue_date 미전달 시 표제란은 서버 now()가 아니라 정직 공란(무목업 원칙)."""
    app = _build_app()
    _override_auth(app)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)
    resp = client.post("/api/v1/design/demo-project-4/submission-bundle", json={})
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        import json

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["issue_date"] == ""


# ── 3) 필수시트 누락 → 422 정직 거부 ──────────────────────────────────


def test_submission_bundle_missing_required_sheet_returns_422_with_missing_list(monkeypatch):
    """도면 생성기가 필수시트 하나를 못 만들면(예: 엔진 이상) 무음 부분산출 대신 422+목록."""
    import app.routers.design_v61 as design_v61_module

    original = design_v61_module.svg_service.generate_full_drawing_set

    def _drop_b03(project_data):
        drawings = original(project_data)
        drawings.pop("B-03", None)
        return drawings

    monkeypatch.setattr(design_v61_module.svg_service, "generate_full_drawing_set", _drop_b03)

    app = _build_app()
    _override_auth(app)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)
    resp = client.post("/api/v1/design/demo-project-5/submission-bundle", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["missing"][0]["code"] == "B-03"


# ── 4) 기존 generate-full-set 엔드포인트 무회귀(additive 필드만 추가) ───


def test_generate_full_set_route_unchanged_plus_additive_sheet_manifest():
    """기존 drawings/drawing_count 필드는 그대로이고, sheet_manifest는 추가 필드로만 붙는다."""
    app = _build_app()
    client = TestClient(app)  # 이 엔드포인트는 인증 불요(기존 동작 — 무회귀 확인 대상)
    resp = client.post("/api/v1/design/demo-project-6/generate-full-set", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "drawings" in data and "drawing_count" in data
    assert data["drawing_count"] == len(data["drawings"])
    assert "sheet_manifest" in data  # WP-F 신규 additive 필드
    codes = {row["code"] for row in data["sheet_manifest"]}
    assert {"B-01", "B-02-STD", "B-03", "B-04-F", "B-04-S"} <= codes


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
