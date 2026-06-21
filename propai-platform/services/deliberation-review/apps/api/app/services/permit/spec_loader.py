"""INC-PD1 — 기본 프로세스 스펙 로드 + applicability 필터 + 위상정렬.

기본 스펙은 건축허가(본허가) + 보편 의제심의(경관/교통/환경/재해). 법정 한도는 criteria_refs의 ssot_ref로
규제 SSOT 참조 — 스펙은 수치 미보유(INV-3). 결정론(동일 버전 동일 결과).
"""
from __future__ import annotations

from app.contracts.permit_process import (
    CriterionKind,
    CriterionRef,
    PermitProcessSpec,
    StageSpec,
)

_DEFAULT = PermitProcessSpec(
    spec_id="permit-default",
    version="v1",
    effective_date="2026-01-01",
    stages=[
        StageSpec(
            stage_id="building_review", name="건축심의", stage_type="의제심의",
            required_inputs=["use_zone"],
            criteria_refs=[
                CriterionRef(criterion_id="far", kind=CriterionKind.QUANTITATIVE,
                             ssot_ref="far_floor_area", basis_article="국토계획법 시행령",
                             legal_ref_ids=["국토계획법§78", "국토계획법시행령§85"]),   # 용적률 법률+시행령
                CriterionRef(criterion_id="bcr", kind=CriterionKind.QUANTITATIVE,
                             ssot_ref="building_area", basis_article="국토계획법 시행령",
                             legal_ref_ids=["국토계획법§77", "국토계획법시행령§84"]),   # 건폐율 법률+시행령(§77 배선)
                CriterionRef(criterion_id="layout", kind=CriterionKind.QUALITATIVE,
                             ssot_ref="배치적정성"),   # 실 qual_facts feature명과 정합(매칭 키)
            ],
            deliverables=["배치도", "면적표"], authority="건축위원회",
            submittals=["건축계획서"],
        ),
        StageSpec(
            stage_id="landscape_review", name="경관심의", stage_type="의제심의",
            predecessors=["building_review"], required_inputs=["use_zone"],
            criteria_refs=[CriterionRef(criterion_id="scenery", kind=CriterionKind.QUALITATIVE,
                                        ssot_ref="경관조화")],   # 실 qual_facts feature명과 정합
            deliverables=["경관계획서"], authority="경관위원회",
            applies_zones=[],  # 조건 없으면 항상; 운영 스펙에서 좁힘
        ),
        StageSpec(
            stage_id="building_permit", name="건축허가", stage_type="본허가",
            predecessors=["building_review"], required_inputs=["use_zone"],
            outcome_predictor="heuristic_v1",   # Phase 2a 승인 가능성 예측(본허가 단계)
            criteria_refs=[CriterionRef(criterion_id="height", kind=CriterionKind.QUANTITATIVE,
                                        ssot_ref="building_height", basis_article="건축법",
                                        legal_ref_ids=["건축법§60", "건축법§61"])],   # 높이제한·일조
            deliverables=["허가도서"], authority="허가권자(시군구)",
            submittals=["건축허가신청서"],
        ),
    ],
)


def load_default_spec() -> PermitProcessSpec:
    """기본 프로세스 스펙(버전드). 향후 JSON 시드/DB 스냅샷으로 대체 가능(인터페이스 동일)."""
    return _DEFAULT.model_copy(deep=True)


def _applies(stage: StageSpec, dev_type: str | None, use_zone: str | None) -> bool:
    if stage.applies_dev_types and dev_type not in stage.applies_dev_types:
        return False
    if stage.applies_zones and use_zone not in stage.applies_zones:
        return False
    return True


def applicable_stages(spec: PermitProcessSpec, *, dev_type: str | None = None,
                      use_zone: str | None = None) -> list[StageSpec]:
    """applicability 필터 + predecessors 위상정렬(결정론 순서). 순환은 입력 순서 폴백."""
    chosen = [s for s in spec.stages if _applies(s, dev_type, use_zone)]
    ids = {s.stage_id for s in chosen}
    ordered: list[StageSpec] = []
    placed: set[str] = set()
    remaining = list(chosen)
    # 결정론 위상정렬: 선행(스코프 내)이 모두 배치된 단계부터, 원래 순서 보존
    progress = True
    while remaining and progress:
        progress = False
        for s in list(remaining):
            if all((p not in ids) or (p in placed) for p in s.predecessors):
                ordered.append(s)
                placed.add(s.stage_id)
                remaining.remove(s)
                progress = True
    ordered.extend(remaining)  # 순환 잔여(있으면) 입력 순서로
    return ordered
