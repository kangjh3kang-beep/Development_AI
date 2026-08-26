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


@pytest.mark.asyncio
async def test_fallback_coverage_splits_below_and_above_the_floor():
    """하한 **미달만** 있는 모집단과 **충족** 모집단이 다른 커버리지를 내야 한다."""
    below = _FakeDb([("permit", 1, 3), ("regulation", 0, 1)], [])      # calls 3·1 < 10
    cov_b: dict = {}
    await A._analyze_fallback_rate(below, None, None, cov_b)
    assert cov_b["fallback_rate"] == {"judged": 0, "withheld": 2, "total": 2, "floor": 10}

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
    hits = subprocess.run(
        ["git", "grep", "-l", "analysis_coverage", "--", "apps/web"],
        capture_output=True, text=True,
    ).stdout.strip()
    assert hits, "analysis_coverage 를 읽는 프론트 표면이 없다"
