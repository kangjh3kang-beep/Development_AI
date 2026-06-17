"""R0 — 기준일 확정(BaseDateResolver). 허가신청(예정)일 → effective_date.

미입력 시 무음 추정 금지 → assumed=True로 표면화하고 effective_date는 미확정(None)으로 전파.
"""
from __future__ import annotations

from datetime import date

from app.contracts.preflight import BaseDateResult


class BaseDateResolver:
    def resolve(self, application_date: date | None = None) -> BaseDateResult:
        if application_date is None:
            return BaseDateResult(effective_date=None, assumed=True)
        return BaseDateResult(effective_date=application_date, assumed=False)
