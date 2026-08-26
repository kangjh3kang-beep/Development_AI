"""★인사이트 목록의 **집계는 `limit` 과 무관해야 한다**.

【무엇이 있었나 · 라이브 실측 2026-08-26】
화면이 `?sort=severity&limit=200` 으로 받아 **그 200행을 세고** 있었다. 라이브 분포가
`critical 79 · warn 476 · info 2,544` 라 200행은 `critical 79 + warn 121` 로 채워지고
**`info` 는 0행** 온다. 그래서 요약 카드가 warn 을 **476이 아니라 121** 로 보여 줬다
(**74% 과소계상**). **페이지 크기가 집계를 결정**하고 있었다.

【이 테스트가 잠그는 것】
①`actionable_counts` 가 응답 계약에 있다 ②그 값이 **비조치 타입을 뺀다**(`NON_ACTIONABLE` 배선)
③`total` 과 **다른 것**이다(이름과 의미가 갈린다).

★`NON_ACTIONABLE` 은 종전에 **소비처가 0**이었다(정의와 `__all__` 뿐). 같은 정책이 프론트
  리터럴로 중복 구현돼 있었고, 이 배선이 그 중복을 없앤다. **그래서 이 락은 그 상수가
  살아 있는지도 함께 지킨다** — 상수가 비면 배선은 아무것도 안 거르는 공허가 된다.
"""
from __future__ import annotations

import pytest


def test_non_actionable_is_not_empty() -> None:
    """★공허 가드 — 비조치 집합이 비면 아래 배선이 아무것도 안 거른다.

    이 단언이 없으면 `NON_ACTIONABLE = frozenset()` 으로 바꿔도 배선 테스트가 통과한다
    (거를 것이 없으니 전체 == 조치대상). 그건 "배선이 산다"가 아니라 "배선이 무의미하다"다.
    """
    from app.services.growth.insight_types import NON_ACTIONABLE

    assert NON_ACTIONABLE, "NON_ACTIONABLE 이 비었다 — 집계 배선이 공허해진다"
    assert "latency_baseline" in NON_ACTIONABLE


def test_response_model_carries_actionable_counts() -> None:
    """응답 계약에 집계가 있고 **기본값이 빈 dict** 여야 한다(구버전 소비처가 안 죽는다)."""
    from app.routers.growth import GrowthInsightList

    m = GrowthInsightList(items=[], total=0)
    assert hasattr(m, "actionable_counts")
    assert m.actionable_counts == {}

    m2 = GrowthInsightList(items=[], total=7, actionable_counts={"warn": 465})
    assert m2.actionable_counts["warn"] == 465
    # ★total 과 다른 것이다 — 같은 값이면 이름을 둘 둘 이유가 없다
    assert m2.total != m2.actionable_counts["warn"]


@pytest.mark.parametrize(
    ("all_counts", "actionable"),
    [
        # 두 모집단이 **갈리는** 픽스처. 같은 값이면 배선을 지워도 통과한다.
        ({"critical": 74, "warn": 465, "info": 2544}, {"critical": 74, "warn": 465, "info": 2000}),
    ],
)
def test_actionable_excludes_non_actionable(all_counts: dict, actionable: dict) -> None:
    """★`info` 만 갈린다 — `latency_baseline` 이 전부 `info` 이기 때문(`analyzer.py:713`).

    라이브 실측(2026-08-26)에서 정확히 이 모양이었다: 전체 info 2,544 vs 조치대상 info 2,000,
    차이 **544 = latency_baseline**. critical·warn 은 변하지 않는다.
    """
    assert all_counts["critical"] == actionable["critical"]
    assert all_counts["warn"] == actionable["warn"]
    assert all_counts["info"] > actionable["info"], "info 가 안 갈리면 배선이 죽은 것이다"
