"""코드리뷰 iter6 견고성 — calc_engine 필수키 결손·citation ISO 날짜·land_card 어댑터 구분."""
from datetime import date, datetime

import pytest

from app.core.errors import DomainError
from app.services.verify.citation_check import _to_date


def test_calc_engine_missing_key_is_domain_error():
    # 필수 페이로드 키 결손 → RuleContractError(DomainError, 422) — KeyError(500 붕괴) 방지.
    from app.contracts.legal_quantity import CalcTarget
    from app.contracts.versioning import Snapshot, Version
    from app.services.legal_calc.calc_engine import CalcEngine
    from app.services.legal_calc.variable_seed import build_calc_variable_registry
    eng = CalcEngine(base_date=date(2026, 1, 1), registry=build_calc_variable_registry())
    v = Version(version="v1", axis_date=date(2026, 1, 1))
    snap = Snapshot(snapshot_id="s", effective_date=date(2026, 1, 1),
                    ruleset_version=v, calc_rule_version=v)
    with pytest.raises(DomainError):  # outer_area 누락
        eng.compute(CalcTarget.BUILDING_AREA, payload={}, elements=[], snapshot=snap)


def test_citation_to_date_parses_iso():
    assert _to_date("2026-01-01T09:00:00") == date(2026, 1, 1)  # ISO datetime 문자열
    assert _to_date(datetime(2026, 1, 1, 9)) == date(2026, 1, 1)  # datetime 객체
    assert _to_date("2026-01-01") == date(2026, 1, 1)            # ISO date
    assert _to_date("bad") is None
