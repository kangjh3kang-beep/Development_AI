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
    ai_costs,
    analytics,
    api_keys,
    ai_assistant,
    auction,
    auth,
    auto_zoning,
    billing,
    integration,
    market_report,
    avm,
    avm_vision,
    bim,
    blockchain,
    building_compliance,
    cad_correction,
    chatbot,
    climate,
    compliance,
    contracts,
    construction,
    contractors,
    cost_intelligence,
    dashboard,
    data_integrity,
    design,
    drawing,
    development_methods,
    digital_twin,
    domain_agents,
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
    kdx,
    lcc,
    lease_ops,
    leases,
    maintenance,
    market_ai,
    marketing,
    monte_carlo,
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
from apps.api.app.routers.bank_report import router as bank_report_router
from apps.api.app.routers.uploads import router as uploads_router
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
from apps.api.versioning import VersionHeaderMiddleware, create_latest_redirect_router

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 생명주기 관리. 시작 시 초기화, 종료 시 정리."""
    # ── 시작 ──
    setup_logging(json_output=settings.environment != "development")
    logger.info("PropAI API 시작", version=settings.app_version, env=settings.environment)

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

    # 관리자 화면에서 입력한 연동 API 키(platform_secrets)를 os.environ에 오버레이
    try:
        from apps.api.database.session import AsyncSessionLocal
        from app.services.secrets import secret_store
        async with AsyncSessionLocal() as _s:
            await secret_store.load_into_env(_s)
    except Exception:
        logger.warning("플랫폼 시크릿 env 로드 실패 — .env 값으로 시작")

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
        from apps.api.database.session import AsyncSessionLocal
        from apps.api.app.services.land_intelligence import presale_monitor_service as _mon
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

    yield

    # ── 종료 ──
    _t = getattr(app.state, "presale_monitor_task", None)
    if _t is not None:
        _t.cancel()
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


# 인증 사용자 ID를 요청 컨텍스트에 주입 (LLM 과금 누적·한도 차단용, best-effort)
@app.middleware("http")
async def _inject_user_context(request, call_next):
    from app.core.request_context import set_current_user_id

    set_current_user_id(None)
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        try:
            from apps.api.auth.jwt_handler import decode_token

            payload = decode_token(auth.split(" ", 1)[1].strip())
            if getattr(payload, "sub", None):
                set_current_user_id(str(payload.sub))
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
app.include_router(maintenance.router, prefix="/api/v1/maintenance", tags=["maintenance"])
app.include_router(tenant.router, prefix="/api/v1/tenant", tags=["tenant-experience"])
app.include_router(digital_twin.router, prefix="/api/v1/digital-twin", tags=["digital-twin"])
app.include_router(portals.router, prefix="/api/v1/portals", tags=["portals"])
app.include_router(chatbot.router, prefix="/api/v1/chatbot", tags=["chatbot"])
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
app.include_router(monte_carlo.router, prefix="/api/v1/monte-carlo", tags=["Monte Carlo 시뮬레이션"])
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

# 프론트가 호출하나 미마운트였던 app/routers 4종(자체 prefix 보유, 기존 라우트와 경로
# 충돌 0·대상경로 미존재 라이브확인). 프론트 호출 없는 agents/cost/rates/v2_tax는
# 표면 확대 방지로 미마운트(필요시 추후). 각각 독립 try로 격리.
for _mod, _attr, _tag in [
    # avm 제거: /api/v1/avm/estimate는 이미 routers/avm.py(line 349, RBAC avm:read)로 마운트됨.
    # app/routers/avm.py(get_current_user, 권한체크 없음)를 중복 등록하면 경로 충돌 → 재정렬 시
    # RBAC 우회 위험. 정본 하나만 유지.
    ("apps.api.app.routers.external_api", "router", "외부 공공데이터"),
    ("apps.api.app.routers.finance", "router", "재무(몬테카를로)"),
    ("apps.api.app.routers.lifecycle", "router", "프로젝트 라이프사이클"),
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
if pipeline_router is not None:
    app.include_router(pipeline_router)  # 자체 prefix: /api/v2/pipeline
if comprehensive_analysis_router is not None:
    app.include_router(comprehensive_analysis_router, prefix="/api/v2/analysis", tags=["종합 부지분석"])
    # 프론트(apiClient)는 /api/v1 접두 → v1 별칭 등록(404 해소: /analysis/llm-providers·/analysis/comprehensive)
    app.include_router(comprehensive_analysis_router, prefix="/api/v1/analysis", tags=["종합 부지분석 v1"])
