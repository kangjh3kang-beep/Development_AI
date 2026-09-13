"""동·호 추첨 엔진 — 즉석추첨(누르면 남은 동호 중 무작위 1개 공개) + seed 해시체인 감사.

흐름:
  1) 추첨그룹 생성(create_group) + 대상자 등록(add_candidates / import_excel / from_customers)
  2) 그룹 동·호판(unit pool) 지정(set_pool) — 그룹이 추첨할 대상 세대 집합
  3) 대상자 순번대로 추첨(draw_for_candidate): 남은 가용 세대 중 seed 기반 무작위 1개 배정
     - 배정 시 세대 상태 HOLD 전이 + 이벤트 원장 DRAW_ASSIGN(seed·group·candidate) 기록(감사)
  공정성(2026-09-13 v2): **사전 공약된 nonce** + **HMAC-SHA256 기반 VRNG**(`vrng.pick`).
    · 공약은 `sales_draw_commitments`(CRUD 밖·append-only·`UNIQUE(scope,ref_id)`)에서 온다 —
      **재공약 불가**라 「뽑아 보고 다시 뽑기」가 막힌다.
    · 선택은 **언어·버전 독립**이라 감사자가 파이썬 없이도 재현한다.
    · pool 을 **전문 저장**하고 해시는 **절단하지 않는다**(종전 64비트 절단).
    ★종전 판(v1)은 `random.Random(secrets.token_hex(8)).choice(...)` 였다. 그 방식은
      **①사전 공약 없음 ②CPython 구현 종속 ③pool 절단** 셋이 겹쳐, 원장에 seed 가 남아도
      «그 seed 가 공정하게 뽑혔다»를 증명하지 못했다.
    ★**v1 배정은 그대로 재현된다** — 「신규 공고부터」 적용이라 그룹 생성 시점의
      `algo_version` 이 경로를 못 박는다(옛 행은 기록 부재 = v1).

지정모드와 공존: 지정모드는 lifecycle_actions(직접 배정), 추첨모드는 본 엔진(무작위). 모드는 프론트 토글.
"""
from __future__ import annotations

import hashlib
import io
import json as _json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.draw import beacon, binding, vrng
from app.services.sales.draw.commitment_store import finalize_draw, reveal_commitment
from app.services.sales.units.event_ledger import append_event

logger = logging.getLogger(__name__)

_DDL_GROUPS = (
    "CREATE TABLE IF NOT EXISTS sales_draw_groups ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  name varchar(120) NOT NULL,"
    "  status varchar(12) NOT NULL DEFAULT 'OPEN',"   # OPEN/CLOSED
    "  unit_pool jsonb,"                               # 그룹 동·호판 unit_id 배열(미지정=현장 전체 가용)
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_DDL_CAND = (
    "CREATE TABLE IF NOT EXISTS sales_draw_candidates ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  group_id uuid NOT NULL,"
    "  site_id uuid NOT NULL,"
    "  seq integer NOT NULL,"                          # 추첨 순번
    "  name varchar(120) NOT NULL,"
    "  phone varchar(40),"
    "  customer_id uuid,"
    "  assigned_unit_id uuid,"                          # 추첨 배정된 세대
    "  draw_seed varchar(32),"
    "  drawn_at timestamptz,"
    "  UNIQUE (group_id, seq)"
    ")"
)
_READY = False


async def _ensure(db: AsyncSession) -> None:
    global _READY
    if _READY:
        return
    await db.execute(text(_DDL_GROUPS))
    await db.execute(text(_DDL_CAND))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_draw_cand_group ON sales_draw_candidates(group_id, seq)"))
    # ★**v1/v2 공존**(2026-09-13 · 「신규 공고부터」 적용). 옛 배정은 **그 알고리즘으로 재현**돼야
    #   하므로 v1 경로를 지울 수 없다. 그런데 지우지 않으면 신규가 실수로 v1 을 탄다 —
    #   그래서 **그룹 생성 시점에 못 박고**(아래 `create_group` 은 항상 'v2'),
    #   **기록 부재 = v1** 로 읽는다(옛 행에는 컬럼이 없었다).
    await db.execute(text(
        "ALTER TABLE sales_draw_groups ADD COLUMN IF NOT EXISTS algo_version varchar(8) "
        "NOT NULL DEFAULT 'v1'"))
    # ★`draw_seed varchar(32)` 는 VRNG 키(64 hex)를 못 담는다 — 넓히지 않으면 **조용히 잘린다.**
    await db.execute(text(
        "ALTER TABLE sales_draw_candidates ALTER COLUMN draw_seed TYPE varchar(128)"))
    # ★pool 을 **전문 저장**한다. 종전엔 `sha256(...)[:16]`(64비트 절단)만 남겨
    #   감사자가 그 시점의 pool 을 복원할 수 없었다.
    await db.execute(text(
        "ALTER TABLE sales_draw_candidates ADD COLUMN IF NOT EXISTS draw_pool jsonb"))
    await db.execute(text(
        "ALTER TABLE sales_draw_candidates ADD COLUMN IF NOT EXISTS algo_version varchar(8)"))
    await db.commit()
    _READY = True


async def create_group(db: AsyncSession, site_id, name: str) -> dict[str, Any]:
    await _ensure(db)
    if not (name or "").strip():
        raise ValueError("추첨그룹 이름을 입력하세요")
    row = (await db.execute(text(
        # ★신규 그룹은 **항상 v2**(검증 가능 난수 + 사전 공약). 「v1 로도 만들 수 있다」를
        #   남기면 그것이 곧 나중의 서식지가 된다.
        "INSERT INTO sales_draw_groups (site_id, name, algo_version) "
        "VALUES (:s,:n,'v2') RETURNING id"),
        {"s": str(site_id), "n": name.strip()})).first()
    await db.commit()
    return {"id": str(row[0]), "name": name.strip(), "status": "OPEN"}


async def list_groups(db: AsyncSession, site_id) -> list[dict[str, Any]]:
    """현장 추첨그룹 목록(대상자수·완료수 포함)."""
    await _ensure(db)
    rows = (await db.execute(text(
        "SELECT g.id, g.name, g.status, g.created_at, "
        "  (SELECT count(*) FROM sales_draw_candidates c WHERE c.group_id=g.id) AS cand, "
        "  (SELECT count(*) FROM sales_draw_candidates c "
        "     WHERE c.group_id=g.id AND c.assigned_unit_id IS NOT NULL) AS drawn "
        "FROM sales_draw_groups g WHERE g.site_id=:s ORDER BY g.created_at DESC"),
        {"s": str(site_id)})).all()
    return [{"id": str(r[0]), "name": r[1], "status": r[2], "created_at": str(r[3]),
             "candidates": int(r[4]), "drawn": int(r[5])} for r in rows]


async def set_pool(db: AsyncSession, site_id, group_id, unit_ids: list[str]) -> dict[str, Any]:
    """그룹 동·호판(추첨 대상 세대 집합) 지정.

    ★★**입력을 검증한다**(R2 리뷰 MAJOR-3). 종전에는 임의 uuid 를 그대로 `unit_pool` 에 넣었고,
      추첨이 그 목록을 모집단으로 쓰면서 **타 현장 세대·소프트삭제 세대**가 배정될 수 있었다.
      ***이 함수가 「그 현장의 살아 있는 세대인가」를 묻지 않으면, 뒤의 어느 층도 그것을 모른다.***
    """
    await _ensure(db)
    import json
    wanted = [str(u) for u in unit_ids]
    if not wanted:
        raise ValueError("대상 세대가 비어 있습니다")
    ok = {str(r[0]) for r in (await db.execute(text(
        "SELECT id FROM sales_unit_inventory "
        "WHERE site_id=:s AND id = ANY(:ids) AND deleted_at IS NULL"),
        {"s": str(site_id), "ids": wanted})).all()}
    bad = [u for u in wanted if u not in ok]
    if bad:
        raise ValueError(
            f"이 현장에 없거나 삭제된 세대가 {len(bad)}건 포함돼 있습니다: {bad[:5]}"
            f"{' …' if len(bad) > 5 else ''}"
        )
    await db.execute(text(
        "UPDATE sales_draw_groups SET unit_pool=CAST(:p AS jsonb) WHERE id=:g AND site_id=:s"),
        {"p": json.dumps(wanted), "g": str(group_id), "s": str(site_id)})
    await db.commit()
    return {"ok": True, "pool_size": len(wanted)}


async def _next_seq(db: AsyncSession, group_id) -> int:
    r = (await db.execute(text(
        "SELECT COALESCE(MAX(seq),0) FROM sales_draw_candidates WHERE group_id=:g"), {"g": str(group_id)})).first()
    return int(r[0] or 0) + 1


async def add_candidates(db: AsyncSession, site_id, group_id, rows: list[dict]) -> dict[str, Any]:
    """대상자 일괄 등록 — rows: [{name, phone?, customer_id?}]. 순번은 기존 뒤에 이어 부여."""
    await _ensure(db)
    seq = await _next_seq(db, group_id)
    n = 0
    for r in rows:
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        await db.execute(text(
            "INSERT INTO sales_draw_candidates (group_id, site_id, seq, name, phone, customer_id) "
            "VALUES (:g,:s,:seq,:n,:p,:c)"),
            {"g": str(group_id), "s": str(site_id), "seq": seq, "n": name,
             "p": (r.get("phone") or None), "c": (str(r["customer_id"]) if r.get("customer_id") else None)})
        seq += 1
        n += 1
    await db.commit()
    return {"ok": True, "added": n}


def parse_excel(content: bytes) -> list[dict]:
    """고객명부 Excel(.xlsx) 파싱 — 1행 헤더(이름/성명/name, 연락처/전화/phone) 자동인식, 그 외 첫2열=이름,전화."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(c or "").strip().lower() for c in rows[0]]
    def _idx(keys, default):
        for i, h in enumerate(header):
            if any(k in h for k in keys):
                return i
        return default
    ni = _idx(["이름", "성명", "name"], 0)
    pi = _idx(["연락처", "전화", "휴대", "phone", "tel"], 1)
    out = []
    for r in rows[1:]:
        if not r or all(c is None for c in r):
            continue
        name = str(r[ni]).strip() if ni < len(r) and r[ni] is not None else ""
        phone = str(r[pi]).strip() if pi < len(r) and r[pi] is not None else None
        if name:
            out.append({"name": name, "phone": phone})
    return out


async def from_customers(db: AsyncSession, site_id, group_id, customer_ids: list[str] | None = None) -> dict[str, Any]:
    """계약자/고객 명부에서 대상자 선별 등록. customer_ids 미지정 시 현장 전체 고객."""
    await _ensure(db)
    q = "SELECT id, name, phone_e164 FROM sales_customers WHERE site_id=:s AND deleted_at IS NULL"
    params: dict[str, Any] = {"s": str(site_id)}
    if customer_ids:
        q += " AND id = ANY(:ids)"
        params["ids"] = [str(c) for c in customer_ids]
    try:
        rows = (await db.execute(text(q), params)).all()
    except Exception:  # noqa: BLE001 — 컬럼차이 시 최소 컬럼
        await db.rollback()
        rows = (await db.execute(text(
            "SELECT id, name, NULL FROM sales_customers WHERE site_id=:s"), {"s": str(site_id)})).all()
    cands = [{"name": r[1] or "고객", "phone": r[2], "customer_id": str(r[0])} for r in rows]
    return await add_candidates(db, site_id, group_id, cands)


async def from_winners(db: AsyncSession, site_id, group_id, announcement_id) -> dict[str, Any]:
    """청약 당첨자 명부 → 동·호 추첨 대상자 시드(흐름 연결: 청약→당첨→동·호배정).

    당첨자(sales_subscription_winners)를 당첨 우선순위(순위 rank↑, 가점 gajeom_score↓)대로
    추첨 대상자로 등록한다 → 순번이 곧 당첨 우선순위. 신청에 고객(customer_id)이 연결돼 있으면
    이름·연락처를, 없으면(청약홈 채널 등) '당첨자 NNNN'으로 표기한다. run_draw 의 세대 자동배정과
    무관하게 '사람'만 대상자로 시드하므로 비파괴(동·호 풀은 set_pool 로 별도 지정)."""
    await _ensure(db)
    rows = (await db.execute(text(
        "SELECT w.id, a.customer_id, c.name, c.phone_e164, COALESCE(a.rank,9) AS rk, COALESCE(a.gajeom_score,0) AS gj "
        "FROM sales_subscription_winners w "
        "JOIN sales_subscription_applications a ON a.id = w.application_id "
        "LEFT JOIN sales_customers c ON c.id = a.customer_id "
        "WHERE w.site_id=:s AND a.announcement_id=:ann "
        "ORDER BY rk ASC, gj DESC, w.decided_at ASC"),
        {"s": str(site_id), "ann": str(announcement_id)})).all()
    cands = [{
        "name": (r[2] or f"당첨자 {str(r[0])[:4]}"),
        "phone": r[3],
        "customer_id": (str(r[1]) if r[1] else None),
    } for r in rows]
    if not cands:
        return {"ok": True, "added": 0, "note": "해당 공고의 당첨자가 없습니다(추첨 실행 전이거나 당첨 0)."}
    return await add_candidates(db, site_id, group_id, cands)


async def committable_pool(db: AsyncSession, site_id, group_id) -> list[str]:
    """★**공약 시점에 못 박을 대상 세대** — 그룹 동·호판(`unit_pool`)이 정본이다.

    판이 지정돼 있지 않으면 **현장 전체 가용 세대**로 떨어지는데, 그 상태로 공약하면
    *"무엇을 대상으로 뽑았는지"* 가 라이브 상태에 의존한다 ⇒ **판을 먼저 지정하라**고 거부한다.
    (`_remaining_units` 는 추첨 중 「남은 것」을 보는 함수라 축이 다르다 — 이름을 나눈 이유다.)
    """
    import json
    g = (await db.execute(text(
        "SELECT unit_pool FROM sales_draw_groups WHERE id=:g AND site_id=:s"),
        {"g": str(group_id), "s": str(site_id)})).first()
    raw = g[0] if g else None
    pool = (raw if isinstance(raw, list) else json.loads(raw)) if raw else []
    if not pool:
        raise ValueError(
            "동·호판(추첨 대상 세대)이 지정되지 않았습니다 — 공약 전에 "
            "`POST /draw/groups/{id}/pool` 로 대상을 확정하십시오. "
            "★판 없이 공약하면 「무엇을 대상으로 뽑았는지」가 추첨 시점 상태에 따라 달라집니다"
        )
    return [str(u) for u in pool]


async def _remaining_units(db: AsyncSession, site_id, group_id) -> list[str]:
    """그룹 동·호판에서 아직 배정되지 않은(AVAILABLE) 세대 목록."""
    import json
    g = (await db.execute(text(
        "SELECT unit_pool FROM sales_draw_groups WHERE id=:g AND site_id=:s"),
        {"g": str(group_id), "s": str(site_id)})).first()
    pool = None
    if g and g[0]:
        pool = g[0] if isinstance(g[0], list) else json.loads(g[0])
    if pool:
        rows = (await db.execute(text(
            "SELECT id FROM sales_unit_inventory WHERE site_id=:s AND id = ANY(:ids) "
            "AND status='AVAILABLE' AND deleted_at IS NULL"),
            {"s": str(site_id), "ids": [str(u) for u in pool]})).all()
    else:  # 풀 미지정 → 현장 전체 가용
        rows = (await db.execute(text(
            "SELECT id FROM sales_unit_inventory WHERE site_id=:s AND status='AVAILABLE' AND deleted_at IS NULL"),
            {"s": str(site_id)})).all()
    # 이미 같은 그룹서 배정된 세대 제외(이중배정 방지).
    assigned = {str(r[0]) for r in (await db.execute(text(
        "SELECT assigned_unit_id FROM sales_draw_candidates WHERE group_id=:g AND assigned_unit_id IS NOT NULL"),
        {"g": str(group_id)})).all()}
    return [str(r[0]) for r in rows if str(r[0]) not in assigned]


async def draw_for_candidate(db: AsyncSession, site_id, group_id, candidate_id, by=None) -> dict[str, Any]:
    """즉석추첨 — 대상자가 누르면 남은 동호 중 seed 기반 무작위 1개를 배정·공개(감사 기록)."""
    await _ensure(db)
    cand = (await db.execute(text(
        "SELECT seq, name, assigned_unit_id FROM sales_draw_candidates WHERE id=:c AND group_id=:g"),
        {"c": str(candidate_id), "g": str(group_id)})).first()
    if not cand:
        raise ValueError("추첨 대상자를 찾을 수 없습니다")
    if cand[2]:
        raise ValueError("이미 추첨이 완료된 대상자입니다")
    # ★HOLD 선점은 'RETURNING id' 로 원자 확정한다(이중배정 방지). 동시 추첨/지정 경합으로 방금 선점된
    #   세대(0행)면 그 세대를 빼고 남은 가용 세대를 재조회해 재추첨한다. 모든 후보가 소진되면 명확한 에러.
    # 공정 추첨: 매 시도마다 secrets seed → 결정적 선택(재현·검증 가능). sorted 로 입력 순서 영향 제거.
    # ★**v2 로 전환**(2026-09-13). 종전에는 이랬다:
    #     seed = secrets.token_hex(8);  random.Random(seed).choice(sorted(remaining))
    #   결함 셋이 있었다 —
    #     ① **사전 공약이 없다**: 뽑아 보고 롤백 후 재시도(grinding)해도 원장엔 **성공분 하나만**
    #        남아 그 사실이 보이지 않는다.
    #     ② **재현이 CPython 구현 종속**: `random.Random(str)` 의 시딩과 `choice` 내부는 구현
    #        세부라 파이썬 버전이 바뀌면 결과가 달라질 수 있고 **다른 언어로는 재현 불가**다.
    #     ③ pool 을 **해시 앞 16자(64비트)** 로만 남겨 감사자가 그 시점 pool 을 복원할 수 없다.
    #   ⇒ 공약된 nonce 로 **HMAC-SHA256 기반 VRNG**(`vrng.pick`)를 쓰고, pool 을 **전문 저장**한다.
    #   ★카운터는 **대상자 순번**으로 도메인 분리한다 — 같은 그룹 안에서 두 사람이 같은 스트림을
    #     쓰면 결과가 상관된다.
    #   ★★**Phase 1(비콘)**: 공약 시점에 못 박은 **미래 drand 라운드**를 여기서 가져와 키에 섞는다.
    #     그래서 nonce 를 아는 사람(DB 직접 접근)도 **그 라운드가 공개되기 전에는** 결과를 계산할 수
    #     없다. 라운드가 아직이면 `beacon.seed_contributions` 가 **몇 초 남았는지 말하며 거부**하고,
    #     비콘을 못 가져와도 **거부**한다(fail-closed — 조용히 비콘 없이 뽑지 않는다).
    rev = await reveal_commitment(db, "dongho", group_id)
    commit_hex = rev.commit_hash
    beacon_parts, beacon_label = beacon.seed_contributions(rev.beacon_round)
    # ★★**명부가 공약 이후에 바뀌었으면 뽑지 않는다**(독립 적대 리뷰 2026-09-13 MAJOR-1).
    #   종전에는 키의 자유변수가 `candidate_id` **뿐**이라, 운영자가 같은 사람을 여러 번 등록해
    #   각 id 의 결과를 오프라인 계산하고 **원하는 동·호가 나오는 행만 누를 수 있었다**
    #   (실측: 30세대 중 지정 1세대를 얻는 데 등록 75회 · 원장·공약·비콘 무변화 · 검증기 ✔).
    #   ***nonce grinding 을 막았더니 식별자 grinding 으로 자리를 옮겼던 것이다.***
    live_roster = [str(r[0]) for r in (await db.execute(text(
        "SELECT id FROM sales_draw_candidates WHERE group_id=:g AND site_id=:s"),
        {"g": str(group_id), "s": str(site_id)})).all()]
    if binding.roster_hash(live_roster) != rev.participants_hash:
        raise ValueError(
            f"공약 이후 **명부가 바뀌었습니다**(공약 {len(rev.participants)}명 ↔ 현재 "
            f"{len(set(live_roster))}명) — 추첨하지 않습니다. 명부를 바꾸려면 "
            "추첨을 취소하고 **다시 공약**해야 합니다"
        )
    domain = f"dongho:{group_id}:{candidate_id}"
    # ★지문을 **seed 에도 섞는다**(이중 방어): 게이트만 두면 게이트를 우회하는 경로가 생기지만,
    #   seed 에 들어가면 명부·세대를 바꾸는 순간 **결과가 바뀌어** 제3자 검증에서 드러난다.
    key = vrng.seed_key(rev.nonce, str(group_id), str(candidate_id),
                        rev.participants_hash, rev.pool_hash, *beacon_parts)
    seed = key.hex()

    chosen: str | None = None
    pool_sorted: list[str] = []
    pool_hash = ""
    counter = 0
    excluded: set[str] = set()  # 이번 호출에서 선점 실패해 제외한 세대(재조회 후에도 중복 시도 방지).
    start_counter = 0           # ★당첨을 만든 시도의 **시작 카운터** — 원장에 남긴다(아래 사유).
    # ★★**모집단은 「공약된 pool」이다 — 라이브 `AVAILABLE` 을 다시 조회하지 않는다**
    #   (독립 적대 리뷰 2026-09-13 MAJOR-2). 종전에는 매 시도마다 실시간 조회라, 추첨 직전에
    #   세대를 HOLD 로 빼는 것만으로 결과를 고를 수 있었다(실측: **3건만 빼면 30세대 중 10세대**
    #   도달). 통로는 최소 셋이었다 — `POST …/pool` · `HOLD_REQUEST` · 범용 CRUD `units`.
    #   이미 배정된 세대만 빼고 **공약된 목록 그대로** 돈다. 세대가 실제로 못 쓰는 상태면
    #   아래 조건부 UPDATE 가 0행을 돌려주므로 **그때 제외**된다(원자적 · 선점 경합과 같은 경로).
    committed_pool = set(rev.pool_ids)
    assigned = {str(r[0]) for r in (await db.execute(text(
        "SELECT assigned_unit_id FROM sales_draw_candidates "
        "WHERE group_id=:g AND assigned_unit_id IS NOT NULL"), {"g": str(group_id)})).all()}
    while True:
        remaining = sorted(committed_pool - assigned - excluded)
        if not remaining:
            raise ValueError("남은 가용 세대가 없습니다(추첨 종료)")
        pool_sorted = remaining
        # ★재시도(선점 경합)마다 **카운터를 이어받는다** — seed 를 새로 뽑지 않는다.
        #   새로 뽑으면 그게 곧 grinding 통로다(공약이 무의미해진다).
        start_counter = counter
        candidate_unit, counter = vrng.pick(key, domain, pool_sorted, start=counter)
        pool_hash = hashlib.sha256(",".join(pool_sorted).encode()).hexdigest()
        # HOLD 선점(원자 조건부 UPDATE) — 0행이면 이미 다른 곳에서 선점됨 → 재추첨.
        # ★★**`site_id`·`deleted_at` 를 여기서 다시 건다**(R2 리뷰 MAJOR-3 · 내가 만든 회귀).
        #   모집단을 라이브 조회에서 공약된 pool 로 바꾸면서 `_remaining_units` 가 걸고 있던
        #   `site_id=:s AND deleted_at IS NULL` 이 **통째로 사라졌다**. 그 결과:
        #     · `CRUDBase.delete` 는 **소프트삭제**(`deleted_at` 만 세우고 `status` 는 안 건드린다)
        #       ⇒ 삭제된 세대가 `status='AVAILABLE'` 로 남아 **배정 가능**했다
        #     · `set_pool` 이 입력을 검증하지 않아 **타 현장 세대 id** 를 넣으면 그대로 HOLD 됐다
        #       (이 저장소에 같은 클래스 IDOR 사고가 이미 두 건 기록돼 있다)
        #   ***모집단을 바꾸면 그 모집단이 지키던 술어도 함께 옮겨야 한다.***
        won = (await db.execute(text(
            "UPDATE sales_unit_inventory SET status='HOLD' "
            "WHERE id=:u AND site_id=:s AND status='AVAILABLE' AND deleted_at IS NULL RETURNING id"),
            {"u": candidate_unit, "s": str(site_id)})).first()
        if won:
            chosen = candidate_unit
            break
        excluded.add(candidate_unit)  # 방금 선점된 세대 — 제외하고 재추첨.

    # 세대 정보(공개용)는 HOLD 확정 후 조회. DRAW_ASSIGN 이벤트도 확정 성공분만 기록한다.
    u = (await db.execute(text(
        "SELECT dong, ho FROM sales_unit_inventory WHERE id=:u AND site_id=:s"),
        {"u": chosen, "s": str(site_id)})).first()
    await db.execute(text(
        "UPDATE sales_draw_candidates SET assigned_unit_id=:u, draw_seed=:seed, "
        "draw_pool=CAST(:pool AS jsonb), algo_version='v2', drawn_at=now() WHERE id=:c"),
        {"u": chosen, "seed": seed, "c": str(candidate_id),
         "pool": _json.dumps(pool_sorted, ensure_ascii=False)})

    # 감사: 이벤트 원장에 추첨 배정 기록(seed·group·candidate·pool_hash → 사후 검증).
    # HOLD UPDATE + candidate UPDATE + 이벤트 원장을 한 트랜잭션으로 묶어 한 번에 커밋(원자성).
    ev = await append_event(db, site_id, chosen, "DRAW_ASSIGN", from_status="AVAILABLE", to_status="HOLD",
                            message=f"추첨 배정: {cand[1]}(순번 {cand[0]})", by=by,
                            meta={"group_id": str(group_id), "candidate_id": str(candidate_id),
                                  "seed": seed, "pool_hash": pool_hash, "pool_size": len(pool_sorted),
                                  "algo_version": "v2", "commit_hash": commit_hex,
                                  "beacon_round": rev.beacon_round, "beacon": beacon_label,
                                  # ★공약이 **무엇을 묶었는지**. 위 `pool_hash` 는 «이번 시도의 남은
                                  #   pool», 아래는 «공약된 전체 pool» — **다른 값이라 이름도 다르다.**
                                  "participants_hash": rev.participants_hash,
                                  "committed_pool_hash": rev.pool_hash,
                                  # ★**건너뛴 세대 목록**을 남긴다(카운터가 아니라).
                                  #   선점 경합이 나면 프로덕션은 카운터를 이어받는데, 그 사실이
                                  #   없으면 검증기가 `start=0` 으로 재계산해 **정직한 추첨을 조작으로
                                  #   신고**한다(R1 MED-5). 그렇다고 **카운터 숫자**를 주면 그건
                                  #   ***아무 데도 대조할 수 없는 자유변수***라 무엇이든 인증된다
                                  #   (R2 MAJOR-4 실측: 임의 6개 세대 전부 통과).
                                  #   ⇒ **어떤 세대를 건너뛰었는지**를 남긴다 — 그 목록은
                                  #   「이미 배정됐는가」로 **원장과 교차 확인이 가능한 공개 사실**이다.
                                  "skipped_units": sorted(excluded),
                                  "start_counter": start_counter},
                            do_commit=False)
    await db.commit()
    # ★★**전원이 뽑혔으면 최종화한다** — 결과 루트를 체인에 올리고 **nonce 공개를 연다.**
    #   ***중간에 열면 남은 대상자의 결과가 즉시 계산된다*** — 그래서 「전원」이 조건이다.
    remaining_cands = (await db.execute(text(
        "SELECT count(*) FROM sales_draw_candidates "
        "WHERE group_id=:g AND assigned_unit_id IS NULL"), {"g": str(group_id)})).first()
    finalized = None
    if remaining_cands and int(remaining_cands[0]) == 0:
        leaves = [
            # 결과 잎: **대상자 id + 배정 세대** — 이름·연락처는 들어가지 않는다(체인은 영구다).
            hashlib.sha256(f"{r[0]}:{r[1]}".encode()).hexdigest()
            for r in (await db.execute(text(
                "SELECT id, assigned_unit_id FROM sales_draw_candidates "
                "WHERE group_id=:g ORDER BY id"), {"g": str(group_id)})).all()
        ]
        try:
            finalized = await finalize_draw(db, "dongho", group_id, leaves)
        except Exception as exc:                  # noqa: BLE001 — 최종화 실패가 추첨을 무르지 않는다
            logger.warning("추첨 최종화 실패(추첨 자체는 성립): %s", exc)
            finalized = {"error": f"{type(exc).__name__}"}
    return {
        "ok": True, "candidate": {"seq": int(cand[0]), "name": cand[1]},
        "finalized": finalized,
        "assigned_unit": {"id": chosen, "dong": u[0] if u else None, "ho": u[1] if u else None},
        "seed": seed, "pool_hash": pool_hash, "pool_size": len(pool_sorted), "remaining_after": len(remaining) - 1,
        # ★비콘을 **썼는지 안 썼는지**를 응답이 말한다 — 침묵하면 「썼다고 해 놓고 안 쓰는」 경로가 보이지 않는다.
        "beacon_round": rev.beacon_round, "beacon": beacon_label,
        "participants_hash": rev.participants_hash, "committed_pool_hash": rev.pool_hash,
        # ★`skipped_units` 가 검증기의 `--taken` 입력이다(대조 가능) · `start_counter` 는 참고값
        "skipped_units": sorted(excluded), "start_counter": start_counter,
        "event": ev,
    }


async def contract_from_candidate(db: AsyncSession, site_id, group_id, candidate_id, by=None) -> dict[str, Any]:
    """추첨으로 동·호를 배정(HOLD)받은 당첨자를 계약으로 연결 — 청약→당첨→동·호배정→계약 완결.

    배정된 세대(assigned_unit_id)와 대상자의 고객(customer_id, 청약홈 채널이면 없음)으로 계약을 생성한다.
    이미 그 세대에 활성 계약이 있으면(중복 클릭 등) 새로 만들지 않고 기존 계약을 반환(멱등)."""
    await _ensure(db)
    cand = (await db.execute(text(
        "SELECT name, assigned_unit_id, customer_id FROM sales_draw_candidates "
        "WHERE id=:c AND group_id=:g AND site_id=:s"),
        {"c": str(candidate_id), "g": str(group_id), "s": str(site_id)})).first()
    if not cand:
        raise ValueError("추첨 대상자를 찾을 수 없습니다")
    if not cand[1]:
        raise ValueError("아직 동·호가 배정되지 않은 대상자입니다(먼저 추첨하세요)")
    unit_id = cand[1]
    # 멱등: 같은 세대에 이미 활성 계약이 있으면 그대로 반환(중복 생성 방지).
    existing = (await db.execute(text(
        "SELECT id, stage, total_price FROM sales_contracts_ext "
        "WHERE unit_id=:u AND site_id=:s AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1"),
        {"u": str(unit_id), "s": str(site_id)})).first()
    if existing:
        return {"ok": True, "existing": True, "contract_id": str(existing[0]),
                "unit_id": str(unit_id), "stage": existing[1], "total_price": int(existing[2] or 0)}
    from app.services.sales.contract.service import create_contract
    c = await create_contract(db, site_id, unit_id,
                              customer_id=(cand[2] if cand[2] else None), by=by)
    # 추첨 당첨자 → 계약 연결을 세대 이벤트 원장에 남겨 사후 추적(감사).
    await append_event(db, site_id, unit_id, "NOTE",
                       message=f"추첨 당첨자 계약 연결: {cand[0]}", by=by, do_commit=False)
    await db.commit()
    return {"ok": True, "existing": False, "contract_id": str(c.id), "unit_id": str(unit_id),
            "stage": c.stage, "total_price": int(c.total_price or 0)}


async def group_status(db: AsyncSession, site_id, group_id) -> dict[str, Any]:
    """그룹 현황 — 대상자(순번·배정세대)·진행률·남은 세대."""
    await _ensure(db)
    g = (await db.execute(text(
        "SELECT name, status FROM sales_draw_groups WHERE id=:g AND site_id=:s"),
        {"g": str(group_id), "s": str(site_id)})).first()
    if not g:
        raise ValueError("추첨그룹을 찾을 수 없습니다")
    cands = (await db.execute(text(
        "SELECT c.seq, c.name, c.phone, c.assigned_unit_id, c.draw_seed, c.drawn_at, u.dong, u.ho, c.id, ct.id "
        "FROM sales_draw_candidates c "
        "LEFT JOIN sales_unit_inventory u ON u.id=c.assigned_unit_id "
        "LEFT JOIN sales_contracts_ext ct ON ct.unit_id=c.assigned_unit_id AND ct.site_id=:s AND ct.status='ACTIVE' "
        "WHERE c.group_id=:g ORDER BY c.seq ASC"), {"g": str(group_id), "s": str(site_id)})).all()
    roster = [{
        "id": str(c[8]),  # candidate_id — 프론트 추첨 버튼용
        "seq": int(c[0]), "name": c[1], "phone": c[2],
        "assigned_unit_id": str(c[3]) if c[3] else None,
        "assigned_label": (f"{c[6]}동 {c[7]}호" if c[3] and c[6] else None),
        "seed": c[4], "drawn_at": str(c[5]) if c[5] else None, "done": bool(c[3]),
        "contract_id": str(c[9]) if c[9] else None,  # 추첨 배정→계약 연결 여부
    } for c in cands]
    remaining = await _remaining_units(db, site_id, group_id)
    drawn = sum(1 for r in roster if r["done"])
    return {"group_id": str(group_id), "name": g[0], "status": g[1],
            "candidates": len(roster), "drawn": drawn, "remaining_units": len(remaining), "roster": roster}
