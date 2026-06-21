"""INC-DL2 — 건축설계 라이프사이클 프로세스 스펙(시스템2). 시스템1 ProcessSpec/실행기 재사용.

6단계: 기획→법규 사전검토→매스→배치→평면→결과물 검증. 법정 한도는 reg SSOT 참조(INV-3 — 스펙 수치 미보유).
완결성은 required_inputs(provided_inputs로 충족 판정 — 산출물 존재). 생성(매스/세대수)은 Phase2 비범위 — 본 스펙은
프로세스 순서·완결성·법규여유·검증만. 결정론(동일 버전 동일 결과).
"""
from __future__ import annotations

from app.contracts.permit_process import (
    CriterionKind,
    CriterionRef,
    ProcessSpec,
    StageSpec,
)

_DESIGN = ProcessSpec(
    spec_id="design-default",
    version="v1",
    effective_date="2026-01-01",
    stages=[
        StageSpec(
            stage_id="programming", name="기획", stage_type="설계",
            required_inputs=["use_zone", "program"],   # 대지 전제 + 소요 프로그램(용도·규모)
            deliverables=["설계개요", "소요면적표"],
        ),
        StageSpec(
            stage_id="legal_precheck", name="법규 사전검토", stage_type="설계",
            predecessors=["programming"], required_inputs=["use_zone"],
            criteria_refs=[
                CriterionRef(criterion_id="far", kind=CriterionKind.QUANTITATIVE,
                             ssot_ref="far_floor_area", basis_article="국토계획법 시행령",
                             legal_ref_ids=["국토계획법§78", "국토계획법시행령§85"]),   # 용적률 법률+시행령
                CriterionRef(criterion_id="bcr", kind=CriterionKind.QUANTITATIVE,
                             ssot_ref="building_area", basis_article="국토계획법 시행령",
                             legal_ref_ids=["국토계획법§77", "국토계획법시행령§84"]),   # 건폐율 법률+시행령(§77 배선)
            ],
            deliverables=["법규검토서"],
        ),
        StageSpec(
            stage_id="massing", name="매스 스터디", stage_type="설계",
            predecessors=["legal_precheck"], required_inputs=["massing"],
            deliverables=["매스안"],
        ),
        StageSpec(
            stage_id="site_layout", name="배치", stage_type="설계",
            predecessors=["massing"], required_inputs=["site_layout"],
            criteria_refs=[CriterionRef(criterion_id="layout", kind=CriterionKind.QUALITATIVE,
                                        ssot_ref="배치적정성")],
            deliverables=["배치도"],
        ),
        StageSpec(
            stage_id="floor_plan", name="평면/면적", stage_type="설계",
            predecessors=["site_layout"], required_inputs=["floor_plan"],
            deliverables=["평면도", "면적표"],
        ),
        StageSpec(
            stage_id="deliverable_verify", name="결과물 검증", stage_type="설계",
            predecessors=["floor_plan"], required_inputs=["use_zone"],
            deliverables=["설계 검증 리포트"],
        ),
    ],
)


def load_design_spec() -> ProcessSpec:
    """건축설계 라이프사이클 기본 스펙(버전드). 단계 조정/추가 = 스펙만 변경."""
    return _DESIGN.model_copy(deep=True)
