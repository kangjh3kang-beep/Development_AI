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
        return _engine_result(ih), "ok"
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
        return _engine_result(ih), "ok"
    async def get(run_id):
        return _engine_result(ih, run_id=run_id), "ok"
    c = _client(monkeypatch, lookup=lookup, post=post, get=get)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["reused"] is True and called["post"] == 0  # 엔진 재호출 안 함(멱등)


def test_analyze_degraded_when_engine_unreachable(monkeypatch):
    async def lookup(**kw):
        return None
    async def post(dump):
        return None, "engine_unreachable"  # 미연결/타임아웃/circuit
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
        return _engine_result("WRONG-HASH"), "ok"  # 응답 input_hash 불일치
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
        return _engine_result(ih, run_id=None), "ok"  # run_id 없음(엔진 계약 위반)
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
        return {"run_id": rid, "report": {"x": 1}}, "ok"
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "_engine_get_analysis", get)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.status_code == 200 and r.json()["result"]["report"] == {"x": 1}


def test_get_degraded_when_no_stored_and_engine_down(monkeypatch):
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "sync", "status": "DONE", "result": None, "input_hash": "ih"}
    async def get(rid):
        return None, "engine_unreachable"
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "_engine_get_analysis", get)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.status_code == 200 and r.json()["degraded"] is True and r.json()["result"] is None


# ── 비결정 입력: 멱등 캐싱 스킵(§3·§9 R7) ──


def test_analyze_nondeterministic_skips_idempotency(monkeypatch):
    nondet = {"pnu": "1111010100100000002", "drawings": [{"sheet_id": "s1"}]}  # VLLM 경로
    ih = analysis_input_hash(build_input_dump(nondet))
    looked = {"n": 0}

    async def lookup(**kw):
        looked["n"] += 1
        return {"run_id": "STALE", "source": "sync", "result": None}  # 있어도 무시돼야
    async def post(dump):
        return _engine_result(ih), "ok"
    inserted = {}
    async def insert(**kw):
        inserted.update(kw)
        return True
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert)
    r = c.post("/api/v1/deliberation/analyze", json=nondet)
    assert r.status_code == 200
    body = r.json()
    assert body["deterministic"] is False and body["reused"] is False
    assert looked["n"] == 0                       # 멱등 lookup 미수행(비결정)
    assert inserted["deterministic"] is False      # 결속은 비-멱등으로 기록


def test_analyze_reuse_degrades_when_engine_get_fails(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return {"run_id": "run-1", "source": "sync", "result": None, "input_hash": ih}
    async def get(run_id):
        return None, "engine_unreachable"
    c = _client(monkeypatch, lookup=lookup, get=get)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["result"] is None


def test_analyze_reuse_parity_fail_invalid_response(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return {"run_id": "run-1", "source": "sync", "result": None, "input_hash": ih}
    async def get(run_id):
        return _engine_result("DIFFERENT-HASH", run_id=run_id), "ok"  # binding input_hash와 불일치
    c = _client(monkeypatch, lookup=lookup, get=get)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["reason"] == "invalid_response"


def test_analyze_insert_race_uses_winner_run_id(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    seq = {"n": 0}

    async def lookup(**kw):
        seq["n"] += 1
        return None if seq["n"] == 1 else {"run_id": "WINNER", "source": "sync",
                                           "result": {"input_hash": ih, "report": {}}, "input_hash": ih}
    async def post(dump):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return False  # 경합 패배
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    body = r.json()
    assert body["run_id"] == "WINNER" and body["result"]["report"] == {}  # 승자 run/result 일관


def test_analyze_audit_failure_is_fail_closed_502(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return None
    async def post(dump):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        raise RuntimeError("ledger down")
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 502  # 감사 없는 판정 제공 금지(fail-closed)


def test_analyze_audit_quota_surfaces_not_blocks(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return None
    async def post(dump):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        return {"ok": False, "quota_exceeded": True}
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200 and r.json()["audit_degraded"] is True  # 감사 한도 표면화·분석은 제공


def test_analyze_engine_rejected_4xx_distinct_reason(monkeypatch):
    async def lookup(**kw):
        return None
    async def post(dump):
        return None, "engine_rejected"  # 엔진 4xx(계약/매핑) — 미연결과 구분
    c = _client(monkeypatch, lookup=lookup, post=post)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["reason"] == "engine_rejected"


def test_analyze_prevalidate_target_enum_and_fact_key(monkeypatch):
    async def lookup(**kw):
        return None
    c = _client(monkeypatch, lookup=lookup)
    r1 = c.post("/api/v1/deliberation/analyze",
                json={"pnu": "1111010100100000002", "calc_targets": [{"target": "BOGUS"}]})
    assert r1.status_code == 422 and "target_enum" in r1.json()["detail"]
    r2 = c.post("/api/v1/deliberation/analyze",
                json={"pnu": "1111010100100000002", "cross_facts": [{"x": 1}]})
    assert r2.status_code == 422 and "fact_key_missing" in r2.json()["detail"]


# ── race 경로 무결성/정직성(MED 2건) ──


def test_analyze_race_winner_parity_fail_degrades(monkeypatch):
    # 경합 패배 후 승자 결속 result의 input_hash가 binding과 불일치 → invalid_response(재사용 경로와 대칭).
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    seq = {"n": 0}

    async def lookup(**kw):
        seq["n"] += 1
        if seq["n"] == 1:
            return None
        return {"run_id": "WINNER", "source": "sync",
                "result": {"input_hash": "A", "report": {}}, "input_hash": "B"}  # parity 불일치
    async def post(dump):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return False  # 경합 패배
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    body = r.json()
    assert body["degraded"] is True and body["reason"] == "invalid_response" and body["run_id"] == "WINNER"


def test_analyze_race_winner_unresolved_does_not_return_loser_result(monkeypatch):
    # 승자 result=None + 엔진 GET 실패 → loser res를 권위본으로 쓰지 않고 정직 degrade(run_id·result 일관 보존).
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    seq = {"n": 0}

    async def lookup(**kw):
        seq["n"] += 1
        return None if seq["n"] == 1 else {"run_id": "WINNER", "source": "sync",
                                           "result": None, "input_hash": ih}
    async def post(dump):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return False
    async def get(rid):
        return None, "engine_unreachable"
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, get=get)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    body = r.json()
    assert body["degraded"] is True and body["reason"] == "engine_unreachable"
    assert body["run_id"] == "WINNER" and body["result"] is None  # loser res 누출 금지


def test_analyze_integrity_violation_trips_breaker(monkeypatch):
    # 200이지만 parity 위반 = 엔진 계약 장애 → record_failure(반복 시 circuit 개방·무음 지속 차단).
    calls = {"fail": 0}
    monkeypatch.setattr(delib._breaker, "record_failure",
                        lambda: calls.__setitem__("fail", calls["fail"] + 1))

    async def lookup(**kw):
        return None
    async def post(dump):
        return _engine_result("WRONG-HASH"), "ok"  # parity 위반(200)
    c = _client(monkeypatch, lookup=lookup, post=post)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["reason"] == "invalid_response" and calls["fail"] == 1


def test_analyze_build_dump_server_bug_is_500_not_422(monkeypatch):
    # 미러/덤프 내부 버그(ValidationError 아님)는 클라이언트 422로 위장하지 않고 500으로 전파.
    def boom(_payload):
        raise AttributeError("mirror regression")
    monkeypatch.setattr(delib, "build_input_dump", boom)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 500


def test_get_404_surfaces_audit_degraded(monkeypatch):
    # 미존재/타테넌트 404이되 read-감사 degrade는 폐기하지 않고 detail로 표면화(무음0).
    async def lookup_by_run(**kw):
        return None
    async def audit(**kw):
        return {"ok": False}  # not_ok → read는 표면화(fail_closed=False)
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "append_audit", audit)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-x")
    assert r.status_code == 404 and r.json()["detail"]["audit_degraded"] is True


def test_get_degraded_reason_engine_rejected(monkeypatch):
    # 저장 result 없음 + 엔진 GET 4xx(토큰/계약) → engine_rejected로 정직 표면화(미연결과 구분).
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "sync", "result": None, "input_hash": "ih"}
    async def get(rid):
        return None, "engine_rejected"
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "_engine_get_analysis", get)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "engine_rejected"
