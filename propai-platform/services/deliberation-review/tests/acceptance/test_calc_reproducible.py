"""AT-8 — 재현성: 동일 입력+스냅샷 → 동일 산정값."""
from datetime import date

from app.contracts.legal_quantity import CalcElement, CalcTarget
from app.contracts.semantic_element import SemanticType
from app.contracts.versioning import Snapshot, Version


def _snapshot() -> Snapshot:
    v = Version(version="v-1", axis_date=date(2026, 1, 1))
    return Snapshot(snapshot_id="snap-1", effective_date=date(2026, 1, 1),
                    ruleset_version=v, calc_rule_version=v)


def _compute():
    from app.services.legal_calc.calc_engine import CalcEngine

    return CalcEngine().compute(
        target=CalcTarget.BUILDING_AREA,
        payload={"outer_area": 600.0},
        elements=[CalcElement(semantic_type=SemanticType.PILOTIS, area=100.0, confidence=0.95)],
        snapshot=_snapshot(),
    )


def test_calc_reproducible():
    assert _compute() == _compute()
