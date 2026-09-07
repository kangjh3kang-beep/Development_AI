"""결제 퍼널이 **성장루프에 도달하는가** — 수집·판정·표시를 한 단위로 잠근다 (2026-09-06).

## 왜 이 파일이 있나 (라이브 실측)

성장루프 인사이트 **200건 전체**에서 `billing`·`payment`·`결제`·`충전` 문자열이 **모두 0건**
이었다. 결제는 매출의 입구인데 **어디서 새는지 아무도 몰랐다.**

★그리고 프론트의 `funnel_step` 타입은 양쪽 화이트리스트에 **선언만 되고 호출 0건**이었다.
  거기에 계측만 더하면 이 저장소가 이미 데인 형태가 된다 —
  *"이벤트는 쌓이는데 analyzer 는 타입별 손수 스캐너만 돌려 **영원히 조회되지 않는다**"*(#797).
  그래서 이 파일은 **셋을 함께** 잠근다: 수집(프론트) · 판정(분석기) · 표시(라벨).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.services.growth import analyzer as _an
from app.services.growth.insight_types import INSIGHT_LABELS, INSIGHT_TYPES

_API = pathlib.Path(__file__).resolve().parents[1]
_WEB = _API.parents[1] / "apps/web"


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FunnelDb:
    def __init__(self, steps: dict[str, int]):
        self.steps = steps
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        self.sql.append(str(getattr(stmt, "text", stmt)))
        return _Rows([(k, v) for k, v in self.steps.items()])


# ═══════════════════════════════════════════════════════════════════════════
# ★판정 — 두 모집단
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_small_sample_is_withheld_not_judged() -> None:
    """★표본 부족은 **결함이 아니다** — 그러나 「판정 안 함」을 남긴다.

    「문제가 없었다」와 「판정할 표본이 없었다」는 다른 사실이고, 보는 사람이
    그것을 구별할 수 있어야 한다(이 저장소의 `note_coverage` 규율).
    """
    cov: dict = {}
    db = _FunnelDb({"view": _an.PAYMENT_FUNNEL_MIN_VIEWS - 1, "order_created": 1})
    out = await _an._analyze_payment_funnel(db, "w0", "w1", cov)
    assert out == [], "표본이 모자란데 판정했다"
    assert "payment_funnel_drop" in cov, "판정 보류를 아무 데도 남기지 않았다"


@pytest.mark.asyncio
async def test_enough_sample_and_a_real_drop_is_judged() -> None:
    """★반대 방향 — 표본이 충분하고 실제로 새면 **인사이트가 나온다**.

    이쪽을 걸지 않으면 "항상 보류"가 만점을 받고 축이 죽는다.
    """
    cov: dict = {}
    db = _FunnelDb({"view": 100, "order_created": 40, "pay_window_opened": 5})
    out = await _an._analyze_payment_funnel(db, "w0", "w1", cov)
    assert len(out) == 1, "이탈 87.5% 인데 판정하지 않았다"
    m = out[0]["metrics_json"]
    assert m["order_to_pay_drop_pct"] >= _an.PAYMENT_FUNNEL_DROP_WARN_PCT
    assert out[0]["insight_type"] == "payment_funnel_drop"
    # ★관측 경계를 지표에 적는다 — 「입금까지의 전환율」로 오독되지 않게.
    assert "observation_boundary" in m


@pytest.mark.asyncio
async def test_window_failure_is_critical_not_merely_warn() -> None:
    """★결제창이 **아예 못 뜬 것**은 사용자 변심이 아니라 **우리 결함일 가능성**이 높다."""
    db = _FunnelDb({"view": 100, "order_created": 90, "pay_window_opened": 88,
                    "pay_window_failed": 2})
    out = await _an._analyze_payment_funnel(db, "w0", "w1", {})
    assert out and out[0]["severity"] == "critical"
    assert out[0]["metrics_json"]["pay_window_failed"] == 2


@pytest.mark.asyncio
async def test_healthy_funnel_produces_nothing() -> None:
    """★대조군 — 정상이면 **아무것도 내지 않는다**(항상 경보하면 곧 무시된다)."""
    db = _FunnelDb({"view": 100, "order_created": 90, "pay_window_opened": 89})
    assert await _an._analyze_payment_funnel(db, "w0", "w1", {}) == []


@pytest.mark.asyncio
async def test_sql_narrows_to_the_payment_funnel_only() -> None:
    """다른 퍼널이 생겨도 결제 판정이 **오염되지 않는다**."""
    db = _FunnelDb({"view": 100})
    await _an._analyze_payment_funnel(db, "w0", "w1", {})
    assert db.sql, "쿼리를 아예 안 돌렸다"
    q = db.sql[0]
    assert "funnel_step" in q and "coin_topup" in q
    # ★아는 단계만 — 임의 값이 카디널리티를 늘리지 못하게(형제 `_CONTAM_SQL` 과 같은 규율).
    assert "IN ('view','order_created','pay_window_opened','pay_window_failed')" in q


# ═══════════════════════════════════════════════════════════════════════════
# ★배선 — 판정이 실제로 **불리는가**, 표시가 **따라오는가**
# ═══════════════════════════════════════════════════════════════════════════
def test_analyzer_actually_runs_the_payment_funnel_scanner() -> None:
    """★「함수가 있다」가 아니라 **`analyze_window` 가 그것을 태운다**.

    등록을 빠뜨리면 이벤트는 쌓이는데 **영원히 조회되지 않는다**(#797 의 형태).
    """
    src = (_API / "app/services/growth/analyzer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "analyze_window"
    )
    body = ast.get_source_segment(src, fn) or ""
    assert "_analyze_payment_funnel(" in body, "분석기 등록부에 없다 — 소비처 0"
    # ★대조군 — 형제 스캐너도 거기 있다(엉뚱한 함수를 본 것이 아니다).
    assert "_analyze_selection_contamination(" in body


def test_type_is_in_catalog_and_has_a_korean_label() -> None:
    """라벨이 없으면 화면에 **영문 enum 이 raw 로** 뜬다(이 저장소의 실측 사고)."""
    assert "payment_funnel_drop" in INSIGHT_TYPES
    assert INSIGHT_LABELS.get("payment_funnel_drop"), "표시명이 없다"


def test_frontend_emits_the_steps_the_analyzer_reads() -> None:
    """★**양쪽이 같은 낱말을 쓰는가.** 한쪽만 바꾸면 조용히 0건이 된다.

    분석기 SQL 의 `IN (...)` 목록과 프론트가 보내는 `step` 문자열을 대조한다.
    """
    api_src = (_API / "app/services/growth/analyzer.py").read_text(encoding="utf-8")
    i = api_src.index("_PAYMENT_FUNNEL_SQL")
    seg = api_src[i : i + 1200]
    j = seg.index("IN (")
    steps = {
        s.strip().strip("'")
        for s in seg[j + 4 : seg.index(")", j)].split(",")
    }
    assert steps, "분석기 단계 목록을 못 읽었다 — 파서가 낡았다"

    web_src = (_WEB / "components/mypage/CoinsClient.tsx").read_text(encoding="utf-8")
    missing = [s for s in steps if f'"{s}"' not in web_src]
    assert not missing, f"분석기는 읽는데 프론트가 **보내지 않는** 단계: {missing}"
    # ★대조군 — 프론트 파일을 실제로 읽었다.
    assert "trackTopupStep(" in web_src


def test_payment_funnel_events_are_collected_in_full() -> None:
    """★기본 `funnel_step` 은 **15%** 다 — 결제를 그대로 계측하면 85%가 버려진다.

    저빈도·고가치 퍼널에서 「이탈 3건」이 실제로는 20건일 수 있다.
    """
    web = (_WEB / "components/mypage/CoinsClient.tsx").read_text(encoding="utf-8")
    assert 'sample: "always"' in web, "결제 퍼널이 샘플링에 걸린다"
    coll = (_WEB / "lib/growth/event-collector.ts").read_text(encoding="utf-8")
    assert "funnel_step: 0.15" in coll, "★기본 비율이 바뀌었다 — 이 락의 전제를 다시 보라"
    assert "if (always) return true;" in coll, "오버라이드가 실제로 동작하지 않는다"
