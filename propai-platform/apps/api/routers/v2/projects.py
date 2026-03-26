"""프로젝트 v2 라우터.

v1 프로젝트 라우터를 재사용하며 v2 스키마 래퍼를 제공한다.
향후 GraphQL 통합, 필드 변경 등 브레이킹 변경 시 분기 지점.
"""

from fastapi import APIRouter

from apps.api.routers.projects import router as v1_router

router = APIRouter()

for route in v1_router.routes:
    router.routes.append(route)
