"""실거래 2층 주기 수집 — **파생된** 시군구만 태운다.

★왜 `etl_scheduled.run_etl_public_data` 에 붙이지 않았나
    그 함수는 시군구 **8개를 하드코딩**한다. 라이브 실측(2026-08-26)에서 그 목록은
    실사용 필지 **394개 중 4개(1.0%)** 만 덮었다. 저장을 거기 붙이면 **99% 가 안 담긴다.**
    → 모집단은 `realtx_store.derive_scan_targets` 가 `user_project_store` 에서 파생한다.

★쿼터
    MOLIT 키는 **G2B 와 같은 키**다(라이브 해시 일치 실측). G2B 는 2시간마다 태우므로
    이 태스크는 **하루 1회**만 돈다. `429/403` 은 **재시도하지 않는다** — 실패를
    "거래 0건"으로 기록하면 *"이 동네는 거래가 없었다"* 는 **거짓 사실**이 만들어진다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

#: 되돌아볼 개월 수 — 정정(해제·등기일자)은 **신고 후 수개월 뒤**에도 붙는다.
#: `rgstDate` 는 라이브 실측 30.2% 만 기재돼 있어, 짧게 잡으면 나머지가 영영 안 채워진다.
DEFAULT_LOOKBACK_MONTHS = 3

#: 유형 — 토지는 지번이 100% 마스킹이지만 **법정동 단위 집계는 유효**하다(`#851` 실측).
DEFAULT_PROP_TYPES = ("apt", "land")


def recent_months(now: datetime, months: int) -> list[str]:
    """`YYYYMM` 목록(최신 우선). `now` 를 인자로 받아 **결정적**으로 만든다."""
    out, cursor = [], now
    for _ in range(max(1, months)):
        out.append(cursor.strftime("%Y%m"))
        cursor = cursor.replace(day=1) - timedelta(days=1)
    return out


async def sync_realtx_trades(ctx: dict[str, Any]) -> dict[str, Any]:
    """파생된 시군구 × 최근 N개월 × 유형을 수집·저장하고 정정을 탐지한다."""
    from app.services.land_intelligence.realtx_store import (
        derive_scan_targets,  # 대상 0건이면 RealtxTargetsEmptyError 를 **전파**한다
        persist_scope,
    )
    from apps.api.database.session import AsyncSessionLocal
    from apps.api.integrations.molit_client import MolitClient

    months = recent_months(datetime.now(tz=UTC), DEFAULT_LOOKBACK_MONTHS)

    async with AsyncSessionLocal() as db:
        # ★★2026-08-26 독립 리뷰 적발 — 종전엔 여기서 예외를 잡아 dict 로 돌려줬다.
        #   `realtx_store` 독스트링은 *"조용히 넘어가지 않고 죽는다"* 고 선언하는데,
        #   **arq 는 정상 반환을 성공으로 기록**하고 이 저장소에 job result 를 읽는
        #   코드가 **0건**이다(실측 · 대조군 arq 임포트 2건). 곧 선언과 동작이 어긋났다.
        #   → **전파한다.** arq 가 실패로 기록하고 재시도한다.
        targets = sorted(await derive_scan_targets(db))

        client = MolitClient()
        stats: dict[str, Any] = {
            "targets": len(targets), "months": len(months),
            # ★`submitted` 로 이름을 바꿨다 — 종전 `stored` 는 **투입 레코드 수**이지
            #   저장된 행 수가 아니다(멱등 upsert 라 기존 행 갱신이 섞인다).
            "submitted": 0, "corrections": 0,
            "fetch_errors": [], "persist_errors": [],
        }
        try:
            for lawd_cd in targets:
                for deal_ym in months:
                    for prop_type in DEFAULT_PROP_TYPES:
                        try:
                            records = await client.get_transactions(lawd_cd, deal_ym, prop_type=prop_type)
                        except Exception as exc:  # noqa: BLE001 — 사유를 실어 계속한다
                            # ★재시도하지 않는다(쿼터를 G2B 와 공유). 사유를 남기고 넘어간다.
                            stats["fetch_errors"].append(
                                {"lawd_cd": lawd_cd, "deal_ym": deal_ym,
                                 "prop_type": prop_type, "error": type(exc).__name__}
                            )
                            continue
                        try:
                            result = await persist_scope(
                                db, lawd_cd=lawd_cd, deal_ym=deal_ym,
                                prop_type=prop_type, records=records,
                            )
                        except Exception as exc:  # noqa: BLE001
                            # ★스코프 하나가 죽어도 나머지를 계속한다. 종전엔 무방비라
                            #   한 건의 DataError 가 **남은 전 시군구·월을 미수집**으로 만들고
                            #   stats 조차 반환되지 않았다. targets 가 정렬돼 있어 잘리는
                            #   부분이 **항상 같은 뒷부분**이라 계통적 손실이었다.
                            logger.error("실거래 저장 실패 lawd=%s ym=%s type=%s: %s",
                                         lawd_cd, deal_ym, prop_type, str(exc)[:200])
                            stats["persist_errors"].append(
                                {"lawd_cd": lawd_cd, "deal_ym": deal_ym,
                                 "prop_type": prop_type, "error": type(exc).__name__})
                            continue
                        stats["submitted"] += result["submitted"]
                        stats["corrections"] += len(result["corrections"])
        finally:
            await client.close()

    stats["status"] = "ok" if not stats["persist_errors"] else "partial"
    logger.info(
        "실거래 2층 수집 %s 시군구=%d 월=%d 투입=%d 정정=%d 조회실패=%d 저장실패=%d",
        stats["status"], stats["targets"], stats["months"], stats["submitted"],
        stats["corrections"], len(stats["fetch_errors"]), len(stats["persist_errors"]),
    )
    return stats
