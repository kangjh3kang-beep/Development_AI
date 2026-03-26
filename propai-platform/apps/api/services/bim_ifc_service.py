"""BIM/IFC 파싱 및 물량산출 서비스.

ifcopenshell 기반 IFC 파일 분석.
목표: 물량산출 오차 ≤ 2% (CoVe O1).

흐름:
1. MinIO에서 IFC 파일 다운로드
2. ifcopenshell로 파싱
3. 요소별 물량 집계 (체적, 면적, 개수)
4. Three.js용 geometry JSON 변환 (Codex 연동)
"""

from pathlib import Path
from uuid import UUID

import structlog
from packages.schemas.models import BIMQuantityResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.design import Design

logger = structlog.get_logger(__name__)


class BIMIFCService:
    """BIM/IFC 파싱 및 물량산출 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def _download_ifc(self, file_url: str) -> str:
        """MinIO에서 IFC 파일을 다운로드하여 임시 경로를 반환한다."""
        import tempfile

        from minio import Minio

        client = Minio(
            self.settings.minio_url.replace("http://", ""),
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=False,
        )

        # URL에서 bucket/object 분리
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp_path = tmp.name
        parts = file_url.split("/", 3)
        bucket = parts[2] if len(parts) > 2 else "propai-bim"
        object_name = parts[3] if len(parts) > 3 else file_url

        client.fget_object(bucket, object_name, tmp_path)
        return tmp_path

    def _parse_ifc(self, filepath: str) -> dict:
        """IFC 파일을 파싱하여 요소별 물량을 집계한다."""
        import ifcopenshell

        ifc_file = ifcopenshell.open(filepath)
        ifc_version = ifc_file.schema

        materials: dict[str, dict] = {}
        total_volume = 0.0
        total_area = 0.0
        element_count = 0

        for element in ifc_file.by_type("IfcBuildingElement"):
            element_count += 1
            element_type = element.is_a()

            # 물량 속성 추출
            volume = 0.0
            area = 0.0
            for definition in element.IsDefinedBy:
                if definition.is_a("IfcRelDefinesByProperties"):
                    prop_set = definition.RelatingPropertyDefinition
                    if prop_set.is_a("IfcElementQuantity"):
                        for quantity in prop_set.Quantities:
                            if quantity.is_a("IfcQuantityVolume"):
                                volume = quantity.VolumeValue or 0.0
                            elif quantity.is_a("IfcQuantityArea"):
                                area = quantity.AreaValue or 0.0

            total_volume += volume
            total_area += area

            if element_type not in materials:
                materials[element_type] = {"count": 0, "volume_m3": 0.0, "area_sqm": 0.0}
            materials[element_type]["count"] += 1
            materials[element_type]["volume_m3"] += volume
            materials[element_type]["area_sqm"] += area

        return {
            "ifc_version": ifc_version,
            "total_volume_m3": total_volume,
            "total_area_sqm": total_area,
            "element_count": element_count,
            "material_breakdown": [
                {"type": k, **v} for k, v in materials.items()
            ],
        }

    def _generate_threejs_geometry(self, filepath: str) -> dict:
        """Three.js용 geometry JSON을 생성한다.

        Codex의 3D 뷰어 컴포넌트에 전달.
        목표: 1,000요소 ≤ 5초 로딩 (CoVe O5).
        """
        import ifcopenshell
        import ifcopenshell.geom

        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        ifc_file = ifcopenshell.open(filepath)
        geometries = []

        for element in ifc_file.by_type("IfcBuildingElement"):
            try:
                shape = ifcopenshell.geom.create_shape(settings, element)
                verts = shape.geometry.verts
                faces = shape.geometry.faces
                geometries.append({
                    "id": element.GlobalId,
                    "type": element.is_a(),
                    "vertices": list(verts),
                    "faces": list(faces),
                })
            except Exception:
                continue  # geometry 변환 실패 시 건너뜀

        return {"geometries": geometries, "count": len(geometries)}

    async def analyze_ifc(
        self,
        project_id: UUID,
        tenant_id: UUID,
        file_url: str,
    ) -> BIMQuantityResponse:
        """IFC 파일을 분석하여 물량산출 결과를 반환한다."""
        logger.info("IFC 분석 시작", project_id=str(project_id))

        # 1. 파일 다운로드
        filepath = await self._download_ifc(file_url)

        # 2. 파싱 및 물량 집계
        result = self._parse_ifc(filepath)

        # 3. DB 저장
        design = Design(
            tenant_id=tenant_id,
            project_id=project_id,
            design_type="bim_ifc",
            file_url=file_url,
            total_area_sqm=result["total_area_sqm"],
            total_volume_m3=result["total_volume_m3"],
            element_count=result["element_count"],
            metadata_json={"material_breakdown": result["material_breakdown"]},
        )
        self.db.add(design)
        await self.db.commit()
        await self.db.refresh(design)

        # 4. 임시 파일 정리
        import os
        os.unlink(filepath)

        logger.info("IFC 분석 완료", elements=result["element_count"])

        return BIMQuantityResponse(
            id=design.id,
            project_id=design.project_id,
            total_volume_m3=result["total_volume_m3"],
            total_area_sqm=result["total_area_sqm"],
            material_breakdown=result["material_breakdown"],
            element_count=result["element_count"],
            ifc_version=result["ifc_version"],
            created_at=design.created_at,
        )

    async def generate_ifc_from_design(
        self,
        project_id: UUID,
        tenant_id: UUID,
        total_area_sqm: float = 1000.0,
        floors: int = 10,
        structure_type: str = "RC",
    ) -> BIMQuantityResponse:
        """설계 파라미터로 IFC 파일을 자동 생성한다.

        ifcopenshell로 기본 건물 모델(벽/슬라브)을 생성하고
        MinIO에 업로드한 뒤 물량산출 결과를 반환한다.
        """
        import io
        import math
        import tempfile

        import ifcopenshell
        from minio import Minio

        logger.info(
            "IFC 자동 생성 시작",
            project_id=str(project_id),
            area=total_area_sqm,
            floors=floors,
        )

        # IFC 파일 생성
        ifc = ifcopenshell.file(schema="IFC4")

        # 프로젝트/사이트/건물 계층
        owner_history = ifc.create_entity("IfcOwnerHistory")
        project = ifc.create_entity(
            "IfcProject",
            GlobalId=ifcopenshell.guid.new(),
            Name="PropAI Generated",
            OwnerHistory=owner_history,
        )
        site = ifc.create_entity(
            "IfcSite",
            GlobalId=ifcopenshell.guid.new(),
            Name="Site",
            OwnerHistory=owner_history,
        )
        building = ifc.create_entity(
            "IfcBuilding",
            GlobalId=ifcopenshell.guid.new(),
            Name="Building",
            OwnerHistory=owner_history,
        )
        ifc.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                          RelatingObject=project, RelatedObjects=[site])
        ifc.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                          RelatingObject=site, RelatedObjects=[building])

        # 층별 건물 요소 생성
        floor_area = total_area_sqm / floors
        side = math.sqrt(floor_area)
        floor_height = 3.0
        element_count = 0
        total_volume = 0.0
        total_area = 0.0

        materials: dict[str, dict] = {}

        for f in range(floors):
            storey = ifc.create_entity(
                "IfcBuildingStorey",
                GlobalId=ifcopenshell.guid.new(),
                Name=f"{f + 1}F",
                Elevation=f * floor_height,
                OwnerHistory=owner_history,
            )
            ifc.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                              RelatingObject=building, RelatedObjects=[storey])

            # 슬라브 (바닥)
            slab = ifc.create_entity(
                "IfcSlab",
                GlobalId=ifcopenshell.guid.new(),
                Name=f"Slab-{f + 1}F",
                OwnerHistory=owner_history,
            )
            slab_volume = side * side * 0.2  # 두께 0.2m
            slab_area = side * side
            total_volume += slab_volume
            total_area += slab_area
            element_count += 1
            materials.setdefault("IfcSlab", {"count": 0, "volume_m3": 0.0, "area_sqm": 0.0})
            materials["IfcSlab"]["count"] += 1
            materials["IfcSlab"]["volume_m3"] += slab_volume
            materials["IfcSlab"]["area_sqm"] += slab_area

            ifc.create_entity("IfcRelContainedInSpatialStructure",
                              GlobalId=ifcopenshell.guid.new(),
                              RelatingStructure=storey,
                              RelatedElements=[slab])

            # 벽 (4면)
            wall_thickness = 0.2 if structure_type == "RC" else 0.15
            for i in range(4):
                ifc.create_entity(
                    "IfcWall",
                    GlobalId=ifcopenshell.guid.new(),
                    Name=f"Wall-{f + 1}F-{i + 1}",
                    OwnerHistory=owner_history,
                )
                wall_volume = side * floor_height * wall_thickness
                wall_area = side * floor_height
                total_volume += wall_volume
                total_area += wall_area
                element_count += 1
                materials.setdefault("IfcWall", {"count": 0, "volume_m3": 0.0, "area_sqm": 0.0})
                materials["IfcWall"]["count"] += 1
                materials["IfcWall"]["volume_m3"] += wall_volume
                materials["IfcWall"]["area_sqm"] += wall_area

        # 임시 파일로 IFC 저장
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp_path = tmp.name
        ifc.write(tmp_path)

        # MinIO 업로드
        import os

        minio_client = Minio(
            self.settings.minio_url.replace("http://", ""),
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=False,
        )
        bucket = "propai-bim"
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)

        object_name = f"generated/{project_id}/{project_id}_auto.ifc"
        ifc_bytes = Path(tmp_path).read_bytes()
        minio_client.put_object(
            bucket, object_name, io.BytesIO(ifc_bytes),
            length=len(ifc_bytes), content_type="application/x-step",
        )
        os.unlink(tmp_path)

        file_url = f"{self.settings.minio_url}/{bucket}/{object_name}"

        # DB 저장
        design = Design(
            tenant_id=tenant_id,
            project_id=project_id,
            design_type="bim_ifc",
            file_url=file_url,
            total_area_sqm=total_area,
            total_volume_m3=total_volume,
            element_count=element_count,
            metadata_json={
                "material_breakdown": [{"type": k, **v} for k, v in materials.items()],
                "generated": True,
                "structure_type": structure_type,
            },
        )
        self.db.add(design)
        await self.db.commit()
        await self.db.refresh(design)

        logger.info("IFC 자동 생성 완료", elements=element_count)

        return BIMQuantityResponse(
            id=design.id,
            project_id=design.project_id,
            total_volume_m3=total_volume,
            total_area_sqm=total_area,
            material_breakdown=[{"type": k, **v} for k, v in materials.items()],
            element_count=element_count,
            ifc_version="IFC4",
            created_at=design.created_at,
        )
