"""BIM 서비스."""
from typing import Any, Dict, List


class BIMService:
    """IFC 파싱 + 물량 산출 서비스."""

    def parse_ifc_metadata(self, ifc_path: str) -> Dict:
        return {
            "schema": "IFC4",
            "file_path": ifc_path,
            "authoring_tool": "Revit 2024",
            "project_name": "PropAI BIM Model",
        }

    def extract_quantities(self, elements: List[Dict]) -> Dict:
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
        self, elements: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """IFC 요소에 공종코드를 매핑하여 물량을 산출한다.

        각 element dict에 'element_type' (IFC 유형)과 'quantity' 필드가 필요하다.
        """
        from app.services.cost.ifc_work_map import map_ifc_to_work_codes

        result: List[Dict[str, Any]] = []
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
