"""인증 v2 라우터.

v1 인증 라우터를 재사용하며 v2 스키마 래퍼를 제공한다.
향후 OAuth2.0 PKCE, 생체인증 등 브레이킹 변경 시 분기 지점.
"""

from fastapi import APIRouter

from apps.api.routers.auth import router as v1_router

router = APIRouter()

# v1 라우터의 모든 경로를 v2에 포함 (현재 동일 동작)
for route in v1_router.routes:
    router.routes.append(route)
