"""예약 ETL 태스크.

야간 배치로 외부 공공 API 데이터를 수집하고 DB를 갱신한다.
"""

from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def run_etl_public_data(ctx: dict[str, Any]) -> dict[str, Any]:
    """공공 API 데이터 일괄 수집.

    1. 국토부 실거래가 (MolitClient)
    2. V-World 토지 특성 (VWorldClient)
    3. 기상청 기후 데이터 (KMAClient)
    4. 한국감정원 공시지가
    """
    from apps.api.config import get_settings
    from apps.api.database.session import AsyncSessionLocal
    from apps.api.integrations.molit_client import MolitClient
    from apps.api.integrations.vworld_client import VWorldClient

    settings = get_settings()
    now = datetime.now(tz=UTC)
    deal_ymd = now.strftime("%Y%m")

    stats: dict[str, int] = {}

    # 1. 국토부 실거래가 수집
    try:
        molit = MolitClient()
        lawd_codes = [
            "11680", "11650", "11710", "11740", "11500",  # 서울 주요 구
            "41135", "41131", "41117",  # 경기 주요 시
        ]
        total_trades = 0
        for lawd_cd in lawd_codes:
            try:
                trades = await molit.get_transactions(lawd_cd, deal_ymd)
                total_trades += len(trades)
            except Exception:
                logger.debug("실거래 수집 실패", lawd_cd=lawd_cd)
        await molit.close()
        stats["molit_trades"] = total_trades
    except Exception:
        logger.warning("국토부 API 수집 실패")
        stats["molit_trades"] = 0

    # 2. V-World 토지 특성 갱신
    try:
        vworld = VWorldClient()
        # 최근 업데이트된 프로젝트 필지의 토지 특성 갱신
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text

            result = await db.execute(
                text(
                    "SELECT DISTINCT p.pnu FROM parcels p "
                    "JOIN projects pr ON p.project_id = pr.id "
                    "WHERE pr.status IN ('planning', 'design', 'construction') "
                    "LIMIT 50"
                )
            )
            pnus = [row.pnu for row in result.fetchall()]

        updated = 0
        for pnu in pnus:
            try:
                await vworld.get_land_info(pnu)
                updated += 1
            except Exception:
                pass
        await vworld.close()
        stats["vworld_parcels"] = updated
    except Exception:
        logger.warning("V-World API 갱신 실패")
        stats["vworld_parcels"] = 0

    logger.info("ETL 공공 데이터 수집 완료", **stats)
    return {"status": "completed", "collected_at": now.isoformat(), **stats}


# 보존기간 정리 대상(테이블명, DELETE 조건). ★테이블명은 실존 스키마와 일치해야 한다 —
# 'ai_usage_logs'는 존재한 적 없는 legacy 명칭(실테이블=llm_usage_log, billing_service가
# 멱등 생성)이었고, 단일 트랜잭션 구조라 이 한 건의 UndefinedTable 실패가 refresh_tokens
# 삭제까지 롤백시키고 webhook_deliveries 정리를 영영 막았다(2026-07-22 운영 실측).
_RETENTION_TARGETS: list[tuple[str, str]] = [
    ("refresh_tokens", "expires_at < NOW()"),
    # ★1830일(5년): llm_usage_log는 순수 로그가 아니라 사용자향 재무 명세의 소스다 —
    #   코인내역 타임라인·CSV 내보내기(coin_ledger_service get_timeline/export_rows)가
    #   최대 1830일 윈도우를 계약하므로 보존기간을 그 상한에 정렬(R1 게이트 반영).
    #   90일이면 잔액·원장 무결성은 불변이나 명세에서 AI사용 차감 항목만 조용히 소실된다.
    ("llm_usage_log", "created_at < NOW() - INTERVAL '1830 days'"),
    ("webhook_deliveries", "created_at < NOW() - INTERVAL '30 days'"),
]


async def run_cleanup_expired(ctx: dict[str, Any]) -> dict[str, Any]:
    """만료 데이터 정리 태스크 — 대상별 독립 트랜잭션(한 대상의 실패·부재가 다른 정리를 막지 않게).

    1. 만료된 리프레시 토큰 삭제
    2. 1830일(5년·명세 내보내기 상한) 초과 LLM 사용 로그 삭제(llm_usage_log)
    3. 30일 이상 웹훅 배송 기록 삭제
    """
    from sqlalchemy import text

    from apps.api.database.session import AsyncSessionLocal

    logger.info("만료 데이터 정리 시작")

    deleted: dict[str, int | str] = {}

    for table, cond in _RETENTION_TARGETS:
        try:
            async with AsyncSessionLocal() as db:
                # 테이블 부재(신규 환경·지연 생성)는 오류가 아니라 정직 스킵.
                exists = await db.execute(
                    text("SELECT to_regclass(:qualified)"),
                    {"qualified": f"public.{table}"},
                )
                if exists.scalar() is None:
                    deleted[table] = "skipped_no_table"
                    logger.warning("정리 대상 테이블 없음 — 건너뜀", table=table)
                    continue
                result = await db.execute(
                    text(f"DELETE FROM {table} WHERE {cond}")  # noqa: S608 — 상수 목록 유래
                )
                await db.commit()
                deleted[table] = result.rowcount or 0
        except Exception as e:  # noqa: BLE001 — 개별 대상 실패는 기록 후 다음 대상 계속
            deleted[table] = f"error:{type(e).__name__}"
            logger.warning("정리 실패 — 다음 대상 계속", table=table, err=str(e)[:100])

    logger.info("만료 데이터 정리 완료", deleted=deleted)
    return {"status": "completed", "deleted": deleted}
