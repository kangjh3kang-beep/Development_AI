"""용도지역 **미확보**를 「요건에 해당하지 않음」으로 번역하지 않는다.

## 무엇이 잘못돼 있었나 (2026-09-05 · `_scenarios()` 직접 실행)

`_is_residential`·`_is_commercial` 이 `bool` 이라 **「주거가 아니다」와 「모른다」를 같은 `False`**
로 뭉갰다. 그래서 용도지역 조회가 실패한 부지가 **상업지역과 완전히 같은 판정**을 받았다:

    주거(대조)      21종 · 추진가능 16 · 불가 5
    상업            20종 · 추진가능 12 · 불가 8
    ★조회실패 ''    20종 · 추진가능 12 · 불가 8   ← **상업과 동일**
    ★조회실패 None  20종 · 추진가능 12 · 불가 8   ← **상업과 동일**

★**그리고 그 「불가」의 사유가 `["요건 미해당"]` 이고 `notes` 가 비어 있었다.**
「요건에 해당하지 않는다」와 「요건을 **판정할 수 없다**」는 **다른 사실**이고,
전자로 말하면 사용자는 **확인할 것이 없다고 읽는다.**

★이 파일이 잠그는 것 — **판정값이 아니라 사유**다. `applicable` 은 안 바꾼다
(프론트가 `APP_STYLE[applicable] || APP_STYLE["불가"]` 라 새 판정어는 「불가」로 떨어지고,
「가능」으로 올리는 것은 **날조**다).
"""
from __future__ import annotations

import pytest

from app.services.development.scenario_simulator import (
    UNKNOWN_ZONE_CONS,
    DevelopmentScenarioSimulator,
    blocked_reason,
    zone_is_unknown,
)

_SIM = DevelopmentScenarioSimulator()


def _ctx(zone):
    """★`zone` 외 **모든 축이 동일**하다 — 그래야 그 축만이 답을 가른다."""
    return {
        "primary_zone": zone, "zones": ([zone] if zone else []),
        "total_area_sqm": 12000, "area": 12000, "parcel_count": 3,
        "region": "서울특별시", "multi": True, "integration_feasible": True,
        "far": 250, "bcr": 60, "near_station": True, "near_station_m": 300,
        "buildings": {}, "block_aging": {},
    }


def _rows(zone):
    return _SIM._scenarios(_ctx(zone))


def _cons_of(rows, scheme):
    return next(r for r in rows if r["scheme"] == scheme)["cons"]


@pytest.mark.parametrize("unknown", ["", None, "   "])
def test_모름은_요건_미해당이라_말하지_않는다(unknown):
    """★핵심 계약 — **닫힌 토큰**으로 본다(특정 문구를 못 박지 않는다)."""
    rows = _rows(unknown)
    assert rows, "시나리오가 하나도 안 나왔다 — 판정 거부(공허 진리 방지)"
    offenders = [
        r["scheme"] for r in rows
        if r.get("applicable") == "불가" and "요건 미해당" in (r.get("cons") or [])
    ]
    assert not offenders, (
        f"용도지역 미확보인데 «요건 미해당» 이라 말한다: {offenders} — "
        "「해당하지 않음」과 「판정하지 못함」은 다른 사실이다."
    )


def test_두_모집단이_갈린다_모름과_상업이_같은_답을_받지_않는다():
    """★**이것이 이 PR 의 존재 이유**다 — 종전에는 두 모집단이 **완전히 동일**했다.

    ★한 모집단만 단언하면 «무엇을 해도 그렇다» 는 공허한 참이 된다. **대비**시킨다.
    """
    unknown = _rows("")
    commercial = _rows("일반상업지역")

    # ① 「모름」은 미확보 사유를 말한다
    u_cons = _cons_of(unknown, "모아주택/모아타운")
    assert UNKNOWN_ZONE_CONS in u_cons, f"미확보 사유가 없다: {u_cons}"

    # ② ★상업은 **종전 그대로**다 — 회귀가 아니라는 근거(음성 대조군)
    c_cons = _cons_of(commercial, "모아주택/모아타운")
    assert "요건 미해당" in c_cons, f"상업의 사유가 바뀌었다(회귀): {c_cons}"
    assert UNKNOWN_ZONE_CONS not in c_cons, "상업인데 미확보라 말한다(위양성)"

    # ③ 두 사유가 **실제로 다르다** — 같으면 위 단언들이 아무것도 안 가른다
    assert u_cons != c_cons


def test_모름의_불가에는_사유가_반드시_있다_무언_실패_금지():
    """★종전에는 「불가」인데 `notes` 가 **빈 문자열**이었다 — 왜 안 되는지 아무 말도 안 했다."""
    rows = _rows("")
    silent = [
        r["scheme"] for r in rows
        if UNKNOWN_ZONE_CONS in (r.get("cons") or []) and not (r.get("notes") or "").strip()
    ]
    assert not silent, f"미확보 사유를 달아 놓고 설명이 없다: {silent}"


def test_용도지역이_확보되면_출력이_종전_그대로다_회귀_아님의_근거():
    """★**바이트 동일** — 확보된 입력에서는 헬퍼가 인자를 그대로 돌려준다."""
    for zone in ["제2종일반주거지역", "일반상업지역", "자연녹지지역"]:
        rows = _rows(zone)
        assert rows, f"{zone}: 시나리오 0종 — 판정 거부"
        for r in rows:
            assert UNKNOWN_ZONE_CONS not in (r.get("cons") or []), (
                f"{zone}: 용도지역이 확보됐는데 미확보 사유가 붙었다 — 위양성이다."
            )


def test_zone_is_unknown_은_모름만_참이다_경계_양방향():
    """★한쪽만 걸면 반대쪽이 무제한이 된다 — **양방향**으로 본다."""
    for v in ["", None, "   ", "\t"]:
        assert zone_is_unknown(v) is True, f"{v!r} 을 모름으로 안 본다"
    for v in ["제2종일반주거지역", "일반상업지역", "자연녹지지역", "미지정용도지역"]:
        assert zone_is_unknown(v) is False, f"{v!r} 을 모름으로 본다(위양성)"


def test_blocked_reason_은_확보된_입력을_건드리지_않는다():
    """★헬퍼 단위 — **두 모집단**을 같은 실행에서."""
    base_cons, base_note = ["요건 미해당"], "원래 설명"
    same = blocked_reason("제2종일반주거지역", base_cons, base_note)
    assert same == (base_cons, base_note), "확보된 입력의 사유를 바꿨다"
    diff = blocked_reason("", base_cons, base_note)
    assert diff != same, "미확보인데 사유가 그대로다"
    assert diff[0] == [UNKNOWN_ZONE_CONS] and diff[1].strip(), "사유·설명이 비었다"


# ★부채를 초록 안에 드러낸다(커밋 메시지에만 적으면 안 드러난다).
#   용도지역 미확보 시 **시나리오 1종이 목록에서 아예 사라진다**(역세권 장기전세주택 · 실측
#   주거 21종 → 모름 20종). 목록 구성 변경은 개수 계약을 건드려 회귀 범위가 커지므로 별건.
#   ★그리고 그것이 **법적으로 옳은지** 는 서울시 조례 원문 확인이 필요하다 — 지어내지 않는다.
def test_todo_사라지는_시나리오도_고지한다():
    pytest.skip("★부채: 용도지역 미확보 시 역세권 장기전세주택이 목록에서 조용히 사라진다(별건)")
