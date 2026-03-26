"""dt_service.py -> digital_twin_service.py 통합 리다이렉트.

이 모듈은 하위 호환성을 위해 존재합니다.
실제 구현은 digital_twin_service.py에 있습니다.
"""
from apps.api.services.digital_twin_service import DigitalTwinService  # noqa: F401
