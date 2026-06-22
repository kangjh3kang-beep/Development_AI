"""다중출처 교차검증 계약 — 같은 사실을 N개 1차출처에서 조회해 합의 판정.

신뢰도·정확도 향상: 출처가 일치할수록 확신↑, 불일치는 무음 없이 표면화(무음 오판 0).
INV-8(3원 합의) 패턴을 데이터 소스로 일반화. 출처별 값·근거 보존(1차출처/감사).
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

from app.contracts._types import Probability


class SourceValue(BaseModel):
    """단일 출처에서 가져온 사실 1건(값 + 1차출처 근거 + 신선도)."""

    source: str                       # 출처 이름(law_go_kr / mirror_store / vworld …)
    value: str | float | int | None   # 조회값(None=결손)
    ref: str | None = None            # 1차출처 링크/식별자(감사·역추적)
    # INC-12 신선도 — as_of(스냅샷 기준일) 대비 노후 시 STALE(무음 사용 금지, NEEDS_REVIEW 보수화).
    collected_at: date | None = None  # 수집 시각(예: INC-11 캐시 fetched_at 승계)
    data_vintage: date | None = None  # 데이터 기준일(예: 공시지가 stdr_year → date)
    max_age_days: int | None = None   # 허용 연한(초과 시 STALE). None=신선도 미평가.

    def is_stale(self, as_of: date | None) -> bool:
        """as_of 기준 데이터가 max_age_days 초과로 노후인가(메타 비교, 결정론). 미평가 시 False."""
        if as_of is None or self.max_age_days is None:
            return False
        ref = self.data_vintage or self.collected_at
        if ref is None:
            return False
        return (as_of - ref).days > self.max_age_days


class CrossStatus(str, Enum):
    UNANIMOUS = "UNANIMOUS"  # 전 출처 일치 → 최고 확신
    MAJORITY = "MAJORITY"    # 과반 일치 + 소수 이견(표면화)
    CONFLICT = "CONFLICT"    # 합의 실패(동수/분산) → NEEDS_REVIEW
    SINGLE = "SINGLE"        # 단일 출처 → 교차검증 불가(보수)
    ABSENT = "ABSENT"        # 출처 없음


class CrossValidation(BaseModel):
    """교차검증 결과 — 합의값 + 신뢰도 + 출처별 값(표면화) + 이견."""

    fact_key: str
    status: CrossStatus
    agreed_value: str | float | int | None = None
    confidence: Probability = 0.0
    sources_present: int = 0
    by_source: dict[str, str | float | int | None] = Field(default_factory=dict)
    sources: list[SourceValue] = Field(default_factory=list)  # 출처별 값+1차출처 ref(역추적 보존)
    dissent: list[str] = Field(default_factory=list)  # 합의와 다른 값을 낸 출처들
    stale_sources: list[str] = Field(default_factory=list)  # INC-12 노후 출처(as_of 대비 max_age 초과)

    @property
    def needs_review(self) -> bool:
        """판정 게이트 연결용 — 단일/불일치/결손, 그리고 노후 출처는 보수적으로 재검토 대상(무음0)."""
        return (self.status in (CrossStatus.CONFLICT, CrossStatus.SINGLE, CrossStatus.ABSENT)
                or bool(self.stale_sources))
