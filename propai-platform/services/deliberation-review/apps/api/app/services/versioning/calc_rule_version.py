"""R1.5 — 산정규칙 버전축(CalcRuleVersion). 산정규칙을 법규셋과 동일 snapshot_id로 결속(INV-6).

calc 버전과 ruleset 버전의 기준일축 불일치 시 VersionAxisError(진행 거부).
"""
from __future__ import annotations

from datetime import date

from app.contracts.versioning import Snapshot, Version
from app.core.errors import VersionAxisError


class CalcRuleVersion:
    def __init__(self, calc: Version) -> None:
        self.calc = calc

    def bind(
        self,
        ruleset: Version,
        snapshot_id: str = "",
        effective_date: date | None = None,
    ) -> Snapshot:
        if self.calc.axis_date != ruleset.axis_date:
            raise VersionAxisError(
                f"calc rule axis {self.calc.axis_date} != ruleset axis {ruleset.axis_date}"
            )
        snap = Snapshot(
            snapshot_id=snapshot_id,
            effective_date=effective_date or self.calc.axis_date,
            ruleset_version=ruleset,
            calc_rule_version=self.calc,
        )
        snap.assert_synced()
        return snap
