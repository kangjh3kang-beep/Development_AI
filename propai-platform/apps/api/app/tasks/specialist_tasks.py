"""성장 뇌 — 종합분석 산출을 도메인 SpecialistAgent로 흘려 회상/원장/자동기억을 발화(Celery).

★소비처 배선(단절① 해소): SpecialistAgent.run() 은 결정론 도구(계층1) → prior read → MemoryHub
recall(2.5) → 원장 cite(4) → 자동 기억저장 ingest(6) 을 수행하지만, 프로덕션 호출처가 없어 한 번도
발화하지 않았다. 종합분석(comprehensive_analysis)이 분석할 때마다 이 태스크를 best-effort 비차단
트리거(.delay)해 데이터가 신뢰 가능한 도메인(far·zoning·market)의 전문가 에이전트를 기동한다.

ledger 어댑터(record_specialist_result·load_prior)는 세션을 자체관리하므로 세션 주입 불필요.
실제 발화는 Celery 워커 가동 의존(deploy-pending) — 미가동 시 .delay 는 큐 적재만/ graceful no-op.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱 지연 임포트(growth_tasks/rate_tasks 선례). 미설치/미생성 시 None."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


_celery = _get_celery_app()


async def _run_specialists_async(payload: dict) -> int:
    """payload['domains'] = {domain: data_dict} 각각 SpecialistAgent.run() 실행. 성공 개수 반환."""
    from app.services.agents.registry import get_specialist

    domains = payload.get("domains") or {}
    if not isinstance(domains, dict):
        return 0
    common = {k: payload.get(k) for k in ("tenant_id", "project_id", "pnu", "address", "created_by")}
    ran = 0
    for domain, data in domains.items():
        try:
            agent = get_specialist(domain)
            await agent.run(data if isinstance(data, dict) else {}, **common)
            ran += 1
        except Exception as e:  # noqa: BLE001 — 도메인별 실패 격리(나머지 계속·분석 무중단)
            logger.warning("specialist run 스킵(graceful) domain=%s err=%s", domain, str(e)[:160])
    return ran


def _run_domain_specialists(payload: dict) -> int:
    """Celery 워커 스레드에서 async 실행(memory_tasks 선례)."""
    try:
        return asyncio.run(_run_specialists_async(payload))
    except Exception as e:  # noqa: BLE001
        logger.warning("specialist task 실패(graceful): %s", str(e)[:160])
        return 0


def dispatch_domain_specialists(payload: dict) -> None:
    """도메인 SpecialistAgent 적재를 핫패스 비차단으로 발화(★G2 해소).

    워커 명시 활성(GROWTH_CELERY_WORKER)+celery 가용 시 Celery(.delay), 아니면(기본·워커부재)
    in-process 백그라운드로 실제 발화. 과거 `.delay()` 는 워커 부재 시 no-op 이라 死였다.
    """
    from app.services.agents.growth_dispatch import fire_and_forget, worker_enabled

    if _celery is not None and worker_enabled():
        run_domain_specialists_task.delay(payload)
        return
    fire_and_forget(_run_specialists_async(payload), label="specialists")


if _celery is not None:
    run_domain_specialists_task = _celery.task(
        name="tasks.specialists.run_for_analysis")(_run_domain_specialists)
else:
    class _NoopTask:
        @staticmethod
        def delay(*_a, **_k) -> None:
            logger.debug("celery 부재 — specialist run .delay no-op(워커 미가동)")

        @staticmethod
        def run(payload: dict) -> int:
            return _run_domain_specialists(payload)

    run_domain_specialists_task = _NoopTask()  # type: ignore[assignment]
