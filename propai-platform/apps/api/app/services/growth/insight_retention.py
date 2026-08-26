"""성장 인사이트 **정리** — 승계된 옛 행을 닫는다.

## 왜 (라이브 실측 2026-08-26 · 활성 컨테이너)

`platform_insights` 에 **정리 경로가 하나도 없다.**

    status 분포        open **3,127** / acknowledged **16**
    expired·superseded **0**            ← 닫는 길이 아예 없다
    latency_regression open 2,298 중 **30일 초과 1,212건**

그래서 같은 지표가 매 실행마다 새 행으로 쌓이고 **옛 행이 영원히 열려 있다.**
화면의 「열린 인사이트」가 **재고**를 세므로, 오늘 실제로 봐야 할 것이 묻힌다.

    ★같은 키에 더 새 행이 있는 옛 행(= 승계됨) = 전 타입 **2,678**
      승계분만 닫으면 open **3,127 → 449** (86% 감소)

## ★보드 진단을 실측으로 정정했다

보드(2026-08-26 16:42)는 *"`content_hash` 무변화 단락이 소음의 본체를 유입에서 끊는다"*
고 적었다. **재보니 아니다** — 최근 24시간 `latency_regression` 유입 **24건**, 내용 기준
**중복 0건(0%)**. 대조군으로 다른 타입도 전부 중복 0. **무변화 재삽입은 일어나지 않는다.**
본체는 **유입 중복이 아니라 닫히지 않는 재고**다.

## 설계 — 무엇을 하지 **않는가**가 더 중요하다

- **삭제하지 않는다.** `status` 를 `superseded` 로 전이한다(감사·추적 보존).
- **`acknowledged`·`dismissed` 는 건드리지 않는다.** 사람이 이미 판단한 것이다.
- **키별 최신 1건은 반드시 남긴다.** 정리 후에도 *"지금 이 지표가 어떻다"* 는 항상 열려 있다.
- **정체 필드가 선언되지 않은 타입은 손대지 않는다**(`IDENTITY_FIELD` 의 `None`).
  `heal_escalation`(critical·사람 점검) 같은 것을 기계가 닫으면 안 된다.
- **멱등** — 두 번 돌려도 두 번째는 0건이다.
- **상한** — 한 번에 `limit` 행까지만. 큰 재고를 한 트랜잭션에 밀어 넣지 않는다.

★`superseded` 로 전이하면 `ack_insight` 의 허용 전이(`open|acknowledged`)에서 빠져
  **사람이 더 이상 처리할 수 없다.** 그것이 의도다 — 승계된 행은 정의상 **더 새 행이
  같은 대상을 말하고 있고**, 그 새 행은 열려 있다.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.growth.insight_types import IDENTITY_FIELD

logger = logging.getLogger(__name__)

#: 한 번에 전이할 최대 행 수 — 재고가 커도 한 트랜잭션을 붓지 않는다.
DEFAULT_LIMIT = 5000

#: 전이 목표 상태. `ack_insight` 의 허용 전이 밖이라 사람이 재처리할 수 없다(의도).
SUPERSEDED = "superseded"


def cleanable_types() -> dict[str, str]:
    """정체 필드가 **선언된** 타입만. `None` 선언은 *"정리하지 않는다"* 는 뜻이다."""
    return {t: f for t, f in IDENTITY_FIELD.items() if f}


#: 키별 최신 1건을 남기고 나머지 `open` 행을 고른다.
#: ★`insight_type` 과 정체 필드를 **파라미터로** 받는다 — SQL 에 타입명을 박으면
#:   새 타입이 자동으로 누락된다(이 저장소가 반복해 데인 형태).
_SELECT_SUPERSEDED = """
WITH ranked AS (
  SELECT id,
         row_number() OVER (
           PARTITION BY insight_type, metrics_json->>:field
           ORDER BY created_at DESC, id DESC
         ) AS rn
  FROM platform_insights
  WHERE status = 'open'
    AND insight_type = :itype
    AND metrics_json ? :field
)
SELECT id FROM ranked WHERE rn > 1 LIMIT :limit
"""


async def supersede_stale_insights(
    db: Any, *, limit: int = DEFAULT_LIMIT, dry_run: bool = False
) -> dict[str, Any]:
    """승계된 옛 `open` 행을 `superseded` 로 전이한다.

    Returns:
        `{"scanned_types": int, "superseded": int, "by_type": {...}, "dry_run": bool}`
    """
    from sqlalchemy import text

    types = cleanable_types()
    if not types:
        # ★조용한 0건 금지 — 카탈로그가 비면 그것은 "정리할 게 없다"가 아니라 결함이다.
        raise RuntimeError(
            "정리 대상 타입이 0건 — IDENTITY_FIELD 가 비었거나 전부 None 이다. "
            "카탈로그를 확인하라(조용한 무동작 금지)."
        )

    by_type: dict[str, int] = {}
    remaining = limit
    for itype, field in sorted(types.items()):
        if remaining <= 0:
            break
        ids = [r[0] for r in (await db.execute(
            text(_SELECT_SUPERSEDED),
            {"itype": itype, "field": field, "limit": remaining},
        )).fetchall()]
        if not ids:
            continue
        by_type[itype] = len(ids)
        remaining -= len(ids)
        if dry_run:
            continue
        # ★`status='open'` 을 UPDATE 조건에 **다시** 건다 — 조회와 갱신 사이에
        #   사람이 ack 했을 수 있다(그 판단을 덮어쓰지 않는다).
        await db.execute(
            text("UPDATE platform_insights SET status = :st "
                 "WHERE id = ANY(:ids) AND status = 'open'"),
            {"st": SUPERSEDED, "ids": ids},
        )

    if not dry_run and by_type:
        await db.commit()

    total = sum(by_type.values())
    logger.info(
        "성장 인사이트 정리%s: 타입 %d개 · 승계 전이 %d건 %s",
        "(모의)" if dry_run else "", len(types), total, by_type or "{}",
    )
    return {"scanned_types": len(types), "superseded": total,
            "by_type": by_type, "dry_run": dry_run}
