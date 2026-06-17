"""AT-2/AT-3 — 원장 충돌 밴드초과 보류 + 필수 변수 결손 MISSING."""
from app.contracts.enums import Method, RecordStatus
from app.core.parameters import param
from app.services.ledger.evidence_ledger import EvidenceLedger


def test_ledger_conflict_beyond_band_holds():
    led = EvidenceLedger(tol_band=param("area_tol"))
    led.add("building_area", 500, method=Method.TABLE)
    led.add("building_area", 460, method=Method.VECTOR)
    r = led.resolve("building_area")
    assert r.value == 500  # 명기(TABLE) 우선 채택
    assert r.status == RecordStatus.HELD  # 밴드 초과(8% > 5%) → 보류
    assert r.conflicts  # 충돌 기록
    assert r.confidence < 1.0  # 신뢰도 하향


def test_within_band_agreed():
    led = EvidenceLedger(tol_band=param("area_tol"))
    led.add("building_area", 500, method=Method.TABLE)
    led.add("building_area", 495, method=Method.VECTOR)  # 1% < 5%
    r = led.resolve("building_area")
    assert r.status == RecordStatus.AGREED
    assert r.value == 500


def test_missing_required_quantity_is_explicit():
    r = EvidenceLedger().resolve("plot_area")
    assert r.status == RecordStatus.MISSING
    assert r.value is None
