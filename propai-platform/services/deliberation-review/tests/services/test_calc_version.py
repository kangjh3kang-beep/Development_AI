"""AT-6/AT-7 — 산정규칙 버전축 불일치 거부 + 기준일이 유효 산정규칙 버전 선택."""
from datetime import date

import pytest

from app.contracts.calc_rule import CalcRuleSet, VersionedRules
from app.contracts.legal_quantity import CalcElement, CalcTarget
from app.contracts.semantic_element import SemanticType
from app.contracts.versioning import Version
from app.core.errors import VersionAxisError
from app.services.legal_calc.calc_engine import CalcEngine
from app.services.versioning.calc_rule_version import CalcRuleVersion


def test_calc_rule_version_axis_mismatch():
    v_calc = Version(version="calc-2026", axis_date=date(2026, 1, 1))
    v_rule = Version(version="rule-2025", axis_date=date(2025, 1, 1))
    with pytest.raises(VersionAxisError):
        CalcRuleVersion(calc=v_calc).bind(ruleset=v_rule)


def test_calc_engine_rejects_unsynced_snapshot():
    from app.contracts.versioning import Snapshot

    unsynced = Snapshot(
        snapshot_id="snap-bad",
        effective_date=date(2026, 1, 1),
        ruleset_version=Version(version="rule-2025", axis_date=date(2025, 1, 1)),
        calc_rule_version=Version(version="calc-2026", axis_date=date(2026, 1, 1)),
    )
    with pytest.raises(VersionAxisError):
        CalcEngine().compute(
            target=CalcTarget.BUILDING_AREA,
            payload={"outer_area": 600.0},
            elements=[CalcElement(semantic_type=SemanticType.PILOTIS, area=100.0, confidence=0.9)],
            snapshot=unsynced,
        )


def test_effective_date_selects_correct_calc_rule():
    rule_set = CalcRuleSet(
        versions=[
            VersionedRules(version="v2020", effective_date=date(2020, 1, 1),
                           params={"balcony_exclusion_depth": 1.0}),
            VersionedRules(version="v2025", effective_date=date(2025, 1, 1),
                           params={"balcony_exclusion_depth": 1.5}),
        ]
    )
    base_date = date(2026, 6, 1)
    engine = CalcEngine(rule_set=rule_set, base_date=base_date)
    q = engine.compute(
        target=CalcTarget.BUILDING_AREA,
        payload={"outer_area": 600.0},
        elements=[CalcElement(semantic_type=SemanticType.PILOTIS, area=100.0, confidence=0.9)],
    )
    assert q.calc_rule_version == rule_set.effective_on(base_date).version == "v2025"
