"""field_audit 표준 계약(Pydantic) — AuditFinding·AuditReport.

W0에서 '값'이 아니라 '규칙·관계·출처·방법론'을 박제하는 계약을 고정한다. 이 shape는
이후 전 척추(커버리지·생성·수집)와 다중 삽입점(analyze·재초환·비례율·부담금)이 공유하는
SSOT 계약이므로 additive 확장만 허용하고 기존 필드 의미는 불변으로 유지한다.

- severity: P0(차단 후보)·P1(오라클 자동교정 후보)·P2(관찰/배지). 계층 taxonomy와 정합.
- tier: A(하드 불변식)·B(수시변동 안전망)·C(LLM/도메인 어드버서리얼).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# 계약 enum — P0/P1/P2·A/B/C. 문자열 Literal로 강제(규칙이 오타 severity를 못 흘리게).
Severity = Literal["P0", "P1", "P2"]
Tier = Literal["A", "B", "C"]


class AuditFinding(BaseModel):
    """도메인 correctness 위반 1건.

    expected/observed는 '권위 오라클/규칙이 기대한 값' vs '분석이 산출한 값'. 값이 아니라
    '불일치'를 기술하며, 자유서술 PII·원본 claim은 담지 않는다(관측전용 emit 정합).
    """

    model_config = ConfigDict(extra="forbid")

    code: str  # 안정 식별자(예: "G1_PROTECTION_ZONE_RISK_FLOOR")
    severity: Severity
    panel: str  # 어느 분석 패널/섹션에서 발견(예: "risk", "poi", "market")
    field: str  # 대상 필드 경로(예: "risk_level", "school_count")
    expected: Any = None  # 규칙/오라클 기대값(없을 수 있음)
    observed: Any = None  # 분석 산출값(없을 수 있음)
    rule_id: str  # 이 finding을 낸 규칙 id(rules_registry 등록 id와 일치)
    tier: Tier
    note: Optional[str] = None  # 사람이 읽는 사유(선택)

    def to_dict(self) -> dict[str, Any]:
        """직렬화(JSON 안전) — model_dump 별칭. 배선/원장 적재는 이 dict를 소비."""
        return self.model_dump()


class AuditReport(BaseModel):
    """1회 감사 결과 — findings 집합 + 메타 + 커버리지 원장 seed.

    is_valid = P0 finding 부재(하드 차단 관점). P1/P2만 있으면 is_valid=True(비차단·배지).
    coverage = 커버리지 원장 seed. W0는 빈 dict라도 **필드 존재**를 보장한다(측정 100%의
    감사가능 지표를 이후 Phase가 채운다 — bare "100%" 금지 원칙의 자리).
    """

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = True
    findings: list[AuditFinding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """직렬화(JSON 안전) — model_dump 별칭. runner가 result에 부착할 때 이 dict를 사용."""
        return self.model_dump()

    @classmethod
    def from_findings(
        cls,
        findings: list[AuditFinding],
        *,
        metadata: dict[str, Any] | None = None,
        coverage: dict[str, Any] | None = None,
    ) -> AuditReport:
        """findings로 리포트 조립 — is_valid는 P0 부재로 결정(하드 차단 관점)."""
        has_p0 = any(f.severity == "P0" for f in findings)
        return cls(
            is_valid=not has_p0,
            findings=findings,
            metadata=metadata or {},
            coverage=coverage or {},
        )
