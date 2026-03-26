"""설계 v2 라우터.

v1 설계 라우터를 재사용하며 v2 스키마 래퍼를 제공한다.
향후 ControlNet 파이프라인, 실시간 협업 등 브레이킹 변경 시 분기 지점.
"""

from fastapi import APIRouter

from apps.api.routers.design import router as v1_router

router = APIRouter()

for route in v1_router.routes:
    router.routes.append(route)
