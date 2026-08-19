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
def test_상향여지는_최대후보에서_나온다(zone: str):
    """상향 여지가 **첫 후보**에 묶여 있으면 실패한다 — 그게 종전 결함이다.

    ★2026-08-19 필드 이동 — 이 단언은 원래 `expected_far_pct_high`(최상위 상한)에
      걸려 있었다. 그런데 그렇게 하면 **라벨과 값이 어긋난다**: `target_zone` 은
      경로별 대표 후보 하나(예: 정비사업→제2종일반주거지역, 법정 150~250)인데
      최상위 상한은 최대 후보(3종) 값 **300** 을 실어, *선언한 용도지역의 법정상한을
      넘는 값*이 화면에 나갔다. 조례 출처일 때는 더 나빴다 —
      `source='지자체 도시계획조례'` 인데 값이 **조례값 150 을 넘는 200** 이었다
      (출처를 붙인 채 그 출처를 넘는 값 = 거짓 근거).

    ★**의도는 그대로 지킨다.** "후보 하나로 좁혀 범위가 소멸했다"는 결함은 여전히
      금지된다 — 다만 그 최대값은 **자기 용도지역 라벨을 달고**(`upside_far_zone`)
      `upside_far_pct_high` 로 나온다. 값을 지운 게 아니라 **라벨을 붙인 것**이다.
    """
    highs = [h for h in (_target_far_pct(t, None, None)[1] for t in UPZONE_TARGETS[zone]) if h]
    if not highs:
        pytest.skip(f"{zone}: 후보 용적률 미확보(법정범위 없음)")
    expected_max = round(max(highs))
    first_high = _target_far_pct(UPZONE_TARGETS[zone][0], None, None)[1]

    scs = _scenarios(zone)
    assert scs, f"{zone}: 시나리오가 0건 — 대상이 없어 통과하는 공허한 초록"
    for sc in scs:
        got = sc.get("upside_far_pct_high")
        assert got == expected_max, (
            f"{zone}/{sc.get('path_key')}: 상향여지 {got} != 최대후보 {expected_max} "
            f"(첫 후보 상한={first_high}) — 후보 하나로 좁혀 범위가 소멸했다"
        )
        # ★그 값이 **어느 용도지역의 것인지** 함께 나와야 한다. 라벨 없는 숫자는
        #   그 자체로 위법값이 될 수 있다(이 필드 이동의 이유).
        assert sc.get("upside_far_zone"), f"{zone}/{sc.get('path_key')}: 상향여지 라벨 없음"


@pytest.mark.parametrize("zone", MULTI)
def test_최상위_상한은_선언한_용도지역_안에_있다(zone: str):
    """★위 단언의 짝 — 최상위 상한은 **`target_zone` 의 법정범위**를 넘지 않는다.

    이 두 단언이 함께 있어야 한다. 위만 있으면 "최대값을 어딘가에 실으면 통과"라
    라벨 불일치가 되살아나고, 아래만 있으면 "보수적으로 좁혀도 통과"라 종전 결함이
    되살아난다. **범위는 넓히되 라벨과 값은 같은 용도지역을 가리킨다.**
    """
    from apps.api.app.services.zoning.legal_zone_limits import legal_limits_for

    for sc in _scenarios(zone):
        legal = legal_limits_for(sc["target_zone"])
        assert legal, f"{zone}/{sc['path_key']}: target_zone 법정범위 미상"
        assert sc["expected_far_pct_high"] <= legal["max_far_pct"], (
            f"{zone}/{sc['path_key']}: target={sc['target_zone']} 상한 "
            f"{sc['expected_far_pct_high']} > 법정 {legal['max_far_pct']} — 라벨·값 불일치"
        )


@pytest.mark.parametrize("zone", MULTI)
def test_상하한이_같은_숫자로_붕괴하지_않는다(zone: str):
    """`150.0~150.0%` 처럼 폭이 0이면 추정이 확정으로 읽힌다.

    ★변이감사가 잡은 내 구멍: 처음엔 `if lo is None: continue` 를 뒀는데, 그러면
    **키 이름이 바뀌어 사라져도 조용히 건너뛰어** 통과했다(공허한 진리). 키의 **존재**를
    먼저 단언한다 — 없어지는 것도 결함이다.
    """
    for sc in _scenarios(zone):
        assert "expected_far_pct_low" in sc, f"{zone}: 하한 키가 없다 — 화면이 범위를 못 그린다"
        assert "expected_far_pct_high" in sc, f"{zone}: 상한 키가 없다"
        lo, hi = sc["expected_far_pct_low"], sc["expected_far_pct_high"]
        assert lo is not None and hi is not None, (
            f"{zone}/{sc.get('path_key')}: 상·하한이 비었다 ({lo}~{hi})"
        )
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
        # ★후보별 출처가 없으면 화면이 "법정범위인가 조례인가"를 말할 수 없다 —
        #   숫자만 있고 출처가 없는 표시는 이 저장소가 금지하는 형태다.
        # ★`strict=True` — 후보 수와 타깃 수가 어긋나면 **조용히 짧은 쪽에서 잘리지 않고** 죽는다.
        #   잘리면 검사하지 못한 후보가 생겨 "전수 확인"이 거짓이 된다(CI ruff B905).
        for c, tz in zip(cands, UPZONE_TARGETS[zone], strict=True):
            assert c.get("expected_far_source") == _target_far_pct(tz, None, None)[2], (
                f"{zone}/{tz}: 후보 용적률 출처가 비거나 어긋난다"
            )
            assert c.get("expected_far_pct_high") == (
                round(_target_far_pct(tz, None, None)[1])
                if _target_far_pct(tz, None, None)[1] is not None else None
            )


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
    """사용자 신고의 정면 재현 — 도시개발법 경로가 1종에 갇히지 않는다.

    ★필드는 `upside_far_pct_high` 다(위 참조). 화면은 "최대 제2종일반주거지역 상향 시
      250%" 로 그 값을 **용도지역과 함께** 보인다 — 숫자만 최상위에 올리면 라벨이
      1종인 채 2종 값을 말하게 된다.
    """
    scs = _scenarios("자연녹지지역")
    assert scs, "자연녹지 시나리오 0건"
    two = _target_far_pct("제2종일반주거지역", None, None)[1]
    assert any(sc.get("upside_far_pct_high") == round(two) for sc in scs), (
        f"어느 경로도 제2종({two}%)에 도달하지 못한다 — 150% 천장이 그대로다"
    )
    assert any(sc.get("upside_far_zone") == "제2종일반주거지역" for sc in scs)
    assert any(sc.get("target_zone_max") == "제2종일반주거지역" for sc in scs)
