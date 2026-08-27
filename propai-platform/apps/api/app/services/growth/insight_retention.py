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

from app.services.growth.insight_types import IDENTITY_FIELDS

logger = logging.getLogger(__name__)

#: 한 번에 전이할 최대 행 수 — 재고가 커도 한 트랜잭션을 붓지 않는다.
DEFAULT_LIMIT = 5000

#: 전이 목표 상태. `ack_insight` 의 허용 전이 밖이라 사람이 재처리할 수 없다(의도).
SUPERSEDED = "superseded"


def cleanable_types() -> dict[str, tuple[str, ...]]:
    """정체 필드가 **선언된** 타입만. `None` 선언은 *"정리하지 않는다"* 는 뜻이다."""
    return {t: f for t, f in IDENTITY_FIELDS.items() if f}


#: 최소 유예 — 방금 만들어진 행은 닫지 않는다.
#: ★근거로 든 것은 **나이**("30일 초과 1,212건")인데 규칙은 **승계**다. 규칙 자체는
#:   옳지만(옛 관측은 조치 대상이 아니다), 유예가 없으면 **5분 전 행도 닫는다** —
#:   근거와 구현이 어긋난다(2026-08-27 독립 리뷰 H1). 유예를 둬 둘을 맞춘다.
DEFAULT_MIN_AGE_HOURS = 6

def _build_select(fields: tuple[str, ...]) -> str:
    """정체 필드 **여러 개**로 파티션하는 SQL 을 만든다.

    ★필드 목록을 **선언에서 파생**한다 — SQL 에 타입명이나 필드명을 박으면 새 타입이
      자동으로 누락된다(이 저장소가 반복해 데인 형태).

    ★★`window_end - window_start` 를 파티션에 넣는다(2026-08-27 독립 리뷰 H2).
      `analyze_window` 는 `window_hours` 와 무관하게 6개 분석기를 전부 돌리므로
      **매시(1h) 실행과 매일(24h) 실행이 같은 키로 행을 낸다.** 윈도우 폭이 정체에
      없으면 03:05 시간별 행이 02:30 의 **24시간 추세 행을 매일 닫는다** —
      `celery_app.py` 가 *"일 단위 추세 **누적**"* 이라고 적어 둔 바로 그것을 지운다.

    ★`->>` 가 NULL 인 행은 제외한다 — NULL 은 파티션에서 서로 같게 취급돼
      **정체 없는 행들이 서로를 승계**시킨다(리뷰 L2 · 라이브 실행으로 확인됨).
    """
    parts = ", ".join(f"metrics_json->>'{f}'" for f in fields)
    guards = " AND ".join(
        f"metrics_json ? '{f}' AND metrics_json->>'{f}' IS NOT NULL" for f in fields
    )
    return f"""
WITH ranked AS (
  SELECT id,
         row_number() OVER (
           PARTITION BY insight_type, (window_end - window_start), {parts}
           ORDER BY created_at DESC, id DESC
         ) AS rn
  FROM platform_insights
  WHERE status = 'open'
    AND insight_type = :itype
    AND created_at < now() - make_interval(hours => :min_age_hours)
    AND {guards}
)
SELECT id FROM ranked WHERE rn > 1 ORDER BY id LIMIT :limit
"""


async def supersede_stale_insights(
    db: Any, *, limit: int = DEFAULT_LIMIT, dry_run: bool = False,
    min_age_hours: int = DEFAULT_MIN_AGE_HOURS,
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
    # ★타입별 **균등 배분** — 종전엔 `sorted()` 순회로 알파벳 앞 타입이 상한을 통째로
    #   먹어, 재고의 79% 를 차지하는 `latency_regression` 이 영구 기아가 될 수 있었다
    #   (2026-08-27 독립 리뷰 M2 · 실측 재현).
    per_type = max(1, limit // len(types))
    for itype, fields in sorted(types.items()):
        ids = [r[0] for r in (await db.execute(
            text(_build_select(fields)),
            {"itype": itype, "limit": per_type, "min_age_hours": min_age_hours},
        )).fetchall()]
        if not ids:
            continue
        if dry_run:
            by_type[itype] = len(ids)
            continue
        # ★`status='open'` 을 UPDATE 조건에 **다시** 건다 — 조회와 갱신 사이에
        #   사람이 ack 했을 수 있다(그 판단을 덮어쓰지 않는다).
        res = await db.execute(
            text("UPDATE platform_insights SET status = :st "
                 "WHERE id = ANY(:ids) AND status = 'open'"),
            {"st": SUPERSEDED, "ids": ids},
        )
        # ★**갱신한 행 수**를 센다 — 선택한 수를 세면 위 ack 경합이 곧 반환값을
        #   거짓으로 만든다(리뷰 M1 · 실측: 보고 2 vs 실제 1).
        changed = getattr(res, "rowcount", None)
        by_type[itype] = len(ids) if changed is None else int(changed)

    if not dry_run and by_type:
        await db.commit()

    total = sum(by_type.values())
    logger.info(
        "성장 인사이트 정리%s: 타입 %d개 · 승계 전이 %d건 %s",
        "(모의)" if dry_run else "", len(types), total, by_type or "{}",
    )
    return {"scanned_types": len(types), "superseded": total,
            "by_type": by_type, "dry_run": dry_run,
            "min_age_hours": min_age_hours, "per_type_limit": per_type}
