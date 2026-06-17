"""R0 — 버전축 동기화/정합(VersionAxis). 산정규칙·법규셋을 한 snapshot에 결속(INV-6).

build()는 생성 시점에 assert_synced로 기준일축 정합을 강제 → 불일치면 VersionAxisError(진행 거부).
"""
from __future__ import annotations

from datetime import date

from app.contracts.versioning import Snapshot, Version


class VersionAxis:
    @staticmethod
    def build(
        snapshot_id: str,
        effective_date: date,
        ruleset_version: Version,
        calc_rule_version: Version,
    ) -> Snapshot:
        snap = Snapshot(
            snapshot_id=snapshot_id,
            effective_date=effective_date,
            ruleset_version=ruleset_version,
            calc_rule_version=calc_rule_version,
        )
        snap.assert_synced()
        return snap

    @staticmethod
    def assert_synced(snapshot: Snapshot) -> bool:
        return snapshot.assert_synced()
