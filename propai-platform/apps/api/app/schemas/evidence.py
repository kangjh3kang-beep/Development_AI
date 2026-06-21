"""근거·법령링크 공용 응답 mixin(전역정책 Phase0) — 신규 라우터가 상속만 하면 됨.

v2_feasibility.FeasibilityResultTrustResponse(evidence[]/legal_refs[])의 패턴을
일반화한다. 신규 응답 스키마가 BaseEvidenceResponse를 상속하면 evidence·legal_refs·
provenance·trust 4필드가 모두 additive(기본 빈배열/None)로 따라온다.

설계 원칙:
- 모든 필드 optional·기본값 빈배열/None → 구버전 클라이언트·미부착 응답과 하위호환.
- 값 구조는 evidence_contract.build_evidence_block 출력과 1:1(단일 계약).
- URL 등 법령 링크는 백엔드 레지스트리(get_legal_refs)가 생성한 값만 담긴다.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class BaseEvidenceResponse(BaseModel):
    """근거·법령링크 공용 응답 mixin(additive — 상속 시 4필드 자동 부착).

    evidence[]   : 산출 근거 트레이스 [{label, value, basis?, legal_ref_key?}].
    legal_refs[] : 법령 근거(레지스트리 get_legal_refs 출력 — law.go.kr 딥링크/텍스트).
    provenance[] : 원천 데이터 출처·신선도(public_data_registry + FreshnessChecker).
    trust        : 교차검증 신뢰도(data_validation.trust.to_dict(); 없으면 None).
    """

    evidence: list[dict[str, Any]] = []
    legal_refs: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    trust: Optional[dict[str, Any]] = None
