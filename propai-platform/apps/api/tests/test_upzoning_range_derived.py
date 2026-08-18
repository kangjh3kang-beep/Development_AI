"""종상향 예상 용적률이 **후보 하나로 좁혀지지 않는다** — 파생형 락.

【무엇이 뚫렸었나 — 2026-08-19 사용자 지적】
화면에 `예상 상한 150.0~150.0%` 가 찍혔다. 상·하한이 같은 숫자라 개발사는 그것을
**"그 위는 안 된다"** 로 읽는다. 실제로는 `UPZONE_TARGETS["자연녹지지역"]` 에
제2종일반주거지역이 **index 1 로 이미 들어 있었다** — 도시개발법으로 2종 상향이
가능한데도 `_pick_target` 이 *"정비/도시개발/공공주택지구는 보수적 1단계(첫 후보)"* 라며
targets[0] 만 골라 범위가 소멸했다.

★결함의 본체는 "보수적으로 골랐다"가 아니라 **모델의 보수성이 사실로 표시된 것**이다.

【파생의 축 = UPZONE_TARGETS 딕셔너리(함수 아님·파일 아님)】
검사 대상 용도지역을 손으로 적지 않고 **정본 딕셔너리에서 파생**한다. 새 용도지역이
추가되거나 후보가 늘어나면 **자동으로 감시망에 들어온다**(목록형이면 새 항목을 놓친다).
"""

from __future__ import annotations

import pytest

from apps.api.app.services.zoning.upzoning_potential import (
    UPZONE_TARGETS,
    UpzoningPotentialAnalyzer,
    _target_far_pct,
)

# ★파생: 후보가 2개 이상인 용도지역만이 "범위 소멸"을 드러낼 수 있다.
#   (후보 1개짜리는 상·하한이 같아도 정상이라 이 결함을 잡지 못한다 — 대조군으로 따로 쓴다.)
MULTI = sorted(z for z, t in UPZONE_TARGETS.items() if len([x for x in t if x]) >= 2)
SINGLE = sorted(z for z, t in UPZONE_TARGETS.items() if len([x for x in t if x]) == 1)


def _scenarios(zone: str) -> list[dict]:
    r = UpzoningPotentialAnalyzer().analyze(
        zone_type=zone,
        land_area_sqm=86_755.0,   # 실사례(오산 내삼미동 77필지 통합)
        parcel_count=77,
        adjacency_contiguous=True,
    )
    return r.get("scenarios") or []


def test_전제_다후보_용도지역이_실제로_존재한다():
    # ★공허한 초록 방지 — MULTI 가 비면 아래 파라미터라이즈가 **0건 실행**되고 조용히 통과한다.
    assert len(MULTI) >= 1, f"다후보 용도지역이 없다 — 파생이 깨졌다: {UPZONE_TARGETS!r}"
    assert "자연녹지지역" in MULTI, "사용자 신고 부지의 용도지역이 파생에서 빠졌다"


@pytest.mark.parametrize("zone", MULTI)
def test_상한은_최대후보에서_나온다(zone: str):
    """상한이 **첫 후보**에 묶여 있으면 실패한다 — 그게 종전 결함이다."""
    highs = [h for h in (_target_far_pct(t, None, None)[1] for t in UPZONE_TARGETS[zone]) if h]
    if not highs:
        pytest.skip(f"{zone}: 후보 용적률 미확보(법정범위 없음)")
    expected_max = round(max(highs))
    first_high = _target_far_pct(UPZONE_TARGETS[zone][0], None, None)[1]

    scs = _scenarios(zone)
    assert scs, f"{zone}: 시나리오가 0건 — 대상이 없어 통과하는 공허한 초록"
    for sc in scs:
        got = sc.get("expected_far_pct_high")
        assert got == expected_max, (
            f"{zone}/{sc.get('path_key')}: 상한 {got} != 최대후보 {expected_max} "
            f"(첫 후보 상한={first_high}) — 후보 하나로 좁혀 범위가 소멸했다"
        )


@pytest.mark.parametrize("zone", MULTI)
def test_상하한이_같은_숫자로_붕괴하지_않는다(zone: str):
    """`150.0~150.0%` 처럼 폭이 0이면 추정이 확정으로 읽힌다."""
    for sc in _scenarios(zone):
        lo, hi = sc.get("expected_far_pct_low"), sc.get("expected_far_pct_high")
        if lo is None or hi is None:
            continue
        assert hi > lo, f"{zone}/{sc.get('path_key')}: 폭 0 ({lo}~{hi}) — 범위가 소멸했다"


@pytest.mark.parametrize("zone", MULTI)
def test_후보_상세가_전부_실린다(zone: str):
    """화면이 '1단계 1종 / 최대 2종' 을 나눠 보이려면 후보별 값이 있어야 한다."""
    for sc in _scenarios(zone):
        cands = sc.get("target_zone_candidates") or []
        assert [c["target_zone"] for c in cands] == UPZONE_TARGETS[zone], (
            f"{zone}: 후보 상세가 정본과 다르다 — 화면이 최대 후보를 못 보인다"
        )
        assert sc.get("target_zone_max") == UPZONE_TARGETS[zone][-1]


@pytest.mark.parametrize("zone", SINGLE)
def test_대조군_단일후보는_최대가_곧_첫후보다(zone: str):
    """★없으면 위 단언들이 '무엇이든 최대를 쓴다'로도 통과할 수 있다.
    후보가 하나뿐인 용도지역은 상한이 **그 하나**여야 한다(범위를 날조하지 않는다)."""
    only = UPZONE_TARGETS[zone][0]
    hi = _target_far_pct(only, None, None)[1]
    for sc in _scenarios(zone):
        assert sc.get("target_zone_max") == only
        if hi is not None:
            assert sc.get("expected_far_pct_high") == round(hi)


def test_자연녹지는_제2종까지_도달한다():
    """사용자 신고의 정면 재현 — 도시개발법 경로가 1종에 갇히지 않는다."""
    scs = _scenarios("자연녹지지역")
    assert scs, "자연녹지 시나리오 0건"
    two = _target_far_pct("제2종일반주거지역", None, None)[1]
    assert any(sc["expected_far_pct_high"] == round(two) for sc in scs), (
        f"어느 경로도 제2종({two}%)에 도달하지 못한다 — 150% 천장이 그대로다"
    )
    assert any(sc.get("target_zone_max") == "제2종일반주거지역" for sc in scs)
