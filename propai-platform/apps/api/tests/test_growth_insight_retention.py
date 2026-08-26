"""성장 인사이트 정리 락 — 승계된 옛 행만 닫고, 나머지는 **건드리지 않는다**.

## 왜 (라이브 실측 2026-08-26 · 활성 컨테이너)

    status 분포        open **3,127** / acknowledged **16**
    expired·superseded **0**            ← 닫는 길이 아예 없었다
    latency_regression open 2,298 중 **30일 초과 1,212건**
    ★승계된 옛 행(같은 키에 더 새 행 존재) = 전 타입 **2,678** → 정리 시 open **449**

## ★이 락이 **못 보는** 것

1. **실제 Postgres 문법**은 검증하지 않는다 — `_FakeInsightDb` 는 SQL 을 해석하지만
   가짜다(`row_number()` 를 파이썬으로 흉내낸다). 문법·인덱스는 라이브에서만 드러난다.
2. **celery beat 가 실제로 발화하는지**는 보지 않는다 — 스케줄 등록만 소스로 잠근다.
3. 정리 **후에도 화면이 옳게 세는지**는 이 파일 밖이다(`actionable_counts` 는 `status` 로 거른다).
"""

from __future__ import annotations

import pytest

from app.services.growth import insight_retention as R
from app.services.growth.insight_types import IDENTITY_FIELD, INSIGHT_TYPES

# ══════════════════════════════════════════════════════════════
# 1. 카탈로그 — 목록이 상한이 되지 않게
# ══════════════════════════════════════════════════════════════

def test_every_insight_type_declares_an_identity_or_explicit_none():
    """★빠진 타입은 정리에서 **조용히 제외**된다 — 누락과 '정리 안 함'을 구별한다."""
    missing = sorted(set(INSIGHT_TYPES) - set(IDENTITY_FIELD))
    assert not missing, f"IDENTITY_FIELD 에 선언되지 않은 타입: {missing}"


def test_catalog_has_no_ghost_types():
    """대조군 — 카탈로그에만 있고 실제 타입엔 없는 유령이 없어야 한다."""
    ghosts = sorted(set(IDENTITY_FIELD) - set(INSIGHT_TYPES))
    assert not ghosts, f"유령 타입: {ghosts}"


def test_cleanable_excludes_the_ones_declared_none():
    got = R.cleanable_types()
    assert "heal_escalation" not in got, "critical(사람 점검)을 기계가 닫으면 안 된다"
    assert "improvement_proposal" not in got
    assert got.get("error_cluster") == "signature", "라이브 정체 필드는 signature 다"
    assert got.get("latency_regression") == "key"


# ══════════════════════════════════════════════════════════════
# 2. 인메모리 모델 — SQL 을 **해석**한다(하드코딩 금지)
# ══════════════════════════════════════════════════════════════

class _Res:
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return list(self._rows)


class _FakeInsightDb:
    """`platform_insights` 최소 모델. rows: [{id, insight_type, status, metrics, created_at}]"""

    def __init__(self, rows): self.rows = rows; self.commits = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        if sql.startswith("WITH ranked"):
            field, itype, limit = p["field"], p["itype"], p["limit"]
            # ★조건을 SQL 에서 읽는다 — 하드코딩하면 조건을 지우는 변이가 생존한다.
            assert "status = 'open'" in sql and "rn > 1" in sql, f"조건이 사라졌다: {sql[:120]}"
            cand = [r for r in self.rows
                    if r["status"] == "open" and r["insight_type"] == itype
                    and field in r["metrics"]]
            groups: dict = {}
            for r in sorted(cand, key=lambda x: (x["created_at"], x["id"]), reverse=True):
                groups.setdefault(r["metrics"][field], []).append(r)
            out = [r["id"] for g in groups.values() for r in g[1:]]   # rn > 1
            return _Res([(i,) for i in out[:limit]])
        if sql.startswith("UPDATE platform_insights"):
            assert "status = 'open'" in sql, "갱신 조건에서 open 가드가 사라졌다"
            for r in self.rows:
                if r["id"] in p["ids"] and r["status"] == "open":
                    r["status"] = p["st"]
            return _Res([])
        raise AssertionError(f"모델이 모르는 SQL: {sql[:90]}")

    async def commit(self): self.commits += 1


def _row(i, t="latency_regression", st="open", key="/a", ts=1, field="key"):
    return {"id": i, "insight_type": t, "status": st, "metrics": {field: key}, "created_at": ts}


# ══════════════════════════════════════════════════════════════
# 3. ★두 모집단 — 승계분은 닫히고 최신은 남는다
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_only_superseded_rows_are_closed_newest_stays_open():
    db = _FakeInsightDb([
        _row("a", key="/x", ts=1), _row("b", key="/x", ts=2), _row("c", key="/x", ts=3),
        _row("d", key="/y", ts=1),
    ])
    res = await R.supersede_stale_insights(db)
    got = {r["id"]: r["status"] for r in db.rows}
    assert got == {"a": R.SUPERSEDED, "b": R.SUPERSEDED, "c": "open", "d": "open"}, got
    assert res["superseded"] == 2


@pytest.mark.asyncio
async def test_a_single_row_key_is_never_touched():
    """대조군 — 승계가 없으면 **아무것도 닫지 않는다**(항상 닫는 코드는 만점이 된다)."""
    db = _FakeInsightDb([_row("a", key="/x"), _row("b", key="/y")])
    res = await R.supersede_stale_insights(db)
    assert res["superseded"] == 0
    assert all(r["status"] == "open" for r in db.rows)


@pytest.mark.asyncio
async def test_acknowledged_rows_are_untouchable():
    """★사람이 이미 판단한 것을 기계가 덮지 않는다."""
    db = _FakeInsightDb([
        _row("a", key="/x", ts=1, st="acknowledged"),
        _row("b", key="/x", ts=2), _row("c", key="/x", ts=3),
    ])
    await R.supersede_stale_insights(db)
    got = {r["id"]: r["status"] for r in db.rows}
    assert got["a"] == "acknowledged"
    assert got == {"a": "acknowledged", "b": R.SUPERSEDED, "c": "open"}, got


@pytest.mark.asyncio
async def test_types_declared_none_are_not_cleaned():
    """`heal_escalation`(critical) 은 승계가 있어도 열려 있어야 한다."""
    db = _FakeInsightDb([
        {"id": "h1", "insight_type": "heal_escalation", "status": "open",
         "metrics": {"service": "s"}, "created_at": 1},
        {"id": "h2", "insight_type": "heal_escalation", "status": "open",
         "metrics": {"service": "s"}, "created_at": 2},
    ])
    res = await R.supersede_stale_insights(db)
    assert res["superseded"] == 0
    assert all(r["status"] == "open" for r in db.rows)


@pytest.mark.asyncio
async def test_running_twice_changes_nothing_the_second_time():
    """멱등 — 두 번째 실행은 0건이어야 한다."""
    db = _FakeInsightDb([_row("a", ts=1), _row("b", ts=2), _row("c", ts=3)])
    first = await R.supersede_stale_insights(db)
    second = await R.supersede_stale_insights(db)
    assert first["superseded"] == 2 and second["superseded"] == 0


@pytest.mark.asyncio
async def test_limit_bounds_a_single_run():
    db = _FakeInsightDb([_row(str(i), ts=i) for i in range(10)])
    res = await R.supersede_stale_insights(db, limit=3)
    assert res["superseded"] == 3
    assert sum(1 for r in db.rows if r["status"] == R.SUPERSEDED) == 3


@pytest.mark.asyncio
async def test_dry_run_reports_without_writing():
    db = _FakeInsightDb([_row("a", ts=1), _row("b", ts=2)])
    res = await R.supersede_stale_insights(db, dry_run=True)
    assert res["superseded"] == 1 and res["dry_run"] is True
    assert all(r["status"] == "open" for r in db.rows)
    assert db.commits == 0


@pytest.mark.asyncio
async def test_empty_catalog_fails_loudly(monkeypatch):
    """★조용한 무동작 금지 — 카탈로그가 비면 '정리할 게 없다'가 아니라 결함이다."""
    monkeypatch.setattr(R, "IDENTITY_FIELD", {"x": None})
    with pytest.raises(RuntimeError):
        await R.supersede_stale_insights(_FakeInsightDb([]))


# ══════════════════════════════════════════════════════════════
# 4. 배선 — beat 에 등록됐는가
# ══════════════════════════════════════════════════════════════

def test_cleanup_is_registered_on_the_beat_schedule():
    """★서비스만 만들고 안 부르면 재고는 그대로다."""
    import ast
    import inspect
    from pathlib import Path

    # …/app/services/growth/insight_retention.py → parents[2] = …/app
    src = Path(inspect.getsourcefile(R)).resolve().parents[2] / "tasks/celery_app.py"
    assert src.is_file(), f"★대상 파일을 못 찾았다(경로 계산 오류): {src}"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    names = {n.value for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "app.tasks.growth_tasks.cleanup_insights" in names, "beat 에 정리 잡이 없다"
    # 대조군 — 이 추출기가 살아 있는가(공허한 참 방지)
    assert "app.tasks.growth_tasks.analyze_growth" in names, "★추출기 사망 의심"
