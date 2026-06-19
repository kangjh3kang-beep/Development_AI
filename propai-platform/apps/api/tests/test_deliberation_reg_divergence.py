"""중심엔진 수렴 — 규제 출처 정합 대조(reg-source divergence·P5).

플랫폼 ZONE_LIMITS vs 엔진 1차출처(reg/zone-limits) drift 대조. 순수 비교(compare_zone_limits)·
엔진 caller(_engine_get_zone_limits, 격리 breaker)·BFF 라우트(/reg/divergence, 인증·degrade) 검증.
"""
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.auth.auth_service import get_current_user
from app.services.deliberation import reg_reconcile
from app.services.deliberation.reg_reconcile import _classify, _engine_value, _num, compare_zone_limits
from apps.api.app.routers import deliberation as delib
from apps.api.integrations.base_client import CircuitBreaker


class _FakeUser:
    def __init__(self, tenant_id="11111111-1111-1111-1111-111111111111"):
        self.id = "u1"
        self.tenant_id = tenant_id


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(delib.router)
    return app


def _engine_env(zones: dict) -> dict:
    return {"meta": {"source": "국토계획법 시행령 §84·§85", "version": "v1"}, "zones": zones}


def _ezone(far=None, bcr=None) -> dict:
    out = {}
    if far is not None:
        out["far_floor_area"] = {"value": far, "unit": "%", "source": "s"}
    if bcr is not None:
        out["building_area"] = {"value": bcr, "unit": "%", "source": "s"}
    return out


# ── 순수 비교 ───────────────────────────────────────────────────────────────────

def test_num_rejects_bool_and_nonfinite():
    assert _num(250) == 250.0
    assert _num(True) is None and _num(float("nan")) is None and _num("250") is None


def test_classify_matched_drift_and_coverage():
    assert _classify(250.0, 250.0, 0.0) == ("matched", 0.0)
    st, rel = _classify(250.0, 300.0, 0.0)
    assert st == "drift" and abs(rel - 0.166667) < 1e-5
    assert _classify(250.0, None, 0.0) == ("platform_only", None)
    assert _classify(None, 250.0, 0.0) == ("engine_only", None)


def test_compare_matched_when_tables_agree():
    platform = {"제2종일반주거지역": {"max_far": 250, "max_bcr": 60}}
    engine = {"제2종일반주거지역": _ezone(far=250, bcr=60)}
    rep = compare_zone_limits(platform, engine)
    assert rep["matched"] == 2 and rep["drift"] == 0 and rep["match_rate"] == 1.0
    assert rep["compared"] == 2


def test_compare_surfaces_drift_and_coverage_gaps():
    platform = {
        "제2종일반주거지역": {"max_far": 250, "max_bcr": 60},   # far drift, bcr match
        "역세권개발구역": {"max_far": 700, "max_bcr": 80},        # 엔진 national 미수록 → platform_only
    }
    engine = {
        "제2종일반주거지역": _ezone(far=300, bcr=60),
        "준주거지역": _ezone(far=500, bcr=70),                    # 플랫폼 미수록 → engine_only
    }
    rep = compare_zone_limits(platform, engine)
    drift_rows = [r for r in rep["rows"] if r["status"] == "drift"]
    assert len(drift_rows) == 1 and drift_rows[0]["metric"] == "FAR"
    assert rep["matched"] == 1 and rep["drift"] == 1            # bcr 일치 1·far drift 1
    assert rep["platform_only"] == 2 and rep["engine_only"] == 2  # 역세권 far/bcr·준주거 far/bcr
    assert rep["match_rate"] == 0.5                             # compared=2(일치1/발산1)
    assert rep["platform_only_zones"] == ["역세권개발구역"]
    assert rep["engine_only_zones"] == ["준주거지역"]
    assert rep["unexpected_platform_only"] == []               # 역세권=기대 미수록 특별구역(회귀 아님)


def test_compare_flags_unexpected_platform_only_as_regression():
    # 엔진이 기존 표준 용도지역(제2종일반주거)을 잃으면 platform_only이나 drift==0 — drift만 보면 회귀가 묻힘.
    # unexpected_platform_only가 특별구역 allowlist 밖 누락을 별도 회귀 신호로 표면화.
    rep = compare_zone_limits({"제2종일반주거지역": {"max_far": 250, "max_bcr": 60}}, {})
    assert rep["drift"] == 0 and rep["match_rate"] is None      # drift/match_rate만 보면 정상 오인
    assert rep["unexpected_platform_only"] == ["제2종일반주거지역"]  # 회귀 표면화


def test_compare_empty_engine_yields_all_platform_only():
    rep = compare_zone_limits({"준주거지역": {"max_far": 500, "max_bcr": 70}}, {})
    assert rep["platform_only"] == 2 and rep["compared"] == 0 and rep["match_rate"] is None
    assert rep["unexpected_platform_only"] == ["준주거지역"]    # 표준 zone 누락 = 회귀 신호


def test_classify_zero_engine_limit():
    # ev==0 분기(0으로 나눔 방지) — 양측 0=matched, 한쪽만 0=drift.
    assert _classify(0.0, 0.0, 0.0) == ("matched", None)
    assert _classify(50.0, 0.0, 0.0) == ("drift", None)


def test_engine_value_isolates_malformed_metric():
    # 엔진 지표 항목 구조 비정상(list 등) → None(예외로 전체 대조를 죽이지 않게 격리).
    assert _engine_value({"value": 250}) == 250.0
    assert _engine_value([1, 2]) is None and _engine_value(None) is None
    assert _engine_value({"value": "x"}) is None  # 비수치 value


def test_compare_isolates_malformed_engine_metric_as_platform_only():
    # far가 list(변형)여도 예외 없이 해당 지표만 engine 결손 처리(bcr는 정상 대조 — 전체 무너짐 방지).
    platform = {"제2종일반주거지역": {"max_far": 250, "max_bcr": 60}}
    engine = {"제2종일반주거지역": {"far_floor_area": [1, 2], "building_area": {"value": 60}}}
    rep = compare_zone_limits(platform, engine)
    assert rep["matched"] == 1                                  # bcr 정상 대조 유지
    far_row = next(r for r in rep["rows"] if r["metric"] == "FAR")
    assert far_row["status"] == "platform_only"                 # 변형 far → engine 결손(격리)


# ── 엔진 caller(_engine_get_zone_limits) ────────────────────────────────────────

class _FakeSettings:
    deliberation_engine_url = "http://engine.local"
    deliberation_engine_api_token = "tok"
    deliberation_engine_connect_timeout_s = 5.0
    deliberation_engine_read_timeout_s = 30.0
    deliberation_engine_async_read_timeout_s = 60.0


class _FakeResp:
    def __init__(self, status_code, payload=None, *, raise_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._raise_json = raise_json
        self.text = "engine-body"

    def json(self):
        if self._raise_json:
            raise ValueError("malformed")
        return self._payload


class _FakeClient:
    def __init__(self, resp, calls):
        self._resp, self._calls = resp, calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        self._calls.append(("get", url, kw.get("headers")))
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def _install(monkeypatch, resp, *, threshold=5):
    monkeypatch.setattr(delib, "get_settings", lambda: _FakeSettings())
    br = CircuitBreaker(failure_threshold=threshold, recovery_timeout=9999.0, half_open_max=1)
    monkeypatch.setattr(delib, "_reg_breaker", br)
    calls: list = []
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(resp, calls))
    return br, calls


async def test_reg_caller_no_url_unreachable(monkeypatch):
    class _NoUrl(_FakeSettings):
        deliberation_engine_url = ""
    monkeypatch.setattr(delib, "get_settings", lambda: _NoUrl())
    data, reason = await delib._engine_get_zone_limits()
    assert data is None and reason == "engine_unreachable"


async def test_reg_caller_circuit_open_shortcircuits(monkeypatch):
    br, calls = _install(monkeypatch, _FakeResp(200, _engine_env({})), threshold=1)
    for _ in range(2):
        br.record_failure()
    data, reason = await delib._engine_get_zone_limits()
    assert reason == "circuit_open" and data is None and calls == []  # httpx 미호출


async def test_reg_caller_200_ok_sends_token(monkeypatch):
    env = _engine_env({"준주거지역": _ezone(far=500, bcr=70)})
    br, calls = _install(monkeypatch, _FakeResp(200, env))
    data, reason = await delib._engine_get_zone_limits()
    assert reason == "ok" and data == env and br.can_execute()
    assert calls[0][2].get("Authorization") == "Bearer tok"  # 인증 헤더 전송


async def test_reg_caller_malformed_200_is_invalid(monkeypatch):
    _install(monkeypatch, _FakeResp(200, raise_json=True))
    data, reason = await delib._engine_get_zone_limits()
    assert data is None and reason == "invalid_response"


async def test_reg_caller_missing_zones_is_invalid(monkeypatch):
    # 200이나 zones 부재 = 계약위반(거짓 빈 대조 방지).
    _install(monkeypatch, _FakeResp(200, {"meta": {}}))
    data, reason = await delib._engine_get_zone_limits()
    assert data is None and reason == "invalid_response"


async def test_reg_caller_4xx_rejected(monkeypatch):
    br, _ = _install(monkeypatch, _FakeResp(403))
    data, reason = await delib._engine_get_zone_limits()
    assert data is None and reason == "engine_rejected" and br.can_execute()  # 도달 → 회복(계약, breaker 제외)


async def test_reg_caller_5xx_counts_failure(monkeypatch):
    br, _ = _install(monkeypatch, _FakeResp(503), threshold=2)
    for _ in range(2):
        data, reason = await delib._engine_get_zone_limits()
        assert reason == "engine_unreachable"
    assert not br.can_execute()  # 5xx 누적 → OPEN(권위 _breaker와 격리됨)


async def test_reg_caller_timeout_records_failure(monkeypatch):
    # 타임아웃 분기 → reason=timeout + record_failure(threshold 1 → 1회로 OPEN, 부작용 입증).
    br, _ = _install(monkeypatch, httpx.TimeoutException("slow"), threshold=1)
    data, reason = await delib._engine_get_zone_limits()
    assert data is None and reason == "timeout" and not br.can_execute()


async def test_reg_caller_connection_error_unreachable(monkeypatch):
    # 연결오류(HTTPError) 분기 → engine_unreachable + record_failure. timeout과 구분.
    br, _ = _install(monkeypatch, httpx.ConnectError("refused"), threshold=1)
    data, reason = await delib._engine_get_zone_limits()
    assert data is None and reason == "engine_unreachable" and not br.can_execute()


async def test_reg_failure_does_not_pollute_authoritative_breaker(monkeypatch):
    # ★핵심 불변식 — reg 관측 5xx는 _reg_breaker만 열고 권위 analyze 회로(_breaker)는 무영향(격리 입증).
    br, _ = _install(monkeypatch, _FakeResp(503), threshold=2)
    for _ in range(4):
        await delib._engine_get_zone_limits()
    assert not br.can_execute()                 # reg breaker OPEN
    assert delib._breaker.can_execute() is True  # 권위 breaker 무오염(별도 인스턴스)


# ── BFF 라우트(/reg/divergence) ─────────────────────────────────────────────────

def test_reg_divergence_requires_auth():
    r = TestClient(_app()).get("/api/v1/deliberation/reg/divergence")
    assert r.status_code in (401, 403)


def test_reg_divergence_degrades_when_engine_down(monkeypatch):
    async def _down():
        return None, "circuit_open"
    monkeypatch.setattr(delib, "_engine_get_zone_limits", _down)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/reg/divergence")
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True and body["reason"] == "circuit_open"


def test_reg_divergence_passes_through_invalid_response(monkeypatch):
    # 엔진 계약위반(malformed/zones부재) → degrade reason 정직 통과(거짓 빈 대조 금지).
    async def _bad():
        return None, "invalid_response"
    monkeypatch.setattr(delib, "_engine_get_zone_limits", _bad)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/reg/divergence")
    assert r.status_code == 200 and r.json()["degraded"] is True
    assert r.json()["reason"] == "invalid_response"


def test_reg_divergence_success_reports_drift(monkeypatch):
    async def _engine():
        return _engine_env({"제2종일반주거지역": _ezone(far=300, bcr=60)}), "ok"
    monkeypatch.setattr(delib, "_engine_get_zone_limits", _engine)
    monkeypatch.setattr(reg_reconcile, "platform_zone_limits",
                        lambda: {"제2종일반주거지역": {"max_far": 250, "max_bcr": 60}})
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/reg/divergence")
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is False and body["drift"] == 1 and body["matched"] == 1
    assert body["engine_meta"]["version"] == "v1"


def test_reg_divergence_reconcile_failure_degrades(monkeypatch):
    async def _engine():
        return _engine_env({"준주거지역": _ezone(far=500)}), "ok"
    def _boom():
        raise RuntimeError("platform table import failed")
    monkeypatch.setattr(delib, "_engine_get_zone_limits", _engine)
    monkeypatch.setattr(reg_reconcile, "platform_zone_limits", _boom)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/reg/divergence")
    assert r.status_code == 200 and r.json()["degraded"] is True
    assert r.json()["reason"] == "reconcile_failed"
