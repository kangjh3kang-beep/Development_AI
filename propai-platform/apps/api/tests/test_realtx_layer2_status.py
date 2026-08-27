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
from app.tasks import realtx_sync_task as T


def _producer_kinds() -> list[str]:
    """★정정 `kind` 어휘를 **생산자에서 파생**한다(리뷰 M4).

    종전 픽스처는 `{"해제": 2, "등기": 1}` 이었는데 `diff_mutable` 이 실제로 내는 값은
    `cancelled` · `registry_added` · `field_changed` 다. 락은 **임의 dict 통과**만
    잠갔고, 이 파일을 읽는 다음 사람은 *"API 가 한국어 kind 를 낸다"* 고 믿게 된다
    (§C-10 — 픽스처에 쓴 근거도 검증 대상).
    """
    from app.services.land_intelligence.realtx_store import diff_mutable

    seen: list[str] = []
    for prev, cur in (
        ({"cancel_type": "", "registered_date": "", "dealing_type": "중개거래"},
         {"cancel_type": "O", "registered_date": "", "dealing_type": "중개거래"}),
        ({"cancel_type": "", "registered_date": "", "dealing_type": "중개거래"},
         {"cancel_type": "", "registered_date": "26.08.07", "dealing_type": "중개거래"}),
        ({"cancel_type": "", "registered_date": "", "dealing_type": "중개거래"},
         {"cancel_type": "", "registered_date": "", "dealing_type": "직거래"}),
    ):
        for ch in diff_mutable(prev, cur):
            if ch["kind"] not in seen:
                seen.append(ch["kind"])
    assert len(seen) >= 2, f"생산자에서 kind 를 못 뽑았다(조회기 의심): {seen}"
    return seen


def test_correction_kind_vocabulary_is_not_invented():
    """★생산자가 내는 `kind` 가 **한국어가 아니다** — 픽스처가 거짓을 말하지 않게 잠근다."""
    kinds = _producer_kinds()
    assert "해제" not in kinds and "등기" not in kinds, (
        f"픽스처 어휘와 생산자 어휘가 어긋난다: {kinds}"
    )
    assert all(k.isascii() for k in kinds), kinds

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
    """★미수집을 `999일 전` 같은 그럴듯한 수로 그리면 그것이 **관측으로 읽힌다**.

    ★독립 리뷰 — 종전엔 `f["state"] == S.NEVER_SCANNED` 뿐이라 **상수를 `""` 로 바꿔도
      통과**했다(동어반복). 리터럴로 못 박는다.
    """
    assert S.NEVER_SCANNED == "미수집" and S.CLOCK_ANOMALY == "시각이상"
    assert S.UNDERIVABLE == "판정불가"
    f = S.freshness(None, _NOW, S.STALE_TAIL_DAYS)
    assert f["state"] == S.NEVER_SCANNED
    assert f["state"] in _UNKNOWN_TOKENS and f["state"] != ""
    assert f["age_hours"] is None, "미수집에 나이를 지어냈다"
    assert f["stale"] is None, "미수집을 '낡지 않음(False)'으로 단정했다"


def test_freshness_splits_on_the_boundary_both_ways():
    """★경계를 **양방향**으로 건다(§D-19) — 한쪽만 걸면 반대쪽이 무제한이 된다.

    ★독립 리뷰 — 종전엔 ±1일이라 `>` 를 `>=` 로 바꾸는 변이가 **경계를 안 밟아** 생존했다.
      → **정확히 경계 위**와 그 **1초 앞뒤**를 태운다.
    """
    exact = S.freshness(_NOW - timedelta(days=S.STALE_TAIL_DAYS), _NOW, S.STALE_TAIL_DAYS)
    just_over = S.freshness(_NOW - timedelta(days=S.STALE_TAIL_DAYS, seconds=1),
                            _NOW, S.STALE_TAIL_DAYS)
    just_under = S.freshness(_NOW - timedelta(days=S.STALE_TAIL_DAYS, seconds=-1),
                             _NOW, S.STALE_TAIL_DAYS)
    # ★경계 **위는 아직 정상**(`>` 이지 `>=` 가 아니다) — 이 줄이 M05 변이를 죽인다
    assert exact["stale"] is False, "경계 정각을 '낡음'으로 신고했다(>= 회귀)"
    assert just_over["stale"] is True and just_under["stale"] is False
    assert just_over["state"] != just_under["state"]


def test_age_is_reported_in_hours_not_some_other_unit():
    """★`age_hours` 의 **단위** — 분·초로 바뀌어도 아무 단언이 없었다(독립 리뷰 M08)."""
    f = S.freshness(_NOW - timedelta(hours=3), _NOW, S.STALE_TAIL_DAYS)
    assert f["age_hours"] == 3.0, f
    assert S.freshness(_NOW - timedelta(minutes=90), _NOW, 8)["age_hours"] == 1.5


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
    꼬리가 멈춰도 **'어제 돌았다'** 로 보인다(거짓 신선도).

    ★★리뷰 L3: 종전의 12개월 루프는 **장식**이었다. 두 목록이 같은 `now` 에서 같은
      걸음으로 만들어지므로 인덱스 6 이 0~2 와 같아질 수 **원리적으로** 없었다.
      → 진짜 위험은 *"프로브가 어제까지 최근 창이던 달인가"* 이므로 **그것**을 단언한다:
        프로브 달은 **`STALE_TAIL_DAYS` 보다 훨씬 전에** 최근 창을 떠났어야 한다.
    """
    for month in range(1, 13):
        for day in (1, 15, 28):                     # ★월초·중순·월말 전부
            now = datetime(2026, month, day, 3, 0, tzinfo=UTC)
            probe = S._tail_probe_month(now)
            assert probe not in S._recent_window(now), (
                f"{now:%Y-%m-%d} 프로브 {probe} 가 최근 창 안에 있다"
            )
            # ★핵심 — 프로브가 최근 창을 떠난 지 **얼마나 됐나**. 하루 전에 떠났다면
            #   그 달의 last_scanned_at 은 *최근 창으로서* 찍힌 값이라 거짓 신선도가 난다.
            left_recent_at = None
            for back in range(0, 400):
                past = now - timedelta(days=back)
                if probe in S._recent_window(past):
                    left_recent_at = back
                    break
            assert left_recent_at is None or left_recent_at > S.STALE_TAIL_DAYS, (
                f"{now:%Y-%m-%d} 프로브 {probe} 가 {left_recent_at}일 전까지 최근 창이었다 — "
                f"경계 {S.STALE_TAIL_DAYS}일 안이라 거짓 신선도가 난다"
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
    """SQL 문자열의 **특징 조각**으로 답을 고르는 스텁.

    ★★한계를 명시한다(리뷰 H1): 이 스텁은 **SQL 의 의미를 태우지 못한다.** 조각만
      남으면 `>` 를 `>=` 로 바꾸든 `max` 를 `min` 으로 바꾸든 같은 값을 돌려준다.
      → **SQL 의미는 `test_realtx_layer2_status_pg.py`(실 Postgres)가 잠근다.**
        이 파일은 **파이썬 층의 판정·배선**만 본다.
    """

    def __init__(self, *, stored, reobserved, corrections, by_kind, scopes,
                 last_recent, last_tail, schema=True, sigungu_ever=6,
                 trade_scopes=None, targets=6,
                 oldest_recent=None, oldest_tail=None, n_recent=36, n_tail=6):
        self._schema = schema
        self._map = {
            "count(DISTINCT split_part": [(sigungu_ever,)],
            "DISTINCT prop_type, lawd_cd, deal_ym": [(
                scopes[0] if trade_scopes is None else trade_scopes,)],
            "count(*) FROM realtx_trades WHERE updated_at": [(reobserved,)],
            "count(*) FROM realtx_trades": [(stored,)],
            "kind, count(*)": list(by_kind.items()),
            "count(*) FROM realtx_corrections": [(corrections,)],
            "FILTER (WHERE baseline_done)": [scopes],
        }
        self._recent = (last_recent, oldest_recent if oldest_recent is not None else last_recent, n_recent)
        self._tail = (last_tail, oldest_tail if oldest_tail is not None else last_tail, n_tail)
        self._targets = targets
        self.seen: list[str] = []

    def begin_nested(self):
        """★세이브포인트 — 실패한 파생이 **뒤 조회를 죽이지 않게** 감싼다.

        실 Postgres 락이 잡은 결함이다(`try/except` 만으로는 트랜잭션이 오염된다).
        """
        db = self

        class _SP:
            async def __aenter__(self): return db
            async def __aexit__(self, *a): return False

        return _SP()

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.seen.append(sql)
        if "to_regclass" in sql:
            n = len(S._LAYER2_TABLES) if self._schema else 0
            return _FakeResult([(n,)])
        if "FROM realtx_scan_state WHERE" in sql:
            months = (params or {}).get("months") or []
            # ★한 달만 오면 꼬리 프로브, 여러 달이면 최근 창 — 두 조회가 **갈린다**
            return _FakeResult([self._tail if len(months) == 1 else self._recent])
        if "FROM user_project_store" in sql:
            if self._targets is None:
                raise RuntimeError("스토어 조회 실패(파생 불가 재현)")
            # derive_scan_targets 가 훑는 blob — 시군구 self._targets 개를 만든다
            return _FakeResult([
                ({"landSchedule": {"rows": [{"pnu": f"{41370 + i}" + "0" * 14}]}},)
                for i in range(self._targets)
            ])
        for needle, rows in self._map.items():
            if needle in sql:
                return _FakeResult(rows)
        raise AssertionError(f"스텁이 모르는 조회다(조회기 의심): {sql[:120]}")


class _FrozenDatetime:
    """`datetime.now(tz=…)` 만 고정한다(나머지는 원본에 위임)."""

    def __init__(self, when: datetime) -> None:
        self._when = when

    def now(self, tz=None):  # noqa: A003
        return self._when

    def __getattr__(self, name):
        import datetime as _dt
        return getattr(_dt.datetime, name)


_FRESH = timedelta(hours=8)


def _db(**kw):
    kw.setdefault("by_kind", {})
    kw.setdefault("last_recent", _NOW - _FRESH)
    kw.setdefault("last_tail", _NOW - timedelta(days=2))
    kw.setdefault("scopes", (36, 36))
    return _FakeDb(**kw)


# ── ★M7: **다섯 판정 전부**를 배선을 통해 태운다 ──────────────────────────
#   종전엔 배선으로 단언되는 판정이 `미시험`·`관측됨_정정없음`·`미배포` **셋뿐**이었고,
#   `모순`·`미수집` 은 한 번도 안 태워졌다. 그래서 `stored_rows=stored` 를
#   `stored_rows=1` 로 바꾸는 변이가 **생존**했다(리뷰 M7).

@pytest.mark.asyncio
@pytest.mark.parametrize(("kw", "expected"), [
    (dict(stored=0, reobserved=0, corrections=0), "미수집"),
    (dict(stored=4898, reobserved=0, corrections=0), "미시험"),
    (dict(stored=4898, reobserved=120, corrections=0), "관측됨_정정없음"),
    (dict(stored=4898, reobserved=120, corrections=7), "관측됨_정정있음"),
    (dict(stored=4898, reobserved=0, corrections=7), "모순"),
    (dict(stored=4898, reobserved=120, corrections=0, trade_scopes=99), "상태소실"),
])
async def test_every_verdict_is_reachable_through_the_wiring(kw, expected):
    """★배선을 통해 **모든 판정이 실제로 도달**하는가 — 파티션형."""
    kw.setdefault("by_kind", {"cancelled": kw.get("corrections", 0)} if kw.get("corrections") else {})
    out = await S.build_layer2_status(_db(**kw), now=_NOW)
    assert out["detection"]["state"] == expected, out["detection"]


@pytest.mark.asyncio
async def test_stored_rows_is_carried_not_invented():
    """★`stored_rows` 가 조회에서 오는가 — 상수로 바꾸는 변이를 잡는다(리뷰 M7)."""
    a = await S.build_layer2_status(_db(stored=4898, reobserved=0, corrections=0), now=_NOW)
    b = await S.build_layer2_status(_db(stored=17, reobserved=0, corrections=0), now=_NOW)
    assert (a["stored_rows"], b["stored_rows"]) == (4898, 17)


@pytest.mark.asyncio
async def test_live_snapshot_reads_as_untested():
    """★라이브 스냅샷(2026-08-27T00:0xZ)을 그대로 태우면 `미시험` 이어야 한다."""
    out = await S.build_layer2_status(
        _db(stored=4898, reobserved=0, corrections=0, last_tail=None), now=_NOW)
    assert out["detection"]["state"] == "미시험"
    assert out["collection"]["recent"]["stale"] is False
    # 꼬리는 아직 안 돌았다 — **미수집**이지 '낡음'이 아니다(수치 위장 금지)
    assert out["collection"]["tail"]["state"] == S.NEVER_SCANNED


# ── ★H2: 부분 정지가 **드러나야** 한다 ────────────────────────────────────

@pytest.mark.asyncio
async def test_partial_stall_is_not_hidden_by_the_freshest_scope():
    """★★리뷰 H2 — 36 스코프 중 **하나만** 최근이고 나머지가 몇 주째 죽었을 때.

    종전 `max(last_scanned_at)` 은 이 경우 `stale: False`(정상)를 냈다.
    *"이 단언이 초록일 때 1/36 만 도는 수집도 초록인가"* 에 **예**였던 것이다.
    """
    healthy = await S.build_layer2_status(
        _db(stored=4898, reobserved=10, corrections=0,
            last_recent=_NOW - _FRESH, oldest_recent=_NOW - _FRESH), now=_NOW)
    stalled = await S.build_layer2_status(
        _db(stored=4898, reobserved=10, corrections=0,
            last_recent=_NOW - _FRESH,                    # 하나는 8시간 전(신선)
            oldest_recent=_NOW - timedelta(days=21)),     # 나머지는 3주째 죽음
        now=_NOW)

    # ★두 모집단이 갈린다 — 갈리지 않으면 부분 정지가 원리적으로 안 보인다
    assert healthy["collection"]["recent"]["stale"] is False
    assert stalled["collection"]["recent"]["stale"] is True, (
        "가장 신선한 스코프가 부분 정지를 가린다 — max() 회귀"
    )
    # 참고값(newest)은 여전히 신선해야 한다 — 판정이 min 을 쓴다는 증거
    assert stalled["collection"]["recent"]["newest_scanned_at"] is not None


@pytest.mark.asyncio
async def test_weekly_tail_stall_surfaces():
    """★★`#884` 부채의 핵심 — **주간 꼬리가 조용히 멈추면 드러나야 한다**."""
    kinds = _producer_kinds()
    out = await S.build_layer2_status(
        _db(stored=4898, reobserved=4898, corrections=3,
            by_kind={kinds[0]: 2, kinds[1]: 1},
            last_recent=_NOW - _FRESH,                 # 최근은 정상
            last_tail=_NOW - timedelta(days=20)),      # 꼬리만 멈췄다
        now=_NOW)
    assert out["collection"]["recent"]["stale"] is False
    assert out["collection"]["tail"]["stale"] is True, "주간 꼬리 중단이 드러나지 않는다"
    assert out["corrections"]["by_kind"] == {kinds[0]: 2, kinds[1]: 1}


@pytest.mark.asyncio
async def test_missing_schema_is_not_reported_as_empty():
    """★스키마 부재를 **0행과 섞지 않는다** — 섞으면 '수집이 죽었다'로 오독한다."""
    out = await S.build_layer2_status(
        _db(stored=0, reobserved=0, corrections=0, schema=False), now=_NOW)
    assert out["detection"]["state"] == "미배포"
    assert out["stored_rows"] is None, "미배포인데 0행이라고 단정했다"


@pytest.mark.asyncio
async def test_now_argument_is_honoured():
    """★독스트링이 선언한 **결정성** 계약(리뷰 L2) — 무잠금이었다."""
    when = datetime(2020, 5, 17, 4, 0, tzinfo=UTC)
    out = await S.build_layer2_status(
        _db(stored=1, reobserved=0, corrections=0), now=when)
    assert out["as_of"] == when.isoformat()
    assert out["collection"]["recent"]["months"] == T.recent_months(when, T.RECENT_MONTHS)


# ══════════════════════════════════════════════════════════════
# 4-2. ★쿼터 — **한도를 지어내지 않는다**(`#884` P-d 부채의 관측 절반)
# ══════════════════════════════════════════════════════════════
#
# `targets` 는 사용자가 늘면 **무한히 는다**. `#884` 의 39.4 스코프/일 산술은
# **시군구 6 고정 가정**이었고, 그 부채는 미봉합으로 남았다.
#
# ★여기서 고치지 않는 이유: 상한을 걸어 대상을 자르면 **그 사용자의 지역이 조용히
#   수집에서 빠진다** — 지금 결함보다 나쁘다. 그래서 자르지 않고 **보이게** 만든다.
#
# ★그리고 MOLIT 일일 한도는 **여전히 미측정**이다(재 본 것은 *"현재 소비량에서 진짜
#   HTTP 429 가 0건"* 까지). 없는 한도를 상수로 박으면 다음 사람이 그것을 관측으로 읽는다.


#: ★「모름」을 뜻하는 **닫힌 토큰 집합**. 이 밖의 값은 전부 *"안다"* 는 주장이다.
_UNKNOWN_TOKENS = frozenset({"미측정", "판정불가", "미수집", "미배포", "시각이상"})


def test_quota_does_not_fabricate_a_limit():
    """★★한도는 **모른다**고 적혀야 한다 — 수치로 위장하면 그것이 관측이 된다.

    ★★2026-08-27 독립 리뷰 — **종전 단언은 동어반복이었다.**
      `view["limit"] == S.QUOTA_LIMIT_UNKNOWN` 은 상수를 `"무제한"` 으로 바꿔도 **참**이고,
      `not isinstance(…, (int, float))` 도 문자열이면 통과한다. 즉 이 락의 이름이
      *"한도를 지어내지 않는다"* 인데 **정반대 주장("무제한")을 막지 못했다.**
      → **리터럴로 못 박고**, 「모름」 어휘를 **닫힌 집합**으로 검사한다.
    """
    assert S.QUOTA_LIMIT_UNKNOWN == "미측정", (
        f"「모름」 어휘가 바뀌었다 — {S.QUOTA_LIMIT_UNKNOWN!r}. "
        "'무제한'·'없음' 류는 **안다는 주장**이라 이 모듈의 계약 위반이다"
    )
    view = S.quota_view(6)
    assert view["limit"] in _UNKNOWN_TOKENS, view["limit"]
    assert not isinstance(view["limit"], (int, float))


def test_quota_arithmetic_is_derived_from_the_task_constants():
    """★상수를 손으로 옮겨 적으면 그 사본이 상한이 된다 — 파생인지 확인한다."""
    from app.tasks import realtx_sync_task as T

    view = S.quota_view(6)
    assert view["daily_scopes"] == 6 * T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)
    assert view["weekly_tail_scopes"] == 6 * (T.TAIL_MONTHS - T.RECENT_MONTHS) * len(T.TAIL_PROP_TYPES)
    # ★라이브 기준선(2026-08-26T19:10Z 실측 36 스코프/일)과 **파생으로** 대조한다.
    #   ★★리뷰 L4: 종전엔 `== 36` 리터럴이라 `RECENT_MONTHS` 를 정당하게 4로 올리면
    #     **정상 변경이 실패로 신고**됐다(위양성도 결함 · §A-6).
    assert view["daily_scopes"] == 6 * T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)


def test_quota_growth_flips_the_verdict():
    """★두 모집단이 갈린다 — 기준선 범위 vs 재측정 필요."""
    at_baseline = S.quota_view(S.QUOTA_BASELINE_TARGETS)
    grown = S.quota_view(S.QUOTA_BASELINE_TARGETS * S.QUOTA_REVIEW_MULTIPLE)
    assert at_baseline["state"] == "기준선범위"
    assert grown["state"] == "재측정필요"
    assert grown["daily_scopes"] > at_baseline["daily_scopes"]
    # ★경계 바로 아래는 넘어가지 않아야 한다(위양성 방지)
    just_under = S.quota_view(S.QUOTA_BASELINE_TARGETS * S.QUOTA_REVIEW_MULTIPLE - 1)
    assert just_under["state"] == "기준선범위"


def test_quota_unknown_targets_is_not_zero():
    """★★리뷰 M3 — `None`(파생 실패)과 `0`(대상 없음)은 **다른 상태**다.

    종전엔 `0` 이 `None` 이 아니라는 이유로 **산술 분기**로 들어가 `기준선범위`(= 정상)를
    냈다. 「아직 아무것도 안 셌다」가 **유효값 0** 을 입은 것이다.
    """
    none_view, zero_view = S.quota_view(None), S.quota_view(0)
    assert none_view["daily_scopes"] is None and zero_view["daily_scopes"] is None
    assert none_view["state"] == S.UNDERIVABLE
    assert zero_view["state"] == S.NEVER_SCANNED
    # ★두 모집단이 갈린다 — 접으면 여기서 죽는다
    assert none_view["state"] != zero_view["state"]
    assert zero_view["state"] != "기준선범위", "대상 0 을 '정상'으로 판정했다"


@pytest.mark.asyncio
async def test_quota_uses_current_targets_not_the_cumulative_history():
    """★★리뷰 H3 — 쿼터는 **현재 대상**에서 나와야 한다.

    `realtx_scan_state` 의 누적 시군구는 **수집 대상이 아니다**(저장소에
    `DELETE FROM realtx_*` 0건 — 사용자가 지역을 빼도 안 줄어든다). 그 위에 얹으면
    `재측정필요` 가 **한 번 켜지면 안 꺼진다**.
    """
    # 누적은 크게, 현재 대상은 작게 — **두 모집단이 갈린다**
    out = await S.build_layer2_status(
        _db(stored=4898, reobserved=0, corrections=0, sigungu_ever=600, targets=6), now=_NOW)
    assert out["scopes"]["sigungu_ever_scanned"] == 600
    assert out["quota"]["targets"] == 6, "쿼터가 누적 이력을 대상으로 오인했다"
    assert out["quota"]["state"] == "기준선범위", (
        "누적 600 때문에 '재측정필요'가 켜졌다 — 영원히 안 꺼지는 판정"
    )
    assert out["quota"]["daily_scopes"] == 6 * T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)


@pytest.mark.asyncio
async def test_quota_flips_when_actual_targets_grow():
    """★대조군 — **현재 대상**이 실제로 늘면 판정이 갈린다."""
    out = await S.build_layer2_status(
        _db(stored=4898, reobserved=10, corrections=0, sigungu_ever=6,
            targets=S.QUOTA_BASELINE_TARGETS * S.QUOTA_REVIEW_MULTIPLE), now=_NOW)
    assert out["quota"]["state"] == "재측정필요"


@pytest.mark.asyncio
async def test_target_derivation_failure_is_not_zero():
    """★파생 실패를 **0 으로 접지 않는다** — 0 은 관측이고 실패는 판정 불가다."""
    out = await S.build_layer2_status(
        _db(stored=4898, reobserved=0, corrections=0, targets=None), now=_NOW)
    assert out["quota"]["targets"] is None
    assert out["quota"]["state"] == S.UNDERIVABLE


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


# ★★종전 여기에 `test_the_route_is_wired_to_the_service` 가 있었다 — 라우트 함수 안의
#   **`ImportFrom` 이름 집합**만 봤다. 파이썬은 임포트를 쓰라고 강요하지 않으므로,
#   임포트를 남긴 채 본문을 `return {}` 로 비워도 **락 19건 + 전역 441건이 전부 초록**
#   이었다(2026-08-27 독립 리뷰 실측). 「부른다」를 잠그면 아무것도 안 잠긴다.
#   → **§6 의 실제 호출 락**(`TestClient`)이 그 자리를 대신한다.


# ══════════════════════════════════════════════════════════════
# 6. ★라우트 — **실제로 호출**해서 응답을 본다 (리뷰 H4)
# ══════════════════════════════════════════════════════════════
#
# ★★종전 `test_the_route_is_wired_to_the_service` 는 라우트 함수 안의 **`ImportFrom`
#   이름 집합**만 봤다. 그래서 임포트를 남긴 채 본문을 `return {}` 로 비워도
#   **락 19건이 전부 초록**이었다(독립 리뷰 실측).
#
#   이 PR 이 *"소비처가 실제로 존재하는지 — 이 PR 의 존재 이유"* 라고 선언한 **바로 그 자리**가
#   무잠금이었다. 메모리의 *"「부른다」를 잠그면 아무것도 안 잠긴다"* 와 동형이다.
#   → **행위를 태운다**: 실제 ASGI 앱에 GET 을 날리고 **응답 본문**을 단언한다.


def _route_app(*, super_admin: bool, payload: dict):
    """라우트 하나만 단 최소 FastAPI 앱."""
    from fastapi import FastAPI

    from apps.api.auth.jwt_handler import get_current_user
    from apps.api.routers import market_report as mod

    app = FastAPI()
    app.include_router(mod.router)

    class _U:
        user_id, tenant_id, email = "u-1", "t-1", "admin@4t8t.net"

    app.dependency_overrides[get_current_user] = lambda: _U()

    class _Sess:
        async def __aenter__(self): return object()
        async def __aexit__(self, *a): return False

    import apps.api.database.session as sess_mod
    from app.services.billing import billing_service
    from app.services.land_intelligence import realtx_layer2_status as svc

    async def _is_super(_db, _uid): return super_admin
    async def _build(_db): return payload

    return app, [
        (sess_mod, "AsyncSessionLocal", lambda: _Sess()),
        (billing_service, "is_super_admin", _is_super),
        (svc, "build_layer2_status", _build),
    ]


def _call_route(monkeypatch, *, super_admin=True, payload=None):
    from fastapi.testclient import TestClient

    payload = payload if payload is not None else {
        "stored_rows": 4898, "reobserved_rows": 0,
        "detection": {"state": "미시험", "meaning": "…"},
        "collection": {}, "quota": {}, "corrections": {}, "scopes": {},
        "as_of": _NOW.isoformat(),
    }
    app, patches = _route_app(super_admin=super_admin, payload=payload)
    for mod, name, val in patches:
        monkeypatch.setattr(mod, name, val)
    with TestClient(app) as c:
        return c.get("/api/v1/market/realtx-layer2/status")


def test_route_actually_returns_the_service_payload(monkeypatch):
    """★★`return {}` 로 본문을 비우면 **여기서 죽어야 한다**(리뷰 H4)."""
    r = _call_route(monkeypatch)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body, "라우트가 빈 응답을 돌려줬다 — 서비스를 안 부른 것이다"
    assert body["detection"]["state"] == "미시험", body
    assert body["stored_rows"] == 4898, body


def test_route_payload_is_not_invented(monkeypatch):
    """★두 모집단 — 서비스가 **다른 값**을 주면 응답도 달라져야 한다(상수 반환 방지)."""
    other = {"stored_rows": 17, "detection": {"state": "모순", "meaning": "…"},
             "collection": {}, "quota": {}, "corrections": {}, "scopes": {},
             "reobserved_rows": 0, "as_of": _NOW.isoformat()}
    a = _call_route(monkeypatch).json()
    b = _call_route(monkeypatch, payload=other).json()
    assert (a["stored_rows"], b["stored_rows"]) == (4898, 17)
    assert a["detection"]["state"] != b["detection"]["state"]


def test_route_is_admin_only(monkeypatch):
    """★★리뷰 M5 — 플랫폼 전역 규모를 **아무 인증 사용자**에게 주지 않는다."""
    r = _call_route(monkeypatch, super_admin=False)
    assert r.status_code == 403, (r.status_code, r.text)
    # ★양성 대조군 — 같은 호출이 관리자에겐 200 이다(게이트가 항상-거부가 아님)
    assert _call_route(monkeypatch, super_admin=True).status_code == 200


# ══════════════════════════════════════════════════════════════
# 7. ★소비처 0 필드 · 창↔경계 짝짓기 (독립 리뷰 M31·M32·M35·M36·M37·M21·M22)
# ══════════════════════════════════════════════════════════════
#
# ★독립 리뷰 실측: `scopes.total`·`scopes.baseline_done`·`as_of`·`quota.weekly_avg_per_day`
#   ·`quota.vs_baseline` 은 **어떤 단언도 읽지 않았다** — 값을 뒤바꾸거나 상수로 만들어도
#   전부 초록이었다. **응답에 싣는 것과 그것을 잠그는 것은 다른 일이다.**


@pytest.mark.asyncio
async def test_scope_counts_are_carried_and_not_transposed():
    """★`total` ↔ `baseline_done` **전도**를 잡는다 — 둘이 같으면 원리적으로 탐지 불가."""
    out = await S.build_layer2_status(
        # ★두 값을 **다르게** 준다. 같은 값이면 전도 변이가 통과한다
        _db(stored=1, reobserved=0, corrections=0, scopes=(36, 20)), now=_NOW)
    assert out["scopes"]["total"] == 36
    assert out["scopes"]["baseline_done"] == 20


@pytest.mark.asyncio
async def test_as_of_reflects_the_given_now():
    """★`as_of` 가 고정 문자열이 되어도 아무도 몰랐다(리뷰 M37)."""
    a = datetime(2021, 1, 2, 3, 4, tzinfo=UTC)
    b = datetime(2022, 5, 6, 7, 8, tzinfo=UTC)
    for when in (a, b):
        out = await S.build_layer2_status(_db(stored=1, reobserved=0, corrections=0), now=when)
        assert out["as_of"] == when.isoformat()


def test_weekly_average_is_actually_the_weekly_average():
    """★`weekly_avg_per_day` 산식 — 단언이 0건이었다(리뷰 M21)."""
    view = S.quota_view(6)
    expected = (view["daily_scopes"] * 7 + view["weekly_tail_scopes"]) / 7
    assert view["weekly_avg_per_day"] == round(expected, 1)
    # ★꼬리가 실제로 평균을 올린다 — 항이 사라지면 여기서 죽는다
    assert view["weekly_avg_per_day"] > view["daily_scopes"]
    assert view["vs_baseline"] == round(6 / S.QUOTA_BASELINE_TARGETS, 2)


def test_quota_baseline_matches_the_live_measurement():
    """★`QUOTA_BASELINE_TARGETS` 가 조용히 바뀌면 **경보 발동점이 옮겨간다**(리뷰 M22).

    이 값은 임의 상수가 아니라 **라이브 실측**이다 — 2026-08-26T19:10Z 에
    `user_project_store` 3행에서 파생된 고유 시군구가 **6**이었고 그때 36 스코프/일이었다.
    """
    assert S.QUOTA_BASELINE_TARGETS == 6
    assert (S.QUOTA_BASELINE_TARGETS * T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)) == 36


@pytest.mark.asyncio
async def test_each_window_is_judged_by_its_own_threshold():
    """★★창↔경계 **짝짓기**가 이 모듈의 핵심 계약인데 무잠금이었다(리뷰 M35·M36).

    최근(매일)은 2일, 꼬리(주1회)는 8일로 판정해야 한다. 바꿔 끼우면
    **일일 크론이 7일 멈춰도 「정상」** 이거나, **정상 주간 실행이 「낡음」** 이 된다.
    """
    # 5일 전 — 최근 창엔 **낡음**(>2), 꼬리엔 **정상**(<8). 경계를 바꿔 끼우면 뒤집힌다.
    five = _NOW - timedelta(days=5)
    out = await S.build_layer2_status(
        _db(stored=1, reobserved=0, corrections=0,
            last_recent=five, last_tail=five), now=_NOW)
    assert out["collection"]["recent"]["stale"] is True, "일일 창을 꼬리 경계로 쟀다"
    assert out["collection"]["tail"]["stale"] is False, "꼬리 창을 일일 경계로 쟀다"
    # ★두 모집단이 **같은 입력에서** 갈린다 — 짝짓기가 깨지면 둘이 같아진다
    assert out["collection"]["recent"]["stale"] != out["collection"]["tail"]["stale"]
