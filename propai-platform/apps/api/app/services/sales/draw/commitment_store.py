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

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.draw import beacon, vrng

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

    "  UNIQUE (scope, ref_id)"               # ★재공약 불가 — 이것이 grinding 을 막는 축이다
    ")"
)


async def _ensure(db: AsyncSession) -> None:
    await db.execute(text(_DDL))
    # Phase 0 에서 만들어진 테이블에는 이 컬럼이 없다 — 기존 배포를 깨지 않고 올린다.
    await db.execute(text(
        "ALTER TABLE sales_draw_commitments ADD COLUMN IF NOT EXISTS beacon_round bigint"))


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


async def commit_draw(db: AsyncSession, site_id, scope: str, ref_id, *, by=None,
                      beacon_round: int | None = None, fetch=None) -> dict[str, Any]:
    """공약을 **한 번만** 게시한다. 이미 있으면 **거부**(재공약 불가).

    ★nonce 는 **서버가 만든다** — 호출자가 넣으면 그것을 고를 수 있다(이 PR 이 없앤 `body.seed`
      와 같은 결함이 자리만 옮기는 것이다).
    ★**비콘 라운드를 함께 못 박는다.** 인자를 주지 않으면 `beacon.target_round()` 로 **미래**
      라운드를 잡고, 비콘을 못 가져오면 **공약 자체를 거부**한다(fail-closed).
      ***「비콘을 쓴다」고 말해 놓고 라운드 없이 공약을 남기면 그게 곧 조용한 우회로다.***
    ★`beacon_round` 를 직접 주면 **미래인지 검사**한다 — 과거·현재 라운드는 **이미 공개된 값**이라
      공약 시점에 결과를 계산할 수 있게 된다(= 공약이 무의미해진다).
    반환에는 **nonce 를 싣지 않는다.**
    """
    import secrets

    await _ensure(db)
    dup = (await db.execute(text(
        "SELECT commit_hash, committed_at FROM sales_draw_commitments "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})).first()
    if dup:
        raise ValueError(
            f"이미 공약이 게시돼 있습니다(게시 {dup[1]}) — 재공약은 허용되지 않습니다. "
            "다시 뽑고 싶다면 추첨을 취소·재오픈하는 별도 절차를 쓰십시오"
        )
    if beacon_round is None:
        beacon_round = beacon.target_round(fetch=fetch)      # 실패하면 BeaconError → 공약 거부
    else:
        latest = beacon.latest_round(fetch=fetch)
        if int(beacon_round) <= latest:
            raise ValueError(
                f"비콘 라운드 {beacon_round} 는 이미 공개된 값입니다(현재 {latest}) — "
                "공약에는 **아직 세상에 없는 미래 라운드**만 쓸 수 있습니다"
            )
    nonce = secrets.token_hex(32)          # 32바이트 — `vrng.is_strong_nonce` 하한과 같은 축
    commit_hash = vrng.commitment(nonce)
    await db.execute(text(
        "INSERT INTO sales_draw_commitments (site_id, scope, ref_id, commit_hash, nonce, committed_by, beacon_round) "
        "VALUES (:site,:s,:r,:c,:n,:by,:br)"),
        {"site": str(site_id), "s": scope, "r": str(ref_id),
         "c": commit_hash, "n": nonce, "by": str(by) if by else None,
         "br": int(beacon_round)})
    await db.commit()
    # ★공개 반환에 nonce 가 없다 — 있으면 이 모듈의 존재 이유가 사라진다.
    #   반대로 `beacon_round` 는 **공개해야** 한다: 검증자가 같은 라운드를 직접 조회해 재현한다.
    return {"scope": scope, "ref_id": str(ref_id), "commit_hash": commit_hash,
            "beacon_round": int(beacon_round),
            "beacon_available_in_s": beacon.seconds_until(int(beacon_round), fetch=fetch)}


async def reveal_commitment(db: AsyncSession, scope: str, ref_id) -> Revealed:
    """추첨 시점에 **서버 내부에서만** 공약을 꺼낸다.

    공약이 없으면 예외 — ***공약 없는 추첨은 하지 않는다(fail-closed).***
    ★종전 이름은 `reveal_nonce` 였고 2-튜플을 돌려줬다. 비콘 라운드를 추가하면서 **이름을 바꿨다** —
      자세한 이유는 `Revealed` 독스트링.
    """
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT nonce, commit_hash, beacon_round FROM sales_draw_commitments "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})).first()
    if not row:
        raise ValueError(
            "추첨 공약이 없습니다 — 추첨 전에 공약을 게시해야 합니다"
            "(사전 공약 없는 추첨은 재추첨을 막을 수 없습니다)"
        )
    nonce, commit_hash = str(row[0]), str(row[1])
    if not vrng.verify_commitment(nonce, commit_hash):
        raise ValueError("추첨 공약이 일치하지 않습니다 — 저장된 nonce 가 공약과 다릅니다")
    # ★`revealed_at` 은 **아무도 쓰지 않는 칸이었다**(생산자 0 — 공개 API 가 항상 `null` 을 돌려줬다).
    #   그 칸이 있어야 *"공약이 추첨보다 앞섰다"* 를 시각으로 말할 수 있다. **첫 공개 때만** 찍는다
    #   (`COALESCE` — 재시도·경합으로 시각이 뒤로 밀리면 그 자체가 증거를 흐린다).
    await db.execute(text(
        "UPDATE sales_draw_commitments SET revealed_at=COALESCE(revealed_at, now()) "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})
    return Revealed(nonce, commit_hash, int(row[2]) if row[2] is not None else None)


async def public_commitment(db: AsyncSession, scope: str, ref_id) -> dict[str, Any] | None:
    """공개용 조회 — **`commit_hash` 와 시각만**. nonce 는 절대 싣지 않는다."""
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT commit_hash, committed_at, revealed_at, beacon_round FROM sales_draw_commitments "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})).first()
    if not row:
        return None
    return {"commit_hash": str(row[0]), "committed_at": str(row[1]),
            "revealed_at": str(row[2]) if row[2] else None,
            # ★비콘 라운드는 **공개 대상**이다 — 이것이 없으면 제3자가 재현할 수 없다.
            "beacon_round": int(row[3]) if row[3] is not None else None}
