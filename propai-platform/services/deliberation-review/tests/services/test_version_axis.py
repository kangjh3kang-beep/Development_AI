"""AT-7 — 버전축 불일치 시 진행 거부."""
from datetime import date

import pytest

from app.contracts.versioning import Snapshot, Version
from app.core.errors import VersionAxisError
from app.services.versioning.version_axis import VersionAxis


def test_version_axis_mismatch_refused():
    v_calc = Version(version="calc-1", axis_date=date(2026, 1, 1))
    v_rule = Version(version="rule-1", axis_date=date(2025, 1, 1))
    snap = Snapshot(
        snapshot_id="s1",
        effective_date=date(2026, 1, 1),
        ruleset_version=v_rule,
        calc_rule_version=v_calc,
    )
    with pytest.raises(VersionAxisError):
        snap.assert_synced()


def test_version_axis_synced_ok():
    v = Version(version="v-1", axis_date=date(2026, 1, 1))
    snap = VersionAxis.build(
        snapshot_id="s2",
        effective_date=date(2026, 1, 1),
        ruleset_version=v,
        calc_rule_version=v,
    )
    assert snap.assert_synced() is True
