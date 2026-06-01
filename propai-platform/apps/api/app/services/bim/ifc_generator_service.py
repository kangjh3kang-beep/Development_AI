"""IFC 3D 모델 생성 서비스 (v62 BIM).

AutoDesignEngine이 산출한 건축 매스(building_width/depth/num_floors/floor_height)로
IFC4 BIM 모델을 절차적으로 생성한다. 각 층은 슬래브 + 외벽 4면을
IfcExtrudedAreaSolid로 압출해 표현한다.

핵심 원칙:
- ifcopenshell만 사용(이미 설치, 0.8.0). 외부 IFC 템플릿 파일 불필요.
- 좌표 단위 미터(IFC 표준). 원점=대지 기준.
- 실패 시 호출자가 graceful 처리하도록 예외 전파(라우터에서 try).

산출 모델 계층:
    IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey[N] → (IfcSlab, IfcWall×4)
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class IfcGeneratorService:
    """건축 매스 파라미터로 IFC4 모델을 절차적으로 생성한다."""

    def generate(
        self,
        *,
        building_width_m: float,
        building_depth_m: float,
        num_floors: int,
        floor_height_m: float = 3.0,
        project_name: str = "PropAI Project",
        wall_thickness_m: float = 0.2,
        slab_thickness_m: float = 0.2,
        cores: list[dict[str, float]] | None = None,
        core_size_m: float = 5.0,
        corridor_width_m: float = 0.0,
        windows_per_side: int = 0,
        unit_width_m: float = 0.0,
        unit_sequence: list[dict[str, Any]] | None = None,
        balconies: bool = False,
        unit_doors: bool = False,
    ) -> bytes:
        """IFC4 모델을 생성해 직렬화된 bytes로 반환한다.

        Args:
            building_width_m: 건물 폭(X)
            building_depth_m: 건물 깊이(Y)
            num_floors: 지상 층수
            floor_height_m: 층고
            project_name: IfcProject 이름
            wall_thickness_m: 외벽 두께
            slab_thickness_m: 슬래브 두께
            cores: 코어 중심 좌표 [{x, y}, ...]. 각 층에 수직 코어(계단·EV) 압출.
            core_size_m: 코어 한 변 길이(정사각 가정).
            corridor_width_m: 중복도 폭(>0이면 각 층 중앙 수평 복도 슬래브 추가).
            windows_per_side: 외벽 변당 창호 개수(>0이면 창 개구부 박스 추가).

        Returns:
            IFC SPF(STEP Physical File) 텍스트의 utf-8 bytes.
        """
        import ifcopenshell
        from ifcopenshell.api import run

        bw = max(float(building_width_m), 1.0)
        bd = max(float(building_depth_m), 1.0)
        n = max(int(num_floors), 1)
        fh = max(float(floor_height_m), 2.0)

        # ── 프로젝트 골격 ──
        model = ifcopenshell.file(schema="IFC4")
        run("root.create_entity", model, ifc_class="IfcProject", name=project_name)
        # 단위(미터) + 3D 컨텍스트
        run("unit.assign_unit", model)
        ctx = run("context.add_context", model, context_type="Model")
        body = run(
            "context.add_context",
            model,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=ctx,
        )

        site = run("root.create_entity", model, ifc_class="IfcSite", name="대지")
        building = run("root.create_entity", model, ifc_class="IfcBuilding", name="건물")
        run("aggregate.assign_object", model, products=[site], relating_object=model.by_type("IfcProject")[0])
        run("aggregate.assign_object", model, products=[building], relating_object=site)

        # ── 층별 슬래브 + 외벽 ──
        for i in range(n):
            elev = i * fh
            storey = run(
                "root.create_entity",
                model,
                ifc_class="IfcBuildingStorey",
                name=f"{i + 1}F",
            )
            run("aggregate.assign_object", model, products=[storey], relating_object=building)

            # 슬래브(바닥): bw×bd 사각형을 slab_thickness만큼 압출
            slab = run("root.create_entity", model, ifc_class="IfcSlab", name=f"{i + 1}F-Slab")
            slab_solid = self._extrude_rect(model, body, 0, 0, bw, bd, slab_thickness_m)
            run("geometry.assign_representation", model, product=slab, representation=slab_solid)
            self._place_z(model, slab, elev)
            run("spatial.assign_container", model, products=[slab], relating_structure=storey)

            # 외벽 4면(각 면을 얇은 박스로 압출) — 슬래브 위 floor_height만큼
            walls = self._make_perimeter_walls(model, body, bw, bd, fh, wall_thickness_m)
            for wi, (wall_solid, name) in enumerate(walls):
                wall = run("root.create_entity", model, ifc_class="IfcWall", name=f"{i + 1}F-Wall-{name}")
                run("geometry.assign_representation", model, product=wall, representation=wall_solid)
                self._place_z(model, wall, elev + slab_thickness_m)
                run("spatial.assign_container", model, products=[wall], relating_structure=storey)

            # 코어(계단+EV): 각 중심좌표에 정사각 박스를 층고만큼 압출 → IfcSpace
            if cores:
                cs = core_size_m
                for ci, c in enumerate(cores):
                    cx = float(c.get("x", bw / 2)) - cs / 2
                    cy = float(c.get("y", bd / 2)) - cs / 2
                    # 건물 경계 내로 클램프
                    cx = max(wall_thickness_m, min(cx, bw - cs - wall_thickness_m))
                    cy = max(wall_thickness_m, min(cy, bd - cs - wall_thickness_m))
                    core = run("root.create_entity", model, ifc_class="IfcColumn", name=f"{i + 1}F-Core-{ci + 1}")
                    core_solid = self._extrude_rect(model, body, cx, cy, cs, cs, fh)
                    run("geometry.assign_representation", model, product=core, representation=core_solid)
                    self._place_z(model, core, elev + slab_thickness_m)
                    run("spatial.assign_container", model, products=[core], relating_structure=storey)

            # 중복도: 건물 중앙 수평 스트립 슬래브(얇게) — 동선 시각화
            if corridor_width_m and corridor_width_m > 0:
                cw = min(corridor_width_m, bd)
                cy = (bd - cw) / 2
                corr = run("root.create_entity", model, ifc_class="IfcSlab", name=f"{i + 1}F-Corridor")
                corr_solid = self._extrude_rect(model, body, wall_thickness_m, cy, bw - 2 * wall_thickness_m, cw, 0.05)
                run("geometry.assign_representation", model, product=corr, representation=corr_solid)
                self._place_z(model, corr, elev + slab_thickness_m)
                run("spatial.assign_container", model, products=[corr], relating_structure=storey)

            # 창호: 정면/배면 외벽에 등간격 개구부 박스(IfcWindow) — 1층 제외(상가/필로티)
            if windows_per_side and windows_per_side > 0 and i > 0:
                win_w, win_h, sill = 1.5, 1.2, 0.9
                step = bw / (windows_per_side + 1)
                for side_y, side in [(0.0, "F"), (bd - wall_thickness_m, "B")]:
                    for wj in range(windows_per_side):
                        wx = step * (wj + 1) - win_w / 2
                        wx = max(wall_thickness_m, min(wx, bw - win_w - wall_thickness_m))
                        win = run("root.create_entity", model, ifc_class="IfcWindow", name=f"{i + 1}F-Win-{side}{wj + 1}")
                        win_solid = self._extrude_rect(model, body, wx, side_y, win_w, wall_thickness_m, win_h)
                        run("geometry.assign_representation", model, product=win, representation=win_solid)
                        self._place_z(model, win, elev + slab_thickness_m + sill)
                        run("spatial.assign_container", model, products=[win], relating_structure=storey)

            # 세대 분할 내벽 + 발코니 + 현관문: 복도 기준 전면/배면 zone에 세대를 배치.
            # unit_sequence가 있으면 평형별 가변 폭(면적/zone깊이), 없으면 unit_width 균등.
            # 1층 제외(상가/로비).
            if (unit_width_m and unit_width_m > 0) or unit_sequence:
                if i > 0:
                    pwt = 0.15  # 세대 칸막이 두께
                    inner_w = bw - 2 * wall_thickness_m
                    cw = min(corridor_width_m, bd) if corridor_width_m > 0 else 0.0
                    corr_y0 = (bd - cw) / 2
                    corr_y1 = corr_y0 + cw
                    # 전면(face=F, 발코니 있음), 배면(face=B)
                    zones = [
                        ("F", wall_thickness_m, max(wall_thickness_m, corr_y0)),
                        ("B", min(bd - wall_thickness_m, corr_y1), bd - wall_thickness_m),
                    ]
                    for zi, (face, zy0, zy1) in enumerate(zones):
                        zd = zy1 - zy0
                        if zd <= 0.3:
                            continue
                        # 평형 시퀀스로 세대 폭 산출(면적/깊이). 없으면 균등.
                        widths = self._unit_widths(inner_w, zd, unit_sequence, unit_width_m)
                        cursor = wall_thickness_m
                        for ui, uw in enumerate(widths):
                            # 세대 사이 칸막이(첫 세대 앞은 외벽이라 생략)
                            if ui > 0:
                                part = run("root.create_entity", model, ifc_class="IfcWallStandardCase", name=f"{i + 1}F-Part-{face}-{ui}")
                                part_solid = self._extrude_rect(model, body, cursor - pwt / 2, zy0, pwt, zd, fh - slab_thickness_m)
                                run("geometry.assign_representation", model, product=part, representation=part_solid)
                                self._place_z(model, part, elev + slab_thickness_m)
                                run("spatial.assign_container", model, products=[part], relating_structure=storey)
                            # 발코니: 전면 세대 외부(외벽 밖 1.5m 캔틸레버 슬래브)
                            if balconies and face == "F":
                                bal_d = 1.5
                                bal = run("root.create_entity", model, ifc_class="IfcSlab", name=f"{i + 1}F-Balcony-{ui}")
                                bal_solid = self._extrude_rect(model, body, cursor + 0.3, -bal_d, max(0.5, uw - 0.6), bal_d, 0.12)
                                run("geometry.assign_representation", model, product=bal, representation=bal_solid)
                                self._place_z(model, bal, elev + slab_thickness_m)
                                run("spatial.assign_container", model, products=[bal], relating_structure=storey)
                            # 현관문: 복도 쪽 개구부(zone 안쪽 모서리)
                            if unit_doors and cw > 0:
                                door_w, door_h = 0.9, 2.1
                                door_y = zy1 if face == "F" else zy0 - wall_thickness_m
                                dx = cursor + uw / 2 - door_w / 2
                                door = run("root.create_entity", model, ifc_class="IfcDoor", name=f"{i + 1}F-Door-{face}-{ui}")
                                door_solid = self._extrude_rect(model, body, dx, door_y, door_w, wall_thickness_m, door_h)
                                run("geometry.assign_representation", model, product=door, representation=door_solid)
                                self._place_z(model, door, elev + slab_thickness_m)
                                run("spatial.assign_container", model, products=[door], relating_structure=storey)
                            cursor += uw

        logger.info(
            "IFC 생성 완료",
            floors=n, width=bw, depth=bd, height=round(n * fh, 1),
            entities=len(list(model)),
        )
        return model.to_string().encode("utf-8")

    # ── 내부 헬퍼 ──

    @staticmethod
    def _unit_widths(
        inner_w: float,
        zone_depth: float,
        unit_sequence: list[dict[str, Any]] | None,
        unit_width_m: float,
    ) -> list[float]:
        """zone(inner_w 폭)을 채울 세대 폭 리스트를 산출.

        unit_sequence(평형별 area_sqm)가 있으면 폭=면적/깊이로 가변 산출 후 inner_w에
        맞게 비례 스케일(합=inner_w). 없으면 unit_width_m 균등 분할.
        """
        if unit_sequence and zone_depth > 0.5:
            raw = []
            for u in unit_sequence:
                area = float(u.get("area_sqm", 84.0))
                w = max(3.0, area / zone_depth)  # 최소 3m
                raw.append(w)
            # zone에 들어갈 만큼만 누적(넘치면 컷), 남으면 비례 확장
            total = sum(raw)
            if total <= 0:
                return []
            scale = inner_w / total
            return [w * scale for w in raw]
        # 균등 분할 폴백
        if unit_width_m and unit_width_m > 0:
            n = max(1, int(inner_w / unit_width_m))
            return [inner_w / n] * n
        return [inner_w]

    def _extrude_rect(self, model, body, x0, y0, w, d, height):
        """(x0,y0) 기준 w×d 사각형을 height만큼 +Z 압출한 Body representation 반환."""
        pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + d), (x0, y0 + d), (x0, y0)]
        profile = model.create_entity(
            "IfcArbitraryClosedProfileDef",
            ProfileType="AREA",
            OuterCurve=model.create_entity(
                "IfcPolyline",
                Points=[model.create_entity("IfcCartesianPoint", Coordinates=(float(px), float(py))) for px, py in pts],
            ),
        )
        direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
        position = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        )
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=position,
            ExtrudedDirection=direction,
            Depth=float(height),
        )
        return model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

    def _make_perimeter_walls(self, model, body, bw, bd, fh, wt):
        """외벽 4면을 각각 얇은 박스로 압출. [(shape, name), ...]."""
        specs = [
            (0, 0, bw, wt, "S"),          # 남(앞) — 깊이방향 두께
            (0, bd - wt, bw, wt, "N"),    # 북(뒤)
            (0, 0, wt, bd, "W"),          # 서(좌)
            (bw - wt, 0, wt, bd, "E"),    # 동(우)
        ]
        out = []
        for x0, y0, w, d, name in specs:
            out.append((self._extrude_rect(model, body, x0, y0, w, d, fh), name))
        return out

    def _place_z(self, model, product, z):
        """product의 ObjectPlacement를 (0,0,z)에 배치."""
        placement = model.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, float(z))),
            ),
        )
        product.ObjectPlacement = placement


def build_ifc_from_mass(mass: dict[str, Any], project_name: str = "PropAI Project") -> bytes:
    """AutoDesignEngine 매스(+선택 core_layout) dict로 IFC를 생성하는 편의 함수.

    mass에 core_positions·corridor_width_m·windows_per_side가 있으면 실내 요소도 압출.
    """
    return IfcGeneratorService().generate(
        building_width_m=float(mass.get("building_width_m", 10.0)),
        building_depth_m=float(mass.get("building_depth_m", 10.0)),
        num_floors=int(mass.get("num_floors", 5)),
        floor_height_m=float(mass.get("floor_height_m", 3.0)),
        project_name=project_name,
        cores=mass.get("core_positions"),
        core_size_m=float(mass.get("core_size_m", 5.0)),
        corridor_width_m=float(mass.get("corridor_width_m", 0.0)),
        windows_per_side=int(mass.get("windows_per_side", 0)),
        unit_width_m=float(mass.get("unit_width_m", 0.0)),
        unit_sequence=mass.get("unit_sequence"),
        balconies=bool(mass.get("balconies", False)),
        unit_doors=bool(mass.get("unit_doors", False)),
    )
