"""히스토리 확산 — /precheck/instant 원장 배선 라우터 테스트(경량 TestClient, 전체 앱 비의존).

90초진단은 완전 무기록·무인증이었다(진단 결과). 이 테스트는:
  1) optional 인증(get_current_user_optional) 부착으로 비로그인도 200(체험 퍼널 무회귀).
  2) 비로그인은 원장 기록을 완전히 skip(과적재 방지 — 로그인 사용자만 기록).
  3) 로그인 시 analysis_type="precheck"로 best-effort 기록되며, summary가
     zone_type/area_sqm/far_effective_pct/bcr_effective_pct/best/pass_count를 담는다
     (legal_limits.applied_far_pct 우선, 없으면 far_pct 폴백 — bcr도 동일).
  4) ★P3(R1 REVISE): zone/pnu 미확인 early-return(ok=False)은 로그인 사용자여도 기록을
     skip한다(핵심 필드 결측인 빈 요약이 히스토리에 쌓이는 것을 방지).

run_instant_precheck/record_user_analysis는 monkeypatch로 대체해 외부 API·DB 호출 없이
라우터의 인증분기 + 기록 매핑 로직만 검증한다.
"""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.services.auth.auth_service import get_current_user_optional
from apps.api.routers import precheck as precheck_router

_ADDR = "서울특별시 강남구 역삼동 736"

_FAKE_RESULT = {
    "ok": True, "address": _ADDR, "pnu": "1168010100108120000",
    "zone_type": "제2종일반주거지역", "area_sqm": 300.0,
    "legal_limits": {
        "applied_far_pct": 220.0, "applied_bcr_pct": 55.0,
        "far_pct": 200.0, "bcr_pct": 60.0,
    },
    "methods": [], "summary": {"pass": 3, "warn": 1, "fail": 0, "best": "M06", "llm_note": None},
    "elapsed_ms": 10, "sources": [],
}

# applied_* 미확보(조례 미확인) — far_pct/bcr_pct(법정상한) 폴백 검증용.
_FAKE_RESULT_NO_APPLIED = {
    "ok": True, "address": _ADDR, "pnu": "1168010100108120000",
    "zone_type": "자연녹지지역", "area_sqm": 500.0,
    "legal_limits": {"far_pct": 80.0, "bcr_pct": 20.0},
    "methods": [], "summary": {"pass": 0, "warn": 2, "fail": 1, "best": None, "llm_note": None},
    "elapsed_ms": 8, "sources": [],
}


class _FakeUser:
    def __init__(self, tenant_id):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id


def _make_client(monkeypatch, *, fake_result=None, record_calls=None, authed_tenant=None):
    import app.services.precheck.precheck_service as precheck_service

    async def _fake_precheck(**kwargs):
        return dict(fake_result or _FAKE_RESULT)

    monkeypatch.setattr(precheck_service, "run_instant_precheck", _fake_precheck)

    if record_calls is not None:
        import app.services.ledger.ledger_adapters as ledger_adapters

        async def _fake_record(**kwargs):
            record_calls.append(kwargs)
            return {"ok": True, "content_hash": "fakehash-precheck", "version": 1}

        monkeypatch.setattr(ledger_adapters, "record_user_analysis", _fake_record)

    app = FastAPI()
    app.include_router(precheck_router.router)

    async def _override_db():
        yield None

    app.dependency_overrides[get_db] = _override_db
    if authed_tenant is not None:
        app.dependency_overrides[get_current_user_optional] = lambda: _FakeUser(authed_tenant)
    return TestClient(app)


def test_precheck_instant_anonymous_returns_200_and_skips_ledger(monkeypatch):
    """optional 인증 무회귀 — 비로그인도 200이며, 원장 기록은 완전히 skip된다."""
    calls: list = []
    client = _make_client(monkeypatch, record_calls=calls)
    resp = client.post("/instant", json={"address": _ADDR})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "ledger_hash" not in body
    assert calls == []  # record_user_analysis 자체가 호출되지 않아야 함(비로그인 skip)


def test_precheck_instant_logged_in_records_precheck_keymap_fields(monkeypatch):
    """로그인 사용자는 analysis_type="precheck"로 DiffTable 키맵용 필드가 기록된다."""
    calls: list = []
    tid = uuid.uuid4()
    client = _make_client(monkeypatch, record_calls=calls, authed_tenant=tid)
    resp = client.post("/instant", json={"address": _ADDR})
    assert resp.status_code == 200
    assert resp.json().get("ledger_hash") == "fakehash-precheck"

    assert len(calls) == 1
    kw = calls[0]
    assert kw["analysis_type"] == "precheck"
    assert kw["tenant_id"] == str(tid)
    assert kw["address"] == _ADDR
    assert kw["source"] == "precheck"
    assert kw["parcel_count"] == 1
    assert kw["use_llm"] is False

    summ = kw["summary"]
    assert summ["zone_type"] == "제2종일반주거지역"
    assert summ["area_sqm"] == 300.0
    assert summ["far_effective_pct"] == 220.0  # applied_far_pct 우선
    assert summ["bcr_effective_pct"] == 55.0   # applied_bcr_pct 우선
    assert summ["best"] == "M06"
    assert summ["pass_count"] == 3


def test_precheck_instant_falls_back_to_legal_far_bcr_when_applied_missing(monkeypatch):
    """applied_far_pct/applied_bcr_pct 미확보(조례 미확인) 시 far_pct/bcr_pct(법정상한)로 폴백."""
    calls: list = []
    client = _make_client(
        monkeypatch, fake_result=_FAKE_RESULT_NO_APPLIED, record_calls=calls,
        authed_tenant=uuid.uuid4(),
    )
    resp = client.post("/instant", json={"address": _ADDR})
    assert resp.status_code == 200
    assert len(calls) == 1
    summ = calls[0]["summary"]
    assert summ["far_effective_pct"] == 80.0
    assert summ["bcr_effective_pct"] == 20.0
    assert summ["best"] is None
    assert summ["pass_count"] == 0


def test_precheck_instant_ok_false_skips_ledger(monkeypatch):
    """★P3(R1 REVISE): zone/pnu 미확인 early-return(ok=False)은 원장 기록에서 제외한다.

    zone_type/legal_limits/summary가 전부 결측인 상태로 기록하면 빈 요약 히스토리 항목만
    쌓인다 — 로그인 사용자여도 ok=False면 record_user_analysis 자체가 호출되지 않아야 한다.
    """
    calls: list = []
    fake_fail_result = {
        "ok": False,
        "message": "용도지역을 확인할 수 없습니다.",
        "address": _ADDR,
        "pnu": None,
        "elapsed_ms": 5,
        "sources": ["auto_zoning_service(error)"],
    }
    client = _make_client(
        monkeypatch, fake_result=fake_fail_result, record_calls=calls, authed_tenant=uuid.uuid4(),
    )
    resp = client.post("/instant", json={"address": _ADDR})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "ledger_hash" not in body
    assert calls == []  # ok=False는 record_user_analysis 자체가 호출되지 않아야 함


def test_precheck_instant_ledger_failure_does_not_break_response(monkeypatch):
    """원장 적재 실패(예외)해도 90초진단 결과는 무손상 반환(best-effort try/except)."""
    import app.services.precheck.precheck_service as precheck_service

    async def _fake_precheck(**kwargs):
        return dict(_FAKE_RESULT)

    monkeypatch.setattr(precheck_service, "run_instant_precheck", _fake_precheck)

    import app.services.ledger.ledger_adapters as ledger_adapters

    async def _boom(**kwargs):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(ledger_adapters, "record_user_analysis", _boom)

    app = FastAPI()
    app.include_router(precheck_router.router)

    async def _override_db():
        yield None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_optional] = lambda: _FakeUser(uuid.uuid4())
    client = TestClient(app)

    resp = client.post("/instant", json={"address": _ADDR})
    assert resp.status_code == 200
    assert "ledger_hash" not in resp.json()
