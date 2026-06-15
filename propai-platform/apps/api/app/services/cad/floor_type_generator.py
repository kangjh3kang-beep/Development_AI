"""층별 차별화 평면 생성기.

건물 유형별로 층의 용도를 자동 결정하고,
각 층에 맞는 평면 배치를 생성한다.

층별 분류:
- 지하층: 주차장 + 기계실 + 전기실
- 1층: 필로티/상가/로비+MDF (용도 복합 시)
- 기준층: 세대 배치 + 코어 + 복도
- 최상층: 펜트하우스 또는 기준층
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()

# ── 주차 규칙 ──
PARKING_AREA_SQM = {"자주식": 33.0, "기계식": 15.0}  # 대당 필요면적
PARKING_SLOT_M = {"자주식": (2.5, 5.0), "기계식": (2.5, 3.0)}  # (폭, 깊이)
PARKING_AISLE_M = {"자주식": 6.0, "기계식": 4.0}


@dataclass
class RoomSpec:
    """개별 방/공간 사양."""
    name: str
    width_m: float
    depth_m: float
    area_sqm: float = 0.0

    def __post_init__(self):
        if self.area_sqm == 0.0:
            self.area_sqm = self.width_m * self.depth_m


@dataclass
class FloorPlan:
    """한 개 층의 평면 정보."""
    floor_number: int  # 양수: 지상, 음수: 지하
    floor_type: str  # "basement_parking", "piloti", "commercial", "lobby", "standard", "penthouse"
    label: str  # "B1F", "1F", "2F", "RF" 등
    building_width_m: float
    building_depth_m: float
    floor_height_m: float
    rooms: list[RoomSpec] = field(default_factory=list)
    core_count: int = 0
    corridor_width_m: float = 0.0
    unit_count: int = 0
    gross_area_sqm: float = 0.0
    net_area_sqm: float = 0.0
    description: str = ""

    def __post_init__(self):
        self.gross_area_sqm = self.building_width_m * self.building_depth_m
        if self.net_area_sqm == 0.0:
            self.net_area_sqm = self.gross_area_sqm


@dataclass
class BuildingFloorSet:
    """건물 전체 층별 평면 세트."""
    floors: list[FloorPlan] = field(default_factory=list)
    total_gross_area_sqm: float = 0.0
    total_parking_count: int = 0
    building_use: str = "공동주택"

    def __post_init__(self):
        self.total_gross_area_sqm = sum(f.gross_area_sqm for f in self.floors)


class FloorTypeGenerator:
    """건물 유형과 법규에 따라 층별 용도를 결정하고 평면을 생성한다."""

    def generate(
        self,
        building_width_m: float,
        building_depth_m: float,
        floor_count: int,
        floor_height_m: float = 3.0,
        basement_floors: int = 1,
        basement_height_m: float = 3.3,
        building_use: str = "공동주택",
        unit_width_m: float = 8.0,
        corridor_width_m: float = 1.8,
        core_count: int = 2,
        first_floor_use: str = "piloti",
        has_penthouse: bool = False,
        parking_count: int = 0,
        parking_type: str = "자주식",
    ) -> BuildingFloorSet:
        """전체 층별 평면을 생성한다."""
        floors: list[FloorPlan] = []

        # ── 지하층 ──
        for bi in range(basement_floors, 0, -1):
            fp = self._generate_basement(
                floor_number=-bi,
                building_width_m=building_width_m,
                building_depth_m=building_depth_m,
                floor_height_m=basement_height_m,
                parking_count=parking_count,
                parking_type=parking_type,
                basement_index=bi,
                total_basements=basement_floors,
            )
            floors.append(fp)

        # ── 1층 ──
        fp_1f = self._generate_first_floor(
            building_width_m=building_width_m,
            building_depth_m=building_depth_m,
            floor_height_m=max(floor_height_m, 3.6),  # 1층은 최소 3.6m
            building_use=building_use,
            first_floor_use=first_floor_use,
            corridor_width_m=corridor_width_m,
            core_count=core_count,
            unit_width_m=unit_width_m,
        )
        floors.append(fp_1f)

        # ── 기준층 (2F ~ N-1F 또는 NF) ──
        top_standard = floor_count - 1 if has_penthouse and floor_count > 2 else floor_count
        for fi in range(2, top_standard + 1):
            fp = self._generate_standard_floor(
                floor_number=fi,
                building_width_m=building_width_m,
                building_depth_m=building_depth_m,
                floor_height_m=floor_height_m,
                unit_width_m=unit_width_m,
                corridor_width_m=corridor_width_m,
                core_count=core_count,
            )
            floors.append(fp)

        # ── 최상층 (펜트하우스) ──
        if has_penthouse and floor_count > 2:
            fp_ph = self._generate_penthouse(
                floor_number=floor_count,
                building_width_m=building_width_m,
                building_depth_m=building_depth_m,
                floor_height_m=floor_height_m + 0.6,  # 펜트하우스 층고 증가
                core_count=core_count,
            )
            floors.append(fp_ph)

        result = BuildingFloorSet(
            floors=floors,
            total_parking_count=parking_count,
            building_use=building_use,
        )
        logger.info(
            "floor_set_generated",
            floor_count=len(floors),
            total_gross_area=result.total_gross_area_sqm,
        )
        return result

    # ── 지하층 ──

    def _generate_basement(
        self,
        floor_number: int,
        building_width_m: float,
        building_depth_m: float,
        floor_height_m: float,
        parking_count: int,
        parking_type: str,
        basement_index: int,
        total_basements: int,
    ) -> FloorPlan:
        rooms: list[RoomSpec] = []
        gross = building_width_m * building_depth_m

        # 기계실+전기실은 최하층에 배치
        if basement_index == total_basements:
            mech_area = gross * 0.10
            mech_w = min(building_width_m * 0.25, 8.0)
            mech_d = mech_area / mech_w if mech_w > 0 else 0
            rooms.append(RoomSpec("기계실", mech_w, mech_d, mech_area))

            elec_area = gross * 0.05
            elec_w = min(building_width_m * 0.15, 5.0)
            elec_d = elec_area / elec_w if elec_w > 0 else 0
            rooms.append(RoomSpec("전기실", elec_w, elec_d, elec_area))

        # 주차 (남은 면적)
        used_area = sum(r.area_sqm for r in rooms)
        pk_area = gross - used_area
        pk_per_floor = 0
        if parking_count > 0 and pk_area > 0:
            area_per_slot = PARKING_AREA_SQM.get(parking_type, 33.0)
            pk_per_floor = int(pk_area / area_per_slot)
            pk_per_floor = min(pk_per_floor, parking_count)

        rooms.append(RoomSpec("주차장", building_width_m, pk_area / building_width_m if building_width_m else 0, pk_area))

        label = f"B{abs(floor_number)}F"
        return FloorPlan(
            floor_number=floor_number,
            floor_type="basement_parking",
            label=label,
            building_width_m=building_width_m,
            building_depth_m=building_depth_m,
            floor_height_m=floor_height_m,
            rooms=rooms,
            core_count=1,
            unit_count=pk_per_floor,
            net_area_sqm=pk_area,
            description=f"지하{abs(floor_number)}층 주차장 ({pk_per_floor}대)",
        )

    # ── 1층 ──

    def _generate_first_floor(
        self,
        building_width_m: float,
        building_depth_m: float,
        floor_height_m: float,
        building_use: str,
        first_floor_use: str,
        corridor_width_m: float,
        core_count: int,
        unit_width_m: float,
    ) -> FloorPlan:
        rooms: list[RoomSpec] = []
        gross = building_width_m * building_depth_m

        if first_floor_use == "piloti":
            # 필로티: 주차+로비
            lobby_area = min(gross * 0.15, 50.0)
            rooms.append(RoomSpec("로비/관리실", min(10, building_width_m * 0.3), lobby_area / min(10, building_width_m * 0.3)))
            rooms.append(RoomSpec("MDF/통신실", 3.0, 2.0))
            pk_area = gross - lobby_area - 6.0
            rooms.append(RoomSpec("필로티 주차", building_width_m, pk_area / building_width_m if building_width_m else 0, pk_area))
            floor_type = "piloti"
            desc = "필로티 (주차+로비)"
            unit_count = 0

        elif first_floor_use == "commercial":
            # 근린생활시설
            shop_depth = building_depth_m * 0.6
            shop_count = max(1, int(building_width_m / 6.0))
            shop_w = building_width_m / shop_count
            for si in range(shop_count):
                rooms.append(RoomSpec(f"상가{si + 1}", shop_w, shop_depth))
            rooms.append(RoomSpec("공용복도", building_width_m, building_depth_m - shop_depth))
            floor_type = "commercial"
            desc = f"근린생활시설 ({shop_count}호)"
            unit_count = shop_count

        else:
            # 기준층과 동일 (주거)
            return self._generate_standard_floor(
                floor_number=1,
                building_width_m=building_width_m,
                building_depth_m=building_depth_m,
                floor_height_m=floor_height_m,
                unit_width_m=unit_width_m,
                corridor_width_m=corridor_width_m,
                core_count=core_count,
            )

        return FloorPlan(
            floor_number=1,
            floor_type=floor_type,
            label="1F",
            building_width_m=building_width_m,
            building_depth_m=building_depth_m,
            floor_height_m=floor_height_m,
            rooms=rooms,
            core_count=core_count,
            corridor_width_m=corridor_width_m,
            unit_count=unit_count,
            description=desc,
        )

    # ── 기준층 ──

    def _generate_standard_floor(
        self,
        floor_number: int,
        building_width_m: float,
        building_depth_m: float,
        floor_height_m: float,
        unit_width_m: float,
        corridor_width_m: float,
        core_count: int,
    ) -> FloorPlan:
        rooms: list[RoomSpec] = []
        wt = 0.2  # 벽두께

        # 복도 면적
        corr_area = (building_width_m - 2 * wt) * corridor_width_m

        # 코어 면적
        core_w = 4.0
        core_d = 6.0
        core_area = core_count * core_w * core_d

        # 가용 세대 면적 (양쪽)
        inner_w = building_width_m - 2 * wt
        units_per_side = max(1, int(inner_w / unit_width_m))
        actual_uw = inner_w / units_per_side

        half_depth = (building_depth_m - 2 * wt - corridor_width_m) / 2
        unit_area = actual_uw * half_depth

        total_units = units_per_side * 2  # 양쪽
        for ui in range(total_units):
            side = "남" if ui < units_per_side else "북"
            idx = (ui % units_per_side) + 1
            rooms.append(RoomSpec(f"{side}측-{idx}호", actual_uw, half_depth, unit_area))

        rooms.append(RoomSpec("복도", inner_w, corridor_width_m, corr_area))
        for ci in range(core_count):
            rooms.append(RoomSpec(f"코어{ci + 1}", core_w, core_d, core_w * core_d))

        net_area = sum(r.area_sqm for r in rooms if "코어" not in r.name and "복도" not in r.name)

        return FloorPlan(
            floor_number=floor_number,
            floor_type="standard",
            label=f"{floor_number}F",
            building_width_m=building_width_m,
            building_depth_m=building_depth_m,
            floor_height_m=floor_height_m,
            rooms=rooms,
            core_count=core_count,
            corridor_width_m=corridor_width_m,
            unit_count=total_units,
            net_area_sqm=net_area,
            description=f"기준층 ({total_units}세대)",
        )

    # ── 최상층 (펜트하우스) ──

    def _generate_penthouse(
        self,
        floor_number: int,
        building_width_m: float,
        building_depth_m: float,
        floor_height_m: float,
        core_count: int,
    ) -> FloorPlan:
        rooms: list[RoomSpec] = []
        wt = 0.2

        # 펜트하우스: 기준층 대비 넓은 세대 (2배 폭)
        inner_w = building_width_m - 2 * wt
        ph_count = max(1, int(inner_w / 16.0))  # 16m 폭 단위
        ph_w = inner_w / ph_count
        ph_d = building_depth_m - 2 * wt

        for pi in range(ph_count):
            rooms.append(RoomSpec(f"PH-{pi + 1}", ph_w, ph_d, ph_w * ph_d))

        # 코어
        for ci in range(core_count):
            rooms.append(RoomSpec(f"코어{ci + 1}", 4.0, 6.0))

        # 옥탑 (계단실)
        rooms.append(RoomSpec("옥탑(계단실)", 4.0, 4.0))

        net_area = sum(r.area_sqm for r in rooms if "코어" not in r.name and "옥탑" not in r.name)

        return FloorPlan(
            floor_number=floor_number,
            floor_type="penthouse",
            label=f"{floor_number}F (PH)",
            building_width_m=building_width_m,
            building_depth_m=building_depth_m,
            floor_height_m=floor_height_m,
            rooms=rooms,
            core_count=core_count,
            unit_count=ph_count,
            net_area_sqm=net_area,
            description=f"펜트하우스 ({ph_count}세대)",
        )

    # ── 유틸리티 ──

    def compute_parking_requirement(
        self,
        total_units: int,
        building_use: str = "공동주택",
        site_area_sqm: float = 0.0,
    ) -> int:
        """법정 주차대수를 산정한다 (주차장법 시행규칙)."""
        if building_use == "공동주택":
            # 세대당 1대 기본 (85sqm 이하 0.7대, 85sqm 초과 1대)
            return max(1, int(total_units * 1.0))
        elif building_use in ("근린생활시설", "업무시설"):
            # 시설면적 150sqm당 1대
            if site_area_sqm > 0:
                return max(1, int(site_area_sqm / 150))
            return max(1, total_units)
        return max(1, total_units)

    def compute_underground_parking_area(
        self,
        parking_count: int,
        parking_type: str = "자주식",
    ) -> float:
        """지하 주차장 필요 면적을 산출한다."""
        area_per_slot = PARKING_AREA_SQM.get(parking_type, 33.0)
        return parking_count * area_per_slot

    def to_summary(self, floor_set: BuildingFloorSet) -> dict:
        """층별 요약 정보를 반환한다."""
        return {
            "building_use": floor_set.building_use,
            "total_floors": len(floor_set.floors),
            "total_gross_area_sqm": round(floor_set.total_gross_area_sqm, 1),
            "total_parking_count": floor_set.total_parking_count,
            "floors": [
                {
                    "label": f.label,
                    "type": f.floor_type,
                    "gross_area_sqm": round(f.gross_area_sqm, 1),
                    "net_area_sqm": round(f.net_area_sqm, 1),
                    "unit_count": f.unit_count,
                    "description": f.description,
                }
                for f in floor_set.floors
            ],
        }
