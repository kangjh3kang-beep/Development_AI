"""대용량 IFC 파일 파싱 태스크.

100MB+ IFC 파일을 비동기로 파싱하여 물량산출 결과를 DB에 저장한다.
"""

import contextlib
import tempfile
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# IFC 요소 유형별 물량 산출 대상
_TARGET_TYPES = [
    "IfcWall", "IfcSlab", "IfcBeam", "IfcColumn",
    "IfcWindow", "IfcDoor", "IfcRoof", "IfcStair",
    "IfcRailing", "IfcCurtainWall",
]


async def run_parse_large_ifc(
    ctx: dict[str, Any],
    file_url: str,
    project_id: str,
) -> dict[str, Any]:
    """대용량 IFC 파싱 처리.

    1. MinIO에서 IFC 파일 다운로드
    2. ifcopenshell로 파싱 (요소별 물량 산출)
    3. 결과 DB 저장
    """
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    logger.info("대용량 IFC 파싱 시작", file_url=file_url, project_id=project_id)

    db: AsyncSession = ctx["db"]

    # 1. IFC 파일 다운로드
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
        tmp_path = tmp.name

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.get(file_url)
        response.raise_for_status()

        with open(tmp_path, "wb") as f:
            f.write(response.content)

    logger.info("IFC 다운로드 완료", size_mb=len(response.content) / 1_048_576)

    # 2. ifcopenshell로 파싱
    import ifcopenshell

    ifc_file = ifcopenshell.open(tmp_path)

    element_summary: list[dict[str, Any]] = []
    total_count = 0

    for ifc_type in _TARGET_TYPES:
        elements = ifc_file.by_type(ifc_type)
        count = len(elements)
        total_count += count

        if count == 0:
            continue

        # 물량 산출 (체적/면적 추출 시도)
        total_volume = 0.0
        total_area = 0.0

        for elem in elements:
            try:
                # IfcQuantityVolume / IfcQuantityArea 추출
                for rel in getattr(elem, "IsDefinedBy", []):
                    if hasattr(rel, "RelatingPropertyDefinition"):
                        prop_def = rel.RelatingPropertyDefinition
                        if hasattr(prop_def, "Quantities"):
                            for q in prop_def.Quantities:
                                q_type = q.is_a()
                                if q_type == "IfcQuantityVolume":
                                    total_volume += q.VolumeValue or 0
                                elif q_type == "IfcQuantityArea":
                                    total_area += q.AreaValue or 0
            except Exception:
                continue

        element_summary.append({
            "type": ifc_type,
            "count": count,
            "volume_m3": round(total_volume, 2),
            "area_sqm": round(total_area, 2),
        })

    # 3. DB에 결과 저장
    result_json = {
        "element_summary": element_summary,
        "total_element_count": total_count,
        "file_url": file_url,
    }

    await db.execute(
        text(
            "UPDATE designs SET bim_data = :data, updated_at = NOW() "
            "WHERE project_id = :pid"
        ),
        {"data": str(result_json), "pid": project_id},
    )
    await db.commit()

    # 임시 파일 삭제
    import os
    with contextlib.suppress(OSError):
        os.unlink(tmp_path)

    logger.info(
        "대용량 IFC 파싱 완료",
        project_id=project_id,
        element_count=total_count,
        types=len(element_summary),
    )
    return {
        "status": "completed",
        "project_id": project_id,
        "element_count": total_count,
        "element_summary": element_summary,
    }
