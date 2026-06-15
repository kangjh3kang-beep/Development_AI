"""BIM 서비스."""
from typing import Any, Dict, List


class BIMService:
    """IFC 파싱 + 물량 산출 서비스."""

    def parse_ifc_metadata(self, ifc_path: str) -> dict:
        """IFC 파일 메타데이터를 실제로 읽는다(ifcopenshell).

        읽기 실패(라이브러리 미설치·손상 파일 등) 시 가짜 도구명(예: 'Revit 2024')을
        지어내지 않고 정직하게 None(미상)으로 표기한다 — 할루시네이션 금지.
        """
        meta: dict[str, Any] = {
            "schema": None, "file_path": ifc_path,
            "authoring_tool": None, "project_name": None, "element_count": None,
        }
        try:
            import ifcopenshell  # noqa: PLC0415
            f = ifcopenshell.open(ifc_path)
            meta["schema"] = f.schema
            projs = f.by_type("IfcProject")
            if projs:
                meta["project_name"] = getattr(projs[0], "Name", None)
            apps = f.by_type("IfcApplication")
            if apps:
                meta["authoring_tool"] = (
                    getattr(apps[0], "ApplicationFullName", None)
                    or getattr(apps[0], "ApplicationIdentifier", None)
                )
            meta["element_count"] = len(f.by_type("IfcProduct"))
        except Exception:  # noqa: BLE001 — 읽기 불가 시 미상 유지(가짜값 금지)
            pass
        return meta

    def extract_quantities(self, elements: list[dict]) -> dict:
        quantities = {}
        for e in elements:
            etype = e.get("element_type", "unknown")
            qty = e.get("quantity", 0)
            quantities[etype] = quantities.get(etype, 0) + qty
        return {
            "quantities": quantities,
            "element_count": len(elements),
            "total_quantity": sum(e.get("quantity", 0) for e in elements),
        }

    def extract_quantities_with_work_codes(
        self, elements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """IFC 요소에 공종코드를 매핑하여 물량을 산출한다.

        각 element dict에 'element_type' (IFC 유형)과 'quantity' 필드가 필요하다.
        """
        from app.services.cost.ifc_work_map import map_ifc_to_work_codes

        result: list[dict[str, Any]] = []
        for elem in elements:
            ifc_type = elem.get("element_type", "")
            qty = elem.get("quantity", 0)
            global_id = elem.get("global_id", "")
            name = elem.get("name", "")
            floor = elem.get("floor_level", "")
            unit = elem.get("unit", "m3")

            work_codes = map_ifc_to_work_codes(ifc_type)
            for wc, wn in work_codes:
                result.append({
                    "ifc_global_id": global_id,
                    "ifc_object_type": ifc_type,
                    "ifc_object_name": name,
                    "work_code": wc,
                    "work_name": wn,
                    "floor_level": floor,
                    "quantity": qty,
                    "unit": unit,
                    "extraction_method": "AI_AUTO",
                })

        return result
