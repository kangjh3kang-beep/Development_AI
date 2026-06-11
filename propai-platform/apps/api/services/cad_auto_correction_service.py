"""CAD 파라메트릭 자동 보정 서비스.

건축물 설계안의 법규 적합성을 검증하고,
위반 시 자동 보정(용적률/건폐율/높이 조정)을 수행한다.

보정 루프:
1. 설계안 입력 (ComplianceBuildingModel — 별칭 BuildingModel)
2. 법규 기준 대비 검증 (RegulationLimit)
3. 위반 항목 감지
4. 자동 보정 (최대 100회 반복)
5. 보정된 설계안 반환

보정 우선순위:
1. 높이 초과 → 층수 감소
2. 용적률 초과 → 층수 감소 (이미 높이로 조정된 경우 건축면적 축소)
3. 건폐율 초과 → 건축면적 축소
"""

from dataclasses import dataclass, field
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ComplianceBuildingModel:
    """건축물 설계 모델 (법규 적합성 검증·자동 보정용 — 정본).

    면적·층수·층고로 건폐율(bcr)/용적률(far)/높이를 산출하는 '법규 보정'
    모델이다. CAD 매스 기하(width/depth/floor_area)를 다루는 동명 클래스
    ``app.services.cad.parametric_cad_service.BuildingModel``과는 별개 라이브
    경로다(병합 금지). 하위호환을 위해 모듈 끝에서 ``BuildingModel`` 별칭을
    유지하므로 기존 ``from ... import BuildingModel`` 호출은 그대로 동작한다.
    """

    site_area_sqm: float  # 대지면적
    building_area_sqm: float  # 건축면적
    num_floors: int  # 층수
    floor_height_m: float  # 층고 (m)
    # v57 신규 필드
    setback_distances: dict[str, float] | None = None  # {"north": 3.0, "south": 2.0, ...}
    min_floor_height_m: float = 2.7  # 최소 층고

    @property
    def gross_floor_area_sqm(self) -> float:
        """연면적."""
        return self.building_area_sqm * self.num_floors

    @property
    def bcr(self) -> float:
        """건폐율 (%)."""
        if self.site_area_sqm <= 0:
            return 0.0
        return round(self.building_area_sqm / self.site_area_sqm * 100, 2)

    @property
    def far(self) -> float:
        """용적률 (%)."""
        if self.site_area_sqm <= 0:
            return 0.0
        return round(self.gross_floor_area_sqm / self.site_area_sqm * 100, 2)

    @property
    def total_height_m(self) -> float:
        """건물 높이 (m)."""
        return self.num_floors * self.floor_height_m


@dataclass
class RegulationLimit:
    """법규 제한 기준."""

    max_bcr: float  # 건폐율 상한 (%)
    max_far: float  # 용적률 상한 (%)
    max_height_m: float  # 높이 상한 (m), 0이면 제한 없음


@dataclass
class Violation:
    """위반 사항."""

    item: str  # "bcr", "far", "height"
    current_value: float
    limit_value: float
    excess: float


@dataclass
class CorrectionResult:
    """보정 결과."""

    original: dict  # 원본 설계
    corrected: dict  # 보정된 설계
    violations_before: list[dict]
    violations_after: list[dict]
    iterations: int
    is_compliant: bool
    corrections_applied: list[str]


class CadAutoCorrectionService:
    """CAD 자동 보정 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def check_compliance(
        building: ComplianceBuildingModel, regulation: RegulationLimit
    ) -> list[Violation]:
        """법규 적합성을 검증한다."""
        violations = []

        if building.bcr > regulation.max_bcr:
            violations.append(
                Violation(
                    item="bcr",
                    current_value=building.bcr,
                    limit_value=regulation.max_bcr,
                    excess=round(building.bcr - regulation.max_bcr, 2),
                )
            )

        if building.far > regulation.max_far:
            violations.append(
                Violation(
                    item="far",
                    current_value=building.far,
                    limit_value=regulation.max_far,
                    excess=round(building.far - regulation.max_far, 2),
                )
            )

        if (
            regulation.max_height_m > 0
            and building.total_height_m > regulation.max_height_m
        ):
            violations.append(
                Violation(
                    item="height",
                    current_value=building.total_height_m,
                    limit_value=regulation.max_height_m,
                    excess=round(
                        building.total_height_m - regulation.max_height_m, 2
                    ),
                )
            )

        return violations

    @staticmethod
    def auto_correct(
        building: ComplianceBuildingModel,
        regulation: RegulationLimit,
        *,
        max_iter: int = 100,
    ) -> CorrectionResult:
        """자동 보정을 수행한다."""
        original = {
            "building_area_sqm": building.building_area_sqm,
            "num_floors": building.num_floors,
            "bcr": building.bcr,
            "far": building.far,
            "height_m": building.total_height_m,
        }
        violations_before = [
            {
                "item": v.item,
                "current": v.current_value,
                "limit": v.limit_value,
                "excess": v.excess,
            }
            for v in CadAutoCorrectionService.check_compliance(building, regulation)
        ]

        corrections: list[str] = []
        iteration_count = 0
        for i in range(max_iter):
            violations = CadAutoCorrectionService.check_compliance(
                building, regulation
            )
            if not violations:
                break
            iteration_count = i + 1

            for v in violations:
                if v.item == "height" and building.num_floors > 1:
                    max_floors = int(
                        regulation.max_height_m / building.floor_height_m
                    )
                    building.num_floors = max(1, max_floors)
                    corrections.append(
                        f"높이 초과: 층수 {original['num_floors']}→{building.num_floors}"
                    )

                elif v.item == "far" and building.num_floors > 1:
                    target_gfa = (
                        regulation.max_far / 100 * building.site_area_sqm
                    )
                    building.num_floors = max(
                        1, int(target_gfa / building.building_area_sqm)
                    )
                    corrections.append(f"용적률 초과: 층수→{building.num_floors}")

                elif v.item == "bcr":
                    max_building_area = (
                        regulation.max_bcr / 100 * building.site_area_sqm
                    )
                    building.building_area_sqm = round(max_building_area, 2)
                    corrections.append(
                        f"건폐율 초과: 건축면적→{building.building_area_sqm}㎡"
                    )

        violations_after = [
            {
                "item": v.item,
                "current": v.current_value,
                "limit": v.limit_value,
                "excess": v.excess,
            }
            for v in CadAutoCorrectionService.check_compliance(building, regulation)
        ]

        return CorrectionResult(
            original=original,
            corrected={
                "building_area_sqm": building.building_area_sqm,
                "num_floors": building.num_floors,
                "bcr": building.bcr,
                "far": building.far,
                "height_m": building.total_height_m,
            },
            violations_before=violations_before,
            violations_after=violations_after,
            iterations=iteration_count if violations_before else 0,
            is_compliant=len(violations_after) == 0,
            corrections_applied=corrections,
        )

    # ── v57 Phase 15 확장: 세트백/층고 최적화 ──

    @staticmethod
    def check_setback_compliance(
        building_model: "ComplianceBuildingModel",
        site_boundary: dict,
        min_setback_m: float,
    ) -> list[dict]:
        """세트백 준수 여부를 검증한다.

        건축물 각 면의 이격거리가 최소 세트백 기준을 충족하는지 검증한다.

        Args:
            building_model: 건축물 모델
            site_boundary: 대지 경계 정보
            min_setback_m: 최소 세트백 거리 (m)

        Returns:
            [{"side": str, "distance": float, "min_required": float, "compliant": bool}]
        """
        results = []
        if hasattr(building_model, "setback_distances") and building_model.setback_distances:
            for side, dist in building_model.setback_distances.items():
                results.append({
                    "side": side,
                    "distance": dist,
                    "min_required": min_setback_m,
                    "compliant": dist >= min_setback_m,
                })
        return results

    @staticmethod
    def optimize_floor_height(
        building_model: "ComplianceBuildingModel",
        max_height_m: float,
    ) -> dict:
        """층고를 최적화한다 (최소 2.7m 확보하면서 높이 제한 준수).

        최소 층고를 유지하면서 가능한 최대 층수를 산출하고,
        각 층의 최적 층고를 계산한다.

        Args:
            building_model: 건축물 모델
            max_height_m: 건물 높이 상한 (m)

        Returns:
            {"optimized_floor_height_m": float, "max_floors": int, "total_height_m": float}
        """
        min_h = getattr(building_model, "min_floor_height_m", 2.7)
        if min_h <= 0:
            min_h = 2.7
        max_floors = int(max_height_m / min_h)
        if max_floors <= 0:
            return {
                "optimized_floor_height_m": round(min_h, 2),
                "max_floors": 0,
                "total_height_m": 0.0,
            }
        optimal_height = max_height_m / max_floors
        optimal_height = max(optimal_height, min_h)
        actual_floors = int(max_height_m / optimal_height)
        return {
            "optimized_floor_height_m": round(optimal_height, 2),
            "max_floors": actual_floors,
            "total_height_m": round(optimal_height * actual_floors, 2),
        }


# ── 하위호환 별칭 ──
# 법규 보정 모델의 정본 이름은 ``ComplianceBuildingModel``이다(CAD 매스 기하용
# parametric_cad_service.BuildingModel과 구분). 기존 임포트
# (cad_correction.py·테스트의 ``from ... import BuildingModel``)를 깨지 않도록
# 동일 객체를 가리키는 별칭을 유지한다.
BuildingModel = ComplianceBuildingModel
