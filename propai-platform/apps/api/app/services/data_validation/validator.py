"""
공공데이터 무결성 검증 레이어.
모든 외부 데이터는 이 검증기를 통과한 후에만 시스템에 입력된다.
"""
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)


# --- 실거래가 검증 스키마 ---
class TransactionRecord(BaseModel):
    """국토부 실거래가 레코드 검증."""
    deal_date: str  # YYYYMMDD
    price_10k_won: int  # 만원 단위
    area_sqm: float
    floor: int
    building_year: Optional[int] = None
    road_name: Optional[str] = None

    @field_validator("price_10k_won")
    @classmethod
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError(f"거래가는 양수여야 합니다: {v}")
        if v > 500_000:  # 50억 초과 = 이상치
            logger.warning(f"이상 거래가 감지: {v}만원 (50억 초과)")
        return v

    @field_validator("area_sqm")
    @classmethod
    def validate_area(cls, v):
        if v <= 0 or v > 1000:  # 1000m² 초과 = 이상치
            raise ValueError(f"면적 범위 초과: {v}m²")
        return v

    @field_validator("floor")
    @classmethod
    def validate_floor(cls, v):
        if v < -5 or v > 120:  # 지하5~120층 범위
            raise ValueError(f"층수 범위 초과: {v}")
        return v


# --- 공시지가 검증 ---
class OfficialLandPrice(BaseModel):
    """공시지가 레코드 검증."""
    pnu: str  # 19자리
    price_per_sqm: int  # 원/m²
    base_year: int
    land_category: str  # 전, 답, 대, 임, 잡 등

    @field_validator("pnu")
    @classmethod
    def validate_pnu(cls, v):
        if len(v) != 19 or not v.isdigit():
            raise ValueError(f"PNU는 19자리 숫자여야 합니다: {v}")
        return v

    @field_validator("price_per_sqm")
    @classmethod
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError(f"공시지가는 양수여야 합니다: {v}")
        if v > 100_000_000:  # m²당 1억 초과 = 검증 필요
            logger.warning(f"고가 공시지가: {v}원/m²")
        return v


# --- 세율 검증 ---
class TaxRateRecord(BaseModel):
    """세율 레코드 검증."""
    tax_type: str  # acquisition, transfer, comprehensive
    rate: float  # 0.0 ~ 1.0
    effective_date: str  # YYYY-MM-DD
    region_code: Optional[str] = None
    conditions: Optional[dict] = None

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, v):
        if v < 0 or v > 1.0:
            raise ValueError(f"세율은 0~100% 범위여야 합니다: {v}")
        return v


# --- 용도지역 검증 ---
class ZoningRecord(BaseModel):
    """용도지역 정보 검증."""
    pnu: str
    zone_type: str
    max_bcr: float  # 건폐율 상한 (%)
    max_far: float  # 용적률 상한 (%)
    max_height_m: Optional[float] = None

    @field_validator("max_bcr")
    @classmethod
    def validate_bcr(cls, v):
        if v <= 0 or v > 100:
            raise ValueError(f"건폐율은 0~100% 범위: {v}")
        return v

    @field_validator("max_far")
    @classmethod
    def validate_far(cls, v):
        if v <= 0 or v > 2000:  # 중심상업 1500% + 특례
            raise ValueError(f"용적률은 0~2000% 범위: {v}")
        return v


# --- 이상치 탐지 ---
class AnomalyDetector:
    """통계 기반 이상치 탐지."""

    @staticmethod
    def check_price_anomaly(
        price_10k: int,
        area_sqm: float,
        region: str,
        recent_prices: list[int],
    ) -> dict:
        """실거래가 이상치 탐지 (IQR 방식)."""
        if not recent_prices or len(recent_prices) < 5:
            return {"is_anomaly": False, "reason": "비교 데이터 부족"}

        price_per_sqm = price_10k * 10000 / area_sqm if area_sqm > 0 else 0
        recent_per_sqm = sorted(recent_prices)
        q1 = recent_per_sqm[len(recent_per_sqm) // 4]
        q3 = recent_per_sqm[3 * len(recent_per_sqm) // 4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        if price_per_sqm < lower or price_per_sqm > upper:
            return {
                "is_anomaly": True,
                "reason": f"m²당 {price_per_sqm:,.0f}원은 지역 범위({lower:,.0f}~{upper:,.0f}) 벗어남",
                "severity": "warning" if abs(price_per_sqm - (q1 + q3) / 2) < 2 * iqr else "critical",
            }
        return {"is_anomaly": False, "reason": ""}


# --- 데이터 신선도 검증 ---
class FreshnessChecker:
    """데이터 신선도(최신성) 검증."""

    FRESHNESS_RULES = {
        "transaction": 30,       # 실거래가: 30일 이내
        "official_price": 365,   # 공시지가: 1년 이내
        "zoning": 90,            # 용도지역: 90일 이내
        "tax_rate": 180,         # 세율: 6개월 이내
        "weather": 1,            # 기상: 1일 이내
        "energy_cert": 365,      # 에너지인증: 1년 이내
    }

    @classmethod
    def check(cls, data_type: str, last_updated: datetime) -> dict:
        max_age_days = cls.FRESHNESS_RULES.get(data_type, 30)
        age_days = (datetime.now() - last_updated).days
        is_fresh = age_days <= max_age_days

        return {
            "is_fresh": is_fresh,
            "age_days": age_days,
            "max_age_days": max_age_days,
            "data_type": data_type,
            "warning": None if is_fresh else f"{data_type} 데이터가 {age_days}일 전 것입니다 (기준: {max_age_days}일)",
        }
