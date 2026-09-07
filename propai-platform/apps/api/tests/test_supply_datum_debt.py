"""남은 축 부채 — **초록 안에** 보이게 둔다(커밋 메시지에만 적으면 드러나지 않는다).

2026-09-07 세션에서 봉합하지 못하고 **범위를 나눈** 것 둘. 둘 다 회귀 위험이 커서
별도 PR 로 미뤘고, 그 사실을 `xfail` 로 초록 안에 남긴다.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason=(
        "★부채 — 전용률 정본이 아직 둘이다. `suggest._JEONYULRYUL`(평면 0.747)과 "
        "`sale_price_resolver._COMPARABLE_SUPPLY_RATIO`(파생 0.747)가 **우연히 값이 같을 뿐** "
        "각자 정의다. resolver 독스트링은 `_JEONYULRYUL` 을 «정확히 그 이중정의» 라고 "
        "기각 선언해 놓았다. sales 모듈 축이 달라 회귀 위험이 커 이번 PR 에서 손대지 않았다."
    ),
    strict=True,
)
def test_전용률_정본은_하나여야_한다() -> None:
    import app.services.feasibility.sale_price_resolver as R
    from app.services.sales.pricing import suggest as S

    # 값이 같은 것으로는 부족하다 — **같은 객체를 참조**해야 정본이 하나다.
    assert S._JEONYULRYUL is R._COMPARABLE_SUPPLY_RATIO["apt"], (
        "값만 같고 정의가 둘이다 — 한쪽이 움직이면 조용히 갈린다"
    )


@pytest.mark.xfail(
    reason=(
        "★부채 — 같은 산출물 안에서 **전용면적 합이 두 값**이다(실측 2.38배). "
        "세대수 축은 `GFA / 표준전용`(전용률 미적용 → GFA의 100%를 전용 취급)이고 "
        "매출 축은 `GFA × 0.70 × 전용률`(42%)이다. 세대수 249는 과대이고(정합식이면 105) "
        "인입공사비(전기·가스·통신)가 세대수 기반이라 함께 부풀어 있다. "
        "부담금·공사비 전 경로가 움직여 별도 PR 로 분리했다."
    ),
    strict=True,
)
def test_세대수_축과_매출_축의_전용면적_합이_같다() -> None:
    GFA = 25412.1
    ratio_supply = 0.70          # _GFA_TO_SALEABLE_RATIO
    ratio_exclusive = 0.60       # unit_standards M07
    avg_unit_exclusive = 102.0   # unit_standards M07 표준 전용면적

    households = int(GFA / avg_unit_exclusive)
    exclusive_from_households = households * avg_unit_exclusive
    exclusive_from_revenue = GFA * ratio_supply * ratio_exclusive

    assert abs(exclusive_from_households / exclusive_from_revenue - 1.0) < 0.05, (
        f"전용면적 합이 갈린다: 세대수 축 {exclusive_from_households:,.0f}㎡ vs "
        f"매출 축 {exclusive_from_revenue:,.0f}㎡ "
        f"({exclusive_from_households / exclusive_from_revenue:.2f}배)"
    )
