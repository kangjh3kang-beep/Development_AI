"""Phase 0 — 도메인 예외 베이스(미충족/보류/거부/버전축/계약). 각 페이즈가 구체화·확장한다."""
from __future__ import annotations


class DomainError(Exception):
    """모든 도메인 예외의 베이스."""


class DataInsufficientError(DomainError):
    """필수 데이터 결손 — 무음 추정 금지, 확인 불가/보류로 귀결."""


class HeldError(DomainError):
    """불확실/저신뢰 — 단정 금지, 보류(HELD)."""


class RefusedError(DomainError):
    """정책상 거부."""


class PreflightRefused(RefusedError):
    """Preflight 게이트 거부(축척/관할/기준일 미확정 등 임계경로 차단)."""


class VersionAxisError(DomainError):
    """버전축 불일치(산정규칙 vs 법규셋 snapshot 등)."""


class RuleContractError(DomainError):
    """룰/계약 위반."""


class CalcTraceMissing(DomainError):
    """산정값에 calc_trace(근거조문/제외규정) 부재 — 추적 불가 산정값 출력 금지(INV-10)."""


class MethodTraceMissing(DomainError):
    """시뮬 지표에 method_trace(모델/가정/입력) 부재 — 근거 없는 지표 출력 금지(INV-19)."""


class SourceMissing(DomainError):
    """사례/인용에 출처(의결서 식별/링크) 부재 — 출처 없는 사례 사용 금지(INV-23)."""


class EvidenceMissing(DomainError):
    """보고서 항목에 근거(조문/trace/사례 출처) 부재 — 근거 없는 항목 출력 금지(INV-29)."""


class CitationRequired(DomainError):
    """정성 판단에 기준 항목 인용 부재 — 인용 없는 정성 판단 금지(INV-31)."""
