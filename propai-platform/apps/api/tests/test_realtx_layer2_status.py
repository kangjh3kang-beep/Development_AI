"""2층 관측 표면 락 — **`0` 이 무엇을 뜻하는지**를 잠근다.

## 이 락이 막으려는 실제 오독

인계서는 *"두 번째 실행이 정정 탐지의 진짜 시험이다. **0 이면 탐지가 죽은 것**"* 이라고
적었다. 라이브로 재 보니 그 문장은 **아직 참이 아니었다**:

    2026-08-27T00:0xZ 실측 (활성 컨테이너 propai-api-8000 · 프로덕션 DB)
      realtx_trades            4,898
      realtx_corrections           0
      재관측 행                    0   ← updated_at > first_seen_at
      scan_state 36건 전부 baseline_done=true · last_scanned_at 2026-08-26T19:10Z

즉 **정정 탐지는 아직 한 번도 돌 기회가 없었다.** 그런데 `corrections = 0` 만 보면
*"탐지가 죽었다"* 와 **구별되지 않는다.**

★그래서 이 파일의 락은 **개수를 세는 것**이 아니라 **판정이 갈리는 것**을 본다.
  판정을 하나로 접는 변이(항상 `정정없음` 을 반환 등)는 개수 단언을 전부 통과한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.land_intelligence import realtx_layer2_status as S

_NOW = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)


# ══════════════════════════════════════════════════════════════
# 1. ★판정 — 네 상태가 **실제로 갈린다**(파티션형)
# ══════════════════════════════════════════════════════════════

def test_detection_states_are_all_distinct():
    """★핵심. 네 입력이 **서로 다른** 판정을 내야 한다.

    ★한 방향만 단언하면(예: `미시험` 케이스만) *"항상 미시험을 반환"* 하는 구현이
      통과한다 — 판정이 **접히는** 결함은 그렇게 새어 나간다. 그래서 **파티션**으로 본다.
    """
    cases = {
        "미수집":            dict(stored_rows=0,    reobserved_rows=0,  corrections_total=0),
        "미시험":            dict(stored_rows=4898, reobserved_rows=0,  corrections_total=0),
        "관측됨_정정없음":   dict(stored_rows=4898, reobserved_rows=120, corrections_total=0),
        "관측됨_정정있음":   dict(stored_rows=4898, reobserved_rows=120, corrections_total=7),
        "모순":              dict(stored_rows=4898, reobserved_rows=0,  corrections_total=7),
    }
    got = {name: S.detection_state(**kw)["state"] for name, kw in cases.items()}

    for name, state in got.items():
        assert state == name, f"{name} 입력이 {state} 로 판정됐다"
    # ★두 모집단이 실제로 갈리는지 — 판정을 하나로 접으면 여기서 죽는다
    assert len(set(got.values())) == len(cases), f"판정이 접혔다: {got}"


def test_zero_corrections_before_and_after_reobservation_differ():
    """★★`corrections = 0` 이 **재관측 여부로 갈린다** — 이 파일의 존재 이유."""
    untested = S.detection_state(stored_rows=4898, reobserved_rows=0, corrections_total=0)
    observed = S.detection_state(stored_rows=4898, reobserved_rows=4898, corrections_total=0)

    assert untested["state"] != observed["state"], (
        "★정정 0 이 '아직 시험 안 됨'과 '재관측했는데 안 변함'을 구별하지 못한다 — "
        "이게 인계서가 밟은 바로 그 오독이다"
    )
    # 사유도 사람에게 전달돼야 한다(상태 코드만 갈리고 문구가 같으면 화면에서 같아 보인다)
    assert untested["meaning"] != observed["meaning"]
    assert "정정 없음" in untested["meaning"] or "아니다" in untested["meaning"]


def test_live_snapshot_is_classified_as_untested_not_dead():
    """★라이브 실측값(2026-08-27T00:0xZ)을 그대로 넣으면 `미시험` 이어야 한다."""
    assert S.detection_state(
        stored_rows=4898, reobserved_rows=0, corrections_total=0
    )["state"] == "미시험"


# ══════════════════════════════════════════════════════════════
# 2. 신선도 — **「모름」을 수치로 위장하지 않는다**
# ══════════════════════════════════════════════════════════════

def test_never_scanned_is_not_a_number():
    """★미수집을 `999일 전` 같은 그럴듯한 수로 그리면 그것이 **관측으로 읽힌다**."""
    f = S.freshness(None, _NOW, S.STALE_TAIL_DAYS)
    assert f["state"] == S.NEVER_SCANNED
    assert f["age_hours"] is None, "미수집에 나이를 지어냈다"
    assert f["stale"] is None, "미수집을 '낡지 않음(False)'으로 단정했다"


def test_freshness_splits_on_the_boundary_both_ways():
    """★경계를 **양방향**으로 건다(§D-19) — 한쪽만 걸면 반대쪽이 무제한이 된다."""
    fresh = S.freshness(_NOW - timedelta(days=S.STALE_TAIL_DAYS - 1), _NOW, S.STALE_TAIL_DAYS)
    stale = S.freshness(_NOW - timedelta(days=S.STALE_TAIL_DAYS + 1), _NOW, S.STALE_TAIL_DAYS)
    assert fresh["stale"] is False and stale["stale"] is True, (fresh, stale)
    assert fresh["state"] != stale["state"]


def test_tail_threshold_exceeds_the_weekly_cadence():
    """꼬리 경계는 **주기보다 커야** 한다 — 7일 이하면 정상 실행을 낡음으로 신고한다."""
    assert S.STALE_TAIL_DAYS > 7, "주 1회 실행이 매번 '낡음'으로 오신고된다(위양성)"
    assert S.STALE_RECENT_DAYS > 1, "매일 실행이 매번 '낡음'으로 오신고된다(위양성)"
    # ★상한도 건다 — 무한히 늘리면 판정이 사라진다
    assert S.STALE_TAIL_DAYS <= 14, "경계가 너무 넓어 2주 중단도 '정상'이 된다"
    assert S.STALE_RECENT_DAYS <= 3


# ══════════════════════════════════════════════════════════════
# 3. ★꼬리 프로브 — **가장 오래된 꼬리 달**이어야 한다
# ══════════════════════════════════════════════════════════════

def test_tail_probe_is_never_inside_the_recent_window():
    """★달이 넘어가면 최근 창의 달이 꼬리로 내려온다 — 그 달을 프로브로 쓰면
    꼬리가 멈춰도 **'어제 돌았다'** 로 보인다(거짓 신선도)."""
    for month in range(1, 13):
        now = datetime(2026, month, 3, 3, 0, tzinfo=UTC)   # 월초 — 롤오버 직후
        probe = S._tail_probe_month(now)
        assert probe not in S._recent_window(now), (
            f"{now:%Y-%m} 프로브 {probe} 가 최근 창 안에 있다 — 거짓 신선도가 난다"
        )


def test_tail_probe_is_derived_from_the_task_constants():
    """★상수를 손으로 옮겨 적지 않았는지 — 옮겨 적은 사본은 **상한**이 된다."""
    from app.tasks import realtx_sync_task as T

    assert S._tail_probe_month(_NOW) == T.recent_months(_NOW, T.TAIL_MONTHS)[-1]
    # ★공허 방지 — 꼬리 구간이 비면 이 락 전체가 무의미하다
    assert T.TAIL_MONTHS > T.RECENT_MONTHS


# ══════════════════════════════════════════════════════════════
# 4. ★배선 — 실제 `build_layer2_status` 를 태운다
# ══════════════════════════════════════════════════════════════
#
# ★어제·오늘 이 저장소가 **네 번** 데인 자리다: 순수 함수에 변이를 9개 넣고
#   "9/9 CAUGHT" 라고 선언했는데 그 함수를 **부르는 층**엔 태우는 테스트가 0건이라
#   어떤 변이든 자동 생존이었다. 그래서 여기서는 **집계 SQL 의 결과가 판정까지
#   실려 나가는지**를 스텁 DB 로 직접 태운다.


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def first(self): return self._rows[0] if self._rows else None
    def fetchall(self): return self._rows


class _FakeDb:
    """SQL 문자열의 **특징 조각**으로 답을 고르는 스텁."""

    def __init__(self, *, stored, reobserved, corrections, by_kind,
                 scopes, last_recent, last_tail, schema=True):
        self._map = {
            "to_regclass": [("realtx_trades",)] if schema else [(None,)],
            "count(*) FROM realtx_trades WHERE updated_at": [(reobserved,)],
            "count(*) FROM realtx_trades": [(stored,)],
            "kind, count(*)": list(by_kind.items()),
            "count(*) FROM realtx_corrections": [(corrections,)],
            "FROM realtx_scan_state WHERE": None,      # 파라미터로 갈린다
            "FILTER (WHERE baseline_done)": [scopes],
        }
        self._last_recent, self._last_tail = last_recent, last_tail
        self.seen: list[str] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.seen.append(sql)
        if "FROM realtx_scan_state WHERE" in sql:
            months = (params or {}).get("months") or []
            # ★한 달만 오면 꼬리 프로브, 여러 달이면 최근 창 — 두 조회가 **갈린다**
            return _FakeResult([(self._last_tail if len(months) == 1 else self._last_recent,)])
        for needle, rows in self._map.items():
            if rows is not None and needle in sql:
                return _FakeResult(rows)
        raise AssertionError(f"스텁이 모르는 조회다(조회기 의심): {sql[:120]}")


@pytest.mark.asyncio
async def test_build_status_carries_counts_into_the_verdict():
    """★라이브 스냅샷을 그대로 태우면 `미시험` 이 나와야 한다 — **판정까지 배선**."""
    db = _FakeDb(stored=4898, reobserved=0, corrections=0, by_kind={},
                 scopes=(36, 36),
                 last_recent=_NOW - timedelta(hours=8), last_tail=None)
    out = await S.build_layer2_status(db, now=_NOW)

    assert db.seen, "조회가 한 번도 안 일어났다 — 이 단언이 공허하다"
    assert out["stored_rows"] == 4898
    assert out["reobserved_rows"] == 0
    assert out["detection"]["state"] == "미시험"
    assert out["collection"]["recent"]["stale"] is False
    # 꼬리는 아직 안 돌았다 — **미수집**이지 '낡음'이 아니다(수치 위장 금지)
    assert out["collection"]["tail"]["state"] == S.NEVER_SCANNED


@pytest.mark.asyncio
async def test_build_status_second_population_flips_the_verdict():
    """★대조군 — 재관측이 생기면 **같은 corrections=0 이 다른 판정**이 된다."""
    db = _FakeDb(stored=4898, reobserved=4898, corrections=0, by_kind={},
                 scopes=(60, 60),
                 last_recent=_NOW - timedelta(hours=8),
                 last_tail=_NOW - timedelta(days=2))
    out = await S.build_layer2_status(db, now=_NOW)
    assert out["detection"]["state"] == "관측됨_정정없음"
    assert out["collection"]["tail"]["stale"] is False


@pytest.mark.asyncio
async def test_build_status_flags_a_stalled_weekly_tail():
    """★★`#884` 부채의 핵심 — **주간 꼬리가 조용히 멈추면 드러나야 한다**."""
    db = _FakeDb(stored=4898, reobserved=4898, corrections=3, by_kind={"해제": 2, "등기": 1},
                 scopes=(60, 60),
                 last_recent=_NOW - timedelta(hours=8),      # 최근은 정상
                 last_tail=_NOW - timedelta(days=20))        # 꼬리만 멈췄다
    out = await S.build_layer2_status(db, now=_NOW)

    # ★두 모집단이 갈린다 — 최근은 정상인데 꼬리만 낡음
    assert out["collection"]["recent"]["stale"] is False
    assert out["collection"]["tail"]["stale"] is True, "주간 꼬리 중단이 드러나지 않는다"
    assert out["corrections"]["by_kind"] == {"해제": 2, "등기": 1}


@pytest.mark.asyncio
async def test_missing_schema_is_not_reported_as_empty():
    """★스키마 부재를 **0행과 섞지 않는다** — 섞으면 '수집이 죽었다'로 오독한다."""
    db = _FakeDb(stored=0, reobserved=0, corrections=0, by_kind={}, scopes=(0, 0),
                 last_recent=None, last_tail=None, schema=False)
    out = await S.build_layer2_status(db, now=_NOW)
    assert out["detection"]["state"] == "미배포"
    assert out["stored_rows"] is None, "미배포인데 0행이라고 단정했다"


# ══════════════════════════════════════════════════════════════
# 5. ★소비처가 **실제로 존재**하는지 — 이 PR 의 존재 이유
# ══════════════════════════════════════════════════════════════

def test_the_layer2_tables_now_have_a_reader():
    """★2층 3종 테이블을 **읽는** 코드가 있어야 한다(종전 0건).

    ★판정은 **파서로** 한다 — 소스 문자열 검사는 *이 수정을 설명하는 내 주석*에 걸린다
      (이 저장소에서 하루에 네 번 났다).
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(S))
    sql = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.strip().upper().startswith("SELECT")
    ]
    assert sql, "SELECT 상수를 못 찾았다 — 조회기 의심(공허한 참 방지)"
    joined = " ".join(sql)
    for table in ("realtx_trades", "realtx_corrections", "realtx_scan_state"):
        assert table in joined, f"{table} 를 읽는 코드가 없다"


def test_the_route_is_wired_to_the_service():
    """★라우트가 실제로 이 서비스를 부르는가 — 서비스만 있고 배선이 없으면 소비처 0 이다."""
    import ast
    import pathlib

    src = pathlib.Path(inspect_router_path()).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fns = [n for n in ast.walk(tree)
           if isinstance(n, ast.AsyncFunctionDef) and n.name == "realtx_layer2_status"]
    assert fns, "라우트 함수가 없다"
    names = {
        a.name for n in ast.walk(fns[0])
        if isinstance(n, ast.ImportFrom) for a in n.names
    }
    assert "build_layer2_status" in names, f"라우트가 서비스를 안 부른다: {names}"


def inspect_router_path() -> str:
    import apps.api.routers.market_report as m

    return m.__file__
