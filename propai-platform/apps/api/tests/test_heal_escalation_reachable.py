"""에스컬레이션이 **구조적으로 발화 불가**였다 — 세는 대상을 바꿔 도달 가능하게 한다.

## 왜 필요한가 (라이브 실측 2026-08-27)

`heal_escalation` 은 코드·카탈로그·프론트 라벨이 **전부 있는데** 한 번도 발화한 적이 없다:

    heal_escalation  전 상태            →  **0**
    ★양성 대조군 fallback_rate         →  26      (조회기 생존)
    ★음성 대조군 zzz_not_a_type        →   0      (판별력)
    heal 액션 total                     → 520      (치유는 돈다)

**원인은 카운터의 천장이 임계보다 낮다는 것이다.**
`should_escalate` 의 입력이 `_guard_counts` 의 **실행수**였는데,
`_cap_exceeded(count, cap) := count >= cap` 가 실행을 막으므로 실행수는 `t_cap` 을 넘을 수 없다:

| action_type | t_cap | 도달 가능한 최대 실행수 | `>=5` |
|---|---|---|---|
| cache_warm | 1 | 1 | ✗ |
| threshold_relax | 2 | 2 | ✗ |
| stale_reanalysis | 3 | 3 | ✗ |
| circuit_observe | 10 | 10 | ◎ |

→ **도달 가능한 유일한 액션이 `circuit_observe`** 이고 그 액션은 스스로를
*"관측 기록(부작용 없음)"* 이라 적는다 — **에스컬레이션이 필요 없는 것만 에스컬레이션할 수 있었다.**

라이브 드라이런(heal-log 472 시간버킷): 캡 도달 **24(5.1%)** · 임계 도달 **0(0.0%)**.

## 처방 — 상수는 그대로, **세는 대상**만 바꾼다

캡을 올리면 `threshold_relax` 가 프로덕션 HTTP 타임아웃을 더 곱하고(볼트 2026-08-25 사고),
임계를 내리면 한 번 막힌 것도 에스컬레이션된다. **둘 다 기각.**
대신 **캡에 막힌 시도**를 센다 — 그 값에는 천장이 없다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.growth import healing_rules as H

NOW = datetime(2026, 8, 27, 3, 0, 0, tzinfo=UTC)


def _code(fn) -> str:
    """함수의 **실행되는 소스**만 — 독스트링을 걷어낸다.

    ★독립 리뷰 지적(MINOR-1): 이 파일의 소스 단언들은 `inspect.getsource` 를 쓰는데,
      `_escalate` 의 독스트링은 이미 `status='open'` 같은 문구를 담고 있다. 공백 하나
      차이로 단언이 **공허하게 참**이 될 수 있는 구조다(저장소 실사고 클래스 —
      *"소스 검사는 주석뿐 아니라 독스트링에도 뚫린다"*).
      그래서 `ast` 로 독스트링 노드를 지운 뒤 검사한다.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        node.body = body[1:]          # 독스트링 제거
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════════
# L3 — 상수는 **바뀌지 않았다**. ★리터럴로 못 박는다(자기 상수 단언 금지).
# ══════════════════════════════════════════════════════════════════════

def _full_cap_population() -> dict[str, int]:
    """★모집단을 **결정적으로** 고정한다.

    `PER_TRIGGER_HOURLY_CAP` 은 `healing_rules` 만의 것이 아니다 —
    `feature_flags` 가 **임포트 시점에** L1 액션 3종을 `setdefault` 로 얹는다
    (`feature_flags.py:568~575`). 그래서 이 사전의 내용은 *"무엇을 임포트했는가"* 에
    따라 달라진다. 임포트를 명시해 **항상 전체 모집단**을 보게 한다.

    ★이걸 안 하면 테스트 **순서에 따라** 답이 달라진다(실제로 그렇게 발견했다).
    """
    from app.services.growth import feature_flags  # noqa: F401 — 등록 부작용이 목적
    return dict(H.PER_TRIGGER_HOURLY_CAP)


def test_constants_are_unchanged_literals():
    """★`H.X == H.X` 류의 자기참조 단언은 상수를 바꾸면 같이 바뀌어
    **정반대 값도 통과**한다. 리터럴로 적는다."""
    assert H.ESCALATION_THRESHOLD == 5
    # heal 액션 4종은 이 모듈이 소유한다 — 값을 리터럴로 못 박는다.
    # (전체 사전은 feature_flags 가 확장하므로 **부분집합**으로 단언한다.)
    for action, cap in {"cache_warm": 1, "threshold_relax": 2,
                        "stale_reanalysis": 3, "circuit_observe": 10}.items():
        assert H.PER_TRIGGER_HOURLY_CAP[action] == cap


def test_the_original_defect_shape_is_documented_by_the_caps():
    """★원결함의 형태 자체를 잠근다 — **실행수로는 임계에 닿을 수 없었다.**

    이 단언이 깨지면 누군가 캡을 임계 위로 올린 것이고, 그것은 볼트가 기각한
    바로 그 길이다(캡↑ = `threshold_relax` 가 프로덕션 HTTP 타임아웃을 더 곱한다).

    ★**전체 모집단**으로 판정한다 — `feature_flags` 가 얹는 L1 액션 3종
    (`threshold_autotune` 1 · `feature_toggle` 2 · `prompt_ab_adopt` 1)까지 포함해서다.
    그 셋도 전부 임계 미만이라, 실행수로 에스컬레이션 가능한 것은 여전히 하나뿐이다.
    """
    pop = _full_cap_population()
    assert len(pop) >= 7, f"모집단이 예상보다 작다({len(pop)}) — 등록 부작용이 안 걸렸나"
    reachable_by_execution = {a: c for a, c in pop.items() if c >= H.ESCALATION_THRESHOLD}
    assert reachable_by_execution == {"circuit_observe": 10}


# ══════════════════════════════════════════════════════════════════════
# L1 — 도달 가능성. 경계 **양쪽**을 본다(한쪽만 걸면 반대 방향이 탐지 불가).
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("blocked,expected", [(0, False), (4, False), (5, True), (100, True)])
def test_should_escalate_partitions_on_blocked_attempts(blocked, expected):
    assert H.should_escalate(blocked) is expected


#: ★**정직한 도달 표** — 「모든 액션이 도달 가능」은 거짓이었다(독립 리뷰 M-3).
#  `trigger_cap` 으로 임계에 닿으려면 **같은 trigger_key 가 반복해서 trigger_cap 에 막혀야**
#  한다. 액션마다 그 성질이 다르다.
_UNREACHABLE_BY_DESIGN = {
    # gate 가 global 을 먼저 판정하는데 g_cap == t_cap 이라 trigger_cap 이 원리적으로 안 나온다
    "cache_warm": "g_cap == t_cap == 1 이라 global_cap 이 항상 먼저 걸린다",
    # trigger_key 가 stale:{insight_id} 라 매번 새 키 — 반복이 성립하지 않는다
    "stale_reanalysis": "trigger_key 가 인사이트마다 고유해 반복되지 않는다",
    # 쿨다운 1분·t_cap 10 인데 beat 는 시간당 6회 — 10 에 닿을 수 없다
    "circuit_observe": "beat 6회/시 < t_cap 10 이라 trigger_cap 에 닿지 않는다",
    # ★L1 액션 3종은 feature_flags 가 gate 를 부르지만 _record_blocked 를 부르지 않는다
    "threshold_autotune": "★생산자 없음 — feature_flags 가 차단을 기록하지 않는다(부채)",
    "feature_toggle": "★생산자 없음 — 위와 같다(부채)",
    "prompt_ab_adopt": "★생산자 없음 — 위와 같다(부채)",
}
_REACHABLE = {"threshold_relax"}


def test_reachability_table_covers_the_whole_population():
    """★목록이 모집단을 **다 덮는지** — 새 액션이 생기면 판정을 강제한다."""
    pop = set(_full_cap_population())
    assert len(pop) >= 7
    classified = set(_UNREACHABLE_BY_DESIGN) | _REACHABLE
    assert pop == classified, (
        f"분류되지 않은 액션: {pop - classified} / 없는 액션: {classified - pop}")


def test_threshold_relax_is_actually_reachable():
    """★이 PR 이 실제로 되살린 것 — **`threshold_relax`** 하나다.

    그리고 그것이 **가장 중요한 하나**다: 프로덕션 HTTP 타임아웃을 곱하는 유일한
    이펙터라(볼트 2026-08-25 사고) 자동치유가 이것을 반복해서 못 하고 있으면
    사람이 반드시 봐야 한다.
    """
    d = H.gate("threshold_relax", "tk", now=NOW, global_count=0,
               trigger_count=H.PER_TRIGGER_HOURLY_CAP["threshold_relax"],
               last_ts=None, blocked_count=H.ESCALATION_THRESHOLD)
    assert d["reason"] == "trigger_cap"
    assert d["escalate"] is True


def test_cache_warm_cannot_produce_trigger_cap_at_all():
    """★`_UNREACHABLE_BY_DESIGN` 의 사유가 **말이 아니라 성질**임을 태운다.

    `cache_warm` 은 `g_cap == t_cap` 이고 `gate` 가 global 을 먼저 보므로
    trigger_count 를 아무리 올려도 `reason` 이 `trigger_cap` 이 되지 않는다.
    """
    assert H.GLOBAL_HOURLY_CAP["cache_warm"] <= H.PER_TRIGGER_HOURLY_CAP["cache_warm"]
    for tc in (1, 5, 99):
        d = H.gate("cache_warm", "tk", now=NOW,
                   global_count=H.GLOBAL_HOURLY_CAP["cache_warm"],
                   trigger_count=tc, last_ts=None, blocked_count=0)
        assert d["reason"] == "global_cap", "cache_warm 에서 trigger_cap 이 나왔다"


def test_l1_actions_have_no_blocked_producer():
    """★**생산자 부재를 락으로 만든다**(소비만 보면 「도달 가능」이 공허하게 초록이다).

    `feature_flags` 는 `healing_rules.gate` 를 부르지만 `_record_blocked` 를 부르지
    않고 `blocked_count` 도 주지 않는다. 그래서 L1 액션 3종은 캡차단이 **생산되지 않는다.**
    ★이건 **알려진 부채**다 — 초록 안에서 보이게 남긴다(커밋 메시지에만 적으면 안 드러난다).
    라이브 실측(2026-08-27): `threshold_autotune` 이 heal 볼륨의 441/520 = **84.8%** 인데
    이 안전망은 그 액션에 대해 여전히 발화하지 않는다.
    """
    import inspect

    from app.services.growth import feature_flags as ff
    src = inspect.getsource(ff)
    assert "_record_blocked" not in src,         "생산자가 생겼다면 _UNREACHABLE_BY_DESIGN 에서 L1 3종을 빼고 도달성을 재측정하라"
    assert "blocked_count=" not in src, "gate 에 blocked_count 를 주기 시작했다 — 위와 같다"


@pytest.mark.xfail(reason="★부채: L1 액션 3종에 캡차단 생산자가 없다(위 락이 그 부재를 고정). "
                          "생산자를 배선하려면 global_cap 과잉 발화를 먼저 해결해야 한다.",
                   strict=True)
def test_all_actions_reachable_someday():
    """부채를 **초록 안에서 보이게** 남긴다 — 해소되면 strict xfail 이 빨개져 알려 준다."""
    assert not _UNREACHABLE_BY_DESIGN


# ══════════════════════════════════════════════════════════════════════
# L2 — ★배선. 원결함을 되살리는 변이(실행수로 되돌리기)가 여기서 죽어야 한다.
# ══════════════════════════════════════════════════════════════════════

def test_escalation_reads_blocked_count_not_execution_count():
    """두 모집단이 **반대 답**을 내야 한다 — 한쪽만 보면 배선을 뒤집어도 초록이다."""
    # 둘 다 **같은 이유로 차단**된 상태로 두고, 다른 것은 오직 캡차단 이력뿐이다.
    # 실행수가 아무리 커도 캡차단 이력이 없으면 에스컬레이션 아님
    many_exec = H.gate("threshold_relax", "tk", now=NOW, global_count=0,
                       trigger_count=999, last_ts=None, blocked_count=0)
    # 실행수는 임계 미만(2=캡)인데 캡차단 이력이 임계를 넘으면 에스컬레이션
    many_block = H.gate("threshold_relax", "tk", now=NOW, global_count=0,
                        trigger_count=2, last_ts=None, blocked_count=5)
    assert many_exec["reason"] == many_block["reason"] == "trigger_cap", "전제: 같은 차단 사유"
    assert many_exec["escalate"] is False
    assert many_block["escalate"] is True
    # ★실행수 999 는 임계 5 를 한참 넘는다 — 종전 배선이었다면 many_exec 가 True 였다.
    assert 999 >= H.ESCALATION_THRESHOLD > 2


def test_default_blocked_count_keeps_other_callers_unchanged():
    """`feature_flags` 는 `blocked_count` 를 주지 않는다 — 그 호출부 동작 불변."""
    d = H.gate("threshold_relax", "tk", now=NOW, global_count=0,
               trigger_count=999, last_ts=None)
    assert d["reason"] == "trigger_cap"      # 전제: 차단 경로를 실제로 탄다
    assert d["escalate"] is False


# ══════════════════════════════════════════════════════════════════════
# L4 — 쿨다운은 세지 않는다(정상 페이싱을 에스컬레이션하면 상시 발화).
# ══════════════════════════════════════════════════════════════════════

def test_cooldown_is_not_a_cap_block_reason():
    assert "cooldown" not in H.CAP_BLOCK_REASONS
    assert set(H.CAP_BLOCK_REASONS) == {"global_cap", "trigger_cap"}


def test_cooldown_wins_over_cap_so_it_never_enters_the_counter():
    """★이 설계가 **의존하는 성질**을 고정한다.

    쿨다운이 캡보다 먼저 판정되므로, 쿨다운 중에는 `reason` 이 캡이 될 수 없고
    따라서 캡차단 카운터에 **구조적으로** 들어오지 않는다. 순서를 뒤집으면 빨개진다.
    """
    d = H.gate("threshold_relax", "tk", now=NOW,
               global_count=999, trigger_count=999,           # 캡도 초과
               last_ts=NOW - timedelta(minutes=1))            # 그런데 쿨다운 중
    assert d["allow"] is False
    assert d["reason"] == "cooldown"
    assert d["reason"] not in H.CAP_BLOCK_REASONS


# ══════════════════════════════════════════════════════════════════════
# L7 — 실행 경로(allow 판정)는 **바이트 동일**이어야 한다.
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("blocked_count", [0, 5, 999])
def test_allow_path_is_independent_of_blocked_count(blocked_count):
    d = H.gate("threshold_relax", "tk", now=NOW, global_count=0,
               trigger_count=0, last_ts=None, blocked_count=blocked_count)
    assert d["allow"] is True
    assert d["reason"] == "ok"
    assert d["escalate"] is False, "통과 경로에서는 에스컬레이션하지 않는다"


# ══════════════════════════════════════════════════════════════════════
# 배선 — ★순수함수만 태우면 `evaluate` 가 그 카운터를 **쓰는지**는 무잠금이다.
#   (이 저장소에서 실제로 난 실패: 변이를 함수 안에만 넣어 5/5 CAUGHT 를 받고
#    호출부 한 줄을 되돌리자 락 24개가 전부 초록이었다.)
# ══════════════════════════════════════════════════════════════════════

class _Scalar:
    def __init__(self, v):
        self._v = v

    def scalar(self):
        return self._v

    def fetchone(self):
        return self._v


class _RoutingDB:
    """SQL 본문으로 갈래를 나눠 응답한다 — **어떤 질의가 실제로 갔는지** 본다.

    ★호출 여부만 세지 않고 **SQL 본문**을 남긴다. 조건절(`status='open'` 등)을
      지워도 초록이 되지 않게 하기 위함이다.
    """

    def __init__(self, *, blocked_prior: int = 0, dup_exists: bool = False,
                 trigger_count: int = 99, global_count: int = 0):
        self.blocked_prior = blocked_prior
        self.dup_exists = dup_exists
        self.trigger_count = trigger_count
        self.global_count = global_count
        self.sql: list[str] = []
        self.blocked_inserts = 0
        self.blocked_payloads: list[dict] = []
        self.insight_inserts = 0

    async def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())
        self.sql.append(q)
        if q.startswith("INSERT INTO platform_events"):
            self.blocked_inserts += 1
            self.blocked_payloads.append(dict(params or {}))
            return _Scalar(None)
        if q.startswith("INSERT INTO platform_insights"):
            self.insight_inserts += 1
            return _Scalar(None)
        if "FROM platform_insights" in q:                       # 중복 억제 조회
            return _Scalar((1,) if self.dup_exists else None)
        if "event_type = :et" in q:                             # 캡차단 시도수
            return _Scalar(self.blocked_prior)
        if "COUNT(*), MAX(created_at)" in q:                    # 트리거 실행수/최종시각
            return _Scalar((self.trigger_count, None))
        return _Scalar(self.global_count)                       # 전역 실행수

    async def commit(self):
        pass

    async def rollback(self):  # pragma: no cover
        pass


def _patch_candidates(monkeypatch, action_type="threshold_relax",
                      trigger_key="fallback_rate:site_analysis"):
    async def _fake(_db, _now):
        return [{"type": action_type, "service": "site_analysis",
                 "params": {"trigger_key": trigger_key}}]
    monkeypatch.setattr(H, "_candidate_actions", _fake)


@pytest.mark.asyncio
async def test_evaluate_records_the_blocked_attempt(monkeypatch):
    """캡에 막히면 **그 시도를 남긴다** — 남기지 않으면 영원히 셀 수 없다(원결함)."""
    _patch_candidates(monkeypatch)
    db = _RoutingDB(blocked_prior=0, trigger_count=99)
    out = await H.evaluate(db, now=NOW)
    assert out["blocked"] == 1
    assert db.blocked_inserts == 1, "캡차단 시도가 기록되지 않았다"
    assert out["escalated"] == 0, "이력이 없는데 에스컬레이션하면 과잉이다"


@pytest.mark.asyncio
async def test_evaluate_escalates_once_threshold_of_blocks_accumulated(monkeypatch):
    """★도달 가능성의 **배선** 확증 — 캡차단 이력이 임계에 닿으면 실제로 발화한다."""
    _patch_candidates(monkeypatch)
    db = _RoutingDB(blocked_prior=H.ESCALATION_THRESHOLD, trigger_count=99)
    out = await H.evaluate(db, now=NOW)
    assert out["escalated"] == 1
    assert db.insight_inserts == 1


@pytest.mark.asyncio
async def test_evaluate_reads_the_blocked_counter_at_all(monkeypatch):
    """★배선 락: `evaluate` 가 캡차단 카운터를 **조회조차 하지 않으면** 빨개진다."""
    _patch_candidates(monkeypatch)
    db = _RoutingDB(blocked_prior=0, trigger_count=99)
    await H.evaluate(db, now=NOW)
    assert any("event_type = :et" in q for q in db.sql), \
        "캡차단 시도수를 조회하지 않았다 — 에스컬레이션 입력이 배선되지 않았다"


@pytest.mark.asyncio
async def test_cooldown_block_is_not_recorded(monkeypatch):
    """L4 배선 — 쿨다운 차단은 카운터에 **들어오지 않는다**(정상 페이싱)."""
    _patch_candidates(monkeypatch)

    class _CooldownDB(_RoutingDB):
        async def execute(self, stmt, params=None):
            q = " ".join(str(stmt).split())
            if "COUNT(*), MAX(created_at)" in q:
                return _Scalar((99, NOW - timedelta(minutes=1)))   # 방금 실행 = 쿨다운
            return await super().execute(stmt, params)

    db = _CooldownDB(blocked_prior=H.ESCALATION_THRESHOLD, trigger_count=99)
    out = await H.evaluate(db, now=NOW)
    assert out["blocked"] == 1
    assert db.blocked_inserts == 0, "쿨다운 차단을 캡차단으로 기록했다"


# ══════════════════════════════════════════════════════════════════════
# L5 · L6 — 중복 억제. **양방향**으로 건다(억제가 은신처가 되면 안 된다).
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_open_escalation_suppresses_a_duplicate(monkeypatch):
    """같은 축에 **열린** 에스컬레이션이 있으면 새로 만들지 않는다.

    라이브 드라이런에서 캡 도달 24건 중 **18건이 한 트리거**였다 — 억제가 없으면
    그 하나가 화면을 18줄 채운다.
    """
    _patch_candidates(monkeypatch)
    db = _RoutingDB(blocked_prior=H.ESCALATION_THRESHOLD, dup_exists=True, trigger_count=99)
    out = await H.evaluate(db, now=NOW)
    assert db.insight_inserts == 0
    assert out["escalated"] == 0, "억제됐는데 발화한 것으로 셌다"


@pytest.mark.parametrize("status,suppressed", [
    ("open", True),            # 아직 아무도 안 봤다 → 억제
    ("acknowledged", True),    # ★사람이 "보고 조치 중" → 억제(안 하면 ack 하는 순간 되살아난다)
    ("dismissed", False),      # 사람이 기각 → 재발하면 **다시 올라와야** 한다
    ("acted", False),          # 기계가 닫음 → 재발 시 재발화
])
def test_suppression_partitions_by_status(status, suppressed):
    """★**세 모집단이 다른 답을 내는지**로 본다 — 문자열 단언은 방향을 구별 못 한다.

    종전 락은 `assert "status = 'open'" in src` 였다. 그건 *"dismissed 를 옳게 제외한다"* 와
    *"acknowledged 를 잘못 제외한다"* 를 **원리적으로 구별할 수 없다**(§한쪽만 거는 단언).
    독립 리뷰가 정확히 그 구멍으로 M-4 를 찾았다.
    """
    assert (status in H._SUPPRESSING_STATUSES) is suppressed


def test_suppressing_statuses_match_the_admin_transitions():
    """★억제 집합이 **관리자 전이와 정합**한지 — 라우터가 진실의 원천이다.

    `routers/growth.py` 가 사람에게 허용하는 전이에 `acknowledged` 가 있는데 억제가
    그것을 빼면, 이 타입에서 `acknowledged` 는 **쓸 수 없는 상태**가 된다.
    """
    from pathlib import Path as _P
    router = (_P(__file__).resolve().parents[1] / "app" / "routers" / "growth.py").read_text(encoding="utf-8")
    assert "acknowledged" in router, "전제 불성립: 라우터에 acknowledged 전이가 없다"
    assert "acknowledged" in H._SUPPRESSING_STATUSES
    assert "open" in H._SUPPRESSING_STATUSES
    # 재발화를 위해 남겨 둔 상태는 억제하지 않는다(양방향)
    for st in ("dismissed", "acted", "superseded"):
        assert st not in H._SUPPRESSING_STATUSES, f"{st} 가 은신처가 된다"


# ══════════════════════════════════════════════════════════════════════
# ★스텁이 **우회하는 층**을 따로 태운다 (변이 감사에서 드러난 구멍)
#
#   위 `_RoutingDB` 는 SQL 을 **실행하지 않고** 본문으로 갈래만 나눈다. 그래서
#   INSERT 가 쓰는 payload 모양과 SELECT 가 읽는 JSON 경로가 **어긋나도 초록**이었다
#   (기계적 변이가 그 자리를 정확히 짚었다 — 문자열변경 6건 생존).
#
#   ★이 어긋남은 **원결함의 재발 형태**다: 카운터가 조용히 영원히 0 이 되고,
#     에스컬레이션은 다시 발화 불가가 된다. 그때 아무것도 빨개지지 않는다.
# ══════════════════════════════════════════════════════════════════════

import inspect
import re


def test_blocked_event_type_is_distinct_from_heal_action():
    """★같은 이름이면 `_guard_counts` 가 **차단 시도를 실행으로 센다**.

    그러면 캡이 즉시 초과되어 치유가 통째로 멈춘다 — 조용한 대형 회귀다.
    """
    assert H.HEAL_BLOCKED_EVENT == "heal_blocked"
    assert H.HEAL_BLOCKED_EVENT != "heal_action"
    guard_sql = inspect.getsource(H._guard_counts)
    assert "'heal_action'" in guard_sql
    assert H.HEAL_BLOCKED_EVENT not in guard_sql, \
        "가드 집계가 차단 이벤트까지 센다"


def test_write_and_read_agree_on_the_payload_shape():
    """★쓰는 모양과 읽는 경로가 **같은 계약**인지 본다.

    한쪽만 바뀌면 **카운터가 영원히 0** 이 된다(= 원결함 재발). 스텁이 SQL 을 실행하지
    않으므로 이 어긋남은 어떤 실행 테스트로도 안 잡힌다.
    """
    write = _code(H._record_blocked)
    read = _code(H._blocked_count)

    # 쓰기: 최상위 action_type · reason + params 아래 trigger_key
    assert "'action_type': action_type" in write
    assert "'reason': reason" in write
    assert "'params': {'trigger_key': trigger_key}" in write

    # 읽기: 그 모양과 **정확히 같은** 경로
    assert "payload->>'action_type'" in read
    assert "payload->'params'->>'trigger_key'" in read
    assert "payload->>'reason'" in read, "사유를 읽지 않는다 — global_cap 이 섞여 든다"

    # 같은 이벤트 타입 상수를 경유
    assert "HEAL_BLOCKED_EVENT" in write and "HEAL_BLOCKED_EVENT" in read
    # 창은 상수 경유(리터럴 1시간으로 되돌리면 도달 불가로 회귀한다)
    assert "ESCALATION_WINDOW_HOURS" in read
    assert "created_at >= :since" in read
    # 판정 사유도 상수 경유
    assert "ESCALATION_COUNT_REASONS" in read


def test_dedup_query_keys_on_both_axes():
    """억제는 **(action_type, trigger_key) 둘 다**로 걸려야 한다.

    하나만 보면 서로 다른 축이 서로를 억제해 **진짜 에스컬레이션이 사라진다**.
    """
    src = _code(H._escalate)
    assert "metrics_json->>'action_type'" in src
    assert "metrics_json->>'trigger_key'" in src
    assert "_SUPPRESSING_STATUSES" in src, "억제 상태를 상수로 경유하지 않는다"


def test_escalate_insert_and_dedup_read_agree_on_metrics_shape():
    """★억제 질의가 읽는 키를 **INSERT 가 실제로 그 이름으로 쓰는가.**

    어긋나면 억제가 영원히 안 걸리고 한 트리거가 화면을 채운다.
    """
    src = _code(H._escalate)
    assert "'action_type': action_type" in src
    assert "'trigger_key': trigger_key" in src
    assert "metrics_json->>'action_type'" in src
    assert "metrics_json->>'trigger_key'" in src
    assert "metrics_json->'params'" not in src, "존재하지 않는 중첩 경로를 읽는다"


def test_exported_names_actually_exist():
    """`__all__` 에 적은 이름이 실재하는지 — 오타는 `import *` 에서만 터진다."""
    for name in H.__all__:
        assert hasattr(H, name), f"__all__ 에 있으나 실재하지 않음: {name}"
    assert "HEAL_BLOCKED_EVENT" in H.__all__
    assert "CAP_BLOCK_REASONS" in H.__all__


def test_blocked_insert_binds_columns_and_is_idempotent():
    """★INSERT 가 값을 다 싣고 **중복을 접는지** — 이 실패는 `best-effort` 라 조용하다.

    ★멱등키가 없으면 beat 중복 발화·태스크 재전달에 카운터가 **배로 세어 임계에
      절반 시간에 닿는다**(독립 리뷰 MINOR-2). 형제 `heal_actions` 는 이미
      `event_id` + `ON CONFLICT DO NOTHING` 을 쓴다 — 옳은 패턴이 바로 옆에 있었다(§G-29).
    """
    write = _code(H._record_blocked)
    assert "(event_id, event_type, payload)" in write
    assert "ON CONFLICT (event_id) DO NOTHING" in write, "멱등키가 없다 — 중복이 배로 세어진다"
    assert "uuid5" in write, "멱등키가 결정적이지 않다(uuid4 면 매번 새 행이다)"


def test_blocked_idempotency_key_is_stable_within_a_minute():
    """멱등키가 **같은 분에는 같고 다른 축이면 다른지** — 문자열이 아니라 값으로 본다."""
    import uuid

    def key(at, tk, ts):
        return str(uuid.uuid5(uuid.NAMESPACE_URL,
                              f"heal_blocked:{at}:{tk}:{ts.strftime('%Y-%m-%dT%H:%M')}"))

    same = key("threshold_relax", "t", NOW) == key("threshold_relax", "t", NOW + timedelta(seconds=30))
    other_axis = key("threshold_relax", "t", NOW) != key("threshold_relax", "u", NOW)
    later = key("threshold_relax", "t", NOW) != key("threshold_relax", "t", NOW + timedelta(minutes=2))
    assert same, "같은 분의 중복이 접히지 않는다"
    assert other_axis, "다른 트리거가 같은 키를 쓴다"
    assert later, "다음 분의 차단이 접혀 카운터가 안 오른다"


def test_insert_targets_platform_events_table():
    """차단 기록이 **어느 표로** 가는지 — 표를 바꾸면 카운터가 조용히 0 이 된다."""
    write = inspect.getsource(H._record_blocked)
    read = inspect.getsource(H._blocked_count)
    assert re.search(r"INSERT INTO platform_events", write)
    assert re.search(r"FROM platform_events", read)


# ══════════════════════════════════════════════════════════════════════
# M-2 · M-1 — ★`global_cap` 팔. **기록은 하되 판정에는 쓰지 않는다.**
#
#   독립 적대 리뷰(2026-08-27)가 여기를 짚었다: 종전에는 이 팔이 **이 PR 효과의 전부**
#   였는데(시뮬: cache_warm n=2 → 계수차단 41건이 전부 global_cap · 발화 31),
#   그 팔을 태우는 테스트가 **0건**이라 배선 변이가 SURVIVED 했다.
#   `global_cap` 은 "이 트리거의 치유가 무효"가 아니라 **"지금 아픈 서비스가 여럿"** 이다.
# ══════════════════════════════════════════════════════════════════════

def test_only_trigger_cap_counts_toward_escalation():
    assert H.ESCALATION_COUNT_REASONS == ("trigger_cap",)
    assert "global_cap" in H.CAP_BLOCK_REASONS, "기록 대상에서는 빠지면 안 된다(관측 가치)"
    assert "global_cap" not in H.ESCALATION_COUNT_REASONS
    assert "cooldown" not in H.CAP_BLOCK_REASONS


@pytest.mark.asyncio
async def test_global_cap_is_recorded_but_does_not_escalate(monkeypatch):
    """★세 모집단 중 두 번째 — `global_cap` 은 **기록되고 발화하지 않는다.**

    이 테스트가 없으면 `if decision["reason"] in CAP_BLOCK_REASONS` 를
    `== "trigger_cap"` 으로 바꾸는 변이가 **그대로 생존한다**(리뷰가 실제로 재현했다).
    """
    _patch_candidates(monkeypatch, action_type="cache_warm",
                      trigger_key="fallback_rate:market")
    db = _RoutingDB(blocked_prior=H.ESCALATION_THRESHOLD,
                    global_count=H.GLOBAL_HOURLY_CAP["cache_warm"], trigger_count=0)
    out = await H.evaluate(db, now=NOW)
    assert out["blocked"] == 1
    assert db.blocked_inserts == 1, "global_cap 차단이 기록되지 않았다(관측 상실)"
    assert db.blocked_payloads[0].get("p", "").find("global_cap") >= 0, \
        "기록에 사유가 안 실렸다 — 사후에 global/trigger 를 가를 수 없다"
    # ★blocked_prior 가 임계여도 **발화하지 않는다** — 그 이력은 trigger_cap 만 세므로
    #   여기서는 _blocked_count 가 사유 필터로 걸러 준다(스텁은 그 필터를 모사하지 않으니
    #   발화 여부가 아니라 **기록과 사유**를 단언한다).
    assert db.blocked_payloads[0].get("et") == H.HEAL_BLOCKED_EVENT


@pytest.mark.asyncio
async def test_trigger_cap_records_its_reason(monkeypatch):
    """세 모집단 중 첫 번째 — `trigger_cap` 은 기록되고 **그 사유로** 기록된다."""
    _patch_candidates(monkeypatch)
    db = _RoutingDB(blocked_prior=0, trigger_count=99, global_count=0)
    out = await H.evaluate(db, now=NOW)
    assert out["blocked"] == 1 and db.blocked_inserts == 1
    assert "trigger_cap" in db.blocked_payloads[0].get("p", "")
    assert "global_cap" not in db.blocked_payloads[0].get("p", "")
