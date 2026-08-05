"""지번이 있는데 면적이 0인 필지 — 조용히 버리지 않는다.

★사용자 지적(2026-08-05): "필지 지번이 있다면 대지면적 0은 있을 수 없음."
  맞다. 그래서 그 조합은 **값이 아니라 수집 실패**다. 그런데 통합 집계는 그 필지를 필터에서
  걸러낸 뒤 아무 흔적도 남기지 않았다 — 2필지를 넣었는데 통합면적이 1필지분으로 나오고,
  사용자는 필지가 빠진 사실 자체를 몰랐다. 그 면적이 land_area로 흘러 GFA·수지까지 간다.

  하위 `compute_usable_area`는 `area_unknown_parcels`로 이걸 이미 잡아내고 있었는데, 상위가
  필지를 **먼저 버려서** 그 신호가 만들어질 기회조차 없었다 — 이번 캠페인의 '미분석 면적'
  결함과 정확히 같은 계열(정직한 신호를 만들어 놓고 소비처가 안 읽음).
"""
import pytest

from app.services.land_intelligence.comprehensive_analysis_service import (
    build_integrated_context,
)

WITH_AREA = {"pnu": "1111", "address": "A", "area_sqm": 400.0,
             "zone_type": "제2종일반주거지역", "land_category": "대"}
SIBLING = {"pnu": "3333", "address": "C", "area_sqm": 600.0,
           "zone_type": "제2종일반주거지역", "land_category": "대"}
ZERO_AREA = {"pnu": "2222", "address": "B", "area_sqm": 0,
             "zone_type": "제2종일반주거지역", "land_category": "대"}


@pytest.mark.asyncio
async def test_zero_area_parcel_is_disclosed_not_dropped_silently():
    """★빠진 필지를 최상위에 명시한다 — 지번까지 남겨 어느 필지인지 추적 가능하게."""
    ctx = await build_integrated_context([WITH_AREA, ZERO_AREA])
    missing = ctx.get("area_missing_parcels")
    assert missing, "면적 0 필지가 아무 흔적 없이 사라졌다"
    assert missing[0]["pnu"] == "2222"


@pytest.mark.asyncio
async def test_disclosure_says_the_aggregate_is_understated():
    """★고지는 '빠졌다'로 끝내지 않고 **통합면적이 과소 산출된다**는 결과까지 말한다."""
    ctx = await build_integrated_context([WITH_AREA, ZERO_AREA])
    warnings = (ctx.get("usable") or {}).get("warnings") or []
    joined = " ".join(str(w) for w in warnings)
    assert "면적 미확보" in joined
    assert "과소" in joined


@pytest.mark.asyncio
async def test_normal_parcels_carry_no_disclosure():
    """정상 필지만 있으면 고지가 붙지 않는다 — 오탐 0."""
    ctx = await build_integrated_context([WITH_AREA, SIBLING])
    assert ctx.get("area_missing_parcels") is None
    assert ((ctx.get("usable") or {}).get("warnings") or []) == []


@pytest.mark.asyncio
async def test_aggregate_still_excludes_the_zero_area_parcel():
    """면적 자체는 종전대로 제외한다 — 고지는 추가지 계산 변경이 아니다(무회귀)."""
    ctx = await build_integrated_context([WITH_AREA, ZERO_AREA])
    assert ctx["total_area_sqm"] == 400.0


@pytest.mark.asyncio
async def test_identityless_row_is_not_reported_as_missing():
    """지번·주소가 모두 없는 행은 '빠진 필지'로 세지 않는다 — 그건 필지가 아니다."""
    ctx = await build_integrated_context([WITH_AREA, {"area_sqm": 0}])
    assert ctx.get("area_missing_parcels") is None
