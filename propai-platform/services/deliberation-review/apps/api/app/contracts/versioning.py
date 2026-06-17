"""R0 — 버전축 계약(snapshot). 산정규칙과 법규셋을 한 기준일축에 결속(INV-6).

assert_synced(): calc_rule_version과 ruleset_version의 기준일축이 불일치하면 진행 거부.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.core.errors import VersionAxisError


class Version(BaseModel):
    """버전 식별자 + 기준일축(axis_date). 동일 axis_date끼리만 정합."""

    version: str
    axis_date: date


class Snapshot(BaseModel):
    """분석 1회의 버전 스냅샷. 산정규칙/법규셋 버전을 effective_date 축에 결속."""

    snapshot_id: str
    effective_date: date
    ruleset_version: Version
    calc_rule_version: Version

    def assert_synced(self) -> bool:
        """기준일축 불일치 시 VersionAxisError(진행 거부)."""
        if self.calc_rule_version.axis_date != self.ruleset_version.axis_date:
            raise VersionAxisError(
                f"version axis mismatch: calc={self.calc_rule_version.axis_date} "
                f"!= ruleset={self.ruleset_version.axis_date}"
            )
        if self.calc_rule_version.axis_date != self.effective_date:
            raise VersionAxisError(
                f"version axis mismatch: versions={self.calc_rule_version.axis_date} "
                f"!= snapshot.effective_date={self.effective_date}"
            )
        return True
