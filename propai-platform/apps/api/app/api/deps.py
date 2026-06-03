"""v62 sales — 공용 의존성 재노출(실제 경로 매핑).

스펙은 app.api.deps 를 가정하나 실제 프로젝트는 get_db=app.core.database,
get_current_user=app.services.auth.auth_service 에 있어 여기서 단일 진입점으로 재노출한다.
"""

from app.core.database import get_db
from app.services.auth.auth_service import get_current_user

__all__ = ["get_db", "get_current_user"]
