"""실거래 2층 락 — 모집단 파생 · 멱등키 · 정정 탐지 · baseline 억제.

## ★이 락이 **못 보는** 실패 모드 (같이 적는다 — 안 적으면 다음 사람이 전수라고 읽는다)

1. **SQL 이 유효한 Postgres 인지 검증하지 않는다.** `_RecordingDb` 는 SQL 을 실행하지 않고
   기록만 한다. 컬럼 오타·타입 불일치는 **라이브에서만** 드러난다.
   → 그래서 DDL·UPSERT 는 **문자열 계약**으로 따로 잠근다(아래 `test_ddl_*`).
2. **가격 정정을 탐지하지 못한다.** 원천이 거래금액을 정정하면 멱등키가 바뀌어 **신규로
   오분류**된다. 원천이 그러는지 **미측정** → `xfail` 로 초록 안에 남긴다.
3. **쿼터 실측이 없다.** MOLIT 일일 한도의 실제 수치는 재지 않았다 — 크론 시각은
   G2B 와 겹치지 않게만 골랐다.
"""

from __future__ import annotations

import pytest

from app.services.land_intelligence import realtx_store as rs

# ── 두 모집단을 가르는 픽스처 ────────────────────────────────────────────
# ★A 는 필지가 있고 B 는 없다. 값이 같으면 배선을 끊어도 결과가 같아 아무것도 안 잠긴다.
_PNU_POHANG = "4711125021" + "0" * 9   # 47111 = 포항 남구
_PNU_ICHEON = "4137025300" + "0" * 9   # 41370 = 이천시

STORE_WITH_PARCELS = {
    "landSchedule": {"byProject": {"p1": [{"pnu": _PNU_POHANG}, {"pnu": _PNU_ICHEON}]}},
    # ★분석 캐시에 실린 **다른 지역** PNU — 모집단에 들어오면 안 된다(쿼터 낭비).
    "contextStore": {"snapshots": {"s1": {"siteAnalysis": {"pnu": "1168010100" + "0" * 9}}}},
}
STORE_WITHOUT_PARCELS = {"landSchedule": {"byProject": {}}, "contextStore": {}}


# ══════════════════════════════════════════════════════════════════
# 1. 모집단은 **파생형** — 손으로 쓴 목록이면 실패한다
# ══════════════════════════════════════════════════════════════════

def test_targets_are_derived_from_the_store_not_a_hardcoded_list():
    """★이 저장소의 하드코딩 목록으로 되돌리면 이 단언이 깨져야 한다.

    `etl_scheduled.py` 의 8개(서울 5구+경기 3)는 포항·이천을 **하나도 포함하지 않는다**.
    따라서 파생을 목록으로 바꾸면 아래 `==` 가 즉시 실패한다.
    """
    got = rs.lawd_codes_from_store_blob(STORE_WITH_PARCELS)
    assert got == {"47111", "41370"}, got

    ETL_HARDCODED = {"11680", "11650", "11710", "11740", "11500", "41135", "41131", "41117"}
    assert not (got & ETL_HARDCODED), (
        "픽스처가 하드코딩 목록과 겹치면 '파생형'과 '목록형'을 구별하지 못한다"
    )


def test_only_land_schedule_counts_not_the_whole_blob():
    """분석 캐시의 PNU(11680)는 모집단에 들어오지 않는다 — 안 그러면 쿼터를 헛쓴다."""
    assert "11680" not in rs.lawd_codes_from_store_blob(STORE_WITH_PARCELS)
    # 대조군: 같은 PNU 를 landSchedule 로 옮기면 **들어와야** 한다(수집기 생존 증명)
    moved = {"landSchedule": {"byProject": {"p": [{"pnu": "1168010100" + "0" * 9}]}}}
    assert rs.lawd_codes_from_store_blob(moved) == {"11680"}


def test_second_population_yields_nothing():
    """★두 모집단이 **다른 값**을 내야 배선 변이가 죽는다."""
    assert rs.lawd_codes_from_store_blob(STORE_WITHOUT_PARCELS) == set()


@pytest.mark.asyncio
async def test_empty_derivation_raises_loudly_never_silently_zero():
    """0건은 **스킵이 아니라 실패**다 — 스토어 형상이 바뀌면 수집이 죽은 채 초록이 된다."""
    class _Db:
        async def execute(self, *_a, **_k):
            class _R:
                @staticmethod
                def fetchall(): return [(STORE_WITHOUT_PARCELS,)]
            return _R()

    with pytest.raises(rs.RealtxTargetsEmpty):
        await rs.derive_scan_targets(_Db())


# ══════════════════════════════════════════════════════════════════
# 2. 멱등키 — 가변 필드가 키에 들어가면 정정이 신규가 된다
# ══════════════════════════════════════════════════════════════════

_BASE = {
    "prop_type": "land", "dong": "대보리", "jibun": "1*", "area_m2": 330.0,
    "floor": 0, "price_10k_won": 12000, "deal_date": "2026년 7월 3일",
    "building_name": "", "cancel_type": " ", "cancel_date": "",
    "registered_date": "", "dealing_type": "중개거래",
    "buyer_type": "개인", "seller_type": "개인",
}


def test_mutable_fields_are_disjoint_from_key_fields():
    assert not (set(rs._KEY_FIELDS) & set(rs._MUTABLE_FIELDS))


def test_key_is_stable_when_only_mutable_fields_change():
    """해제·등기일자가 붙어도 **같은 거래**로 식별돼야 정정을 탐지할 수 있다."""
    before = rs.trade_key(_BASE, "47111", "202607")
    after = rs.trade_key({**_BASE, "cancel_type": "O", "registered_date": "26.08.01"},
                         "47111", "202607")
    assert before == after


def test_key_changes_when_an_immutable_field_changes():
    """대조군 — 키가 **아무것에도 반응하지 않으면** 위 단언은 공허한 참이다."""
    other = rs.trade_key({**_BASE, "jibun": "2*"}, "47111", "202607")
    assert other != rs.trade_key(_BASE, "47111", "202607")


def test_key_is_scoped_by_lawd_and_month():
    k = rs.trade_key(_BASE, "47111", "202607")
    assert k != rs.trade_key(_BASE, "41370", "202607")
    assert k != rs.trade_key(_BASE, "47111", "202608")


# ══════════════════════════════════════════════════════════════════
# 3. 정정 탐지
# ══════════════════════════════════════════════════════════════════

def test_space_cancel_type_is_not_a_cancellation():
    """★정상 건의 `cancel_type` 은 `' '`(스페이스)다 — strip 없이 보면 **전건이 해제**가 된다."""
    # ★해당 필드만 갈라 본다 — 나머지를 함께 바꾸면 무엇이 단언을 통과시켰는지 알 수 없다.
    assert rs.diff_mutable({**_BASE, "cancel_type": ""}, {**_BASE, "cancel_type": " "}) == []
    # 대조군: 진짜 해제('O')는 **잡혀야** 한다 — 없으면 "아무것도 안 잡는 diff"가 만점이다.
    assert rs.diff_mutable({**_BASE, "cancel_type": ""}, {**_BASE, "cancel_type": "O"})


def test_cancellation_is_detected():
    out = rs.diff_mutable(_BASE, {**_BASE, "cancel_type": "O", "cancel_date": "26.08.01"})
    kinds = {c["kind"] for c in out}
    assert "cancelled" in kinds, out


def test_registry_date_added_is_its_own_kind():
    """등기일자는 원천에서 **30%만 기재**된다 — 나중에 붙는 것이 정상이고, 해제와 다른 사건이다."""
    out = rs.diff_mutable(_BASE, {**_BASE, "registered_date": "26.08.20"})
    assert [c["kind"] for c in out] == ["registry_added"], out


def test_no_change_yields_no_correction():
    assert rs.diff_mutable(_BASE, dict(_BASE)) == []


@pytest.mark.xfail(reason="★미측정 부채 — 원천이 거래금액을 정정하면 멱등키가 바뀌어 "
                          "정정이 아니라 **신규 거래**로 오분류된다. MOLIT 이 가격을 "
                          "정정하는지 재 보지 않았다.", strict=True)
def test_price_correction_is_detected_as_a_correction():
    corrected = {**_BASE, "price_10k_won": 13000}
    assert rs.trade_key(_BASE, "47111", "202607") == rs.trade_key(corrected, "47111", "202607")


# ══════════════════════════════════════════════════════════════════
# 4. SQL 계약 — 스텁이 SQL 을 실행하지 않으므로 **문자열로** 잠근다
# ══════════════════════════════════════════════════════════════════

def test_ddl_is_idempotent_and_adds_no_alembic_head():
    for ddl in (rs._TRADES_DDL, rs._CORRECTIONS_DDL, rs._SCAN_STATE_DDL):
        assert "CREATE TABLE IF NOT EXISTS" in ddl
    for index_sql in rs._INDEXES:
        assert "CREATE INDEX IF NOT EXISTS" in index_sql


def test_upsert_never_overwrites_immutable_fields():
    """`ON CONFLICT DO UPDATE` 가 갱신하는 것은 **가변 필드뿐**이어야 한다.

    불변 필드를 갱신하면 그건 이미 **다른 거래**이므로 같은 키일 수 없다(모순).
    """
    update_clause = rs._UPSERT_SQL.split("DO UPDATE SET", 1)[1]
    for field in rs._KEY_FIELDS:
        assert f"{field} = EXCLUDED" not in update_clause, field
    for field in rs._MUTABLE_FIELDS:
        assert f"{field} = EXCLUDED.{field}" in update_clause, field


def test_schema_ready_flag_is_set_only_after_commit():
    """유령 ready 방지 — 커밋 **후에만** 플래그를 세운다(`design_run_store` 선례)."""
    import inspect
    src = inspect.getsource(rs._ensure_schema)
    body = src.split("global _SCHEMA_READY", 1)[1]
    commit_at = body.index("await db.commit()")
    ready_at = body.index("_SCHEMA_READY = True", commit_at)
    assert commit_at < ready_at
