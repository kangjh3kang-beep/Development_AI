"""R0.5 — 도면→원장 라우팅(WB17 해소). 오분류/불합의 시트는 라우팅 제외(INV-8).

확정 시트의 수량만 원장에 적재. 필수 변수의 출처 시트가 결손이면 원장 resolve가 MISSING으로
표면화(무음 skip 금지). 필수 시트 부재 → 하류 '확인 불가'로 연결.
"""
from __future__ import annotations

from app.contracts.enums import Method, Unit
from app.services.ledger.evidence_ledger import EvidenceLedger
from app.services.sheet.sheet_role_resolver import SheetRoleResolver


def route_to_ledger(sheets: list[dict], tol_band: float | None = None) -> EvidenceLedger:
    resolver = SheetRoleResolver()
    led = EvidenceLedger(tol_band=tol_band)

    for sheet in sheets:
        assignment = resolver.resolve(sheet)
        if assignment.isolated:
            continue  # 오분류/불합의 시트는 라우팅하지 않음(잘못된 수치 주입 차단).
        for q in sheet.get("quantities", []):
            led.add(
                variable_id=q["variable_id"],
                value=q["value"],
                method=Method[q.get("method", "TABLE")],
                unit=Unit(q["unit"]) if q.get("unit") else Unit.NONE,
                source_sheet=assignment.sheet_id,
                confidence=q.get("confidence", 1.0),
            )

    return led
