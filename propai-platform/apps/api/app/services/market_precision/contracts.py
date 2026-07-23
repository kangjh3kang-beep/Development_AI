"""시장·분양 정밀화 5계약 — 데이터클래스 정의 (v4.0 Wave3 W3-8).

UNKNOWN/OBSERVED/DERIVED 어휘는 새로 발명하지 않고 ``app.services.provenance.fact_status.
FactStatus``(Zero-Trust P1 SSOT)를 그대로 재사용한다(W3-6 RFI·W3-7 Rule 계약과 동일 관례 —
정합점: UNKNOWN/CONFLICT 보존 어휘 통일).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.provenance.fact_status import FactStatus


@dataclass(frozen=True)
class ComparableCase:
    """비교사례 1건 — 어떤 단지·거래·근접범위인지, 선정/제외 사유를 명시한다(무음 절단 금지).

    ★정직 한계: ``proximity_scope``는 실측 거리(m)가 아니라 법정동 텍스트 일치 여부에 기반한
    근접 등급이다(이 파이프라인은 좌표 지오코딩을 하지 않는다 — nearby_map_service의 반경검색과
    다른 경로). 실측 거리(m)를 날조하지 않기 위해 등급으로만 표기한다.
    """

    case_id: str
    source: str                  # 예: "MOLIT_실거래"
    building_name: str
    dong: str
    jibun: str
    deal_ym: str                 # YYYYMM
    deal_date: str | None
    price_10k_won: float
    area_m2: float
    per_pyeong_10k: float | None
    proximity_scope: str         # "동일법정동" | "동일시군구(타동)"
    included: bool
    selection_basis: str
    exclude_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source": self.source,
            "building_name": self.building_name,
            "dong": self.dong,
            "jibun": self.jibun,
            "deal_ym": self.deal_ym,
            "deal_date": self.deal_date,
            "price_10k_won": self.price_10k_won,
            "area_m2": self.area_m2,
            "per_pyeong_10k": self.per_pyeong_10k,
            "proximity_scope": self.proximity_scope,
            "included": self.included,
            "selection_basis": self.selection_basis,
            "exclude_reason": self.exclude_reason,
        }


@dataclass(frozen=True)
class ComparableSet:
    """비교사례 묶음 — 선정/제외 카운트를 항상 함께 노출한다(무음 절단 금지)."""

    cases: tuple[ComparableCase, ...]
    included_count: int
    excluded_count: int
    anchor_scope: str            # "동" | "시군구" | "unavailable"
    data_source: str             # "molit_live" | "unavailable"
    note: str

    @property
    def total_count(self) -> int:
        return self.included_count + self.excluded_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": [c.to_dict() for c in self.cases],
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "total_count": self.total_count,
            "anchor_scope": self.anchor_scope,
            "data_source": self.data_source,
            "note": self.note,
        }


@dataclass(frozen=True)
class TimeAdjustment:
    """거래 시점 → 현재 시점 보정 — 지수·출처·정직 마커(외삽 금지)."""

    status: FactStatus            # OBSERVED(R-ONE 실계수 적용 가능) | UNKNOWN(미보정)
    factor: float | None
    source: str                   # "R-ONE" | "미보정"
    basis: str
    assumption: str | None
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "factor": self.factor,
            "source": self.source,
            "basis": self.basis,
            "assumption": self.assumption,
            "limitation": self.limitation,
        }


@dataclass(frozen=True)
class AbsorptionEstimate:
    """흡수율(분양률) 추정 — 데이터 없으면 UNKNOWN 정직 표기(모델 날조 금지)."""

    status: FactStatus            # 현재 데이터 소스 부재로 항상 UNKNOWN
    absorption_rate_pct: float | None
    basis: str
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    def __post_init__(self) -> None:
        if self.status == FactStatus.UNKNOWN and self.absorption_rate_pct is not None:
            raise ValueError(
                "AbsorptionEstimate: status=UNKNOWN이면 absorption_rate_pct는 반드시 None이어야 "
                "합니다(UNKNOWN을 임의값으로 대체 금지 — Zero-Trust 불변식)."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "absorption_rate_pct": self.absorption_rate_pct,
            "basis": self.basis,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "note": self.note,
        }


@dataclass(frozen=True)
class PriceSuggestion:
    """분양가 제안 — 비교사례 기반 범위 + 지불여력 크로스체크(점추정 단독 금지).

    ``point_10k``가 있으면(=값을 냈으면) ``range_low_10k``/``range_high_10k``도 반드시 함께
    있어야 한다(스펙 P ⑤ "점추정 단독 금지" 불변식 — 값을 만들되 범위 없이 단독 표기하는
    경로를 계약 수준에서 차단한다).
    """

    point_10k: float | None
    range_low_10k: float | None
    range_high_10k: float | None
    unit_label: str
    data_source: str
    basis: str
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    affordability: dict[str, Any] | None = None
    comparable_set: ComparableSet | None = None
    time_adjustment: TimeAdjustment | None = None
    absorption_estimate: AbsorptionEstimate | None = None

    def __post_init__(self) -> None:
        if self.point_10k is not None and (self.range_low_10k is None or self.range_high_10k is None):
            raise ValueError(
                "PriceSuggestion: point_10k가 있으면 range_low_10k/range_high_10k도 함께 "
                "있어야 합니다(점추정 단독 금지)."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_10k": self.point_10k,
            "range_low_10k": self.range_low_10k,
            "range_high_10k": self.range_high_10k,
            "unit_label": self.unit_label,
            "data_source": self.data_source,
            "basis": self.basis,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "affordability": self.affordability,
            "comparable_set": self.comparable_set.to_dict() if self.comparable_set else None,
            "time_adjustment": self.time_adjustment.to_dict() if self.time_adjustment else None,
            "absorption_estimate": (
                self.absorption_estimate.to_dict() if self.absorption_estimate else None
            ),
        }


__all__ = [
    "AbsorptionEstimate",
    "ComparableCase",
    "ComparableSet",
    "PriceSuggestion",
    "TimeAdjustment",
]
