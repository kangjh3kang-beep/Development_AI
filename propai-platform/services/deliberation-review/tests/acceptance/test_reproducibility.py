"""AT-8 — 재현성: 동일 입력+스냅샷 → 동일 input_hash, 동일 context.

추가(자기수렴 감사 1회차): 버전축 불일치 스냅샷은 Preflight 진입 거부(INV-6 배선).
"""
from datetime import date

import pytest

from app.contracts.versioning import Snapshot, Version
from app.core.errors import VersionAxisError
from app.services.preflight.preflight_gate import run_preflight


def _snapshot() -> Snapshot:
    v = Version(version="v-1", axis_date=date(2026, 1, 1))
    return Snapshot(
        snapshot_id="snap-1",
        effective_date=date(2026, 1, 1),
        ruleset_version=v,
        calc_rule_version=v,
    )


_INPUT = {
    "pnu": "1111010100100000002",
    "application_date": date(2026, 1, 1),
    "drawing": {"scale_text": "1:100"},
}


def test_reproducible_audit():
    snap = _snapshot()
    a = run_preflight(_INPUT, snap)
    b = run_preflight(_INPUT, snap)
    assert a.input_hash == b.input_hash
    assert a == b


def test_preflight_rejects_unsynced_snapshot():
    unsynced = Snapshot(
        snapshot_id="snap-bad",
        effective_date=date(2026, 1, 1),
        ruleset_version=Version(version="rule-1", axis_date=date(2025, 1, 1)),
        calc_rule_version=Version(version="calc-1", axis_date=date(2026, 1, 1)),
    )
    with pytest.raises(VersionAxisError):
        run_preflight(_INPUT, unsynced)
