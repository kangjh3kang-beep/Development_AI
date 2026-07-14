"""PropAI FastAPI 앱 엔트리포인트.

실행: uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

주요 기능:
- 멀티테넌트 JWT 인증
- API 버전 관리 (v1/v2, /api/latest → 308)
- Prometheus 메트릭
- 구조화 로깅 (structlog)
- 헬스체크
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from packages.schemas.models import HealthResponse
from prometheus_client import make_asgi_app
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from apps.api.app.routers.bank_report import router as bank_report_router
from apps.api.app.routers.uploads import router as uploads_router
from apps.api.config import get_settings
from apps.api.database.init_qdrant import check_qdrant_health, init_qdrant_collections
from apps.api.exceptions import register_exception_handlers
from apps.api.logging_config import get_logger, setup_logging
from apps.api.metrics import DB_POOL_SIZE
from apps.api.middleware import setup_middlewares
from apps.api.rate_limit import limiter, rate_limit_exceeded_handler
from apps.api.routers import (
    admin_lists,
    agents,
    ai_assistant,
    ai_costs,
    analytics,
    api_keys,
    auction,
    auth,
    auto_zoning,
    avm,
    avm_vision,
    billing,
    bim,
    blockchain,
    building_compliance,
    cad_correction,
    climate,
    compliance,
    construction,
    contractors,
    contracts,
    cost_intelligence,
    dashboard,
    data_integrity,
    design,
    development_methods,
    digital_twin,
    domain_agents,
    drawing,
    drone,
    energy,
    environment,
    esg,
    esign,
    eu_taxonomy,
    expert_panel,
    facility_reservations,
    finance,
    gresb,
    integration,
    kdx,
    lcc,
    lease_ops,
    leases,
    maintenance,
    market_ai,
    market_report,
    marketing,
    notifications,
    parking,
    permit_cases,
    permits,
    portals,
    precheck,
    projects,
    re100,
    registry,
    regulation,
    reports,
    risk,
    safety,
    specialist_agents,
    sre,
    system,
    tax,
    tenant,
    terrain,
    underwriting,
    unit_mix,
    user_store,
    verification,
    webhooks,
    webrtc,
)
from apps.api.routers.v2 import auth as v2_auth
from apps.api.routers.v2 import design as v2_design
from apps.api.routers.v2 import projects as v2_projects

# v2 feasibility (자체 prefix 포함)
try:
    from apps.api.app.routers.v2_feasibility import router as v2_feasibility_router
except ImportError:
    try:
        from app.routers.v2_feasibility import router as v2_feasibility_router
    except ImportError:
        v2_feasibility_router = None

# v2 collaboration (회의방/협업 — 자체 prefix /api/v2/collaboration)
try:
    from apps.api.app.routers.v2_collaboration import router as v2_collaboration_router
except ImportError:
    try:
        from app.routers.v2_collaboration import router as v2_collaboration_router
    except ImportError:
        v2_collaboration_router = None

# v2 review comments (회의방 의견교환/심의 스레드 — 자체 prefix /api/v2/collaboration)
try:
    from apps.api.app.routers.v2_review_comments import router as v2_review_comments_router
except ImportError:
    try:
        from app.routers.v2_review_comments import router as v2_review_comments_router
    except ImportError:
        v2_review_comments_router = None

# v2 livekit (화상회의 토큰/녹화 — 자체 prefix /api/v2/livekit)
try:
    from apps.api.app.routers.v2_livekit import router as v2_livekit_router
except ImportError:
    try:
        from app.routers.v2_livekit import router as v2_livekit_router
    except ImportError:
        v2_livekit_router = None

# v2 pipeline (자체 prefix 포함)
try:
    from apps.api.app.routers.pipeline import router as pipeline_router
except ImportError:
    try:
        from app.routers.pipeline import router as pipeline_router
    except ImportError:
        pipeline_router = None

# v2 종합분석
try:
    from apps.api.app.routers.comprehensive_analysis import router as comprehensive_analysis_router
except ImportError:
    try:
        from app.routers.comprehensive_analysis import router as comprehensive_analysis_router
    except ImportError:
        comprehensive_analysis_router = None

# C2R(Coordinate-to-Render) — 부지 좌표 기반 렌더 브리프·이미지 렌더 (자체 prefix="/c2r")
try:
    from apps.api.app.routers.c2r import router as c2r_router
except ImportError:
    try:
        from app.routers.c2r import router as c2r_router
    except ImportError:
        c2r_router = None

# 접도·도로 기반(access_basis) — P4 legal/physical/emergency 3상태 (자체 prefix="/access")
try:
    from apps.api.app.routers.access import router as access_router
except ImportError:
    try:
        from app.routers.access import router as access_router
    except ImportError:
        access_router = None

# 나라장터(G2B) 공공입찰 (자체 prefix="/g2b")
try:
    from apps.api.app.routers.g2b_bid import router as g2b_router
except ImportError:
    try:
        from app.routers.g2b_bid import router as g2b_router
    except ImportError:
        g2b_router = None

# v62 분양관리 ERP + 모델하우스 데스크 (자체 내부 prefix, /api/v1/sales 하위)
try:
    from apps.api.app.api.endpoints.sales import sales_router
except ImportError:
    try:
        from app.api.endpoints.sales import sales_router
    except ImportError:
        sales_router = None

# Phase1-E 공통 구인구직 마켓 + 재사용 프로필 (PUBLIC 컨텐츠, 자체 prefix=/api/v1/market)
try:
    from apps.api.app.api.endpoints.sales.market import market_router
except ImportError:
    try:
        from app.api.endpoints.sales.market import market_router
    except ImportError:
        market_router = None

# v61 공사비(QTO) 라우터 — 시공관리 단계가 호출(자체 prefix=/api/v1/cost)
try:
    from apps.api.app.routers.cost import router as cost_router
except ImportError:
    try:
        from app.routers.cost import router as cost_router
    except ImportError:
        cost_router = None

# 범용 AI 프록시 — 설계 AI 등 공통 LLM 키 일원화(자체 prefix=/api/v1/ai)
try:
    from apps.api.app.routers.ai_analyze import router as ai_analyze_router
except ImportError:
    try:
        from app.routers.ai_analyze import router as ai_analyze_router
    except ImportError:
        ai_analyze_router = None

# 대량 다필지 배치(F-Parcel ParcelBatchJob) — 구역/수천 필지 비동기 취합·집계
try:
    from apps.api.app.routers.parcel_batch import router as parcel_batch_router
except ImportError:
    try:
        from app.routers.parcel_batch import router as parcel_batch_router
    except ImportError:
        parcel_batch_router = None

# 심의/설계도면 자동분석 엔진 BFF(별도 엔진 서비스 HTTP 게이트웨이) — 미설정 시 degraded만 응답
try:
    from apps.api.app.routers.deliberation import router as deliberation_router
except ImportError:
    try:
        from app.routers.deliberation import router as deliberation_router
    except ImportError:
        deliberation_router = None
from apps.api.versioning import VersionHeaderMiddleware, create_latest_redirect_router

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 생명주기 관리. 시작 시 초기화, 종료 시 정리."""
    # ── 시작 ──
    setup_logging(json_output=settings.environment != "development")
    logger.info("PropAI API 시작", version=settings.app_version, env=settings.environment)

    # Phase 4: 위험알림 기본 채널(telegram/ws) 등록(graceful·env-gated — 무설정 시 no-op)
    try:
        from app.services.ledger.risk_monitor import setup_default_notifiers
        setup_default_notifiers()
    except Exception:  # noqa: BLE001
        pass

    # Sentry 에러 추적 초기화
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            release=f"propai@{settings.app_version}",
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
        )
        logger.info("Sentry 초기화 완료")

    # OpenTelemetry 분산 추적
    if settings.otel_enabled:
        from apps.api.core.tracing import init_tracing, instrument_fastapi
        if init_tracing(
            service_name=settings.otel_service_name,
            otlp_endpoint=settings.otel_exporter_otlp_endpoint,
            sample_rate=settings.otel_sample_rate,
        ):
            instrument_fastapi(app)

    # Qdrant 컬렉션 초기화
    try:
        qdrant_results = await init_qdrant_collections()
        logger.info("Qdrant 초기화 완료", collections=qdrant_results)
    except Exception:
        logger.warning("Qdrant 초기화 실패 — 서비스 없이 시작")

    # DB 풀 크기 메트릭 설정
    DB_POOL_SIZE.set(settings.db_pool_size)

    # P1-4 배포 가드: production에서 시크릿 마스터키가 하드코딩 폴백이면 fail-fast(침묵 오염 차단).
    # ★의도적으로 try 밖 — 이 RuntimeError는 삼키면 안 되는 기동 차단 신호다(dev/test는 경고만).
    from app.services.secrets import secret_store
    secret_store.enforce_master_key_guard()

    # 관리자 화면에서 입력한 연동 API 키(platform_secrets)를 os.environ에 오버레이
    try:
        from apps.api.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as _s:
            await secret_store.load_into_env(_s)
    except Exception:
        logger.warning("플랫폼 시크릿 env 로드 실패 — .env 값으로 시작")

    # 자가성장 엔진 — 텔레메트리 3 테이블 멱등 보장(마이그레이션 미적용 환경 안전망).
    try:
        from app.services.growth import schema_guard
        from apps.api.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as _s:
            ok = await schema_guard.ensure_schema(_s)
        logger.info("growth schema_guard", ensured=ok)
    except Exception:
        logger.warning("growth schema_guard 호출 실패 — 마이그레이션에 의존")

    # 성장 뇌(MemoryHub) — agent_memories 테이블 멱등 보장(없으면 자동 기억저장 ingest 실패).
    try:
        from app.services.memory_hub import schema_guard as memory_schema_guard
        from apps.api.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as _s:
            mok = await memory_schema_guard.ensure_memory_schema(_s)
        logger.info("memory schema_guard", ensured=mok)
    except Exception:
        logger.warning("memory schema_guard 호출 실패 — 마이그레이션에 의존")

    # 매스 백본 — mass_templates 테이블 멱등 보장(없으면 매스 템플릿 수집 영속이 실패).
    try:
        from app.services.mass_backbone import schema_guard as mass_schema_guard
        from apps.api.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as _s:
            msok = await mass_schema_guard.ensure_mass_schema(_s)
        logger.info("mass schema_guard", ensured=msok)
    except Exception:
        logger.warning("mass schema_guard 호출 실패 — 마이그레이션/지연생성에 의존")

    # LangSmith LLM 추적 활성화(키 있을 때만). load_into_env 이후여야 관리자 키가 반영됨.
    try:
        from apps.api.core.observability import init_langsmith
        init_langsmith()
    except Exception:
        logger.warning("LangSmith 초기화 실패 — 추적 없이 시작")

    # 분양·청약 관심지역 모니터링 — 인프로세스 주기 폴링(celery 미배포 환경 대응).
    # 단일 uvicorn 워커에서 1개 루프만 동작. 관심지역/키 없으면 즉시 반환되어 유휴비용 0.
    import asyncio as _asyncio

    async def _presale_monitor_loop() -> None:
        from apps.api.app.services.land_intelligence import presale_monitor_service as _mon
        from apps.api.database.session import AsyncSessionLocal
        await _asyncio.sleep(300)  # 부팅 안정화 후 시작
        while True:
            try:
                async with AsyncSessionLocal() as _s:
                    res = await _mon.run_all(_s)
                logger.info("분양 모니터링 폴링", **res)
            except Exception as e:  # noqa: BLE001
                logger.warning("분양 모니터링 폴링 실패: %s", str(e)[:160])
            await _asyncio.sleep(6 * 3600)  # 6시간 주기

    try:
        app.state.presale_monitor_task = _asyncio.create_task(_presale_monitor_loop())
    except Exception:  # noqa: BLE001
        logger.warning("분양 모니터링 루프 시작 실패")

    # 한국은행 ECOS 실 기준금리/시장금리 — 백그라운드 프리페치 + 주기 갱신.
    #   금융비 엔진 get_pf_rate가 동기 소비라 모듈 캐시를 채운다. ★인라인 await 금지: ECOS 지연이
    #   기동 readiness를 막지 않도록 create_task(콜드 캐시는 이미 하드코딩 폴백이라 안전). 12h 주기로
    #   재갱신(기준금리 월 단위 → 7일 TTL 만료 전 갱신, 무재배포 장기가동에도 실시간 유지).
    async def _ecos_refresh_loop() -> None:
        from app.services.external_api import ecos_service as _ecos
        while True:
            try:
                await _ecos.refresh()
            except Exception as e:  # noqa: BLE001
                logger.warning("ECOS 실금리 갱신 실패 — 하드코딩 폴백 유지: %s", str(e)[:120])
            await _asyncio.sleep(12 * 3600)  # 12시간 주기

    try:
        app.state.ecos_refresh_task = _asyncio.create_task(_ecos_refresh_loop())
    except Exception:  # noqa: BLE001
        logger.warning("ECOS 갱신 루프 시작 실패 — 폴백 유지")

    # #4 수납 — 분양현장 연체이자 일배치(인프로세스 폴백). 미납 회차의 연체이자를 매일 1회
    # '오늘 기준'으로 산정·적재한다(자금이동 없음, 산출만). overdue_calc 가 멱등이라
    # (site_id,installment_id,calc_date) UNIQUE 로 같은 날 재실행해도 행이 중복되지 않는다.
    # 멀티워커 안전: pg_try_advisory_lock 으로 한 워커만 돌린다(획득 실패 시 skip). 단일워커는 항상 획득.
    # 환경(SALES_OVERDUE_INPROCESS, 기본 on)으로 off 가능. 현장/미납 없으면 즉시 0 반환(유휴비용 0).
    # advisory lock 키 — lifecycle_p5 수동 트리거와 '같은' 키로 상호배제(SSOT: payment/locks.py).
    from app.services.sales.payment.locks import OVERDUE_LOCK_KEY as _OVERDUE_LOCK_KEY  # noqa: N806

    async def _overdue_batch_loop() -> None:
        import os as _os2

        from sqlalchemy import text as _text  # advisory lock SQL 용.
        if _os2.getenv("SALES_OVERDUE_INPROCESS", "1") == "0":
            return
        from app.services.sales.payment.service import run_overdue_all_sites
        from apps.api.database.session import AsyncSessionLocal
        await _asyncio.sleep(420)  # 부팅 안정화 후 시작(다른 루프와 시차).
        while True:
            try:
                async with AsyncSessionLocal() as _s:
                    # ★lifecycle_p5 수동 트리거와 통일: pg_try_advisory_xact_lock(트랜잭션 종료 시
                    #   자동해제)으로 잡는다. 기존 세션락 + finally 수동 unlock 은 run_overdue_all_sites
                    #   가 내부에서 commit/rollback(테이블 미존재 폴백 등)으로 트랜잭션 경계를 바꾼 뒤
                    #   세션락이 잔존하거나 unlock 이 빗나갈 위험이 있었다. xact 락은 commit/rollback
                    #   어느 쪽으로 끝나도 자동해제돼 락 누수가 원천 차단된다(별도 unlock 불필요).
                    got = bool((await _s.execute(
                        _text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _OVERDUE_LOCK_KEY})).scalar())
                    if got:
                        res = await run_overdue_all_sites(_s)
                        logger.info("연체이자 일배치 완료", **res)
                    else:
                        # 다른 워커가 보유 중 → skip. 이 세션은 락만 시도하고 끝나며,
                        # 세션 종료(async with 이탈) 시 트랜잭션이 정리돼 시도분도 자동해제된다.
                        await _s.rollback()
                        logger.debug("연체 일배치 skip(다른 워커 보유)")
            except Exception as e:  # noqa: BLE001 — 루프는 절대 죽지 않게(분류는 서비스 내부에서 처리).
                logger.warning("연체이자 일배치 실패: %s", str(e)[:160])
            await _asyncio.sleep(24 * 3600)  # 하루 1회 주기.

    try:
        app.state.overdue_batch_task = _asyncio.create_task(_overdue_batch_loop())
    except Exception:  # noqa: BLE001
        logger.warning("연체이자 일배치 루프 시작 실패")

    # 자가성장 엔진 — 텔레메트리 큐 → platform_events 인프로세스 주기 flush.
    # Celery Beat(5초)가 정본이지만, Celery 미배포 환경에서도 적재되도록
    # _presale_monitor_loop 와 동일한 asyncio 폴백을 둔다(단일 워커 1개 루프).
    async def _growth_flush_loop() -> None:
        from app.services.growth import capture_service
        from apps.api.database.session import AsyncSessionLocal
        while True:
            await _asyncio.sleep(5)
            try:
                if capture_service.queue_size() == 0:
                    continue
                async with AsyncSessionLocal() as _s:
                    for _ in range(20):
                        n = await capture_service.flush_batch(_s)
                        if n < 500:
                            break
            except Exception as e:  # noqa: BLE001
                logger.warning("growth flush 루프 오류: %s", str(e)[:160])

    try:
        app.state.growth_flush_task = _asyncio.create_task(_growth_flush_loop())
    except Exception:  # noqa: BLE001
        logger.warning("growth flush 루프 시작 실패")

    # 자가성장 엔진 — analyze/heal/correct/learn 주기 잡 인프로세스 스케줄러(Path B).
    # 운영 Micro 는 uvicorn --workers 1 만 돌고 Celery worker/beat·Redis 가 없어
    # Celery Beat 에만 걸린 분석/치유/수정/학습이 실제로는 잠들어 있다. _growth_flush_loop
    # 와 동일한 asyncio 폴백으로, Celery 태스크 래퍼가 아니라 그 안의 async 코어
    # (_analyze_async/_heal_async/_correct_async + learning_loop.run_learning_cycle)를
    # 같은 프로세스에서 직접 await 해 자율 구동한다. ENV(GROWTH_INPROCESS_SCHED, 기본 on)로 off 가능.
    #
    # 멀티워커 안전: 각 사이클 진입 전 Postgres advisory lock(pg_try_advisory_lock)을
    # best-effort 로 시도해, 다른 워커가 잡았으면 그 사이클을 skip 한다(중복실행 방지).
    # Micro 는 단일워커라 항상 획득. lock 획득/해제 실패·예외는 안전하게 무시(단일워커 폴백).
    import os as _os

    # advisory lock 키(상수) — 잡별로 구분(동일 잡만 상호배제, 잡 간 병렬 허용).
    _GROWTH_LOCK_KEYS = {
        "analyze": 911_000_001,
        "heal": 911_000_002,
        "correct": 911_000_003,
        "learn": 911_000_004,
        "improve": 911_000_005,  # L2 개선제안(Draft PR 봇) — Celery 미배포 환경 인프로세스 배선.
    }

    async def _growth_try_lock(session, key: int) -> bool:
        """pg_try_advisory_lock 시도. 획득 True / 실패·예외 False(best-effort)."""
        try:
            from sqlalchemy import text as _text
            row = (await session.execute(
                _text("SELECT pg_try_advisory_lock(:k)"), {"k": key}
            )).scalar()
            return bool(row)
        except Exception:  # noqa: BLE001 — lock 실패는 안전하게 skip.
            return False

    async def _growth_unlock(session, key: int) -> None:
        """pg_advisory_unlock(best-effort, 예외 무시)."""
        try:
            from sqlalchemy import text as _text
            await session.execute(_text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        except Exception:  # noqa: BLE001
            pass

    async def _growth_run_locked(job_name: str, coro_factory) -> None:
        """advisory lock 획득 시에만 async 코어를 1회 실행한다(잡 단위 격리).

        coro_factory(session) -> awaitable. 한 세션 안에서 lock→실행→unlock 을 묶어
        다른 워커와 상호배제. 어떤 예외도 스케줄러를 죽이지 않는다(잡별 try/except).
        """
        from apps.api.database.session import AsyncSessionLocal
        key = _GROWTH_LOCK_KEYS[job_name]
        try:
            async with AsyncSessionLocal() as _s:
                got = await _growth_try_lock(_s, key)
                if not got:
                    logger.debug("growth 스케줄러 skip(다른 워커 보유): %s", job_name)
                    return
                try:
                    res = await coro_factory()
                    logger.info("growth 인프로세스 잡 완료", job=job_name, result=str(res)[:200])
                finally:
                    await _growth_unlock(_s, key)
        except Exception as e:  # noqa: BLE001 — 한 잡 실패가 다른 잡·앱을 깨지 않게.
            logger.warning("growth 인프로세스 잡 실패(%s): %s", job_name, str(e)[:160])

    async def _growth_scheduler_loop() -> None:
        """analyze(매시)·heal(10분)·correct(15분)·learn(주간) 주기 구동.

        heal/correct 는 analyze 가 만든 open 인사이트를 읽으므로, 매 틱마다 먼저
        analyze 가 시간경계를 넘었으면 analyze 를 돌린 직후 heal/correct 가 최신
        인사이트를 보게 순서를 보장한다(tick=60초 단위 시계). 부팅 안정화 초기 지연.
        """
        from app.tasks import growth_tasks

        await _asyncio.sleep(120)  # 부팅 안정화 후 시작(flush 루프보다 늦게).

        tick = 0  # 60초 단위 카운터.
        while True:
            try:
                run_analyze = (tick % 60 == 0)   # 매시(60분).
                run_heal = (tick % 10 == 0)      # 10분.
                run_correct = (tick % 15 == 0)   # 15분.
                run_learn = (tick % 10080 == 0 and tick > 0)  # 주간(7일=10080분).
                run_improve = (tick % 1440 == 0 and tick > 0)  # 일배치(24h=1440분) — L2 개선제안.

                # 순서 보장: analyze 를 먼저 끝낸 뒤 heal/correct 가 최신 인사이트를 본다.
                if run_analyze:
                    await _growth_run_locked(
                        "analyze", lambda: growth_tasks._analyze_async(window_hours=1)
                    )
                if run_heal:
                    await _growth_run_locked("heal", growth_tasks._heal_async)
                if run_correct:
                    await _growth_run_locked("correct", growth_tasks._correct_async)
                if run_learn:
                    # ★C2: growth_learning_task._learn_async 재사용(세션 자체관리 async
                    #   코어) — 과거엔 learning_loop.run_learning_cycle 만 호출해, 뒤이은
                    #   improvement_agent.generate_prompt_candidates(프롬프트 개선후보
                    #   A/B 후보군 등록)가 Celery 전용 경로(growth_learning_task._learn_async)
                    #   에만 구현돼 있어 프로드(워커 미가동)에서 영구 미발화였다(중복구현
                    #   제거 + read-back 배선 완결). asyncio.run 없는 순수 코루틴이라
                    #   이미 가동 중인 인프로세스 스케줄러 루프에서 안전하게 await 가능.
                    from app.tasks import growth_learning_task
                    await _growth_run_locked("learn", growth_learning_task._learn_async)
                if run_improve:
                    # L2 개선제안 — improvement_agent.generate_proposals(requires_approval=True 인간게이트).
                    #   GH_TOKEN 없으면 PR 생성 스킵·아티팩트만 기록(graceful). main push·자동머지 없음.
                    await _growth_run_locked("improve", growth_tasks._improve_async)
            except Exception as e:  # noqa: BLE001 — 루프 자체는 절대 죽지 않게.
                logger.warning("growth 스케줄러 틱 오류: %s", str(e)[:160])
            tick += 1
            await _asyncio.sleep(60)  # 1분 틱.

    if _os.getenv("GROWTH_INPROCESS_SCHED", "1") != "0":
        try:
            app.state.growth_scheduler_task = _asyncio.create_task(_growth_scheduler_loop())
        except Exception:  # noqa: BLE001
            logger.warning("growth 인프로세스 스케줄러 시작 실패")

    yield

    # ── 종료 ──
    _t = getattr(app.state, "presale_monitor_task", None)
    if _t is not None:
        _t.cancel()
    _ect = getattr(app.state, "ecos_refresh_task", None)
    if _ect is not None:
        _ect.cancel()
    _ot = getattr(app.state, "overdue_batch_task", None)
    if _ot is not None:
        _ot.cancel()
    _st = getattr(app.state, "growth_scheduler_task", None)
    if _st is not None:
        _st.cancel()
    _gt = getattr(app.state, "growth_flush_task", None)
    if _gt is not None:
        _gt.cancel()
        # 루프 cancel 직후 마지막 동기 flush 1회 — 종료 시 큐 잔여 이벤트 유실 방지.
        # best-effort: 어떤 예외도 종료를 막지 않는다.
        try:
            from app.services.growth import capture_service
            from apps.api.database.session import AsyncSessionLocal
            if capture_service.queue_size() > 0:
                async with AsyncSessionLocal() as _fs:
                    for _ in range(20):
                        n = await capture_service.flush_batch(_fs)
                        if n < 500:
                            break
        except Exception as e:  # noqa: BLE001
            logger.warning("growth 종료 flush 오류: %s", str(e)[:160])
    logger.info("PropAI API 종료")


# FastAPI 앱 생성
app = FastAPI(
    title="PropAI API",
    description="부동산개발 전주기 AI 자동화 플랫폼",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 미들웨어 등록
setup_middlewares(app)
app.add_middleware(VersionHeaderMiddleware)

# 자가성장 엔진 — 요청 텔레메트리 수집(논블로킹 큐 push만, 동기 INSERT 없음).
# 헬스/메트릭/자기수집 경로는 미들웨어 내부 화이트리스트로 제외. best-effort 등록.
try:
    from apps.api.app.middleware.growth_telemetry import GrowthTelemetryMiddleware
    app.add_middleware(GrowthTelemetryMiddleware)
except Exception as _e:  # noqa: BLE001
    logger.warning("growth 텔레메트리 미들웨어 등록 실패", err=str(_e)[:160])


# 인증 사용자 ID를 요청 컨텍스트에 주입 (LLM 과금 누적·한도 차단용, best-effort)
@app.middleware("http")
async def _inject_user_context(request, call_next):
    from app.core.request_context import set_current_tenant_id, set_current_user_id

    set_current_user_id(None)
    set_current_tenant_id(None)
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        try:
            from apps.api.auth.jwt_handler import decode_token

            payload = decode_token(auth.split(" ", 1)[1].strip())
            if getattr(payload, "sub", None):
                set_current_user_id(str(payload.sub))
            # 자가성장 텔레메트리 귀속용 테넌트 ID(best-effort).
            if getattr(payload, "tenant_id", None):
                set_current_tenant_id(str(payload.tenant_id))
        except Exception:  # noqa: BLE001 — 토큰 없음/무효는 무시(비로그인 허용)
            pass
    return await call_next(request)


# 예외 핸들러 등록
register_exception_handlers(app)

# Rate Limiting 등록 (SlowAPIMiddleware → 모든 엔드포인트에 default_limits 적용)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Prometheus 메트릭 엔드포인트
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# /api/latest → 308 리다이렉트 라우터
app.include_router(create_latest_redirect_router())


# ──────────────────────────────────────
# 헬스체크 엔드포인트
# ──────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["시스템"])
async def health_check() -> HealthResponse:
    """헬스체크. 의존 서비스 상태를 함께 반환한다."""
    from apps.api.database.session import engine

    services: dict[str, str] = {}

    # PostgreSQL 연결 확인
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        services["postgres"] = "healthy"
    except Exception as e:
        db_url = str(engine.url)
        masked = db_url.split("@")[-1] if "@" in db_url else db_url
        logger.error("PostgreSQL health check failed", host=masked, error=str(e)[:200])
        services["postgres"] = "unhealthy"

    # Redis 연결 확인
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        services["redis"] = "healthy"
    except Exception:
        services["redis"] = "unhealthy"

    # Qdrant 확인
    qdrant_ok = await check_qdrant_health()
    services["qdrant"] = "healthy" if qdrant_ok else "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

    return HealthResponse(
        status=overall,
        version=settings.app_version,
        services=services,
    )


# ──────────────────────────────────────
# API v1 라우터
# ──────────────────────────────────────

app.include_router(auth.router, prefix="/api/v1/auth", tags=["인증"])
app.include_router(billing.router, tags=["구독·과금"])  # 자체 prefix=/api/v1/billing
from apps.api.routers import teams as _teams_router  # 팀(공유 워크스페이스)

app.include_router(_teams_router.router, tags=["팀"])  # 자체 prefix=/api/v1/teams
from apps.api.routers import presale as _presale_router  # 분양·청약 정보 + 관심지역 모니터링

app.include_router(_presale_router.router, tags=["분양정보"])  # 자체 prefix=/api/v1/presale
from apps.api.routers import design_references as _design_ref_router  # 표준설계 참조 라이브러리(P7)

app.include_router(_design_ref_router.router, tags=["설계 참조 라이브러리"])  # 자체 prefix=/api/v1/design-references
from apps.api.routers import personas as _personas_router  # P1 실무 전문가 페르소나(분양대행·도시계획)

app.include_router(_personas_router.router, prefix="/api/v1", tags=["실무 전문가 페르소나"])  # /api/v1/personas
from apps.api.routers import design_generation as _design_gen_router  # 설계 생성(인제스트·검색·생성·법규)

app.include_router(_design_gen_router.router)  # 자체 prefix=/api/v1/design-gen, tags는 라우터에 정의
from apps.api.routers import senior_agents as _senior_agents_router  # 시니어 전문가 에이전트 자문(결정론)

app.include_router(_senior_agents_router.router, prefix="/api/v1", tags=["시니어 전문가 에이전트"])  # /api/v1/senior/*
app.include_router(market_report.router, tags=["시장조사보고서"])  # 자체 prefix=/api/v1/market
app.include_router(projects.router, prefix="/api/v1/projects", tags=["프로젝트"])
app.include_router(user_store.router, prefix="/api/v1", tags=["사용자 저장소"])
app.include_router(expert_panel.router, prefix="/api/v1", tags=["전문가 패널"])
app.include_router(verification.router, prefix="/api/v1", tags=["분석 검증"])
app.include_router(registry.router, prefix="/api/v1", tags=["부동산 등기부"])
app.include_router(avm.router, prefix="/api/v1/avm", tags=["AVM 시세추정"])
app.include_router(avm_vision.router, prefix="/api/v1/avm-vision", tags=["이미지융합 AVM"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["분석 대시보드"])
app.include_router(integration.router, prefix="/api/v1/integration", tags=["연동 상태"])
app.include_router(admin_lists.router, prefix="/api/v1", tags=["관리자 편집목록"])
app.include_router(regulation.router, prefix="/api/v1/regulation", tags=["법규 검토"])
app.include_router(tax.router, prefix="/api/v1/tax", tags=["세금 계산"])
app.include_router(design.router, prefix="/api/v1/design", tags=["설계"])
app.include_router(bim.router, prefix="/api/v1/bim", tags=["BIM/IFC"])
app.include_router(finance.router, prefix="/api/v1/finance", tags=["재무 분석"])
app.include_router(drone.router, prefix="/api/v1/drone", tags=["드론 점검"])
app.include_router(blockchain.router, prefix="/api/v1/blockchain", tags=["블록체인"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["보고서"])
app.include_router(construction.router, prefix="/api/v1/construction", tags=["시공/ESG"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["에이전트"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["웹훅"])
app.include_router(api_keys.router, prefix="/api/v1/api-keys", tags=["API 키"])
app.include_router(building_compliance.router, prefix="/api/v1/building-compliance", tags=["건축 법규 검증"])
app.include_router(cad_correction.router, prefix="/api/v1/cad-correction", tags=["CAD 자동 보정"])
app.include_router(drawing.router, prefix="/api/v1/drawing", tags=["도면 자동 생성"])
app.include_router(ai_assistant.router, prefix="/api/v1/ai", tags=["AI 비서"])
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(ai_costs.router, prefix="/api/v1/ai-costs", tags=["ai-costs"])
app.include_router(energy.router, prefix="/api/v1/energy", tags=["energy"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
app.include_router(esign.router, prefix="/api/v1/esign", tags=["esign"])
app.include_router(underwriting.router, prefix="/api/v1/underwriting", tags=["underwriting"])
app.include_router(climate.router, prefix="/api/v1/climate", tags=["climate"])
app.include_router(compliance.router, prefix="/api/v1/compliance", tags=["compliance"])
app.include_router(leases.router, prefix="/api/v1/leases", tags=["leases"])
app.include_router(lease_ops.router, prefix="/api/v1/lease-ops", tags=["lease-ops"])
app.include_router(esg.router, prefix="/api/v1/esg", tags=["esg"])
app.include_router(marketing.router, prefix="/api/v1/marketing", tags=["marketing"])
app.include_router(domain_agents.router, prefix="/api/v1/agents/domain", tags=["domain-agents"])
app.include_router(specialist_agents.router, prefix="/api/v1/agents/specialist", tags=["specialist-agents"])
app.include_router(maintenance.router, prefix="/api/v1/maintenance", tags=["maintenance"])
app.include_router(tenant.router, prefix="/api/v1/tenant", tags=["tenant-experience"])
app.include_router(digital_twin.router, prefix="/api/v1/digital-twin", tags=["digital-twin"])
app.include_router(portals.router, prefix="/api/v1/portals", tags=["portals"])
# chatbot 라우터 삭제됨(2026-07-12 — 결정론 캔드 리플라이, 전역 AIAssistant 실LLM과 중복·열등)
app.include_router(auction.router, prefix="/api/v1/auction", tags=["auction"])
app.include_router(contractors.router, prefix="/api/v1/contractors", tags=["contractors"])

# RE100 + K-ETS 라우터
app.include_router(re100.router, prefix="/api/v1/re100", tags=["RE100/K-ETS"])

# v50 KDX 라우터
app.include_router(kdx.router, prefix="/api/v1/kdx", tags=["KDX 연동"])

# v49 Phase 2 라우터
app.include_router(safety.router, prefix="/api/v1/safety", tags=["safety"])
app.include_router(parking.router, prefix="/api/v1/parking", tags=["parking"])
app.include_router(webrtc.router, prefix="/api/v1/webrtc", tags=["webrtc"])
app.include_router(sre.router, prefix="/api/v1/sre", tags=["sre"])
app.include_router(facility_reservations.router, prefix="/api/v1/facilities", tags=["facilities"])

# LCC 생애주기비용 + EU Taxonomy 라우터
app.include_router(lcc.router, prefix="/api/v1/lcc", tags=["LCC 생애주기비용"])
app.include_router(eu_taxonomy.router, prefix="/api/v1/eu-taxonomy", tags=["EU Taxonomy"])
# monte_carlo 라우터 삭제됨(독립 표면 잉여 — MC는 finance.py·project_dashboard·/cost/{id}/monte-carlo로 노출)
app.include_router(development_methods.router, prefix="/api/v1/development-methods", tags=["개발기획 자동화"])
app.include_router(cost_intelligence.router, prefix="/api/v1/cost-intelligence", tags=["cost-intelligence"])
app.include_router(contracts.router, prefix="/api/v1/contracts", tags=["contracts"])
app.include_router(risk.router, prefix="/api/v1/risk", tags=["risk"])
app.include_router(permits.router, prefix="/api/v1/permits", tags=["permits"])
app.include_router(permit_cases.router, prefix="/api/v1/permit-cases", tags=["인허가 사례(건축HUB)"])
app.include_router(data_integrity.router, prefix="/api/v1", tags=["데이터 무결성"])

# 자동 용도지역 + 유닛믹스 최적화 라우터
app.include_router(auto_zoning.router, prefix="/api/v1/zoning", tags=["자동 용도지역"])
# 90초 AI PreCheck(Flagship A) — 즉시 룰체크 + 조닝 시그널
app.include_router(precheck.router, prefix="/api/v1/precheck", tags=["AI PreCheck"])
# 지형분석(Flagship C-1) — 경사도·토공량·지형단면(DEM 기반)
app.include_router(terrain.router, prefix="/api/v1/terrain", tags=["지형분석"])
# 환경분석(Flagship C-2) — 일조·조망·스카이라인(약식·천문식)
app.include_router(environment.router, prefix="/api/v1/environment", tags=["환경분석"])
app.include_router(unit_mix.router, prefix="/api/v1/unit-mix", tags=["유닛믹스 최적화"])

# 대화형 시장분석 AI + GRESB ESG 스코어링 라우터
app.include_router(market_ai.router, prefix="/api/v1/market-ai", tags=["대화형 시장분석"])
app.include_router(gresb.router, prefix="/api/v1/gresb", tags=["GRESB ESG 스코어링"])

# 은행제출용 통합 보고서 라우터
app.include_router(bank_report_router, prefix="/api/v1", tags=["은행제출용 보고서"])

# 파일 업로드(현장 이미지 등) → /api/v1/uploads/*
app.include_router(uploads_router, prefix="/api/v1", tags=["업로드"])

# 관리자 — 연동 API 키 관리(입력/수정/삭제/사용자추가) → /api/v1/admin/secrets/*
try:
    from apps.api.app.routers.admin_secrets import router as admin_secrets_router
    app.include_router(admin_secrets_router, tags=["관리자·API키"])  # 자체 prefix
except Exception as _e:  # noqa: BLE001
    logger.warning("admin_secrets 라우터 등록 실패", err=str(_e)[:160])

# 자가성장 엔진 — 프론트 텔레메트리 수신 → /api/v1/growth/events (익명 허용)
try:
    from apps.api.app.routers.growth import router as growth_router
    app.include_router(growth_router, prefix="/api/v1", tags=["자가성장 텔레메트리"])
except Exception as _e:  # noqa: BLE001
    logger.warning("growth 라우터 등록 실패", err=str(_e)[:160])

# 관리자 — 분양(sales) RLS 부트스트랩(적용/상태/롤백) → /api/v1/admin/sales-rls/*
try:
    from apps.api.app.routers.admin_sales_rls import router as admin_sales_rls_router
    app.include_router(admin_sales_rls_router, tags=["관리자·분양RLS"])  # 자체 prefix
except Exception as _e:  # noqa: BLE001
    logger.warning("admin_sales_rls 라우터 등록 실패", err=str(_e)[:160])

# SiteScore — 설명가능 학습형 입지 점수 → /api/v1/site-score
try:
    from apps.api.app.routers.site_score import router as site_score_router
    app.include_router(site_score_router, tags=["입지점수(SiteScore)"])  # 자체 prefix
except Exception as _e:  # noqa: BLE001
    logger.warning("site_score 라우터 등록 실패", err=str(_e)[:160])

# 토지 적정 매입가 추정 → /api/v1/land-price
try:
    from apps.api.app.routers.land_price import router as land_price_router
    app.include_router(land_price_router, tags=["토지 적정가"])  # 자체 prefix
except Exception as _e:  # noqa: BLE001
    logger.warning("land_price 라우터 등록 실패", err=str(_e)[:160])

try:
    from apps.api.app.routers.analysis_ledger import router as analysis_ledger_router
    app.include_router(analysis_ledger_router, tags=["분석원장(해시체인)"])  # 자체 prefix
except Exception as _e:  # noqa: BLE001
    logger.warning("analysis_ledger 라우터 등록 실패", err=str(_e)[:160])

# 중심 엔진 통합 BFF — 심의/설계도면 자동분석 엔진 게이트웨이 → /api/v1/deliberation/*
try:
    from apps.api.app.routers.deliberation import router as deliberation_router
    app.include_router(deliberation_router, tags=["심의분석 엔진"])  # 자체 prefix
except Exception as _e:  # noqa: BLE001
    logger.warning("deliberation 라우터 등록 실패", err=str(_e)[:160])

# BOQ 자동화 — 공내역서 마스터(B1) + 드래프트(B2) + 개산 연동 → /api/v1/boq-auto/*
try:
    from apps.api.app.routers.boq_auto import router as boq_auto_router
    app.include_router(boq_auto_router, tags=["BOQ 자동화"])  # 자체 prefix
except Exception as _e:  # noqa: BLE001
    logger.warning("boq_auto 라우터 등록 실패", err=str(_e)[:160])

# 나라장터(G2B) 공공입찰 — 라우터 자체 prefix="/g2b" → 최종 /api/v1/g2b/*
if g2b_router is not None:
    app.include_router(g2b_router, prefix="/api/v1", tags=["공공입찰(G2B)"])
if cost_router is not None:
    app.include_router(cost_router, tags=["v61 공사비"])  # 자체 prefix=/api/v1/cost
if ai_analyze_router is not None:
    app.include_router(ai_analyze_router, tags=["ai"])  # 자체 prefix=/api/v1/ai
if parcel_batch_router is not None:
    app.include_router(parcel_batch_router, tags=["대량 다필지 배치"])  # 자체 prefix=/api/v1/parcels/batch
if deliberation_router is not None:
    app.include_router(deliberation_router, tags=["심의분석 엔진"])  # 자체 prefix=/api/v1/deliberation
if market_router is not None:
    # PUBLIC 마켓(구인구직·프로필·홍보) — 자체 prefix=/api/v1/market, 현장 격리 없음
    app.include_router(market_router, tags=["구인구직 마켓(public)"])

# Phase1-H 소셜 네트워크 — 친구·단톡·푸시·다중톡 (PUBLIC 전역, 자체 prefix=/api/v1/social)
try:
    from apps.api.app.api.endpoints.sales.social import social_router
except ImportError:
    try:
        from app.api.endpoints.sales.social import social_router
    except ImportError:
        social_router = None

if social_router is not None:
    # PUBLIC 소셜(친구 소셜그래프·단톡·WS·FCM 푸시) — 현장 격리 없음. WS(/api/v1/social/ws)도 내장.
    app.include_router(social_router, tags=["소셜 네트워크(public)"])
if sales_router is not None:
    app.include_router(sales_router, prefix="/api/v1/sales", tags=["분양관리(sales)"])
    try:
        from apps.api.app.api.endpoints.sales.ws_routes import ws_router as sales_ws_router
    except ImportError:
        from app.api.endpoints.sales.ws_routes import ws_router as sales_ws_router
    app.include_router(sales_ws_router, tags=["분양관리(sales-ws)"])

# ── 프론트 호출하나 미마운트였던 app/routers (404 위험 해소). 각각 독립 try로 격리 ──
# ESG LCA/EPD: app/routers/esg.py(자체 prefix=/api/v1/esg). /esg/assessment는 위
# routers/esg.py(선등록)와 중복이나 first-match라 무해(라이브 충돌 0 확인).
try:
    from apps.api.app.routers.esg import router as app_esg_router

    app.include_router(app_esg_router, tags=["ESG·탄소(LCA/EPD)"])
except Exception as e:
    logger.warning("app/routers/esg 로드 실패", error=str(e))

# 프로젝트 대시보드: /projects/{id}/bim-takeoff·simulate-feasibility (자체 prefix=/projects).
try:
    from apps.api.app.routers.project_dashboard import router as project_dashboard_router

    app.include_router(project_dashboard_router, prefix="/api/v1", tags=["프로젝트 대시보드"])
except Exception as e:
    logger.warning("app/routers/project_dashboard 로드 실패", error=str(e))

# v61 설계도면: /design/{id}/generate-full-set·drawings/* (CadExportPanel/ExportPanel
# 호출, 자체 prefix=/api/v1/design). 기존 design.py와 하위경로 분리라 충돌0(라이브확인).
# import·의존(svg_drawing/parametric_cad/seed) 정상 로드 확인 후 마운트.
try:
    from apps.api.app.routers.design_v61 import router as design_v61_router

    app.include_router(design_v61_router, tags=["v61 설계도면"])
except Exception as e:
    logger.warning("app/routers/design_v61 로드 실패", error=str(e))

# D3 설계변경 사전예측: /api/v1/design-risk/predict (착공 전 법규초과·누락·정합 예측 +
# 보완방안). 룰기반 우선·AI 보조(use_llm). 자체 prefix=/api/v1/design-risk(충돌0).
try:
    from apps.api.app.routers.design_risk import router as design_risk_router

    app.include_router(design_risk_router, tags=["설계변경 사전예측(D3)"])
except Exception as e:
    logger.warning("app/routers/design_risk 로드 실패", error=str(e))

# U6 설계심사(Design Audit): 개요 추출·심사 실행·결과 조회·리포트 PDF(S0~S7).
# U5 오케스트레이터는 라우터 내부 지연 임포트(미배포 시 run만 503 정직).
# 자체 prefix=/api/v1/design-audit(충돌0).
try:
    from apps.api.app.routers.design_audit import router as design_audit_router

    app.include_router(design_audit_router, tags=["설계심사(Design Audit)"])
except Exception as e:
    logger.warning("app/routers/design_audit 로드 실패", error=str(e))

# 매스 백본(P3.5-Data D1.5-wire): 건축물대장 종류별 매스 템플릿 수집(관리자)·조회(D2 소비).
# 자체 prefix=/api/v1/mass-templates(충돌0). 미배포 환경에서도 라우터 등록은 무중단.
try:
    from app.routers.mass_templates import router as mass_templates_router

    app.include_router(mass_templates_router, tags=["매스 백본"])
except Exception as e:
    logger.warning("app/routers/mass_templates 로드 실패", error=str(e))

# 프론트가 호출하나 미마운트였던 app/routers(자체 prefix 보유, 기존 라우트와 경로
# 충돌 0·대상경로 미존재 라이브확인). 프론트 호출 없는 agents는
# 표면 확대 방지로 미마운트(필요시 추후). v2_tax는 삭제됨(2026-07-12 정리 — v1 tax와
# 기능 중복 死모듈, TRIAGE_wiring_p2_2026-07-11.md G7 삭제후보). 각각 독립 try로 격리.
# ★rates 추가(2026-07-03): BimCostDashboard.tsx가 /api/v1/rates/current(법정요율)를 호출하는데
#   미마운트라 런타임 404였음 — stale 전제 정정(정찰 F1). cost는 위 g2b 블록에서 이미 마운트됨.
for _mod, _attr, _tag in [
    # avm 제거: /api/v1/avm/estimate는 이미 routers/avm.py(line 349, RBAC avm:read)로 마운트됨.
    # app/routers/avm.py(get_current_user, 권한체크 없음)를 중복 등록하면 경로 충돌 → 재정렬 시
    # RBAC 우회 위험. 정본 하나만 유지.
    ("apps.api.app.routers.external_api", "router", "외부 공공데이터"),
    ("apps.api.app.routers.finance", "router", "재무(몬테카를로)"),
    ("apps.api.app.routers.lifecycle", "router", "프로젝트 라이프사이클"),
    ("apps.api.app.routers.rates", "router", "v61 법정요율"),
]:
    try:
        import importlib as _il

        app.include_router(getattr(_il.import_module(_mod), _attr), tags=[_tag])
    except Exception as e:
        logger.warning("app/routers 로드 실패", module=_mod, error=str(e))

# ──────────────────────────────────────
# API v2 라우터
# ──────────────────────────────────────

app.include_router(v2_auth.router, prefix="/api/v2/auth", tags=["인증 v2"])
app.include_router(v2_projects.router, prefix="/api/v2/projects", tags=["프로젝트 v2"])
app.include_router(v2_design.router, prefix="/api/v2/design", tags=["설계 v2"])
if v2_feasibility_router is not None:
    app.include_router(v2_feasibility_router)  # 자체 prefix: /api/v2/feasibility
if v2_collaboration_router is not None:
    app.include_router(v2_collaboration_router)  # 자체 prefix: /api/v2/collaboration
if v2_review_comments_router is not None:
    app.include_router(v2_review_comments_router)  # 자체 prefix: /api/v2/collaboration
if v2_livekit_router is not None:
    app.include_router(v2_livekit_router)  # 자체 prefix: /api/v2/livekit
if pipeline_router is not None:
    app.include_router(pipeline_router)  # 자체 prefix: /api/v2/pipeline
if comprehensive_analysis_router is not None:
    app.include_router(comprehensive_analysis_router, prefix="/api/v2/analysis", tags=["종합 부지분석"])
    # 프론트(apiClient)는 /api/v1 접두 → v1 별칭 등록(404 해소: /analysis/llm-providers·/analysis/comprehensive)
    app.include_router(comprehensive_analysis_router, prefix="/api/v1/analysis", tags=["종합 부지분석 v1"])
if c2r_router is not None:
    # C2R: 라우터 자체 prefix="/c2r" → /api/v1/c2r/brief·/api/v1/c2r/render
    app.include_router(c2r_router, prefix="/api/v1")
if access_router is not None:
    # 접도·도로 기반(P4): 라우터 자체 prefix="/access" → /api/v1/access/assess
    app.include_router(access_router, prefix="/api/v1")
