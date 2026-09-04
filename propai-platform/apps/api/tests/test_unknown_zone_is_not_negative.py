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
    zone_pool_unknown,
)

#: ★**금지 어휘를 집합으로** — 첫 판은 리터럴 `"요건 미해당"` **하나**만 봤고, 그래서
#:   같은 뜻의 다른 문구(`"미해당"`·`"규모·용도 미해당"`)를 쓰는 **4행이 감시망 밖**이었다
#:   (적대 리뷰 H-1 · M-1). ★**목록은 곧 상한**이므로 `_rows()` 실측에서 파생시켜 검증한다.
DENIED_CONS = frozenset({"요건 미해당", "미해당", "규모·용도 미해당", "소규모 시가지 부적합"})

#: ★기대값을 **소스 상수에서 파생시키지 않는다**. 첫 판은 `UNKNOWN_ZONE_CONS` 를 임포트해
#:   단언했고, 그래서 그 상수를 `"요건 미해당 "`(끝 공백)으로 바꿔도 **초록이었다**
#:   — 화면에서 끝 공백은 안 보이므로 사용자에겐 **원래 결함과 글자까지 동일**하다(H-4/M3).
#:   **독립 리터럴**로 못 박는다.
EXPECTED_UNKNOWN_CONS = "용도지역 미확보 — 요건을 판정하지 못했습니다"

#: 「모른다」를 단정하는 금지 토큰 — `notes` 는 **비어 있음이 아니라 내용**으로 잠근다(H-4/M2).
FORBIDDEN_NOTE_TOKENS = ("주거지역 아님", "미해당", "부적합")

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


def _rows(zone, area=12000):
    ctx = _ctx(zone)
    ctx["total_area_sqm"] = ctx["area"] = area
    return _SIM._scenarios(ctx)


def _cons_of(rows, scheme):
    return next(r for r in rows if r["scheme"] == scheme)["cons"]


@pytest.mark.parametrize("unknown", ["", None, "   "])
def test_모름은_금지_어휘로_말하지_않는다(unknown):
    """★핵심 계약 — **닫힌 토큰**으로 본다(특정 문구를 못 박지 않는다)."""
    rows = _rows(unknown)
    assert rows, "시나리오가 하나도 안 나왔다 — 판정 거부(공허 진리 방지)"
    offenders = [
        r["scheme"] for r in rows
        if r.get("applicable") == "불가" and (DENIED_CONS & set(r.get("cons") or []))
        and UNKNOWN_ZONE_CONS in (r.get("cons") or [])
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
    assert EXPECTED_UNKNOWN_CONS in u_cons, f"미확보 사유가 없다: {u_cons}"
    # ★상수를 **독립 리터럴과 대조**한다 — 자기 상수를 단언하면 그 상수를 바꿔도 초록이다.
    assert UNKNOWN_ZONE_CONS == EXPECTED_UNKNOWN_CONS, "상수가 조용히 바뀌었다"
    assert not (DENIED_CONS & set(u_cons)), f"금지 어휘가 섞였다: {u_cons}"

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


def test_zone_pool_unknown_은_모름만_참이다_경계_양방향():
    """★한쪽만 걸면 반대쪽이 무제한이 된다 — **양방향**으로 본다."""
    for v in ["", None, "   ", "\t"]:
        assert zone_pool_unknown(v) is True, f"{v!r} 을 모름으로 안 본다"
    for v in ["제2종일반주거지역", "일반상업지역", "자연녹지지역", "미지정용도지역"]:
        assert zone_pool_unknown(v) is False, f"{v!r} 을 모름으로 본다(위양성)"


def test_blocked_reason_은_확보된_입력을_건드리지_않는다():
    """★헬퍼 단위 — **두 모집단**을 같은 실행에서."""
    base_cons, base_note = ["요건 미해당"], "원래 설명"
    same = blocked_reason(False, False, base_cons, base_note)
    assert same == (base_cons, base_note), "확보된 입력의 사유를 바꿨다"
    diff = blocked_reason(True, False, base_cons, base_note)
    assert diff != same, "미확보인데 사유가 그대로다"
    assert diff[0] == [UNKNOWN_ZONE_CONS] and diff[1].strip(), "사유·설명이 비었다"


# ★부채를 초록 안에 드러낸다(커밋 메시지에만 적으면 안 드러난다).
#   용도지역 미확보 시 **시나리오 1종이 목록에서 아예 사라진다**(역세권 장기전세주택 · 실측
#   주거 21종 → 모름 20종). 목록 구성 변경은 개수 계약을 건드려 회귀 범위가 커지므로 별건.
#   ★그리고 그것이 **법적으로 옳은지** 는 서울시 조례 원문 확인이 필요하다 — 지어내지 않는다.
def test_todo_사라지는_시나리오도_고지한다():
    pytest.skip("★부채: 용도지역 미확보 시 역세권 장기전세주택이 목록에서 조용히 사라진다(별건)")


def test_미확보_사유를_단_행의_설명은_모르는_것을_단정하지_않는다():
    """★**`notes` 는 「비어 있음」이 아니라 「내용」으로 잠근다**(적대 리뷰 H-4/M2).

    첫 판의 락은 `not notes.strip()` — **비어 있음만** 봤다. 그래서 `blocked_reason` 이
    **원래 note 를 그대로 유지**하도록 되돌리는 변이가 **SURVIVED** 했다. 그 변이 하에서
    미확보 부지의 가로주택정비사업은 `notes='주거지역 **아님** 또는 면적 1만㎡ 이상'` 을 낸다 —
    ***모르는 것을 「아니다」로 단정하는 문장***, 즉 **이 PR 이 없애려는 바로 그 거짓**이다.

    ★★그리고 나는 `FORBIDDEN_NOTE_TOKENS` 를 **선언만 하고 쓰지 않았다** — 이 세션이 계속
      고쳐 온 **「선언 ≠ 소비」** 를 락 자신이 재발시켰다. 내 변이가 그것을 잡았다.
    """
    rows = _rows("")
    flagged = [r for r in rows if EXPECTED_UNKNOWN_CONS in (r.get("cons") or [])]
    # ★공허 진리 방지 — 대상이 0이면 아래가 그 자체로 참이 된다.
    assert flagged, "미확보 사유를 단 행이 없다 — 판정 거부"
    for r in flagged:
        note = r.get("notes") or ""
        assert note.strip(), f"{r['scheme']}: 사유를 달아 놓고 설명이 없다"
        for tok in FORBIDDEN_NOTE_TOKENS:
            assert tok not in note, (
                f"{r['scheme']}: 미확보라 말해 놓고 설명이 «{tok}» 로 단정한다 — {note!r}"
            )


def test_주거_대조군과_갈린_행은_모두_그_사실을_말한다_파생형():
    """★**이 락이 H-1 을 직접 잡는다** — 첫 판은 축이 **리터럴 문구**라 4행을 놓쳤다.

    첫 판의 파생은 `"요건 미해당"` 이라는 **문구**를 축으로 삼았다. 그런데 결함이 사는 축은
    **「`res`/`com` 로 게이트되는 「불가」 분기」**다. 같은 뜻의 다른 문구(`"미해당"`·
    `"규모·용도 미해당"`)를 쓰는 자리가 **통째로 빠졌고**, 그중 둘은
    **내 커밋 메시지가 스스로 「뒤집힌다」고 적은 시나리오**였다(§D20 — 처방 범위 ≠ 결함 범위).

    ★그래서 축을 **문구가 아니라 「행동의 차이」**로 바꾼다:
      *"주거 대조군과 판정이 갈린 행은 **반드시** 그 사실을 말한다."*
      새 시나리오가 추가돼도 **자동으로 감시망에 든다** — 목록이 상한이 되지 않는다.
    """
    residential = {r["scheme"]: r for r in _rows("제2종일반주거지역")}
    unknown = {r["scheme"]: r for r in _rows("")}
    # ★공허 진리 방지 — 갈리는 행이 0이면 아래 루프가 0회 돌고 「위반 0」으로 통과한다.
    diverged = [
        k for k in residential
        if k in unknown and residential[k]["applicable"] != unknown[k]["applicable"]
    ]
    assert len(diverged) >= 3, f"갈리는 행이 {len(diverged)}건뿐 — 판정 거부(픽스처가 축을 못 태운다)"

    silent = [
        k for k in diverged
        if EXPECTED_UNKNOWN_CONS not in (unknown[k].get("cons") or [])
    ]
    assert not silent, (
        f"용도지역 때문에 판정이 갈렸는데 그 사실을 말하지 않는다: {silent} — "
        "축은 「문구」가 아니라 「주거 대조군과의 차이」다."
    )


def test_다른_축이_이미_막으면_참인_사유를_지우지_않는다():
    """★적대 리뷰 H-2 — 첫 판은 사유를 **대체**해 **참인 사유를 지우고 헛걸음으로 보냈다**.

    가로주택정비사업의 법정 요건은 **면적 1만㎡ 미만**이다. **5만㎡** 부지는 용도지역이
    무엇이든 불가이므로, 용도지역을 확인해도 결과가 안 바뀐다.
    ★그때 *"용도지역을 조회하지 못해 … 확인한 뒤 다시 보십시오"* 는 **거짓이자 헛걸음**이다.
    """
    big_unknown = {r["scheme"]: r for r in _rows("", area=50000)}
    big_commercial = {r["scheme"]: r for r in _rows("일반상업지역", area=50000)}
    u = big_unknown["가로주택정비사업"]
    c = big_commercial["가로주택정비사업"]
    assert EXPECTED_UNKNOWN_CONS not in (u.get("cons") or []), (
        "면적이 이미 답을 냈는데 «용도지역 미확보» 라 말한다 — 참인 사유를 지우고 헛걸음으로 보낸다."
    )
    # ★참인 사유가 **남아 있다** — 그리고 상업 대조군과 같다(용도지역이 판정을 안 가른다).
    assert (u.get("notes") or "") == (c.get("notes") or ""), "면적이 지배하는데 사유가 갈린다"
    assert "1만㎡" in (u.get("notes") or ""), f"면적 사유가 사라졌다: {u.get('notes')!r}"


def test_확보된_zones_가_있으면_미확보라_말하지_않는다_972_모집단():
    """★적대 리뷰 H-3 — `#972` 가 만드는 모집단을 잠근다.

    `#972`(우세 용도지역 **보류**)는 동률·규제성격 상이면 `primary_zone=None` 을 내는데
    **`zones` 에는 두 용도지역이 살아 있다.** 첫 판은 `zone` 하나만 봐서 그 부지에
    *"용도지역을 **조회하지 못해**"* 라고 말했다 — **확보됐는데 미확보라 말하는 것**이다.
    ★내 겹침 주장(*"조회 실패는 둘 다 빈다"*)은 **한 방향만 참**이었다.
    """
    rows = _SIM._scenarios({
        **_ctx(None), "zones": ["제2종일반주거지역", "일반공업지역"],
    })
    offenders = [
        r["scheme"] for r in rows
        if EXPECTED_UNKNOWN_CONS in (r.get("cons") or [])
    ]
    assert not offenders, f"zones 가 확보됐는데 미확보라 말한다: {offenders}"
    # ★음성 대조군 — 풀이 **통째로** 비면 여전히 말한다(위 단언이 «항상 침묵» 이 아님).
    empty = _SIM._scenarios({**_ctx(None), "zones": []})
    assert any(EXPECTED_UNKNOWN_CONS in (r.get("cons") or []) for r in empty), (
        "풀이 비었는데도 미확보라 말하지 않는다 — 위 단언이 공허해졌다."
    )


def test_미확보가_녹지_관리지역으로_승격되지_않는다_거울상():
    """★적대 리뷰 M-3 — 이 PR 이 없애려는 형태의 **반대 방향**.

    `if area >= 10000 or (not res and not com)` 는 **「녹지·관리지역」과 「모른다」를 뭉친다.**
    그래서 미확보 부지가 **조건부로 승격**되고 안내문이 *"녹지/관리지역"* 이라고 **단정**했다.
    ★「모른다」를 「아니다」로가 아니라 **「모른다」를 「그것이다」로** 옮긴 것이다.
    """
    small_unknown = {r["scheme"]: r for r in _rows("", area=1800)}
    r = small_unknown["대지조성사업"]
    assert r["applicable"] == "불가", f"미확보인데 승격됐다: {r['applicable']}"
    assert "녹지" not in (r.get("notes") or ""), f"모르는 용도지역을 단정했다: {r.get('notes')!r}"
