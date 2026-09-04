"""나라장터(G2B) 입찰 데이터 동기화 스케줄러.

arq 기반 비동기 작업으로 나라장터 API에서 데이터를 주기적으로 수집/갱신한다.
- 매 2시간: 신규 입찰 공고 수집 (공사+용역+물품)
- 매일 06:00 KST: 낙찰 결과 업데이트
- 매주 월요일: 낙찰가율 통계 재집계
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _get_service_key() -> str:
    """G2B 서비스 키를 환경변수 → settings(MOLIT 폴백) 순으로 해석한다."""
    key = os.getenv("G2B_SERVICE_KEY")
    if key:
        return key
    try:
        from app.core.config import settings
        return settings.G2B_SERVICE_KEY or ""
    except Exception:
        return ""


async def sync_bid_notices(ctx: dict) -> dict:
    """신규 입찰 공고를 수집하여 DB에 저장한다."""
    service_key = _get_service_key()
    if not service_key:
        logger.warning("G2B 서비스 키가 설정되지 않았습니다. 동기화를 건너뜁니다.")
        return {"status": "skipped", "reason": "missing_service_key"}

    from app.core.database import async_session_factory
    from app.integrations.g2b_client import G2BClient
    from app.services.g2b_bid_service import G2BBidService

    client = G2BClient(service_key=service_key)
    try:
        # 최근 48시간 공고 수집
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(hours=48)
        start_str = start_dt.strftime("%Y%m%d%H%M")
        end_str = end_dt.strftime("%Y%m%d%H%M")

        raw_items = await client.fetch_all_bid_notices(
            start_date=start_str, end_date=end_str
        )
        logger.info("G2B API에서 총 %d건의 입찰 공고를 수집했습니다.", len(raw_items))

        async with async_session_factory() as db:
            service = G2BBidService(db)
            saved = await service.upsert_bid_notices(raw_items)

        return {"status": "ok", "fetched": len(raw_items), "saved": saved}
    finally:
        await client.close()


async def sync_award_results(ctx: dict) -> dict:
    """낙찰 결과를 수집하여 기존 입찰 공고 레코드를 갱신한다."""
    service_key = _get_service_key()
    if not service_key:
        return {"status": "skipped", "reason": "missing_service_key"}

    from app.core.database import async_session_factory
    from app.integrations.g2b_client import G2BClient
    from app.services.g2b_bid_service import G2BBidService

    client = G2BClient(service_key=service_key)
    try:
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=7)

        raw_items = await client.fetch_all_award_results(
            start_date=start_dt.strftime("%Y%m%d%H%M"),
            end_date=end_dt.strftime("%Y%m%d%H%M"),
        )
        logger.info("G2B API에서 총 %d건의 낙찰 결과를 수집했습니다.", len(raw_items))

        async with async_session_factory() as db:
            service = G2BBidService(db)
            updated = await service.update_award_results(raw_items)

        return {"status": "ok", "fetched": len(raw_items), "updated": updated}
    finally:
        await client.close()


async def rebuild_award_stats(ctx: dict) -> dict:
    """낙찰가율 통계를 재집계한다."""
    from sqlalchemy import and_, delete, func, select, text

    from app.core.database import async_session_factory
    from app.models.g2b_bid import G2BAwardStat, G2BBid

    async with async_session_factory() as db:
        # 최근 12개월 데이터 집계
        twelve_months_ago = datetime.utcnow() - timedelta(days=365)

        query = (
            select(
                func.to_char(G2BBid.award_dt, text("'YYYY-MM'")).label("period"),
                G2BBid.bid_type,
                G2BBid.region_sido,
                func.avg(G2BBid.award_rate).label("avg_rate"),
                func.min(G2BBid.award_rate).label("min_rate"),
                func.max(G2BBid.award_rate).label("max_rate"),
                func.count().label("cnt"),
                func.avg(G2BBid.bid_count).label("avg_comp"),
            )
            .where(
                and_(
                    G2BBid.award_rate.isnot(None),
                    G2BBid.award_dt >= twelve_months_ago,
                )
            )
            .group_by(
                func.to_char(G2BBid.award_dt, text("'YYYY-MM'")),
                G2BBid.bid_type,
                G2BBid.region_sido,
            )
        )

        result = await db.execute(query)
        rows = result.all()
        count = 0

        # 전체 재집계이므로 기존 통계를 먼저 비운다.
        # (테이블에 UNIQUE 제약이 없어 미삭제 시 매 실행마다 동일 기간 통계가
        #  중복 누적되어 get_award_stats 평균이 왜곡된다.)
        await db.execute(delete(G2BAwardStat))

        for row in rows:
            stat = G2BAwardStat(
                stat_period=row.period,
                bid_type=row.bid_type,
                region_sido=row.region_sido,
                avg_award_rate=float(row.avg_rate) if row.avg_rate else None,
                min_award_rate=float(row.min_rate) if row.min_rate else None,
                max_award_rate=float(row.max_rate) if row.max_rate else None,
                bid_count=int(row.cnt),
                avg_competition_ratio=float(row.avg_comp) if row.avg_comp else None,
            )
            db.add(stat)
            count += 1

        await db.commit()
        logger.info("G2B 낙찰가율 통계 %d건 재집계 완료", count)
        return {"status": "ok", "stats_count": count}


async def sync_public_material_prices(ctx: dict) -> dict:
    """조달청 가격정보(등록 전 분야)를 T1 공공단가 계층으로 주기 주입한다(멱등).

    실제 수집·정규화·upsert는 public_price_ingest(단가 4계층 T1 통로)에 위임한다 —
    T2 표준품셈 행과 별개 네임스페이스(PUB-*)라 기존 단가를 덮어쓰지 않는다.
    키 미설정 시 ingest가 0건·정직 사유를 반환한다(graceful).
    """
    from app.core.database import async_session_factory
    from app.services.cost.public_price_ingest import ingest_public_prices

    try:
        async with async_session_factory() as db:
            result = await ingest_public_prices(db, max_pages=10, num_rows=100)
            logger.info("T1 공공단가 주기 주입 완료: %s", result)
            return result
    except Exception as e:
        logger.exception("T1 공공단가 주기 주입 중 오류")
        return {"ok": False, "reason": str(e)}
