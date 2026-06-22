"""INC-4 — 픽셀/도면단위 → 실척 축척 환산: 결정론·assumed 표면화·미확정 무변환."""
from app.contracts.drawing_extraction import DrawingExtraction, ExtractedElement
from app.contracts.enums import ScaleSource
from app.contracts.preflight import ScaleResult
from app.services.extraction.scale_convert import apply_scale, real_area, real_length


def _scale(denom, assumed=False, source=ScaleSource.NOTATION):
    return ScaleResult(scale_denominator=denom, source=source, assumed=assumed)


def test_real_conversion_deterministic():
    assert real_area(2.0, 100.0) == 20000.0  # 2 × 100²
    assert real_length(3.0, 50.0) == 150.0   # 3 × 50
    assert real_area(2.0, 100.0) == real_area(2.0, 100.0)  # 결정론


def test_apply_scale_fills_real_from_px():
    ext = DrawingExtraction(elements=[
        ExtractedElement(element_id="e", semantic_hint="EAVE", area_px=2.0, length_px=0.3)])
    apply_scale(ext, _scale(100.0))
    el = ext.elements[0]
    assert el.area == 20000.0 and el.length == 30.0
    assert el.provenance["scale_denominator"] == 100.0 and el.provenance["scale_source"] == "NOTATION"


def test_apply_scale_assumed_flagged():
    ext = DrawingExtraction(elements=[
        ExtractedElement(element_id="e", semantic_hint="PILOTIS", area_px=1.0)])
    apply_scale(ext, _scale(50.0, assumed=True, source=ScaleSource.USER))
    assert ext.elements[0].provenance.get("scale_assumed") is True  # 가정 축척 — 신뢰 제한 표면화


def test_apply_scale_none_no_change():
    ext = DrawingExtraction(elements=[
        ExtractedElement(element_id="e", semantic_hint="PILOTIS", area_px=1.0)])
    apply_scale(ext, None)  # 축척 미확정 → 무변환(픽셀값 미승계, 날조 금지)
    assert ext.elements[0].area is None


def test_apply_scale_keeps_existing_real_area():
    # 실척 area가 이미 있으면 px 환산으로 덮어쓰지 않음.
    ext = DrawingExtraction(elements=[
        ExtractedElement(element_id="e", semantic_hint="PILOTIS", area=500.0, area_px=1.0)])
    apply_scale(ext, _scale(100.0))
    assert ext.elements[0].area == 500.0
