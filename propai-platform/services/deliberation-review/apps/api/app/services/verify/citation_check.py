"""L5 — 인용 검증(미러 대조: 실재 + 시행일 유효 + 내용 일치). 분석경로 라이브 금지(INV-25/13).

통과(passed=True)만 활성. 미통과 인용은 FinalGate가 BLOCKED 처리. R2 미러를 재대조.
"""
from __future__ import annotations

from datetime import date, datetime

from app.contracts.mirror import MirrorSnapshot
from app.contracts.verification import VerificationResult


def _to_date(value: object) -> date | None:
    if isinstance(value, datetime):  # datetime은 date 하위 — date 변환 먼저(시행일 비교 정확)
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])  # ISO date/datetime('…T…') 앞 10자 파싱
        except ValueError:
            return None
    return None


class CitationCheck:
    def verify(
        self,
        citation: dict,
        snapshot: MirrorSnapshot | None = None,
        base_date: date | None = None,
    ) -> VerificationResult:
        rules = snapshot.rules if snapshot else []
        ref = citation.get("ref")
        match = next((r for r in rules if r.get("ref") == ref), None)

        exists = match is not None
        effective = False
        content_ok = False

        if exists:
            rule_eff = _to_date(match.get("effective_date"))
            cit_eff = _to_date(citation.get("effective_date"))
            if rule_eff is None:
                effective = True  # 미러에 시행일 미기재 — 실재만 확인
            else:
                in_force = base_date is None or rule_eff <= base_date
                date_matches = cit_eff is None or cit_eff == rule_eff
                effective = in_force and date_matches
            cit_content = citation.get("content")
            content_ok = cit_content is None or cit_content == match.get("content")

        passed = exists and effective and content_ok
        reason = None if passed else "; ".join(
            r for r in (
                None if exists else "not_found",
                None if effective else "effective_date_mismatch",
                None if content_ok else "content_mismatch",
            ) if r
        )
        return VerificationResult(
            citation_ref=ref, passed=passed,
            checks={"exists": exists, "effective": effective, "content": content_ok},
            reason=reason,
        )
