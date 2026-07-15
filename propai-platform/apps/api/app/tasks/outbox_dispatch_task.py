"""전역 아웃박스 디스패처 — outbox_event 폴링 → at-least-once 발행(P15 A4).

무엇을 하는가: outbox_event 테이블의 **미발행 행**을 배치로 잡아(FOR UPDATE SKIP LOCKED),
등록된 소비처에 전달한다. 성공하면 `published_at` 을 원자적으로 확정(WHERE published_at IS NULL)
하고, 실패하면 attempts+1·백오프 후 다음 폴링에 재시도한다(at-least-once).

정본 스택(★): arq 다(celery 신규 금지 — 계획 규약). 이 코어(`run_outbox_dispatch`)는 arq
워커(apps/worker/main.py 등록)에서 주기 실행되며, arq/Redis 미배포 환경(운영 Micro)에서는
API 프로세스의 인프로세스 루프(main.py, `_growth_flush_loop` 선례와 동형)가 같은 코어를 호출한다.
두 경로가 동시에 돌아도 안전하다 — mark_published 의 원자 가드(1승)와 소비처 멱등이 중복
발행을 1회로 접는다.

best-effort: 어떤 예외도 워커/루프를 죽이지 않는다(로그 후 다음 폴링).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def run_outbox_dispatch(ctx: dict | None = None, limit: int = 200) -> dict[str, Any]:
    """미발행 아웃박스 이벤트를 1배치 발행한다. 반환: 처리 통계.

    처리 절차(행마다):
      1) 소비처 전달(deliver) 성공 → mark_published(원자, 1승만 확정)
      2) 실패 → mark_failed(attempts+1·백오프)
    행 잠금·발행·실패기록을 **한 세션·한 트랜잭션**으로 커밋해 잠금이 즉시 풀리게 한다.
    """
    from app.services.events import outbox_event as ox
    from app.services.events.outbox_consumer import deliver

    stats = {"fetched": 0, "published": 0, "failed": 0}
    try:
        from app.core.database import async_session_factory
    except Exception as e:  # noqa: BLE001
        logger.warning("outbox 디스패처 — 세션 팩토리 로드 실패: %s", str(e)[:120])
        return {**stats, "status": "no_db"}

    try:
        async with async_session_factory() as db:
            rows = await ox.fetch_publishable(db, limit=limit)
            stats["fetched"] = len(rows)
            for row in rows:
                event = dict(row)
                eid = str(event.get("event_id", ""))
                try:
                    ok = await deliver(event)
                except Exception as e:  # noqa: BLE001
                    ok = False
                    logger.warning("outbox deliver 예외(%s): %s", eid[:16], str(e)[:160])
                if ok:
                    n = await ox.mark_published(db, eid)
                    stats["published"] += 1 if n else 0
                else:
                    await ox.mark_failed(db, eid, "deliver_failed")
                    stats["failed"] += 1
            # 잠금 확보(FOR UPDATE)와 발행/실패 갱신을 함께 커밋 → 잠금 해제.
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("outbox 디스패처 배치 실패: %s", str(e)[:160])
        return {**stats, "status": "error"}

    if stats["fetched"]:
        logger.info(
            "outbox 디스패치 — 조회 %d·발행 %d·실패 %d",
            stats["fetched"], stats["published"], stats["failed"],
        )
    return {**stats, "status": "ok"}


async def run_outbox_dispatch_until_empty(
    ctx: dict | None = None, limit: int = 200, max_batches: int = 20
) -> dict[str, Any]:
    """더 이상 발행할 게 없을 때까지(또는 max_batches) 반복 발행한다(캐치업용).

    growth flush 루프가 한 틱에 여러 배치를 드레인하는 선례와 동형. 폭주 방지로 max_batches 상한.
    """
    total = {"fetched": 0, "published": 0, "failed": 0, "batches": 0}
    for _ in range(max(1, int(max_batches))):
        res = await run_outbox_dispatch(ctx, limit=limit)
        total["batches"] += 1
        with contextlib.suppress(Exception):
            total["fetched"] += int(res.get("fetched", 0))
            total["published"] += int(res.get("published", 0))
            total["failed"] += int(res.get("failed", 0))
        if int(res.get("fetched", 0)) < limit:
            break  # 마지막 배치가 limit 미만 → 더 없음.
    return {**total, "status": "ok"}
