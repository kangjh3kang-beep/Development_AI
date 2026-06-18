"""중심엔진 통합 Phase 1-④ — BFF POST /api/v1/deliberation/analyze 오케스트레이션.

격리 앱 + dependency_overrides(인증) + 엔진 HTTP/binding/audit monkeypatch(엔진·DB 비의존).
검증: 성공(신규)·멱등 재사용·미연결 degrade·무결성실패(input_hash 불일치/run_id None)·인증·선검증 422·감사.
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.auth.auth_service import get_current_user
from app.services.deliberation._engine_contract import analysis_input_hash, build_input_dump
from apps.api.app.routers import deliberation as delib

_TID = uuid.UUID("11111111111111111111111111111111")


class _FakeUser:
    def __init__(self, tenant_id: uuid.UUID = _TID):
        self.id = uuid.UUID("22222222222222222222222222222222")
        self.tenant_id = tenant_id


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(delib.router)
    return app


def _client(monkeypatch, **patches):
    """엔진/binding/audit 기본 스텁 주입 후 인증 오버라이드 TestClient."""
    async def _audit_ok(**_):
        return {"ok": True}
    monkeypatch.setattr(delib, "append_audit", patches.get("audit", _audit_ok))
    monkeypatch.setattr(delib.binding_service, "lookup", patches["lookup"])
    monkeypatch.setattr(delib.binding_service, "insert", patches.get("insert"))
    monkeypatch.setattr(delib, "_engine_post_analyze", patches.get("post"))
    monkeypatch.setattr(delib, "_engine_get_analysis", patches.get("get"))
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return TestClient(app)


_PAYLOAD = {"pnu": "1111010100100000002",
            "calc_targets": [{"target": "building_area", "payload": {"outer_area": 500.0}}]}


_MISSING = object()


def _engine_result(ih: str, run_id=_MISSING):
    rid = str(uuid.uuid4()) if run_id is _MISSING else run_id  # None은 명시 None 유지(run_id 가드 테스트)
    return {"run_id": rid, "snapshot_id": "snap-1",
            "input_hash": ih, "report": {"items": [], "sections": []}, "skipped": []}


def test_analyze_requires_auth():
    app = _app()  # no override
    r = TestClient(app).post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code in (401, 403)


def test_analyze_success_new(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    posted = {}

    async def lookup(**kw):
        return None  # 신규
    async def post(dump):
        posted["dump"] = dump
        return _engine_result(ih)
    inserted = {}
    async def insert(**kw):
        inserted.update(kw)
        return True
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is False and body["result"]["input_hash"] == ih
    assert posted["dump"]["snapshot_id"] == "snap-1"           # 미러 기본값 채워 전송
    assert inserted["source"] == "sync" and inserted["tenant_id"] == _TID.hex  # 테넌트 결속


def test_analyze_idempotent_reuse(monkeypatch):
    existing_run = str(uuid.uuid4())
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    called = {"post": 0}

    async def lookup(**kw):
        return {"run_id": existing_run, "source": "sync", "status": "DONE", "result": None}
    async def post(dump):
        called["post"] += 1
        return _engine_result(ih)
    async def get(run_id):
        return _engine_result(ih, run_id=run_id)
    c = _client(monkeypatch, lookup=lookup, post=post, get=get)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["reused"] is True and called["post"] == 0  # 엔진 재호출 안 함(멱등)


def test_analyze_degraded_when_engine_unreachable(monkeypatch):
    async def lookup(**kw):
        return None
    async def post(dump):
        return None  # 미연결/타임아웃/circuit
    c = _client(monkeypatch, lookup=lookup, post=post)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True and body["final_status"] == "NEEDS_REVIEW"
    assert body["result"] is None and "engine" in body["reason"]


def test_analyze_invalid_response_input_hash_mismatch(monkeypatch):
    async def lookup(**kw):
        return None
    async def post(dump):
        return _engine_result("WRONG-HASH")  # 응답 input_hash 불일치
    inserted = {"n": 0}
    async def insert(**kw):
        inserted["n"] += 1
        return True
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True and body["reason"] == "invalid_response"
    assert inserted["n"] == 0  # 무결성 실패 → binding 미생성


def test_analyze_invalid_response_run_id_none(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return None
    async def post(dump):
        return _engine_result(ih, run_id=None)  # run_id 없음(엔진 계약 위반)
    async def insert(**kw):
        return True
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["reason"] == "invalid_response"


def test_analyze_prevalidate_rules_missing_rule_key(monkeypatch):
    async def lookup(**kw):
        return None
    c = _client(monkeypatch, lookup=lookup)
    bad = {"pnu": "1111010100100000002", "rules": [{"measured": 1}]}  # 'rule' 키 결손 → KeyError→500 회피
    r = c.post("/api/v1/deliberation/analyze", json=bad)
    assert r.status_code == 422


# ── GET /analyze/{run_id} (binding 소유검증→엔진 프록시) ──


def test_get_requires_auth():
    r = TestClient(_app()).get("/api/v1/deliberation/analyze/run-1")
    assert r.status_code in (401, 403)


def test_get_not_found_or_cross_tenant_returns_404(monkeypatch):
    async def lookup_by_run(**kw):
        return None  # 미존재 또는 타테넌트 — 동일 404(존재은닉)
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-x")
    assert r.status_code == 404


def test_get_returns_stored_result(monkeypatch):
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "async", "status": "DONE",
                "result": {"input_hash": "ih", "report": {"items": []}}}
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.status_code == 200 and r.json()["result"]["input_hash"] == "ih"


def test_get_proxies_engine_when_no_stored_result(monkeypatch):
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "sync", "status": "DONE", "result": None}
    async def get(rid):
        return {"run_id": rid, "report": {"x": 1}}
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "_engine_get_analysis", get)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.status_code == 200 and r.json()["result"]["report"] == {"x": 1}
