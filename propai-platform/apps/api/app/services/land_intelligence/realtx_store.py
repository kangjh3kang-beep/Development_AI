"""실거래 **2층** — MOLIT 신고내역을 영속하고 **정정(해제·등기일자 추가)을 탐지**한다.

## 1층과 무엇이 다른가

`#851`(1층 · `realtx_report_service`)은 **요청 시점에 MOLIT 을 부르고 버린다.** 그래서
*"지난주엔 정상이었는데 지금 보니 해제됐다"* 를 **말할 수 없다** — 비교할 과거가 없기 때문이다.
이 모듈은 그 과거를 만든다.

## ★모집단을 **손으로 쓰지 않는다** (이 파일의 가장 중요한 설계)

`apps/worker/tasks/etl_scheduled.py` 는 시군구 **8개를 하드코딩**해 두고 매일 MOLIT 을 부른다.
그 목록이 실제 사용자를 얼마나 덮는지 재 보았다:

    라이브 실측 2026-08-26T07:5xZ (활성 컨테이너 propai-api-8001)
      동기화된 필지 PNU **394** 개(고유 129) → 고유 시군구 **6**
        11590 · 41370 · 41465 · 47111 · 11710 · 11680
      하드코딩 8개가 덮는 PNU = **4 / 394 = 1.0%**

즉 **99% 가 안 담긴다.** 그래서 여기서는 수집 대상을 `user_project_store` 에 동기화된
필지에서 **파생**한다. 새 프로젝트·새 지역이 자동으로 감시망에 들어오고, 아무도 안 쓰는
지역은 태우지 않는다(쿼터가 곧 제약이다 — 아래).

★**파생이 0건이면 조용히 넘어가지 않고 죽는다**(`RealtxTargetsEmptyError`). 프론트 스토어 형상이
  바뀌면 파생이 소리 없이 0건이 될 수 있는데, 그때 *"수집할 것이 없었다"* 로 읽히면
  **수집이 죽은 채 초록**이 된다.

## ★쿼터 — MOLIT 키는 **G2B 와 같은 키**다

    라이브 실측 2026-08-26 (해석된 settings 값 비교 · env 아님)
      MOLIT_API_KEY == G2B_SERVICE_KEY == sha12 `cd5d6fc742c4`
      G2B 는 2시간마다 실제로 태운다 — `cron:g2b_sync_bids ● {'fetched': 300}`

그래서 이 모듈은 **하루 1회**, 파생된 시군구에 대해서만 돈다. `429/403` 은 **재시도하지 않고**
보류값 계약(`#832`)으로 사유를 싣는다 — 조회 실패를 **"거래 0건"으로 기록하면 거짓 사실**이
만들어진다.

## ★정정 탐지 — `presale_monitor_service` 선례를 그대로 쓴다

`presale_seen(interest_id, pblanc_key)` upsert + `last_status` diff + **`baseline_done` 억제**.
최초 수집에서 억제하지 않으면 **첫 실행에 전건이 "정정"으로 보고**된다.

## ★멱등키 — MOLIT 응답에는 고유 ID 가 없다

불변 조합키로 만든다. **가변 필드는 키에서 제외**해야 정정이 "새 거래"로 오분류되지 않는다.

    불변(키)  prop_type · lawd_cd · deal_ym · dong · jibun · area_m2 · floor
              · price_10k_won · deal_date · building_name
    가변(정정) cancel_type · cancel_date · registered_date · dealing_type
              · buyer_type · seller_type

★**미측정 부채**: 원천이 **거래금액을 정정**하면 키가 달라져 **신규로 오분류**된다.
  MOLIT 이 가격을 정정하는지는 재 보지 않았다 — `tests/test_realtx_store.py` 에 `it.todo` 상당의
  `xfail` 로 초록 안에 남겨 둔다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

#: PNU 19자리 — 앞 5자리가 MOLIT `LAWD_CD`(시군구)
_PNU_RE = re.compile(r"^\d{19}$")

#: 멱등키를 이루는 **불변** 필드(순서 고정 — 순서가 바뀌면 키가 바뀐다)
_KEY_FIELDS: tuple[str, ...] = (
    "prop_type", "dong", "jibun", "area_m2", "floor",
    "price_10k_won", "deal_date", "building_name",
)

#: **가변** 필드 = 정정 탐지 대상. 여기 있는 것은 절대 `_KEY_FIELDS` 에 넣지 않는다.
_MUTABLE_FIELDS: tuple[str, ...] = (
    "cancel_type", "cancel_date", "registered_date",
    "dealing_type", "buyer_type", "seller_type",
)

assert not (set(_KEY_FIELDS) & set(_MUTABLE_FIELDS)), (
    "가변 필드가 멱등키에 들어가면 정정이 '신규 거래'로 오분류된다"
)


class RealtxTargetsEmptyError(RuntimeError):
    """수집 대상 파생이 **0건** — 조용한 0건 금지(스토어 형상 변경 등)."""


# ══════════════════════════════════════════════════════════════════════
# 1. 모집단 파생 — 손으로 쓴 목록을 쓰지 않는다
# ══════════════════════════════════════════════════════════════════════

def _iter_pnus(node: Any) -> Iterable[str]:
    """중첩 구조 어디에 있든 `pnu` 형식 문자열을 전부 훑는다(전수·파생형)."""
    if isinstance(node, dict):
        for value in node.values():
            if isinstance(value, str) and _PNU_RE.match(value.strip()):
                yield value.strip()
            else:
                yield from _iter_pnus(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_pnus(value)


def lawd_codes_from_store_blob(blob: Any) -> set[str]:
    """`user_project_store.data` 한 벌 → 그 사용자가 실제로 가진 **시군구 코드 집합**.

    ★`landSchedule` **만** 본다. `data` 전체를 훑으면 분석 캐시에 실린 남의 지역 PNU 까지
      섞여 들어와(라이브 실측: 전체 1,602 vs landSchedule 394) **쓰지도 않는 지역의 쿼터를
      태운다.** 모집단은 *"사용자가 자기 사업지로 등록한 필지"* 다.
    """
    data = blob if isinstance(blob, dict) else json.loads(blob or "{}")
    land_schedule = data.get("landSchedule")
    if not isinstance(land_schedule, dict):
        return set()
    return {pnu[:5] for pnu in _iter_pnus(land_schedule)}


async def derive_scan_targets(db: Any) -> set[str]:
    """동기화된 전 사용자에서 시군구 코드를 **파생**한다.

    Raises:
        RealtxTargetsEmpty: 파생이 0건일 때. **조용히 넘어가지 않는다.**
    """
    from sqlalchemy import text

    rows = (await db.execute(text("SELECT data FROM user_project_store"))).fetchall()
    targets: set[str] = set()
    for (blob,) in rows:
        targets |= lawd_codes_from_store_blob(blob)

    if not targets:
        raise RealtxTargetsEmptyError(
            f"수집 대상 시군구 0건 — user_project_store {len(rows)}행에서 landSchedule PNU 를 "
            "하나도 못 찾았다. 스토어 형상 변경을 의심하라(조용한 0건 금지)."
        )
    logger.info("실거래 수집 대상 파생: 사용자 %d명 → 시군구 %d개", len(rows), len(targets))
    return targets


# ══════════════════════════════════════════════════════════════════════
# 2. 멱등키
# ══════════════════════════════════════════════════════════════════════

def trade_key(record: dict[str, Any], lawd_cd: str, deal_ym: str, ordinal: int = 0) -> str:
    """거래 1건의 **결정적** 식별자. 같은 입력 → 같은 키(uuid/now/random 0).

    `ordinal` 은 **불변 필드가 완전히 같은 쌍둥이**를 가르는 순번이다(아래 참조).
    """
    parts = [lawd_cd, deal_ym] + [
        ("" if record.get(f) is None else str(record.get(f)).strip())
        for f in _KEY_FIELDS
    ] + [str(ordinal)]
    return "rtx_" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def assign_ordinals(records: list[dict[str, Any]], lawd_cd: str, deal_ym: str) -> list[str]:
    """스코프 안에서 **키가 겹치는 쌍둥이**에 순번을 붙여 유일한 키 목록을 만든다.

    ## ★왜 필요한가 — 라이브 실측(2026-08-26, 활성 컨테이너)

    MOLIT 은 거래 고유 ID 를 주지 않는다. 그런데 **토지 지번은 100% 마스킹**(`1**`)이라
    서로 다른 필지가 같은 문자열이 되고, 면적·금액·일자까지 같으면 **구별이 사라진다.**

        스코프                 행    고유키   소실
        41370/202607 land     114     81    **33 (29%)**
        41370/202607 apt      433    430      3
        47111/202606 land      57     56      1
        ─────────────────────────────────────────
        4스코프 합계         1,284  1,232   **52 (4.0%)**

    순번 없이 upsert 하면 **평균 4%·최악 29% 가 조용히 덮어써진다.** 아파트도 같은 단지·
    같은 층·같은 면적·같은 금액·같은 날이면 **다른 호실**인데 구별이 안 된다.

    ## ★이 처방의 한계 (같이 적는다)

    순번은 **응답 순서**에 결속한다. 원천이 쌍둥이의 순서를 바꾸면 두 행의 **정정 귀속이
    서로 뒤바뀔 수 있다**(불변 필드는 같으므로 데이터 자체는 안 틀리지만, "이 거래가
    해제됐다"가 쌍둥이 중 다른 쪽에 붙을 수 있다). 원천이 순서를 보장하는지는 **미측정**이다.
    그래도 **29% 를 버리는 것보다는 낫다** — 버리면 그 거래는 아예 없던 일이 된다.
    """
    # ★★2026-08-26 독립 리뷰 적발 — 종전엔 순번이 **응답 순서**에 결속했다.
    #   그러면 원천이 쌍둥이를 다른 순서로 주는 날 **정정이 다른 거래에 귀속된다.**
    #   내 종전 주석은 *"불변 필드가 같으니 데이터 자체는 안 틀린다"* 고 했는데 **거짓**이다 —
    #   이 층의 유일한 산출물이 정정 원장이고, 귀속이 틀리면 **원장이 거짓**이다.
    #
    #   → 순번을 **가변 필드 지문**으로 정렬해 결정적으로 만든다. 같은 쌍둥이 집합이면
    #     응답 순서와 무관하게 같은 순번을 받는다.
    #   ★가변 필드까지 완전히 같은 쌍둥이는 **원리적으로 구별 불가**하다. 그때 개별 귀속은
    #     의미가 없고 *"쌍둥이 3건 중 1건이 해제됐다"* 는 집계만 참이다 —
    #     그래서 정정 행에 `twin_group_size` 를 실어 **소비처가 개별 귀속을 신뢰하지 않게** 한다.
    groups: dict[str, list[int]] = {}
    for i, record in enumerate(records):
        groups.setdefault(trade_key(record, lawd_cd, deal_ym, 0), []).append(i)

    out: list[str] = [""] * len(records)
    for base, idxs in groups.items():
        if len(idxs) == 1:
            out[idxs[0]] = base
            continue
        # 가변 필드 지문으로 정렬 → 응답 순서가 바뀌어도 같은 순번.
        ordered = sorted(idxs, key=lambda i: _mutable_fingerprint(records[i]))
        for ordinal, i in enumerate(ordered):
            out[i] = base if ordinal == 0 else trade_key(records[i], lawd_cd, deal_ym, ordinal)
    return out


def _mutable_fingerprint(record: dict[str, Any]) -> tuple[str, ...]:
    """가변 필드만으로 만든 정렬 열쇠 — 쌍둥이 순번을 **응답 순서에서 떼어낸다**."""
    return tuple(
        ("" if record.get(f) is None else str(record.get(f)).strip())
        for f in _MUTABLE_FIELDS
    )


def twin_group_sizes(records: list[dict[str, Any]], lawd_cd: str, deal_ym: str) -> list[int]:
    """각 레코드가 속한 **쌍둥이 집합의 크기**. 1 이면 개별 귀속이 신뢰 가능하다."""
    counts: dict[str, int] = {}
    bases = [trade_key(r, lawd_cd, deal_ym, 0) for r in records]
    for b in bases:
        counts[b] = counts.get(b, 0) + 1
    return [counts[b] for b in bases]


def diff_mutable(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, str]]:
    """가변 필드만 비교해 **정정 목록**을 만든다. 변화 없으면 빈 목록."""
    out: list[dict[str, str]] = []
    for field in _MUTABLE_FIELDS:
        before = ("" if previous.get(field) is None else str(previous.get(field))).strip()
        after = ("" if current.get(field) is None else str(current.get(field))).strip()
        if before == after:
            continue
        # ★정상 건의 `cancel_type` 은 `' '`(스페이스)다 — strip 후 비교해야
        #   전건이 "해제됨"으로 뒤집히지 않는다(molit_client 실측 주석 참조).
        if field == "cancel_type" and after:
            kind = "cancelled"
        elif field == "registered_date" and after and not before:
            kind = "registry_added"
        else:
            kind = "field_changed"
        out.append({"kind": kind, "field": field, "old": before, "new": after})
    return out


# ══════════════════════════════════════════════════════════════════════
# 3. 영속 — alembic 신규 헤드 없이 lazy DDL(schema_guard 선례)
# ══════════════════════════════════════════════════════════════════════

_TRADES_DDL = """
CREATE TABLE IF NOT EXISTS realtx_trades (
    trade_key         text PRIMARY KEY,
    lawd_cd           text NOT NULL,
    deal_ym           text NOT NULL,
    prop_type         text NOT NULL,
    dong              text,
    jibun             text,
    area_m2           double precision,
    floor             integer,
    price_10k_won     bigint,
    deal_date         text,
    building_name     text,
    cancel_type       text,
    cancel_date       text,
    registered_date   text,
    dealing_type      text,
    buyer_type        text,
    seller_type       text,
    share_dealing_type text,
    first_seen_at     timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
)
"""

_CORRECTIONS_DDL = """
CREATE TABLE IF NOT EXISTS realtx_corrections (
    id           bigserial PRIMARY KEY,
    trade_key    text NOT NULL,
    lawd_cd      text NOT NULL,
    deal_ym      text NOT NULL,
    kind         text NOT NULL,
    field        text,
    old_value    text,
    new_value    text,
    -- ★이 정정이 속한 쌍둥이 집합의 크기. 1 이 아니면 **개별 귀속은 의미가 없다**
    --   (원천이 마스킹한 지번 때문에 구별 불가) — 집계로만 읽어야 한다.
    twin_group_size integer NOT NULL DEFAULT 1,
    detected_at  timestamptz NOT NULL DEFAULT now()
)
"""

#: 스코프 = (유형, 시군구, 거래년월). `baseline_done` 이 **최초 수집의 전건 오보**를 막는다.
_SCAN_STATE_DDL = """
CREATE TABLE IF NOT EXISTS realtx_scan_state (
    scope_key       text PRIMARY KEY,
    baseline_done   boolean NOT NULL DEFAULT false,
    last_scanned_at timestamptz,
    last_note       text
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_realtx_trades_scope ON realtx_trades (lawd_cd, deal_ym, prop_type)",
    "CREATE INDEX IF NOT EXISTS ix_realtx_corrections_key ON realtx_corrections (trade_key)",
    "CREATE INDEX IF NOT EXISTS ix_realtx_corrections_at ON realtx_corrections (detected_at DESC)",
)

_SCHEMA_READY = False


async def _ensure_schema(db: Any, force: bool = False) -> None:
    """멱등 lazy DDL.

    ★`_SCHEMA_READY` 는 **커밋 성공 후에만** 세팅한다. 커밋 전에 세우면 이후 데이터
      트랜잭션이 롤백될 때 DDL 도 함께 되돌려지는데 플래그는 ready 로 남아 다음 호출이
      생성을 건너뛴다 — **유령 ready**(테이블 부재인데 생성 스킵). `design_run_store` 동형.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    from sqlalchemy import text

    for ddl in (_TRADES_DDL, _CORRECTIONS_DDL, _SCAN_STATE_DDL):
        await db.execute(text(ddl))
    for index_sql in _INDEXES:
        await db.execute(text(index_sql))
    # 이미 배포된 테이블 방어(design_run_store 선례 동형).
    await db.execute(text(
        "ALTER TABLE realtx_corrections "
        "ADD COLUMN IF NOT EXISTS twin_group_size integer NOT NULL DEFAULT 1"))
    await db.commit()
    _SCHEMA_READY = True


def scope_key(prop_type: str, lawd_cd: str, deal_ym: str) -> str:
    return f"{prop_type}|{lawd_cd}|{deal_ym}"


_UPSERT_SQL = """
INSERT INTO realtx_trades (
    trade_key, lawd_cd, deal_ym, prop_type, dong, jibun, area_m2, floor,
    price_10k_won, deal_date, building_name, cancel_type, cancel_date,
    registered_date, dealing_type, buyer_type, seller_type, share_dealing_type,
    updated_at
) VALUES (
    :trade_key, :lawd_cd, :deal_ym, :prop_type, :dong, :jibun, :area_m2, :floor,
    :price_10k_won, :deal_date, :building_name, :cancel_type, :cancel_date,
    :registered_date, :dealing_type, :buyer_type, :seller_type, :share_dealing_type,
    now()
)
ON CONFLICT (trade_key) DO UPDATE SET
    cancel_type = EXCLUDED.cancel_type,
    cancel_date = EXCLUDED.cancel_date,
    registered_date = EXCLUDED.registered_date,
    dealing_type = EXCLUDED.dealing_type,
    buyer_type = EXCLUDED.buyer_type,
    seller_type = EXCLUDED.seller_type,
    updated_at = now()
"""


#: `_UPSERT_SQL` 이 요구하는 바인드 이름 — **SQL 에서 파생**한다(손으로 나열하면 상한이 된다).
_UPSERT_BINDS: frozenset[str] = frozenset(re.findall(r":([a-z_][a-z0-9_]*)", _UPSERT_SQL))

#: 문자열로 정규화해 저장하는 필드(공백은 strip — `cancel_type` 의 `' '` 함정 참조)
_TEXT_FIELDS: tuple[str, ...] = (
    "dong", "jibun", "deal_date", "building_name", "share_dealing_type", *_MUTABLE_FIELDS,
)
#: 수치 그대로 저장하는 필드
_NUMERIC_FIELDS: tuple[str, ...] = ("area_m2", "floor", "price_10k_won")


def upsert_params(
    record: dict[str, Any], key_id: str, lawd_cd: str, deal_ym: str, prop_type: str
) -> dict[str, Any]:
    """`_UPSERT_SQL` 에 넘길 바인드 사전.

    ★순수 함수로 꺼낸 이유: 스텁 DB 는 SQL 을 실행하지 않으므로 **바인드 누락·오타를
      런타임까지 못 잡는다.** 여기서 만들면 `_UPSERT_BINDS` 와 **키 집합 동일성**을 테스트로
      잠글 수 있다(락의 한계 ①을 그만큼 좁힌다).
    """
    params: dict[str, Any] = {
        "trade_key": key_id,
        "lawd_cd": lawd_cd,
        "deal_ym": deal_ym,
        "prop_type": record.get("prop_type") or prop_type,
    }
    for field in _TEXT_FIELDS:
        value = record.get(field)
        params[field] = None if value is None else str(value).strip()
    for field in _NUMERIC_FIELDS:
        params[field] = record.get(field)
    return params


async def persist_scope(
    db: Any,
    *,
    lawd_cd: str,
    deal_ym: str,
    prop_type: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """한 스코프의 거래를 저장하고 **정정을 탐지**한다.

    ★최초 수집(`baseline_done=false`)에서는 **정정을 0건으로 억제**한다. 그러지 않으면
      첫 실행에 전건이 "정정"으로 보고된다(`presale_monitor_service` 선례).

    Returns:
        `{"submitted": int, "corrections": list, "baseline": bool}`

    ★`submitted` 는 **투입 레코드 수**다(저장된 행 수가 아니다 — 멱등 upsert 라
      기존 행 갱신이 섞인다). 이름이 사실을 과대표현하지 않게 바꿨다.
    """
    from sqlalchemy import text

    await _ensure_schema(db)
    key = scope_key(prop_type, lawd_cd, deal_ym)

    state = (await db.execute(
        text("SELECT baseline_done FROM realtx_scan_state WHERE scope_key = :k"), {"k": key}
    )).first()
    is_baseline = not (state and state[0])

    previous = {
        row[0]: dict(zip(_MUTABLE_FIELDS, row[1:], strict=True))
        for row in (await db.execute(
            text(
                "SELECT trade_key, " + ", ".join(_MUTABLE_FIELDS) + " FROM realtx_trades "
                # ★`prop_type` 으로 좁히지 않는다 — 조회는 **키로** 하고 키는 이미
                #   `prop_type` 을 담는다(`_KEY_FIELDS`). 좁히면 오히려 **비대칭 결함**이
                #   생긴다: 저장 컬럼은 `record["prop_type"]`(레코드 값)에서 오는데
                #   조회는 스코프 인자로 걸어, 둘이 다른 날 `previous` 가 자기 행을 못 찾아
                #   **정정 탐지가 영구 0건**이 된다(2026-08-26 독립 리뷰 지적).
                #   여기서 넓게 읽어도 lookup 은 키로 하므로 남의 행이 섞이지 않는다.
                "WHERE lawd_cd = :l AND deal_ym = :y"
            ),
            {"l": lawd_cd, "y": deal_ym},
        )).fetchall()
    }

    corrections: list[dict[str, Any]] = []
    # ★쌍둥이(불변 필드가 완전히 같은 행)에 순번을 붙인다 — 안 붙이면 라이브 실측 기준
    #   평균 4%·최악 29% 가 upsert 로 **조용히 덮어써진다**.
    keys = assign_ordinals(records, lawd_cd, deal_ym)
    # ★쌍둥이 집합 크기 — 1 이 아니면 **개별 귀속을 신뢰하면 안 된다**(정정 행에 실어 보낸다).
    sizes = twin_group_sizes(records, lawd_cd, deal_ym)
    for record, key_id, twin_size in zip(records, keys, sizes, strict=True):
        await db.execute(text(_UPSERT_SQL), upsert_params(record, key_id, lawd_cd, deal_ym, prop_type))

        before = previous.get(key_id)
        if before is None or is_baseline:
            continue
        for change in diff_mutable(before, record):
            corrections.append({"trade_key": key_id, "twin_group_size": twin_size, **change})
            await db.execute(
                text(
                    "INSERT INTO realtx_corrections "
                    "(trade_key, lawd_cd, deal_ym, kind, field, old_value, new_value, "
                    " twin_group_size) "
                    "VALUES (:t, :l, :y, :k, :f, :o, :n, :g)"
                ),
                {"t": key_id, "l": lawd_cd, "y": deal_ym, "k": change["kind"],
                 "f": change["field"], "o": change["old"], "n": change["new"],
                 "g": twin_size},
            )

    await db.execute(
        text(
            "INSERT INTO realtx_scan_state (scope_key, baseline_done, last_scanned_at) "
            "VALUES (:k, true, now()) "
            "ON CONFLICT (scope_key) DO UPDATE SET baseline_done = true, last_scanned_at = now()"
        ),
        {"k": key},
    )
    await db.commit()
    return {"submitted": len(records), "corrections": corrections, "baseline": is_baseline}
