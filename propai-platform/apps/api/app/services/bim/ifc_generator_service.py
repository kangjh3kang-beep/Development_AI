"""IFC 3D 모델 생성 서비스 (v62 BIM).

AutoDesignEngine이 산출한 건축 매스(building_width/depth/num_floors/floor_height)로
IFC4 BIM 모델을 절차적으로 생성한다. 각 층은 슬래브 + 외벽 4면을
IfcExtrudedAreaSolid로 압출해 표현한다.

핵심 원칙:
- ifcopenshell만 사용(이미 설치, 0.8.4). 외부 IFC 템플릿 파일 불필요.
- 좌표 단위 미터(IFC 표준). 원점=대지 기준.
- 실패 시 호출자가 graceful 처리하도록 예외 전파(라우터에서 try).

산출 모델 계층:
    IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey[N] → (IfcSlab, IfcWall×4)

품질 보강(R4′ — additive):
- 모든 생성 요소에 IfcElementQuantity(BaseQuantities: 벽 Length/NetSideArea/NetVolume,
  슬래브 NetArea/NetVolume 등)를 부착 — 수치는 압출 지오메트리와 동일 수식(가짜값 없음).
- 벽(IfcWall/IfcWallStandardCase)에 Pset_WallCommon(LoadBearing·IsExternal) 부착.
- 기존 생성 키·지오메트리·요소 수 불변. 자사 analyze_ifc 파서(IfcElementQuantity 의존)가
  자기 생성 IFC를 그대로 적산할 수 있게 하는 것이 목적.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:  # 타입 힌트 전용 — 런타임 import 회피
    from app.services.bim.bimir_schema import BimModel

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
            # BaseQuantities — 압출 수식과 동일(bw×bd 사각 × slab_thickness)
            self._attach_base_quantities(model, slab, "Qto_SlabBaseQuantities", [
                ("IfcQuantityLength", "Width", slab_thickness_m),
                ("IfcQuantityLength", "Perimeter", 2 * (bw + bd)),
                ("IfcQuantityArea", "NetArea", bw * bd),
                ("IfcQuantityVolume", "NetVolume", bw * bd * slab_thickness_m),
            ])

            # 외벽 4면(각 면을 얇은 박스로 압출) — 슬래브 위 floor_height만큼
            walls = self._make_perimeter_walls(model, body, bw, bd, fh, wall_thickness_m)
            for _wi, (wall_solid, name) in enumerate(walls):
                wall = run("root.create_entity", model, ifc_class="IfcWall", name=f"{i + 1}F-Wall-{name}")
                run("geometry.assign_representation", model, product=wall, representation=wall_solid)
                self._place_z(model, wall, elev + slab_thickness_m)
                run("spatial.assign_container", model, products=[wall], relating_structure=storey)
                # BaseQuantities + Pset_WallCommon — S/N면 길이=bw, W/E면 길이=bd
                wall_len = bw if name in ("S", "N") else bd
                self._attach_base_quantities(model, wall, "Qto_WallBaseQuantities", [
                    ("IfcQuantityLength", "Length", wall_len),
                    ("IfcQuantityLength", "Height", fh),
                    ("IfcQuantityLength", "Width", wall_thickness_m),
                    ("IfcQuantityArea", "NetSideArea", wall_len * fh),
                    ("IfcQuantityVolume", "NetVolume", wall_len * wall_thickness_m * fh),
                ])
                self._attach_pset_wall_common(model, wall, load_bearing=True, is_external=True)

            # 코어(계단실+EV): 외곽벽 4면(코어벽) + 층참 슬래브 + 계단 경사판.
            # 단순 솔리드 대신 실제 계단실 형상으로 표현.
            if cores:
                cs = core_size_m
                cwt = 0.2  # 코어 벽 두께
                for ci, c in enumerate(cores):
                    cx = float(c.get("x", bw / 2)) - cs / 2
                    cy = float(c.get("y", bd / 2)) - cs / 2
                    cx = max(wall_thickness_m, min(cx, bw - cs - wall_thickness_m))
                    cy = max(wall_thickness_m, min(cy, bd - cs - wall_thickness_m))
                    # 코어 외곽벽 4면(IfcColumn으로 그룹=core 유지)
                    core_walls = [
                        (cx, cy, cs, cwt),                    # 하
                        (cx, cy + cs - cwt, cs, cwt),         # 상
                        (cx, cy, cwt, cs),                    # 좌
                        (cx + cs - cwt, cy, cwt, cs),         # 우
                    ]
                    for wpi, (wx, wy, ww, wd) in enumerate(core_walls):
                        cwl = run("root.create_entity", model, ifc_class="IfcColumn", name=f"{i + 1}F-CoreWall-{ci + 1}-{wpi}")
                        cwl_solid = self._extrude_rect(model, body, wx, wy, ww, wd, fh)
                        run("geometry.assign_representation", model, product=cwl, representation=cwl_solid)
                        self._place_z(model, cwl, elev + slab_thickness_m)
                        run("spatial.assign_container", model, products=[cwl], relating_structure=storey)
                        # BaseQuantities — 코어벽(IfcColumn): 단면적 ww×wd, 수직길이 fh
                        self._attach_base_quantities(model, cwl, "Qto_ColumnBaseQuantities", [
                            ("IfcQuantityLength", "Length", fh),
                            ("IfcQuantityArea", "CrossSectionArea", ww * wd),
                            ("IfcQuantityVolume", "NetVolume", ww * wd * fh),
                        ])
                    # 계단 경사판: 코어 내부를 가로지르는 2개 계단참(half-flight) 슬래브
                    inset = cwt + 0.05
                    half_w = (cs - 2 * inset) / 2
                    for sp in range(2):
                        sx = cx + inset + sp * half_w
                        stair = run("root.create_entity", model, ifc_class="IfcStair", name=f"{i + 1}F-Stair-{ci + 1}-{sp}")
                        # 계단참: 층 중간 높이의 얇은 슬래브(경사 대용 — glTF에서 단 표현)
                        st_z = sp * (fh / 2)
                        stair_solid = self._extrude_rect(model, body, sx, cy + inset, half_w - 0.05, cs - 2 * inset, 0.15)
                        run("geometry.assign_representation", model, product=stair, representation=stair_solid)
                        self._place_z(model, stair, elev + slab_thickness_m + st_z)
                        run("spatial.assign_container", model, products=[stair], relating_structure=storey)
                        # BaseQuantities — 계단참 슬래브 압출 수식과 동일
                        st_w = half_w - 0.05
                        st_d = cs - 2 * inset
                        self._attach_base_quantities(model, stair, "Qto_StairFlightBaseQuantities", [
                            ("IfcQuantityLength", "Length", st_d),
                            ("IfcQuantityArea", "GrossArea", st_w * st_d),
                            ("IfcQuantityVolume", "NetVolume", st_w * st_d * 0.15),
                        ])

            # 중복도: 건물 중앙 수평 스트립 슬래브(얇게) — 동선 시각화
            if corridor_width_m and corridor_width_m > 0:
                cw = min(corridor_width_m, bd)
                cy = (bd - cw) / 2
                corr = run("root.create_entity", model, ifc_class="IfcSlab", name=f"{i + 1}F-Corridor")
                corr_solid = self._extrude_rect(model, body, wall_thickness_m, cy, bw - 2 * wall_thickness_m, cw, 0.05)
                run("geometry.assign_representation", model, product=corr, representation=corr_solid)
                self._place_z(model, corr, elev + slab_thickness_m)
                run("spatial.assign_container", model, products=[corr], relating_structure=storey)
                # BaseQuantities — 복도 스트립 슬래브(두께 0.05) 압출 수식과 동일
                corr_len = bw - 2 * wall_thickness_m
                self._attach_base_quantities(model, corr, "Qto_SlabBaseQuantities", [
                    ("IfcQuantityLength", "Width", 0.05),
                    ("IfcQuantityArea", "NetArea", corr_len * cw),
                    ("IfcQuantityVolume", "NetVolume", corr_len * cw * 0.05),
                ])

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
                        # BaseQuantities — 창호 개구부 면적(폭×높이)
                        self._attach_base_quantities(model, win, "Qto_WindowBaseQuantities", [
                            ("IfcQuantityLength", "Width", win_w),
                            ("IfcQuantityLength", "Height", win_h),
                            ("IfcQuantityArea", "Area", win_w * win_h),
                        ])

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
                    for _zi, (face, zy0, zy1) in enumerate(zones):
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
                                # BaseQuantities + Pset_WallCommon — 내벽(비내력·내부)
                                part_h = fh - slab_thickness_m
                                self._attach_base_quantities(model, part, "Qto_WallBaseQuantities", [
                                    ("IfcQuantityLength", "Length", zd),
                                    ("IfcQuantityLength", "Height", part_h),
                                    ("IfcQuantityLength", "Width", pwt),
                                    ("IfcQuantityArea", "NetSideArea", zd * part_h),
                                    ("IfcQuantityVolume", "NetVolume", pwt * zd * part_h),
                                ])
                                self._attach_pset_wall_common(model, part, load_bearing=False, is_external=False)
                            # 발코니: 전면 세대 외부(외벽 밖 1.5m 캔틸레버 슬래브)
                            if balconies and face == "F":
                                bal_d = 1.5
                                bal = run("root.create_entity", model, ifc_class="IfcSlab", name=f"{i + 1}F-Balcony-{ui}")
                                bal_solid = self._extrude_rect(model, body, cursor + 0.3, -bal_d, max(0.5, uw - 0.6), bal_d, 0.12)
                                run("geometry.assign_representation", model, product=bal, representation=bal_solid)
                                self._place_z(model, bal, elev + slab_thickness_m)
                                run("spatial.assign_container", model, products=[bal], relating_structure=storey)
                                # BaseQuantities — 발코니 캔틸레버 슬래브 압출 수식과 동일
                                bal_w = max(0.5, uw - 0.6)
                                self._attach_base_quantities(model, bal, "Qto_SlabBaseQuantities", [
                                    ("IfcQuantityLength", "Width", 0.12),
                                    ("IfcQuantityArea", "NetArea", bal_w * bal_d),
                                    ("IfcQuantityVolume", "NetVolume", bal_w * bal_d * 0.12),
                                ])
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
                                # BaseQuantities — 현관문 개구부 면적(폭×높이)
                                self._attach_base_quantities(model, door, "Qto_DoorBaseQuantities", [
                                    ("IfcQuantityLength", "Width", door_w),
                                    ("IfcQuantityLength", "Height", door_h),
                                    ("IfcQuantityArea", "Area", door_w * door_h),
                                ])
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

    @staticmethod
    def _attach_base_quantities(
        model,
        product,
        qto_name: str,
        quantities: list[tuple[str, str, float]],
    ) -> None:
        """product에 IfcElementQuantity(BaseQuantities)를 부착한다(additive).

        기존 create_entity 생성 패턴 확장 — ifcopenshell.api pset 모듈의 버전별
        템플릿 해석에 의존하지 않고 파서 계약(bim_ifc_service._parse_ifc:
        IsDefinedBy → IfcRelDefinesByProperties → IfcElementQuantity → Quantities의
        IfcQuantityArea.AreaValue / IfcQuantityVolume.VolumeValue)을 직접 충족한다.

        주의: 요소당 IfcQuantityArea·IfcQuantityVolume은 각 1개만 부착할 것 —
        _parse_ifc가 마지막 값으로 덮어쓰므로(대입 누적 아님) 2개 이상이면 비결정적.

        Args:
            qto_name: IfcElementQuantity 이름(Qto_WallBaseQuantities 등 표준명).
            quantities: (ifc_class, 물량명, 값) 목록.
                ifc_class ∈ {IfcQuantityLength, IfcQuantityArea, IfcQuantityVolume}.
        """
        import ifcopenshell

        value_attr = {
            "IfcQuantityLength": "LengthValue",
            "IfcQuantityArea": "AreaValue",
            "IfcQuantityVolume": "VolumeValue",
        }
        qs = [
            model.create_entity(qclass, Name=qname, **{value_attr[qclass]: float(qvalue)})
            for qclass, qname, qvalue in quantities
        ]
        element_quantity = model.create_entity(
            "IfcElementQuantity",
            GlobalId=ifcopenshell.guid.new(),
            Name=qto_name,
            MethodOfMeasurement="BaseQuantities",
            Quantities=qs,
        )
        model.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=[product],
            RelatingPropertyDefinition=element_quantity,
        )

    @staticmethod
    def _attach_pset_wall_common(
        model,
        product,
        *,
        load_bearing: bool,
        is_external: bool,
    ) -> None:
        """벽 요소에 Pset_WallCommon(LoadBearing·IsExternal)을 부착한다(additive)."""
        import ifcopenshell

        props = [
            model.create_entity(
                "IfcPropertySingleValue",
                Name="LoadBearing",
                NominalValue=model.create_entity("IfcBoolean", bool(load_bearing)),
            ),
            model.create_entity(
                "IfcPropertySingleValue",
                Name="IsExternal",
                NominalValue=model.create_entity("IfcBoolean", bool(is_external)),
            ),
        ]
        pset = model.create_entity(
            "IfcPropertySet",
            GlobalId=ifcopenshell.guid.new(),
            Name="Pset_WallCommon",
            HasProperties=props,
        )
        model.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=[product],
            RelatingPropertyDefinition=pset,
        )


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


def build_ifc_from_bimir(model: BimModel, project_name: str = "PropAI Project") -> bytes:
    """BimIR(propai.bimir/1.0) → IFC (WP-D 소비처 전환·대표 1곳).

    ★무회귀: 기존 build_ifc_from_mass(매스 dict 직접 경로)는 그대로 둔다. 이 함수는 '추가' 경로로,
      BimIR에서 매스를 복원(mass_from_bimir)해 동일한 build_ifc_from_mass로 넘긴다.
    ★구조 동등성: mass_from_bimir(bimir_from_mass(mass)) == mass (왕복 무손실)이므로, 이 BimIR 경로는
      기존 매스 경로와 '동일 파라미터'로 generate()를 호출한다 → 동일 IFC(요소·기하 동일).
      (IFC의 GlobalId는 ifcopenshell.guid.new()로 매 호출 랜덤이라 바이트 동일은 불가 — 구조 동등이 정답.)

    glb/QTO의 BimIR 소비 전환은 다음 세션 범위다(이 세션은 IFC 대표 1곳만).
    """
    from app.services.bim.bimir_adapters import mass_from_bimir

    mass = mass_from_bimir(model)
    return build_ifc_from_mass(mass, project_name=project_name)
