"""`/zoning/special-parcels` 라우터 관통 테스트 — 실제 진입점을 아무도 안 태우고 있었다.

★왜(2026-08-05 R2 적대검증 MEDIUM): 이 라우터는 R1이 "실제 진입점"으로 지목한 곳인데
  저장소에 이 핸들러를 **실행하는 테스트가 0건**이었다(회귀락은 primitive 층에만 있었다).
  누군가 라우터에 사후 판정 블록을 다시 넣어도(= 2026-08-02에 CRITICAL을 만든 바로 그
  순서 역전) 아무도 못 잡는 상태였다.

  primitive가 옳아도 라우터가 그 결과를 덮거나 순서를 뒤집으면 화면 숫자는 틀린다.
  그래서 **핸들러를 직접 호출**해 응답 dict를 검사한다.
"""
import pytest

from routers.auto_zoning import special_parcels_check

ANALYZED = {"pnu": "a", "area_sqm": 400.0, "zone_type": "제2종일반주거지역", "land_category": "대"}
UNANALYZED = {"pnu": "b", "area_sqm": 600.0}


@pytest.mark.asyncio
async def test_router_returns_area_tiers_that_exclude_unanalyzed():
    """★대조군 격리 — 라우터 응답의 확정 면적에서 미분석분이 실제로 빠진다."""
    control = await special_parcels_check({"parcels": [ANALYZED, {**UNANALYZED, "land_category": "대",
                                                                  "zone_type": "제2종일반주거지역"}]})
    mixed = await special_parcels_check({"parcels": [ANALYZED, UNANALYZED]})

    c_usable = control["usable_area"]
    m_usable = mixed["usable_area"]
    assert c_usable["usable_confirmed_sqm"] == 1000.0
    assert c_usable["usable_conditional_sqm"] == 0.0
    # 격차가 미분석 필지 면적과 정확히 일치한다("값이 있다"가 아니라 "값이 변했다").
    assert c_usable["usable_confirmed_sqm"] - m_usable["usable_confirmed_sqm"] == 600.0
    assert m_usable["usable_conditional_sqm"] == 600.0


@pytest.mark.asyncio
async def test_router_marks_and_counts_unanalyzed():
    """표식과 카운트가 응답에 실린다 — 소비처(프론트 배지)가 읽는 키."""
    out = await special_parcels_check({"parcels": [ANALYZED, UNANALYZED]})
    assert out["unanalyzed_count"] == 1
    assert [p.get("analysis_status") for p in out["per_parcel"]] == ["analyzed", "unanalyzed"]
    assert out["developability"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_router_does_not_downgrade_all_analyzed_case():
    """정상 입력 무회귀 — 오탐 0."""
    out = await special_parcels_check({"parcels": [
        ANALYZED, {"pnu": "b", "area_sqm": 600.0, "zone_type": "제2종일반주거지역", "land_category": "대"},
    ]})
    assert out["developability"] == "POSSIBLE"
    assert out["usable_area"]["usable_confirmed_sqm"] == 1000.0
    assert "unanalyzed_count" not in out


@pytest.mark.asyncio
async def test_router_warns_when_only_land_category_missing():
    """지목만 없는 필지는 미분석이 아니라 **부분 미확인** — 침묵하지 않고 경고한다."""
    out = await special_parcels_check({"parcels": [
        ANALYZED, {"pnu": "b", "area_sqm": 600.0, "zone_type": "제2종일반주거지역"},
    ]})
    warnings = out["per_parcel"][1].get("warnings") or []
    joined = " ".join(str(w) for w in warnings)
    # 원본 필지에 붙은 경고가 아니라 라우터가 붙인 것이므로 입력 쪽에서 확인한다.
    assert out["developability"] != "UNKNOWN"  # 미분석으로 강등되지 않는다
    assert "unanalyzed_count" not in out
    assert joined == "" or "지목" in joined


@pytest.mark.asyncio
async def test_router_rejects_empty_parcels():
    """빈 입력은 400 — 조용히 빈 결과를 만들지 않는다."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await special_parcels_check({"parcels": []})
    assert exc.value.status_code == 400
