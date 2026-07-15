"""PropAI arq 워커 엔트리포인트.

실행: arq apps.worker.main.WorkerSettings

장시간 실행 태스크를 Redis 기반 비동기 큐로 처리한다.
- 법령 임베딩 생성
- MLOps 모델 재학습
- 대용량 IFC 파싱
- 평면도 이미지 생성
- PDF 보고서 생성
- AVM 배치 추정
- 블록체인 이벤트 리스닝
- 공공 데이터 ETL / 만료 데이터 정리
"""

from typing import Any

import structlog
from arq import cron
from arq.connections import RedisSettings

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    """워커 시작 시 초기화."""
    logger.info("PropAI 워커 시작")
    ctx["settings"] = settings

    # DB 세션 팩토리 주입 — 태스크에서 ctx['db_factory']()로 세션 생성
    try:
        from apps.api.database.session import AsyncSessionLocal
        ctx["db_factory"] = AsyncSessionLocal
        logger.info("DB 세션 팩토리 주입 완료")
    except ImportError:
        logger.warning("DB 세션 팩토리 로드 실패 — DB 접근 태스크 비활성화")

    # MQTT 드론 구독자 시작 (EMQX 설정이 있을 때만)
    mqtt_host = getattr(settings, "mqtt_broker_host", "")
    if mqtt_host:
        from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

        subscriber = MQTTDroneSubscriber(
            broker_host=mqtt_host,
            broker_port=getattr(settings, "mqtt_broker_port", 1883),
            username=getattr(settings, "mqtt_username", ""),
            password=getattr(settings, "mqtt_password", ""),
        )
        subscriber.start()
        ctx["mqtt_subscriber"] = subscriber
        logger.info("MQTT 드론 구독자 연결됨")


async def shutdown(ctx: dict[str, Any]) -> None:
    """워커 종료 시 정리."""
    # MQTT 구독자 정리
    subscriber = ctx.get("mqtt_subscriber")
    if subscriber is not None:
        subscriber.stop()

    logger.info("PropAI 워커 종료")


async def embed_regulations(ctx: dict[str, Any], batch_size: int = 100) -> dict[str, Any]:
    """법령 텍스트를 벡터 임베딩하여 Qdrant에 적재한다."""
    from apps.worker.tasks.embed_regulations import run_embed_regulations
    return await run_embed_regulations(ctx, batch_size)


async def retrain_avm_model(ctx: dict[str, Any]) -> dict[str, Any]:
    """AVM 모델을 최신 실거래가 데이터로 재학습한다."""
    from apps.worker.tasks.mlops import run_retrain_avm
    return await run_retrain_avm(ctx)


async def parse_large_ifc(ctx: dict[str, Any], file_url: str, project_id: str) -> dict[str, Any]:
    """대용량 IFC 파일을 파싱한다 (100MB+)."""
    from apps.worker.tasks.parse_large_ifc import run_parse_large_ifc
    return await run_parse_large_ifc(ctx, file_url, project_id)


async def generate_floor_plan(
    ctx: dict[str, Any],
    project_id: str,
    prompt: str,
    rooms: int = 3,
) -> dict[str, Any]:
    """SDXL 기반 평면도 이미지를 생성한다."""
    from apps.worker.tasks.generate_floor_plan import run_generate_floor_plan
    return await run_generate_floor_plan(ctx, project_id, prompt, rooms)


async def generate_report_pdf(
    ctx: dict[str, Any],
    project_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """프로젝트 종합 보고서 PDF를 생성한다."""
    from apps.worker.tasks.generate_report_pdf import run_generate_report_pdf
    return await run_generate_report_pdf(ctx, project_id, tenant_id)


async def dispatch_webhook(
    ctx: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    tenant_id: str,
) -> dict[str, Any]:
    """웹훅 이벤트를 구독 엔드포인트에 발송한다."""
    from apps.worker.tasks.webhook_dispatch import dispatch_webhook_event
    return await dispatch_webhook_event(ctx, event_type, payload, tenant_id)


async def avm_batch(
    ctx: dict[str, Any],
    tenant_id: str,
    parcel_ids: list[str],
) -> dict[str, Any]:
    """복수 필지에 대한 AVM 배치 시세 추정."""
    from apps.worker.tasks.avm_batch import run_avm_batch
    return await run_avm_batch(ctx, tenant_id, parcel_ids)


async def blockchain_listen(
    ctx: dict[str, Any],
    from_block: int | None = None,
) -> dict[str, Any]:
    """블록체인 이벤트 스캔 및 DB 동기화."""
    from apps.worker.tasks.blockchain_listener import run_blockchain_listener
    return await run_blockchain_listener(ctx, from_block)


async def etl_public_data(ctx: dict[str, Any]) -> dict[str, Any]:
    """공공 API 데이터 일괄 수집."""
    from apps.worker.tasks.etl_scheduled import run_etl_public_data
    return await run_etl_public_data(ctx)


async def cleanup_expired(ctx: dict[str, Any]) -> dict[str, Any]:
    """만료 데이터 정리."""
    from apps.worker.tasks.etl_scheduled import run_cleanup_expired
    return await run_cleanup_expired(ctx)


async def g2b_sync_bids(ctx: dict[str, Any]) -> dict[str, Any]:
    """나라장터 신규 입찰 공고 수집."""
    from app.tasks.g2b_sync_task import sync_bid_notices
    return await sync_bid_notices(ctx)


async def g2b_sync_awards(ctx: dict[str, Any]) -> dict[str, Any]:
    """나라장터 낙찰 결과 갱신."""
    from app.tasks.g2b_sync_task import sync_award_results
    return await sync_award_results(ctx)


async def g2b_rebuild_stats(ctx: dict[str, Any]) -> dict[str, Any]:
    """나라장터 낙찰가율 통계 재집계."""
    from app.tasks.g2b_sync_task import rebuild_award_stats
    return await rebuild_award_stats(ctx)


async def dispatch_outbox(ctx: dict[str, Any]) -> dict[str, Any]:
    """전역 아웃박스(outbox_event) 미발행 이벤트를 at-least-once 발행한다(P15 A4)."""
    from app.tasks.outbox_dispatch_task import run_outbox_dispatch_until_empty
    return await run_outbox_dispatch_until_empty(ctx)


class WorkerSettings:
    """arq 워커 설정."""

    functions = [
        embed_regulations,
        retrain_avm_model,
        parse_large_ifc,
        generate_floor_plan,
        generate_report_pdf,
        dispatch_webhook,
        avm_batch,
        blockchain_listen,
        etl_public_data,
        cleanup_expired,
        g2b_sync_bids,
        g2b_sync_awards,
        g2b_rebuild_stats,
        dispatch_outbox,
    ]

    cron_jobs = [
        # 매일 새벽 2시: AVM 모델 재학습
        cron(retrain_avm_model, hour=2, minute=0),
        # 매일 새벽 3시: 공공 데이터 ETL
        cron(etl_public_data, hour=3, minute=0),
        # 매일 새벽 4시: 만료 데이터 정리
        cron(cleanup_expired, hour=4, minute=0),
        # 매 10분: 블록체인 이벤트 리스닝
        cron(blockchain_listen, minute={0, 10, 20, 30, 40, 50}),
        # 나라장터(G2B) — 워커 TZ는 UTC 가정 (KST = UTC+9)
        # 매 2시간: 신규 입찰 공고 수집
        cron(g2b_sync_bids, hour=set(range(0, 24, 2)), minute=0),
        # 매일 21:00 UTC(= KST 06:00): 낙찰 결과 갱신
        cron(g2b_sync_awards, hour=21, minute=0),
        # 매주 월 22:00 UTC: 낙찰가율 통계 재집계
        cron(g2b_rebuild_stats, weekday="mon", hour=22, minute=0),
        # 전역 아웃박스 디스패처 — 매 분 미발행 이벤트 발행(at-least-once). arq/Redis 미배포
        # 환경(운영 Micro)에서는 API 인프로세스 루프(main.py)가 같은 코어를 호출한다(중복 안전).
        cron(dispatch_outbox, minute=set(range(0, 60))),
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # 태스크별 최대 실행 시간 (기본 30분)
    max_jobs = 10
    job_timeout = 1800
