"""BIM/IFC 파싱 및 물량산출 서비스.

ifcopenshell 기반 IFC 파일 분석.
목표: 물량산출 오차 ≤ 2% (CoVe O1).

흐름:
1. MinIO에서 IFC 파일 다운로드
2. ifcopenshell로 파싱
3. 요소별 물량 집계 (체적, 면적, 개수)
4. Three.js용 geometry JSON 변환 (Codex 연동)
"""

import contextlib
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

        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError(
                "minio 패키지가 설치되지 않아 IFC 파일을 다운로드할 수 없습니다"
            ) from exc

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
        # 요소 단위 물량(공종코드 매핑·bim_quantities INSERT 입력) — 집계 키와 병행.
        elements: list[dict] = []

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

            # 요소 단위 레코드 — BIMService.extract_quantities_with_work_codes 입력 형식.
            # 물량 기준: 체적(m3)이 0이면 면적(m2)을 quantity 로 사용(정직 — 가짜값 없음).
            qty = volume if volume else area
            elements.append({
                "element_type": element_type,
                "global_id": getattr(element, "GlobalId", "") or "",
                "name": getattr(element, "Name", "") or "",
                "quantity": qty,
                "unit": "m3" if volume else "m2",
                "floor_level": "",
            })

        return {
            "ifc_version": ifc_version,
            "total_volume_m3": total_volume,
            "total_area_sqm": total_area,
            "element_count": element_count,
            "material_breakdown": [
                {"type": k, **v} for k, v in materials.items()
            ],
            # 신규: 요소 단위 물량(기존 키 불변 — additive).
            "elements": elements,
        }

    async def _persist_bim_quantities(
        self,
        project_id: UUID,
        tenant_id: UUID,
        elements: list[dict],
    ) -> int:
        """요소 단위 물량을 공종코드로 매핑해 bim_quantities 로 교체 영속한다.

        commit 은 호출측(analyze_ifc/generate_ifc_from_design)이 수행한다(동일 세션 일괄 처리).
        매핑되는 공종이 없거나 요소가 없으면 0행을 반환한다(정직 — 가짜 행 없음).

        ★PR#315 H1(전역 전파방지): 실제 DB 쓰기는 공용 헬퍼 replace_bim_quantities 를
          경유한다 — INSERT 전 같은 project_id·extraction_method(AI_AUTO) 기존 행을 DELETE
          하므로, 같은 프로젝트를 재분석/재생성해도 물량이 배가되지 않는다(비멱등 이중적재
          방지). upload_ifc(app/routers/cost.py)도 동일 헬퍼를 경유 — 한 곳 수정이 3개
          쓰기 경로(analyze/generate/upload) 전부에 적용된다.
        """
        if not elements:
            return 0

        from app.services.cost.bim_quantity_writer import replace_bim_quantities
        from app.services.cost.ifc_work_map import map_ifc_to_work_codes

        mapped_rows: list[dict] = []
        for elem in elements:
            ifc_type = elem.get("element_type", "") or ""
            work_codes = map_ifc_to_work_codes(ifc_type)
            for work_code, _work_name in work_codes:
                mapped_rows.append({
                    "ifc_global_id": elem.get("global_id") or None,
                    "ifc_object_type": ifc_type or None,
                    "ifc_object_name": elem.get("name") or None,
                    "work_code": work_code,
                    "floor_level": elem.get("floor_level") or None,
                    "quantity": elem.get("quantity", 0) or 0,
                    "unit": elem.get("unit") or None,
                    "extraction_method": "AI_AUTO",
                })

        return await replace_bim_quantities(self.db, project_id, tenant_id, mapped_rows)

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

        # 3-1. 요소 단위 물량 → 공종코드 매핑 → bim_quantities bulk INSERT(동일 세션).
        # 요소 정보가 없으면(구버전 _parse_ifc/mock) 조용히 스킵 — 하위호환.
        # ★독립리뷰 MEDIUM(전역 전파방지): generate_ifc_from_design과 동일한 graceful
        #   래퍼를 형제 경로에도 적용 — 영속 실패가 이미 커밋된 Design을 500으로 고아화
        #   하지 않게 rollback 후 경고만 남긴다(분석 응답 무영향·가짜 성공 표기 없음).
        bim_quantity_rows = 0
        try:
            bim_quantity_rows = await self._persist_bim_quantities(
                project_id=project_id,
                tenant_id=tenant_id,
                elements=result.get("elements") or [],
            )
            if bim_quantity_rows:
                await self.db.commit()
        except Exception as exc:  # noqa: BLE001 — 영속 실패는 분석 응답을 막지 않는다
            await self.db.rollback()
            logger.warning(
                "IFC 분석 bim_quantities 영속 실패(분석 응답 무영향)",
                project_id=str(project_id),
                error=str(exc),
            )
            bim_quantity_rows = 0

        # 4. 임시 파일 정리
        import os
        os.unlink(filepath)

        logger.info(
            "IFC 분석 완료",
            elements=result["element_count"],
            bim_quantities=bim_quantity_rows,
        )

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

    @staticmethod
    def _design_params_to_mass(
        total_area_sqm: float,
        floors: int,
        structure_type: str = "RC",
    ) -> dict:
        """설계 파라미터(연면적·층수·구조형식)를 정본 생성기 입력 매스 dict로 사상한다.

        연면적 ÷ 층수 = 층당 바닥면적 → 정사각 가정으로 한 변 길이 산출
        (building_width_m = building_depth_m). 층고는 legacy와 동일 3.0m.

        ★PR#315 M3(전역 전파방지): legacy 는 RC/비RC 벽두께를 0.2/0.15 로 분기했으나,
        정본 위임 초판은 build_ifc_from_mass 가 wall_thickness_m 을 forwarding 하지 않아
        고정 0.2 로 근사되며 구조형식 차이가 물량에 반영되지 않았다. build_ifc_from_mass
        가 이제 mass["wall_thickness_m"]을 forwarding 하므로(같은 PR 수정) 여기서 구조형식
        분기값을 실제로 전달 — 압출·BaseQuantities 양쪽에 정확히 반영된다(근사 표기 불필요).
        """
        import math

        n = max(int(floors), 1)
        floor_area = max(float(total_area_sqm), 1.0) / n
        side = math.sqrt(floor_area)
        wall_thickness_m = 0.2 if structure_type == "RC" else 0.15
        return {
            "building_width_m": side,
            "building_depth_m": side,
            "num_floors": n,
            "floor_height_m": 3.0,
            "wall_thickness_m": wall_thickness_m,
        }

    async def generate_ifc_from_design(
        self,
        project_id: UUID,
        tenant_id: UUID,
        total_area_sqm: float = 1000.0,
        floors: int = 10,
        structure_type: str = "RC",
    ) -> BIMQuantityResponse:
        """설계 파라미터로 IFC 파일을 자동 생성한다.

        ★정본 위임(전역 전파방지): 자체 엔티티 조립(지오메트리·물량 부재로 '빈 IFC'
          산출 — /threejs 빈 지오메트리·/analyze 물량 0)을 제거하고, 실압출
          (IfcExtrudedAreaSolid)·BaseQuantities(IfcElementQuantity)를 부착하는 정본
          생성기 app.services.bim.ifc_generator_service.build_ifc_from_mass 로 위임한다.
          → /threejs(지오메트리)·/analyze(물량 재적산)가 실데이터를 반환한다.
        생성 IFC 를 자사 파서(_parse_ifc)로 재적산해 응답 물량을 산출하고, MinIO 업로드
        후 Design + bim_quantities 로 영속한다(업로드/영속 실패는 graceful — 메트릭 반환
        무영향, 가짜 성공 표기 없음). ifcopenshell 미설치 시 build_ifc_from_mass 내부
        import 가 명시 실패한다(무목업 — 가짜 IFC 없음).
        """
        import io
        import os
        import tempfile

        from app.services.bim.ifc_generator_service import build_ifc_from_mass

        logger.info(
            "IFC 자동 생성 시작(정본 위임)",
            project_id=str(project_id),
            area=total_area_sqm,
            floors=floors,
        )

        # 1. 정본 생성기로 실압출 IFC 생성(지오메트리 + BaseQuantities 부착).
        mass = self._design_params_to_mass(total_area_sqm, floors, structure_type)
        ifc_bytes = build_ifc_from_mass(mass, project_name=f"PropAI {project_id}")

        # 2. 임시 파일로 기록 후 자사 파서로 재적산(자기 생성 IFC 자가 적산 루프).
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp_path = tmp.name
        Path(tmp_path).write_bytes(ifc_bytes)

        file_url: str | None = None
        storage_skipped = False
        storage_error: str | None = None
        try:
            result = self._parse_ifc(tmp_path)

            # 3. MinIO 업로드(실패해도 물량/메트릭은 반환 — 저장만 스킵).
            try:
                from minio import Minio

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
                minio_client.put_object(
                    bucket, object_name, io.BytesIO(ifc_bytes),
                    length=len(ifc_bytes), content_type="application/x-step",
                )
                file_url = f"{self.settings.minio_url}/{bucket}/{object_name}"
            except ImportError:
                storage_skipped = True
                storage_error = "minio 패키지 미설치 — IFC 파일 저장 스킵"
                logger.warning("MinIO 미설치로 IFC 저장 스킵", project_id=str(project_id))
            except Exception as exc:  # noqa: BLE001 (저장 실패는 메트릭 반환을 막지 않음)
                storage_skipped = True
                storage_error = f"MinIO 저장 실패: {exc}"
                logger.warning(
                    "MinIO 업로드 실패로 IFC 저장 스킵",
                    project_id=str(project_id),
                    error=str(exc),
                )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

        # 4. DB 저장(재적산 물량 기반 — 정본 지오메트리와 정합).
        design = Design(
            tenant_id=tenant_id,
            project_id=project_id,
            design_type="bim_ifc",
            file_url=file_url,
            total_area_sqm=result["total_area_sqm"],
            total_volume_m3=result["total_volume_m3"],
            element_count=result["element_count"],
            metadata_json={
                "material_breakdown": result["material_breakdown"],
                "generated": True,
                "structure_type": structure_type,
                "storage_skipped": storage_skipped,
                "storage_error": storage_error,
            },
        )
        self.db.add(design)
        await self.db.commit()
        await self.db.refresh(design)

        # 5. 요소 단위 물량 → 공종코드 매핑 → bim_quantities bulk INSERT(동일 세션).
        # 실패해도 IFC 생성 응답은 정상 반환한다(graceful) — 이미 커밋된 Design은 무영향,
        # 물량 영속만 스킵되고 경고 로그로 남긴다(무목업 — 가짜 성공 표기 없음).
        bim_quantity_rows = 0
        try:
            bim_quantity_rows = await self._persist_bim_quantities(
                project_id=project_id,
                tenant_id=tenant_id,
                elements=result.get("elements") or [],
            )
            if bim_quantity_rows:
                await self.db.commit()
        except Exception as exc:  # noqa: BLE001 — 영속 실패는 생성 응답을 막지 않는다
            await self.db.rollback()
            logger.warning(
                "IFC 자동생성 bim_quantities 영속 실패(생성 응답 무영향)",
                project_id=str(project_id),
                error=str(exc),
            )
            bim_quantity_rows = 0

        logger.info(
            "IFC 자동 생성 완료(정본 위임)",
            elements=result["element_count"],
            bim_quantities=bim_quantity_rows,
        )

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
