"""T2/T3 dead-path 배선 계약 테스트 — comprehensive 경로가 조례 경사도·산림청 임목축적을 실연결.

#162가 resolve_slope_criteria(T2)·get_forest_facts(T3)를 만들었으나 프로덕션 호출처가
0건(dead-path)이었다. 본 테스트는 종합분석(comprehensive) 경로의 조회 헬퍼가
  - 임야/산지 후보만 조회하고(비후보는 현행 지연·동작 100% 보존),
  - 실패·미프로비저닝을 전부 None(graceful·무날조 정직 게이트)으로 처리하며,
  - 두 값을 detect_special_parcel에 전달만 하고(developability 완화 없음),
  - 실제 detect_special_parcel이 그 값으로 forest_preliminary_assessment(예비판정)를
    채우는지(=화면 응답에 도달)를 검증한다.
원칙(비협상): 전달 데이터 없으면 None=현행 동일(additive), 게이트(NEEDS_OFFICIAL_SURVEY) 불변.
"""

from __future__ import annotations

from typing import Any

from app.services.land_intelligence.comprehensive_analysis_service import (
    _detect_special_parcel_compat,
    _fetch_forest_data,
    _fetch_slope_criteria,
)
from app.services.zoning.special_parcel import detect_special_parcel

_FOREST_INPUT = {"land_category": "임야", "special_districts": []}
_ORDINARY_INPUT = {"land_category": "대", "special_districts": []}


# ── T3: 산림청 임목축적 조회 — 후보만·동기함수 스레드 실행·graceful ──


async def test_fetch_forest_data_for_candidate(monkeypatch):
    calls: list[str] = []

    def _fake_facts(pnu: str) -> dict[str, Any]:
        calls.append(pnu)
        return {
            "입목축적_per_ha": 120.0,
            "관할평균_입목축적_per_ha": 100.0,
            "산지구분": "준보전산지",
            "source": "forest.go.kr",
        }

    import app.integrations.forest_service_client as fsc

    monkeypatch.setattr(fsc, "get_forest_facts", _fake_facts)
    out = await _fetch_forest_data("4211010100100010000", _FOREST_INPUT)
    assert calls == ["4211010100100010000"]
    assert out["입목축적_per_ha"] == 120.0


async def test_fetch_forest_data_skips_non_candidate(monkeypatch):
    # ★raise가 아니라 호출추적으로 검증 — SUT의 broad except가 AssertionError를 삼켜
    #   후보게이트가 깨져도 raise 방식은 false-secure(항상 통과)이기 때문.
    calls: list[str] = []

    def _tracker(pnu: str) -> dict[str, Any]:
        calls.append(pnu)
        return {"입목축적_per_ha": 1.0}

    import app.integrations.forest_service_client as fsc

    monkeypatch.setattr(fsc, "get_forest_facts", _tracker)
    assert await _fetch_forest_data("1168010100100010000", _ORDINARY_INPUT) is None
    assert calls == []  # 비후보 → 조회 자체가 일어나지 않아야 한다


async def test_fetch_forest_data_none_pnu():
    assert await _fetch_forest_data(None, _FOREST_INPUT) is None
    assert await _fetch_forest_data("   ", _FOREST_INPUT) is None


async def test_fetch_forest_data_graceful_on_failure(monkeypatch):
    def _boom(pnu: str):  # noqa: ANN202
        raise RuntimeError("산림청 API 장애")

    import app.integrations.forest_service_client as fsc

    monkeypatch.setattr(fsc, "get_forest_facts", _boom)
    assert await _fetch_forest_data("42110", _FOREST_INPUT) is None


# ── T2: 조례 경사도 기준 조회 — 후보만·법제처 API·graceful ──


class _FakeOrdinanceService:
    """resolve_slope_criteria만 흉내내는 경량 대역(무인자 생성자)."""

    last_sigungu: str | None = None

    async def resolve_slope_criteria(self, sigungu, force_refresh: bool = False):  # noqa: ANN001
        _FakeOrdinanceService.last_sigungu = sigungu
        return {
            "slope_deg": 20.0,
            "ordinance_name": f"{sigungu} 도시계획 조례",
            "verified": "api_parsed",
        }


async def test_fetch_slope_criteria_for_candidate(monkeypatch):
    import app.services.land_intelligence.ordinance_service as os_mod

    _FakeOrdinanceService.last_sigungu = None
    monkeypatch.setattr(os_mod, "OrdinanceService", _FakeOrdinanceService)
    monkeypatch.setattr(os_mod, "resolve_ordinance_region", lambda addr: "용인시")

    out = await _fetch_slope_criteria("경기도 용인시 처인구 산 1", _FOREST_INPUT)
    assert _FakeOrdinanceService.last_sigungu == "용인시"
    assert out["slope_deg"] == 20.0
    assert out["verified"] == "api_parsed"


async def test_fetch_slope_criteria_skips_non_candidate(monkeypatch):
    # ★raise가 아니라 호출추적으로 검증(broad except가 AssertionError를 삼키는 false-secure 방지).
    import app.services.land_intelligence.ordinance_service as os_mod

    calls: list[str] = []

    class _Tracker:
        async def resolve_slope_criteria(self, sigungu, force_refresh: bool = False):  # noqa: ANN001
            calls.append(sigungu)
            return {"slope_deg": 20.0}

    monkeypatch.setattr(os_mod, "OrdinanceService", _Tracker)
    monkeypatch.setattr(os_mod, "resolve_ordinance_region", lambda addr: "서울특별시")
    assert await _fetch_slope_criteria("서울 강남구 역삼동 1", _ORDINARY_INPUT) is None
    assert calls == []  # 비후보 → 조례 조회 자체가 일어나지 않아야 한다


async def test_fetch_slope_criteria_none_when_no_sigungu(monkeypatch):
    import app.services.land_intelligence.ordinance_service as os_mod

    monkeypatch.setattr(os_mod, "resolve_ordinance_region", lambda addr: None)
    assert await _fetch_slope_criteria("불명확 주소", _FOREST_INPUT) is None


async def test_fetch_slope_criteria_graceful_on_failure(monkeypatch):
    import app.services.land_intelligence.ordinance_service as os_mod

    class _Boom:
        async def resolve_slope_criteria(self, *a, **k):  # noqa: ANN002, ANN003
            raise RuntimeError("법제처 API 장애")

    monkeypatch.setattr(os_mod, "OrdinanceService", _Boom)
    monkeypatch.setattr(os_mod, "resolve_ordinance_region", lambda addr: "용인시")
    assert await _fetch_slope_criteria("경기도 용인시 산 1", _FOREST_INPUT) is None


# ── 호환 호출: forest_data/slope_criteria를 지원 시그니처에만 전달 ──


def test_compat_passes_forest_and_slope_to_new_signature(monkeypatch):
    received: dict[str, Any] = {}

    def _fake_detect(result, *, terrain_facts=None, forest_data=None, slope_criteria=None):  # noqa: ANN001
        received.update(
            terrain_facts=terrain_facts, forest_data=forest_data, slope_criteria=slope_criteria
        )
        return {"is_special": True, "developability": "NEEDS_OFFICIAL_SURVEY"}

    import app.services.zoning.special_parcel as sp_mod

    monkeypatch.setattr(sp_mod, "detect_special_parcel", _fake_detect)
    terrain = {"평균경사도_pct": 18.0, "최대경사도_pct": 30.0, "source": "SRTM30_DEM"}
    forest = {"입목축적_per_ha": 120.0, "관할평균_입목축적_per_ha": 100.0}
    slope = {"slope_deg": 20.0, "ordinance_name": "용인시 조례", "verified": "api_parsed"}
    out = _detect_special_parcel_compat(_FOREST_INPUT, terrain, forest, slope)
    assert received == {"terrain_facts": terrain, "forest_data": forest, "slope_criteria": slope}
    # developability pass-through — 배선이 게이트를 절대 완화하지 않는다.
    assert out["developability"] == "NEEDS_OFFICIAL_SURVEY"


def test_compat_drops_unsupported_kwargs_on_legacy_signature(monkeypatch):
    """E-gate 미착지(구 시그니처: terrain_facts만)면 forest/slope는 조용히 드롭(TypeError 없음)."""
    received: dict[str, Any] = {}

    def _legacy_detect(result, terrain_facts=None):  # noqa: ANN001
        received["terrain_facts"] = terrain_facts
        return {"is_special": True, "developability": "BLOCKED"}

    import app.services.zoning.special_parcel as sp_mod

    monkeypatch.setattr(sp_mod, "detect_special_parcel", _legacy_detect)
    out = _detect_special_parcel_compat(
        _FOREST_INPUT, {"평균경사도_pct": 18.0}, {"입목축적_per_ha": 120.0}, {"slope_deg": 20.0}
    )
    assert received["terrain_facts"] == {"평균경사도_pct": 18.0}
    assert out["developability"] == "BLOCKED"


# ── ★end-to-end: 실제 detect_special_parcel이 배선값으로 예비판정을 채우는가(화면 도달 증명) ──


def test_real_detect_populates_forest_preliminary_assessment():
    """임야 + terrain + slope_criteria(조례) + forest_data(임목축적) → forest_preliminary_assessment
    에 slope(조례기준 적용)·stocking(별표4 150% 비교)이 채워지고, 게이트는 불변."""
    result = {"land_category": "임야", "zone_type": "자연녹지지역"}
    terrain = {"평균경사도_pct": 22.0, "최대경사도_pct": 35.0, "source": "SRTM30_DEM"}
    slope = {"slope_deg": 20.0, "ordinance_name": "용인시 도시계획 조례", "verified": "api_parsed"}
    forest = {
        "입목축적_per_ha": 180.0,
        "관할평균_입목축적_per_ha": 100.0,  # 180% → 150% 초과 → 예비 초과 판정
        "산지구분": "준보전산지",
        "source": "forest.go.kr",
    }
    out = detect_special_parcel(
        result, terrain_facts=terrain, forest_data=forest, slope_criteria=slope
    )
    assert out is not None
    # ★게이트 불변 — 배선은 예비판정만 가산, 확정판정 완화 없음.
    assert out["developability"] == "NEEDS_OFFICIAL_SURVEY"
    pa = out.get("forest_preliminary_assessment")
    assert isinstance(pa, dict)
    # 경사도 예비판정: 조례 기준(20°)이 국가기준(25°) 대신 적용됐는지.
    assert pa["slope"] is not None
    assert pa["slope"]["criteria_deg"] == 20.0
    assert "조례" in pa["slope"]["criteria_source"]
    # 임목축적 예비판정: 180/100=180% → 별표4 150% 초과.
    assert pa["stocking"] is not None
    assert pa["stocking"]["입목축적_비율_pct"] == 180.0
    assert "초과" in pa["stocking"]["judgment"]


async def test_analyze_wires_forest_assessment_into_response(monkeypatch):
    """★관통(글루) 통합: analyze()가 3종 조회→compat→result['special_parcel']까지 흘려
    forest_preliminary_assessment가 실제 응답에 실리는지 검증(화면 도달 증명).

    무거운 외부 섹션(실거래·입지·원장 prior)은 mock — 검증 대상은 배선 글루뿐.
    """
    from app.services.land_intelligence import comprehensive_analysis_service as mod

    service = mod.ComprehensiveAnalysisService()

    async def _fake_base(address):  # noqa: ANN001
        return {
            "address": address,
            "pnu": "4211010100100010000",
            "zone_type": "자연녹지지역",
            "land_register": {"area_sqm": 1000.0, "land_category": "임야"},
            "special_districts": [],
            "warnings": [],
        }

    monkeypatch.setattr(service.land_info, "collect_comprehensive", _fake_base)
    # 3종 조회를 canned 값으로 대체(외부 API 없이 배선 글루만 검증).
    monkeypatch.setattr(mod, "_fetch_terrain_facts",
                        lambda *a, **k: _async({"평균경사도_pct": 22.0, "최대경사도_pct": 35.0, "source": "SRTM30_DEM"}))
    monkeypatch.setattr(mod, "_fetch_slope_criteria",
                        lambda *a, **k: _async({"slope_deg": 20.0, "ordinance_name": "용인시 조례", "verified": "api_parsed"}))
    monkeypatch.setattr(mod, "_fetch_forest_data",
                        lambda *a, **k: _async({"입목축적_per_ha": 180.0, "관할평균_입목축적_per_ha": 100.0, "산지구분": "준보전산지", "source": "forest.go.kr"}))
    # 무거운 외부 섹션·원장 prior 무력화(배선과 무관).
    monkeypatch.setattr(service, "_research_transactions", lambda base: _async({}))
    monkeypatch.setattr(service, "_analyze_location", lambda base: _async({}))
    import app.services.ledger.prior_context as pc
    monkeypatch.setattr(pc, "load_prior", lambda **k: _async(None))

    result = await service.analyze("경기도 용인시 처인구 산 1", with_senior=False)

    sp = result.get("special_parcel")
    assert isinstance(sp, dict)
    assert sp["developability"] == "NEEDS_OFFICIAL_SURVEY"  # 게이트 불변
    pa = sp.get("forest_preliminary_assessment")
    assert isinstance(pa, dict)
    assert pa["slope"]["criteria_deg"] == 20.0  # 조례 경사도 적용(화면 도달)
    assert pa["stocking"]["입목축적_비율_pct"] == 180.0  # 임목축적 150% 비교(화면 도달)


async def _async(value):
    """monkeypatch용 코루틴 팩토리 — 호출 시 즉시 value를 반환하는 코루틴."""
    return value


def test_real_detect_slope_falls_back_to_national_when_no_ordinance():
    """조례 경사도 미확보(None) → 국가기준 별표4 25°로 폴백 + 조례 별도확인 캐비앳(무날조)."""
    result = {"land_category": "임야", "zone_type": "자연녹지지역"}
    terrain = {"평균경사도_pct": 22.0, "최대경사도_pct": 35.0, "source": "SRTM30_DEM"}
    out = detect_special_parcel(result, terrain_facts=terrain, slope_criteria=None)
    pa = out["forest_preliminary_assessment"]
    assert pa["slope"]["criteria_deg"] == 25.0
    assert any("조례" in c for c in pa["slope"].get("caveats", []))
    # forest_data 미확보 → 150% 비교는 정직 스킵(비율 날조 금지).
    assert pa["stocking"] is None
    assert "미확보" in pa.get("stocking_skip_reason", "")
