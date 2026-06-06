"""경·공매 전국 동기화 태스크 — 무목업(온비드 공매 + 법원경매 스크래핑).

Celery beat 스케줄로 주기 실행되어 ① 온비드 공매(실 API) ② 법원경매(스크래핑)를
전국 시/도 배치로 auction_items에 멱등 upsert한다.

★정직(무목업): 키 미설정/호출실패/스크래핑 불가 시 가짜데이터 없이 빈 결과로 흡수한다
(data_source=unavailable). ★예의: 소스별로 분리 수집하고, 법원경매는 지연(court_scraper의
delay)에 더해 시/도 배치 사이에도 추가 sleep을 둬 서버부하·IP차단을 방지한다.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# 전국 시/도(배치 단위).
_SIDO_LIST = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

# 시/도 배치 사이 지연(초). 법원경매 스크래핑 예의(서버부하 방지)용 추가 sleep.
_COURT_REGION_DELAY_SEC = 2.0


def _resolve_service_key() -> str | None:
    """온비드 키: 환경변수 → settings(공용키 폴백) 순. 없으면 None(=unavailable)."""
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
    """온비드(공매)·법원경매(스크래핑)를 소스별로 분리 수집한다."""
    from app.core.database import async_session_factory
    from app.services.auction.auction_service import AuctionStep1Service

    service_key = _resolve_service_key()
    onbid_saved = 0
    court_saved = 0
    onbid_source = "unavailable"
    court_source = "unavailable"

    async with async_session_factory() as db:
        service = AuctionStep1Service(db)

        # ① 온비드 공매(실 API, 무목업).
        for sido in _SIDO_LIST:
            try:
                res = await service.sync_region(
                    service_key=service_key, region=sido, rows=100, source="onbid",
                )
                onbid_saved += int(res.get("saved", 0))
                onbid_source = res.get("data_source", onbid_source)
            except Exception as e:  # noqa: BLE001
                logger.warning("온비드 동기화 실패(%s): %s", sido, str(e)[:120])

        # ② 법원경매(스크래핑, 지연·예의). 시/도 사이 추가 sleep으로 부하 분산.
        for sido in _SIDO_LIST:
            try:
                res = await service.sync_region(
                    service_key=None, region=sido, source="court",
                )
                court_saved += int(res.get("saved", 0))
                court_source = res.get("data_source", court_source)
            except Exception as e:  # noqa: BLE001
                logger.warning("법원경매 스크래핑 실패(%s): %s", sido, str(e)[:120])
            time.sleep(_COURT_REGION_DELAY_SEC)  # ★시/도 배치 사이 예의 지연.

    logger.info(
        "경공매 동기화 완료: 온비드 %d건(%s) / 법원경매 %d건(%s)",
        onbid_saved, onbid_source, court_saved, court_source,
    )
    return {
        "status": "ok",
        "onbid": {"saved": onbid_saved, "data_source": onbid_source},
        "court": {"saved": court_saved, "data_source": court_source},
    }


def sync_onbid_auctions() -> dict:
    """경공매 전국 동기화(Celery 진입점). 매일 04:00 실행(beat_schedule)."""
    return asyncio.run(_sync_all_regions())
