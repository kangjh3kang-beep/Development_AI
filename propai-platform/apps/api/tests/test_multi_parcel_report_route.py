"""S5 다필지 종합 보고 라우트(/zoning/multi-parcel-report) 계약 테스트 — additive(★G2).

배경: build_multi_parcel_report(special_parcel.py:1753)는 usable 3계층·§84 걸침·제외 시나리오·
시니어 리뷰까지 조립하는 완성 함수인데 프로덕션 소비처가 없었다(오펀). routers/auto_zoning.py에
신설한 POST /zoning/multi-parcel-report가 유일 소비처다.

검증 축(2건, additive):
  A. 정상 — tests/test_multi_parcel_report.py::test_report_contract_full과 동일 필지 픽스처를
     그대로 재사용해, 라우트가 enrich 파이프라인을 거친 뒤 build_multi_parcel_report 결과를
     그대로(계약 불변) 반환하는지 검증.
  B. 필지부족(단일 필지) — 차단(400)하지 않고 그대로 산출하되 '단일 필지' 정직 고지가
     honest_limitations에 additive로 붙는지 검증.

외부 API(VWorld·조례서비스·법제처)는 monkeypatch로 passthrough/no-op 대역해 라이브 네트워크
호출 없이 결정론 검증한다(무네트워크·무행 — 표적 테스트 요건).
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

import apps.api.routers.auto_zoning as auto_zoning_router  # noqa: E402
from apps.api.app.services.land_intelligence.parcel_excel_service import (  # noqa: E402
    ParcelExcelService,
)


def _run(coro):
    """이벤트 루프 안전 실행(러닝 루프 부재 환경에서도 동작) — test_precheck_upgrade.py 관례 재사용."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _passthrough_enrich(self, items, with_building=True):
    """ParcelExcelService.enrich_parcel_list 대역 — 픽스처가 이미 enrich된 shape이므로 그대로 통과."""
    return [dict(p) for p in items]


async def _noop_enrich_effective(enriched):
    """_enrich_effective_and_special 대역 — 픽스처가 이미 _far_eff 등을 보유해 in-place 부착 불필요."""
    return None


@pytest.fixture(autouse=True)
def _stub_external(monkeypatch):
    """라이브 네트워크(VWorld·조례서비스) 완전 차단 — 라우트 조립 로직만 결정론 검증."""
    monkeypatch.setattr(ParcelExcelService, "enrich_parcel_list", _passthrough_enrich)
    monkeypatch.setattr(auto_zoning_router, "_enrich_effective_and_special", _noop_enrich_effective)


def _parcels_fixture_full() -> list[dict]:
    """test_multi_parcel_report.py::test_report_contract_full과 동일 필지(이미 enrich된 shape)."""
    return [
        {"pnu": "P-A", "address": "A", "land_category": "대",
         "zone_type": "제2종일반주거지역", "area_sqm": 1000,
         "_far_eff": 200, "_bcr_eff": 50, "_far_legal": 250, "_bcr_legal": 60,
         "_far_basis": "조례"},
        {"pnu": "P-N", "address": "N", "land_category": "전",
         "zone_type": "계획관리지역", "area_sqm": 500,
         "official_land_price_per_m2": 100000,
         "_far_eff": 100, "_bcr_eff": 40, "_far_legal": 100, "_bcr_legal": 40,
         "_far_basis": "조례"},
        {"pnu": "P-GB", "address": "GB", "land_category": "대",
         "zone_type": "자연녹지지역", "area_sqm": 300,
         "special_districts": ["개발제한구역"],
         "_far_eff": 80, "_bcr_eff": 20, "_far_legal": 100, "_bcr_legal": 20,
         "_far_basis": "조례"},
    ]


def test_route_contract_full_report():
    """정상 — 라우트가 build_multi_parcel_report 계약(전 키 + 값)을 무손상 그대로 반환."""
    req = auto_zoning_router.MultiParcelReportRequest(parcels=_parcels_fixture_full())
    resp = _run(auto_zoning_router.multi_parcel_report(req))

    for key in ("report_type", "parcel_count", "matrix", "usable_area",
                "zone_straddle_ruling", "integrated_zoning", "charges",
                "verification", "senior_review", "senior_verdict",
                "exclusion_scenario", "developability", "resolvable",
                "blocking_parcels", "honest_disclosure", "recommendation",
                "honest_limitations", "basis"):
        assert key in resp, f"보고 키 {key} 누락"
    assert resp["report_type"] == "multi_parcel_report"
    assert resp["parcel_count"] == 3
    by_pnu = {row["pnu"]: row for row in resp["matrix"]}
    assert by_pnu["P-A"]["usable_tier"] == "confirmed"
    assert by_pnu["P-GB"]["usable_tier"] == "excluded"
    assert by_pnu["P-GB"]["gate"] == "BLOCK"
    ua = resp["usable_area"]
    assert ua["gross_sqm"] == 1800.0
    assert resp["zone_straddle_ruling"]["straddle"] is True
    assert resp["exclusion_scenario"] is not None
    assert resp["resolvable"] == "NO"
    assert resp["developability"] == "BLOCKED"
    # 다필지(3필지) 정상 산출 — 단일필지 정직고지는 붙지 않는다.
    assert not any("단일 필지 입력" in s for s in resp["honest_limitations"])


def test_route_single_parcel_honest_note():
    """필지부족(단일 필지) — 차단(400) 대신 그대로 산출 + 단일필지 정직고지 additive 부착."""
    single = [{"pnu": "N1", "land_category": "대", "zone_type": "제2종일반주거지역",
               "area_sqm": 500, "_far_eff": 200, "_bcr_eff": 50,
               "_far_legal": 250, "_bcr_legal": 60, "_far_basis": "조례"}]
    req = auto_zoning_router.MultiParcelReportRequest(parcels=single)
    resp = _run(auto_zoning_router.multi_parcel_report(req))

    assert resp["report_type"] == "multi_parcel_report"
    assert resp["parcel_count"] == 1
    # 단일 필지 — straddle·exclusion 미해당(기존 build_multi_parcel_report 계약과 동일).
    assert resp["zone_straddle_ruling"]["straddle"] is False
    assert resp["exclusion_scenario"] is None
    # 라우트 additive — 단일 필지 정직고지가 honest_limitations에 부착.
    assert any("단일 필지 입력" in s for s in resp["honest_limitations"]), resp["honest_limitations"]


def test_route_empty_parcels_raises_400():
    """필지 0건 — 정직 안내(400), 기존 /integrated-analysis·/special-parcels 가드와 동일 관례."""
    from fastapi import HTTPException

    req = auto_zoning_router.MultiParcelReportRequest(parcels=[])
    with pytest.raises(HTTPException) as exc_info:
        _run(auto_zoning_router.multi_parcel_report(req))
    assert exc_info.value.status_code == 400
