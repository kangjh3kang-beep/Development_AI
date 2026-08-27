"""효과기 **발화 관측**의 잠금.

## 왜 필요한가 (라이브 실측 2026-08-27 12:33 UTC)

`effector_reach` 는 *"닿지 않는 것을 닿지 않는다고 적는 데 값어치가 있다"* 고 스스로
적어 뒀는데, **거울상**(발화하지 않는 것을 발화하지 않는다고 적기)이 없었다.

    threshold_relax      PRODUCT    47건   ★66시간 휴면   ← 제품에 닿는 **유일한** 효과기
    threshold_autotune   SELF      441건   ★493시간 휴면
    feature_toggle       SELF        0건   ★한 번도 발화한 적 없음
    stale_reanalysis     NONE        0건   ★한 번도 발화한 적 없음
    prompt_ab_adopt      NONE        0건   ★한 번도 발화한 적 없음
    (대조군 `zzz_nope` total=0 — 조회기 생존 확인)

## 이 파일이 잠그는 것

1. **파생형** — 선언 표에서 전수를 뽑는다. 손 목록이면 새 효과기가 감시망 밖에 남는다.
2. **두 모집단** — `never_fired` / `dormant` / `active` 가 **서로 다른 값**을 낸다.
   한 모집단만 단언하면 "전부 active" 도 "전부 never" 도 통과한다.
3. **양방향** — 선언에 없는데 이벤트에는 있는 액션(`undeclared`)도 나온다.
   한 방향만 보면 낡은 선언을 영원히 못 잡는다.
4. ★**라벨과 원값을 함께** — `state` 는 임계에 의존하므로, 사람이 동의하지 않을 수 있게
   `hours_since` 를 반드시 싣는다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.growth import effector_firing as ef
from app.services.growth.effector_reach import EFFECTORS, Reach

NOW = datetime(2026, 8, 27, 12, 33, tzinfo=UTC)


# ═══════════════════════════════════════════════════════════════════════════
# 순수 판정 — 세 상태가 **서로 다르다**
# ═══════════════════════════════════════════════════════════════════════════
def test_never_fired_is_not_dormant() -> None:
    """★"한 번도 안 했다"와 "하다가 멈췄다"는 **다른 사실**이다.

    되살리는 변이: `total <= 0` 분기를 지우면 0건이 `dormant` 로 뭉개진다 —
    원인도 처방도 다른 둘이 같은 라벨을 받는다.
    """
    assert ef.classify(0, None) == ef.STATE_NEVER
    assert ef.classify(0, 9999.0) == ef.STATE_NEVER, "0건인데 시간으로 판정했다"
    assert ef.classify(47, 500.0) == ef.STATE_DORMANT
    assert ef.STATE_NEVER != ef.STATE_DORMANT


def test_three_states_split() -> None:
    """★세 모집단이 **서로 다른 값**을 낸다(하나로 뭉치는 구현 방지)."""
    got = {
        ef.classify(0, None),
        ef.classify(10, ef.DORMANT_HOURS + 1),
        ef.classify(10, 1.0),
    }
    assert got == {ef.STATE_NEVER, ef.STATE_DORMANT, ef.STATE_ACTIVE}, got


def test_dormant_boundary_is_inclusive_both_ways() -> None:
    """★경계를 **양방향**으로 건다 — 한쪽만 걸면 반대쪽이 무제한이 된다."""
    assert ef.classify(1, ef.DORMANT_HOURS) == ef.STATE_DORMANT
    assert ef.classify(1, ef.DORMANT_HOURS - 0.1) == ef.STATE_ACTIVE


def test_states_are_a_closed_set() -> None:
    """새 상태를 늘리면 이 단언이 라벨 등재를 요구한다."""
    for t, h in [(0, None), (1, 1.0), (1, 9999.0)]:
        assert ef.classify(t, h) in ef.ALL_STATES


# ═══════════════════════════════════════════════════════════════════════════
# 배선 — 선언 표에서 **파생**하는가
# ═══════════════════════════════════════════════════════════════════════════
class _Row(tuple):
    pass


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    """`platform_events` 집계 질의에만 응답한다."""

    def __init__(self, rows):
        self.rows = rows
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = " ".join(str(getattr(stmt, "text", stmt)).split())
        self.sql.append(s)
        return _Res(self.rows)


@pytest.mark.asyncio
async def test_every_declared_effector_appears_even_with_zero_firings() -> None:
    """★**핵심** — 발화 0건인 효과기도 **행으로 나온다**.

    되살리는 변이: 이벤트 집계만 순회하면(`for k in fired`) 0건 효과기가 **사라진다** —
    바로 그 사실을 보이려고 만든 표면인데 그 사실만 안 보이게 된다.
    """
    # 실측에서 실제로 잡힌 둘만 이벤트에 넣는다.
    db = _FakeDb([("threshold_relax", 47, NOW - timedelta(hours=66)),
                  ("threshold_autotune", 441, NOW - timedelta(hours=493))])
    out = await ef.firing_status(db, now=NOW)
    keys = {r["key"] for r in out["effectors"]}
    declared = {e.key for e in EFFECTORS}
    assert keys == declared, f"선언과 출력이 다르다 — 없는 것: {declared - keys}"
    assert len(declared) >= 5, "★선언 표가 비정상적으로 작다 — 추출기가 죽었다"

    zero = [r for r in out["effectors"] if r["total"] == 0]
    assert zero, "★발화 0건 효과기가 한 행도 없다 — 0건을 버리는 구현이다"
    assert all(r["state"] == ef.STATE_NEVER for r in zero)


@pytest.mark.asyncio
async def test_undeclared_action_surfaces_the_other_direction() -> None:
    """★양방향 — 표에 **없는데** 이벤트에는 있는 액션을 잡는다(선언이 낡았다는 신호)."""
    db = _FakeDb([("brand_new_action_2099", 3, NOW - timedelta(hours=1))])
    out = await ef.firing_status(db, now=NOW)
    und = out["undeclared"]
    assert [u["key"] for u in und] == ["brand_new_action_2099"]
    assert und[0]["state"] == ef.STATE_UNDECLARED
    # ★반대 방향도 동시에 성립해야 한다 — 선언된 것은 여전히 0건으로 나온다.
    assert all(r["total"] == 0 for r in out["effectors"])


@pytest.mark.asyncio
async def test_declared_and_measured_sit_in_the_same_row() -> None:
    """★선언(`reach`)과 실측(`state`)을 **같은 행에** 둔다 — 따로 두면 아무도 대조하지 않는다."""
    db = _FakeDb([("threshold_relax", 47, NOW - timedelta(hours=66))])
    out = await ef.firing_status(db, now=NOW)
    row = next(r for r in out["effectors"] if r["key"] == "threshold_relax")
    assert row["declared_reach"] == str(Reach.PRODUCT)
    # ★66시간은 임계(72) **미만**이라 `active` 가 맞다 — 라벨은 그렇게 나온다.
    #   ★그런데 이 작업을 촉발한 라이브 관측이 정확히 그 66시간이었다.
    #     라벨이 그 사례를 안 잡는다는 것을 여기서 **명시적으로 잠근다** —
    #     임계를 66 아래로 내려 하나를 잡게 만드는 것은 관측에 지표를 맞추는 것이다.
    assert row["state"] == ef.STATE_ACTIVE
    # ★그래서 **원값**이 진실이다. 라벨에 동의하지 않을 수 있게 항상 싣는다.
    assert row["hours_since"] == pytest.approx(66.0, abs=0.2)
    assert row["last_fired_at"], "최신 발화 시각이 비었다"
    # ★임계 없는 사실이 요약에 올라온다 — 사람이 이걸 보고 판단한다.
    assert out["summary"]["product_reaching_max_hours_since"] == pytest.approx(66.0, abs=0.2)


@pytest.mark.asyncio
async def test_product_reaching_active_differs_from_declared() -> None:
    """★**이 표면의 존재 이유** — 선언은 초록인데 실제는 죽어 있는 것을 가른다.

    되살리는 변이: `product_reaching_active` 를 `product_reaching_declared` 와
    같은 식으로 만들면 두 수가 **영원히 같아져** 아무것도 말하지 않는다.
    """
    # 제품에 닿는 효과기가 임계를 넘게 휴면 → declared 1, active 0
    dormant = _FakeDb([("threshold_relax", 47, NOW - timedelta(hours=ef.DORMANT_HOURS + 10))])
    a = (await ef.firing_status(dormant, now=NOW))["summary"]
    assert a["product_reaching_declared"] >= 1
    assert a["product_reaching_active"] == 0, "★휴면인데 살아 있다고 셌다"

    # 같은 효과기가 방금 발화 → 둘이 같아진다(두 모집단)
    fresh = _FakeDb([("threshold_relax", 48, NOW - timedelta(hours=1))])
    b = (await ef.firing_status(fresh, now=NOW))["summary"]
    assert b["product_reaching_active"] == b["product_reaching_declared"]
    assert a["product_reaching_active"] != b["product_reaching_active"], (
        "★두 모집단이 같은 값 — 이 지표는 아무것도 구별하지 못한다"
    )


@pytest.mark.asyncio
async def test_query_reads_the_medium_that_both_layers_write() -> None:
    """★L0·L1 이 **같은 매체**에 쓴다 — 한쪽만 보면 절반을 놓친다.

    `heal_actions`(L0)도 `feature_flags._emit_l1_event`(L1)도
    `event_type='heal_action'` 으로 쓴다(소스 실측). 질의가 그 값을 써야 한다.
    """
    db = _FakeDb([])
    await ef.firing_status(db, now=NOW)
    assert db.sql, "★질의를 하나도 안 했다"
    joined = " ".join(db.sql)
    assert "platform_events" in joined
    assert "action_type" in joined
    assert ef.EVENT_TYPE == "heal_action"


@pytest.mark.asyncio
async def test_summary_counts_match_rows() -> None:
    """요약이 행과 어긋나지 않는다(집계를 따로 세는 구현 방지)."""
    db = _FakeDb([("threshold_relax", 47, NOW - timedelta(hours=66)),
                  ("threshold_autotune", 441, NOW - timedelta(hours=1))])
    out = await ef.firing_status(db, now=NOW)
    rows = out["effectors"]
    s = out["summary"]
    assert s["declared"] == len(rows)
    for st in (ef.STATE_NEVER, ef.STATE_DORMANT, ef.STATE_ACTIVE):
        assert s[st] == sum(1 for r in rows if r["state"] == st), st
    assert s[ef.STATE_NEVER] + s[ef.STATE_DORMANT] + s[ef.STATE_ACTIVE] == len(rows)


def test_dormant_threshold_is_documented_as_a_judgment_not_a_measurement() -> None:
    """★임계를 낮춰 「휴면 0건」을 만드는 것을 막는다(굿하트).

    이 상수는 **측정이 아니라 운영 판단**이고, 그 사실이 코드에 적혀 있어야
    다음 사람이 조용히 낮추지 않는다. 그리고 진실은 언제나 `hours_since` 다.
    """
    import inspect

    src = inspect.getsource(ef)
    i = src.index("DORMANT_HOURS = ")
    doc = src[max(0, i - 700): i]
    assert "측정이 아니라" in doc, "★임계의 성격이 코드에 안 적혀 있다"
    assert ef.DORMANT_HOURS >= 24, "★하루 미만으로 낮추면 정상 주기를 휴면으로 신고한다"


@pytest.mark.asyncio
async def test_hours_since_is_always_present_when_fired() -> None:
    """★라벨만 주고 원값을 빼면 사람이 라벨에 동의할 수도 반대할 수도 없다."""
    db = _FakeDb([("threshold_relax", 1, NOW - timedelta(hours=5))])
    out = await ef.firing_status(db, now=NOW)
    for r in out["effectors"]:
        if r["total"] > 0:
            assert r["hours_since"] is not None, f"{r['key']}: 발화했는데 경과가 없다"
        else:
            assert r["hours_since"] is None
