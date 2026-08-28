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

    # ★자가성장 엔진 — 이 프로세스의 텔레메트리 큐를 **비운다**.
    #
    #   종전에 이 워커에는 배수구가 **하나도 없었다**(실측: `apps/worker` 전수 `flush_batch`
    #   호출 0건 · 대조군으로 `apps/api` 에서는 3건 탐지 = 조회기 생존).
    #   그런데 워커는 이벤트를 **담는다** — 직접 호출은 0건이지만 **전이 임포트**로 닿는다:
    #
    #     etl_public_data(매일 03:00 cron) → tasks/etl_scheduled.py → MolitClient
    #       → BaseAPIClient._request 실패 → integrations/base_client.py:_emit_growth_fallback
    #       → capture_service.record_event(...)
    #
    #   `capture_service._QUEUE` 는 **프로세스 로컬 deque**(maxlen=10,000)라 API 프로세스의
    #   flush 루프가 **이 큐를 볼 수 없다.** 즉 워커가 담은 이벤트는
    #   **컨테이너 재시작마다 통째로 사라졌고**, 그 안에는 회로차단기 폴백과
    #   `ledger_broken`(severity=critical) 이 포함된다.
    #
    #   ★`#920` 의 계수기도 이것을 못 본다 — 그 계수기 역시 **API 프로세스 큐**만 센다.
    #     즉 이 프로세스의 유실은 **화면에도 안 나오고 로그에도 안 남았다.**
    try:
        import asyncio as _asyncio

        from app.services.growth import capture_service as _gcap

        async def _growth_flush_loop() -> None:
            from apps.api.database.session import AsyncSessionLocal
            while True:
                await _asyncio.sleep(_gcap.flush_interval_s())
                try:
                    await _gcap.drain_until_empty(AsyncSessionLocal)
                except Exception as e:  # noqa: BLE001 — 배수 실패가 워커를 죽이면 안 된다.
                    logger.warning("growth flush 루프 오류", error=str(e)[:160])

        ctx["growth_flush_task"] = _asyncio.create_task(_growth_flush_loop())
        logger.info("성장루프 배수 루프 시작")
    except Exception as e:  # noqa: BLE001 — 배선 실패가 워커 기동을 막으면 안 된다.
        logger.warning("성장루프 배수 루프 시작 실패", error=str(e)[:160])


async def shutdown(ctx: dict[str, Any]) -> None:
    """워커 종료 시 정리."""
    # MQTT 구독자 정리
    subscriber = ctx.get("mqtt_subscriber")
    if subscriber is not None:
        subscriber.stop()

    # ★종료 시 큐 잔여를 마지막으로 비운다 — 여기가 **가장 많이 잃던 자리**다.
    #   배수구가 없던 종전에는 워커가 담은 것이 **전부** 여기서 사라졌다.
    _gt = ctx.get("growth_flush_task")
    if _gt is not None:
        _gt.cancel()
    try:
        from app.services.growth import capture_service as _gcap
        from apps.api.database.session import AsyncSessionLocal
        await _gcap.drain_until_empty(AsyncSessionLocal)
    except Exception as e:  # noqa: BLE001 — 어떤 예외도 종료를 막지 않는다.
        logger.warning("growth 종료 flush 오류", error=str(e)[:160])

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


async def g2b_sync_public_prices(ctx: dict[str, Any]) -> dict[str, Any]:
    """조달청 가격정보 → T1 공공단가(material_unit_prices PUB-*) 주기 주입."""
    from app.tasks.g2b_sync_task import sync_public_material_prices
    return await sync_public_material_prices(ctx)


async def realtx_sync(ctx: dict[str, Any]) -> dict[str, Any]:
    """실거래 2층 — **파생된** 시군구만 수집·저장하고 정정을 탐지한다.

    ★`etl_public_data` 의 하드코딩 시군구 8개는 실사용 필지의 **1.0%(4/394)** 만 덮는다
      (2026-08-26 라이브 실측). 모집단은 `user_project_store` 에서 파생한다.
    """
    from app.tasks.realtx_sync_task import sync_realtx_trades
    return await sync_realtx_trades(ctx)


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
        g2b_sync_public_prices,
        dispatch_outbox,
        realtx_sync,
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
        # 매일 20:30 UTC(= KST 05:30): 조달청 가격정보 → T1 공공단가 주입
        # (21:00 낙찰 갱신과 시차를 둬 동일 조달청 API군 레이트리밋 경합 방지)
        cron(g2b_sync_public_prices, hour=20, minute=30),
        # 전역 아웃박스 디스패처 — 매 분 미발행 이벤트 발행(at-least-once). arq/Redis 미배포
        # 환경(운영 Micro)에서는 API 인프로세스 루프(main.py)가 같은 코어를 호출한다(중복 안전).
        cron(dispatch_outbox, minute=set(range(0, 60))),
        # 매일 19:10 UTC(= KST 04:10): 실거래 2층 수집.
        # ★MOLIT 키를 **G2B 와 공유**하므로(라이브 해시 일치 실측 2026-08-26) 짝수시 정각의
        #   g2b_sync_bids · 20:30 조달청 · 21:00 낙찰 갱신과 **겹치지 않는 시각**을 고른다.
        cron(realtx_sync, hour=19, minute=10),
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # 태스크별 최대 실행 시간 (기본 30분)
    max_jobs = 10
    job_timeout = 1800

    # ★헬스 신호가 **실제 생존**을 뜻하게 한다 (2026-08-12 실측으로 정함).
    #   arq 는 이 주기마다 Redis 에 health 키를 쓰고, 만료를 `interval + 1` 초로 건다
    #   (arq/worker.py: psetex(key, (health_check_interval + 1) * 1000, ...) — 컨테이너에서 실측).
    #   기본값 3600 이면 **워커가 죽어도 최대 1시간 동안 `arq --check` 가 성공**한다.
    #   그 상태로 컨테이너 헬스체크를 걸면 위양성 빨강을 **위양성 초록**으로 바꿀 뿐이다
    #   (종전 상태가 정확히 위양성 빨강이었다 — API 이미지의 HTTP 헬스체크를 상속해
    #   워커가 멀쩡한데 3일째 unhealthy 였고, 그래서 아무도 그 신호를 보지 않았다).
    #   ★★값을 60 이 아니라 300 으로 둔다(리뷰 지적으로 정정). arq 는 health 키를
    #   **이벤트 루프에서** 쓰는데, 이 워커의 태스크 일부는 루프를 막는 동기 작업을
    #   `async def` 안에서 그대로 돈다(`run_in_executor`/`to_thread` 사용 0건 — 실측):
    #     · tasks/mlops.py `model.fit(...)`  · tasks/parse_large_ifc.py `ifcopenshell.open(...)`
    #     · tasks/generate_report_pdf.py `doc.build(...)`
    #   60 이면 새벽 2시 재학습이 루프를 몇 분 막는 동안 키가 만료돼 **일하는 중인
    #   워커가 unhealthy** 가 된다 — "상시 위양성"을 "중부하 위양성"으로 바꿀 뿐이다.
    #   TTL 301초는 그 블로킹을 견디면서도 죽은 워커를 빨갛게 만든다 — 탐지까지
    #   TTL 301초 + 연속 실패 3회(--health-interval 60s) ⇒ **최선 약 7분 · 최악 약 8분**.
    #   (초판 주석은 "5~6분"이라 적었는데 retries 3 을 계산에 넣지 않은 값이었다 — 리뷰가 잡았다.)
    #   ★진짜 해법은 블로킹 작업을 스레드로 빼는 것이다 — 별건으로 남긴다.
    health_check_interval = 300
