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
  그 층까지 막으려면 nonce 를 **외부 공개 비콘**에서 끌어오거나(계획서 Phase 1) 별도 비밀
  보관소에 둬야 한다. ***이 모듈은 「운영자 무신뢰」가 아니라 「사후 변조·재공약 불가」까지다.***
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.draw import vrng

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
    "  UNIQUE (scope, ref_id)"               # ★재공약 불가 — 이것이 grinding 을 막는 축이다
    ")"
)


async def _ensure(db: AsyncSession) -> None:
    await db.execute(text(_DDL))


async def commit_draw(db: AsyncSession, site_id, scope: str, ref_id, *, by=None) -> dict[str, Any]:
    """공약을 **한 번만** 게시한다. 이미 있으면 **거부**(재공약 불가).

    ★nonce 는 **서버가 만든다** — 호출자가 넣으면 그것을 고를 수 있다(이 PR 이 없앤 `body.seed`
      와 같은 결함이 자리만 옮기는 것이다).
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
    nonce = secrets.token_hex(32)          # 32바이트 — `vrng.is_strong_nonce` 하한과 같은 축
    commit_hash = vrng.commitment(nonce)
    await db.execute(text(
        "INSERT INTO sales_draw_commitments (site_id, scope, ref_id, commit_hash, nonce, committed_by) "
        "VALUES (:site,:s,:r,:c,:n,:by)"),
        {"site": str(site_id), "s": scope, "r": str(ref_id),
         "c": commit_hash, "n": nonce, "by": str(by) if by else None})
    await db.commit()
    # ★공개 반환에 nonce 가 없다 — 있으면 이 모듈의 존재 이유가 사라진다.
    return {"scope": scope, "ref_id": str(ref_id), "commit_hash": commit_hash}


async def reveal_nonce(db: AsyncSession, scope: str, ref_id) -> tuple[str, str]:
    """추첨 시점에 **서버 내부에서만** nonce 를 꺼낸다. 반환 `(nonce, commit_hash)`.

    공약이 없으면 예외 — ***공약 없는 추첨은 하지 않는다(fail-closed).***
    """
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT nonce, commit_hash FROM sales_draw_commitments "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})).first()
    if not row:
        raise ValueError(
            "추첨 공약이 없습니다 — 추첨 전에 공약을 게시해야 합니다"
            "(사전 공약 없는 추첨은 재추첨을 막을 수 없습니다)"
        )
    nonce, commit_hash = str(row[0]), str(row[1])
    if not vrng.verify_commitment(nonce, commit_hash):
        raise ValueError("추첨 공약이 일치하지 않습니다 — 저장된 nonce 가 공약과 다릅니다")
    return nonce, commit_hash


async def public_commitment(db: AsyncSession, scope: str, ref_id) -> dict[str, Any] | None:
    """공개용 조회 — **`commit_hash` 와 시각만**. nonce 는 절대 싣지 않는다."""
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT commit_hash, committed_at, revealed_at FROM sales_draw_commitments "
        "WHERE scope=:s AND ref_id=:r"), {"s": scope, "r": str(ref_id)})).first()
    if not row:
        return None
    return {"commit_hash": str(row[0]), "committed_at": str(row[1]),
            "revealed_at": str(row[2]) if row[2] else None}
