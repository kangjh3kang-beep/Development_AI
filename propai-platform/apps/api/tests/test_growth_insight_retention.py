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

import re

import pytest

from app.services.growth import insight_retention as R
from app.services.growth.insight_types import IDENTITY_FIELDS, INSIGHT_TYPES

# ══════════════════════════════════════════════════════════════
# 1. 카탈로그 — 목록이 상한이 되지 않게
# ══════════════════════════════════════════════════════════════

def test_every_insight_type_declares_an_identity_or_explicit_none():
    """★빠진 타입은 정리에서 **조용히 제외**된다 — 누락과 '정리 안 함'을 구별한다."""
    missing = sorted(set(INSIGHT_TYPES) - set(IDENTITY_FIELDS))
    assert not missing, f"IDENTITY_FIELD 에 선언되지 않은 타입: {missing}"


def test_catalog_has_no_ghost_types():
    """대조군 — 카탈로그에만 있고 실제 타입엔 없는 유령이 없어야 한다."""
    ghosts = sorted(set(IDENTITY_FIELDS) - set(INSIGHT_TYPES))
    assert not ghosts, f"유령 타입: {ghosts}"


def test_cleanable_excludes_the_ones_declared_none():
    got = R.cleanable_types()
    assert "heal_escalation" not in got, "critical(사람 점검)을 기계가 닫으면 안 된다"
    assert "improvement_proposal" not in got
    assert got.get("error_cluster") == ("signature",), "라이브 정체 필드는 signature 다"
    assert got.get("latency_regression") == ("key",)


# ══════════════════════════════════════════════════════════════
# 2. 인메모리 모델 — SQL 을 **해석**한다(하드코딩 금지)
# ══════════════════════════════════════════════════════════════

class _Res:
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return list(self._rows)


class _FakeInsightDb:
    """`platform_insights` 최소 모델. rows: [{id, insight_type, status, metrics, created_at}]"""

    #: 현재 시각(시간 단위 정수) — `created_at` 도 같은 단위로 둔다(결정적).
    now = 1000

    def __init__(self, rows): self.rows = rows; self.commits = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        if sql.startswith("WITH ranked"):
            itype, limit = p["itype"], p["limit"]
            # ★★가짜 DB 가 SQL 을 **거의 안 읽으면** 그것이 곧 무잠금이다
            #   (2026-08-27 독립 리뷰 H3 — ORDER BY 반전·PARTITION BY 축소·존재가드 삭제·
            #    LIMIT 삭제 **4개 변이가 전부 생존**했다. 의미론이 파이썬에 하드코딩돼 있었다).
            #   아래는 전부 **SQL 본문에서 파생**한다.
            assert "status = 'open'" in sql, f"open 가드가 사라졌다: {sql[:150]}"
            assert "rn > 1" in sql, f"rn 조건이 사라졌다: {sql[:150]}"
            assert "LIMIT :limit" in sql, "LIMIT 이 사라졌다"
            assert "make_interval" in sql, "최소 유예(created_at 임계)가 사라졌다"

            # PARTITION BY 식에서 정체 필드를 파생한다.
            part = sql.split("PARTITION BY", 1)[1].split("ORDER BY", 1)[0]
            fields = re.findall(r"metrics_json->>'([a-z_]+)'", part)
            assert fields, f"PARTITION BY 에서 정체 필드를 못 읽었다: {part[:120]}"
            by_window = "window_end - window_start" in part

            # ORDER BY 방향을 파생한다(반전 변이를 죽인다).
            order = sql.split("PARTITION BY", 1)[1].split("ORDER BY", 1)[1].split(")", 1)[0]
            newest_first = "created_at DESC" in order
            assert "created_at" in order, "ORDER BY 에 created_at 이 없다"

            # 존재/NULL 가드를 파생한다.
            guarded = [f for f in fields
                       if f"metrics_json ? '{f}'" in sql
                       and f"metrics_json->>'{f}' IS NOT NULL" in sql]

            cand = []
            for r in self.rows:
                if r["status"] != "open" or r["insight_type"] != itype:
                    continue
                if r["created_at"] > self.now - p["min_age_hours"]:
                    continue                       # 최소 유예
                if any(r["metrics"].get(f) is None for f in guarded):
                    continue                       # 존재/NULL 가드
                cand.append(r)

            groups: dict = {}
            for r in sorted(cand, key=lambda x: (x["created_at"], x["id"]),
                            reverse=newest_first):
                key = tuple(r["metrics"].get(f) for f in fields)
                if by_window:
                    key = (r.get("window_hours", 1), *key)
                groups.setdefault(key, []).append(r)
            out = [r["id"] for g in groups.values() for r in g[1:]]   # rn > 1
            return _Res([(i,) for i in out[:limit]])
        if sql.startswith("UPDATE platform_insights"):
            assert "status = 'open'" in sql, "갱신 조건에서 open 가드가 사라졌다"
            n = 0
            for r in self.rows:
                if r["id"] in p["ids"] and r["status"] == "open":
                    r["status"] = p["st"]; n += 1
            res = _Res([])
            res.rowcount = n           # ★실제 갱신 수(리뷰 M1 — 선택 수를 세면 거짓이 된다)
            return res
        raise AssertionError(f"모델이 모르는 SQL: {sql[:90]}")

    async def commit(self): self.commits += 1


def _row(i, t="latency_regression", st="open", key="/a", ts=1, field="key", wh=1):
    """`ts` 는 시간 단위. 기본값은 충분히 과거라 최소 유예를 통과한다."""
    return {"id": i, "insight_type": t, "status": st, "metrics": {field: key},
            "created_at": ts, "window_hours": wh}


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
async def test_a_single_run_is_bounded():
    """상한은 실행 전체를 묶는다(큰 재고를 한 트랜잭션에 붓지 않는다)."""
    db = _FakeInsightDb([_row(str(i), ts=i) for i in range(40)])
    res = await R.supersede_stale_insights(db, limit=7)
    n = sum(1 for r in db.rows if r["status"] == R.SUPERSEDED)
    assert 0 < n <= 7, n
    assert res["superseded"] == n


@pytest.mark.asyncio
async def test_limit_is_shared_so_the_biggest_backlog_is_not_starved():
    """★종전엔 알파벳 앞 타입이 상한을 **통째로** 먹어 재고 최대 타입이 굶었다.

    라이브에서 `latency_regression` 이 재고의 79%(2,298/3,127)인데 알파벳상
    `error_cluster`·`fallback_rate`·`latency_baseline` 뒤라, 상한이 낮아지는 순간
    **영구 기아**가 된다(2026-08-27 독립 리뷰 M2 · 실측 재현).
    """
    rows = ([_row(f"e{i}", t="error_cluster", key="sig", ts=i, field="signature")
             for i in range(9)]
            + [_row(f"l{i}", t="latency_regression", key="/x", ts=i) for i in range(9)])
    db = _FakeInsightDb(rows)
    res = await R.supersede_stale_insights(db, limit=8)
    assert res["by_type"].get("latency_regression", 0) > 0, (
        f"재고 최대 타입이 굶었다: {res['by_type']}"
    )
    # 대조군 — 두 타입이 실제로 갈렸는지(한쪽만 나오면 위 단언이 공허해질 수 있다)
    assert res["by_type"].get("error_cluster", 0) > 0, res["by_type"]


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
    monkeypatch.setattr(R, "IDENTITY_FIELDS", {"x": None})
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


# ══════════════════════════════════════════════════════════════
# 5. ★독립 적대 리뷰(2026-08-27)가 낸 것 — 전부 저자가 재현해 확증
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_same_run_distinct_defects_do_not_supersede_each_other():
    """★C1 — `recurring_verify_error` 는 생산자가 `(service, issue_type)` 로 군집한다.

    즉 **한 번의 `analyze_window` 가 같은 service 에 issue_type 개수만큼 행을 발행**한다.
    정체가 `service` 뿐이면 그것들이 서로를 승계해, 닫히는 것이 *옛 관측*이 아니라
    **같은 순간에 발행된 서로 다른 결함**이 된다. 게다가 한 윈도우가 한 트랜잭션이라
    `created_at` 이 전부 같아 **무엇이 살아남을지가 uuid 정렬 = 사실상 난수**였다.
    """
    same_ts = 5
    rows = [
        {"id": f"r{i}", "insight_type": "recurring_verify_error", "status": "open",
         "metrics": {"service": "feasibility", "issue_type": it},
         "created_at": same_ts, "window_hours": 1}
        for i, it in enumerate(("missing_field", "bad_ratio", "stale_data"))
    ]
    db = _FakeInsightDb(rows)
    res = await R.supersede_stale_insights(db)
    assert res["superseded"] == 0, f"같은 실행의 서로 다른 결함이 닫혔다: {res}"
    assert all(r["status"] == "open" for r in db.rows)


@pytest.mark.asyncio
async def test_the_same_issue_type_across_runs_still_supersedes():
    """대조군 — 복합키로 바꿨다고 **승계 자체가 죽으면** 안 된다."""
    rows = [
        {"id": "old", "insight_type": "recurring_verify_error", "status": "open",
         "metrics": {"service": "feasibility", "issue_type": "missing_field"},
         "created_at": 1, "window_hours": 1},
        {"id": "new", "insight_type": "recurring_verify_error", "status": "open",
         "metrics": {"service": "feasibility", "issue_type": "missing_field"},
         "created_at": 9, "window_hours": 1},
    ]
    db = _FakeInsightDb(rows)
    res = await R.supersede_stale_insights(db)
    assert res["superseded"] == 1
    assert {r["id"]: r["status"] for r in db.rows} == {"old": R.SUPERSEDED, "new": "open"}


@pytest.mark.asyncio
async def test_daily_trend_rows_are_not_eaten_by_hourly_rows():
    """★H2 — `analyze_window` 는 `window_hours` 와 무관하게 6개 분석기를 전부 돌린다.

    그래서 매시(1h) 실행과 매일(24h) 실행이 **같은 키**로 행을 낸다. 윈도우 폭이 정체에
    없으면 03:05 시간별 행이 02:30 의 **24시간 추세 행을 매일 닫는다** —
    `celery_app.py` 가 *"일 단위 추세 **누적**"* 이라고 적어 둔 것을 지운다.
    """
    db = _FakeInsightDb([
        _row("daily", key="/x", ts=1, wh=24),
        _row("hourly", key="/x", ts=9, wh=1),
    ])
    res = await R.supersede_stale_insights(db)
    assert res["superseded"] == 0, f"윈도우 폭이 다른데 승계됐다: {res}"
    assert {r["id"]: r["status"] for r in db.rows} == {"daily": "open", "hourly": "open"}


@pytest.mark.asyncio
async def test_freshly_created_rows_are_not_closed():
    """★H1 — 근거는 **나이**(30일 초과 1,212건)인데 규칙은 **승계**였다.

    유예가 없으면 **5분 전 행도 닫는다** — 근거와 구현이 어긋난다.
    """
    db = _FakeInsightDb([_row("a", key="/x", ts=_FakeInsightDb.now - 1),
                         _row("b", key="/x", ts=_FakeInsightDb.now)])
    res = await R.supersede_stale_insights(db, min_age_hours=6)
    assert res["superseded"] == 0, "유예 안의 행이 닫혔다"
    # 대조군 — 유예를 0 으로 낮추면 승계가 살아난다(유예가 승계 자체를 죽이지 않는다)
    db2 = _FakeInsightDb([_row("a", key="/x", ts=_FakeInsightDb.now - 1),
                          _row("b", key="/x", ts=_FakeInsightDb.now)])
    assert (await R.supersede_stale_insights(db2, min_age_hours=0))["superseded"] == 1


@pytest.mark.asyncio
async def test_reported_count_is_rows_changed_not_rows_selected():
    """★M1 — 조회와 갱신 사이에 사람이 ack 하면 **선택 수**가 거짓이 된다."""
    db = _FakeInsightDb([_row("a", key="/x", ts=1), _row("b", key="/x", ts=2),
                         _row("c", key="/x", ts=9)])

    orig = db.execute
    async def racing(stmt, params=None):
        sql = " ".join(str(stmt).split())
        if sql.startswith("UPDATE"):                 # 갱신 직전에 한 건이 ack 된다
            for r in db.rows:
                if r["id"] == "a":
                    r["status"] = "acknowledged"
        return await orig(stmt, params)
    db.execute = racing

    res = await R.supersede_stale_insights(db)
    actual = sum(1 for r in db.rows if r["status"] == R.SUPERSEDED)
    assert res["superseded"] == actual == 1, (res, actual)


def test_superseded_is_queryable_through_the_api():
    """★H5 — 어휘에 없으면 `GET ?status=superseded` 가 **400** 이라, 2,678행 전이를
    제품 안에서 확인할 방법이 0 이 된다(되돌리기가 원시 SQL 뿐).
    """
    from app.routers.growth import _ACK_STATUSES, _INSIGHT_STATUSES

    assert R.SUPERSEDED in _INSIGHT_STATUSES, "조회 어휘에 없다"
    # 대조군 — 그렇다고 **사람이 재처리**할 수 있으면 안 된다.
    assert R.SUPERSEDED not in _ACK_STATUSES, "승계분은 ack 대상이 아니다"


def test_failure_log_shares_the_probe_prefix():
    """★H4 — 실패 로그가 성공과 **다른 접두**면 라이브 프로브가 못 잡는다.

    계획서가 선언한 프로브: `docker logs … | grep 'growth 정리'`.
    종전 실패 로그는 `cleanup_insights 실패` 라 **안 걸렸다** — 즉 *"배치가 터졌다"* 와
    *"beat 가 아예 안 돌았다"* 가 운영자에게 똑같이 보였다.
    """
    import inspect

    from app.tasks import growth_tasks

    src = inspect.getsource(growth_tasks.cleanup_insights)
    logged = [ln for ln in src.splitlines() if "logger." in ln and "growth 정리" in ln]
    assert len(logged) >= 2, f"성공/실패 양쪽에 같은 접두가 없다: {logged}"
    assert any("error" in ln for ln in logged), "실패 경로가 error 로 안 남는다"


@pytest.mark.asyncio
async def test_rows_without_the_identity_field_are_left_alone():
    """★정체가 없는 행은 손대지 않는다 — 없으면 **서로를 승계**시킨다.

    `metrics_json->>field` 가 NULL 이면 `PARTITION BY` 가 그것들을 **같은 파티션**으로
    묶는다. 즉 *정체가 없다는 사실만 공유하는 무관한 행들*이 서로를 닫는다
    (2026-08-27 독립 리뷰 L2 · 라이브 실행으로 재현됨).

    오늘 선언된 7개 타입의 생산자는 전부 NULL 을 배제하지만(도달 불가), **새 타입이
    들어오면 즉시 결함**이 된다 — 그래서 가드를 두고 여기서 잠근다.
    """
    rows = [
        # 정체 필드가 아예 없는 행 둘 — 서로 무관하다.
        {"id": "n1", "insight_type": "latency_regression", "status": "open",
         "metrics": {"p95_ms": 10}, "created_at": 1, "window_hours": 1},
        {"id": "n2", "insight_type": "latency_regression", "status": "open",
         "metrics": {"p95_ms": 20}, "created_at": 2, "window_hours": 1},
        # 정체 값이 JSON null 인 행 둘 — 역시 무관하다.
        {"id": "z1", "insight_type": "latency_regression", "status": "open",
         "metrics": {"key": None}, "created_at": 3, "window_hours": 1},
        {"id": "z2", "insight_type": "latency_regression", "status": "open",
         "metrics": {"key": None}, "created_at": 4, "window_hours": 1},
    ]
    db = _FakeInsightDb(rows)
    res = await R.supersede_stale_insights(db)
    assert res["superseded"] == 0, f"정체 없는 행이 서로를 승계했다: {res}"
    assert all(r["status"] == "open" for r in db.rows)

    # ★대조군 — 정체가 **있는** 두 행은 정상적으로 승계돼야 한다(가드가 전부를 막으면 안 된다).
    db2 = _FakeInsightDb([_row("a", key="/x", ts=1), _row("b", key="/x", ts=2)])
    assert (await R.supersede_stale_insights(db2))["superseded"] == 1
