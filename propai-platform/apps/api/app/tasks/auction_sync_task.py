"""경·공매(온비드 공매) 전국 동기화 태스크.

Celery beat 스케줄로 주기 실행되어 온비드 공매 물건을 전국 시/도 배치로
auction_items에 멱등 upsert한다. 키 미설정 시 mock 폴백(개발/검증용, 정직 표기).
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# 전국 시/도(배치 단위).
_SIDO_LIST = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]


def _resolve_service_key() -> str | None:
    """온비드 키: 환경변수 → settings(공용키 폴백) 순. 없으면 None(=mock)."""
    import os

    key = os.getenv("ONBID_SERVICE_KEY")
    if key:
        return key
    try:
        from app.core.config import settings

        return getattr(settings, "ONBID_SERVICE_KEY", "") or None
    except Exception:  # noqa: BLE001
        return None


async def _sync_all_regions() -> dict:
    from app.core.database import async_session_factory
    from app.services.auction.auction_service import AuctionStep1Service

    service_key = _resolve_service_key()
    total_saved = 0
    data_source = "mock"
    async with async_session_factory() as db:
        service = AuctionStep1Service(db)
        for sido in _SIDO_LIST:
            try:
                res = await service.sync_region(
                    service_key=service_key, region=sido, rows=100
                )
                total_saved += int(res.get("saved", 0))
                data_source = res.get("data_source", data_source)
            except Exception as e:  # noqa: BLE001
                logger.warning("온비드 동기화 실패(%s): %s", sido, str(e)[:120])
    logger.info("온비드 공매 동기화 완료: %d건 저장(data_source=%s)", total_saved, data_source)
    return {"status": "ok", "saved": total_saved, "data_source": data_source}


def sync_onbid_auctions() -> dict:
    """온비드 공매 전국 동기화(Celery 진입점). 매일 04:00 실행(beat_schedule)."""
    return asyncio.run(_sync_all_regions())
