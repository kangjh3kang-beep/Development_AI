"""P1 — BIM/IFC 이중경로: IFC 파싱·타입 매핑·이중경로 선택·파이프라인 BIM 배선."""
from datetime import date

from app.adapters.bim.ifc_parser import IfcParser
from app.contracts.analysis import AnalysisInput
from app.contracts.semantic_element import SemanticType
from app.services.extraction.dual_path import resolve_elements
from app.services.pipeline.analysis_pipeline import run_analysis

_IFC = """ISO-10303-21;
DATA;
#1= IFCWALLSTANDARDCASE('guid-w1',#2,'외벽-1',$,$);
#2= IFCSTAIR('guid-s1',#2,'직통계단-1',$,$);
#3= IFCSLAB('guid-b1',#2,'지하층 슬래브',$,$);
#4= IFCSPACE('guid-p1',#2,'주차장',$,$);
#5= IFCBUILDINGELEMENTPROXY('guid-x1',#2,'미상요소',$,$);
ENDSEC;
END-ISO-10303-21;
"""


def test_ifc_parse_maps_types():
    model = IfcParser().parse(_IFC)
    by_type = {e.ifc_type: e.semantic_type for e in model.elements}
    assert by_type["IFCWALLSTANDARDCASE"] == SemanticType.EXT_WALL
    assert by_type["IFCSTAIR"] == SemanticType.CORE_STAIR
    assert by_type["IFCSLAB"] == SemanticType.BASEMENT      # 이름 '지하' 힌트
    assert by_type["IFCSPACE"] == SemanticType.PARKING      # 이름 '주차' 힌트
    assert by_type["IFCBUILDINGELEMENTPROXY"] == SemanticType.UNKNOWN  # 미매핑→UNKNOWN(INV-9)


def test_dual_path_prefers_bim():
    r = resolve_elements({"ifc": _IFC, "elements": [{"element_id": "e1", "features": {}}]})
    assert r.source == "BIM"
    assert any(s.semantic_type == SemanticType.CORE_STAIR for s in r.semantic_elements)


def test_dual_path_falls_back_to_vllm():
    r = resolve_elements({"elements": [{"element_id": "e1", "features": {"semantic_hint": "PILOTIS", "hint_strength": 0.9}}]})
    assert r.source == "VLLM"
    assert r.semantic_elements


def test_dual_path_none_surfaced():
    assert resolve_elements({}).source == "none"


def test_pipeline_bim_wired():
    r = run_analysis(AnalysisInput(pnu="1111010100100000002", application_date=date(2026, 1, 1),
                                   drawing={"scale_text": "1:100"}, ifc=_IFC))
    assert r.extraction_source == "BIM"
    assert r.bim_elements
    assert any(e.semantic_type == SemanticType.PARKING for e in r.bim_elements)
