"""설계엔진(auto_design_engine) 실효 용적률 far_tier SSOT 배선 회귀 가드 — WP-U2a.

버그클래스(실효FAR SSOT 캠페인 5번째 표면): 설계엔진은 자체 보수 static ZONE_LIMITS를
hard cap으로 쓰고, SSOT(far_tier_service.calc_effective_far — 법정§84/85·조례·계획·인센티브·
구조상한 계층 min) 실효치는 ordinance_far_percent로 opt-in 유입된다(상향 불가 min-clamp).
이 테스트는 그 배선 계약을 잠근다:

 (1) 자연녹지: SSOT 실효(구조상한 80%) 주입 시 적용 한도가 80%로 정직 하향(과대 방지).
 (2) SSOT 미주입: 기존 보수 동작(static 100%·12m 높이캡 → 4층·FAR≈80%) 완전 보존(무회귀).
 (3) 비클램프 지역(제2종): SSOT(250%)가 static(200%)보다 높아도 상향 없음(보수 정책 유지 —
     hard cap 상향 금지). 주입/미주입 산출 동일.
 (4) far_basis/far_reliable 정직 전파: SiteInput → summary.basis.applied_limits · rule_trace.
 (5) 페르소나 러너 _ssot_effective_limits: SSOT 소비 헬퍼(재계산 금지·zone 미매칭 무주입).
 (6) design_v61 캐시 핑거프린트: far_basis/far_reliable 누락 시 근거만 다른 요청이 같은
     캐시열쇠로 충돌하는 오염 차단.

실행: /usr/bin/python3.12 -m pytest tests/test_design_effective_far_ssot.py
"""

from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput
from app.services.land_intelligence.far_tier_service import calc_effective_far

_EMPTY_BASE = {"local_ordinance": {}, "zone_limits": {}, "special_districts": []}


def _generate(zone: str, **kwargs):
    svc = AutoDesignEngineService()
    si = SiteInput(site_area_sqm=1000, zone_code=zone, building_use="공동주택", **kwargs)
    return svc.generate(si)


# ── (0) SSOT 그라운드 트루스 앵커 — 이 값들이 바뀌면 아래 가드 전제도 갱신 필요 ──

def test_ssot_green_zone_effective_far_is_80():
    """far_tier SSOT: 자연녹지 실효 용적률 = 80%(건폐 20%×4층 구조상한 < 법정 100%)."""
    eff = calc_effective_far(_EMPTY_BASE, "자연녹지지역", 1000)
    assert eff["effective_far_pct"] == 80.0
    assert eff["far_basis"] == "구조상한(건폐율×층수)"


# ── (1) 자연녹지: SSOT 주입 시 적용 한도 80% 정직 하향(과대 방지 방향만) ──

def test_green_zone_with_ssot_injection_applies_80():
    eff = calc_effective_far(_EMPTY_BASE, "자연녹지지역", 1000)
    r = _generate(
        "자연녹지지역",
        ordinance_far_percent=eff["effective_far_pct"],
        ordinance_bcr_percent=eff["effective_bcr_pct"],
    )
    al = r.summary["basis"]["applied_limits"]
    assert al["max_far_percent"] == 80.0  # 적용 한도 = min(static 100, SSOT 80) = 80(정직)
    assert al["statutory_max_far_percent"] == 100.0  # static 기본값은 그대로 표기(정직 구분)
    assert r.summary["far_percent"] <= 80.0  # 산출 FAR도 SSOT 실효 이내


# ── (2) SSOT 미주입: 기존 보수 동작 완전 보존(무회귀) ──

def test_green_zone_without_injection_keeps_conservative_baseline():
    """미주입 시 static 12m 높이캡 → 4층·FAR≈80%(결과 근사 정합) — 종전 동작 그대로."""
    r = _generate("자연녹지지역")
    al = r.summary["basis"]["applied_limits"]
    assert al["max_far_percent"] == 100.0  # 적용 한도는 static 그대로(주입 없음 → 클램프 없음)
    assert al["ordinance_far_percent"] is None
    assert r.summary["num_floors"] == 4  # 12m 높이캡 / 3m 층고
    assert r.summary["far_percent"] <= 80.0  # 물리 결과는 구조상한과 근사 정합(기존 특성)
    # 근거 메타 미주입 → None(무날조·기존 표기 불변)
    assert al["far_basis"] is None
    assert al["far_reliable"] is None


# ── (3) 비클램프 지역: SSOT가 static보다 높아도 상향 없음(보수 정책·min-clamp) ──

def test_no_upward_cap_when_ssot_above_static():
    """제2종일반주거: SSOT 실효 250% > static 200% → 적용 한도 200% 유지(가짜 상향 금지)."""
    base = _generate("2R")
    injected = _generate("2R", ordinance_far_percent=250.0)
    al = injected.summary["basis"]["applied_limits"]
    assert al["max_far_percent"] == 200.0  # min(200, 250) = 200 — 상향 불가
    # 산출 수치도 미주입과 동일(비클램프 지역 무영향)
    assert injected.summary["far_percent"] == base.summary["far_percent"]
    assert injected.summary["num_floors"] == base.summary["num_floors"]


# ── (4) far_basis/far_reliable 정직 전파 — applied_limits · rule_trace ──

def test_far_basis_propagates_to_applied_limits():
    r = _generate(
        "자연녹지지역",
        ordinance_far_percent=80.0,
        far_basis="구조상한(건폐율×층수)",
        far_reliable=True,
    )
    al = r.summary["basis"]["applied_limits"]
    assert al["far_basis"] == "구조상한(건폐율×층수)"
    assert al["far_reliable"] is True


def test_far_basis_propagates_to_rule_trace():
    from app.services.cad.rule_trace import build_rule_trace

    svc = AutoDesignEngineService()
    si = SiteInput(
        site_area_sqm=1000, zone_code="자연녹지지역", building_use="공동주택",
        ordinance_far_percent=80.0,
        far_basis="구조상한(건폐율×층수)", far_reliable=True,
    )
    legal = svc.get_legal_limits(si.zone_code)
    effective = svc.compute_effective_site(si)
    mass = svc.compute_optimal_mass(si, effective, legal)
    trace, _rule_set = build_rule_trace(si, legal, mass)
    ord_entry = next(e for e in trace if e["rule_code"] == "지자체_도시계획조례")
    assert ord_entry["applied"]["far_basis"] == "구조상한(건폐율×층수)"
    assert ord_entry["applied"]["far_reliable"] is True
    assert "구조상한(건폐율×층수)" in ord_entry["basis"]  # "조례" 오인 방지 문구


def test_rule_trace_without_basis_keeps_legacy_wording():
    """근거 메타 미주입이면 rule_trace 조례 entry는 종전 모양/문구 그대로(무회귀)."""
    from app.services.cad.rule_trace import build_rule_trace

    svc = AutoDesignEngineService()
    si = SiteInput(
        site_area_sqm=1000, zone_code="2R", building_use="공동주택",
        ordinance_far_percent=180.0,
    )
    legal = svc.get_legal_limits(si.zone_code)
    mass = svc.compute_optimal_mass(si, svc.compute_effective_site(si), legal)
    trace, _ = build_rule_trace(si, legal, mass)
    ord_entry = next(e for e in trace if e["rule_code"] == "지자체_도시계획조례")
    assert "far_basis" not in ord_entry["applied"]  # additive 키는 메타가 올 때만
    assert ord_entry["basis"] == "조례 실효한도(법정 이내로만 적용 — 가짜 상향 금지)"


# ── (5) 페르소나 러너 SSOT 소비 헬퍼 ──

def test_persona_ssot_helper_green_zone():
    from app.services.persona.runner import _ssot_effective_limits

    out = _ssot_effective_limits("자연녹지지역", 1000)
    assert out is not None
    assert out["far"] == 80.0
    assert out["far_basis"] == "구조상한(건폐율×층수)"
    assert out["far_reliable"] is True
    assert out["bcr"] == 20.0


def test_persona_ssot_helper_unmatched_zone_returns_none():
    """축약코드/빈값 등 SSOT 미매칭이면 None → 호출부 무주입(기존 보수 동작 유지·무날조)."""
    from app.services.persona.runner import _ssot_effective_limits

    assert _ssot_effective_limits("2R") is None
    assert _ssot_effective_limits(None) is None
    assert _ssot_effective_limits("") is None


# ── (6) design_v61 캐시 핑거프린트 — far_basis/far_reliable 캐시오염 차단 ──

def test_mass_cache_fingerprint_includes_far_basis():
    from app.routers.design_v61 import BimGenerateRequest, _request_fingerprint

    a = BimGenerateRequest(land_area_sqm=1000, zone_code="자연녹지지역",
                           ordinance_far_pct=80.0, far_basis="구조상한(건폐율×층수)",
                           far_reliable=True)
    b = BimGenerateRequest(land_area_sqm=1000, zone_code="자연녹지지역",
                           ordinance_far_pct=80.0)
    fa, fb = _request_fingerprint(a), _request_fingerprint(b)
    assert fa != fb  # 근거만 다른 요청이 같은 열쇠가 되면 남의 근거 문구가 새는 캐시오염
    assert fa["far_basis"] == "구조상한(건폐율×층수)"
    assert fa["far_reliable"] is True
