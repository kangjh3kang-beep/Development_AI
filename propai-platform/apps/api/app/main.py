"""호환성 레이어 — apps.api.main 의 app 객체를 re-export.

기존에 `app.main:app`으로 참조하던 코드가 있을 수 있으므로
단일 엔트리포인트(apps.api.main)를 그대로 re-export한다.

프로덕션 Dockerfile CMD: uvicorn apps.api.main:app
"""

from apps.api.main import app  # noqa: F401 — re-export

__all__ = ["app"]
