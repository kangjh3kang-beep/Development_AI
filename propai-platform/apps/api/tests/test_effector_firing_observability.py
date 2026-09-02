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


# ═══════════════════════════════════════════════════════════════════════════
# ★★독립 적대 리뷰(2026-08-27) 봉합 — **25개 변이 중 20개 생존**했다
#
# 내 변이 6종은 전부 `classify()`/`firing_status()` **한 층 안**이었다.
# "6/6 CAUGHT" 는 **참이지만 무의미**했다 — 저장소 교훈 그대로:
#   *"N/N CAUGHT 전에 **몇 개 층에** 넣었나를 물어라."*
# 아래는 리뷰가 뚫은 층들(라우터 · SQL · 값 · 렌더)을 직접 태운다.
# ═══════════════════════════════════════════════════════════════════════════
import app.routers.growth as _gr  # noqa: E402


class _ExactDb(_FakeDb):
    """바인드 파라미터까지 붙잡는다 — SQL 이 **실제로 무엇을 거르는지** 보려고."""

    def __init__(self, rows):
        super().__init__(rows)
        self.params: list[dict] = []

    async def execute(self, stmt, params=None):
        self.params.append(dict(params or {}))
        return await super().execute(stmt, params)


@pytest.mark.asyncio
async def test_sql_filters_by_event_type_with_bound_param() -> None:
    """★리뷰 M1 — `event_type` 필터를 지우면 **모든 이벤트**(page_view·llm_call…)를 센다.

    옛 락은 `"platform_events" in sql` 만 봐서 그 변이가 **생존**했다.
    문자열이 아니라 **바인드된 값**과 **WHERE 절의 구조**를 본다.
    """
    db = _ExactDb([])
    await ef.firing_status(db, now=NOW)
    sql = " ".join(db.sql)
    assert "WHERE event_type = :et" in sql, f"★event_type 필터가 사라졌다: {sql}"
    assert db.params and db.params[0].get("et") == "heal_action", (
        f"★바인드 값이 heal_action 이 아니다: {db.params}"
    )


@pytest.mark.asyncio
async def test_sql_reads_the_action_type_key_not_an_alias() -> None:
    """★리뷰 M5 — `payload->>'totally_wrong_key' AS action_type` 이 **생존**했다.

    별칭에 `action_type` 이 들어가면 옛 부분문자열 단언이 만족된다 →
    모든 효과기가 `never_fired` 가 되는데(이 표면이 구별하려던 바로 그 상태) 초록이었다.
    **선택식 자체**를 본다.
    """
    db = _ExactDb([])
    await ef.firing_status(db, now=NOW)
    sql = " ".join(db.sql)
    assert "payload->>'action_type' AS k" in sql, f"★잘못된 키를 읽는다: {sql}"


@pytest.mark.asyncio
async def test_exact_counts_and_timestamps_survive(_two_rows) -> None:
    """★리뷰 M7·M8·M12 — `total`/`last_fired_at` 을 **아무도 단언하지 않았다**.

    옛 락은 `total == 0` 또는 `> 0` 만 봐서 47·441 이 **1 로 뭉개져도** 초록이었고,
    `last_fired_at` 을 상수로 바꿔도 초록이었다.
    ★**두 행이 서로 다른 값**을 갖게 해서 상수 구현이 둘 다 만족할 수 없게 한다.
    """
    out = await ef.firing_status(_two_rows, now=NOW)
    by = {r["key"]: r for r in out["effectors"]}
    assert by["threshold_relax"]["total"] == 47
    assert by["threshold_autotune"]["total"] == 441
    assert by["threshold_relax"]["total"] != by["threshold_autotune"]["total"]
    assert str(by["threshold_relax"]["last_fired_at"]).startswith("2026-08-24T18:50")
    assert str(by["threshold_autotune"]["last_fired_at"]).startswith("2026-08-06T23:46")
    assert by["threshold_relax"]["hours_since"] != by["threshold_autotune"]["hours_since"]


@pytest.fixture
def _two_rows():
    return _FakeDb([
        ("threshold_relax", 47, datetime(2026, 8, 24, 18, 50, 15, tzinfo=UTC)),
        ("threshold_autotune", 441, datetime(2026, 8, 6, 23, 46, 54, tzinfo=UTC)),
    ])


@pytest.mark.asyncio
async def test_each_row_carries_its_own_declaration(_two_rows) -> None:
    """★리뷰 M9·M15·M2 — 전 행 `declared_reach="product"` 로 바꿔도, 키를 **바꿔치기**해도,
    `evidence`/`missing` 을 지워도 전부 **생존**했다.

    옛 단언은 `threshold_relax` 하나만 봤는데 그것이 마침 PRODUCT 라 **공허하게 참**이었다.
    """
    out = await ef.firing_status(_two_rows, now=NOW)
    by = {r["key"]: r for r in out["effectors"]}
    declared = {e.key: e for e in EFFECTORS}
    # ★전수 대조 — 한 행이 아니라 모든 행이 **자기** 선언을 지녀야 한다.
    for k, r in by.items():
        assert r["declared_reach"] == str(declared[k].reach), f"{k}: 선언이 뒤바뀌었다"
        assert r["evidence"] == declared[k].evidence, f"{k}: 근거가 사라졌다"
        assert r["missing"] == declared[k].missing, f"{k}: missing 이 사라졌다"
    # ★두 모집단 — reach 가 서로 다른 값이 실제로 나온다(전부 product 인 구현 차단).
    reaches = {r["declared_reach"] for r in out["effectors"]}
    assert len(reaches) >= 2, f"모든 효과기의 reach 가 같다 — 선언을 안 읽는다: {reaches}"
    # ★키 바꿔치기 차단 — 각 행의 건수가 **자기 키**의 것이어야 한다.
    assert by["threshold_relax"]["total"] == 47
    assert by["threshold_autotune"]["total"] == 441


@pytest.mark.asyncio
async def test_max_silence_is_none_when_any_product_effector_never_fired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★리뷰 #6 — **진짜 결함**이었다(락 구멍이 아니라 동작이 틀렸다).

    PRODUCT 효과기가 둘이고 하나가 5시간 전 발화·하나가 **한 번도 없음**이면
    옛 식은 `None` 을 걸러 **5.0**("최장 침묵 5시간")을 냈다 — **거짓말**이다.
    ★그리고 이 결함은 `product_reaching_count()` 가 1 을 넘는 **성공 시점**에 발화한다.
    """
    from app.services.growth.effector_reach import Effector

    extra = Effector(key="second_product", reach=Reach.PRODUCT, evidence="테스트용")
    patched = (*EFFECTORS, extra)
    monkeypatch.setattr(ef, "EFFECTORS", patched)

    # ① 하나만 발화, 다른 PRODUCT 는 한 번도 없음 → **None**(= 무한대)
    db = _FakeDb([("second_product", 3, NOW - timedelta(hours=5))])
    s = (await ef.firing_status(db, now=NOW))["summary"]
    assert s["product_reaching_never_fired"] >= 1
    assert s["product_reaching_max_hours_since"] is None, (
        "★한쪽이 영원히 조용한데 다른 쪽 시간을 「최장 침묵」이라 보고했다"
    )

    # ② 둘 다 발화 → **더 오래된 쪽**(min 으로 바꾸는 변이를 죽인다)
    db2 = _FakeDb([
        ("second_product", 3, NOW - timedelta(hours=5)),
        ("threshold_relax", 47, NOW - timedelta(hours=200)),
    ])
    s2 = (await ef.firing_status(db2, now=NOW))["summary"]
    assert s2["product_reaching_never_fired"] == 0
    assert s2["product_reaching_max_hours_since"] == pytest.approx(200.0, abs=0.2), (
        "★max 가 아니라 min 을 쓰고 있다"
    )
    assert s["product_reaching_max_hours_since"] != s2["product_reaching_max_hours_since"]


def test_dormant_threshold_is_bounded_on_both_sides() -> None:
    """★리뷰 #5 — 옛 단언은 `>= 24` **한쪽만** 걸어서, 임계를 **올려** 「휴면 0건」을
    만드는 변이(72 → 499)가 **생존**했다. 방향이 정반대였다.

    ★상한의 근거는 **라이브 관측**이다: `threshold_autotune` 이 493시간 조용했다.
      임계가 그것을 넘으면 그 관측이 `active` 로 분류돼 표면이 아무 말도 못 한다.
    """
    assert 24 <= ef.DORMANT_HOURS <= 168, (
        f"★임계 {ef.DORMANT_HOURS} — 상한(168h=7일)을 넘으면 라이브 493시간 침묵도 "
        "「발화 중」이 된다(임계를 올려 휴면 0건을 만드는 것을 막는다)"
    )
    # ★파티션형 — 라이브 최장 침묵은 어떤 허용 임계에서도 **반드시** dormant 여야 한다.
    assert ef.classify(441, 493.0) == ef.STATE_DORMANT
    assert ef.classify(1, 1.0) == ef.STATE_ACTIVE


def test_never_fired_wording_is_narrowed_to_telemetry_start() -> None:
    """★리뷰 #9 — 계획서가 *"보존창 안에서 0건이라 좁혀야 한다"* 고 적었는데
    코드는 *"기록 전체에서 0건"* 을 그대로 실었다. 주석에 쓴 주장도 검증 대상이다(§G-30).
    """
    import inspect
    import re

    src = inspect.getsource(ef)
    # ★검사 대상을 **선언 줄**로 좁힌다. 전체 소스를 보면 이 결함을 **설명하는 주석**이
    #   걸린다 — 실제로 첫 판이 그렇게 빨개졌다(내가 쓴 인용문을 내 검사가 집었다).
    #   *"주석에 예시를 적으면 그 예시가 다음 검사의 위양성이 된다"*(§검증 규율 8).
    decl = next(
        (ln for ln in src.splitlines() if re.match(r'^STATE_NEVER\s*=', ln)), None
    )
    assert decl, "★STATE_NEVER 선언을 못 찾았다 — 추출기가 죽었다(위반 아님)"
    assert "기록 전체" not in decl, f"★과대주장이 선언에 남아 있다: {decl}"
    assert "계측 시작" in decl, f"★무엇에 대해 0건인지 안 밝힌다: {decl}"
    assert ef.TELEMETRY_SINCE, "계측 시작 시점이 없다"


@pytest.mark.asyncio
async def test_route_requires_admin_and_returns_all_declared(monkeypatch) -> None:
    """★리뷰 #1 — **라우트를 태우는 테스트가 하나도 없었다.**

    `await _require_admin(request, db)` 를 지워도, 본문을 통째로 상수로 바꿔도
    95개 테스트가 전부 초록이었다(리뷰 M13·M14).

    ★두 모집단: 관리자가 **아니면** 예외가 나가고, 관리자면 **선언 수만큼** 행이 온다.
    """
    calls: list[str] = []

    async def deny(request, db):
        calls.append("guard")
        raise _gr.HTTPException(status_code=403, detail="관리자만")

    monkeypatch.setattr(_gr, "_require_admin", deny)
    with pytest.raises(_gr.HTTPException) as e:
        await _gr.effector_firing(request=object(), db=_FakeDb([]))
    assert e.value.status_code == 403
    assert calls == ["guard"], "★가드를 부르지 않았다"

    async def allow(request, db):
        calls.append("guard")
        return "admin-1"

    monkeypatch.setattr(_gr, "_require_admin", allow)
    body = await _gr.effector_firing(request=object(), db=_FakeDb([]))
    # ★선언 표에서 **파생** — 행 수를 손으로 적지 않는다.
    assert len(body["effectors"]) == len(EFFECTORS)
    assert body["summary"]["declared"] == len(EFFECTORS)
    assert len(calls) == 2, "★두 번째 호출에서 가드를 건너뛰었다"


# ═══════════════════════════════════════════════════════════════════════════
# ★기계적 변이(`scripts/mutate_changed.py`) 생존분 봉합 — 손으로 고르지 않은 변이
#
# 리뷰 항목 ⑩: *"손으로 고른 여섯 개 말고 도구를 돌려라 — 사람이 고른 변이는 사람이
# 못 본 층을 비껴간다."* 돌렸더니 **11건 중 5건이 생존**했다. 넷은 진짜 구멍이었다.
# ═══════════════════════════════════════════════════════════════════════════
def test_state_literals_are_pinned() -> None:
    """★상태 **문자열 값**을 못 박는다(기계 변이 #2 생존).

    이 값은 프론트 `EFFECTOR_STATE_LABELS` 의 **키**다. 바뀌면 화면에 영문 raw 가 뜬다.
    프론트 정합 테스트가 잡긴 하지만 **다른 스위트**라, 백엔드만 돌리는 사람에게는
    무잠금이었다. 리터럴을 여기서도 못 박는다.
    """
    assert ef.STATE_NEVER == "never_fired"
    assert ef.STATE_DORMANT == "dormant"
    assert ef.STATE_ACTIVE == "active"
    assert ef.STATE_UNDECLARED == "undeclared"
    # ★네 값이 서로 달라야 상태 구별이 성립한다.
    assert len({ef.STATE_NEVER, ef.STATE_DORMANT, ef.STATE_ACTIVE, ef.STATE_UNDECLARED}) == 4


def test_telemetry_since_is_a_real_date_not_a_placeholder() -> None:
    """★`TELEMETRY_SINCE` 를 아무 문자열로 바꿔도 통과했다(기계 변이 #4 생존).

    이 값은 화면이 *"(… 계측 시작 이후)"* 라고 말할 때 쓰는 **근거**다.
    형식이 깨지면 사용자에게 의미 없는 문자열이 그대로 나간다.
    """
    from datetime import date

    d = date.fromisoformat(ef.TELEMETRY_SINCE)  # 형식이 깨지면 ValueError
    assert date(2026, 1, 1) <= d <= date.today(), f"★미래이거나 비현실적: {d}"


@pytest.mark.asyncio
async def test_response_carries_telemetry_since(_two_rows) -> None:
    """★응답에서 `telemetry_since` 를 빼도 백엔드는 초록이었다(기계 변이 #5·#6 생존).

    이게 없으면 화면이 *"한 번도 없음"* 을 **무엇에 대해** 말하는지 밝힐 수 없다 —
    바로 그 과대주장을 막으려고 넣은 값이다.
    """
    out = await ef.firing_status(_two_rows, now=NOW)
    assert out["telemetry_since"] == ef.TELEMETRY_SINCE
    assert out["dormant_hours"] == ef.DORMANT_HOURS
