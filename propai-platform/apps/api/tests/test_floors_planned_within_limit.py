"""층수를 **제약 안에서 계획**하는지 잠근다 (2026-08-21 · 사용자 화면 검증에서 발견).

## 무엇이 있었나

자연녹지(건폐 20% · 실효 용적 80%) 164,823㎡ 부지에서 화면이 이렇게 나왔다.

    단독주택  연면적 39,887.2평  679세대  4층  →  **부적합**
    전원주택  연면적 39,887.2평  560세대  4층  →  **부적합**
    사유: 층수제한: 계획 4층 > 상한 3층 (M10/M11)

층수를 `연면적 ÷ 건축면적` 으로 **역산만** 하고 유형별 상한(`MAX_FLOORS`)은 **사후 검증**
에서만 봤다. **시스템이 스스로 규칙 위반 계획을 세우고 자기 규칙으로 탈락**시킨 것이다.

더 나쁜 것은 **연면적이 4층 기준 그대로**였다는 점이다 — 3층이면 약 29,915평인데
39,887평으로 표시됐고, 세대수·주차·공사비가 전부 **실현 불가능한 값** 위에서 계산됐다.

## ★2026-08-23 — 이 파일이 잠그던 전제가 **뒤집혔다**

위 진단은 절반만 맞았다. 배선(제약을 계획에 반영)은 옳았지만 **상한값 자체가 틀렸다**:
`M10`(단독)·`M11`(전원)의 **3층**은 건축법 시행령 별표1 제1호 **나목·다목(다중·다가구주택)**
기준이고, **가목(단독주택)에는 유형 자체의 층수 제한이 없다.**

그래서 `MAX_FLOORS` 는 이제 `LegalLimit`(값 + 법령근거)을 담고, 세 상태를 **구분**한다.

    미등재            → 근거 미확인      → 깎지 않는다(그러나 침묵하지도 않는다)
    등재 + unlimited  → 법이 제한 안 함  → 깎지 않는다(근거 있음)
    등재 + 값 있음    → 그 값으로 캡

**이 파일도 그에 맞춰 대상을 바꿨다.** 종전에는 `M10`/`M11` 이 "캡이 걸리는 유형"이었지만
이제는 **캡 없는 유형**이라, 캡 동작을 태우려면 실제로 캡이 있는 유형이 필요하다 —
현재 표에서 값을 가진 유형은 `M12`(연립주택, 별표1 제2호 나목, 4층)뿐이다.
★대상을 바꾼 것은 락을 약화시킨 것이 아니다. 오히려 아래 `test_제천_실제조건에서_단독주택은_깎이지_않는다`
가 **이번 사고의 실제 조건**을 그대로 태워, 3층 캡이 되살아나면 즉시 빨강이 된다.

## 이 파일이 잠그는 것

1. 계획 층수가 유형 상한을 **넘지 않는다**(캡이 실제로 있는 유형에서)
2. 층수가 깎이면 **연면적도 함께 내려간다**(그러지 않으면 숫자가 거짓이 된다)
3. 그때 **용적률 표시도 함께** 내려간다(같은 화면이 두 계획을 가리키지 않게)
4. `unlimited` 유형은 **깎지 않는다**(대조군 — 무조건 깎는 구현에서도 초록이 되는 것 방지)
5. ★**제천 실제 조건에서 단독주택이 깎이지 않는다**(이번 사고의 회귀 락)
"""

from __future__ import annotations

import pytest

from app.services.zoning.development_feasibility_validator import MAX_FLOORS


def _cap_of(dev_type: str) -> int | None:
    """유형의 **실효 캡**. 미등재·`unlimited` 는 둘 다 "깎지 않는다"(=None).

    ★서비스(`comprehensive_analysis_service`)의 `_cap` 유도와 **같은 식**이어야 한다 —
      다르면 이 파일은 서비스가 아니라 자기 자신을 검증하게 된다.
    """
    limit = MAX_FLOORS.get(dev_type)
    return None if (limit is None or limit.unlimited) else int(limit.value)


def _plan(land_area: float, bcr: float, far: float, dev_type: str) -> dict:
    """서비스와 **같은 식**으로 계획을 만든다(로직 대조용 축소판)."""
    building_area = land_area * (bcr / 100)
    gfa_by_far = land_area * (far / 100)
    floors_by_far = max(1, round(gfa_by_far / building_area)) if building_area > 0 else 1
    cap = _cap_of(dev_type)
    floors = max(1, min(floors_by_far, cap) if cap else floors_by_far)
    capped = floors < floors_by_far
    gfa = min(gfa_by_far, building_area * floors) if building_area > 0 else gfa_by_far
    return {
        "floors": floors, "gfa": gfa, "capped": capped,
        "far": (gfa / land_area * 100) if land_area else 0,
        "floors_by_far": floors_by_far,
    }


# 화면에 나온 실제 조건(제천 자연녹지) — 이번 사고가 난 그 값이다.
_LAND, _BCR, _FAR = 164_823.0, 20.0, 80.0

#: 캡 동작을 태울 유형 — 현재 표에서 **값을 가진 유일한 유형**.
#  ★목록을 손으로 적지 않고 표에서 **파생**시킨다. 새 유형에 캡이 생기면 자동으로 들어온다
#    (사람이 센 목록이 곧 상한이 되는 것을 막는다).
_CAPPED_TYPES = sorted(k for k in MAX_FLOORS if _cap_of(k) is not None)

#: 캡을 실제로 물리려면 역산 층수가 캡을 넘어야 한다. 건폐 20% 에 용적 120% → 6층.
_FAR_OVER_CAP = 120.0


@pytest.mark.parametrize("dev_type", _CAPPED_TYPES)
def test_계획_층수가_유형_상한을_넘지_않는다(dev_type: str) -> None:
    cap = _cap_of(dev_type)
    assert cap, f"{dev_type} 에 층수 상한이 없다 — 이 케이스는 아무것도 검증하지 않는다"

    plan = _plan(_LAND, _BCR, _FAR_OVER_CAP, dev_type)
    # 전제: 제약이 없었다면 상한을 넘었어야 한다(안 넘으면 이 락은 공허하다).
    assert plan["floors_by_far"] > cap, (
        f"이 조건에서는 역산 층수({plan['floors_by_far']})가 상한({cap})을 넘지 않는다 — "
        "픽스처가 두 경우를 가르지 못한다"
    )
    assert plan["floors"] <= cap, f"상한 {cap}층을 넘겨 계획했다: {plan['floors']}층"


@pytest.mark.parametrize("dev_type", _CAPPED_TYPES)
def test_층수가_깎이면_연면적과_용적률도_함께_내려간다(dev_type: str) -> None:
    """★이게 핵심이다. 층수만 깎고 연면적을 그대로 두면 **숫자가 거짓**이 된다."""
    plan = _plan(_LAND, _BCR, _FAR_OVER_CAP, dev_type)
    assert plan["capped"], "이 조건에서 층수가 깎이지 않았다 — 픽스처가 잘못됐다"

    gfa_by_far = _LAND * (_FAR_OVER_CAP / 100)
    assert plan["gfa"] < gfa_by_far, (
        f"층수는 깎였는데 연면적이 그대로다 — 실현 불가능한 값이다: {plan['gfa']:,.0f}㎡"
    )
    # 건축면적 × 층수 와 정확히 일치해야 한다.
    assert plan["gfa"] == pytest.approx(_LAND * (_BCR / 100) * plan["floors"])
    assert plan["far"] < _FAR_OVER_CAP, f"연면적은 줄었는데 용적률 표시가 그대로다: {plan['far']}%"


def test_상한이_없는_유형은_깎지_않는다_대조군() -> None:
    """★위 락들은 *무조건 깎는* 구현에서도 초록이다. 정상 경로를 함께 본다."""
    no_limit = [k for k, v in MAX_FLOORS.items() if v.unlimited]
    assert no_limit, "상한 없는 유형이 하나도 없다 — 이 대조군은 아무것도 검증하지 않는다"

    dev_type = no_limit[0]
    plan = _plan(_LAND, _BCR, _FAR_OVER_CAP, dev_type)
    assert not plan["capped"], f"{dev_type} 은 상한이 없는데 깎였다"
    assert plan["gfa"] == pytest.approx(_LAND * (_FAR_OVER_CAP / 100)), "상한이 없는데 연면적을 줄였다"
    assert plan["far"] == pytest.approx(_FAR_OVER_CAP)


def test_미등재_유형도_깎지_않는다_대조군() -> None:
    """★'미등재'(근거 미확인)와 'unlimited'(법이 제한 안 함)는 **뜻이 다르지만**
    계획을 깎지 않는다는 **행동은 같다**. 둘 다 태워야 한 쪽만 고친 구현이 걸린다.
    """
    unregistered = "M13"  # 도시형생활주택 — 유형별 규율이 달라 단일 상한 미확정
    assert unregistered not in MAX_FLOORS, (
        f"{unregistered} 이 표에 등재됐다 — 이 대조군이 무의미해졌으니 미등재인 다른 유형으로 바꿔라"
    )
    plan = _plan(_LAND, _BCR, _FAR_OVER_CAP, unregistered)
    assert not plan["capped"], "미등재 유형인데 깎였다 — 근거 없이 제약을 적용했다"


def test_제천_실제조건에서_단독주택은_깎이지_않는다() -> None:
    """★이번 사고(2026-08-23)의 **회귀 락** — 근거 없는 3층이 되살아나면 여기서 죽는다.

    제천 자연녹지 164,823㎡ · 건폐 20% · 실효 용적 80% → 역산 4층.
    종전에는 근거 없는 3층 캡이 이걸 깎아 연면적을 39,887평 → 29,915평으로 **과소** 산출했다.
    """
    for dev_type in ("M10", "M11"):
        plan = _plan(_LAND, _BCR, _FAR, dev_type)
        assert plan["floors_by_far"] == 4, f"픽스처 전제가 깨졌다: 역산 {plan['floors_by_far']}층"
        assert not plan["capped"], (
            f"{dev_type}(단독·전원주택)의 4층 계획이 다시 깎였다 — "
            "3개 층 이하는 다중·다가구주택 기준이다(건축법 시행령 별표1 제1호 가목)"
        )
        assert plan["far"] == pytest.approx(_FAR), "깎이지 않았는데 용적률이 내려갔다"


def test_상한_이내이면_역산값을_그대로_쓴다_대조군() -> None:
    """저밀 조건(용적률이 낮아 층수가 상한 이내)에서는 아무것도 깎이지 않아야 한다."""
    dev_type = _CAPPED_TYPES[0]
    cap = _cap_of(dev_type)
    plan = _plan(_LAND, _BCR, 40.0, dev_type)  # 40% ÷ 20% = 2층
    assert plan["floors"] == 2, f"역산 2층이어야 한다: {plan['floors']}"
    assert plan["floors"] <= cap, "픽스처가 상한을 넘는다 — 이 대조군은 상한 이내여야 한다"
    assert not plan["capped"]
    assert plan["far"] == pytest.approx(40.0)
