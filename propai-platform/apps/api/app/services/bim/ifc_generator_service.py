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

        logger.info(
            "IFC 생성 완료",
            floors=n, width=bw, depth=bd, height=round(n * fh, 1),
            entities=len(list(model)),
        )
        return model.to_string().encode("utf-8")

    # ── 내부 헬퍼 ──

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
    """AutoDesignEngine.compute_optimal_mass() 결과 dict로 IFC를 생성하는 편의 함수."""
    return IfcGeneratorService().generate(
        building_width_m=float(mass.get("building_width_m", 10.0)),
        building_depth_m=float(mass.get("building_depth_m", 10.0)),
        num_floors=int(mass.get("num_floors", 5)),
        floor_height_m=float(mass.get("floor_height_m", 3.0)),
        project_name=project_name,
    )
