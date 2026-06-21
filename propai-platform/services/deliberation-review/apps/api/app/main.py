"""Phase 0 — FastAPI 앱 팩토리(헬스체크만). 비즈니스 라우터는 각 페이즈가 추가."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.settings import settings


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # 시작 시 플랫폼 관리자 시크릿(platform_secrets) 복호화→os.environ 오버레이(설정 시).
    # 마스터키(SECRET_STORE_KEY/APP_SECRET_KEY/JWT_SECRET_KEY) 미설정이면 건너뜀.
    from app.services.secrets.platform_secret_loader import has_master_key
    if settings.LOAD_PLATFORM_SECRETS and has_master_key():
        try:
            from app.db.session import async_session
            from app.services.secrets.platform_secret_loader import load_platform_secrets
            async with async_session() as session:
                result = await load_platform_secrets(session)
            from app.core.logging import logger
            logger.info("platform_secrets 오버레이", applied=result.get("applied_count"),
                        failed=result.get("failed"), denied=result.get("denied"),
                        key_index=result.get("key_index"), candidates=result.get("candidates"))
        except Exception as exc:  # noqa: BLE001 — 시크릿 로드 실패가 부팅을 막지 않음(graceful)
            from app.core.logging import logger
            logger.warning("platform_secrets 로드 실패(graceful)", err=str(exc)[:120])
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="propai-review", version="0.0.1", lifespan=_lifespan)

    # 프런트(플랫폼 /deliberation-review, 콘솔)가 크로스오리진으로 /analyze 호출 허용.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    # 레이트리밋(security) — 클라이언트별 분당 상한. 0=비활성(기본). 외부 1차출처 쿼터/비용 폭주 방어.
    from app.core.rate_limit import FixedWindowRateLimiter
    limiter = FixedWindowRateLimiter(settings.REQUESTS_PER_MINUTE)

    @app.middleware("http")
    async def _rate_limit(request, call_next):
        # /health는 가용성 프로브 → 면제. 키=인증 토큰(사용자 단위) 우선, 없으면 클라이언트 IP.
        if limiter.enabled and request.url.path != "/health":
            key = request.headers.get("authorization") or (request.client.host if request.client else "anon")
            if not limiter.check(key):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"detail": "rate_limit_exceeded", "retry_after_s": 60},
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from app.api.routes.report_routes import router as report_router
    app.include_router(report_router)

    from app.api.routes.analysis_routes import router as analysis_router
    app.include_router(analysis_router)

    from app.api.routes.ui_routes import router as ui_router
    app.include_router(ui_router)

    from app.api.routes.ops_routes import router as ops_router
    app.include_router(ops_router)

    from app.api.routes.reg_routes import router as reg_router
    app.include_router(reg_router)

    from app.api.routes.project_routes import router as project_router
    app.include_router(project_router)

    from app.api.routes.permit_routes import router as permit_router
    app.include_router(permit_router)

    return app


app = create_app()
