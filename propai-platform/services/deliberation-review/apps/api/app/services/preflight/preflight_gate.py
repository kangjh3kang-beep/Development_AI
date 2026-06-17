"""R0 — Preflight 통합 게이트. 관할/기준일/축척을 PreflightContext로 잠금(INV-5).

입력해시로 재현성 보장(INV-7). 미확정+가정 플래그 허용하되 후속에 그대로 전파.
축척 전 chain 실패(PreflightRefused)는 상위로 전파 = 진행 거부.
"""
from __future__ import annotations

from typing import Any

from app.contracts.preflight import PreflightContext
from app.contracts.versioning import Snapshot
from app.core.hashing import input_hash
from app.services.preflight.base_date import BaseDateResolver
from app.services.preflight.jurisdiction import JurisdictionResolver
from app.services.preflight.scale_unit import ScaleUnitResolver


class PreflightGate:
    def __init__(
        self,
        jurisdiction_resolver: JurisdictionResolver | None = None,
        base_date_resolver: BaseDateResolver | None = None,
        scale_resolver: ScaleUnitResolver | None = None,
    ) -> None:
        self.jr = jurisdiction_resolver or JurisdictionResolver()
        self.bdr = base_date_resolver or BaseDateResolver()
        self.scr = scale_resolver or ScaleUnitResolver()

    def run(self, payload: dict[str, Any], snapshot_id: str) -> PreflightContext:
        ih = input_hash({"payload": payload, "snapshot_id": snapshot_id})

        jurisdiction = self.jr.resolve(
            pnu=payload["pnu"], manual=payload.get("manual_jurisdiction")
        )
        base_date = self.bdr.resolve(payload.get("application_date"))
        scale = self.scr.resolve(payload.get("drawing"))

        assumed_fields: list[str] = []
        if jurisdiction.assumed:
            assumed_fields.append("jurisdiction")
        if base_date.assumed:
            assumed_fields.append("base_date")
        if scale.assumed:
            assumed_fields.append("scale")

        return PreflightContext(
            pnu=payload["pnu"],
            snapshot_id=snapshot_id,
            input_hash=ih,
            jurisdiction=jurisdiction,
            base_date=base_date,
            scale=scale,
            blocked=jurisdiction.blocked,
            assumed_fields=assumed_fields,
        )


def run_preflight(payload: dict[str, Any], snapshot: Snapshot | str) -> PreflightContext:
    """편의 진입점. snapshot은 Snapshot 또는 snapshot_id 문자열 허용.

    Snapshot 객체가 오면 버전축 정합을 게이트 진입 전에 강제(INV-6). 불일치 시 진행 거부.
    """
    if isinstance(snapshot, Snapshot):
        snapshot.assert_synced()
        snapshot_id = snapshot.snapshot_id
    else:
        snapshot_id = str(snapshot)
    return PreflightGate().run(payload, snapshot_id)
