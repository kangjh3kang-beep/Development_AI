"""`persist_scope` 를 **실제로 태우는** 락 — 2026-08-26 독립 적대 리뷰가 낸 C1 봉합.

## 왜 이 파일이 생겼나

`#855` 는 *"멱등키 충돌로 라이브 거래의 4%(최악 29%)가 덮어써지던 것을 고쳤다"* 고 선언하고
`assign_ordinals` **내부**만 태우는 락 5종을 붙였다. 그런데 **호출부는 잠기지 않았다** —
독립 리뷰가 `persist_scope` 안의

    keys = assign_ordinals(records, lawd_cd, deal_ym)
      → keys = [trade_key(r, lawd_cd, deal_ym, 0) for r in records]   # 봉합 이전 상태

로 되돌렸는데 **24개 테스트가 전부 초록**이었다(저자 재현 확인).
저장소 메모리의 **「'부른다'를 잠그면 아무것도 안 잠긴다 — 행위를 태워라」**(2026-08-26)를
**하루 만에 같은 형태로 재발**시킨 것이다.

## 이 파일이 태우는 것

`_FakeRealtxDb` 는 세 테이블을 **인메모리로 모델링**하고 `persist_scope` 의 SQL 을
실제로 해석한다 — upsert 의 충돌 병합, `previous` 조회, 정정 INSERT, scan_state 까지.

## ★이 락이 **못 보는** 것

- **SQL 이 유효한 Postgres 인지**는 보지 않는다(가짜 해석기다). 타입 캐스팅·트랜잭션
  원자성·인덱스는 라이브에서만 드러난다.
- `_ensure_schema` 의 DDL 은 태우지 않는다(no-op 으로 둔다).
"""

from __future__ import annotations

import re

import pytest

from app.services.land_intelligence import realtx_store as rs

_BASE = {
    "prop_type": "land", "dong": "외삼미동", "jibun": "1**", "area_m2": 1718.0,
    "floor": 0, "price_10k_won": 105737, "deal_date": "2026년 7월 13일",
    "building_name": "", "cancel_type": " ", "cancel_date": "",
    "registered_date": "", "dealing_type": "중개거래",
    "buyer_type": "개인", "seller_type": "개인",
}
LAWD, YM, PT = "41370", "202607", "land"


class _Res:
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return list(self._rows)
    def first(self): return self._rows[0] if self._rows else None


class _FakeRealtxDb:
    """`realtx_trades` / `realtx_corrections` / `realtx_scan_state` 인메모리 모델."""

    def __init__(self) -> None:
        self.trades: dict[str, dict] = {}
        self.corrections: list[dict] = []
        self.scan_state: dict[str, bool] = {}
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if sql.startswith(("CREATE", "ALTER")):
            return _Res([])
        if sql.startswith("SELECT baseline_done"):
            k = params["k"]
            return _Res([(True,)] if self.scan_state.get(k) else [])
        if sql.startswith("SELECT trade_key"):
            cols = re.search(r"SELECT trade_key, (.+?) FROM", sql).group(1).split(", ")
            # ★WHERE 절을 **SQL 에서 파생**한다 — 하드코딩하면 스텁이 검증 대상 층을
            #   우회해, 조회 스코프를 지우는 변이가 조용히 생존한다(실제로 생존했다).
            where = sql.split("WHERE", 1)[1] if "WHERE" in sql else ""
            filters = [(c, b) for c, b in
                       (("lawd_cd", "l"), ("deal_ym", "y"), ("prop_type", "p"))
                       if f"{c} = :{b}" in where]
            assert filters, "★WHERE 절을 하나도 못 읽었다 — 파서 의심(공허한 참 방지)"
            out = []
            for key, row in self.trades.items():
                if all(row[c] == params[b] for c, b in filters):
                    out.append((key, *[row.get(c) for c in cols]))
            return _Res(out)
        if sql.startswith("INSERT INTO realtx_trades"):
            key = params["trade_key"]
            if key in self.trades:                       # ON CONFLICT DO UPDATE — 가변만
                for f in rs._MUTABLE_FIELDS:
                    self.trades[key][f] = params[f]
            else:
                self.trades[key] = dict(params)
            return _Res([])
        if sql.startswith("INSERT INTO realtx_corrections"):
            self.corrections.append(dict(params)); return _Res([])
        if sql.startswith("INSERT INTO realtx_scan_state"):
            self.scan_state[params["k"]] = True; return _Res([])
        raise AssertionError(f"모델이 모르는 SQL: {sql[:90]}")

    async def commit(self): self.commits += 1


async def _run(db, records):
    return await rs.persist_scope(db, lawd_cd=LAWD, deal_ym=YM, prop_type=PT, records=records)


# ══════════════════════════════════════════════════════════════
# 1. ★쌍둥이가 **행으로 보존**되는가 — 봉합을 되돌리면 여기서 죽어야 한다
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_three_identical_twins_become_three_rows():
    """라이브 실측 모양: 41370/202607 land 는 114행 중 33건이 쌍둥이였다."""
    db = _FakeRealtxDb()
    res = await _run(db, [dict(_BASE) for _ in range(3)])
    assert res["submitted"] == 3
    assert len(db.trades) == 3, f"쌍둥이가 덮어써졌다: {len(db.trades)}행"


@pytest.mark.asyncio
async def test_a_scope_with_many_twins_loses_no_row():
    db = _FakeRealtxDb()
    records = [dict(_BASE) for _ in range(33)] + [{**_BASE, "price_10k_won": 999}]
    await _run(db, records)
    assert len(db.trades) == len(records) == 34


@pytest.mark.asyncio
async def test_reprocessing_the_same_response_adds_no_row():
    """멱등 — 같은 응답을 두 번 처리해도 행 수가 늘지 않는다."""
    db = _FakeRealtxDb()
    records = [dict(_BASE), dict(_BASE), {**_BASE, "floor": 1}]
    await _run(db, records)
    n1 = len(db.trades)
    await _run(db, records)
    assert len(db.trades) == n1 == 3


# ══════════════════════════════════════════════════════════════
# 2. baseline 억제 — 두 모집단이 **다른 값**을 내야 한다
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_first_scan_records_no_correction_second_scan_does():
    db = _FakeRealtxDb()
    first = await _run(db, [dict(_BASE)])
    assert first["baseline"] is True
    assert first["corrections"] == [] and db.corrections == []

    second = await _run(db, [{**_BASE, "cancel_type": "O", "cancel_date": "26.08.01"}])
    assert second["baseline"] is False
    kinds = [c["kind"] for c in second["corrections"]]
    assert "cancelled" in kinds, second["corrections"]
    assert len(db.corrections) >= 1, "정정 원장에 한 행도 안 쓰였다"


@pytest.mark.asyncio
async def test_no_change_writes_no_correction_row():
    """대조군 — 변화가 없으면 정정이 **안** 나와야 한다(항상 쓰는 코드는 만점이 된다)."""
    db = _FakeRealtxDb()
    await _run(db, [dict(_BASE)])
    await _run(db, [dict(_BASE)])
    assert db.corrections == []


# ══════════════════════════════════════════════════════════════
# 3. ★순번이 **응답 순서에 흔들리지 않는가** (C2)
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_correction_sticks_to_the_same_row_when_source_reorders_twins():
    """★종전 결함: 원천이 쌍둥이를 다른 순서로 주면 정정이 **다른 거래에 귀속**됐다."""
    plain, cancelled = dict(_BASE), {**_BASE, "cancel_type": "O"}

    db = _FakeRealtxDb()
    await _run(db, [dict(plain), dict(plain)])           # baseline: 쌍둥이 2건
    await _run(db, [dict(plain), dict(cancelled)])       # 하나가 해제
    a = {k: v["cancel_type"] for k, v in db.trades.items()}

    db2 = _FakeRealtxDb()
    await _run(db2, [dict(plain), dict(plain)])
    await _run(db2, [dict(cancelled), dict(plain)])      # ★순서만 뒤집는다
    b = {k: v["cancel_type"] for k, v in db2.trades.items()}

    assert a == b, f"응답 순서가 정정 귀속을 바꿨다\n순서1={a}\n순서2={b}"


@pytest.mark.asyncio
async def test_corrections_carry_twin_group_size_so_consumers_know_attribution_limits():
    """쌍둥이 집합이 1보다 크면 **개별 귀속은 신뢰 불가**하다 — 그 사실을 실어 보낸다."""
    db = _FakeRealtxDb()
    await _run(db, [dict(_BASE), dict(_BASE)])
    await _run(db, [dict(_BASE), {**_BASE, "cancel_type": "O"}])
    assert db.corrections, "정정이 없다 — 이 단언이 공허하다"
    assert all(c["g"] == 2 for c in db.corrections), db.corrections

    db2 = _FakeRealtxDb()                                 # 대조군: 쌍둥이 아님 → 1
    await _run(db2, [dict(_BASE)])
    await _run(db2, [{**_BASE, "cancel_type": "O"}])
    assert all(c["g"] == 1 for c in db2.corrections), db2.corrections


# ══════════════════════════════════════════════════════════════
# 4. ★부채 — 초록 안에 보이게
# ══════════════════════════════════════════════════════════════

@pytest.mark.xfail(reason="★소비처 0 — realtx_trades·realtx_corrections·realtx_scan_state 를 "
                          "읽는 코드가 라우터·서비스·프론트 어디에도 없다. 2층은 3층의 기반이지만, "
                          "'해제됐다고 말할 수 있게 한다'는 약속은 아직 이행되지 않았다.",
                   strict=True)
def test_a_reader_exists_for_the_new_tables():
    """★이 프로브는 **repo root 에서** 돌아야 한다 — CI 의 cwd 는 `apps/api` 라

    `git grep -- apps/web` 이 조용히 0건이 된다(같은 리뷰의 M3 지적). 그래서
    **양성 대조군을 같은 실행에** 넣어 조회기 생존을 먼저 증명한다.
    """
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]          # …/propai-platform
    def grep(pat, *paths):
        return subprocess.run(["git", "grep", "-l", pat, "--", *paths],
                              cwd=root, capture_output=True, text=True).stdout.strip()

    assert grep("persist_scope", "apps/api"), "★양성 대조군 0건 — 조회기가 죽었다(cwd 확인)"
    hits = grep("realtx_trades", "apps/api/app/routers", "apps/api/routers", "apps/web")
    assert hits, "새 테이블을 읽는 표면이 없다"


# ══════════════════════════════════════════════════════════════
# 5. 변이가 생존한 두 자리 — 픽스처가 **모집단을 안 갈랐기 때문**이었다
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_baseline_flag_suppresses_even_when_rows_already_exist():
    """★`before is None` 만으로는 부족하다 — 행은 있는데 scan_state 가 없는 상태가 있다.

    (배포 중단·롤백·상태행 소실). 그때 `baseline_done` 가드가 없으면 **전건이 정정으로**
    보고된다. 첫 스캔만 태우는 픽스처로는 이 자리가 안 잠긴다(변이 M1 이 생존했다).
    """
    db = _FakeRealtxDb()
    await _run(db, [dict(_BASE)])                 # 행을 만들고
    db.scan_state.clear()                         # ★상태행만 잃는다
    res = await _run(db, [{**_BASE, "cancel_type": "O"}])
    assert res["baseline"] is True
    assert res["corrections"] == [], "상태행이 없다는 이유로 전건이 정정으로 보고됐다"
    assert db.corrections == []


@pytest.mark.asyncio
async def test_previous_snapshot_is_scoped_by_prop_type():
    """★같은 시군구·월에 유형이 둘이면, 스코프를 안 나눈 조회는 **남의 행을 자기 것으로** 본다.

    한 유형만 쓰는 픽스처로는 안 잠긴다(변이 M7 이 생존했다).
    """
    land = dict(_BASE)
    apt = {**_BASE, "prop_type": "apt", "building_name": "오산센트럴푸르지오", "floor": 16}

    db = _FakeRealtxDb()
    await rs.persist_scope(db, lawd_cd=LAWD, deal_ym=YM, prop_type="land", records=[land])
    await rs.persist_scope(db, lawd_cd=LAWD, deal_ym=YM, prop_type="apt", records=[apt])
    assert len(db.trades) == 2

    # apt 스코프를 다시 처리 — land 행은 이 스코프의 previous 에 들어오면 안 된다.
    res = await rs.persist_scope(
        db, lawd_cd=LAWD, deal_ym=YM, prop_type="apt",
        records=[{**apt, "registered_date": "26.08.20"}],
    )
    fields = {c["field"] for c in res["corrections"]}
    assert fields == {"registered_date"}, res["corrections"]
    # ★대조군: land 행은 건드려지지 않았다(스코프 분리 증명)
    land_rows = [v for v in db.trades.values() if v["prop_type"] == "land"]
    assert len(land_rows) == 1 and land_rows[0]["registered_date"] == ""


@pytest.mark.asyncio
async def test_correction_still_detected_when_record_carries_its_own_prop_type():
    """★저장은 레코드 값, 조회는 스코프 인자 — 둘이 다르면 정정이 **영구 0건**이 된다.

    오늘 `_parse_trade_items` 는 항상 스코프와 같은 값을 넣어 도달 불가하지만,
    `upsert_params` 가 `record.get("prop_type") or prop_type` 이라는 **폴백을 굳이 두고 있어**
    비대칭이 잠복한다. 조회를 키 기반으로 넓히면 그 잠복이 사라진다.
    """
    rec = {**_BASE, "prop_type": "토지"}          # ★스코프 인자('land')와 다른 값
    db = _FakeRealtxDb()
    await rs.persist_scope(db, lawd_cd=LAWD, deal_ym=YM, prop_type="land", records=[rec])
    res = await rs.persist_scope(
        db, lawd_cd=LAWD, deal_ym=YM, prop_type="land",
        records=[{**rec, "cancel_type": "O"}],
    )
    assert [c["kind"] for c in res["corrections"]] == ["cancelled"], res["corrections"]
