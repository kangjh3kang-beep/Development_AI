"""★배선 테스트 — 지배 제약이 **실제 응답에 실려 나가는지** 관통 검증(사통맵 v2 W1).

왜 이 파일이 따로 있는가(2026-07-30 회고):
  직전 세션에 "순수함수만 초록이고 배선을 되돌리면 그대로 통과"한 사례가 4번 있었다.
  test_dominant_constraint.py(순수함수)는 build_for_parcel의 계약만 고정한다 — 그 함수를
  아무도 호출하지 않아도 초록이다. 그래서 여기서 두 실제 소비 경로를 **끝까지** 태운다:

    ① 지도 경로  : POST /zoning/parcel-boundaries → features[].dominant_constraint
    ② 분석 경로  : ComprehensiveAnalysisService.analyze() → result["dominant_constraint"]

hermetic: 외부 I/O(VWorld 지적/토지특성/용도지구, 건축물대장, 조례, DEM, 원장/DB, LLM)만
대역한다 — 지배 제약 판정·severity SSOT·정북일조 산식은 전부 실물을 태운다.
★DB를 요구하지 않는다: CI에 Postgres가 없어 DB 게이트 skip을 쓰면 이 배선 테스트가 CI에서
  항상 건너뛰어져 '가짜 안전'이 된다(원장·prior만 대역해 무DB로 완주시킨다).

라이브 기준 케이스: 호미곶 대보리 산1-1(보전관리지역·임야·군사 통제보호구역+비행안전구역).
"""
from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.asyncio

_PNU = "4711025029000010001"  # 포항시 남구 호미곶면 대보리 산1-1 형태
_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[129.56, 36.07], [129.5604, 36.07], [129.5604, 36.07027],
                     [129.56, 36.07027], [129.56, 36.07]]],
}
# 라이브에서 실제로 관측된 designation 조합(군사 통제보호 = 최고 severity, 비행안전 = 높이제약).
_DISTRICTS = ["군사시설보호구역(통제보호구역)", "비행안전구역(제6구역)"]


# ══════════════════════════════════════════════════════════════════════════
# ① 지도 경로 — /zoning/parcel-boundaries features[].dominant_constraint
# ══════════════════════════════════════════════════════════════════════════
def _stub_boundary_io(
    monkeypatch,
    *,
    districts: list[str],
    zone_type: str,
    jimok: str = "임야",
    ned_districts: list[str] | None = None,
):
    """VWorld·건축물대장·조례를 hermetic 대역. 지배 제약 판정은 실물이 돈다.

    ★R1 HIGH-2: 두 designation 출처를 **API별로 분리**해 대역한다.
      districts     → VWorld UD802/UD803 = 국토계획법 **용도지구·용도구역**
                      (고도지구·경관지구·방화지구·개발제한구역 등)
      ned_districts → NED getLandUseAttr = **개별법 지역지구**
                      (군사시설보호구역·통제보호구역·비행안전구역·상수원보호구역 등)
    종전 스텁은 UD802/803 자리에 군사 명칭을 넣어 **그 API가 반환할 수 없는 값**으로 초록을
    만들었다 — 배선(파이프)은 증명되지만 라이브에서는 대표 화면(호미곶 배너)이 비어 있게 된다.
    이제 각 출처가 실제로 낼 수 있는 값만 넣고, 군사 배너는 NED 스텁이 있을 때만 뜨게 고정한다.
    """
    import apps.api.routers.auto_zoning as az
    from apps.api.app.services.external_api.building_registry_service import (
        BuildingRegistryService,
    )
    from apps.api.app.services.external_api.vworld_service import VWorldService
    from apps.api.app.services.land_intelligence.ordinance_service import OrdinanceService

    async def _fake_land_info(self, pnu):  # noqa: ANN001
        return {"geometry": _GEOMETRY, "properties": {"area": 147_078.0}}

    async def _fake_land_characteristics(self, pnu):  # noqa: ANN001
        return {
            "area_sqm": 147_078.0, "zone_type": zone_type, "zone_type_2": None,
            "official_price_per_sqm": 12_000, "land_category": jimok,
            "land_use_situation": None, "terrain_form": None,
        }

    async def _fake_title(self, pnu):  # noqa: ANN001
        return None, "no_data"

    async def _fake_districts(self, pnu):  # noqa: ANN001
        """UD802/UD803 — 용도지구·용도구역만(개별법 지역지구는 이 레이어에 없다)."""
        return [{"name": n} for n in districts]

    async def _fake_land_use_plan(self, pnu):  # noqa: ANN001
        """NED getLandUseAttr — 개별법 지역지구(군사·비행안전·상수원 등)."""
        return [{"district_name": n} for n in (ned_districts or [])]

    async def _fake_ordinance(self, address, zone_type_, force_refresh=False):  # noqa: ANN001
        return {}

    monkeypatch.setattr(VWorldService, "get_land_use_plan", _fake_land_use_plan, raising=True)
    monkeypatch.setattr(VWorldService, "get_land_info", _fake_land_info, raising=True)
    monkeypatch.setattr(
        VWorldService, "get_land_characteristics", _fake_land_characteristics, raising=True,
    )
    monkeypatch.setattr(VWorldService, "get_land_use_districts", _fake_districts, raising=True)
    monkeypatch.setattr(
        BuildingRegistryService, "get_title_with_status_by_pnu", _fake_title, raising=True,
    )
    monkeypatch.setattr(OrdinanceService, "get_ordinance_limits", _fake_ordinance, raising=True)
    return az


async def test_parcel_boundaries_exposes_dominant_constraint(monkeypatch):
    """★배선①: 지도 경계 응답의 각 feature가 dominant_constraint를 싣고 나온다.

    호미곶 라이브 케이스 — 군사·비행안전은 **NED**(개별법 지역지구)에서 온다.
    """
    az = _stub_boundary_io(
        monkeypatch, districts=[], zone_type="보전관리지역", ned_districts=_DISTRICTS,
    )

    result = await az.parcel_boundaries(az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}]))

    feat = result["features"][0]
    assert "dominant_constraint" in feat, (
        "지도 필지 상세 배너가 소비하는 키가 응답에 없다 — 배선 끊김"
    )
    dc = feat["dominant_constraint"]
    assert dc is not None, "군사 통제보호구역+비행안전구역인데 지배 제약이 None"
    # 헤드라인은 severity 최고인 군사 통제보호구역이어야 한다(SSOT 랭킹이 실제로 작동).
    assert "통제보호구역" in dc["headline"], f"headline이 군사가 아님: {dc['headline']}"
    assert dc["severity"] == "높음"
    # 높이: 비행안전구역은 수치 미보유 → 일부 미반영(정직 표기)
    assert dc["height"] is not None
    assert dc["height"]["incomplete"] is True
    assert dc["height"]["governing_m"] is None, (
        "보전관리지역엔 정북일조가 적용되지 않으므로 숫자가 나오면 날조"
    )
    # 내부 전용 키는 계속 스트립된다(응답 계약 유지 — 기존 회귀 테스트와 동일 규약).
    assert not any(k.startswith("_") for k in feat), (
        f"밑줄 내부키 누출: {sorted(k for k in feat if k.startswith('_'))}"
    )


async def test_parcel_boundaries_residential_gets_numeric_sunlight_height(monkeypatch):
    """★배선①-b: 주거지역은 실측 geometry로 정북일조 숫자가 실제로 채워진다."""
    az = _stub_boundary_io(
        monkeypatch, districts=["고도지구"], zone_type="제2종일반주거지역", jimok="대",
    )

    result = await az.parcel_boundaries(az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}]))

    dc = result["features"][0]["dominant_constraint"]
    assert dc is not None
    h = dc["height"]
    assert h["governing_source"] == "정북일조", f"정북일조 항목 미생성: {h}"
    assert isinstance(h["governing_m"], float) and h["governing_m"] > 0
    # 고도지구는 수치 미보유 → 숫자가 최종이 아님을 반드시 고지.
    assert h["incomplete"] is True


async def test_parcel_boundaries_needs_ned_source_for_military(monkeypatch):
    """★R1 HIGH-2 회귀락: **UD802/803만으로는 군사 배너가 뜨지 않는다**는 사실을 명시 고정.

    지배 제약 입력을 다시 용도지구·용도구역만으로 좁히면(=NED 수집 배선을 되돌리면) 이 테스트가
    실패한다. 종전 스텁은 UD802/803 자리에 군사 명칭을 넣어 이 구조적 갭을 가리고 있었다.
    """
    az = _stub_boundary_io(
        monkeypatch, districts=_DISTRICTS, zone_type="보전관리지역", ned_districts=[],
    )
    only_ud = await az.parcel_boundaries(az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}]))
    # UD802/803에 군사 명칭이 들어오는 상황 자체는 실재하지 않지만, 만약 들어오면 판정은
    # 정상 동작해야 한다(입력원 확장이 판정 로직을 우회하지 않는다는 확인).
    assert only_ud["features"][0]["dominant_constraint"] is not None

    # 실제 분포: 군사는 NED에만 있고 UD802/803은 비어 있다 → NED 수집이 없으면 배너 0건.
    az2 = _stub_boundary_io(
        monkeypatch, districts=[], zone_type="보전관리지역", ned_districts=_DISTRICTS,
    )
    with_ned = await az2.parcel_boundaries(az2.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}]))
    dc = with_ned["features"][0]["dominant_constraint"]
    assert dc is not None and "통제보호구역" in dc["headline"], (
        "NED(개별법 지역지구) 수집이 지배 제약 입력에 도달하지 않는다 — 라이브 배너 무음 소실"
    )


async def test_parcel_boundaries_marks_lookup_failure_as_unverified(monkeypatch):
    """★무음 낙관 차단(배선): 두 출처 모두 하드 실패면 배너가 사라지지 않고 unverified로 뜬다.

    NED는 None(하드 실패)과 [](규제 0건)을 계약으로 구분한다. 그 구분을 여기서 흘리면
    "조회 실패"가 "제약 없는 필지"로 표시돼 사용자가 규제를 확인했다고 착각한다.
    """
    az = _stub_boundary_io(monkeypatch, districts=[], zone_type="보전관리지역", ned_districts=[])
    from apps.api.app.services.external_api.vworld_service import VWorldService

    async def _hard_fail_ned(self, pnu):  # noqa: ANN001
        return None  # 키 미설정·HTTP 실패 — 목록을 확정할 수 없음

    async def _hard_fail_ud(self, pnu):  # noqa: ANN001
        raise RuntimeError("UD802 조회 실패")  # _districts가 None으로 격리

    monkeypatch.setattr(VWorldService, "get_land_use_plan", _hard_fail_ned, raising=True)
    monkeypatch.setattr(VWorldService, "get_land_use_districts", _hard_fail_ud, raising=True)

    dc = (await az.parcel_boundaries(
        az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}])
    ))["features"][0]["dominant_constraint"]

    assert dc is not None, "조회 실패가 '제약 없음'으로 뭉개졌다(무음 낙관)"
    assert dc["unverified"] is True
    assert dc["headline"] is None, "확정 못 한 상태에서 제약을 만들어내면 날조"


async def test_parcel_boundaries_partial_failure_is_unverified(monkeypatch):
    """★R2 HIGH 회귀락: **한쪽만** 실패해도 unverified다(부분 실패 = 반쪽 목록).

    종전 OR 논리는 "하나라도 성공하면 확인 완료"로 봐서 무음 낙관이 재발했다. 재현:
    NED(군사·비행안전을 주는 **유일한** 출처)가 실패하고 UD802/803만 성공해 보호구역 매치가
    0건이면 → 배너가 조용히 사라지고 사용자는 "규제 없는 깨끗한 필지"로 읽는다.
    합집합이 완전하려면 두 출처가 **모두** 성공해야 한다.
    """
    az = _stub_boundary_io(
        monkeypatch, districts=["자연녹지지역"], zone_type="자연녹지지역", ned_districts=[],
    )
    from apps.api.app.services.external_api.vworld_service import VWorldService

    async def _ned_hard_fail(self, pnu):  # noqa: ANN001
        return None  # 군사·비행안전 출처만 실패

    monkeypatch.setattr(VWorldService, "get_land_use_plan", _ned_hard_fail, raising=True)

    dc = (await az.parcel_boundaries(
        az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}])
    ))["features"][0]["dominant_constraint"]

    assert dc is not None, (
        "NED(군사·비행안전 유일 출처)가 실패했는데 UD802/803만으로 '제약 없음'이 됐다 — "
        "부분 실패 무음 낙관 재발"
    )
    assert dc["unverified"] is True


async def test_parcel_boundaries_zero_regulation_is_verified_and_hidden(monkeypatch):
    """조회 성공 + 규제 0건은 unverified가 아니라 정말 '제약 없음'(배너 미표시)."""
    az = _stub_boundary_io(monkeypatch, districts=[], zone_type="보전관리지역", ned_districts=[])

    feat = (await az.parcel_boundaries(
        az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}])
    ))["features"][0]
    assert feat["dominant_constraint"] is None


async def test_parcel_boundaries_merges_both_designation_sources(monkeypatch):
    """두 출처(NED 개별법 + UD802/803 용도지구)가 **합집합**으로 랭킹된다."""
    az = _stub_boundary_io(
        monkeypatch,
        districts=["고도지구"],                      # 용도지구
        zone_type="보전관리지역",
        ned_districts=["군사시설보호구역(통제보호구역)"],  # 개별법
    )

    dc = (await az.parcel_boundaries(
        az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}])
    ))["features"][0]["dominant_constraint"]

    names = [r["name"] for r in dc["ranked"]]
    assert "군사시설보호구역(통제보호구역)" in names, f"NED 출처 누락: {names}"
    assert "고도지구" in names, f"UD802 출처 누락: {names}"


async def test_parcel_boundaries_unconstrained_parcel_has_no_banner(monkeypatch):
    """★배선①-c: 제약 0건 필지는 dominant_constraint=None(빈 배너 금지)."""
    az = _stub_boundary_io(
        monkeypatch, districts=[], zone_type="보전관리지역", ned_districts=[],
    )

    result = await az.parcel_boundaries(az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}]))

    feat = result["features"][0]
    assert "dominant_constraint" in feat, "키 자체는 계약상 항상 실린다"
    assert feat["dominant_constraint"] is None, (
        "규제 0건·비주거 용도지역인데 배너 데이터가 생성됨(빈 배너 원인)"
    )


# ══════════════════════════════════════════════════════════════════════════
# ② 분석 경로 — analyze() → result["dominant_constraint"]
# ══════════════════════════════════════════════════════════════════════════
def _stub_analyze_io(monkeypatch, *, districts: list[str], zone_type: str, slope_pct: float | None):
    """analyze() 주경로를 무DB·무네트워크로 완주시키는 대역(판정 로직은 실물)."""
    import app.services.land_intelligence.comprehensive_analysis_service as cas
    from app.services.ai.market_interpreter import MarketInterpreter
    from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
    from app.services.ledger import analysis_ledger_service as _ledger
    from app.services.ledger import prior_context as _prior

    svc = cas.ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):  # noqa: ANN001
        return {
            "pnu": _PNU,
            "zone_type": zone_type,
            "address": address,
            "land_register": {"area_sqm": 147_078.0, "land_category": "임야"},
            # 규제 designation은 land_use_plan → _research_dev_plans(sec7)를 통해 흐른다.
            "land_use_plan": {"districts": [{"district_name": n} for n in districts]},
            # ★실 생산자(collect_comprehensive)가 **항상** 채우는 키다 — 대역이 이걸 빼면
            #   "조회 성공" 시나리오를 표현하지 못하고 전부 미확인으로 판정된다(대역 충실성).
            "land_use_plan_status": "ok",
            "special_districts": districts,
            # 외부 왕복 회피용 사전 채움(이 테스트의 관심사가 아닌 경로).
            "nearby_transactions": {"note": "stub"},
            "infrastructure": {},
            "coordinates": {},
            "official_prices": [],
            "warnings": [],
        }

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    # ── DEM 경사도: terrain_service만 대역하고 _terrain_facts_from_result는 실물을 태운다
    #    (계약 변환까지 관통 — 상위 헬퍼를 대역하면 변환 버그를 못 잡는다).
    async def _fake_terrain(address, pnu=None, lat=None, lon=None):  # noqa: ANN001
        if slope_pct is None:
            return {"ok": False}
        return {"ok": True, "slope": {"mean_pct": slope_pct, "max_pct": slope_pct + 9}}

    from app.services.terrain import terrain_service as _ts
    monkeypatch.setattr(_ts, "analyze_terrain", _fake_terrain, raising=True)

    # 조례 경사도 기준·산림 임목축적은 이 테스트의 관심사 아님(외부 왕복 차단).
    async def _none_criteria(address, sp_input):  # noqa: ANN001
        return None

    async def _none_forest(pnu, sp_input):  # noqa: ANN001
        return None

    monkeypatch.setattr(cas, "_fetch_slope_criteria", _none_criteria, raising=True)
    monkeypatch.setattr(cas, "_fetch_forest_data", _none_forest, raising=True)

    # ── 원장·prior(DB) 대역 — CI에 Postgres가 없다. skip 대신 대역해 배선을 반드시 태운다.
    async def _no_prior(**kwargs):  # noqa: ANN003
        return None

    async def _no_append(**kwargs):  # noqa: ANN003
        return {"ok": False}

    monkeypatch.setattr(_prior, "load_prior", _no_prior, raising=True)
    monkeypatch.setattr(_ledger, "append_analysis", _no_append, raising=True)

    # ── 전문가 교차검증(심의/설계 엔진·MemoryHub)·LLM 해석은 관심사 아님.
    from app.services.agents import specialist_dispatch as _sd

    async def _no_specialists(domains, **kwargs):  # noqa: ANN001, ANN003
        return None

    monkeypatch.setattr(_sd, "run_specialist_domains", _no_specialists, raising=True)

    async def _no_interpretation(self, result, prior_context=None):  # noqa: ANN001
        return None

    monkeypatch.setattr(
        SiteAnalysisInterpreter, "generate_interpretation", _no_interpretation, raising=True,
    )
    monkeypatch.setattr(
        MarketInterpreter, "generate_interpretation", _no_interpretation, raising=True,
    )
    return svc


async def _analyze(svc: Any, address: str = "경북 포항시 남구 호미곶면 대보리 산1-1") -> dict:
    return await svc.analyze(address, tenant_id=None, project_id=None, with_senior=False)


async def test_analyze_wires_dominant_constraint_into_result(monkeypatch):
    """★배선②: analyze() 응답에 dominant_constraint가 실린다(순수함수 초록≠배선 존재)."""
    svc = _stub_analyze_io(
        monkeypatch, districts=_DISTRICTS, zone_type="보전관리지역", slope_pct=18.0,
    )

    result = await _analyze(svc)

    assert "dominant_constraint" in result, "analyze() 주경로 배선 끊김(키 부재)"
    dc = result["dominant_constraint"]
    assert dc is not None
    assert "통제보호구역" in dc["headline"], f"headline이 군사가 아님: {dc['headline']}"
    assert dc["severity"] == "높음"


async def test_analyze_dominant_constraint_consumes_real_terrain_slope(monkeypatch):
    """★배선②-b: DEM 경사도가 terrain_service→terrain_facts→지배 제약까지 실제로 도달한다.

    (경사도 인자를 배선에서 빼먹어도 headline은 군사라 초록이 된다 — 그래서 ranked를 본다.)
    """
    svc = _stub_analyze_io(
        monkeypatch, districts=_DISTRICTS, zone_type="보전관리지역", slope_pct=18.0,
    )

    result = await _analyze(svc)

    names = [r["name"] for r in result["dominant_constraint"]["ranked"]]
    assert any(n == "경사도 18%" for n in names), (
        f"DEM 경사도가 지배 제약까지 도달하지 못했다(slope_pct 미전달 배선 결함): {names}"
    )


async def test_analyze_no_constraint_yields_none(monkeypatch):
    """★배선②-c: 규제 0건·완경사 필지는 None — 화면이 배너를 띄우지 않는다."""
    svc = _stub_analyze_io(
        monkeypatch, districts=[], zone_type="제2종일반주거지역", slope_pct=4.0,
    )

    result = await _analyze(svc)

    assert result["dominant_constraint"] is None, (
        "제약 없는 필지에 배너 데이터가 생성됨(빈 배너 원인)"
    )


async def test_land_info_produces_land_use_plan_status(monkeypatch):
    """★생산자 관통: land_info_service가 조회 성패 플래그를 **실제로 만들어낸다**.

    ★왜 필요한가(변이 실증): 아래 analyze 테스트는 base에 land_use_plan_status를 **주입**해
    소비 배선만 검증한다. 그래서 생산자 한 줄을 지우는 변이가 51건 전부 생존했다 — 테스트가
    검증해야 할 값을 스스로 넣어주는 가짜 골든이었다. 여기서는 값을 주입하지 않고
    `_fetch_land_use_plan`(외부 I/O 경계)만 대역해 **실제 산출**을 확인한다.

    계약: None(하드 실패)→"unavailable" · [](확인 완료·규제 0건)→"ok" · [..]→"ok"
    """
    from app.services.land_intelligence.land_info_service import LandInfoService

    async def _run(land_use_result) -> dict:
        svc = LandInfoService()

        async def _none(*a, **k):  # noqa: ANN002, ANN003
            return None

        async def _land_use(pnu):  # noqa: ANN001
            return land_use_result

        async def _zoning(addr):  # noqa: ANN001
            return {"pnu": _PNU, "zone_type": "보전관리지역", "success": True}

        async def _ordinance(addr, zone, force_refresh=False, pnu=None, resolved_sigungu=None):  # noqa: ANN001
            return {}

        monkeypatch.setattr(svc.zoning, "analyze_by_address", _zoning, raising=False)
        for name in (
            "_fetch_land_register", "_fetch_official_price", "_fetch_building_info",
            "_fetch_land_characteristics", "_fetch_building_detail",
            "_fetch_nearby_transactions", "_fetch_precise_road_width", "_fetch_infrastructure",
        ):
            monkeypatch.setattr(svc, name, _none, raising=False)
        monkeypatch.setattr(svc, "_fetch_land_use_plan", _land_use, raising=True)
        monkeypatch.setattr(svc.ordinance, "get_ordinance_limits", _ordinance, raising=False)
        return await svc._collect_comprehensive_impl("경북 포항시 남구 호미곶면 대보리 산1-1")  # noqa: SLF001

    hard_fail = await _run(None)
    assert hard_fail.get("land_use_plan_status") == "unavailable", (
        "조회 하드 실패가 '확인 완료'로 표기되면 소비처가 '규제 없음'으로 오독한다"
    )

    zero_regs = await _run([])
    assert zero_regs.get("land_use_plan_status") == "ok", (
        "확인 완료·규제 0건은 실패가 아니다(과잉 경고도 정직이 아니다)"
    )

    with_regs = await _run([{"district_name": "개발제한구역"}])
    assert with_regs.get("land_use_plan_status") == "ok"

    # ★조회 코루틴이 예외를 던지면 gather(return_exceptions=True)가 **Exception 인스턴스**를
    #   담는다 — `is None` 판정은 그것을 "ok"로 흘려보내 실패를 성공으로 표기한다(정반대 오류).
    async def _boom(pnu):  # noqa: ANN001
        raise RuntimeError("NED 호출 폭발")

    svc_err = LandInfoService()

    async def _none(*a, **k):  # noqa: ANN002, ANN003
        return None

    async def _zoning_err(addr):  # noqa: ANN001
        return {"pnu": _PNU, "zone_type": "보전관리지역", "success": True}

    async def _ord_err(addr, zone, force_refresh=False, pnu=None, resolved_sigungu=None):  # noqa: ANN001
        return {}

    monkeypatch.setattr(svc_err.zoning, "analyze_by_address", _zoning_err, raising=False)
    for name in (
        "_fetch_land_register", "_fetch_official_price", "_fetch_building_info",
        "_fetch_land_characteristics", "_fetch_building_detail",
        "_fetch_nearby_transactions", "_fetch_precise_road_width", "_fetch_infrastructure",
    ):
        monkeypatch.setattr(svc_err, name, _none, raising=False)
    monkeypatch.setattr(svc_err, "_fetch_land_use_plan", _boom, raising=True)
    monkeypatch.setattr(svc_err.ordinance, "get_ordinance_limits", _ord_err, raising=False)

    raised = await svc_err._collect_comprehensive_impl("경북 포항시 남구 호미곶면 대보리 산1-1")  # noqa: SLF001
    assert raised.get("land_use_plan_status") == "unavailable", (
        "예외(gather return_exceptions)가 '확인 완료'로 흘러갔다 — 실패를 성공으로 표기"
    )

    # ★R3 MEDIUM: PNU 해석 자체가 실패하면 위 판정 블록(`if effective_pnu is not None:`)에
    #   **도달조차 못 한다**. 기본값이 없으면 키가 빠지고 소비처가 "확인 완료"로 낙관 폴백한다
    #   — "조회를 시도조차 못 했다"는 미확인이지 "규제 없음"이 아니다.
    svc_nopnu = LandInfoService()

    async def _zoning_no_pnu(addr):  # noqa: ANN001
        return {"pnu": None, "zone_type": None, "success": False}

    monkeypatch.setattr(svc_nopnu.zoning, "analyze_by_address", _zoning_no_pnu, raising=False)
    for name in (
        "_fetch_land_register", "_fetch_official_price", "_fetch_building_info",
        "_fetch_land_characteristics", "_fetch_building_detail",
        "_fetch_nearby_transactions", "_fetch_precise_road_width", "_fetch_infrastructure",
        "_fetch_land_use_plan",
    ):
        monkeypatch.setattr(svc_nopnu, name, _none, raising=False)
    monkeypatch.setattr(svc_nopnu.ordinance, "get_ordinance_limits", _ord_err, raising=False)

    no_pnu = await svc_nopnu._collect_comprehensive_impl("해석불가주소")  # noqa: SLF001
    assert no_pnu.get("land_use_plan_status") == "unavailable", (
        "PNU 미해석 필지에서 상태 키가 빠져 소비처가 '확인 완료'로 낙관 폴백한다"
    )


def test_designations_verified_uses_whitelist_not_negation():
    """★소비처는 화이트리스트("ok"일 때만 verified)여야 한다 — 부정형이면 키 부재가 낙관이 된다."""
    import inspect

    from app.services.land_intelligence import comprehensive_analysis_service as cas

    src = inspect.getsource(cas.ComprehensiveAnalysisService.analyze)
    assert 'base.get("land_use_plan_status") == "ok"' in src, (
        "부정형(!= 'unavailable') 판정은 키 부재·오탈자·새 상태값을 전부 verified로 흘려보낸다"
    )


async def test_analyze_marks_regulation_lookup_failure_as_unverified(monkeypatch):
    """★배선②-d: 종합분석 표면도 "조회 실패"를 "제약 없음"으로 표기하지 않는다.

    sec7의 land_use_regulations는 base["land_use_plan"] 단일 출처인데 그 키는 비어있지 않은
    목록일 때만 채워져 실패/0건 구분이 소실됐다 — land_info_service의 land_use_plan_status가
    그 구분을 정직하게 남기고 analyze()가 소비하는지 관통 확인.
    """
    svc = _stub_analyze_io(
        monkeypatch, districts=[], zone_type="자연녹지지역", slope_pct=None,
    )

    # 조회 실패(land_use_plan_status="unavailable") — collect_comprehensive 대역에 주입.
    import app.services.land_intelligence.comprehensive_analysis_service as cas  # noqa: F401

    original = type(svc.land_info).collect_comprehensive

    async def _failed_lookup(self, address, pnu=None):  # noqa: ANN001
        base = await original(self, address, pnu)
        base["land_use_plan_status"] = "unavailable"
        return base

    monkeypatch.setattr(
        type(svc.land_info), "collect_comprehensive", _failed_lookup, raising=True,
    )

    result = await _analyze(svc)

    dc = result["dominant_constraint"]
    assert dc is not None, "규제 조회 실패가 '제약 없음'으로 뭉개졌다(무음 낙관)"
    assert dc["unverified"] is True
    assert dc["headline"] is None


async def test_analyze_successful_lookup_is_verified(monkeypatch):
    """조회 성공(land_use_plan_status='ok')이면 unverified=False — 과잉 경고도 정직이 아니다."""
    svc = _stub_analyze_io(
        monkeypatch, districts=_DISTRICTS, zone_type="보전관리지역", slope_pct=None,
    )
    original = type(svc.land_info).collect_comprehensive

    async def _ok_lookup(self, address, pnu=None):  # noqa: ANN001
        base = await original(self, address, pnu)
        base["land_use_plan_status"] = "ok"
        return base

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _ok_lookup, raising=True)

    result = await _analyze(svc)
    assert result["dominant_constraint"]["unverified"] is False


async def test_analyze_headline_severity_agrees_with_risk_level(monkeypatch):
    """지배 제약 severity와 종합 리스크 등급이 **같은 규제 목록**에서 나오는지(자기모순 차단).

    두 값이 서로 다른 목록에서 나오면 "리스크 낮음 / 지배 제약 극히 높음"처럼 화면이
    스스로를 반박한다 — 같은 clean_regulations를 쓰는지 관통 확인.
    """
    svc = _stub_analyze_io(
        monkeypatch, districts=["개발제한구역"], zone_type="자연녹지지역", slope_pct=None,
    )

    result = await _analyze(svc)

    assert result["development_plans"]["risk_level"] == "극히 높음"
    assert result["dominant_constraint"]["severity"] == "극히 높음"
