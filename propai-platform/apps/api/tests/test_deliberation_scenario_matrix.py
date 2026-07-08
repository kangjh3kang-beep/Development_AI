"""BE-4 — POST /api/v1/deliberation/scenario-matrix(다경우수 결정론 비교) + overrides 병합 단위검증.

격리 앱 + dependency_overrides(인증) + 엔진 HTTP/binding/audit monkeypatch(analyze 테스트 패턴 재사용).
검증: ①2~3 시나리오 정상 비교(verdict 상이) ②엔진 미도달 시 전 시나리오 unavailable 정직 강등
③시나리오 캡(12) 초과 422 ④overrides 병합 정확성(base 불변·깊은 병합, use_zone SSOT 치환)
⑤멱등 재사용 시 엔진 호출수 감소(캐시 로직 경유 확인).
"""
from __future__ import annotations

import copy
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.auth.auth_service import get_current_user
from app.services.deliberation import scenario_matrix as sm
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


def _sm_client(monkeypatch, **patches):
    """엔진/binding/audit 기본 스텁 주입 후 인증 오버라이드 TestClient(test_deliberation_analyze 패턴 재사용)."""
    async def _audit_ok(**_):
        return {"ok": True}
    monkeypatch.setattr(delib, "append_audit", patches.get("audit", _audit_ok))
    monkeypatch.setattr(delib.binding_service, "lookup", patches["lookup"])
    if "insert" in patches:
        monkeypatch.setattr(delib.binding_service, "insert", patches["insert"])
    monkeypatch.setattr(delib, "_engine_post_analyze", patches.get("post"))
    if "get" in patches:
        monkeypatch.setattr(delib, "_engine_get_analysis", patches["get"])
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return TestClient(app)


_BASE = {
    "pnu": "1111010100100000002",
    "rules": [
        {"rule": {"rule_id": "far-rule", "target_variable": "far_floor_area", "comparator": "<="},
         "measured": 220.0, "limit": 200.0, "relaxation_states": {}},
    ],
    "calc_targets": [{"target": "building_area", "payload": {"outer_area": 500.0}}],
}


def _fake_engine_result(dump: dict) -> dict:
    """실 엔진 대신 rules[0].measured<=limit로 COMPLIANT/NON_COMPLIANT 판정을 흉내(시나리오별 verdict 차이 재현)."""
    rule = (dump.get("rules") or [{}])[0]
    measured, limit = rule.get("measured"), rule.get("limit")
    compliant = measured is not None and limit is not None and measured <= limit
    sections = {"CONFIRMED": [{"item_id": "1"}]} if compliant else {"BLOCKED": [{"item_id": "1"}]}
    return {
        "run_id": str(uuid.uuid4()), "snapshot_id": dump.get("snapshot_id"),
        "input_hash": analysis_input_hash(dump),
        "report": {"items": [], "sections": sections},
        "findings": [{"rule_id": "far-rule", "verdict": "COMPLIANT" if compliant else "NON_COMPLIANT",
                     "measured_value": measured, "limit_value": limit}],
        "skipped": [],
    }


# ── HTTP 엔드포인트 ──────────────────────────────────────────────────────────


def test_scenario_matrix_requires_auth():
    app = _app()
    req = {"base": _BASE, "scenarios": [{"scenario_id": "s1", "label": "기준안", "overrides": {}}]}
    r = TestClient(app).post("/api/v1/deliberation/scenario-matrix", json=req)
    assert r.status_code in (401, 403)


def test_scenario_matrix_compares_scenarios_with_differing_verdicts(monkeypatch):
    async def lookup(**kw):
        return None  # 신규(멱등 미적중)

    async def post(dump, deterministic=True, tenant=None):
        return _fake_engine_result(dump), "ok"

    async def insert(**kw):
        return True

    c = _sm_client(monkeypatch, lookup=lookup, post=post, insert=insert)
    req = {
        "base": _BASE,
        "scenarios": [
            {"scenario_id": "baseline", "label": "기준안(완화 미적용)", "overrides": {}},
            {"scenario_id": "relaxed", "label": "완화 적용(한도 상향)",
             "overrides": {"rules": [{"rule_id": "far-rule", "limit": 250.0}]}},
        ],
    }
    r = c.post("/api/v1/deliberation/scenario-matrix", json=req)
    assert r.status_code == 200
    body = r.json()
    by_id = {s["scenario_id"]: s for s in body["scenarios"]}
    assert by_id["baseline"]["verdict"] == "BLOCKED"        # 220 > 200 → 미준수
    assert by_id["relaxed"]["verdict"] == "CONFIRMED"       # 220 <= 250(완화 후 한도) → 준수
    assert by_id["baseline"]["degraded"] is False and by_id["relaxed"]["degraded"] is False
    assert body["comparison"]["best_scenario_id"] == "relaxed"
    assert "baseline" in body["comparison"]["deltas"]


def test_scenario_matrix_all_unavailable_when_engine_unreachable(monkeypatch):
    async def lookup(**kw):
        return None

    async def post(dump, deterministic=True, tenant=None):
        return None, "engine_unreachable"

    c = _sm_client(monkeypatch, lookup=lookup, post=post)
    req = {
        "base": _BASE,
        "scenarios": [
            {"scenario_id": "s1", "label": "A", "overrides": {}},
            {"scenario_id": "s2", "label": "B", "overrides": {}},
        ],
    }
    r = c.post("/api/v1/deliberation/scenario-matrix", json=req)
    assert r.status_code == 200  # 정직 강등 — raise 금지
    body = r.json()
    assert len(body["scenarios"]) == 2
    for s in body["scenarios"]:
        assert s["degraded"] is True and s["verdict"] == "unavailable" and s["reason"] == "engine_unreachable"
    assert body["comparison"]["best_scenario_id"] is None  # 전원 degraded → 거짓 비교 금지


def test_scenario_matrix_cap_exceeded_returns_422():
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    scenarios = [{"scenario_id": f"s{i}", "label": f"시나리오{i}", "overrides": {}} for i in range(13)]  # 12 초과
    r = TestClient(app).post("/api/v1/deliberation/scenario-matrix",
                             json={"base": _BASE, "scenarios": scenarios})
    assert r.status_code == 422


def test_scenario_matrix_idempotent_reuse_reduces_engine_calls(monkeypatch):
    store: dict = {}
    posted = {"n": 0}
    ih_base = analysis_input_hash(build_input_dump(_BASE))

    async def lookup(**kw):
        key = (kw["tenant_id"], kw["content_input_hash"], kw.get("snapshot_id"))
        return store.get(key)

    async def post(dump, deterministic=True, tenant=None):
        posted["n"] += 1
        return _fake_engine_result(dump), "ok"

    async def insert(**kw):
        key = (kw["tenant_id"], kw["content_input_hash"], kw.get("snapshot_id"))
        store[key] = {"run_id": kw["run_id"], "source": kw["source"], "status": "DONE",
                     "result": None, "input_hash": kw["input_hash"]}
        return True

    async def get(run_id, tenant=None):
        base_result = _fake_engine_result(build_input_dump(_BASE))
        base_result["run_id"] = run_id
        base_result["input_hash"] = ih_base
        return base_result, "ok"

    c = _sm_client(monkeypatch, lookup=lookup, post=post, insert=insert, get=get)
    req = {"base": _BASE, "scenarios": [{"scenario_id": "s1", "label": "기준안", "overrides": {}}]}
    r1 = c.post("/api/v1/deliberation/scenario-matrix", json=req)
    r2 = c.post("/api/v1/deliberation/scenario-matrix", json=req)
    assert r1.status_code == 200 and r2.status_code == 200
    assert posted["n"] == 1  # 2회차는 멱등캐시 재사용 — 엔진 재호출 없음
    assert r2.json()["scenarios"][0]["reused"] is True


# ── overrides 병합(순수함수) ────────────────────────────────────────────────


def test_apply_overrides_base_immutable_and_relaxation_states_merge():
    base = copy.deepcopy(_BASE)
    snapshot = copy.deepcopy(base)
    merged, warnings = sm.apply_overrides(base, {
        "relaxation_states": {"far-rule": {"public_open_space": "applied"}},
    })
    assert base == snapshot  # base 원본 불변
    assert merged["rules"][0]["relaxation_states"] == {"public_open_space": "applied"}
    assert merged["pnu"] == base["pnu"]  # 무관 필드는 그대로 보존(깊은 병합)
    assert warnings == []


def test_apply_overrides_relaxation_states_unmatched_rule_warns():
    _, warnings = sm.apply_overrides(_BASE, {"relaxation_states": {"no-such-rule": {"x": "y"}}})
    assert warnings == ["relaxation_states_no_matching_rule:no-such-rule"]


def test_apply_overrides_rules_patch_alternative_measured_limit():
    merged, warnings = sm.apply_overrides(_BASE, {
        "rules": [{"rule_id": "far-rule", "measured": 180.0, "limit": 220.0}],
    })
    assert merged["rules"][0]["measured"] == 180.0 and merged["rules"][0]["limit"] == 220.0
    assert _BASE["rules"][0]["measured"] == 220.0  # base 불변(모듈 상수 오염 없음)
    assert warnings == []


def test_apply_overrides_use_zone_substitutes_limit_from_ssot():
    merged, warnings = sm.apply_overrides(_BASE, {"use_zone": "제3종일반주거지역"})
    assert merged["rules"][0]["limit"] == 300  # ZONE_LIMITS["제3종일반주거지역"]["max_far"]
    assert warnings == []


def test_apply_overrides_unknown_use_zone_surfaces_warning():
    merged, warnings = sm.apply_overrides(_BASE, {"use_zone": "존재하지않는용도지역"})
    assert merged["rules"][0]["limit"] == 200.0  # 원본 유지(무음 변경 금지)
    assert warnings == ["unknown_use_zone:존재하지않는용도지역"]


def test_apply_overrides_calc_targets_payload_merge():
    merged, warnings = sm.apply_overrides(_BASE, {
        "calc_targets": [{"target": "building_area", "payload": {"outer_area": 600.0}}],
    })
    assert merged["calc_targets"][0]["payload"]["outer_area"] == 600.0
    assert _BASE["calc_targets"][0]["payload"]["outer_area"] == 500.0  # base 불변
    assert warnings == []


def test_build_comparison_empty_when_all_degraded():
    results = [sm.unavailable_result("s1", "A", reason="engine_unreachable"),
              sm.unavailable_result("s2", "B", reason="engine_unreachable")]
    comparison = sm.build_comparison(results)
    assert comparison == {"best_scenario_id": None, "deltas": {}}


# ── 독립리뷰 반영 회귀(HIGH 2건) ────────────────────────────────────────────


def test_apply_overrides_non_dict_patch_items_warn_not_raise():
    """★리뷰 HIGH: overrides.rules/calc_targets에 비-dict 항목 — 예외 없이 경고 표면화(배치 생존)."""
    merged, w = sm.apply_overrides(copy.deepcopy(_BASE), {"rules": ["oops-not-a-dict"]})
    assert any(x.startswith("rules_patch_not_dict:") for x in w)
    assert merged["rules"] == _BASE["rules"]  # 원본 rules 불변(스킵)

    merged2, w2 = sm.apply_overrides(copy.deepcopy(_BASE), {"calc_targets": ["oops"]})
    assert any(x.startswith("calc_targets_patch_not_dict:") for x in w2)
    assert merged2["calc_targets"] == _BASE["calc_targets"]


def test_scenario_matrix_batch_survives_malformed_overrides(monkeypatch):
    """★리뷰 HIGH: 시나리오 1건의 overrides 구조 오류가 배치 전체를 500으로 죽이면 안 됨 —
    해당 시나리오는 경고와 함께 진행(또는 강등)되고 정상 시나리오 결과는 보존된다."""
    async def lookup(**kw):
        return None

    async def post(dump, deterministic=True, tenant=None):
        return _fake_engine_result(dump), "ok"

    async def insert(**kw):
        return True

    c = _sm_client(monkeypatch, lookup=lookup, post=post, insert=insert)
    req = {
        "base": _BASE,
        "scenarios": [
            {"scenario_id": "good", "label": "정상", "overrides": {}},
            {"scenario_id": "bad", "label": "구조오류", "overrides": {"rules": ["oops-not-a-dict"]}},
        ],
    }
    r = c.post("/api/v1/deliberation/scenario-matrix", json=req)
    assert r.status_code == 200  # ★배치 생존(과거: AttributeError → 500)
    body = r.json()
    by_id = {s["scenario_id"]: s for s in body["scenarios"]}
    assert by_id["good"]["degraded"] is False  # 정상 시나리오 결과 보존
    assert any(x.startswith("rules_patch_not_dict:") for x in by_id["bad"]["warnings"])  # 정직 표면화


def test_scenario_matrix_audit_failure_degrades_scenario_not_502(monkeypatch):
    """★리뷰 HIGH: 감사(append_audit) 실패가 배치 전체 502가 아니라 — 권위 판정 시나리오만
    audit_failed로 강등되고(감사 없는 권위 판정 금지 보존) 나머지 시나리오는 산출된다."""
    calls = {"n": 0}

    async def lookup(**kw):
        return None

    async def post(dump, deterministic=True, tenant=None):
        return _fake_engine_result(dump), "ok"

    async def insert(**kw):
        return True

    async def audit_fails_second(**_):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("audit backend down")
        return {"ok": True}

    c = _sm_client(monkeypatch, lookup=lookup, post=post, insert=insert, audit=audit_fails_second)
    req = {
        "base": _BASE,
        "scenarios": [
            {"scenario_id": "s1", "label": "A", "overrides": {}},
            {"scenario_id": "s2", "label": "B",
             "overrides": {"rules": [{"rule_id": "far-rule", "limit": 250.0}]}},
            {"scenario_id": "s3", "label": "C",
             "overrides": {"rules": [{"rule_id": "far-rule", "limit": 300.0}]}},
        ],
    }
    r = c.post("/api/v1/deliberation/scenario-matrix", json=req)
    assert r.status_code == 200  # ★배치 생존(과거: HTTPException 502 전파로 전체 소실)
    body = r.json()
    assert len(body["scenarios"]) == 3
    degraded = [s for s in body["scenarios"] if s["degraded"]]
    ok = [s for s in body["scenarios"] if not s["degraded"]]
    # 감사 실패한 1건만 audit_failed 강등 — 나머지 2건은 정상 산출.
    assert len(degraded) == 1 and degraded[0]["reason"] == "audit_failed"
    assert "audit:write_failed" in degraded[0]["warnings"]
    assert len(ok) == 2
