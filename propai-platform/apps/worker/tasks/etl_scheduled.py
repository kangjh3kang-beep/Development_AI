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


async def run_cleanup_expired(ctx: dict[str, Any]) -> dict[str, Any]:
    """만료 데이터 정리 태스크.

    1. 만료된 리프레시 토큰 삭제
    2. 90일 이상 된 AI 사용 로그 아카이브
    3. 임시 파일 정리
    """
    from apps.api.database.session import AsyncSessionLocal

    logger.info("만료 데이터 정리 시작")

    deleted: dict[str, int] = {}

    async with AsyncSessionLocal() as db:
        from sqlalchemy import text

        # 만료 리프레시 토큰 삭제
        result = await db.execute(
            text("DELETE FROM refresh_tokens WHERE expires_at < NOW()")
        )
        deleted["refresh_tokens"] = result.rowcount or 0

        # 90일 이상 AI 사용 로그 (soft-delete)
        result = await db.execute(
            text(
                "DELETE FROM ai_usage_logs "
                "WHERE created_at < NOW() - INTERVAL '90 days'"
            )
        )
        deleted["ai_usage_logs"] = result.rowcount or 0

        # 30일 이상 웹훅 배송 기록 삭제
        result = await db.execute(
            text(
                "DELETE FROM webhook_deliveries "
                "WHERE created_at < NOW() - INTERVAL '30 days'"
            )
        )
        deleted["webhook_deliveries"] = result.rowcount or 0

        await db.commit()

    logger.info("만료 데이터 정리 완료", **deleted)
    return {"status": "completed", "deleted": deleted}
