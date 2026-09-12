"""스케줄 스냅샷 — **「경과」만으로는 정상과 정지를 못 가른다**를 잠근다.

★왜 이 파일이 있나 (실측 2026-09-12 13:11Z · 측정자가 곧 오독자다):
  `growth_last_run.learn` 이 **9,471분 전**이었고 나는 그것을 보고 *"6.6일째 멈췄다"* 고
  의심했다. `JOB_SPECS["learn"].period_minutes` 는 **10080(7일)** 이라 **정상**이었다.
  같은 「7일 전」이 `learn` 에겐 정상이고 `analyze`(60분)에겐 **대형 장애**다.
  ⇒ 이 파일의 중심 단언은 ***같은 경과값이 잡에 따라 다른 판정을 내는가*** 다.
    하나로 접히면 이 변경은 장식이다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.api.app.services.growth.schedule import (
    JOB_SPECS,
    SCHEDULE_SNAPSHOT_KEY,
    compute_due,
    schedule_snapshot_payload,
    watermark_key,
)

NOW = datetime(2026, 9, 12, 13, 11, 0, tzinfo=UTC)


def _jobs_map(payload):
    """`"analyze 7/60 heal 6/10"` → `{"analyze": (7, 60), ...}`."""
    out = {}
    for tok in str(payload["jobs"]).split():
        if "/" not in tok:
            out[tok] = None          # 잡 이름 토큰
            last = tok
            continue
        a, b = tok.split("/", 1)
        out[last] = (a, b)
    return out


def test_population_is_derived_from_job_specs_not_a_hand_list():
    """모집단을 손으로 적지 않는다 — 잡을 추가하면 자동으로 들어온다."""
    assert len(JOB_SPECS) >= 5, "잡 표가 줄었다 — 아래 검사들이 공허해진다"
    observed = [(j, NOW - timedelta(minutes=1)) for j in JOB_SPECS]
    got = _jobs_map(schedule_snapshot_payload(observed, NOW))
    assert set(got) == set(JOB_SPECS), f"스냅샷이 일부 잡을 뺐다: {set(JOB_SPECS) - set(got)}"


def test_same_elapsed_two_verdicts_learn_ok_analyze_overdue():
    """★두 모집단 — **같은 9,471분**이 `learn` 엔 정상이고 `analyze` 엔 지연이다.

    이 단언이 없으면 「경과만 싣는」 구현도 통과한다(그게 고치려는 결함이다).
    """
    elapsed = timedelta(minutes=9471)
    p = schedule_snapshot_payload(
        [("learn", NOW - elapsed), ("analyze", NOW - elapsed)], NOW,
    )
    overdue = str(p["overdue"]).split()
    assert "analyze" in overdue, f"analyze(60분)가 9471분 경과인데 지연이 아니다: {p}"
    assert "learn" not in overdue, f"learn(10080분)이 9471분 경과인데 지연으로 찍혔다: {p}"
    # ★그리고 **주기가 값에 실려야** 한다 — 없으면 사람이 다시 SSOT 를 찾아가야 한다.
    got = _jobs_map(p)
    assert got["learn"] == ("9471", "10080"), got
    assert got["analyze"] == ("9471", "60"), got


def test_never_seen_is_not_zero_elapsed():
    """워터마크를 본 적 없음(`-`)과 「방금 돌았음(0)」은 다른 사실이다."""
    p = schedule_snapshot_payload([("analyze", None), ("heal", NOW)], NOW)
    got = _jobs_map(p)
    assert got["analyze"] == ("-", "60"), got
    assert got["heal"] == ("0", "10"), got
    assert "analyze" not in str(p["overdue"]).split(), "본 적 없음을 지연으로 단정했다"


def test_clock_rollback_agrees_with_is_due():
    """시계가 뒤로 가면 `is_due` 는 참을 낸다 — 스냅샷도 같은 값이어야 한다.

    두 곳이 갈리면 계기판이 「돌 때가 됐다」의 **반대**를 말한다.
    """
    p = schedule_snapshot_payload([("analyze", NOW + timedelta(minutes=5))], NOW)
    assert "analyze" in str(p["overdue"]).split(), p


def test_value_is_not_a_list():
    """`routers/growth.py:452` 실측 — 활성 플래그 `value` 가 list 면 **HTTP 500** 이다."""
    p = schedule_snapshot_payload([("analyze", NOW)], NOW)
    assert isinstance(p, dict), type(p)
    for k, v in p.items():
        assert not isinstance(v, list), f"{k} 가 list 다 — 읽기가 500 으로 죽는다"


def test_job_names_are_not_truncated():
    """접두를 줄이면 접두가 겹치는 잡이 생기는 순간 **두 잡이 한 칸으로 뭉친다**."""
    observed = [(j, NOW) for j in JOB_SPECS]
    got = _jobs_map(schedule_snapshot_payload(observed, NOW))
    for j in JOB_SPECS:
        assert j in got, f"{j} 가 요약에 온전한 이름으로 없다: {got}"


class _FakeSettings:
    """`get_setting`/`set_setting` 만 흉내내는 가짜. 무엇이 쓰였는지 기록한다."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.writes: list[tuple[str, object]] = []

    async def get_setting(self, _db, key):
        return self.store.get(key)

    async def set_setting(self, _db, key, value, *, scope="global",
                          ttl_expires_at=None, updated_by=None):
        self.store[key] = value
        self.writes.append((key, value))
        return True


@pytest.mark.asyncio
async def test_compute_due_actually_publishes_the_snapshot():
    """★**배선**을 잠근다 — 순수 함수만 잠그면 부르는 곳을 지워도 초록이다.

    이 저장소가 반복해서 데인 *"배선 미변이"* 다(`compute_due` 독스트링이 그 사고를 적고 있다).
    """
    fake = _FakeSettings({watermark_key(j): NOW.isoformat() for j in JOB_SPECS})
    await compute_due(None, fake, NOW)
    keys = [k for k, _ in fake.writes]
    assert SCHEDULE_SNAPSHOT_KEY in keys, f"스냅샷을 발행하지 않았다: {keys}"
    payload = dict(fake.writes)[SCHEDULE_SNAPSHOT_KEY]
    assert set(_jobs_map(payload)) == set(JOB_SPECS), payload


@pytest.mark.asyncio
async def test_publishing_does_not_change_the_due_verdict():
    """관측만 추가한다 — 판정은 그대로여야 한다(회귀가 아님의 근거)."""
    stale = (NOW - timedelta(days=99)).isoformat()
    fake = _FakeSettings({watermark_key(j): stale for j in JOB_SPECS})
    due = await compute_due(None, fake, NOW)
    assert set(due) == set(JOB_SPECS)
    assert all(due.values()), f"99일 경과인데 발화하지 않는 잡이 있다: {due}"


# ─────────────────────────────────────────────────────────────────────────────
# ★기계 변이가 짚은 생존 5건을 닫는다 (2026-09-12 · 손 변이 5/5 CAUGHT **뒤에** 나온 것들)
#   ***«N/N CAUGHT» 뒤에는 «그 N 을 누가 골랐나»가 온다*** — 위 다섯은 내가 골랐고,
#   아래 다섯은 도구가 골랐다. 내 분모 밖이었다.
# ─────────────────────────────────────────────────────────────────────────────

import ast as _ast
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[2]          # …/propai-platform
_PROBE = _REPO / "scripts" / "monitor" / "growth_stale_producer_probe.py"


def test_snapshot_key_literal_is_pinned_and_matches_the_probe():
    """★상수를 **자기 자신과 비교하지 않는다**.

    `SCHEDULE_SNAPSHOT_KEY` 를 임포트해 쓰는 단언은 값을 바꿔도 초록이다(기계 변이 실측:
    이 줄의 문자열 변경이 **생존**했다). 그런데 소비처인 프로브는 **다른 프로세스**라
    같은 문자열을 자기 파일에 들고 있다 — **둘이 갈리면 계기판이 영원히 「확인 불가」** 다.
    그래서 ①리터럴로 핀하고 ②프로브 쪽 상수와 **문법으로** 대조한다.
    """
    assert SCHEDULE_SNAPSHOT_KEY == "growth_schedule"   # ① 리터럴 핀

    src = _PROBE.read_text(encoding="utf-8")
    tree = _ast.parse(src)
    found = {}
    for node in _ast.walk(tree):                       # ② 주석·독스트링이 아니라 **실행 대입**만
        if isinstance(node, _ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, _ast.Name) and isinstance(node.value, _ast.Constant):
                found[tgt.id] = node.value.value
    assert "SCHEDULE_SETTING_KEY" in found, (
        f"프로브에 SCHEDULE_SETTING_KEY 대입이 없다(소비처 0) — 찾은 상수: {sorted(found)}"
    )
    assert found["SCHEDULE_SETTING_KEY"] == SCHEDULE_SNAPSHOT_KEY, (
        f"생산자 {SCHEDULE_SNAPSHOT_KEY!r} ↔ 소비처 {found['SCHEDULE_SETTING_KEY']!r} 가 갈렸다"
    )


def test_probe_reason_has_no_handcopied_period_or_ttl():
    """★사용자에게 나가는 사유에 **손복사 상수**가 없다(실행되는 줄만 본다).

    종전 `:143` 은 «TTL(180분) > 주기(60분) 이므로 3회 연속 미실행» 이라고 단정했고
    그 두 수는 `schedule.py`/`analyzer.py` 에서 **손으로 복사**된 것이었다 —
    주기가 60→90 이면 180/90=2 인데 문장은 여전히 «3회» 라고 말한다.
    ★주석에는 그 경위가 남아 있으므로 **실행 리터럴만** 본다(주석을 보면 위양성이 된다).
    """
    tree = _ast.parse(_PROBE.read_text(encoding="utf-8"))
    strings = [
        n.value for n in _ast.walk(tree)
        if isinstance(n, _ast.Constant) and isinstance(n.value, str)
    ]
    # 독스트링(모듈·함수·클래스의 첫 표현식)은 실행 문자열이 아니다 — 걷어낸다.
    docstrings = set()
    for n in _ast.walk(tree):
        if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            d = _ast.get_docstring(n, clean=False)
            if d:
                docstrings.add(d)
    live = [s for s in strings if s not in docstrings]
    # ★대조군 — 조회기가 살아 있는가(이 문자열은 반드시 실행 리터럴에 있다)
    assert any("분석상태 행이 없다" in s for s in live), (
        "대조군 실패 — 실행 문자열을 하나도 못 읽었다(파서가 죽었다)"
    )
    offenders = [s for s in live if "180분" in s or "60분) 이므로" in s or "3회 연속" in s]
    assert offenders == [], f"사유에 손복사 상수가 남아 있다: {offenders}"


def test_at_is_published_and_is_the_liveness_signal():
    """★`at` 이 빠지면 **「스케줄러가 도는가」를 판정할 수 없다**(기계 변이: 줄삭제 생존).

    TTL 을 안 걸었으므로 행은 늘 노출된다 — 살아 있음의 유일한 축이 `at` 의 나이다.
    """
    p = schedule_snapshot_payload([("analyze", NOW)], NOW)
    assert "at" in p, f"at 이 없다 — 나이를 못 재면 정지와 정상이 같은 모양이다: {p}"
    assert p["at"] == NOW.isoformat(), p["at"]
    assert datetime.fromisoformat(str(p["at"])) == NOW      # 파싱 가능해야 한다


def test_unknown_job_is_not_silently_dropped():
    """`JOB_SPECS` 에 없는 잡이 와도 **조용히 사라지지 않는다**(기계 변이: `?/?` 생존)."""
    p = schedule_snapshot_payload([("analyze", NOW), ("zzz_nope", NOW)], NOW)
    got = _jobs_map(p)
    assert "zzz_nope" in got, f"모르는 잡이 요약에서 증발했다: {p}"
    assert got["zzz_nope"] == ("?", "?"), got
    assert "zzz_nope" not in str(p["overdue"]).split(), "주기를 모르면서 지연이라 단정했다"


@pytest.mark.asyncio
async def test_snapshot_write_identifies_its_producer_and_is_not_a_seed():
    """★`updated_by` 는 장식이 아니다(기계 변이: 줄삭제·문자열변경 **둘 다 생존**).

    형제 락(`test_growth_schedule.py`)이 **「씨드가 아닌 쓰기는 워터마크를 안 건드린다」**
    를 `updated_by` 에 `"seed"` 가 있는지로 가른다 — 이 값이 비거나 `seed` 를 품으면
    그 락이 **조용히 무력화**된다.
    """
    fake = _FakeSettings({watermark_key(j): NOW.isoformat() for j in JOB_SPECS})

    captured: list[tuple[str, str | None]] = []
    orig = fake.set_setting

    async def spy(_db, key, value, *, scope="global", ttl_expires_at=None, updated_by=None):
        captured.append((key, updated_by))
        return await orig(_db, key, value, scope=scope,
                          ttl_expires_at=ttl_expires_at, updated_by=updated_by)

    fake.set_setting = spy
    await compute_due(None, fake, NOW)

    ub = dict(captured).get(SCHEDULE_SNAPSHOT_KEY, None)
    assert ub, f"스냅샷 쓰기에 updated_by 가 없다 — 출처 불명 행이 생긴다: {captured}"
    assert "seed" not in ub, f"스냅샷이 씨드로 위장했다({ub!r}) — 형제 락이 무력화된다"
    assert "scheduler" in ub, f"생산자를 식별할 수 없다: {ub!r}"
