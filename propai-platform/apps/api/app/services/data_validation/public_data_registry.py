"""
공공데이터 레지스트리 — 모든 외부 데이터 소스의 상태를 중앙 관리.
하드코딩 데이터 사용 시 반드시 이 레지스트리에서 '최신 여부'를 확인한 후 사용.
"""
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DataSourceStatus:
    """단일 데이터 소스의 상태."""
    def __init__(self, name: str, source_type: str, update_frequency: str):
        self.name = name
        self.source_type = source_type  # "api" | "hardcoded" | "db"
        self.update_frequency = update_frequency  # "realtime" | "daily" | "monthly" | "yearly"
        self.last_updated: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.record_count: int = 0
        self.is_healthy: bool = True

    def mark_updated(self, record_count: int = 0):
        self.last_updated = datetime.now()
        self.record_count = record_count
        self.is_healthy = True
        self.last_error = None

    def mark_error(self, error: str):
        self.last_error = error
        self.is_healthy = False
        logger.error(f"[DataRegistry] {self.name} 오류: {error}")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "update_frequency": self.update_frequency,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "last_error": self.last_error,
            "record_count": self.record_count,
            "is_healthy": self.is_healthy,
        }


class PublicDataRegistry:
    """공공데이터 레지스트리 싱글톤."""

    _instance: Optional["PublicDataRegistry"] = None

    def __init__(self):
        self.sources: dict[str, DataSourceStatus] = {}
        self._register_all_sources()

    @classmethod
    def get_instance(cls) -> "PublicDataRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _register_all_sources(self):
        """모든 공공데이터 소스 등록."""
        sources = [
            # API 기반 (실시간/주기적 갱신)
            ("molit_transactions", "api", "daily"),       # 국토부 실거래가
            ("molit_official_price", "api", "yearly"),    # 공시지가
            ("vworld_land_info", "api", "daily"),         # V-World 필지정보
            ("vworld_zoning", "api", "monthly"),          # 용도지역
            ("kma_weather", "api", "realtime"),           # 기상청
            ("mois_disaster_risk", "api", "monthly"),     # 재해위험
            ("court_registry", "api", "daily"),           # 등기정보
            ("kepco_energy", "api", "monthly"),           # 전력사용량
            ("molit_building_register", "api", "daily"),  # 건축HUB 건축물대장(표제부·세대/동/호·멸실/미준공)

            # 하드코딩 (수동 갱신 — 위험!)
            ("tax_acquisition_rates", "hardcoded", "yearly"),   # 취득세율
            ("tax_transfer_rates", "hardcoded", "yearly"),      # 양도세율
            ("tax_comprehensive_rates", "hardcoded", "yearly"), # 종합부동산세율
            ("tax_regional_fees", "hardcoded", "yearly"),       # 지역별 부담금
            ("construction_unit_costs", "hardcoded", "yearly"), # 공사비 단가
            ("beec_grade_thresholds", "hardcoded", "yearly"),   # BEEC 등급 기준
            ("zone_bcr_far_limits", "hardcoded", "yearly"),     # 건폐율/용적률 한도
        ]

        for name, source_type, frequency in sources:
            self.sources[name] = DataSourceStatus(name, source_type, frequency)

    def get_status(self, name: str) -> Optional[DataSourceStatus]:
        return self.sources.get(name)

    def get_all_status(self) -> list[dict]:
        return [s.to_dict() for s in self.sources.values()]

    def get_stale_sources(self) -> list[dict]:
        """오래된(갱신 필요) 데이터 소스 목록."""
        from .validator import FreshnessChecker

        stale = []
        for name, source in self.sources.items():
            if source.last_updated is None:
                stale.append({"name": name, "reason": "한 번도 갱신되지 않음"})
                continue

            # 데이터 타입에 맞는 신선도 확인
            data_type_map = {
                "molit_transactions": "transaction",
                "molit_official_price": "official_price",
                "vworld_zoning": "zoning",
                "tax_acquisition_rates": "tax_rate",
                "kma_weather": "weather",
            }
            data_type = data_type_map.get(name, "transaction")
            freshness = FreshnessChecker.check(data_type, source.last_updated)
            if not freshness["is_fresh"]:
                stale.append({"name": name, "reason": freshness["warning"]})

        return stale

    def get_hardcoded_warnings(self) -> list[dict]:
        """하드코딩된 데이터 소스에 대한 경고."""
        warnings = []
        for name, source in self.sources.items():
            if source.source_type == "hardcoded":
                warnings.append({
                    "name": name,
                    "warning": f"'{name}'은 하드코딩 데이터입니다. 법령 개정 시 수동 업데이트 필요.",
                    "last_updated": source.last_updated.isoformat() if source.last_updated else "미확인",
                    "recommendation": "공공 API 연동으로 자동화 권장",
                })
        return warnings
