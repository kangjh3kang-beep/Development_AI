"""AI 자동 설계 생성 엔진.

토지면적과 법규(용도지역)에 맞춰 최적의 건축 매스 + 평면 배치를 자동 생성한다.

알고리즘 5단계:
1. 법규 한도 자동 조회 (ZONE_LIMITS)
2. 유효 건축 영역 → 최적 매스 산출
3. 코어 + 복도 자동 배치
4. 세대/호실 자동 배분
5. DesignPayload 형식 변환 (프론트 CAD 스토어 호환)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import structlog

logger = structlog.get_logger(__name__)


# ── 법규 한도 (building_compliance_service.ZONE_LIMITS 동등) ──

class LegalLimits(NamedTuple):
    """용도지역별 법규 한도."""
    building_coverage_ratio: float  # 건폐율 (0~1)
    floor_area_ratio: float  # 용적률 (0~N)
    max_height_m: float  # 최고 높이 (m)
    min_setback_m: float  # 최소 이격거리 (m)
    sunlight_hours: float  # 일조시간 (h)


ZONE_LIMITS: dict[str, LegalLimits] = {
    "1R": LegalLimits(0.60, 2.00, 20.0, 1.5, 4.0),  # 제1종일반주거
    "2R": LegalLimits(0.60, 2.00, 35.0, 1.0, 2.0),  # 제2종일반주거
    "3R": LegalLimits(0.50, 3.00, 50.0, 1.0, 2.0),  # 제3종일반주거
    "GC": LegalLimits(0.60, 10.00, 0.0, 0.0, 0.0),  # 일반상업 (높이 무제한)
    "NC": LegalLimits(0.60, 9.00, 0.0, 0.5, 0.0),  # 근린상업
    "QI": LegalLimits(0.60, 4.00, 0.0, 1.0, 0.0),  # 준공업
    "QR": LegalLimits(0.60, 5.00, 0.0, 1.0, 0.0),  # 준주거
}

_DEFAULT_LIMITS = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)


# ── 건축물 용도별 상수 ──

CORRIDOR_WIDTHS: dict[str, float] = {
    "공동주택": 1.8,
    "근린생활시설": 2.4,
    "업무시설": 2.4,
    "판매시설": 3.0,
    "숙박시설": 2.0,
}

CORE_AREA_SQM = 25.0  # 코어 1개당 면적 (계단+EV+파이프)
CORE_PER_FLOOR_AREA = 1500.0  # 연면적 N sqm당 코어 1개 (피난규칙)

UNIT_TYPES: dict[str, float] = {
    "39A": 39.0,
    "49A": 49.0,
    "59A": 59.0,
    "74A": 74.0,
    "84A": 84.0,
    "114A": 114.0,
}

PARKING_RULES: dict[str, dict[str, Any]] = {
    "공동주택": {"per_unit": True, "rate": 1.0, "area_per_car_sqm": 33.0},
    "근린생활시설": {"per_unit": False, "rate_per_sqm": 100, "area_per_car_sqm": 33.0},
    "업무시설": {"per_unit": False, "rate_per_sqm": 150, "area_per_car_sqm": 33.0},
}


@dataclass
class SiteInput:
    """대지 입력 정보."""

    site_area_sqm: float
    site_shape: list[dict[str, float]] | None = None  # [{x, y}, ...]
    site_width_m: float = 0.0  # 대지 폭 (자동 산출 가능)
    site_depth_m: float = 0.0  # 대지 깊이 (자동 산출 가능)
    zone_code: str = "2R"
    building_use: str = "공동주택"
    target_unit_types: list[str] = field(default_factory=lambda: ["84A"])
    floor_height_m: float = 3.0
    setback_m: dict[str, float] = field(
        default_factory=lambda: {"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5}
    )
    # P5: 정북일조 사선제한 "단계후퇴" 모드. True면 단일 세트백 높이캡 대신 층별 북측
    # 후퇴(상부일수록 더 후퇴)로 더 높게 짓고 상부 세대의 일조를 확보한다(결정론).
    daylight_step: bool = False


@dataclass
class DesignResult:
    """자동 설계 결과."""

    design_payload: dict[str, Any]  # 프론트 DesignPayload 호환
    summary: dict[str, Any]
    compliance: dict[str, Any]
    alternatives: list[dict[str, Any]] = field(default_factory=list)


def compute_north_step_profile(
    building_w: float,
    building_d: float,
    max_floors: int,
    floor_height_m: float,
    base_north_m: float,
    max_total_floor_area: float,
) -> tuple[list[dict[str, float]], float, int]:
    """정북일조 사선제한 단계후퇴 프로파일을 산출한다(결정론).

    한국 건축법 정북일조: 어떤 높이 h의 외벽은 정북 인접대지경계선에서 h/2 이상 이격
    (최소 1.5m). 따라서 층의 윗변 높이 h=층수×층고에 대해 필요 북측 이격 d=max(base, h/2).
    base(=설계 북측 세트백)를 넘는 만큼(inset)만 상부 층이 북쪽으로 후퇴한다.

    Returns: (profile, 단계후퇴 반영 총연면적, 실제 층수)
      profile[f] = {floor, north_setback_m, inset_m, depth_m}
    """
    profile: list[dict[str, float]] = []
    area = 0.0
    n = 0
    min_depth = max(4.0, building_d * 0.35)  # 후퇴해도 세대 성립 최소 깊이
    for f in range(1, max(1, max_floors) + 1):
        top_h = f * floor_height_m
        req_north = max(base_north_m, top_h / 2.0)  # 정북일조: 높이/2
        inset = max(0.0, req_north - base_north_m)
        depth_f = building_d - inset
        if depth_f < min_depth:
            break  # 더 후퇴하면 세대 불가 → 이 층부터 못 올림
        af = building_w * depth_f
        if max_total_floor_area > 0 and area + af > max_total_floor_area:
            break  # 용적률 초과 → 중단
        area += af
        n += 1
        profile.append({
            "floor": f,
            "north_setback_m": round(req_north, 2),
            "inset_m": round(inset, 2),
            "depth_m": round(depth_f, 1),
        })
    if n == 0:  # 최소 1층 보장
        profile = [{"floor": 1, "north_setback_m": round(base_north_m, 2),
                    "inset_m": 0.0, "depth_m": round(building_d, 1)}]
        area = building_w * building_d
        n = 1
    return profile, round(area, 2), n


class AutoDesignEngineService:
    """AI 자동 설계 생성 엔진."""

    # ── 1단계: 법규 한도 조회 ──

    @staticmethod
    def get_legal_limits(zone_code: str) -> dict[str, Any]:
        """용도지역 코드로 법규 한도를 조회한다.

        주의: 본 한도는 ZONE_LIMITS의 국토계획법 시행령 '법정 상한' 기준이며,
        지자체 도시계획조례·지구단위계획 가감을 반영하지 않는다(설계엔진 경로 한정).
        조례 실효 한도가 필요한 정밀 산정은 feasibility_service_v2(ordinance_far_pct/
        ordinance_bcr_pct, land_info_service 출처)를 사용한다. 출처를 정직 표기한다.
        """
        limits = ZONE_LIMITS.get(zone_code)
        is_known = limits is not None
        if not is_known:
            logger.warning("알 수 없는 용도지역 코드, 기본값 사용", zone_code=zone_code)
            limits = _DEFAULT_LIMITS
        return {
            "max_bcr_percent": round(limits.building_coverage_ratio * 100, 2),
            "max_far_percent": round(limits.floor_area_ratio * 100, 2),
            "max_height_m": limits.max_height_m,
            "min_setback_m": limits.min_setback_m,
            "sunlight_hours": limits.sunlight_hours,
            # 정직 출처 표기 — 조례 미반영 법정상한, 미지정 코드는 기본값 폴백
            "limits_source": "statutory_default" if is_known else "fallback_default",
            "ordinance_applied": False,
            "warnings": ([] if is_known else [f"미지정 용도지역 코드 '{zone_code}' — 기본값 적용"]) + [
                "지자체 조례·지구단위계획 가감 미반영(법정 상한 기준). 조례 실효 한도는 v2 수지엔진 참조.",
            ],
        }

    # ── 2단계: 유효 건축 영역 + 최적 매스 ──

    @staticmethod
    def compute_effective_site(
        site_input: SiteInput,
    ) -> dict[str, float]:
        """세트백 반영 후 유효 건축 가능 영역을 산출한다."""
        sb = site_input.setback_m

        # 대지 치수 추정 (정사각형 가정, site_shape 있으면 바운딩박스 사용)
        if site_input.site_width_m > 0 and site_input.site_depth_m > 0:
            w = site_input.site_width_m
            d = site_input.site_depth_m
        elif site_input.site_shape and len(site_input.site_shape) >= 3:
            xs = [p["x"] for p in site_input.site_shape]
            ys = [p["y"] for p in site_input.site_shape]
            w = max(xs) - min(xs)
            d = max(ys) - min(ys)
        else:
            side = math.sqrt(site_input.site_area_sqm)
            w = side
            d = side

        eff_w = max(0, w - sb.get("east", 1.5) - sb.get("west", 1.5))
        eff_d = max(0, d - sb.get("north", 3.0) - sb.get("south", 2.0))
        effective_area = eff_w * eff_d

        return {
            "site_width_m": round(w, 2),
            "site_depth_m": round(d, 2),
            "effective_width_m": round(eff_w, 2),
            "effective_depth_m": round(eff_d, 2),
            "effective_area_sqm": round(effective_area, 2),
        }

    @staticmethod
    def compute_optimal_mass(
        site_input: SiteInput,
        effective: dict[str, float],
        legal: dict[str, float],
    ) -> dict[str, Any]:
        """법규 제약 하 최적 건축 매스를 산출한다."""
        site_area = site_input.site_area_sqm
        eff_area = effective["effective_area_sqm"]

        max_bcr = legal["max_bcr_percent"] / 100.0
        max_far = legal["max_far_percent"] / 100.0
        max_height = legal["max_height_m"]

        # 건폐율 제약 → 최대 건축면적
        max_footprint = site_area * max_bcr
        building_footprint = min(max_footprint, eff_area)

        # 건물 치수 (유효 영역 내 직사각형)
        eff_w = effective["effective_width_m"]
        eff_d = effective["effective_depth_m"]

        if eff_w * eff_d > 0:
            scale = math.sqrt(building_footprint / (eff_w * eff_d))
            building_w = round(eff_w * min(scale, 1.0), 1)
            building_d = round(eff_d * min(scale, 1.0), 1)
        else:
            building_w = 0
            building_d = 0

        actual_footprint = building_w * building_d

        # 용적률 제약 → 최대 연면적 → 최대 층수
        max_total_floor = site_area * max_far
        max_floors_by_far = (
            int(max_total_floor / actual_footprint)
            if actual_footprint > 0
            else 1
        )

        # 높이 제약 → 최대 층수
        max_floors_by_height = (
            int(max_height / site_input.floor_height_m)
            if max_height > 0
            else 100
        )

        north_setback = site_input.setback_m.get("north", 3.0)
        fh = site_input.floor_height_m
        north_step_profile: list[dict[str, float]] | None = None

        if getattr(site_input, "daylight_step", False):
            # 정북일조 "단계후퇴" 모드: 단일 세트백 높이캡을 쓰지 않고(FAR·높이 한도만),
            # 상부 층을 북쪽으로 후퇴시켜 더 높이 짓고 일조를 확보(결정론 사선제한).
            base_north = max(1.5, north_setback)
            cap_floors = max(1, min(max_floors_by_far * 3, max_floors_by_height))  # 후퇴로 더 높이 가능
            north_step_profile, total_floor_area, num_floors = compute_north_step_profile(
                building_w, building_d, cap_floors, fh, base_north, max_total_floor,
            )
            building_height = num_floors * fh
        else:
            # 정북방향 일조권 제약(기존: 단일 세트백 기준 높이 하드캡)
            max_height_by_sunlight = 100.0  # 기본 무제한
            if north_setback > 0:
                if north_setback <= 4.5:
                    max_height_by_sunlight = north_setback * 2.0
                else:
                    max_height_by_sunlight = (north_setback - 4.5) * 2.0 + 9.0
            max_floors_by_sunlight = int(max_height_by_sunlight / fh)
            num_floors = max(1, min(max_floors_by_far, max_floors_by_height, max_floors_by_sunlight))
            total_floor_area = actual_footprint * num_floors
            building_height = num_floors * fh

        bcr = round(actual_footprint / site_area * 100, 2) if site_area > 0 else 0
        far = round(total_floor_area / site_area * 100, 2) if site_area > 0 else 0

        result: dict[str, Any] = {
            "building_width_m": building_w,
            "building_depth_m": building_d,
            "building_footprint_sqm": round(actual_footprint, 2),
            "num_floors": num_floors,
            "floor_height_m": fh,
            "building_height_m": round(building_height, 2),
            "total_floor_area_sqm": round(total_floor_area, 2),
            "bcr_pct": bcr,
            "far_pct": far,
            "max_bcr_pct": legal["max_bcr_percent"],
            "max_far_pct": legal["max_far_percent"],
            "max_height_m": max_height,
        }
        if north_step_profile is not None:
            result["north_step_profile"] = north_step_profile
            result["daylight_step"] = True
        return result

    # ── 3단계: 코어 + 복도 배치 ──

    @staticmethod
    def compute_core_layout(
        mass: dict[str, Any],
        building_use: str,
    ) -> dict[str, Any]:
        """코어 수, 복도폭, 위치를 산출한다."""
        total_floor = mass["total_floor_area_sqm"]
        num_cores = max(1, math.ceil(total_floor / CORE_PER_FLOOR_AREA))
        corridor_w = CORRIDOR_WIDTHS.get(building_use, 1.8)

        bw = mass["building_width_m"]
        bd = mass["building_depth_m"]

        # 코어 위치: 건물 중심축에 등분 배치
        core_positions: list[dict[str, float]] = []
        if num_cores == 1:
            core_positions.append({"x": round(bw / 2, 1), "y": round(bd / 2, 1)})
        else:
            spacing = bw / (num_cores + 1)
            for i in range(num_cores):
                core_positions.append({
                    "x": round(spacing * (i + 1), 1),
                    "y": round(bd / 2, 1),
                })

        total_core_area = num_cores * CORE_AREA_SQM
        corridor_area = bw * corridor_w  # 중복도 기준

        return {
            "num_cores": num_cores,
            "core_area_sqm": round(total_core_area, 2),
            "corridor_width_m": corridor_w,
            "corridor_area_sqm": round(corridor_area, 2),
            "core_positions": core_positions,
        }

    # ── 4단계: 세대/호실 자동 배분 ──

    @staticmethod
    def compute_unit_layout(
        mass: dict[str, Any],
        core_layout: dict[str, Any],
        target_unit_types: list[str],
        building_use: str,
    ) -> dict[str, Any]:
        """세대 유형별 배분을 산출한다."""
        footprint = mass["building_footprint_sqm"]
        net_area_per_floor = footprint - core_layout["core_area_sqm"] - core_layout["corridor_area_sqm"]
        net_area_per_floor = max(0, net_area_per_floor)

        units: list[dict[str, Any]] = []
        total_units = 0

        if building_use == "공동주택" and target_unit_types:
            # 세대 유형별 균등 배분
            type_areas = [UNIT_TYPES.get(t, 84.0) for t in target_unit_types]
            avg_area = sum(type_areas) / len(type_areas) if type_areas else 84.0

            units_per_floor = max(1, int(net_area_per_floor / avg_area))

            for ut in target_unit_types:
                unit_area = UNIT_TYPES.get(ut, 84.0)
                count_per_floor = max(1, units_per_floor // len(target_unit_types))
                total = count_per_floor * mass["num_floors"]
                units.append({
                    "type": ut,
                    "area_sqm": unit_area,
                    "count_per_floor": count_per_floor,
                    "total_count": total,
                })
                total_units += total
        else:
            # 비주거: 호실 면적 기준
            room_area = 50.0  # 기본 호실 면적
            rooms_per_floor = max(1, int(net_area_per_floor / room_area))
            total_units = rooms_per_floor * mass["num_floors"]
            units.append({
                "type": "일반",
                "area_sqm": room_area,
                "count_per_floor": rooms_per_floor,
                "total_count": total_units,
            })

        # 주차 대수 산정
        parking = _compute_parking(total_units, mass["total_floor_area_sqm"], building_use)

        return {
            "net_area_per_floor_sqm": round(net_area_per_floor, 2),
            "units": units,
            "total_units": total_units,
            "parking_required": parking["required"],
            "parking_area_sqm": parking["area_sqm"],
            "basement_floors_for_parking": parking["basement_floors"],
        }

    # ── 5단계: DesignPayload 변환 ──

    @staticmethod
    def to_design_payload(
        site_input: SiteInput,
        effective: dict[str, float],
        mass: dict[str, Any],
        core_layout: dict[str, Any],
        unit_layout: dict[str, Any],
    ) -> dict[str, Any]:
        """프론트 CAD 스토어 호환 DesignPayload를 생성한다."""
        scale = 10.0  # 1m = 10px
        sb = site_input.setback_m
        bw = mass["building_width_m"]
        bd = mass["building_depth_m"]

        # 세트백 오프셋
        ox = sb.get("west", 1.5) * scale
        oy = sb.get("north", 3.0) * scale

        points: list[dict[str, Any]] = []
        lines: list[dict[str, Any]] = []
        surfaces: list[dict[str, Any]] = []

        # 건물 외곽선 (폴리곤)
        corners = [
            {"id": "pt-b0", "x": ox, "y": oy},
            {"id": "pt-b1", "x": ox + bw * scale, "y": oy},
            {"id": "pt-b2", "x": ox + bw * scale, "y": oy + bd * scale},
            {"id": "pt-b3", "x": ox, "y": oy + bd * scale},
        ]
        points.extend(corners)
        surfaces.append({
            "id": "pg-building",
            "point_ids": [c["id"] for c in corners],
        })

        # 외벽 라인
        for i in range(4):
            j = (i + 1) % 4
            lines.append({
                "id": f"ln-wall-{i}",
                "start_point_id": corners[i]["id"],
                "end_point_id": corners[j]["id"],
            })

        # 복도 (중앙 수평선)
        corr_w = core_layout["corridor_width_m"]
        corr_y = oy + (bd * scale) / 2
        p_cl = {"id": "pt-corr-l", "x": ox, "y": corr_y}
        p_cr = {"id": "pt-corr-r", "x": ox + bw * scale, "y": corr_y}
        points.extend([p_cl, p_cr])
        lines.append({
            "id": "ln-corridor",
            "start_point_id": p_cl["id"],
            "end_point_id": p_cr["id"],
        })

        # 코어 (사각형)
        for i, cp in enumerate(core_layout["core_positions"]):
            core_size = math.sqrt(CORE_AREA_SQM) * scale
            cx = ox + cp["x"] * scale - core_size / 2
            cy = oy + cp["y"] * scale - core_size / 2

            core_pts = [
                {"id": f"pt-core-{i}-0", "x": round(cx, 1), "y": round(cy, 1)},
                {"id": f"pt-core-{i}-1", "x": round(cx + core_size, 1), "y": round(cy, 1)},
                {"id": f"pt-core-{i}-2", "x": round(cx + core_size, 1), "y": round(cy + core_size, 1)},
                {"id": f"pt-core-{i}-3", "x": round(cx, 1), "y": round(cy + core_size, 1)},
            ]
            points.extend(core_pts)
            surfaces.append({
                "id": f"pg-core-{i}",
                "point_ids": [p["id"] for p in core_pts],
            })

        # 세대 구분선 (상부/하부 각각)
        total_units_per_side = sum(
            u["count_per_floor"] for u in unit_layout["units"]
        )
        units_top = total_units_per_side // 2
        units_bottom = total_units_per_side - units_top

        if units_top > 1:
            unit_w = bw * scale / units_top
            for i in range(1, units_top):
                x = ox + i * unit_w
                pid_top = f"pt-udiv-t-{i}"
                pid_bot = f"pt-udiv-tb-{i}"
                points.append({"id": pid_top, "x": round(x, 1), "y": oy})
                points.append({"id": pid_bot, "x": round(x, 1), "y": corr_y})
                lines.append({
                    "id": f"ln-udiv-t-{i}",
                    "start_point_id": pid_top,
                    "end_point_id": pid_bot,
                })

        if units_bottom > 1:
            unit_w = bw * scale / units_bottom
            for i in range(1, units_bottom):
                x = ox + i * unit_w
                pid_top = f"pt-udiv-b-{i}"
                pid_bot = f"pt-udiv-bb-{i}"
                points.append({"id": pid_top, "x": round(x, 1), "y": corr_y})
                points.append({"id": pid_bot, "x": round(x, 1), "y": oy + bd * scale})
                lines.append({
                    "id": f"ln-udiv-b-{i}",
                    "start_point_id": pid_top,
                    "end_point_id": pid_bot,
                })

        return {
            "points": points,
            "lines": lines,
            "surfaces": surfaces,
            "floor_count": mass["num_floors"],
            "building_height_m": mass["building_height_m"],
            "scale": scale,
        }

    # ── 통합 실행 ──

    def generate(self, site_input: SiteInput) -> DesignResult:
        """토지+법규 기반 자동 설계를 생성한다."""
        logger.info(
            "자동 설계 생성 시작",
            area=site_input.site_area_sqm,
            zone=site_input.zone_code,
            use=site_input.building_use,
        )

        # 1. 법규 조회
        legal = self.get_legal_limits(site_input.zone_code)

        # 2. 유효 영역 + 매스
        effective = self.compute_effective_site(site_input)
        mass = self.compute_optimal_mass(site_input, effective, legal)

        # 내장 자동 보정 (BCR/FAR/높이 위반 시 축소)
        corrections_applied = False
        max_bcr = legal["max_bcr_percent"]
        max_far = legal["max_far_percent"]
        max_h = legal["max_height_m"]

        for _ in range(20):  # 최대 20회 반복 보정
            violation = False
            if mass["bcr_pct"] > max_bcr and mass["building_footprint_sqm"] > 0:
                mass["building_footprint_sqm"] *= 0.95
                mass["building_width_m"] = round(mass["building_width_m"] * 0.975, 1)
                mass["building_depth_m"] = round(mass["building_depth_m"] * 0.975, 1)
                violation = True
            if mass["far_pct"] > max_far and mass["num_floors"] > 1:
                mass["num_floors"] = max(1, mass["num_floors"] - 1)
                violation = True
            if max_h > 0 and mass["building_height_m"] > max_h and mass["num_floors"] > 1:
                mass["num_floors"] = max(1, mass["num_floors"] - 1)
                violation = True
            if not violation:
                break
            corrections_applied = True
            # 재계산
            fp = mass["building_width_m"] * mass["building_depth_m"]
            mass["building_footprint_sqm"] = round(fp, 2)
            mass["total_floor_area_sqm"] = round(fp * mass["num_floors"], 2)
            mass["building_height_m"] = round(mass["num_floors"] * site_input.floor_height_m, 2)
            mass["bcr_pct"] = round(fp / site_input.site_area_sqm * 100, 2) if site_input.site_area_sqm > 0 else 0
            mass["far_pct"] = round(mass["total_floor_area_sqm"] / site_input.site_area_sqm * 100, 2) if site_input.site_area_sqm > 0 else 0

        # 2-b. 정북일조 단계후퇴: 보정 루프가 box 연면적으로 덮어쓰므로 여기서 재산출(층수/치수 반영)
        if mass.get("daylight_step"):
            base_north = max(1.5, site_input.setback_m.get("north", 1.5))
            far_cap_area = site_input.site_area_sqm * (max_far / 100.0)
            profile, stepped_area, n = compute_north_step_profile(
                mass["building_width_m"], mass["building_depth_m"], mass["num_floors"],
                site_input.floor_height_m, base_north, far_cap_area,
            )
            mass["num_floors"] = n
            mass["north_step_profile"] = profile
            mass["total_floor_area_sqm"] = stepped_area
            mass["building_height_m"] = round(n * site_input.floor_height_m, 2)
            mass["far_pct"] = round(stepped_area / site_input.site_area_sqm * 100, 2) if site_input.site_area_sqm > 0 else 0

        # 3. 코어 배치
        core_layout = self.compute_core_layout(mass, site_input.building_use)

        # 4. 세대 배분
        unit_layout = self.compute_unit_layout(
            mass, core_layout, site_input.target_unit_types, site_input.building_use,
        )

        # 5. DesignPayload 변환
        payload = self.to_design_payload(site_input, effective, mass, core_layout, unit_layout)

        summary = {
            "building_area_sqm": mass["building_footprint_sqm"],
            "total_floor_area_sqm": mass["total_floor_area_sqm"],
            "num_floors": mass["num_floors"],
            "building_height_m": mass["building_height_m"],
            "bcr_percent": mass["bcr_pct"],
            "far_percent": mass["far_pct"],
            "total_units": unit_layout["total_units"],
            "parking_count": unit_layout["parking_required"],
            "core_count": core_layout["num_cores"],
        }

        # P5: 정북일조 단계후퇴 정보 — 3D 매스 후퇴 렌더·근거 표기에 사용
        if mass.get("north_step_profile"):
            profile = mass["north_step_profile"]
            step_from = next((p["floor"] for p in profile if p["inset_m"] > 0), None)
            summary["daylight_step"] = True
            summary["north_step_profile"] = profile
            summary["base_north_setback_m"] = max(1.5, site_input.setback_m.get("north", 1.5))
            summary["daylight_note"] = (
                f"정북일조 사선제한 적용 — {step_from}층부터 북측 단계 후퇴(상부 세대 일조 확보)"
                if step_from else "정북일조 사선제한 검토 — 현재 높이는 단계후퇴 없이 충족"
            )

        bcr_ok = mass["bcr_pct"] <= max_bcr
        far_ok = mass["far_pct"] <= max_far
        height_ok = max_h <= 0 or mass["building_height_m"] <= max_h
        setback_ok = True  # 세트백은 설계 시 이미 반영됨

        compliance = {
            "bcr_ok": bcr_ok,
            "far_ok": far_ok,
            "height_ok": height_ok,
            "setback_ok": setback_ok,
            "all_pass": bcr_ok and far_ok and height_ok and setback_ok,
            "corrections_applied": corrections_applied,
        }

        logger.info(
            "자동 설계 생성 완료",
            floors=mass["num_floors"],
            bcr=mass["bcr_pct"],
            far=mass["far_pct"],
            units=unit_layout["total_units"],
            compliant=compliance["all_pass"],
        )

        return DesignResult(
            design_payload=payload,
            summary=summary,
            compliance=compliance,
        )

    def generate_alternatives(
        self,
        site_input: SiteInput,
        count: int = 3,
    ) -> list[DesignResult]:
        """대안 3개를 생성한다.

        대안 A: 최대 용적률 (층수 최대화)
        대안 B: 최대 세대수 (소형 위주)
        대안 C: 최적 일조 (낮은 층수, 넓은 세트백)
        """
        alternatives: list[DesignResult] = []

        # A: 기본 (최적 밸런스)
        result_a = self.generate(site_input)
        result_a.summary["alternative_name"] = "A: 최적 밸런스"
        alternatives.append(result_a)

        if count >= 2:
            # B: 소형 세대 위주 (최대 세대수)
            input_b = SiteInput(
                site_area_sqm=site_input.site_area_sqm,
                site_shape=site_input.site_shape,
                site_width_m=site_input.site_width_m,
                site_depth_m=site_input.site_depth_m,
                zone_code=site_input.zone_code,
                building_use=site_input.building_use,
                target_unit_types=["39A", "49A"],
                floor_height_m=2.8,  # 최소 층고
                setback_m=site_input.setback_m,
                daylight_step=site_input.daylight_step,
            )
            result_b = self.generate(input_b)
            result_b.summary["alternative_name"] = "B: 최대 세대수"
            alternatives.append(result_b)

        if count >= 3:
            # C: 최적 일조 (넓은 세트백 + 낮은 층수)
            wider_setback = {k: v + 2.0 for k, v in site_input.setback_m.items()}
            input_c = SiteInput(
                site_area_sqm=site_input.site_area_sqm,
                site_shape=site_input.site_shape,
                site_width_m=site_input.site_width_m,
                site_depth_m=site_input.site_depth_m,
                zone_code=site_input.zone_code,
                building_use=site_input.building_use,
                target_unit_types=["84A", "114A"],
                floor_height_m=3.3,  # 여유 층고
                setback_m=wider_setback,
                daylight_step=site_input.daylight_step,
            )
            result_c = self.generate(input_c)
            result_c.summary["alternative_name"] = "C: 최적 일조"
            alternatives.append(result_c)

        return alternatives


# ── 유틸리티 ──

def _compute_parking(
    total_units: int,
    total_floor_area: float,
    building_use: str,
) -> dict[str, Any]:
    """법규 기반 주차대수를 산정한다."""
    rule = PARKING_RULES.get(building_use, PARKING_RULES["공동주택"])

    if rule.get("per_unit"):
        required = int(total_units * rule["rate"])
    else:
        required = max(1, int(total_floor_area / rule.get("rate_per_sqm", 100)))

    area_per_car = rule.get("area_per_car_sqm", 33.0)
    total_parking_area = required * area_per_car
    # 지하 주차장 기준 1개 층 약 500sqm
    basement_floors = max(1, math.ceil(total_parking_area / 500))

    return {
        "required": required,
        "area_sqm": round(total_parking_area, 2),
        "basement_floors": basement_floors,
    }
