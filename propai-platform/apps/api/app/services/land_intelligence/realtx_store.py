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

★**파생이 0건이면 조용히 넘어가지 않고 죽는다**(`RealtxTargetsEmpty`). 프론트 스토어 형상이
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
from typing import Any, Iterable

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


class RealtxTargetsEmpty(RuntimeError):
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
        raise RealtxTargetsEmpty(
            f"수집 대상 시군구 0건 — user_project_store {len(rows)}행에서 landSchedule PNU 를 "
            "하나도 못 찾았다. 스토어 형상 변경을 의심하라(조용한 0건 금지)."
        )
    logger.info("실거래 수집 대상 파생: 사용자 %d명 → 시군구 %d개", len(rows), len(targets))
    return targets


# ══════════════════════════════════════════════════════════════════════
# 2. 멱등키
# ══════════════════════════════════════════════════════════════════════

def trade_key(record: dict[str, Any], lawd_cd: str, deal_ym: str) -> str:
    """거래 1건의 **결정적** 식별자. 같은 입력 → 같은 키(uuid/now/random 0)."""
    parts = [lawd_cd, deal_ym] + [
        ("" if record.get(f) is None else str(record.get(f)).strip())
        for f in _KEY_FIELDS
    ]
    return "rtx_" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


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
        `{"stored": int, "corrections": list, "baseline": bool}`
    """
    from sqlalchemy import text

    await _ensure_schema(db)
    key = scope_key(prop_type, lawd_cd, deal_ym)

    state = (await db.execute(
        text("SELECT baseline_done FROM realtx_scan_state WHERE scope_key = :k"), {"k": key}
    )).first()
    is_baseline = not (state and state[0])

    previous = {
        row[0]: dict(zip(_MUTABLE_FIELDS, row[1:]))
        for row in (await db.execute(
            text(
                "SELECT trade_key, " + ", ".join(_MUTABLE_FIELDS) + " FROM realtx_trades "
                "WHERE lawd_cd = :l AND deal_ym = :y AND prop_type = :p"
            ),
            {"l": lawd_cd, "y": deal_ym, "p": prop_type},
        )).fetchall()
    }

    corrections: list[dict[str, Any]] = []
    for record in records:
        key_id = trade_key(record, lawd_cd, deal_ym)
        params = {
            "trade_key": key_id, "lawd_cd": lawd_cd, "deal_ym": deal_ym,
            "prop_type": record.get("prop_type") or prop_type,
        }
        for field in ("dong", "jibun", "deal_date", "building_name",
                      "share_dealing_type", *_MUTABLE_FIELDS):
            value = record.get(field)
            params[field] = None if value is None else str(value).strip()
        params["area_m2"] = record.get("area_m2")
        params["floor"] = record.get("floor")
        params["price_10k_won"] = record.get("price_10k_won")
        await db.execute(text(_UPSERT_SQL), params)

        before = previous.get(key_id)
        if before is None or is_baseline:
            continue
        for change in diff_mutable(before, record):
            corrections.append({"trade_key": key_id, **change})
            await db.execute(
                text(
                    "INSERT INTO realtx_corrections "
                    "(trade_key, lawd_cd, deal_ym, kind, field, old_value, new_value) "
                    "VALUES (:t, :l, :y, :k, :f, :o, :n)"
                ),
                {"t": key_id, "l": lawd_cd, "y": deal_ym, "k": change["kind"],
                 "f": change["field"], "o": change["old"], "n": change["new"]},
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
    return {"stored": len(records), "corrections": corrections, "baseline": is_baseline}
