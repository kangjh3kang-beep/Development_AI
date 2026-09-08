"""상태 전이를 **원자적으로** 한다 — 읽고-판정하고-쓰는 사이에 남이 끼어들지 못하게.

## 왜 (2026-09-09 · 적대 리뷰 B-1)

승인 경로 둘이 전부 이렇게 돼 있었다:

    row = SELECT status ... WHERE id = :i        # ← 읽고
    if row.status != 'pending': raise 409        # ← 판정하고
    UPDATE ... SET status = :st WHERE id = :i    # ← **조건 없이** 쓴다

**실패 시나리오**: 같은 현장의 본부장과 팀장이 대기열에서 같은 신청을 동시에 승인한다.
둘 다 `pending` 을 읽고, 둘 다 판정을 통과하고, 둘 다 UPDATE 하고, 둘 다 멤버십 연결로 들어간다.
멤버십 쪽의 «이미 멤버?» 조회도 둘 다 빈 결과를 본다 ⇒ **`create_node` 가 두 번 실행된다.**

`sales_org_nodes` 에 `(site_id, user_id)` UNIQUE 가 **없다** — 저장소가 그 사실을 명문으로
적어 뒀다(`app/api/deps_sales.py:41`). 그래서 한 사람이 **두 개의 서로 다른 조상 체인**에
동시에 소속되고, 수수료 배분(`commission/engine.py` 가 `chain[0]` 을 본다)이 어느 체인을
타는지가 우선순위 동률 파괴에 좌우된다. **어떤 오류도 안 난다 — 조용하다.**

★정답 패턴은 이미 저장소 안에 있었다: `site_join.cancel_join_request` 가
`WHERE id AND user_id AND status='pending' RETURNING id` 로 원자적이었다.
**전이 3건 중 1건만** 그랬다 — 그래서 한 곳을 고치는 대신 **공용 함수로 뽑는다.**

## 왜 「pending 고정」이 아니라 CAS 인가

`market.decide_application` 은 **거절 → 수락** 재결정을 허용한다(멱등 검사만 있다).
전이 조건을 `status='pending'` 으로 못 박으면 그 정당한 경로가 **409 로 죽는다** —
정상 사용을 막는 가드는 그 자체가 결함이다. 그래서 **읽은 값 그대로**를 조건에 싣는다
(compare-and-swap): 의미는 그대로 두고 **경쟁만** 없앤다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ★테이블 이름은 SQL 에 **문자열로** 들어가므로 화이트리스트로 가둔다.
#   («위험을 열거» 하지 않고 **«허용된 모양»** 을 요구하는 형태 — 저장소가 반복해 배운 방향.)
_TRANSITIONABLE = frozenset({"job_applications", "sales_site_join_requests"})


async def claim_status_transition(
    db: AsyncSession,
    table: str,
    row_id,
    expected_status: str,
    new_status: str,
    extra_set: str = "",
    params: dict | None = None,
) -> bool:
    """`expected_status` 가 **아직 그대로일 때만** `new_status` 로 바꾼다.

    반환 `True` = 내가 바꿨다(이 요청이 전이의 주인이다).
    반환 `False` = **남이 먼저 바꿨다** — 호출부는 부작용(멤버십 생성 등)을 **하면 안 된다.**

    `extra_set` 은 `", decided_by = :by, decided_at = now()"` 처럼 **앞에 쉼표를 포함한** 추가
    대입절이다. 값은 전부 `params` 로 바인딩한다(문자열 보간 금지).
    """
    if table not in _TRANSITIONABLE:
        # 화이트리스트 밖은 **거부**한다(fail-closed) — 이 값은 SQL 에 문자열로 들어간다.
        raise ValueError(f"전이 대상 테이블이 아닙니다: {table!r}")

    sql = (
        f"UPDATE {table} SET status = :__new{extra_set}, updated_at = now() "
        "WHERE id = :__id AND status = :__expected RETURNING id"
    )
    bind = dict(params or {})
    bind.update(__new=new_status, __id=str(row_id), __expected=expected_status)
    row = (await db.execute(text(sql), bind)).first()
    return row is not None
