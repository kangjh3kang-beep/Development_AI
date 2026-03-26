"""녹색건축 인증 자동 평가 서비스.

G-SEED(녹색건축인증), ZEB(제로에너지건축), LEED 인증 등급을 예측한다.

G-SEED 등급 기준:
- 최우수 (그린1등급): 74점 이상
- 우수 (그린2등급): 66점 이상
- 우량 (그린3등급): 58점 이상
- 일반 (그린4등급): 50점 이상

ZEB 등급:
- ZEB 1등급: 에너지 자립률 100% 이상
- ZEB 2등급: 에너지 자립률 80% 이상
- ZEB 3등급: 에너지 자립률 60% 이상
- ZEB 4등급: 에너지 자립률 40% 이상
- ZEB 5등급: 에너지 자립률 20% 이상

LEED 등급:
- Platinum: 80점 이상
- Gold: 60점 이상
- Silver: 50점 이상
- Certified: 40점 이상
"""

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BuildingGreenData:
    """녹색건축 평가를 위한 건물 데이터."""

    # 에너지
    energy_independence_rate: float  # 에너지 자립률 (0~1)
    primary_energy_demand_kwh_m2: float
    renewable_energy_ratio: float

    # 환경
    co2_reduction_rate: float  # CO2 감축률 (0~1)
    green_material_ratio: float  # 친환경 자재 비율 (0~1)
    indoor_air_quality_score: float  # 실내공기질 점수 (0~100)
    water_saving_rate: float  # 물 절약률 (0~1)
    waste_recycling_rate: float  # 폐기물 재활용률 (0~1)

    # 교통/토지
    public_transit_score: float  # 대중교통 접근성 (0~10)
    site_greenery_ratio: float  # 녹지율 (0~1)

    # 기타
    has_bems: bool  # BEMS 설치 여부
    has_ev_charging: bool  # 전기차 충전 시설


class GreenCertificationService:
    """녹색건축 인증 자동 평가 서비스."""

    @staticmethod
    def evaluate_gseed(data: BuildingGreenData) -> dict:
        """G-SEED 점수를 산출하고 등급을 예측한다.

        7대 평가 분야 (총 100점):
        - 토지이용 (10) + 교통 (8) + 에너지 (30) + 재료자원 (14)
        - 물환경 (10) + 유지관리 (12) + 실내환경 (16)
        """
        energy_score = min(
            30,
            data.energy_independence_rate * 15
            + data.renewable_energy_ratio * 10
            + (5 if data.has_bems else 0),
        )
        transport_score = min(8, data.public_transit_score * 0.8)
        land_score = min(10, data.site_greenery_ratio * 10)
        material_score = min(14, data.green_material_ratio * 10 + data.waste_recycling_rate * 4)
        water_score = min(10, data.water_saving_rate * 10)
        maintenance_score = min(12, 6 + (3 if data.has_bems else 0) + (3 if data.has_ev_charging else 0))
        indoor_score = min(16, data.indoor_air_quality_score * 0.16)

        total = round(
            energy_score + transport_score + land_score
            + material_score + water_score + maintenance_score + indoor_score,
            2,
        )

        if total >= 74:
            grade = "최우수 (그린1등급)"
        elif total >= 66:
            grade = "우수 (그린2등급)"
        elif total >= 58:
            grade = "우량 (그린3등급)"
        elif total >= 50:
            grade = "일반 (그린4등급)"
        else:
            grade = "미인증"

        return {
            "score": total,
            "grade": grade,
            "breakdown": {
                "에너지": round(energy_score, 2),
                "교통": round(transport_score, 2),
                "토지이용": round(land_score, 2),
                "재료자원": round(material_score, 2),
                "물환경": round(water_score, 2),
                "유지관리": round(maintenance_score, 2),
                "실내환경": round(indoor_score, 2),
            },
        }

    @staticmethod
    def evaluate_zeb(data: BuildingGreenData) -> dict:
        """ZEB 등급을 산출한다."""
        rate = data.energy_independence_rate
        if rate >= 1.0:
            grade = "ZEB 1등급"
        elif rate >= 0.8:
            grade = "ZEB 2등급"
        elif rate >= 0.6:
            grade = "ZEB 3등급"
        elif rate >= 0.4:
            grade = "ZEB 4등급"
        elif rate >= 0.2:
            grade = "ZEB 5등급"
        else:
            grade = "미인증"
        return {"energy_independence_rate": rate, "grade": grade}

    @staticmethod
    def evaluate_leed(data: BuildingGreenData) -> dict:
        """LEED 점수를 산출한다 (간이 평가)."""
        score = 0.0
        score += min(25, data.energy_independence_rate * 15 + data.renewable_energy_ratio * 10)
        score += min(10, data.water_saving_rate * 10)
        score += min(10, data.green_material_ratio * 10)
        score += min(10, data.site_greenery_ratio * 10)
        score += min(10, data.waste_recycling_rate * 10)
        score += min(10, data.public_transit_score)
        score += min(15, data.indoor_air_quality_score * 0.15)
        score += 5 if data.has_ev_charging else 0
        score += 5 if data.has_bems else 0
        score = round(min(100, score), 2)

        if score >= 80:
            grade = "Platinum"
        elif score >= 60:
            grade = "Gold"
        elif score >= 50:
            grade = "Silver"
        elif score >= 40:
            grade = "Certified"
        else:
            grade = "미인증"
        return {"score": score, "grade": grade}

    @staticmethod
    def evaluate_all(data: BuildingGreenData) -> dict:
        """전체 인증 평가 (G-SEED, ZEB, LEED)."""
        return {
            "gseed": GreenCertificationService.evaluate_gseed(data),
            "zeb": GreenCertificationService.evaluate_zeb(data),
            "leed": GreenCertificationService.evaluate_leed(data),
        }
