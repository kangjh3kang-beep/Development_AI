"""통합 컨텍스트 오라클 — 미분석 필지가 확정 개발가능 면적에 새지 않는다.

★왜 이 파일이 별도로 있나(2026-08-02 W4 CRITICAL의 재발 방지):
  같은 결함을 이미 한 번 놓쳤다. `compute_usable_area`를 **합성 픽스처로 직접 부르는**
  회귀락은 통과했는데, 실제 요청 흐름은 그 코드를 안 타서 프로덕션 숫자가 하나도 안
  바뀌었다 — 죽은 경로를 완벽히 잠근 가짜 골든이었다.

  그래서 이 파일은 primitive를 부르지 않는다. **공용 통로인 `build_integrated_context`**
  를 그대로 호출한다. 종합분석·파이프라인·수지(Top3)·90초진단·의사결정브리프가 전부
  이 함수를 통해 통합 컨텍스트를 얻으므로, 여기가 막히면 그 전부가 따라온다.

  검증 방식도 대조군 격리다 — 미분석 필지 유무만 다른 두 입력의 **숫자 격차**가 그
  필지 면적과 정확히 일치하는지 본다. "값이 있다"가 아니라 "값이 변했다"를 본다.
"""
import pytest

from app.services.land_intelligence.comprehensive_analysis_service import (
    build_integrated_context,
)

ANALYZED_A = {"address": "A", "area_sqm": 400, "zone_type": "제2종일반주거지역", "land_category": "대"}
ANALYZED_B = {"address": "B", "area_sqm": 600, "zone_type": "제2종일반주거지역", "land_category": "대"}
# 지목·용도지역·용도지구가 전부 없다 = '특이 제약 없음'이 아니라 '못 봤음'.
UNANALYZED_B = {"address": "B", "area_sqm": 600}


@pytest.mark.asyncio
async def test_unanalyzed_parcel_excluded_from_confirmed_via_public_path():
    """★대조군 격리 — 미분석 600㎡가 확정에서 빠지고 조건부로 간다."""
    control = await build_integrated_context([ANALYZED_A, ANALYZED_B])
    mixed = await build_integrated_context([ANALYZED_A, UNANALYZED_B])

    c_usable = control["usable"]
    m_usable = mixed["usable"]

    # 대조군은 종전과 동일해야 한다(오탐 0).
    assert c_usable["confirmed_sqm"] == 1000.0
    assert c_usable["conditional_sqm"] == 0.0

    # 격차가 미분석 필지 면적과 정확히 일치한다.
    assert c_usable["confirmed_sqm"] - m_usable["confirmed_sqm"] == 600.0
    assert m_usable["confirmed_sqm"] == 400.0
    assert m_usable["conditional_sqm"] == 600.0


@pytest.mark.asyncio
async def test_effective_land_area_does_not_inherit_unanalyzed_area():
    """★이 숫자가 land_area로 채택돼 GFA·세대수·수지로 전파된다 — 여기서 막아야 한다."""
    control = await build_integrated_context([ANALYZED_A, ANALYZED_B])
    mixed = await build_integrated_context([ANALYZED_A, UNANALYZED_B])

    assert control["land_area_effective_sqm"] == 1000.0
    assert mixed["land_area_effective_sqm"] == 400.0


@pytest.mark.asyncio
async def test_all_analyzed_is_unchanged_single_and_multi():
    """정상 입력 무회귀 — 단일·다필지 모두 종전 산출 유지."""
    single = await build_integrated_context([ANALYZED_A])
    assert single["usable"]["confirmed_sqm"] == 400.0
    assert single["usable"]["conditional_sqm"] == 0.0

    multi = await build_integrated_context([ANALYZED_A, ANALYZED_B])
    assert multi["usable"]["conditional_sqm"] == 0.0
    assert multi["usable"]["excluded_sqm"] == 0.0


def test_special_result_present_is_not_treated_as_unanalyzed():
    """특이부지 판정 결과가 이미 붙어 있으면 '못 봤음'이 아니다 — 과잉강등 가드.

    ★정직 표기: 이 단언은 공용 통로가 아니라 계산 함수를 직접 부른다. 변이검증에서 이
    가드를 지워도 아무 테스트가 안 깨져(생존) 무검증임이 드러났고, 그래서 채운다. 다만
    이 형상이 공용 통로(build_integrated_context)로 실제 도달하는지는 **재현하지 못했다**
    — 즉 이건 살아 있는 경로의 회귀락이 아니라 **방어 분기의 계약 고정**이다. 그 이상으로
    읽지 말 것.
    """
    from app.services.zoning.usable_area import compute_usable_area

    seen_but_no_top_level_signal = {
        "address": "B", "area_sqm": 600,
        "special": {"is_special": True, "developability": "POSSIBLE", "resolvable": "YES",
                    "factors": [{"category": "맹지(도로 미접)"}]},
    }
    got = compute_usable_area([ANALYZED_A, seen_but_no_top_level_signal])
    assert got["usable_confirmed_sqm"] == 1000.0
    assert got["usable_conditional_sqm"] == 0.0


@pytest.mark.asyncio
async def test_partial_signal_is_not_downgraded():
    """★과잉강등 금지 — 신호가 하나라도 있으면 미분석이 아니다.

    이 단언이 없으면 '전부 조건부로 내리면 통과'하는 반대 방향 사고를 못 잡는다
    (실제로 형제 모듈에서 zone_type 폴백 누락으로 정상 필지가 통째로 강등된 전례가 있다).
    """
    only_zone = {"address": "C", "area_sqm": 600, "zone_type": "제2종일반주거지역"}
    only_category = {"address": "D", "area_sqm": 600, "land_category": "대"}
    for partial in (only_zone, only_category):
        ctx = await build_integrated_context([ANALYZED_A, partial])
        assert ctx["usable"]["conditional_sqm"] == 0.0, partial
        assert ctx["usable"]["confirmed_sqm"] == 1000.0, partial


@pytest.mark.asyncio
async def test_gross_fallback_is_flagged_when_everything_is_unanalyzed():
    """★H-1: 확정 면적이 0이라 gross를 채택할 때는 **잠정임을 말한다**.

    혼합 케이스만 막고 '전부 미분석'은 뚫려 있었다 — gross 1000이 그대로 land_area가 되어
    GFA·세대수·수지로 흐르는데 경고조차 동반되지 않았다. 면적 자체는 바꾸지 않는다(분석이
    멈추면 안 된다). 대신 소비처가 잠정으로 다룰 수 있게 신호를 싣는다.
    """
    all_unanalyzed = await build_integrated_context([
        {"address": "A", "area_sqm": 400}, {"address": "B", "area_sqm": 600},
    ])
    assert all_unanalyzed["land_area_effective_sqm"] == 1000.0  # 면적은 불변
    assert all_unanalyzed.get("land_area_effective_is_gross_fallback") is True
    warnings = all_unanalyzed["usable"].get("warnings") or []
    assert any("잠정" in str(w) for w in warnings), warnings


@pytest.mark.asyncio
async def test_normal_cases_carry_no_gross_fallback_flag():
    """정상·혼합 케이스에는 폴백 표식이 붙지 않는다 — 오탐 0."""
    for parcels in ([ANALYZED_A, ANALYZED_B], [ANALYZED_A, UNANALYZED_B]):
        ctx = await build_integrated_context(parcels)
        assert ctx.get("land_area_effective_is_gross_fallback") is None
        assert (ctx["usable"].get("warnings") or []) == []
