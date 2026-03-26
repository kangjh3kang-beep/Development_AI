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
    agents,
    ai_costs,
    api_keys,
    auction,
    auth,
    avm,
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
    design,
    development_methods,
    digital_twin,
    domain_agents,
    drone,
    energy,
    esg,
    esign,
    eu_taxonomy,
    facility_reservations,
    finance,
    kdx,
    lcc,
    leases,
    maintenance,
    marketing,
    monte_carlo,
    notifications,
    parking,
    permits,
    portals,
    projects,
    re100,
    regulation,
    reports,
    risk,
    safety,
    sre,
    system,
    tax,
    tenant,
    underwriting,
    webhooks,
    webrtc,
)
from apps.api.routers.v2 import auth as v2_auth
from apps.api.routers.v2 import design as v2_design
from apps.api.routers.v2 import projects as v2_projects
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

    # Qdrant 컬렉션 초기화
    try:
        qdrant_results = await init_qdrant_collections()
        logger.info("Qdrant 초기화 완료", collections=qdrant_results)
    except Exception:
        logger.warning("Qdrant 초기화 실패 — 서비스 없이 시작")

    # DB 풀 크기 메트릭 설정
    DB_POOL_SIZE.set(settings.db_pool_size)

    yield

    # ── 종료 ──
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
    except Exception:
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
app.include_router(projects.router, prefix="/api/v1/projects", tags=["프로젝트"])
app.include_router(avm.router, prefix="/api/v1/avm", tags=["AVM 시세추정"])
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

# ──────────────────────────────────────
# API v2 라우터
# ──────────────────────────────────────

app.include_router(v2_auth.router, prefix="/api/v2/auth", tags=["인증 v2"])
app.include_router(v2_projects.router, prefix="/api/v2/projects", tags=["프로젝트 v2"])
app.include_router(v2_design.router, prefix="/api/v2/design", tags=["설계 v2"])
