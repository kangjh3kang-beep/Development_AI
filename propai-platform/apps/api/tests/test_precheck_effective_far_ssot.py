"""90초진단(precheck) 실효 용적률 SSOT 단일화(WP-U1b) 회귀 테스트.

근본: precheck_service._legal_limits가 과거 applicable_limits_for(min(법정,조례))까지만
적용하고 **구조상한(건폐율×층수)**을 누락해 자연녹지(건폐 20%×4층=80% < 법정 100%)의
적용 용적률(applied_far_pct)을 100%로 과대표시했다 — 90초진단 카드·산출근거 트레이스·
수지밴드 연면적·LLM 요약까지 과대낙관 전파(2026-06-19 산/임야 과대표시 버그클래스).

수정: 실효 용적률을 far_tier_service.calc_effective_far(SSOT — 법정범위→조례→계획→
인센티브→구조상한 계층) 단일경유로 전환. far_basis·far_reliable·structural_cap_pct·
floor_cap 정직 전파. SSOT 실패 시 법정/조례 폴백 + far_reliable=False(정직강등 —
과대값이 '실효'로 라벨되어 부활하지 않음).

★calc_effective_far는 재계산하지 않고 그대로 소비한다(SSOT 진실원천). 이 테스트는
OrdinanceService만 hermetic mock(또는 무주소=조례 미조회)하고 calc_effective_far는
실물을 태워 '90초진단 표면이 정말 SSOT 값(80%)을 소비하는지'를 검증한다 —
수지(feasibility_v2)·종합(comprehensive)·규제(PR#333)·인허가(PR#334) 표면과 교차 일치.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.precheck.precheck_service import (  # noqa: E402
    _area_checks,
    _build_band_module_input,
    _build_evidence,
    _legal_limits,
)


# ──────────────────────────────────────────────────────────────────────────
# (a) 자연녹지 — 실효 용적률 80%(구조상한) 정직 산정
# ──────────────────────────────────────────────────────────────────────────
async def test_natural_green_zone_effective_far_is_80():
    """자연녹지 90초진단 적용 용적률 = 80%(구조상한). 100% 과대표시 회귀 방지."""
    legal = await _legal_limits("자연녹지지역")
    assert legal["applied_far_pct"] == 80.0, "자연녹지 적용 용적률은 구조상한 80%여야 한다(100% 과대 금지)"
    assert legal["far_basis"] == "구조상한(건폐율×층수)"
    assert legal["structural_cap_pct"] == 80.0
    assert legal["floor_cap"] == 4
    assert legal["far_reliable"] is True
    # 법정상한(프론트 '법정 한도' 칩 계약)은 정직 보존 — 실효로 덮어쓰지 않는다.
    assert legal["far_pct"] == 100
    assert legal["applied_bcr_pct"] == 20.0
    # far_source가 '법정상한 적용' 문구로 80% 값과 모순되지 않게 정직 갱신됐는지.
    assert "구조상한" in legal["far_source"]


async def test_natural_green_ordinance_cannot_inflate_above_structural_cap(monkeypatch):
    """조례 effective_far=100이 실려와도 구조상한 80%가 최종 상한(과대낙관 차단)."""
    import app.services.land_intelligence.ordinance_service as ordinance_module

    async def _fake_ordinance(self, address, zone_type, force_refresh=False, pnu=None, **_kwargs):
        return {"effective_far": 100, "effective_bcr": 20, "ordinance_far": 100,
                "ordinance_bcr": 20, "source": "지자체 도시계획조례", "sigungu": "용인시"}

    monkeypatch.setattr(
        ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance
    )
    legal = await _legal_limits("자연녹지지역", "경기도 용인시 처인구 어딘가 산 12")
    assert legal["ordinance_confirmed"] is True
    assert legal["applied_far_pct"] == 80.0
    assert legal["far_basis"] == "구조상한(건폐율×층수)"


# ──────────────────────────────────────────────────────────────────────────
# (b) 층수클램프 없는 지역 — 무영향(안 낮아짐)
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "zone_type, expected_far",
    [("제2종일반주거지역", 250.0), ("일반상업지역", 1300.0)],
)
async def test_non_clamped_zones_unaffected(zone_type, expected_far):
    """층수제한 없는 지역은 구조상한 None — 적용 용적률이 낮아지지 않는다."""
    legal = await _legal_limits(zone_type)
    assert legal["applied_far_pct"] == expected_far, (
        f"{zone_type} 적용 용적률은 {expected_far}%로 유지돼야 한다"
    )
    assert legal["structural_cap_pct"] is None
    assert legal["floor_cap"] is None
    assert legal["far_basis"] == "법정/조례"
    assert legal["far_reliable"] is True
    # 기존 4키 계약(bcr_pct/far_pct/height_m/source) 보존 — 프론트 무회귀.
    for k in ("bcr_pct", "far_pct", "height_m", "source"):
        assert k in legal


# ──────────────────────────────────────────────────────────────────────────
# (c) SSOT 실패 — 정직강등(과대값이 '실효'로 라벨되어 부활 금지)
# ──────────────────────────────────────────────────────────────────────────
async def test_ssot_failure_honest_degrade(monkeypatch):
    """calc_effective_far 실패 시: 법정/조례 폴백 유지 + far_reliable=False +
    far_basis 미표기(폴백값을 '실효/구조상한'으로 라벨하지 않음) — 침묵 승격 금지."""
    import app.services.land_intelligence.far_tier_service as far_tier_module

    def _boom(*args, **kwargs):
        raise RuntimeError("SSOT 산정 실패(모의)")

    monkeypatch.setattr(far_tier_module, "calc_effective_far", _boom)
    legal = await _legal_limits("자연녹지지역")
    # 폴백은 applicable_limits_for(법정→조례→계획→구조상한 4계층) 경로이되, 신뢰도·근거로
    # calc_effective_far(SSOT) 미경유(='실효' 확정 아님)를 정직 표기.
    # ★결함 고정 교정(2026-07-23, QA 레인A): applicable_limits_for 자체에 구조상한(건폐
    # 20%×4층=80%) 계층이 승격되어, calc_effective_far가 실패해도 이 폴백값은 80이다(100이
    # 아님) — SSOT 실패 시에도 과대표시가 아닌 물리적 실질상한이 유지되는 안전측 개선.
    # structural_cap_pct/far_basis는 precheck_service가 calc_effective_far 성공 시에만 채우는
    # 필드라 SSOT 실패 시 여전히 None(아래 두 단언 불변 — 계층 소스가 다름).
    assert legal["applied_far_pct"] == 80
    assert legal["far_reliable"] is False
    assert legal["far_basis"] is None
    assert legal["structural_cap_pct"] is None
    # 산출근거 트레이스도 '법정 상한' 라벨로만 표기(실효 라벨 사칭 금지).
    ev = _build_evidence(legal=legal, area_checks=[], legal_refs=[], area_sqm=1000.0)
    ev_far = next(e for e in ev if e["id"] == "ev_far")
    assert ev_far["formula"].startswith("법정 용적률 상한")


# ──────────────────────────────────────────────────────────────────────────
# 하류 소비처 — 산출근거 트레이스·면적체크·수지밴드 연면적이 SSOT 값을 소비
# ──────────────────────────────────────────────────────────────────────────
async def test_evidence_trace_shows_structural_cap():
    """자연녹지 산출근거: min() 인자에 구조상한 정직 나열 + 연면적 800㎡(1,000㎡ 과대 금지)."""
    legal = await _legal_limits("자연녹지지역")
    ev = _build_evidence(legal=legal, area_checks=[], legal_refs=[], area_sqm=1000.0)
    ev_far = next(e for e in ev if e["id"] == "ev_far")
    assert "구조상한" in ev_far["formula"]
    assert ev_far["result"] == "80%"
    ev_buildable = next(e for e in ev if e["id"] == "ev_buildable")
    assert ev_buildable["result"] == "800㎡"


async def test_area_checks_use_effective_far():
    """면적체크 '연면적 최대' 안내가 실효 80% 기준(800㎡) — 법정 100%(1,000㎡) 과대 금지."""
    legal = await _legal_limits("자연녹지지역")
    checks = _area_checks(1000.0, legal)
    far_check = next(c for c in checks if c["rule"] == "용적률")
    assert "800㎡" in far_check["detail"]
    assert "1,000㎡" not in far_check["detail"]
    # 법정과 다르면 산정근거+법정상한을 정직 병기.
    assert "구조상한" in far_check["detail"]
    assert "100%" in far_check["detail"]


async def test_band_module_input_consumes_effective_far():
    """수지밴드 연면적 = 대지면적 × min(실효 80%, 유형 일반 FAR) — 법정 100% 기준 과대 금지."""
    legal = await _legal_limits("자연녹지지역")
    svc, inp = await _build_band_module_input(
        best_code="M06", zone_type="자연녹지지역", legal=legal,
        area_sqm=1000.0, address="경기도 용인시 처인구 어딘가 산 12",
        official_price_per_sqm=1_000_000,
    )
    typical = svc._get_type_typical_far("M06")
    expected_gfa = 1000.0 * min(80.0, typical) / 100.0
    assert inp.total_gfa_sqm == expected_gfa
    # 회귀 핵심: 법정 100% 기준 연면적(1,000㎡ 또는 그 이상)으로 커지면 안 된다.
    assert inp.total_gfa_sqm <= 800.0
