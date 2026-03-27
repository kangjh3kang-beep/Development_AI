"""v44.0 건축 법규 검증 / 자동 보정 엔진 서비스 (G96~G99, 모듈 560).

건폐율, 용적률, 높이 제한, 벽체 경간 등을 검증하고
위반 시 자동 보정 대안을 생성한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DesignPoint:
    id: str
    x: float
    y: float


@dataclass
class DesignLine:
    id: str
    start_point_id: str
    end_point_id: str


@dataclass
class DesignSurface:
    id: str
    point_ids: list[str]


@dataclass
class DesignData:
    points: list[DesignPoint]
    lines: list[DesignLine]
    surfaces: list[DesignSurface]
    floor_count: int = 1
    building_height_m: float = 0.0
    scale: float = 10.0
    setback_distances: dict[str, float] | None = None  # {"north": 3.0, "south": 2.0, ...}
    north_setback_m: float = 0.0  # 정북방향 이격거리


@dataclass
class LegalLimits:
    building_coverage_ratio: float
    floor_area_ratio: float
    max_height_m: float
    min_setback_m: float
    sunlight_hours_min: float


@dataclass
class ComplianceViolation:
    type: Literal["building_coverage", "floor_area_ratio", "height", "setback", "sunlight", "structure"]
    message: str
    severity: Literal["error", "warning"]
    current_value: float = 0.0
    limit_value: float = 0.0


@dataclass
class CorrectionAlternative:
    alternative_id: str
    description: str
    corrected_design: dict[str, Any]
    estimated_cost_change_krw: int
    far_after: float
    bcr_after: float


class LegalRegulationVerifier:
    """건축법규 검증기: 건폐율, 용적률, 높이 제한."""

    def _compute_polygon_area_m2(self, points: list[DesignPoint], scale: float) -> float:
        n = len(points)
        if n < 3:
            return 0.0
        area_px = 0.0
        for i in range(n):
            j = (i + 1) % n
            area_px += points[i].x * points[j].y - points[j].x * points[i].y
        return abs(area_px) / 2.0 / (scale ** 2)

    def verify(self, design: DesignData, site_area_m2: float, limits: LegalLimits) -> list[ComplianceViolation]:
        violations: list[ComplianceViolation] = []
        point_map = {p.id: p for p in design.points}

        building_area_m2 = 0.0
        if design.surfaces:
            pts_1f = [point_map[pid] for pid in design.surfaces[0].point_ids if pid in point_map]
            building_area_m2 = self._compute_polygon_area_m2(pts_1f, design.scale)

        total_floor_area_m2 = building_area_m2 * design.floor_count

        bcr = building_area_m2 / site_area_m2 if site_area_m2 > 0 else 0
        if bcr > limits.building_coverage_ratio:
            violations.append(ComplianceViolation(
                type="building_coverage",
                message=f"건폐율 초과: 현재 {bcr * 100:.1f}%, 허용 {limits.building_coverage_ratio * 100:.1f}%",
                severity="error",
                current_value=bcr,
                limit_value=limits.building_coverage_ratio,
            ))

        far = total_floor_area_m2 / site_area_m2 if site_area_m2 > 0 else 0
        if far > limits.floor_area_ratio:
            violations.append(ComplianceViolation(
                type="floor_area_ratio",
                message=f"용적률 초과: 현재 {far * 100:.1f}%, 허용 {limits.floor_area_ratio * 100:.1f}%",
                severity="error",
                current_value=far,
                limit_value=limits.floor_area_ratio,
            ))

        if design.building_height_m > limits.max_height_m:
            violations.append(ComplianceViolation(
                type="height",
                message=f"높이 초과: 현재 {design.building_height_m:.1f}m, 허용 {limits.max_height_m:.1f}m",
                severity="error",
                current_value=design.building_height_m,
                limit_value=limits.max_height_m,
            ))

        # 세트백 검증
        if hasattr(design, 'setback_distances') and design.setback_distances:
            for side, distance in design.setback_distances.items():
                if distance < limits.min_setback_m:
                    violations.append(ComplianceViolation(
                        type="setback",
                        message=f"세트백 미달: {side}면 {distance:.1f}m (최소 {limits.min_setback_m}m)",
                        severity="error",
                        current_value=distance,
                        limit_value=limits.min_setback_m,
                    ))

        # 일조권 검증 (정북방향 이격거리)
        if design.building_height_m > 0 and hasattr(design, 'north_setback_m') and design.north_setback_m > 0:
            required_north = _calculate_north_setback(design.building_height_m)
            if design.north_setback_m < required_north:
                violations.append(ComplianceViolation(
                    type="sunlight",
                    message=f"일조권 이격거리 미달: {design.north_setback_m:.1f}m (최소 {required_north:.1f}m)",
                    severity="error",
                    current_value=design.north_setback_m,
                    limit_value=required_north,
                ))
        return violations


class StructuralAnalysisVerifier:
    """구조 검증기: 벽체 경간 한계."""

    WALL_SPAN_LIMIT_M = 6.0

    def _euclidean_dist(self, p1: DesignPoint, p2: DesignPoint) -> float:
        return math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)

    def verify(self, design: DesignData) -> list[ComplianceViolation]:
        violations: list[ComplianceViolation] = []
        point_map = {p.id: p for p in design.points}
        for line in design.lines:
            sp = point_map.get(line.start_point_id)
            ep = point_map.get(line.end_point_id)
            if sp and ep:
                span_m = self._euclidean_dist(sp, ep) / design.scale
                if span_m > self.WALL_SPAN_LIMIT_M:
                    violations.append(ComplianceViolation(
                        type="structure",
                        message=f"벽체 경간 초과: {span_m:.1f}m (허용 {self.WALL_SPAN_LIMIT_M}m)",
                        severity="warning",
                        current_value=span_m,
                        limit_value=self.WALL_SPAN_LIMIT_M,
                    ))
        return violations


class AutoCorrectionExecutor:
    """자동 보정 엔진: 위반 유형별 대안 생성."""

    def generate_alternatives(
        self,
        design: DesignData,
        violation: ComplianceViolation,
        site_area_m2: float,
        limits: LegalLimits,
    ) -> list[CorrectionAlternative]:
        alts: list[CorrectionAlternative] = []
        if violation.type == "building_coverage":
            scale = limits.building_coverage_ratio / violation.current_value
            c_pts = [{"id": p.id, "x": p.x * scale, "y": p.y * scale} for p in design.points]
            alts.append(CorrectionAlternative(
                alternative_id="A",
                description=f"건물 외곽선을 내측 축소해 건폐율 {limits.building_coverage_ratio * 100:.0f}% 준수",
                corrected_design={"points": c_pts},
                estimated_cost_change_krw=int(-50_000_000 * (1 - scale)),
                far_after=violation.current_value * design.floor_count / (site_area_m2 / 1),
                bcr_after=limits.building_coverage_ratio,
            ))
        elif violation.type == "height":
            alts.append(CorrectionAlternative(
                alternative_id="A",
                description=f"건물 높이를 {limits.max_height_m:.1f}m 이하로 조정",
                corrected_design={"building_height_m": limits.max_height_m},
                estimated_cost_change_krw=int(
                    -30_000_000 * (violation.current_value - limits.max_height_m) / violation.current_value
                ),
                far_after=0.0,
                bcr_after=violation.current_value,
            ))
        return alts


class BuildingComplianceService:
    """건축 법규 준수 검증 + 자동 보정 통합 서비스."""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._legal_verifier = LegalRegulationVerifier()
        self._structural_verifier = StructuralAnalysisVerifier()
        self._correction_executor = AutoCorrectionExecutor()

    async def _get_legal_limits(self, project_id: str) -> LegalLimits:
        return LegalLimits(
            building_coverage_ratio=0.60,
            floor_area_ratio=2.50,
            max_height_m=35.0,
            min_setback_m=1.0,
            sunlight_hours_min=2.0,
        )

    @staticmethod
    def get_zone_limits(zone_code: str) -> LegalLimits | None:
        """용도지역 코드로 법규 기본값을 조회한다.

        Args:
            zone_code: 용도지역 코드 (1R, 2R, 3R, GC, NC, QI, QR)

        Returns:
            해당 용도지역의 LegalLimits 또는 None
        """
        return ZONE_LIMITS.get(zone_code)

    async def _get_site_area(self, project_id: str) -> float:
        return 500.0

    async def check_compliance(self, project_id: str, design_raw: dict) -> dict:
        d = DesignData(
            points=[DesignPoint(**p) for p in design_raw.get("points", [])],
            lines=[DesignLine(**ln) for ln in design_raw.get("lines", [])],
            surfaces=[DesignSurface(**s) for s in design_raw.get("surfaces", [])],
            floor_count=design_raw.get("floor_count", 1),
            building_height_m=design_raw.get("building_height_m", 0.0),
            scale=design_raw.get("scale", 10.0),
        )
        limits = await self._get_legal_limits(project_id)
        site_area = await self._get_site_area(project_id)
        all_viol = self._legal_verifier.verify(d, site_area, limits) + self._structural_verifier.verify(d)
        return {
            "project_id": project_id,
            "violations": [
                {
                    "type": v.type,
                    "message": v.message,
                    "severity": v.severity,
                    "current_value": v.current_value,
                    "limit_value": v.limit_value,
                }
                for v in all_viol
            ],
            "compliant": len(all_viol) == 0,
        }

    async def auto_correct(self, project_id: str, design_raw: dict, violation_type: str) -> dict:
        d = DesignData(
            points=[DesignPoint(**p) for p in design_raw.get("points", [])],
            lines=[DesignLine(**ln) for ln in design_raw.get("lines", [])],
            surfaces=[DesignSurface(**s) for s in design_raw.get("surfaces", [])],
            floor_count=design_raw.get("floor_count", 1),
            building_height_m=design_raw.get("building_height_m", 0.0),
            scale=design_raw.get("scale", 10.0),
        )
        limits = await self._get_legal_limits(project_id)
        site_area = await self._get_site_area(project_id)
        legal_violations = self._legal_verifier.verify(d, site_area, limits)
        target = next((v for v in legal_violations if v.type == violation_type), None)
        alts = self._correction_executor.generate_alternatives(d, target, site_area, limits) if target else []
        return {
            "violation_type": violation_type,
            "alternatives": [
                {
                    "alternative_id": a.alternative_id,
                    "description": a.description,
                    "corrected_design": a.corrected_design,
                    "estimated_cost_change_krw": a.estimated_cost_change_krw,
                    "far_after": round(a.far_after, 3),
                    "bcr_after": round(a.bcr_after, 3),
                }
                for a in alts
            ],
        }


# ── 정북방향 이격거리 계산 (건축법 제61조) ──

def _calculate_north_setback(building_height_m: float) -> float:
    """건축법 제61조 기준 정북방향 이격거리를 산출한다.

    - 9m 이하: max(높이 * 0.5, 1.0)
    - 9m 초과: max((높이 - 9) * 0.5 + 4.5, 3.0)
      (9m까지 4.5m + 초과분 * 0.5, 최소 3.0m)

    Args:
        building_height_m: 건물 높이 (m)

    Returns:
        정북방향 최소 이격거리 (m)
    """
    if building_height_m <= 9.0:
        return max(building_height_m * 0.5, 1.0)
    else:
        return max((building_height_m - 9.0) * 0.5 + 4.5, 3.0)


# ── 7개 용도지역별 법규 기본값 ──

ZONE_LIMITS: dict[str, LegalLimits] = {
    "1R": LegalLimits(0.60, 1.00, 12.0, 1.0, 4.0),  # 제1종일반주거
    "2R": LegalLimits(0.60, 2.00, 18.0, 1.0, 3.0),  # 제2종일반주거
    "3R": LegalLimits(0.50, 3.00, 35.0, 1.5, 2.0),  # 제3종일반주거
    "GC": LegalLimits(0.60, 4.00, 50.0, 0.0, 0.0),  # 일반상업
    "NC": LegalLimits(0.60, 9.00, 60.0, 0.0, 0.0),  # 근린상업
    "QI": LegalLimits(0.60, 4.00, 35.0, 0.0, 0.0),  # 준공업
    "QR": LegalLimits(0.60, 5.00, 35.0, 1.0, 2.0),  # 준주거
}
