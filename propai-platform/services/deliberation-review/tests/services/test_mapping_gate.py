"""AT-8 — 오매핑(저신뢰) → 정성 보류 degrade(무음 오통과 금지)."""
from app.contracts.enums import RecordStatus
from app.core.parameters import param
from app.services.mapping.mapping_gate import MappingGate

LOW_CONF_MAPPING = {"source_criterion": "지자체 경관기준 X", "standard_item": "경관", "confidence": 0.3}
HIGH_CONF_MAPPING = {"source_criterion": "지자체 주차기준 Y", "standard_item": "주차", "confidence": 0.95}


def test_mismapped_criterion_holds():
    m = MappingGate(threshold=param("mapping_confidence_threshold")).map(LOW_CONF_MAPPING)
    assert m.status == RecordStatus.HELD
    assert m.silent_pass is False


def test_confident_mapping_agreed():
    m = MappingGate(threshold=param("mapping_confidence_threshold")).map(HIGH_CONF_MAPPING)
    assert m.status == RecordStatus.AGREED
    assert m.silent_pass is False
