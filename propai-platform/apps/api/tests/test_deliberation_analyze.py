"""중심엔진 통합 Phase 1-④ — BFF POST /api/v1/deliberation/analyze 오케스트레이션.

격리 앱 + dependency_overrides(인증) + 엔진 HTTP/binding/audit monkeypatch(엔진·DB 비의존).
검증: 성공(신규)·멱등 재사용·미연결 degrade·무결성실패(input_hash 불일치/run_id None)·인증·선검증 422·감사.
"""
from __future__ import annotations

import uuid
from datetime import UTC

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.auth.auth_service import get_current_user
from app.services.deliberation._engine_contract import analysis_input_hash, build_input_dump
from apps.api.app.routers import deliberation as delib
from apps.api.integrations.base_client import CircuitBreaker

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
    async def post(dump, deterministic=True, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
        called["post"] += 1
        return _engine_result(ih), "ok"
    async def get(run_id, tenant=None):
        return _engine_result(ih, run_id=run_id), "ok"
    c = _client(monkeypatch, lookup=lookup, post=post, get=get)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["reused"] is True and called["post"] == 0  # 엔진 재호출 안 함(멱등)


def test_analyze_degraded_when_engine_unreachable(monkeypatch):
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
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
    async def get(rid, tenant=None):
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
    async def get(rid, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
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
    async def get(run_id, tenant=None):
        return None, "engine_unreachable"
    c = _client(monkeypatch, lookup=lookup, get=get)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["result"] is None


def test_analyze_reuse_parity_fail_invalid_response(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return {"run_id": "run-1", "source": "sync", "result": None, "input_hash": ih}
    async def get(run_id, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        raise RuntimeError("ledger down")
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 502  # 감사 없는 판정 제공 금지(fail-closed)


def test_analyze_audit_quota_write_is_fail_closed_502(monkeypatch):
    # write 경로: 쿼터로 원장 미적재 = 감사 없는 권위 판정 → 502 차단(write_failed와 위험 동일).
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        return {"ok": False, "quota_exceeded": True}
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 502  # 감사 없는 판정 제공 금지(quota도 fail-closed)


def test_analyze_reuse_stored_result_parity_fail_degrades(monkeypatch):
    # 저장 영속본(async writer)이 채운 result라도 input_hash parity 불일치면 degrade(무음 disclose 금지).
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return {"run_id": "run-1", "source": "sync",
                "result": {"input_hash": "STALE", "report": {}}, "input_hash": ih}  # 저장본 parity 불일치
    c = _client(monkeypatch, lookup=lookup)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["reason"] == "invalid_response"


def test_analyze_reuse_audit_failure_is_fail_closed_502(monkeypatch):
    # 재사용도 write 경로(fail_closed) — 감사 예외 시 502(신규 경로와 대칭).
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return {"run_id": "run-1", "source": "sync",
                "result": {"input_hash": ih, "report": {}}, "input_hash": ih}
    async def audit(**kw):
        raise RuntimeError("ledger down")
    c = _client(monkeypatch, lookup=lookup, audit=audit)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 502


def test_analyze_engine_rejected_4xx_distinct_reason(monkeypatch):
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return False
    async def get(rid, tenant=None):
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
    async def post(dump, deterministic=True, tenant=None):
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
    assert r.json()["detail"]["audit_skipped"] == ["audit:not_ok"]  # skip 사유 라벨까지 고정


def test_get_degraded_reason_engine_rejected(monkeypatch):
    # 저장 result 없음 + 엔진 GET 4xx(토큰/계약) → engine_rejected로 정직 표면화(미연결과 구분).
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "sync", "result": None, "input_hash": "ih"}
    async def get(rid, tenant=None):
        return None, "engine_rejected"
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "_engine_get_analysis", get)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "engine_rejected"


def test_get_result_missing_when_engine_404(monkeypatch):
    # binding 존재하나 엔진이 run 분실(404) → result_missing(정합성 경고)로 정직 표면화.
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "sync", "result": None, "input_hash": "ih"}
    async def get(rid, tenant=None):
        return None, "not_found"
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "_engine_get_analysis", get)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "result_missing" and r.json()["run_id"] == "run-1"


def test_get_audit_failure_surfaces_not_502(monkeypatch):
    # read 경로(fail_closed=False) — 감사 예외는 502가 아니라 audit_degraded 표면화(write와 대칭의 반대).
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "sync",
                "result": {"input_hash": "ih", "report": {}}, "input_hash": "ih"}
    async def audit(**kw):
        raise RuntimeError("ledger down")
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "append_audit", audit)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.status_code == 200 and r.json()["audit_degraded"] is True
    assert r.json()["audit_skipped"] == ["audit:write_failed"]  # 예외→write_failed 라벨 고정


# ── _engine_post_analyze breaker/HTTP 분기(스텁 미사용·httpx mock으로 실분기 실행) ──


class _FakeSettings:
    deliberation_engine_url = "http://engine.local"
    deliberation_engine_api_token = "tok"
    deliberation_engine_connect_timeout_s = 5.0
    deliberation_engine_read_timeout_s = 30.0
    deliberation_engine_async_read_timeout_s = 60.0


class _FakeResp:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = "engine-body"

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp, calls):
        self._resp, self._calls = resp, calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _do(self, kind, url):
        self._calls.append((kind, url))
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp

    async def post(self, url, **kw):
        return await self._do("post", url)

    async def get(self, url, **kw):
        return await self._do("get", url)


def _install_engine(monkeypatch, resp, *, threshold=5):
    monkeypatch.setattr(delib, "get_settings", lambda: _FakeSettings())
    br = CircuitBreaker(failure_threshold=threshold, recovery_timeout=9999.0, half_open_max=1)
    monkeypatch.setattr(delib, "_breaker", br)
    calls: list = []
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(resp, calls))
    return br, calls


def test_engine_timeout_uses_async_read_for_nondeterministic():
    s = _FakeSettings()
    assert delib._engine_timeout(s, deterministic=True).read == 30.0
    assert delib._engine_timeout(s, deterministic=False).read == 60.0  # 라이브 경로 60s


async def test_engine_post_circuit_open_shortcircuits(monkeypatch):
    br, calls = _install_engine(monkeypatch, _FakeResp(200, {"run_id": "x"}), threshold=1)
    for _ in range(2):
        br.record_failure()  # circuit OPEN(threshold 1)
    data, reason = await delib._engine_post_analyze({"pnu": "x"})
    assert reason == "circuit_open" and data is None and calls == []  # httpx 미호출(폭주 차단)


async def test_engine_post_5xx_counts_failure_until_open(monkeypatch):
    br, calls = _install_engine(monkeypatch, _FakeResp(503), threshold=5)
    for _ in range(5):
        data, reason = await delib._engine_post_analyze({"pnu": "x"})
        assert data is None and reason == "engine_unreachable"
    assert not br.can_execute()  # 5xx 5회 → record_failure 누적 → circuit OPEN


async def test_engine_post_200_returns_ok(monkeypatch):
    payload = {"run_id": str(uuid.uuid4()), "input_hash": "ih", "report": {}}
    br, calls = _install_engine(monkeypatch, _FakeResp(200, payload))
    data, reason = await delib._engine_post_analyze({"pnu": "x"})
    assert reason == "ok" and data == payload and calls and br.can_execute()  # record_success → CLOSED 유지


async def test_engine_post_sends_x_tenant_id(monkeypatch):
    # #8a — BFF가 엔진 호출 시 X-Tenant-Id(정규화 테넌트)를 전송(엔진 organization_id 적재·소유필터의 키).
    captured: dict = {}
    payload = {"run_id": str(uuid.uuid4()), "input_hash": "ih", "report": {}}

    class _CapClient(_FakeClient):
        async def post(self, url, **kw):
            captured.update(kw)
            return await self._do("post", url)

    monkeypatch.setattr(delib, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(delib, "_breaker",
                        CircuitBreaker(failure_threshold=5, recovery_timeout=9999.0, half_open_max=1))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _CapClient(_FakeResp(200, payload), []))
    await delib._engine_post_analyze({"pnu": "x"}, tenant="1111111111111111ffff1111111111ff")
    assert captured["headers"].get("X-Tenant-Id") == "1111111111111111ffff1111111111ff"
    assert captured["headers"].get("Authorization", "").startswith("Bearer ")  # 토큰도 동봉


async def test_engine_get_sends_x_tenant_id(monkeypatch):
    captured: dict = {}

    class _CapClient(_FakeClient):
        async def get(self, url, **kw):
            captured.update(kw)
            return await self._do("get", url)

    monkeypatch.setattr(delib, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(delib, "_breaker",
                        CircuitBreaker(failure_threshold=5, recovery_timeout=9999.0, half_open_max=1))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _CapClient(_FakeResp(404), []))
    await delib._engine_get_analysis("run-1", tenant="abc123")
    assert captured["headers"].get("X-Tenant-Id") == "abc123"


async def test_engine_post_4xx_is_engine_rejected_no_breaker(monkeypatch):
    br, calls = _install_engine(monkeypatch, _FakeResp(422), threshold=5)
    for _ in range(5):
        data, reason = await delib._engine_post_analyze({"pnu": "x"})
        assert data is None and reason == "engine_rejected"
    assert br.can_execute()  # 4xx는 record_success(breaker 제외) → 5회에도 CLOSED


async def test_engine_get_non_dict_is_invalid_response(monkeypatch):
    # GET 200+비-dict(계약위반)는 POST와 대칭으로 invalid_response(미연결 아님).
    br, calls = _install_engine(monkeypatch, _FakeResp(200, ["not", "a", "dict"]))
    data, reason = await delib._engine_get_analysis("run-1")
    assert data is None and reason == "invalid_response"


def test_analyze_report_missing_is_invalid_response(monkeypatch):
    # 엔진 200이나 필수 report 결손(부분응답) → 공시 금지·invalid_response degrade.
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
        return {"run_id": str(uuid.uuid4()), "input_hash": ih, "snapshot_id": "snap-1"}, "ok"  # report 없음
    c = _client(monkeypatch, lookup=lookup, post=post)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["reason"] == "invalid_response"


def test_get_stored_result_parity_fail_degrades(monkeypatch):
    # ★저장 영속본(async writer)도 input_hash parity 불일치면 무검증 disclose 금지(reuse 경로와 대칭).
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "async",
                "result": {"input_hash": "STALE", "report": {}}, "input_hash": "ih"}
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "invalid_response"


def test_get_stored_result_report_missing_degrades(monkeypatch):
    # 저장 영속본의 report 결손(부분응답)도 disclose 금지.
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "async",
                "result": {"input_hash": "ih"}, "input_hash": "ih"}  # report 없음
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "invalid_response"


def test_get_circuit_open_reason(monkeypatch):
    async def lookup_by_run(**kw):
        return {"run_id": "run-1", "source": "sync", "result": None, "input_hash": "ih"}
    async def get(rid, tenant=None):
        return None, "circuit_open"
    monkeypatch.setattr(delib.binding_service, "lookup_by_run", lookup_by_run)
    monkeypatch.setattr(delib, "_engine_get_analysis", get)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/analyze/run-1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "circuit_open"


def test_analyze_audit_unchanged_passes(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        return {"unchanged": True}  # 멱등 재기록 → 통과(degraded 아님)
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 200 and r.json()["audit_degraded"] is False


def test_analyze_audit_not_ok_write_is_502(monkeypatch):
    # not_ok(quota 아님)도 write 경로는 502 fail-closed.
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        return {"ok": False}
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    r = c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert r.status_code == 502


def test_analyze_audit_records_authoritative_with_ih(monkeypatch):
    # fail-closed 감사의 신뢰가치=무엇이 기록되는가 — action/decision/input_hash 내용 검증.
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    captured: dict = {}
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        captured.update(kw)
        return {"ok": True}
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert captured["action"] == "analyze" and captured["resource_type"] == "deliberation"
    assert captured["metadata"]["decision"] == "authoritative" and captured["metadata"]["input_hash"] == ih


def test_analyze_audit_chain_key_matches_platform_canonical(monkeypatch):
    # 감사 체인 키=플랫폼 표준 str(tenant_id)(하이픈) — hex/하이픈 분열 방지. binding hex는 metadata 교차참조.
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    captured: dict = {}
    async def lookup(**kw):
        return None
    async def post(dump, deterministic=True, tenant=None):
        return _engine_result(ih), "ok"
    async def insert(**kw):
        return True
    async def audit(**kw):
        captured.update(kw)
        return {"ok": True}
    c = _client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit)
    c.post("/api/v1/deliberation/analyze", json=_PAYLOAD)
    assert captured["tenant_id"] == str(_TID)              # 하이픈 UUID(플랫폼 audit 표준 == str(tenant_id))
    assert "-" in captured["tenant_id"]                     # hex 아님(체인 통일)
    assert captured["metadata"]["binding_tenant"] == _TID.hex  # 결속 hex 교차참조 보존


# ── 비동기 경로(클러스터 D): POST /analyze/async · GET /analyze/task/{run_id} ──


def _ares(ih: str) -> dict:
    return {"run_id": str(uuid.uuid4()), "snapshot_id": "snap-1", "input_hash": ih,
            "report": {"sections": {}}, "skipped": []}


def _async_client(monkeypatch, **p):
    """async 경로 스텁(post_async/get_task/binding) 주입 후 인증 오버라이드 TestClient."""
    async def _audit_ok(**_):
        return {"ok": True}
    monkeypatch.setattr(delib, "append_audit", p.get("audit", _audit_ok))
    if "post_async" in p:
        monkeypatch.setattr(delib, "_engine_post_async", p["post_async"])
    if "get_task" in p:
        monkeypatch.setattr(delib, "_engine_get_task", p["get_task"])
    if "insert" in p:
        monkeypatch.setattr(delib.binding_service, "insert", p["insert"])
    if "lookup_by_run" in p:
        monkeypatch.setattr(delib.binding_service, "lookup_by_run", p["lookup_by_run"])
    if "update_result" in p:
        monkeypatch.setattr(delib.binding_service, "update_result", p["update_result"])
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return TestClient(app)


def test_async_eager_success_persists_and_returns(monkeypatch):
    ih = analysis_input_hash(build_input_dump(_PAYLOAD))
    inserted = {}
    async def post_async(dump, *, tenant=None):
        return {"task_id": "tk1", "status": "SUCCESS", "eager": True, "result": _ares(ih)}, "ok"
    async def insert(**kw):
        inserted.update(kw)
        return True
    c = _async_client(monkeypatch, post_async=post_async, insert=insert)
    r = c.post("/api/v1/deliberation/analyze/async", json=_PAYLOAD)
    body = r.json()
    assert body["degraded"] is False and body["status"] == "DONE" and body["result"]["input_hash"] == ih
    assert inserted["source"] == "async" and inserted["deterministic"] is False and inserted["engine_task_id"] == "tk1"


def test_async_queued_returns_pending(monkeypatch):
    async def post_async(dump, *, tenant=None):
        return {"task_id": "tk2", "status": "PENDING", "eager": False}, "ok"  # 결과 없음(broker)
    async def insert(**kw):
        return True
    c = _async_client(monkeypatch, post_async=post_async, insert=insert)
    r = c.post("/api/v1/deliberation/analyze/async", json=_PAYLOAD)
    body = r.json()
    assert body["degraded"] is False and body["status"] == "PENDING" and body["result"] is None and body["run_id"]


def test_async_post_degrade_when_engine_down(monkeypatch):
    async def post_async(dump, *, tenant=None):
        return None, "engine_unreachable"
    c = _async_client(monkeypatch, post_async=post_async)
    r = c.post("/api/v1/deliberation/analyze/async", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["reason"] == "engine_unreachable"


def test_async_eager_integrity_fail_degrades(monkeypatch):
    async def post_async(dump, *, tenant=None):
        return {"task_id": "tk3", "eager": True, "result": _ares("WRONG-HASH")}, "ok"  # parity 위반
    c = _async_client(monkeypatch, post_async=post_async)
    r = c.post("/api/v1/deliberation/analyze/async", json=_PAYLOAD)
    assert r.json()["degraded"] is True and r.json()["reason"] == "invalid_response"


def test_async_prevalidate_422(monkeypatch):
    c = _async_client(monkeypatch)
    r = c.post("/api/v1/deliberation/analyze/async",
               json={"pnu": "1111010100100000002", "calc_targets": [{"target": "BOGUS"}]})
    assert r.status_code == 422 and "target_enum" in r.json()["detail"]


def test_task_returns_stored_result(monkeypatch):
    ih = "ih-x"
    async def lookup_by_run(**kw):
        return {"run_id": "r1", "source": "async", "status": "DONE",
                "result": {"input_hash": ih, "report": {}}, "input_hash": ih,
                "engine_task_id": "tk", "created_at": None}
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run)
    r = c.get("/api/v1/deliberation/analyze/task/r1")
    assert r.json()["degraded"] is False and r.json()["status"] == "DONE" and r.json()["result"]["input_hash"] == ih


def test_task_resolves_engine_success_and_persists(monkeypatch):
    ih = "ih-y"
    updated = {}
    async def lookup_by_run(**kw):
        return {"run_id": "r1", "source": "async", "status": "PENDING", "result": None,
                "input_hash": ih, "engine_task_id": "tk", "created_at": None}
    async def get_task(task_id, *, tenant=None):
        return {"task_id": task_id, "status": "SUCCESS", "ready": True,
                "result": {"input_hash": ih, "report": {}}}, "ok"
    async def update_result(**kw):
        updated.update(kw)
        return True
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run, get_task=get_task, update_result=update_result)
    r = c.get("/api/v1/deliberation/analyze/task/r1")
    assert r.json()["status"] == "DONE" and r.json()["result"]["input_hash"] == ih
    assert updated["run_id"] == "r1" and updated["status"] == "DONE"  # BFF 영속


def test_task_failure_is_engine_task_failed(monkeypatch):
    async def lookup_by_run(**kw):
        return {"run_id": "r1", "source": "async", "result": None, "input_hash": "ih",
                "engine_task_id": "tk", "created_at": None}
    async def get_task(task_id, *, tenant=None):
        return {"status": "FAILURE", "ready": True, "result": None}, "ok"
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run, get_task=get_task)
    r = c.get("/api/v1/deliberation/analyze/task/r1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "engine_task_failed"


def test_task_ready_but_result_none_is_async_result_lost(monkeypatch):
    async def lookup_by_run(**kw):
        return {"run_id": "r1", "source": "async", "result": None, "input_hash": "ih",
                "engine_task_id": "tk", "created_at": None}
    async def get_task(task_id, *, tenant=None):
        return {"status": "SUCCESS", "ready": True, "result": None}, "ok"
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run, get_task=get_task)
    r = c.get("/api/v1/deliberation/analyze/task/r1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "async_result_lost"


def test_task_pending_returns_pending(monkeypatch):
    async def lookup_by_run(**kw):
        from datetime import datetime
        return {"run_id": "r1", "source": "async", "result": None, "input_hash": "ih",
                "engine_task_id": "tk", "created_at": datetime.now(UTC)}
    async def get_task(task_id, *, tenant=None):
        return {"status": "STARTED", "ready": False, "result": None}, "ok"
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run, get_task=get_task)
    r = c.get("/api/v1/deliberation/analyze/task/r1")
    assert r.json()["degraded"] is False and r.json()["status"] == "STARTED" and r.json()["result"] is None


def test_task_timeout_when_pending_too_long(monkeypatch):
    from datetime import datetime, timedelta
    async def lookup_by_run(**kw):
        return {"run_id": "r1", "source": "async", "result": None, "input_hash": "ih",
                "engine_task_id": "tk", "created_at": datetime.now(UTC) - timedelta(seconds=99999)}
    async def get_task(task_id, *, tenant=None):
        return {"status": "PENDING", "ready": False, "result": None}, "ok"
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run, get_task=get_task)
    r = c.get("/api/v1/deliberation/analyze/task/r1")
    assert r.json()["degraded"] is True and r.json()["reason"] == "async_timeout"


def test_task_ownership_404(monkeypatch):
    async def lookup_by_run(**kw):
        return None  # 미존재/타테넌트
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run)
    assert c.get("/api/v1/deliberation/analyze/task/r1").status_code == 404


def test_task_rejects_non_async_binding(monkeypatch):
    async def lookup_by_run(**kw):
        return {"run_id": "r1", "source": "sync", "result": None, "input_hash": "ih",
                "engine_task_id": None, "created_at": None}  # sync 결속은 task 경로 대상 아님
    c = _async_client(monkeypatch, lookup_by_run=lookup_by_run)
    assert c.get("/api/v1/deliberation/analyze/task/r1").status_code == 404
