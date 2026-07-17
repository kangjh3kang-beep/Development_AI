"""회원 수명주기 Celery 태스크 — 탈퇴 30일 유예 경과 계정 익명화(§7-2).

매일 03:30 실행(beat_schedule "anonymize-withdrawn-daily").
Celery 워커는 동기 컨텍스트이므로 asyncio.run 으로 async 서비스를 구동한다
(growth_tasks 와 동일 패턴).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


async def _anonymize_async() -> dict:
    from apps.api.database.session import AsyncSessionLocal
    from apps.api.services.member_lifecycle import anonymize_expired_withdrawals

    async with AsyncSessionLocal() as session:
        return await anonymize_expired_withdrawals(session)


def anonymize_withdrawn_accounts() -> dict:
    """유예 경과 탈퇴 계정 익명화 배치 진입점. 반환: {"scanned": n, "anonymized": n}."""
    import asyncio

    try:
        result = asyncio.run(_anonymize_async())
    except RuntimeError:
        # 이미 이벤트루프가 있는 환경(테스트 등) — 새 루프로 격리 실행
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_anonymize_async())
        finally:
            loop.close()
    logger.info("탈퇴 익명화 배치 완료: %s", result)
    return result


async def _purge_order_pii_async() -> dict:
    from app.services.billing.coin_orders_service import purge_expired_buyer_pii

    return await purge_expired_buyer_pii()


def purge_expired_order_pii() -> dict:
    """전상법 §6 보존기간(5년) 경과 충전주문의 구매자 PII 파기 배치. 반환: {"purged": n}.

    개인정보보호법 §21(보유기간 경과 시 지체 없는 파기) 정합 — 회원 익명화(탈퇴 기준)와
    독립적으로 주문 자체의 법정 보존기간을 근거로 buyer_name/buyer_email을 NULL화한다.
    """
    import asyncio

    try:
        result = asyncio.run(_purge_order_pii_async())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_purge_order_pii_async())
        finally:
            loop.close()
    logger.info("충전주문 PII 파기 배치 완료: %s", result)
    return result


# Celery 태스크 등록(앱이 있을 때만; 미설치 환경에서도 함수는 직접 호출 가능).
_celery_app = _get_celery_app()
if _celery_app is not None:
    anonymize_withdrawn_accounts = _celery_app.task(
        name="app.tasks.member_tasks.anonymize_withdrawn_accounts"
    )(anonymize_withdrawn_accounts)
    purge_expired_order_pii = _celery_app.task(
        name="app.tasks.member_tasks.purge_expired_order_pii"
    )(purge_expired_order_pii)
