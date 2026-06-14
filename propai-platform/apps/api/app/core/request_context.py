"""요청 범위 컨텍스트 — 인증 사용자 ID를 LLM 호출 경로까지 전달.

미들웨어가 JWT에서 user_id를 추출해 set_current_user_id로 저장하면,
세션 없는 서비스(base_interpreter 등)에서도 get_current_user_id로 읽어
과금 누적·한도 차단을 적용할 수 있다.
"""

from contextvars import ContextVar

_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)
_current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


def set_current_user_id(user_id: str | None) -> None:
    _current_user_id.set(user_id)


def get_current_user_id() -> str | None:
    return _current_user_id.get()


def set_current_tenant_id(tenant_id: str | None) -> None:
    """현재 요청의 테넌트 ID를 저장(자가성장 텔레메트리 귀속용)."""
    _current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> str | None:
    return _current_tenant_id.get()
