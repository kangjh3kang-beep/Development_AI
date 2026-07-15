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


# Celery 태스크 등록(앱이 있을 때만; 미설치 환경에서도 함수는 직접 호출 가능).
_celery_app = _get_celery_app()
if _celery_app is not None:
    anonymize_withdrawn_accounts = _celery_app.task(
        name="app.tasks.member_tasks.anonymize_withdrawn_accounts"
    )(anonymize_withdrawn_accounts)
