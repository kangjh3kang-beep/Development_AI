# re-export: 테스트 호환성을 위한 하위 패키지 경로
from app.services.esg.lca_service import LCAService  # noqa: F401

__all__ = ["LCAService"]
