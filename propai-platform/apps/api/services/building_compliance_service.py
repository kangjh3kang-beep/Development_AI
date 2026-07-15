"""v44.0 건축 법규 검증 / 자동 보정 엔진 서비스 (G96~G99, 모듈 560).

건폐율, 용적률, 높이 제한, 벽체 경간 등을 검증하고
위반 시 자동 보정 대안을 생성한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.common.sunlight_setback import required_north_setback_m
from app.services.zoning.legal_zone_limits import legal_limits_for


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
        """프로젝트 DB에서 법규 한도를 조회한다.

        프로젝트에 zone_type, max_bcr, max_far, max_height가 저장되어 있으면
        해당 값을 사용하고, 없으면 용도지역 기본값 → 최종 폴백 순서로 결정한다.
        """
        from sqlalchemy import select

        from apps.api.database.models.project import Project

        fallback = LegalLimits(
            building_coverage_ratio=0.60,
            floor_area_ratio=2.50,
            max_height_m=35.0,
            min_setback_m=1.0,
            sunlight_hours_min=2.0,
        )

        try:
            stmt = select(Project).where(Project.id == project_id)
            result = await self._db.execute(stmt)
            project = result.scalar_one_or_none()
        except Exception:
            return fallback

        if project is None:
            return fallback

        # 용도지역 기본값 조회
        zone_defaults = ZONE_LIMITS.get(project.zone_type or "") if project.zone_type else None

        bcr = float(project.max_bcr) / 100.0 if project.max_bcr else (
            zone_defaults.building_coverage_ratio if zone_defaults else fallback.building_coverage_ratio
        )
        far = float(project.max_far) / 100.0 if project.max_far else (
            zone_defaults.floor_area_ratio if zone_defaults else fallback.floor_area_ratio
        )
        max_h = float(project.max_height) if project.max_height else (
            zone_defaults.max_height_m if zone_defaults else fallback.max_height_m
        )
        min_setback = zone_defaults.min_setback_m if zone_defaults else fallback.min_setback_m
        sunlight = zone_defaults.sunlight_hours_min if zone_defaults else fallback.sunlight_hours_min

        return LegalLimits(
            building_coverage_ratio=bcr,
            floor_area_ratio=far,
            max_height_m=max_h,
            min_setback_m=min_setback,
            sunlight_hours_min=sunlight,
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
        """프로젝트 DB에서 대지면적을 조회한다. 없으면 500.0m2 폴백."""
        from sqlalchemy import select

        from apps.api.database.models.project import Project

        try:
            stmt = select(Project.total_area_sqm).where(Project.id == project_id)
            result = await self._db.execute(stmt)
            area = result.scalar_one_or_none()
            if area is not None and float(area) > 0:
                return float(area)
        except Exception:
            pass
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
    """건축법 제61조·시행령 제86조(2023.9.12 개정) 정북방향 이격거리(공용 산식).

    - 10m 이하: 1.5m 이상
    - 10m 초과: 해당 높이의 1/2 이상
    (구버전은 임계 9m + 저층에 높이/2를 적용해 저층을 과대 이격했음 → 법-정합 일원화.)

    Args:
        building_height_m: 건물 높이 (m)

    Returns:
        정북방향 최소 이격거리 (m)
    """
    return required_north_setback_m(building_height_m)


# ── 용도지역별 법규 기본값(정본 위임 — 하드코딩 금지) ──
# ★법정 상한(건폐율/용적률/높이)은 이 파일에 직접 쓰지 않고 국토계획법 시행령 §84/§85 정본
#   (legal_zone_limits SSOT = auto_zoning_service.ZONE_LIMITS 재노출)에서 파생한다.
#   과거 이 표는 제1종일반주거 용적률 100%(법정 200%)·일반상업 400%/50m(법정 1300%/무제한)
#   등 오값을 '법정 한도'로 노출해 persona 전문가 감사·check_compliance 폴백·building_compliance
#   라우터 LLM evidence 3곳에 합법 설계를 위반으로 오판정하는 오류를 주입했다 → 정본 단일출처로
#   일원화해 그림자(divergent copy)를 제거한다.
#   이격거리(min_setback)·일조(sunlight)는 용도지역 SSOT 밖(건축법 §61 등 별도 규칙)이라
#   검증 편의를 위한 전형 기본값을 주입한다(법정 상한 아님 — 조례·가로구역별 상이).

# 단축코드(1R…QR) → 정식 한글 용도지역명(정본 SSOT 키). persona가 단축코드로 조회하므로 유지.
_ZONE_CODE_TO_LEGAL_NAME: dict[str, str] = {
    "1R": "제1종일반주거지역",
    "2R": "제2종일반주거지역",
    "3R": "제3종일반주거지역",
    "GC": "일반상업지역",
    "NC": "근린상업지역",
    "QI": "준공업지역",
    "QR": "준주거지역",
}

# 이격거리(m)·일조시간(h) 기본값 — 용도지역 SSOT 외(건축법 별도). 법정 상한 아님.
# 종전 단축코드 7종 값을 유지(무회귀), 그 외 표준 용도지역은 보수 기본값(_DEFAULT_*).
_SETBACK_SUNLIGHT_BY_NAME: dict[str, tuple[float, float]] = {
    "제1종일반주거지역": (1.0, 4.0),
    "제2종일반주거지역": (1.0, 3.0),
    "제3종일반주거지역": (1.5, 2.0),
    "일반상업지역": (0.0, 0.0),
    "근린상업지역": (0.0, 0.0),
    "준공업지역": (0.0, 0.0),
    "준주거지역": (1.0, 2.0),
}
_DEFAULT_SETBACK_M = 1.0
_DEFAULT_SUNLIGHT_H = 2.0
_FLOOR_HEIGHT_M = 3.0  # 층고 근사(녹지 층수제한 → 실효 높이 환산)


def _legal_limits_dataclass(legal_name: str) -> LegalLimits | None:
    """정본(legal_zone_limits SSOT)의 법정 상한으로 LegalLimits를 구성한다.

    - 건폐율/용적률: 국토계획법 시행령 §84/§85 정본(퍼센트 → 0~1 비율/배수 환산).
    - 높이: 정본 max_height_m(전용주거 10/12m 등) → 없으면 층수제한(녹지 4층≈12m) →
            둘 다 없으면 float('inf')(상업·일반주거 등 무제한 — 가로구역·일조 별도 규율,
            design_audit_orchestrator와 동일 관례). 과거 일반상업 50m 오표기의 정본 교정.
    - 이격/일조: 용도지역 SSOT 밖(건축법 별도) → 전형 기본값 주입(법정 상한 아님).
    """
    legal = legal_limits_for(legal_name)
    if not legal:
        return None
    max_bcr_pct = legal.get("max_bcr_pct") or 0
    max_far_pct = legal.get("max_far_pct") or 0
    max_height_m = legal.get("max_height_m")
    max_floors = legal.get("max_floors")
    if max_height_m is not None:
        height = float(max_height_m)
    elif max_floors:
        height = round(max_floors * _FLOOR_HEIGHT_M, 1)  # 녹지 4층≈12m
    else:
        height = float("inf")  # 무제한(상업·일반주거 등) — 높이룰 비활성
    setback, sunlight = _SETBACK_SUNLIGHT_BY_NAME.get(
        legal_name, (_DEFAULT_SETBACK_M, _DEFAULT_SUNLIGHT_H)
    )
    return LegalLimits(
        building_coverage_ratio=max_bcr_pct / 100.0,
        floor_area_ratio=max_far_pct / 100.0,
        max_height_m=height,
        min_setback_m=setback,
        sunlight_hours_min=sunlight,
    )


def _build_zone_limits() -> dict[str, LegalLimits]:
    """정식 한글 용도지역명 전체 + 단축코드 별칭을 정본에서 파생(그림자 없음).

    한글명(check_compliance·router 소비)과 단축코드(persona 소비)를 모두 키로 노출하되,
    단축코드 엔트리는 정식명 엔트리 객체를 그대로 재사용해 drift가 구조적으로 불가능하게 한다.
    """
    from app.services.zoning.auto_zoning_service import ZONE_LIMITS as _SSOT

    table: dict[str, LegalLimits] = {}
    for legal_name in _SSOT:
        ll = _legal_limits_dataclass(legal_name)
        if ll is not None:
            table[legal_name] = ll
    for code, legal_name in _ZONE_CODE_TO_LEGAL_NAME.items():
        if legal_name in table:
            table[code] = table[legal_name]  # 동일 객체 재사용 → 값 일치 영구 보장
    return table


ZONE_LIMITS: dict[str, LegalLimits] = _build_zone_limits()
