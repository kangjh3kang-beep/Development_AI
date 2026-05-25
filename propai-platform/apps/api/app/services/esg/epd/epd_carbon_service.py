# re-export: 테스트 호환성을 위한 하위 패키지 경로
from app.services.esg.epd_carbon_service import EPDCarbonService, EPD_KOREA_DATABASE  # noqa: F401

__all__ = ["EPDCarbonService", "EPD_KOREA_DATABASE"]
