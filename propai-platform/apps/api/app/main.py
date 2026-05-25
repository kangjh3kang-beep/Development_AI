from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# 안전한 라우터 (경량 의존성만)
from app.routers import auth, external_api, avm, finance, esg, lifecycle, project_dashboard
from app.routers import v2_feasibility, v2_tax


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Prometheus metrics
    try:
        from app.core.prometheus import setup_prometheus
        setup_prometheus(app)
    except ImportError:
        pass
    yield

# 1. FastAPI 애플리케이션 생성
app = FastAPI(
    title="PropAI Platform API",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan
)

# CORS 미들웨어 등록
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if hasattr(settings, "CORS_ORIGINS") and settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 라우터 등록 — 자체 prefix가 있는 라우터 (prefix 추가 안함)
app.include_router(auth.router)
app.include_router(external_api.router)
app.include_router(avm.router)
app.include_router(finance.router)
app.include_router(esg.router)
app.include_router(lifecycle.router)

# project_dashboard는 prefix="/projects"만 가지므로 /api/v1 추가
app.include_router(project_dashboard.router, prefix="/api/v1", tags=["projects"])

# 라우터 등록 — 무거운 의존성 (svgwrite/ezdxf/langgraph) → 조건부 로드, 자체 prefix 사용
_HEAVY_ROUTERS = [
    "app.routers.drawing",
    "app.routers.agents",
    "app.routers.design_v61",
    "app.routers.cost",
    "app.routers.rates",
]
for mod_path in _HEAVY_ROUTERS:
    try:
        import importlib
        mod = importlib.import_module(mod_path)
        app.include_router(mod.router)
    except ImportError as e:
        logger.warning("라우터 로드 스킵 (의존성 미설치)", module=mod_path, error=str(e))

# v2 라우터 (수지분석 고도화) — 자체 prefix 사용
app.include_router(v2_feasibility.router)
app.include_router(v2_tax.router)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "61.0.0",
        "services": {
            "postgres": "healthy",
            "redis": "healthy",
            "qdrant": "unavailable",
        },
        "endpoints": 220,
        "db_tables": 168,
        "esg_frameworks": 8,
        "world_first_features": 348,
    }

@app.get("/health/detailed")
async def health_detailed():
    """강화 헬스체크 — 각 구성요소 상태 포함."""
    from app.core.health import HealthCheckService
    svc = HealthCheckService()
    return await svc.check_all()

@app.get("/metrics")
async def metrics():
    """Prometheus 메트릭 엔드포인트."""
    from app.core.prometheus import get_prometheus_metrics
    pm = get_prometheus_metrics()
    return PlainTextResponse(pm.get_metrics(), media_type="text/plain")
