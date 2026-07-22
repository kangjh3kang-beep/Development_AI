"""CSM(Canonical Site Model) 조립체 + 부분 invalidation (v4.0 Wave2 W2-6 — SPEC §P5 실용 1차).

SPEC v4 원문 요지(§[Canonical Site Model]): 부지 분석 전주기(P0~P4 — 필지·법규·실효한도·
접도·시장)에서 산출된 사실들을 **단일 스냅샷(CSM)**으로 조립하고, 그 스냅샷의 해시(전체 +
섹션별)를 근거로 "무엇이 바뀌었을 때 무엇을 다시 계산해야 하는가"를 선언적으로 판단한다.

★스파이크 결론(그린필드 금지 — 근거, 반드시 읽을 것):
1) ``app.services.basis.site_basis_service``(SiteBasis)는 CSM과 이름은 유사하지만 범위가
   다르다 — P2(dev_act_permit)·P3(rights)·P4(access) **3개 P0 게이트만** 집계해
   ADVISORY/AUTHORIZED 승인 상태전이(승인자·SoD·원장 append)를 관리하는 **워크플로우 계약**
   이다. 법규(effective_far)·시장(land_prices 등) 섹션은 아예 다루지 않고, "스냅샷 조립"이
   아니라 "게이트 통과/승인" 자체가 목적이다 — CSM의 대체재가 아니라 인접 자산으로 남긴다
   (재구현 금지 대상이 아니라 "다른 관심사"로 문서화).
2) ``app.services.ledger.contradiction``(모순탐지)은 **prior(원장 과거 스냅샷) vs 현재
   분석**의 시간축 비교(status flip·수치 delta)다 — 이 모듈의 ``diff_csm``이 하는 "동일
   조립 시점 내 섹션별 해시 비교"와는 축이 다르다(시간축 vs 구조축). 알고리즘도 겹치지
   않아 재사용하지 않는다(용도가 다름).
3) ``app.services.design_risk.design_change_predictor``는 "설계 확정 후 착공 전 변경
   가능성"만 다루는 설계단계 전용 리스크라 이 모듈의 Risk Register(사업 전반 리스크)와
   범위가 겹치지 않는다(별도 자산 — risk_register.py 독스트링 참고).
4) **조립 지점**: ``ComprehensiveAnalysisService.analyze()``(comprehensive_analysis_service.py)
   가 실코드 확인상 부지분석 P0~P4 사실을 가장 넓게 이미 모으는 지점이다(zone_type·
   land_area_sqm·effective_far·special_parcel·dev_act_permit_gate·access_basis·
   allowed_buildings·land_prices·transaction_prices·sale_prices·location 등 전부 그 함수의
   ``result`` dict 하나에 실린다). 이 모듈은 그 결과 dict를 **참조로만** 담는 얇은 계약이지,
   어떤 값도 재계산하지 않는다(``assemble_csm``은 순수 재구조화 함수).

섹션 5종(SPEC 어휘 그대로, P0~P4와 1:1 대응):
  parcel(필지) · legal(법규) · effective_limits(실효한도) · access(접도) · market(시장)

section_hashes/csm_hash는 W2-3 ``handoff_bundle.compute_payload_checksum``(canonical JSON
sha256)을 그대로 재사용한다(신규 해시 알고리즘 0 — 스펙 요구사항 "알고리즘 재사용").

★부분 invalidation(무자동재실행 원칙 — 반드시 지킬 것): ``invalidation_advice``는 항상
"권장 표식만" 반환한다(``auto_reexecuted: False`` 고정). 이 모듈 자체가 재분석을 트리거하는
코드 경로는 어디에도 없다 — 기존 staleness 관례(``site_basis_state`` evidence_changed류)와
동일하게, 실제 재실행 여부는 소비처(사람 또는 상위 오케스트레이터)의 몫이다.

신규 의존성 0(표준 라이브러리만) — dataclasses·datetime·typing.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .fact_status import FactStatus
from .handoff_bundle import compute_payload_checksum
from .lineage_ref import LineageRef

# CSM 섹션 5종(SPEC 어휘 고정 순서) — P0~P4 부지분석 사실 계열과 1:1 대응.
CSM_SECTION_NAMES: tuple[str, ...] = ("parcel", "legal", "effective_limits", "access", "market")

# ── 섹션 → 하류 산출물 의존표(선언적 dict — SPEC 예시 그대로: legal→설계+수지,
#    market→수지만). 이 dict가 유일한 판단근거다(코드에 흩어진 ad hoc 조건 없음).
#    ★"design"·"feasibility"는 실제 파이프라인 단계명이 아니라 이 계약의 권장 카테고리
#    어휘다(project_pipeline.py의 실제 단계와는 별도 축 — 소비처가 자신의 단계명으로 매핑).
SECTION_DOWNSTREAM: dict[str, tuple[str, ...]] = {
    "parcel": ("design", "feasibility"),
    "legal": ("design", "feasibility"),
    "effective_limits": ("design", "feasibility"),
    "access": ("design",),
    "market": ("feasibility",),
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_empty_value(section: Mapping[str, Any]) -> bool:
    """섹션 전체가 사실상 비어있는지(모든 값이 None/빈 컨테이너) — fact_refs 판정용."""
    return not any(v not in (None, "", [], {}, ()) for v in section.values())


# ── 섹션 빌더(comprehensive_analysis_service.analyze() 의 result dict → 섹션 dict) ──
#    ★재계산 금지: 아래 함수들은 전부 이미 산출된 키를 그대로 참조만 한다(값 변환·산식 0).

def _section_parcel(analysis: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pnu": analysis.get("pnu"),
        "address": analysis.get("address"),
        "zone_type": analysis.get("zone_type"),
        "land_area_sqm": analysis.get("land_area_sqm"),
        "land_area_basis": analysis.get("land_area_basis"),
        "parcel_count": analysis.get("parcel_count"),
        "integrated_zoning": analysis.get("integrated_zoning"),
        "special_parcel": analysis.get("special_parcel"),
        "developability": analysis.get("developability"),
    }


def _section_legal(analysis: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "allowed_buildings": analysis.get("allowed_buildings"),
        "dev_act_permit_gate": analysis.get("dev_act_permit_gate"),
        "upzoning": analysis.get("upzoning"),
        "legal_refs": analysis.get("legal_refs"),
        "evidence": analysis.get("evidence"),
    }


def _section_effective_limits(analysis: Mapping[str, Any]) -> dict[str, Any]:
    sec1 = analysis.get("effective_far")
    return dict(sec1) if isinstance(sec1, Mapping) else {}


def _section_access(analysis: Mapping[str, Any]) -> dict[str, Any]:
    access_basis = analysis.get("access_basis")
    return dict(access_basis) if isinstance(access_basis, Mapping) else {}


def _section_market(analysis: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "land_prices": analysis.get("land_prices"),
        "transaction_prices": analysis.get("transaction_prices"),
        "sale_prices": analysis.get("sale_prices"),
        "location": analysis.get("location"),
        "development_plans": analysis.get("development_plans"),
    }


_SECTION_BUILDERS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "parcel": _section_parcel,
    "legal": _section_legal,
    "effective_limits": _section_effective_limits,
    "access": _section_access,
    "market": _section_market,
}

# 섹션 → 대표 근거 문구(fact_refs.basis) — 사람이 읽는 설명, 날조 아님(실제 참조원 명시).
_SECTION_BASIS: dict[str, str] = {
    "parcel": "comprehensive_analysis 필지·특이부지 판정 스냅샷 참조(재계산 없음)",
    "legal": "comprehensive_analysis 허용건축물·개발행위허가 게이트 스냅샷 참조(재계산 없음)",
    "effective_limits": "comprehensive_analysis effective_far(법정/조례/실효 용적률·건폐율) 스냅샷 참조(재계산 없음)",
    "access": "comprehensive_analysis access_basis(접도 판정) 스냅샷 참조(재계산 없음)",
    "market": "comprehensive_analysis 시장(실거래·분양가·입지) 스냅샷 참조(재계산 없음)",
}


@dataclass(frozen=True)
class CanonicalSiteModel:
    """단일 CSM 스냅샷 — 기존 종합분석 조립 결과를 5개 섹션으로 재구조화한 얇은 계약.

    Attributes:
        sections: CSM_SECTION_NAMES 5종을 키로 하는 섹션 dict(값은 참조 스냅샷 — 재계산 금지).
        section_hashes: 섹션별 canonical JSON sha256(``compute_payload_checksum`` 재사용).
        csm_hash: 전체 스냅샷 해시(section_hashes 자체의 canonical JSON sha256).
        assembled_at: 조립 시각(ISO8601 UTC).
        fact_refs: 섹션별 LineageRef.to_dict() — 1차는 섹션 단위 개략 계보만 제공한다(필드
            수준 정밀 추적은 W2-2 LineageRef의 점진 채택 범위 — 이 모듈은 "섹션에 값이
            존재하는가"만으로 DERIVED/UNKNOWN을 개략 판정한다, 아래 ``_lineage_for_section``).
    """

    sections: dict[str, dict[str, Any]]
    section_hashes: dict[str, str]
    csm_hash: str
    assembled_at: str
    fact_refs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": self.sections,
            "section_hashes": self.section_hashes,
            "csm_hash": self.csm_hash,
            "assembled_at": self.assembled_at,
            "fact_refs": self.fact_refs,
        }


def sections_of(csm: CanonicalSiteModel | Mapping[str, Any]) -> dict[str, Any]:
    """CanonicalSiteModel 인스턴스 또는 그 to_dict() 결과 모두에서 sections dict를 뽑는다.

    risk_register.py 등 소비처가 CSM 인스턴스/역직렬화 dict 어느 쪽을 받아도 동일하게
    동작하도록 하는 공용 접근자(중복 분기 방지).
    """
    if isinstance(csm, CanonicalSiteModel):
        return csm.sections
    if isinstance(csm, Mapping):
        sections = csm.get("sections")
        return dict(sections) if isinstance(sections, Mapping) else {}
    return {}


def _lineage_for_section(name: str, section: Mapping[str, Any]) -> dict[str, Any]:
    """섹션 1개의 개략 LineageRef(1차 — 섹션 단위, 필드 단위 아님).

    비어있지 않으면 source_kind="CALC"(comprehensive_analysis가 이미 계산 완료한 값의
    참조 — RULE/LIVE_API 등 세분류는 필드수준 추적이 붙는 후속 W2-2 점진 채택 범위)·
    fact_status=DERIVED로, 완전히 비어있으면 source_kind="UNKNOWN"(traced=False)·
    fact_status=UNKNOWN(근거 없음 — 무날조: 값이 없는데 CALC/DERIVED로 표기하지 않는다)으로
    표기한다.
    """
    if _is_empty_value(section):
        ref = LineageRef(source_kind="UNKNOWN", fact_status=FactStatus.UNKNOWN.value, basis=_SECTION_BASIS.get(name))
    else:
        ref = LineageRef(source_kind="CALC", fact_status=FactStatus.DERIVED.value, basis=_SECTION_BASIS.get(name))
    return ref.to_dict()


def assemble_csm(
    analysis: Mapping[str, Any] | None, *, assembled_at: str | None = None,
) -> CanonicalSiteModel:
    """기존 종합분석 결과(dict) → CSM 스냅샷(섹션 재구조화 + 해시). 값 재계산 없음(순수 함수).

    analysis가 None이거나 dict가 아니면 5개 섹션 전부 빈 dict로 조립한다(무날조 — 값을
    지어내지 않고 정직하게 빈 스냅샷을 반환).
    """
    data = analysis if isinstance(analysis, Mapping) else {}
    sections = {name: builder(data) for name, builder in _SECTION_BUILDERS.items()}
    section_hashes = {name: compute_payload_checksum(sec) for name, sec in sections.items()}
    csm_hash = compute_payload_checksum(section_hashes)
    fact_refs = {name: _lineage_for_section(name, sec) for name, sec in sections.items()}
    return CanonicalSiteModel(
        sections=sections,
        section_hashes=section_hashes,
        csm_hash=csm_hash,
        assembled_at=assembled_at or _utc_now_iso(),
        fact_refs=fact_refs,
    )


def csm_from_dict(data: Mapping[str, Any] | None) -> CanonicalSiteModel | None:
    """직렬화된 dict(``to_dict()`` 결과, 예: 캐시/원장에서 재로드) → CanonicalSiteModel.

    형식이 안 맞으면 None(``bundle_from_dict``/``lineage_from_dict``와 동형 — 날조 금지).
    """
    if not isinstance(data, Mapping):
        return None
    try:
        section_hashes = dict(data.get("section_hashes") or {})
        csm_hash = str(data.get("csm_hash") or "")
        if not csm_hash or not section_hashes:
            return None
        return CanonicalSiteModel(
            sections=dict(data.get("sections") or {}),
            section_hashes=section_hashes,
            csm_hash=csm_hash,
            assembled_at=str(data.get("assembled_at") or ""),
            fact_refs=dict(data.get("fact_refs") or {}),
        )
    except (TypeError, ValueError):
        return None


def diff_csm(
    old: CanonicalSiteModel | None, new: CanonicalSiteModel,
) -> list[str]:
    """old→new 사이에 내용이 바뀐 섹션명 목록(section_hashes 비교, 순수 함수).

    old=None(최초 조립·비교대상 없음)이면 전 섹션을 "변경"으로 취급한다(첫 조립은 전부
    신규 사실이므로 하류 전체에 신규 조립을 알리는 것이 안전한 기본값 — 과소 통보보다
    과다 통보가 안전 방향).
    """
    if old is None:
        return list(new.section_hashes.keys())
    return [
        name for name in CSM_SECTION_NAMES
        if old.section_hashes.get(name) != new.section_hashes.get(name)
    ]


def invalidation_advice(changed_sections: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """변경된 섹션 목록 → 재분석 권장 목록(SECTION_DOWNSTREAM 선언적 매핑 기반).

    ★자동 재실행 금지(반드시 지킬 것): 이 함수는 절대 어떤 재분석도 트리거하지 않는다 —
    ``auto_reexecuted`` 는 항상 False로 고정된 "권장 표식"일 뿐이다(기존 staleness 재분석
    권장 관례와 정합 — site_basis_state의 evidence_changed 강등과 동일하게, 실행은 항상
    별도 명시 액션이 담당한다).
    """
    changed = list(changed_sections)
    recommended: set[str] = set()
    reasons: dict[str, list[str]] = {}
    for name in changed:
        for downstream in SECTION_DOWNSTREAM.get(name, ()):
            recommended.add(downstream)
            reasons.setdefault(downstream, []).append(name)
    return {
        "changed_sections": changed,
        "recommended_reanalysis": sorted(recommended),
        "reasons": {k: sorted(v) for k, v in reasons.items()},
        "auto_reexecuted": False,
        "note": "권장 표식만 — 자동 재실행되지 않습니다(기존 staleness 재분석 권장 관례와 정합).",
    }


__all__ = [
    "CSM_SECTION_NAMES",
    "SECTION_DOWNSTREAM",
    "CanonicalSiteModel",
    "assemble_csm",
    "csm_from_dict",
    "diff_csm",
    "invalidation_advice",
    "sections_of",
]
