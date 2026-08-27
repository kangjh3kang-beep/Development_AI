"""성장루프 분석이 **판정하지 못한 것을 말하는가** — 커버리지 락.

## 무엇이 결함이었나 (라이브 실측 2026-08-26T09:0xZ · 활성 컨테이너)

    latency   키 **825개 중 802개(97%)** 가 표본 하한 미달로 `continue` → 행이 사라진다
    fallback  서비스 **5개 전부** 하한 미달 → 인사이트 **0건**
    quality   두 표본 모두 미달이면 판정 없이 반환

세 자리의 주석은 **이미** *"판정 보류"* 라고 말하고 있었다. 없던 것은 그 보류가
**어디에도 남지 않는다**는 것이다 — 보는 사람이 *"문제 없음"* 과 *"판정할 표본이 없음"* 을
**구별할 수 없다**. 커버리지 3%가 100%로 읽힌다.

## ★이 락이 **못 보는** 것

1. **행이 실제로 DB 에 들어가는지는 보지 않는다.** `analyze_window` 의 INSERT 는
   여기서 태우지 않는다(별도 통합 테스트 영역). 여기서 잠그는 것은 **판정 로직**이다.
2. **커버리지 값이 화면에 도달하는지 안 본다** — `metrics_json.analysis_coverage` 를
   읽는 표면은 아직 **0곳**이다. 그것은 다음 단계(#854 계열)의 몫이고, 여기서는
   **부채로 남긴다**(`xfail`).
3. 로그 문구 자체는 단언하지 않는다 — 산문이라 다듬을 때마다 깨지는 취약한 락이 된다.
   대신 **0건일 때도 로그가 나가는 조건**(분기)만 잠근다.
"""

from __future__ import annotations

from datetime import UTC

import pytest

from app.services.growth import analyzer as A

# ══════════════════════════════════════════════════════════════
# 1. 헬퍼 계약
# ══════════════════════════════════════════════════════════════

def test_coverage_records_both_halves_and_the_floor():
    cov: dict = {}
    A.note_coverage(cov, "latency_regression", judged=23, withheld=802, floor=20)
    assert cov["latency_regression"] == {
        "judged": 23, "withheld": 802, "total": 825, "floor": 20,
        # ★전체 동등성을 **유지**한다(부분집합으로 약화하지 않는다) — 키가 조용히
        #   늘어나는 것도 계속 잡아야 한다. 새 키는 명시적으로 적는다.
        "judged_pct": 2.8, "state": "partial",
    }


def test_coverage_is_a_noop_when_no_accumulator():
    """분석기를 단독 호출하는 기존 테스트가 깨지지 않아야 한다(무회귀)."""
    A.note_coverage(None, "x", judged=1, withheld=1, floor=1)   # 예외가 나면 실패


def test_total_is_derived_not_passed():
    """★`total` 을 인자로 받으면 judged+withheld 와 어긋나도 아무도 모른다."""
    cov: dict = {}
    A.note_coverage(cov, "k", judged=0, withheld=5, floor=10)
    assert cov["k"]["total"] == cov["k"]["judged"] + cov["k"]["withheld"]


# ══════════════════════════════════════════════════════════════
# 2. ★두 모집단이 **다른 값**을 내야 한다 — 안 그러면 배선을 끊어도 초록
# ══════════════════════════════════════════════════════════════

class _Rows(list):
    def fetchall(self): return list(self)


class _FakeDb:
    """지정한 순서대로 결과를 돌려주는 최소 스텁."""
    def __init__(self, *results): self._r = list(results)
    async def execute(self, *_a, **_k): return _Rows(self._r.pop(0) if self._r else [])
    async def commit(self): ...
    async def rollback(self): ...


@pytest.mark.asyncio
async def test_fallback_coverage_splits_below_and_above_the_floor():
    """하한 **미달만** 있는 모집단과 **충족** 모집단이 다른 커버리지를 내야 한다."""
    below = _FakeDb([("permit", 1, 3), ("regulation", 0, 1)], [])      # calls 3·1 < 10
    cov_b: dict = {}
    await A._analyze_fallback_rate(below, None, None, cov_b)
    assert cov_b["fallback_rate"] == {
        "judged": 0, "withheld": 2, "total": 2, "floor": 10,
        "judged_pct": 0.0, "state": "partial",
    }

    above = _FakeDb([("assistant", 9, 50), ("market", 0, 40)], [])     # calls 50·40 >= 10
    cov_a: dict = {}
    await A._analyze_fallback_rate(above, None, None, cov_a)
    assert cov_a["fallback_rate"]["judged"] == 2
    assert cov_a["fallback_rate"]["withheld"] == 0

    # ★두 값이 실제로 갈렸는지 — 같으면 위 단언들은 배선을 끊어도 참이 된다.
    assert cov_b["fallback_rate"]["judged"] != cov_a["fallback_rate"]["judged"]


@pytest.mark.asyncio
async def test_withheld_is_counted_by_sample_not_by_severity():
    """★`sev is None` 으로 세면 **'표본 충분·정상'** 이 보류로 오분류된다.

    아래 서비스는 표본이 충분(50콜)하고 폴백률도 정상(2%)이라 인사이트가 **안 나온다**.
    그래도 **판정은 했으므로** withheld 가 아니라 judged 여야 한다.
    """
    db = _FakeDb([("healthy", 1, 50)], [])
    cov: dict = {}
    rows = await A._analyze_fallback_rate(db, None, None, cov)
    assert rows == []                                   # 인사이트는 없다
    assert cov["fallback_rate"]["judged"] == 1          # 그러나 판정은 했다
    assert cov["fallback_rate"]["withheld"] == 0


# ══════════════════════════════════════════════════════════════
# 3. 배선 — 스탬프가 **전 타입**에 붙는가(목록형 금지)
# ══════════════════════════════════════════════════════════════

def test_coverage_is_stamped_next_to_the_producer_mark_for_every_insight():
    """★타입별 분기로 박으면 새 타입이 자동 누락된다 — 같은 자리 한 곳에서 박아야 한다.

    이 파일의 원 주석이 그렇게 지시한다(*"타입별 손수 분기는 새 타입을 자동으로 누락"*).
    """
    import inspect
    src = inspect.getsource(A.analyze_window)
    stamp = src[src.index("producer_build_id"):src.index("producer_build_id") + 400]
    assert "analysis_coverage" in stamp, "커버리지가 생산자 표식과 같은 자리에 없다"
    # 타입 이름으로 분기해 박는 흔적이 없어야 한다.
    for t in ("fallback_rate", "quality_drop", "latency_regression"):
        assert f'== "{t}"' not in stamp, f"타입별 분기 발견: {t}"


def test_zero_insight_run_still_logs_coverage():
    """★종전엔 `if insights:` 라 **0건 실행이 아무 로그도 안 남겼다**(배치 미실행과 구별 불가).

    라이브에서 fallback 은 0건이 정상 상태다 — 그때가 커버리지가 가장 필요한 순간이다.
    """
    import ast
    import inspect
    import textwrap

    # ★소스 문자열 검사는 **이 수정을 설명하는 주석**에 걸린다(실제로 걸렸다).
    #   판정은 파서로 — 함수 스코프 안에서 구조를 본다.
    fn = ast.parse(textwrap.dedent(inspect.getsource(A.analyze_window))).body[0]

    logger_calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "info"
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "logger"
    ]
    assert logger_calls, "logger.info 호출을 못 찾았다 — 조회기 의심(공허한 참 방지)"

    # 그 호출을 감싸는 `if insights:` 가 있으면 0건 실행이 침묵한다.
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        if isinstance(node.test, ast.Name) and node.test.id == "insights":
            inner = [n for n in ast.walk(node) if n in logger_calls]
            assert not inner, "0건일 때 로그를 건너뛰는 `if insights:` 분기가 남아 있다"

    # 커버리지가 그 로그의 **인자**여야 한다(문구가 아니라 값을 싣는지).
    names = {n.id for c in logger_calls for n in ast.walk(c) if isinstance(n, ast.Name)}
    assert "coverage" in names, f"로그가 커버리지를 싣지 않는다: {sorted(names)}"


# ══════════════════════════════════════════════════════════════
# 4. ★부채 — 초록 안에 보이게 남긴다
# ══════════════════════════════════════════════════════════════

@pytest.mark.xfail(reason="★소비처 0 — `metrics_json.analysis_coverage` 를 읽는 화면이 "
                          "아직 없다. 값을 실어 보내는 것과 사용자가 보는 것은 다르다. "
                          "다음 단계(성장루프 페이지 계약 · #854 계열)의 몫.",
                   strict=True)
def test_a_surface_reads_analysis_coverage():
    import subprocess
    from pathlib import Path

    # ★CI 는 `propai-platform/apps/api` 에서 pytest 를 돌린다(ci.yml 실측). 거기서
    #   `git grep -- apps/web` 은 **영원히 0건**이라, cwd 를 안 주면 이 strict xfail 이
    #   부채를 갚아도 계속 초록이다 — 표식이 죽는다(2026-08-26 독립 리뷰 M3).
    root = Path(__file__).resolve().parents[3]          # …/propai-platform
    def grep(pat: str) -> str:
        return subprocess.run(["git", "grep", "-l", pat, "--", "apps/web"],
                              cwd=root, capture_output=True, text=True).stdout.strip()

    # ★같은 실행에 양성 대조군 — 조회기 생존을 먼저 증명한다.
    assert grep("GrowthDashboard"), "★양성 대조군 0건 — 조회기가 죽었다(cwd 확인)"
    assert grep("analysis_coverage"), "analysis_coverage 를 읽는 프론트 표면이 없다"


# ══════════════════════════════════════════════════════════════
# 5. ★배선을 **행위로** 태운다 — 2026-08-26 독립 리뷰 H1·H2 봉합
# ══════════════════════════════════════════════════════════════
#
# 종전 락은 `analysis_coverage` 라는 **문자열이 소스에 있는가**만 봤다. 그래서
# `"analysis_coverage": coverage` → `"analysis_coverage": {}` 로 바꿔도 전부 초록이었다
# (리뷰어 변이 M1 · 인접 476건 전체 스위트에서도 SURVIVED).
# ★저장소 메모리: 「'부른다'를 잠그면 아무것도 안 잠긴다 — **행위를 태워라**」

class _CapturingDb:
    """`analyze_window` 가 INSERT 에 넘긴 파라미터를 붙잡는다."""

    def __init__(self) -> None:
        self.inserted: list[dict] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if sql.startswith("INSERT INTO platform_insights") and params:
            self.inserted.append(dict(params))
        class _R:
            @staticmethod
            def fetchall(): return []
            @staticmethod
            def first(): return None
            @staticmethod
            def scalar(): return None
        return _R()

    async def commit(self): ...
    async def rollback(self): ...


async def _burn_analyze_window(monkeypatch, coverage_by_axis, insight_types):
    """실제 `analyze_window` 를 태우고 INSERT 파라미터를 돌려준다."""
    import json
    from datetime import datetime, timedelta

    async def _fake_prime(db=None): return None
    monkeypatch.setattr(A, "_prime_dynamic_config", _fake_prime)

    async def _empty(db, w0, w1, coverage=None): return []
    async def _empty3(db, w0, w1): return []
    for fn in ("_analyze_error_cluster", "_analyze_recurring_verify_errors",
               "_analyze_selection_contamination"):
        monkeypatch.setattr(A, fn, _empty3)
    for fn in ("_analyze_fallback_rate", "_analyze_quality_drop", "_analyze_latency_regression"):
        monkeypatch.setattr(A, fn, _empty)

    axis, rows = coverage_by_axis

    async def _producer(db, w0, w1, coverage=None):
        A.note_coverage(coverage, axis, **rows)
        return [{"insight_type": t, "severity": "warn", "tenant_id": None,
                 "recommended_action": "none", "metrics_json": {"x": 1}}
                for t in insight_types]
    monkeypatch.setattr(A, "_analyze_fallback_rate", _producer)

    db = _CapturingDb()
    now = datetime.now(tz=UTC)
    await A.analyze_window(db, now - timedelta(hours=1), now, use_llm=False)
    return [json.loads(p["metrics_json"]) for p in db.inserted]


@pytest.mark.asyncio
async def test_the_stamped_value_is_the_real_coverage_not_just_the_key(monkeypatch):
    """★키가 아니라 **값**을 단언한다 — `coverage` → `{}` 변이가 여기서 죽어야 한다."""
    got = await _burn_analyze_window(
        monkeypatch, ("fallback_rate", {"judged": 3, "withheld": 802, "floor": 20}),
        ["fallback_rate"])
    assert got, "인사이트가 하나도 INSERT 되지 않았다 — 이 단언이 공허하다"
    assert got[0]["analysis_coverage"] == {
        "fallback_rate": {
            "judged": 3, "withheld": 802, "total": 805, "floor": 20,
            "judged_pct": 0.4, "state": "partial",
        },
    }, got[0].get("analysis_coverage")


@pytest.mark.asyncio
async def test_every_insight_type_gets_the_stamp_not_just_some(monkeypatch):
    """★타입 분기로 박으면 새 타입이 자동 누락된다 — 값으로 확인한다(음성 단언 금지)."""
    types = ["fallback_rate", "quality_drop", "latency_regression", "error_cluster"]
    got = await _burn_analyze_window(
        monkeypatch, ("fallback_rate", {"judged": 1, "withheld": 1, "floor": 10}), types)
    assert len(got) == len(types)
    for row in got:
        assert row.get("analysis_coverage"), f"스탬프 누락: {row}"
        assert row["analysis_coverage"]["fallback_rate"]["withheld"] == 1


# ══════════════════════════════════════════════════════════════
# 6. quality · latency 축도 **두 모집단으로** 잠근다 (H2)
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_quality_coverage_splits_below_and_above_the_floor():
    verify = [("permit", "fail", None)] * 2                   # vtotal 2 < 5
    fb = [("permit", 0, 2)]                                   # ftotal 2 < 5
    cov_b: dict = {}
    await A._analyze_quality_drop(_FakeDb(verify, fb), None, None, cov_b)
    assert cov_b["quality_drop"] == {
        "judged": 0, "withheld": 1, "total": 1, "floor": 5,
        "judged_pct": 0.0, "state": "partial",
    }

    verify2 = [("assistant", "fail", None)] * 6               # vtotal 6 >= 5
    cov_a: dict = {}
    await A._analyze_quality_drop(_FakeDb(verify2, []), None, None, cov_a)
    assert cov_a["quality_drop"]["judged"] == 1
    assert cov_b["quality_drop"]["judged"] != cov_a["quality_drop"]["judged"]


@pytest.mark.asyncio
async def test_latency_coverage_splits_below_and_above_the_floor():
    from datetime import datetime, timedelta
    w1 = datetime(2026, 8, 26, tzinfo=UTC)           # ★결정적 — now() 금지
    w0 = w1 - timedelta(hours=24)

    few = [("/a", 10.0)] * 3                                  # 3 < 20
    cov_b: dict = {}
    await A._analyze_latency_regression(_FakeDb(few, []), w0, w1, cov_b)
    assert cov_b["latency_regression"] == {
        "judged": 0, "withheld": 1, "total": 1, "floor": 20,
        "judged_pct": 0.0, "state": "partial",
    }

    many = [("/b", 10.0)] * 25                                # 25 >= 20
    cov_a: dict = {}
    await A._analyze_latency_regression(_FakeDb(many, []), w0, w1, cov_a)
    assert cov_a["latency_regression"]["judged"] == 1
    assert cov_b["latency_regression"]["judged"] != cov_a["latency_regression"]["judged"]


# ══════════════════════════════════════════════════════════════
# 7. ★안 잰 축을 0.0 으로 발행하지 않는다 (H3)
# ══════════════════════════════════════════════════════════════

def test_unmeasured_axis_is_withheld_not_zero():
    """★종전엔 feedback 표본이 0인데 `down_pct=0.0` 이 **발행**됐다(severity='warn')."""
    from app.utils.withheld import INSUFFICIENT_COVERAGE, is_withheld

    sev, m = A._classify_quality(fail=1, warn=0, verify_total=5, down=0, feedback_total=0)
    assert sev == "warn"                       # 행은 실제로 발행된다
    assert m["down_pct"] is None, m
    assert m["down_pct_absent"] == INSUFFICIENT_COVERAGE
    assert is_withheld(m, "down_pct")
    assert "표본" in m["down_pct_basis"]
    # 대조군: 실제로 잰 축은 값이 있어야 한다(전부 None 으로 만들면 만점이 된다).
    assert m["fail_pct"] == 20.0


def test_the_mirror_case_withholds_the_other_axis():
    sev, m = A._classify_quality(fail=0, warn=0, verify_total=0, down=5, feedback_total=10)
    assert m["fail_pct"] is None and m["warn_pct"] is None
    assert m["down_pct"] == 50.0
