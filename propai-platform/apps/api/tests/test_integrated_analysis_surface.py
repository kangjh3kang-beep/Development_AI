"""`/zoning/integrated-analysis` per_parcel 표면 — 미분석 표식이 여기서도 살아 나가는가.

★왜(2026-08-05 R3 H-2): 이 응답은 다필지 감지 결과를 그대로 싣지 않고 **자체 재조립본**이다.
  그래서 표식을 따로 실어야 하는데, 그 4줄을 지워도 저장소의 어떤 테스트도 깨지지 않았다
  (변이 생존). 프론트 "판정 불가(미분석)" 배지가 읽는 키라 빠지면 배지가 다시 굶는다.

  형제 표면(build_multi_parcel_report matrix)은 회귀락이 있었는데 이 표면만 없었다 —
  "두 표면에 실었다"는 주장의 절반만 잠겨 있던 셈이다.
"""
import pytest

from app.services.zoning.special_parcel import is_unanalyzed_parcel


@pytest.mark.asyncio
async def test_integrated_analysis_per_parcel_declares_status_both_ways():
    """라우터 응답의 per_parcel이 표식을 **양방향**으로 싣는다."""
    from routers.auto_zoning import IntegratedAnalysisRequest, integrated_analysis

    req = IntegratedAnalysisRequest(parcels=[
        {"address": "A", "area_sqm": 400.0, "zone_type": "제2종일반주거지역", "land_category": "대"},
        {"address": "B", "area_sqm": 600.0},
    ])
    out = await integrated_analysis(req)
    statuses = [p.get("analysis_status") for p in out["per_parcel"]]
    assert statuses == ["analyzed", "unanalyzed"], statuses
    # 부재(None)로 남지 않는다 — 부재는 "분석됨"과 "판정 안 함"을 구분하지 못한다.
    assert None not in statuses


def test_status_source_is_the_shared_predicate():
    """판정은 SSOT를 쓴다 — 라우터가 자체 규칙을 갖고 있으면 우회 경로에 적용되지 않는다."""
    assert is_unanalyzed_parcel({"area_sqm": 600.0}) is True
    assert is_unanalyzed_parcel({"area_sqm": 600.0, "zone_type": "제2종일반주거지역"}) is False
