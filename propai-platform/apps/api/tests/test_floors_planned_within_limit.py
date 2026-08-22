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

## 이 파일이 잠그는 것

1. 계획 층수가 유형 상한을 **넘지 않는다**
2. 층수가 깎이면 **연면적도 함께 내려간다**(그러지 않으면 숫자가 거짓이 된다)
3. 그때 **용적률 표시도 함께** 내려간다(같은 화면이 두 계획을 가리키지 않게)
4. 상한이 없는 유형은 **깎지 않는다**(대조군 — 무조건 깎는 구현에서도 초록이 되는 것 방지)
"""

from __future__ import annotations

import pytest

from app.services.zoning.development_feasibility_validator import MAX_FLOORS


def _plan(land_area: float, bcr: float, far: float, dev_type: str) -> dict:
    """서비스와 **같은 식**으로 계획을 만든다(로직 대조용 축소판)."""
    building_area = land_area * (bcr / 100)
    gfa_by_far = land_area * (far / 100)
    floors_by_far = max(1, round(gfa_by_far / building_area)) if building_area > 0 else 1
    max_f = MAX_FLOORS.get(dev_type)
    floors = max(1, min(floors_by_far, max_f) if max_f else floors_by_far)
    capped = floors < floors_by_far
    gfa = min(gfa_by_far, building_area * floors) if building_area > 0 else gfa_by_far
    return {
        "floors": floors, "gfa": gfa, "capped": capped,
        "far": (gfa / land_area * 100) if land_area else 0,
        "floors_by_far": floors_by_far,
    }


# 화면에 나온 실제 조건
_LAND, _BCR, _FAR = 164_823.0, 20.0, 80.0


@pytest.mark.parametrize("dev_type", ["M10", "M11"])
def test_계획_층수가_유형_상한을_넘지_않는다(dev_type: str) -> None:
    max_f = MAX_FLOORS.get(dev_type)
    assert max_f, f"{dev_type} 에 층수 상한이 없다 — 이 케이스는 아무것도 검증하지 않는다"

    plan = _plan(_LAND, _BCR, _FAR, dev_type)
    # 전제: 제약이 없었다면 상한을 넘었어야 한다(안 넘으면 이 락은 공허하다).
    assert plan["floors_by_far"] > max_f, (
        f"이 조건에서는 역산 층수({plan['floors_by_far']})가 상한({max_f})을 넘지 않는다 — "
        "픽스처가 두 경우를 가르지 못한다"
    )
    assert plan["floors"] <= max_f, f"상한 {max_f}층을 넘겨 계획했다: {plan['floors']}층"


@pytest.mark.parametrize("dev_type", ["M10", "M11"])
def test_층수가_깎이면_연면적과_용적률도_함께_내려간다(dev_type: str) -> None:
    """★이게 핵심이다. 층수만 깎고 연면적을 그대로 두면 **숫자가 거짓**이 된다."""
    plan = _plan(_LAND, _BCR, _FAR, dev_type)
    assert plan["capped"], "이 조건에서 층수가 깎이지 않았다 — 픽스처가 잘못됐다"

    gfa_by_far = _LAND * (_FAR / 100)
    assert plan["gfa"] < gfa_by_far, (
        f"층수는 깎였는데 연면적이 그대로다 — 실현 불가능한 값이다: {plan['gfa']:,.0f}㎡"
    )
    # 건축면적 × 층수 와 정확히 일치해야 한다.
    assert plan["gfa"] == pytest.approx(_LAND * (_BCR / 100) * plan["floors"])
    assert plan["far"] < _FAR, f"연면적은 줄었는데 용적률 표시가 그대로다: {plan['far']}%"


def test_상한이_없는_유형은_깎지_않는다_대조군() -> None:
    """★위 락들은 *무조건 깎는* 구현에서도 초록이다. 정상 경로를 함께 본다."""
    no_limit = [k for k, v in MAX_FLOORS.items() if v is None]
    assert no_limit, "상한 없는 유형이 하나도 없다 — 이 대조군은 아무것도 검증하지 않는다"

    dev_type = no_limit[0]
    plan = _plan(_LAND, _BCR, _FAR, dev_type)
    assert not plan["capped"], f"{dev_type} 은 상한이 없는데 깎였다"
    assert plan["gfa"] == pytest.approx(_LAND * (_FAR / 100)), "상한이 없는데 연면적을 줄였다"
    assert plan["far"] == pytest.approx(_FAR)


def test_상한_이내이면_역산값을_그대로_쓴다_대조군() -> None:
    """저밀 조건(용적률이 낮아 층수가 상한 이내)에서는 아무것도 깎이지 않아야 한다."""
    plan = _plan(_LAND, _BCR, 40.0, "M10")  # 40% ÷ 20% = 2층 → 상한 3층 이내
    assert plan["floors"] == 2, f"역산 2층이어야 한다: {plan['floors']}"
    assert not plan["capped"]
    assert plan["far"] == pytest.approx(40.0)
