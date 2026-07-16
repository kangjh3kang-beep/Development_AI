"""실효 용적률 교차표면 패리티 계약 테스트(WP-U4) — CI 상설 재발 단선.

배경: 실효FAR 버그클래스(구조상한 누락·날조 기본값)가 4개 표면에서 연쇄 발견·봉합됐다 —
규제(PR#333)·인허가(PR#334)·90초진단(PR#336)·파이프라인(PR#337). 기존 정합 표면은
수지(feasibility_service_v2)·종합분석(comprehensive). 개별 표면 회귀 테스트만으로는
'새 표면 추가'나 '리팩토링발 재계산 부활'을 막지 못한다 — 이 파일은 **실효FAR를 노출하는
모든 표면이 SSOT(far_tier_service.calc_effective_far) 산출과 일치해야 통과**하는 계약을
CI에 상설한다(어느 표면이든 SSOT와 발산하면 이 테스트가 먼저 깨진다).

패리티 정의(★하드코딩 80 금지):
- 기대값 = calc_effective_far(실물 SSOT)를 테스트 안에서 실제 실행한 산출값.
  SSOT 산식이 진화해도 '표면 산출 == SSOT 산출' 패리티 정의가 그대로 유지된다.
- 단, 자연녹지=80% 상수 어서션 1개는 SSOT 자체의 회귀 앵커로 병행한다
  (SSOT가 조용히 80이 아닌 값을 내기 시작하면 패리티는 전 표면이 함께 이동해
  통과해버리므로, 절대값 앵커 1개가 그 침묵 드리프트를 잡는다).

hermetic 원칙(무목업 아님 — SSOT·표면 로직은 실물):
- 외부 I/O(AutoZoning 주소해석·Ordinance 조례조회·LandInfo 수집·LLM·시니어)만 mock.
- calc_effective_far와 각 표면의 소비 로직은 실물을 태운다 — #333/#334/#336/#337
  기준선 테스트(test_regulation_analysis_wiring / test_permit_effective_far_ssot /
  test_precheck_effective_far_ssot / pipeline/test_pipeline_effective_far_ssot)와
  동일한 mock 패턴을 재사용한다.

새 표면 추가법(1줄 잠금): 아래 `_surface_*` 러너 함수 1개를 작성하고
SURFACES 레지스트리에 항목 1줄을 추가하면 zone 3종 × 신규 표면 패리티가 자동으로 잠긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.services.land_intelligence.far_tier_service import calc_effective_far

# ──────────────────────────────────────────────────────────────────────────
# zone 픽스처 3종 — 구조상한 바인딩 1종 + 비클램프 2종
#   zone_limits shape = AutoZoningService.build_zone_limits(법정 페이로드) 기준
#   (#334 기준선 테스트와 동일 형태).
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ZoneCase:
    zone_type: str
    zone_limits: dict = field(hash=False)
    land_area: float = 1000.0


NATURAL_GREEN = ZoneCase("자연녹지지역", {"max_bcr_pct": 20, "max_far_pct": 100})
# 자연녹지: 건폐 20% × 4층(별표17 두문) = 구조상한 80% < 법정 100% → 구조상한 바인딩.
R2_RESIDENTIAL = ZoneCase("제2종일반주거지역", {"max_bcr_pct": 60, "max_far_pct": 250})
COMMERCIAL = ZoneCase("일반상업지역", {"max_bcr_pct": 80, "max_far_pct": 1300})
# 제2종일반주거·일반상업: 층수클램프 없음 → 구조상한 None(법정/조례 그대로, 비클램프).

ZONE_CASES = [NATURAL_GREEN, R2_RESIDENTIAL, COMMERCIAL]


def _ssot_base(case: ZoneCase) -> dict:
    """SSOT 입력 base — 표면들이 hermetic mock 하에서 실제로 구성하게 되는 것과 동일한
    페이로드(조례 미확보 {} — 각 표면 러너의 Ordinance mock도 {}를 반환해 입력 정합)."""
    return {
        "zone_limits": dict(case.zone_limits),
        "special_districts": [],
        "local_ordinance": {},
    }


def _ssot(case: ZoneCase) -> dict:
    """기대값 = SSOT 실물 산출(하드코딩 금지 — SSOT 변경 시에도 패리티 정의 유지)."""
    return calc_effective_far(_ssot_base(case), case.zone_type, case.land_area)


# far_basis를 응답에 노출하지 않는 표면(수지 Top3)의 정직 센티널 — None(값 없음)과 구분.
NOT_EXPOSED = object()


# ──────────────────────────────────────────────────────────────────────────
# 표면 러너 — 각 표면을 hermetic 실행해 {far, basis[, tolerance]}를 반환한다.
#   far: 표면이 최종 노출한 실효 용적률(%) / basis: 표면이 노출한 far_basis
#   tolerance: 표면이 표기 반올림을 하는 경우의 허용오차(기본 0 = 완전일치)
# ──────────────────────────────────────────────────────────────────────────


async def _surface_regulation(monkeypatch, case: ZoneCase, ssot: dict) -> dict[str, Any]:
    """① 규제분석(regulation_analysis_service, PR#333 봉합 표면).

    이 표면의 SSOT 배선은 생산자(land_info_service.collect_comprehensive Phase4 —
    land_info_service.py:652에서 calc_effective_far 직접 대입)가 담당하고, 규제 서비스는
    comp["effective_far"]를 **소비만** 한다. 여기서는 수집기를 hermetic mock하되 주입값을
    '이 테스트가 방금 실행한 실물 SSOT 산출(ssot)'로 넣어(하드코딩 사본 아님), 소비 경로가
    SSOT 값을 재계산·법정 폴백 없이 최종 표면(limits.far.effective)까지 그대로 나르는지 검증한다.
    """
    import app.services.land_intelligence.land_info_service as land_info_module
    from app.services.regulation.regulation_analysis_service import RegulationAnalysisService

    comp = {
        "zone_type": case.zone_type,
        "zone_type_secondary": "",
        "pnu": "PARITY-PNU-0001",
        "coordinates": {"lat": 37.3, "lng": 127.1},
        "land_area_sqm": case.land_area,
        "land_register": {"area_sqm": case.land_area, "land_category": "대"},
        "land_characteristics": {},
        "land_use_plan": {"districts": [case.zone_type]},
        "special_districts": [],
        "zone_limits": dict(case.zone_limits),
        "local_ordinance": {},
        "effective_far": ssot,  # ★실물 SSOT 산출 주입(생산자 배선은 :652 직대입이라 항등)
    }

    async def _fake_comprehensive(self, address, pnu=None):  # noqa: ANN001
        return comp

    monkeypatch.setattr(
        land_info_module.LandInfoService, "collect_comprehensive", _fake_comprehensive,
    )
    res = await RegulationAnalysisService().analyze(
        "패리티 검증용 주소 1-1", pnu=None, use_llm=False, with_senior=False,
    )
    return {
        "far": res["limits"]["far"]["effective"],
        # 단일필지(_show_structural=True)는 passthrough effective_far.far_basis 노출.
        "basis": (res.get("effective_far") or {}).get("far_basis"),
    }


async def _surface_permit(monkeypatch, case: ZoneCase, ssot: dict) -> dict[str, Any]:
    """② 인허가분석(permit_analysis_service._enrich_site, PR#334 봉합 표면).

    AutoZoning·Ordinance만 hermetic mock — _enrich_site가 실물 calc_effective_far를
    단일경유해 site.max_far에 SSOT 값을 싣는지 검증(#334 기준선 테스트와 동일 패턴).
    """
    import app.services.land_intelligence.ordinance_service as ordinance_module
    import app.services.zoning.auto_zoning_service as auto_zoning_module
    from app.services.permit.permit_analysis_service import PermitAnalysisService

    async def _fake_analyze(self, address):  # noqa: ANN001
        return {
            "zone_type": case.zone_type,
            "zone_limits": dict(case.zone_limits),
            "land_area_sqm": case.land_area,
            "land_category": None,
            "special_districts": [],
        }

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}

    monkeypatch.setattr(auto_zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance)

    site = await PermitAnalysisService()._enrich_site("패리티 검증용 주소 1-1", {})
    return {"far": site["max_far"], "basis": site["far_basis"]}


async def _surface_precheck(monkeypatch, case: ZoneCase, ssot: dict) -> dict[str, Any]:
    """③ 90초진단(precheck_service._legal_limits, PR#336 봉합 표면).

    무주소 호출 = 조례 미조회(외부 I/O 없음) — _legal_limits가 실물 calc_effective_far를
    단일경유해 applied_far_pct에 SSOT 값을 싣는지 검증(#336 기준선 테스트와 동일 호출 형태).
    """
    from app.services.precheck.precheck_service import _legal_limits

    legal = await _legal_limits(case.zone_type)
    return {"far": legal["applied_far_pct"], "basis": legal["far_basis"]}


async def _surface_pipeline(monkeypatch, case: ZoneCase, ssot: dict) -> dict[str, Any]:
    """④ 파이프라인 부지분석(project_pipeline._run_site_analysis, PR#337 봉합 표면).

    외부 수집(LandInfo/Ordinance)·LLM 해석만 hermetic mock — 파이프라인이 실물
    calc_effective_far를 단일경유해 stage data zoning.effective_far에 SSOT 값을 싣는지
    검증(#337 기준선 테스트와 동일 하네스).
    """
    import app.services.land_intelligence.land_info_service as land_info_module
    import app.services.land_intelligence.ordinance_service as ordinance_module
    from app.services.pipeline.project_pipeline import (
        PipelineStage,
        PipelineState,
        ProjectPipeline,
        StageResult,
    )

    async def _fake_comprehensive(self, address, pnu=None):  # noqa: ANN001
        return {}

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}

    async def _noop_ai(self, state):  # noqa: ANN001 — LLM 해석은 본 계약과 무관(네트워크 차단)
        return None

    monkeypatch.setattr(
        land_info_module.LandInfoService, "collect_comprehensive", _fake_comprehensive,
    )
    monkeypatch.setattr(ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance)
    monkeypatch.setattr(ProjectPipeline, "_attach_site_ai", _noop_ai)

    pipeline = ProjectPipeline()
    state = PipelineState(address="패리티 검증용 주소 1-1")
    state.project_id = ""  # DB 자동저장 경로 미진입(hermetic)
    state.stages["site_analysis"] = StageResult(stage=PipelineStage.SITE_ANALYSIS)
    await pipeline._run_site_analysis(
        state,
        {"site_data": {"zone_type": case.zone_type, "land_area_sqm": case.land_area}},
    )
    zoning = state.stages["site_analysis"].data["zoning"]
    return {"far": zoning["effective_far"], "basis": zoning["far_basis"]}


async def _surface_feasibility_top3(monkeypatch, case: ZoneCase, ssot: dict) -> dict[str, Any]:
    """⑤-a 수지 Top3 추천(feasibility_service_v2.auto_recommend_top3 — 기존 정합 표면).

    AutoZoning·Ordinance만 hermetic mock(use_llm/with_senior=False) — Top3가 실물
    calc_effective_far를 단일경유해 FAR→GFA→ROI 전 계단에 실제 사용한 실효 용적률을
    effective_far_pct로 노출하는지 검증한다. 표면이 round(x, 1) 표기 반올림을 하므로
    허용오차 0.05(반올림 최대오차)만 인정한다 — far_basis는 이 응답에 미노출(정직 센티널).
    """
    import app.services.land_intelligence.ordinance_service as ordinance_module
    import app.services.zoning.auto_zoning_service as auto_zoning_module
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    async def _fake_analyze(self, address):  # noqa: ANN001
        return {
            "zone_type": case.zone_type,
            "zone_limits": dict(case.zone_limits),
            "land_area_sqm": case.land_area,
            "official_price_per_sqm": 3_000_000,
            "special_districts": [],
            "land_category": "대",
        }

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}

    monkeypatch.setattr(auto_zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance)

    out = await FeasibilityServiceV2().auto_recommend_top3(
        address="패리티 검증용 주소 1-1",
        land_area_sqm=case.land_area,
        use_llm=False,
        with_senior=False,
    )
    assert "error" not in out, f"Top3가 산출돼야 패리티 검증 가능 — {out.get('error')}"
    assert out.get("far_reliable") is True, "법정상한 확보 케이스 — 가정치(250) 경로면 안 됨"
    return {"far": out["effective_far_pct"], "basis": NOT_EXPOSED, "tolerance": 0.05}


async def _surface_comprehensive_delegate(
    monkeypatch, case: ZoneCase, ssot: dict,
) -> dict[str, Any]:
    """⑤-b 종합분석(comprehensive_analysis_service — 기존 정합 표면) 소비 계약.

    ★정직 명시(무엇을 검증하는가): 종합분석 analyze() 전체는 실행하지 않는다(외부수집·
    LLM·원장·7섹션 — hermetic 구성이 과도하게 무겁다). 대신 다음 2가지로 소비 계약을 잠근다.
    (1) 종합 표면의 실효FAR 산정 경로 `_calc_effective_far`가 SSOT calc_effective_far와
        **전체 dict 동일**(위임 — 부분 복제·변형·독자 재계산 없음)임을 실행으로 확인.
    (2) analyze():427의 소비 지점 `sec1 = base.get("effective_far") or
        self._calc_effective_far(base, ...)`은 두 피연산자가 모두 calc_effective_far 산물이다
        — base["effective_far"]는 collect_comprehensive Phase4(land_info_service.py:652)가
        같은 SSOT로 직대입 생산한다. 따라서 (1)의 위임 항등이 지켜지는 한 종합 표면의
        실효FAR 원천은 SSOT 단일이다. (수지 표면은 ⑤-a에서 실물 전체 실행으로 별도 검증)
    """
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    sec1 = ComprehensiveAnalysisService()._calc_effective_far(
        _ssot_base(case), case.zone_type, case.land_area,
    )
    # 위임 항등 — 값 몇 개가 아니라 산출 전체가 SSOT와 동일해야 한다(변형·누락 금지).
    assert sec1 == ssot, "종합 표면 _calc_effective_far는 SSOT 위임 항등이어야 한다"
    return {"far": sec1["effective_far_pct"], "basis": sec1["far_basis"]}


# ──────────────────────────────────────────────────────────────────────────
# ★표면 레지스트리 — 새 실효FAR 표면은 러너 작성 후 여기 1줄 추가로 잠근다.
# ──────────────────────────────────────────────────────────────────────────
SURFACES: list[tuple[str, Any]] = [
    ("regulation-규제분석(PR#333)", _surface_regulation),
    ("permit-인허가분석(PR#334)", _surface_permit),
    ("precheck-90초진단(PR#336)", _surface_precheck),
    ("pipeline-부지분석(PR#337)", _surface_pipeline),
    ("feasibility-수지Top3", _surface_feasibility_top3),
    ("comprehensive-종합분석 위임계약", _surface_comprehensive_delegate),
]


# ──────────────────────────────────────────────────────────────────────────
# SSOT 자체 회귀 앵커 — 자연녹지 80% 상수 1개(패리티의 침묵 동반이동 차단)
# ──────────────────────────────────────────────────────────────────────────


def test_ssot_regression_anchor_natural_green_is_80():
    """SSOT 앵커: 자연녹지 실효 용적률 = 80%(건폐 20% × 4층 구조상한) 절대값.

    패리티 테스트의 기대값은 SSOT 산출이므로, SSOT가 잘못 바뀌면 전 표면이 '함께'
    이동해 패리티는 통과해버린다 — 이 상수 앵커 1개가 그 침묵 드리프트를 잡는다.
    """
    ssot = _ssot(NATURAL_GREEN)
    assert ssot["effective_far_pct"] == 80.0
    assert ssot["far_basis"] == "구조상한(건폐율×층수)"
    assert ssot["structural_cap_pct"] == 80.0
    assert ssot["floor_cap"] == 4
    assert ssot["national_far_pct"] == 100.0  # 법정상한(라벨)은 정직 보존


# ──────────────────────────────────────────────────────────────────────────
# 패리티 계약 본체 — 표면 × zone 전 조합(6표면 × 3zone = 18케이스)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", ZONE_CASES, ids=[c.zone_type for c in ZONE_CASES])
@pytest.mark.parametrize("surface_id,runner", SURFACES, ids=[s[0] for s in SURFACES])
async def test_effective_far_cross_surface_parity(monkeypatch, surface_id, runner, case):
    """표면 실효 용적률 == SSOT(calc_effective_far) 산출 — 발산 0 계약."""
    ssot = _ssot(case)
    # 패리티 전제: 픽스처 zone은 법정 라벨 매칭이 성공해야 한다(미매칭이면 패리티 정의 불성립).
    assert ssot["effective_far_pct"] is not None, f"{case.zone_type} SSOT 산출 실패(전제 붕괴)"

    observed = await runner(monkeypatch, case, ssot)

    assert observed["far"] is not None, f"[{surface_id}] {case.zone_type} 실효 용적률 미노출"
    tol = float(observed.get("tolerance", 0.0))
    diff = abs(float(observed["far"]) - float(ssot["effective_far_pct"]))
    assert diff <= tol, (
        f"[{surface_id}] {case.zone_type} 실효 용적률 발산 — "
        f"표면={observed['far']} vs SSOT={ssot['effective_far_pct']} (허용오차 {tol})"
    )

    basis = observed.get("basis", NOT_EXPOSED)
    if basis is not NOT_EXPOSED:
        assert basis == ssot["far_basis"], (
            f"[{surface_id}] {case.zone_type} far_basis 발산 — "
            f"표면={basis!r} vs SSOT={ssot['far_basis']!r}"
        )
