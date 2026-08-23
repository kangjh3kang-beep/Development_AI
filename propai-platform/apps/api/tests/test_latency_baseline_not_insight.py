"""지연 baseline 적재가 **"회귀" 인사이트로 쌓였다** (2026-08-23).

★라이브 실측(propai-v002719 · platform_insights):

    latency_regression   2059건  ← 최신 6건 전부 `p95_ms == baseline_p95`(회귀 아님)
    error_cluster         108건
    status: open 2248 / acknowledged 16   ← 미확인 99.3%
    severity: info 1855(82%) / warn 352 / critical 57

  `_analyze_latency_regression` 의 `out.append` 가 **조건 없이** 실행돼,
  회귀가 없어도(`_classify_latency` → None) 매 배치마다 모든 route 에 대해
  `insight_type='latency_regression'` 행이 생긴다. baseline 저장소로 insights 테이블을
  재사용한 설계 탓에 **"사람이 볼 것"과 "기계가 참조할 것"이 한 테이블에 섞였다**.

★심각도는 정직하게 **중간**이다 — 조회 API 가 severity 가중치로 정렬(critical>warn>info)
  하므로 진짜 신호가 맨 아래로 묻히지는 않는다. 그러나 하루 20~90건씩 **무한 축적**되고
  "미확인 2,248건" 이라는 카운트가 실제 조치 대상(critical 57 + warn 352)을 가린다.

★처방: 회귀가 아닌 행은 `insight_type='latency_baseline'` 으로 분리한다.
  ★★baseline 조회는 **두 타입을 모두** 보게 해 **체인을 끊지 않는다** —
    끊기면 baseline 이 0 이 되어 회귀 판정이 영원히 None 이 된다(더 나쁜 회귀).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.growth import analyzer as az  # noqa: E402


def test_A_회귀가_아니면_baseline_타입으로_쌓인다():
    """★A/B 가 갈리는 지점 — 같은 코드가 두 타입을 내야 한다."""
    assert az._classify_latency(100.0, 90.0) is None          # 전제: 회귀 아님
    assert az.insight_type_for_latency(None) == "latency_baseline"


def test_B_회귀면_regression_타입이다():
    assert az._classify_latency(200.0, 100.0) == "warn"        # 전제: 1.5배 초과
    assert az.insight_type_for_latency("warn") == "latency_regression"


def test_C_baseline_조회는_두_타입을_모두_본다_체인유지():
    """★이걸 놓치면 baseline 이 0 이 되어 회귀 판정이 **영원히 None** 이 된다.

    기존 데이터는 전부 `latency_regression` 이므로 새 타입만 보면 과거 체인이 끊긴다.
    """
    types = az.LATENCY_BASELINE_SOURCE_TYPES
    assert "latency_regression" in types, "기존 데이터(2,059건)의 체인이 끊긴다"
    assert "latency_baseline" in types, "새로 쌓이는 baseline 을 못 읽는다"


def test_D_판정_경계_무회귀():
    """1.5배 **초과**만 회귀 — 경계값은 회귀가 아니다(기존 계약 유지)."""
    assert az._classify_latency(150.0, 100.0) is None          # 정확히 1.5배 → 아님
    assert az._classify_latency(150.1, 100.0) == "warn"
    assert az._classify_latency(100.0, 0.0) is None            # baseline 없음(첫 배치)


# ── 배선 층 (2026-08-23) ────────────────────────────────────────────────────
#   ★1차 변이에서 **생존 3건이 전부 배선**이었다(SQL 의 ANY(:types), 그리고
#     insight_type_for_latency 의 실제 사용처). 순수 함수만 잠그면 초록이 일찍 나오고
#     배선은 안 태운 채 끝난다 — 인계서가 경고한 바로 그 패턴이다.

import pytest  # noqa: E402


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return self._rows


class _FakeDB:
    """platform_events / platform_insights 두 쿼리를 구분해 답하는 대역."""

    def __init__(self, event_rows, baseline_rows):
        self.queries: list[tuple[str, dict]] = []
        self._ev, self._bl = event_rows, baseline_rows

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.queries.append((sql, params or {}))
        return _FakeResult(self._ev if "platform_events" in sql else self._bl)


async def _run(p95_vals, baseline):
    from datetime import UTC, datetime
    db = _FakeDB([("/api/v1/x", v) for v in p95_vals],
                 [("/api/v1/x", baseline)] if baseline else [])
    w1 = datetime(2026, 8, 23, tzinfo=UTC)
    w0 = datetime(2026, 8, 22, tzinfo=UTC)
    out = await az._analyze_latency_regression(db, w0, w1)
    return out, db


@pytest.mark.asyncio
async def test_E_배선_회귀아니면_baseline_타입으로_생성된다():
    out, _ = await _run([100.0] * 25, baseline=100.0)   # 1.5배 미만 → 회귀 아님
    assert len(out) == 1, "전제: 샘플 25개면 인사이트가 생성된다"
    assert out[0]["insight_type"] == "latency_baseline"
    assert out[0]["recommended_action"] == "none"


@pytest.mark.asyncio
async def test_F_배선_회귀면_regression_타입으로_생성된다():
    out, _ = await _run([300.0] * 25, baseline=100.0)   # 3배 → 회귀
    assert out[0]["insight_type"] == "latency_regression"   # ★E와 갈리는 지점
    assert out[0]["severity"] == "warn"
    assert out[0]["recommended_action"] == "heal"


@pytest.mark.asyncio
async def test_G_배선_baseline_조회가_두_타입을_모두_넘긴다():
    """★체인 유지의 실제 배선 — SQL 파라미터에 두 타입이 실려야 한다."""
    _, db = await _run([100.0] * 25, baseline=100.0)
    ins_q = [(s, p) for s, p in db.queries if "platform_insights" in s]
    assert ins_q, "baseline 조회 자체가 없다"
    sql, params = ins_q[0]
    assert "ANY(:types)" in sql, "단일 타입으로 조회하면 기존 2,059건 체인이 끊긴다"
    assert set(params.get("types") or []) == {"latency_regression", "latency_baseline"}
