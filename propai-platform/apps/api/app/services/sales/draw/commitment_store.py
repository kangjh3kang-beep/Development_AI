"""추첨 **공약 저장소** — 공약이 「연극」이 되지 않게 하는 최소 구조.

## 무엇이 연극이었나 (독립 적대 리뷰 2026-09-13 · M-1/M-2 실측)

공약을 `announcement.rules`(JSONB)에 두었더니 두 가지가 동시에 깨졌다:

  **M-1 — 공약과 공개를 같은 역할이 같은 API 로 함께 쓴다.**
    `rules` 는 범용 CRUD(`PATCH /sales/subscription/announcements/{id}`)로 **통째로 덮어쓸 수
    있고**, 그 쓰기 역할(`AGENCY·SUBAGENCY·DIRECTOR·GM_DIRECTOR·DEVELOPER`)은 추첨 역할
    (`DEVELOPER·AGENCY`)을 **완전히 포함**한다. 즉 운영자는 신청자 명부를 본 뒤
    `PATCH rules={draw_commit: H(n), draw_nonce: n}` 한 번 → `POST draw` 로 **원하는 결과를 고를
    수 있다.** 롤백도 필요 없다.
    ***「공약 이후 바꾸면 해시가 어긋난다」는 공약이 추첨보다 앞섰다는 증거가 있을 때만 참인데,
    그 증거를 만드는 장치가 없었다.***

  **M-2 — nonce 가 추첨 전에 읽히는 필드에 산다.**
    `GET /subscription/announcements` 는 쓰기 역할을 요구하지 않는다. 공약을 정직하게 «미리»
    게시하려고 nonce 를 같이 넣는 순간 **같은 현장을 보는 누구나 결과를 사전 계산**한다.
    미리 안 넣으면 M-1 이다 — ***같은 칸에 둔 것이 이 딜레마의 원인이었다.***

## 이 저장소가 하는 것

  1. **CRUD 표면 밖**이다 — 이 테이블은 어떤 범용 CRUD 에도 등록하지 않는다.
  2. **append-only** — `UNIQUE(scope, ref_id)` 로 **한 번만** 공약할 수 있다(재공약 불가).
     되돌리려면 행을 지워야 하고, 그건 DB 직접 접근이라 **흔적이 남는 층**으로 올라간다.
  3. **nonce 는 읽기 API 에 실리지 않는다** — 공개하는 것은 `commit_hash` 와 `committed_at` 뿐.
     추첨 시점에 서버가 내부에서만 읽어 검증한다.
  4. **시점을 기록한다** — `committed_at` 이 있어야 «공약이 추첨보다 앞섰다」를 말할 수 있다.

★**남은 한계(정직하게 적는다)**: DB 를 직접 읽을 수 있는 사람은 여전히 nonce 를 본다.
  ★★**Phase 1 이 이 자리를 겨눴다** — 공약 시점에 **미래 drand 라운드**를 함께 못 박고
  추첨 seed 에 섞는다. 그러면 nonce 를 다 읽어도 **그 라운드가 공개되기 전에는 결과를 계산할 수
  없다**(그 값은 아직 세상에 없다). ***운영자 무신뢰에 한 걸음 더 갔지만, 여전히 완전하지는 않다***:
  운영자는 라운드가 나온 **뒤에** 결과를 먼저 보고 추첨을 미룰 수 있다 — 그 층은 `committed_at`
  과 원장 시각으로 **보이게** 할 뿐 막지는 못한다.
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.draw import beacon, binding, vrng

_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_draw_commitments ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  scope varchar(24) NOT NULL,"          # 'subscription' | 'dongho'
    "  ref_id uuid NOT NULL,"                # 공고 id 또는 추첨그룹 id
    "  commit_hash varchar(64) NOT NULL,"    # sha256(nonce) — 공개해도 되는 값
    "  nonce varchar(128) NOT NULL,"         # ★읽기 API 에 싣지 않는다
    "  committed_by uuid,"
    "  committed_at timestamptz NOT NULL DEFAULT now(),"
    "  revealed_at timestamptz,"
    "  beacon_round bigint,"                # ★공개 비콘의 **미래** 라운드 — 공개해도 되는 값
    "  participants jsonb,"                  # ★공약 시점 명부 전문(서버 내부)
    "  pool_ids jsonb,"                      # ★공약 시점 대상 세대 전문(서버 내부)
    "  participants_hash varchar(64),"       # 그 지문 — **공개**한다
    "  pool_hash varchar(64),"               # 그 지문 — **공개**한다

    "  UNIQUE (scope, ref_id)"               # ★재공약 불가 — 이것이 grinding 을 막는 축이다
    ")"
)


#: ★DDL 을 **프로세스당 한 번만** 돌린다. `ALTER TABLE … IF NOT EXISTS` 는 **무변경일 때도**
#:   Postgres 에서 `ACCESS EXCLUSIVE` 잠금을 잡는다 — 공개 GET 과 추첨 트랜잭션이 매번 그
#:   잠금을 줄 세우면 즉석추첨(동시 다발)에서 추첨 경로 전체가 직렬화된다(리뷰 MED-4).
#:   ★플래그는 **성공한 뒤에만** 세운다 — 실패를 「했다」로 기억하면 영원히 다시 시도하지 않는다.
_DDL_DONE = False


async def _ensure(db: AsyncSession) -> None:
    global _DDL_DONE
    if _DDL_DONE:
        return
    await db.execute(text(_DDL))
    # Phase 0 에서 만들어진 테이블에는 이 컬럼들이 없다 — 기존 배포를 깨지 않고 올린다.
    for col, typ in (("beacon_round", "bigint"), ("participants", "jsonb"), ("pool_ids", "jsonb"),
                     ("participants_hash", "varchar(64)"), ("pool_hash", "varchar(64)")):
        await db.execute(text(
            f"ALTER TABLE sales_draw_commitments ADD COLUMN IF NOT EXISTS {col} {typ}"))
    _DDL_DONE = True


@dataclass(frozen=True)
class Revealed:
    """추첨 시점에 서버 내부에서만 읽는 공약 내용.

    ★**튜플이 아니라 이름 있는 구조**로 돌려주는 이유: 종전 `(nonce, commit_hash)` 2-튜플에
      비콘 라운드를 **뒤에 덧붙이면** 기존 호출부가 조용히 옛 모양으로 계속 언팩한다
      (= 비콘을 안 쓰는 경로가 초록으로 남는다). 이름을 바꿔 **모든 호출부가 갱신되도록** 강제한다.
    """
    nonce: str
    commit_hash: str
    beacon_round: int | None
    #: ★공약 시점의 **명부와 대상 세대 전문**. 추첨은 **이것을 모집단으로 쓴다** —
    #:   라이브 상태를 다시 조회하면 공약 이후 바꾼 것이 그대로 먹힌다(리뷰 MAJOR-1/2).
    participants: list[str]
    pool_ids: list[str]
    participants_hash: str
    pool_hash: str


async def commit_draw(db: AsyncSession, site_id, scope: str, ref_id, *,
                      participants, pool_ids, by=None,
                      beacon_round: int | None = None, fetch=None) -> dict[str, Any]:
    """공약을 **한 번만** 게시한다. 이미 있으면 **거부**(재공약 불가).

    ★nonce 는 **서버가 만든다** — 호출자가 넣으면 그것을 고를 수 있다.
    ★**비콘 라운드를 함께 못 박는다.** 안 주면 `beacon.target_round()` 로 **미래** 라운드를 잡고,
      비콘을 못 가져오면 **공약 자체를 거부**한다(fail-closed).
    ★★**`participants` 와 `pool_ids` 는 기본값이 없다** — 호출부가 **반드시** 넘겨야 한다.
      기본값을 두면 «안 넘겨도 도는 경로»가 생기고, 그 경로가 곧 리뷰가 찾아낸 grinding 통로다.
      ***공약이 무엇을 묶는지 안 적으면 grinding 은 사라지지 않고 자리를 옮긴다.***
    반환에는 **nonce 를 싣지 않는다.**
    """
    import secrets

    await _ensure(db)
    participants = binding.normalize(participants)
    pool_ids = binding.normalize(pool_ids)
    if not participants:
        raise ValueError(
            "명부가 비어 있습니다 — 공약은 **확정된 명부 위에서만** 의미가 있습니다"
            "(공약 뒤에 사람을 더 넣을 수 있으면 그게 곧 결과를 고르는 통로입니다)"
        )
    if not pool_ids:
        raise ValueError("대상 세대가 비어 있습니다 — 공약 전에 동·호판을 지정하십시오")
    dup = (await db.execute(text(
        "SELECT commit_hash, committed_at FROM sales_draw_commitments "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})).first()
    if dup:
        raise ValueError(
            f"이미 공약이 게시돼 있습니다(게시 {dup[1]}) — 재공약은 허용되지 않습니다. "
            "다시 뽑고 싶다면 추첨을 취소·재오픈하는 별도 절차를 쓰십시오"
        )
    # ★비콘 조회는 **INSERT 전에 전부 끝낸다.** 종전에는 `seconds_until` 을 반환 dict 안에서
    #   불러 **커밋 뒤에 세 번째 HTTP** 를 태웠고, 거기서 실패하면 *"게시하지 않았습니다"* 라고
    #   말하면서 **행은 남았다**(`db.rollback()` 은 커밋 뒤엔 no-op) ⇒ 그 ref_id 는 **영구히 409**.
    #   ***일시적 네트워크 장애가 그룹 하나를 수동 절차 뒤로 영구히 밀어냈다***(리뷰 MAJOR-4).
    latest = beacon.latest_round(fetch=fetch)
    if beacon_round is None:
        beacon_round = latest + beacon.LEAD_ROUNDS
    elif int(beacon_round) <= latest:
        raise ValueError(
            f"비콘 라운드 {beacon_round} 는 이미 공개된 값입니다(현재 {latest}) — "
            "공약에는 **아직 세상에 없는 미래 라운드**만 쓸 수 있습니다"
        )
    beacon_round = int(beacon_round)
    # 남은 시간은 **방금 받은 `latest` 로 산술**한다 — 네트워크를 한 번 더 타지 않는다.
    available_in_s = max(0, (beacon_round - latest) * beacon.ROUND_PERIOD_S)

    nonce = secrets.token_hex(32)          # 32바이트 — `vrng.is_strong_nonce` 하한과 같은 축
    commit_hash = vrng.commitment(nonce)
    p_hash = binding.roster_hash(participants)
    u_hash = binding.pool_hash(pool_ids)
    await db.execute(text(
        "INSERT INTO sales_draw_commitments "
        "(site_id, scope, ref_id, commit_hash, nonce, committed_by, beacon_round, "
        " participants, pool_ids, participants_hash, pool_hash) "
        "VALUES (:site,:s,:r,:c,:n,:by,:br,CAST(:p AS jsonb),CAST(:u AS jsonb),:ph,:uh)"),
        {"site": str(site_id), "s": scope, "r": str(ref_id),
         "c": commit_hash, "n": nonce, "by": str(by) if by else None,
         "br": beacon_round, "p": _json.dumps(participants), "u": _json.dumps(pool_ids),
         "ph": p_hash, "uh": u_hash})
    await db.commit()
    # ★공개 반환에 nonce 가 없다. 반대로 라운드·지문은 **공개해야** 한다 —
    #   그것이 없으면 제3자가 «무엇을 대상으로 뽑았는지»를 확인할 수 없다.
    return {"scope": scope, "ref_id": str(ref_id), "commit_hash": commit_hash,
            "beacon_round": beacon_round, "beacon_available_in_s": available_in_s,
            "participants_hash": p_hash, "participants_count": len(participants),
            "pool_hash": u_hash, "pool_size": len(pool_ids)}


async def reveal_commitment(db: AsyncSession, scope: str, ref_id) -> Revealed:
    """추첨 시점에 **서버 내부에서만** 공약을 꺼낸다.

    공약이 없으면 예외 — ***공약 없는 추첨은 하지 않는다(fail-closed).***
    ★명부·pool 이 비어 있는 **옛 행도 거부**한다. 그런 행으로 추첨하면 모집단이 라이브 상태에서
      오고, 그것이 리뷰가 찾아낸 grinding 통로다. ***옛 데이터 호환은 보장을 끄는 값이 아니다.***
    """
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT nonce, commit_hash, beacon_round, participants, pool_ids, "
        "       participants_hash, pool_hash "
        "FROM sales_draw_commitments WHERE scope=:s AND ref_id=:r"),
        {"s": scope, "r": str(ref_id)})).first()
    if not row:
        raise ValueError(
            "추첨 공약이 없습니다 — 추첨 전에 공약을 게시해야 합니다"
            "(사전 공약 없는 추첨은 재추첨을 막을 수 없습니다)"
        )
    nonce, commit_hash = str(row[0]), str(row[1])
    if not vrng.verify_commitment(nonce, commit_hash):
        raise ValueError("추첨 공약이 일치하지 않습니다 — 저장된 nonce 가 공약과 다릅니다")
    participants = list(row[3] or [])
    pool_ids = list(row[4] or [])
    if not participants or not pool_ids:
        raise ValueError(
            "이 공약은 **명부·대상 세대를 묶고 있지 않습니다**(옛 형식) — 다시 공약해야 합니다. "
            "묶지 않은 공약으로 뽑으면 공약 이후에 명부·세대를 바꿔 결과를 고를 수 있습니다"
        )
    # ★저장된 전문으로 지문을 **다시 계산해** 저장된 지문과 대조한다 — 둘 중 하나만 바꾼
    #   DB 쓰기를 잡는다(둘 다 바꾸는 상대는 못 잡는다 · 아래 「남은 한계」).
    p_hash, u_hash = binding.roster_hash(participants), binding.pool_hash(pool_ids)
    if str(row[5] or "") != p_hash or str(row[6] or "") != u_hash:
        raise ValueError(
            "공약의 명부·세대 지문이 저장된 전문과 다릅니다 — 공약이 변조됐을 수 있습니다"
        )
    # ★`revealed_at` 은 **아무도 쓰지 않는 칸이었다**(공개 API 가 항상 `null` 을 돌려줬다).
    #   그 칸이 있어야 *"공약이 추첨보다 앞섰다"* 를 시각으로 말할 수 있다. **첫 공개 때만** 찍는다
    #   (재시도·경합으로 시각이 뒤로 밀리면 그 자체가 증거를 흐린다).
    await db.execute(text(
        "UPDATE sales_draw_commitments SET revealed_at=COALESCE(revealed_at, now()) "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})
    return Revealed(nonce, commit_hash,
                    int(row[2]) if row[2] is not None else None,
                    participants, pool_ids, p_hash, u_hash)


async def public_commitment(db: AsyncSession, scope: str, ref_id) -> dict[str, Any] | None:
    """공개용 조회 — **`commit_hash` 와 시각만**. nonce 는 절대 싣지 않는다."""
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT commit_hash, committed_at, revealed_at, beacon_round, "
        "       participants_hash, pool_hash, participants, pool_ids FROM sales_draw_commitments "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})).first()
    if not row:
        return None
    return {"commit_hash": str(row[0]), "committed_at": str(row[1]),
            "revealed_at": str(row[2]) if row[2] else None,
            # ★비콘 라운드·지문은 **공개 대상**이다 — 이것이 없으면 제3자가 재현할 수 없다.
            "beacon_round": int(row[3]) if row[3] is not None else None,
            "participants_hash": str(row[4]) if row[4] else None,
            "pool_hash": str(row[5]) if row[5] else None,
            "participants_count": len(row[6] or []),
            "pool_size": len(row[7] or [])}
