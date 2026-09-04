"""(G9) 파이프라인 단계 명칭 FE/BE 계약 고정 — 이중 표현 드리프트 CI 게이트.

apps/api/app/services/pipeline/project_pipeline.py의 PipelineStage(BE 8단계 컴퓨트 스텝)와
apps/web/lib/lifecycle-stages.ts의 LIFECYCLE_STAGES(FE 11단계 UI 네비)는 의도적으로 입도가
다르다(FE=사용자 네비게이션 단위, BE=파이프라인 실행 단위). 이 둘을 잇는 유일한 공식 번역은
apps/web/lib/lifecycle-stages.ts의 PIPELINE_STAGE_TO_LIFECYCLE 매핑 상수다.

이 테스트는 BE측 계약만 고정한다: PipelineStage가 정확히 8종이고 그 리터럴 값이 아래와
동일한지 검증한다. FE측 계약(매핑 키=이 8종 전수·값=FE 단계 id 또는 null)은
apps/web/lib/lifecycle-stages.test.ts의 "PIPELINE_STAGE_TO_LIFECYCLE — G9 계약" describe가
동일한 리터럴 값을 자체 핀(BE_PIPELINE_STAGES)해 대조한다 — 상수를 교차언어로 import할 수
없으므로(G4 계약과 동일 방식), 양쪽이 각자 리터럴로 핀하고 값을 사람이 대조·동기화한다.
BE가 스텝을 추가/변경하면 이 파일과 apps/web/lib/lifecycle-stages.ts(PIPELINE_STAGE_TO_LIFECYCLE·
PipelineStageBE) + lifecycle-stages.test.ts(BE_PIPELINE_STAGES)를 함께 갱신할 것.
"""

from app.services.pipeline.project_pipeline import PipelineStage


def test_pipeline_stage_has_exactly_8_steps():
    """PipelineStage는 정확히 8종(FE 11단계와 의도적으로 다른 입도 — G9 정합)."""
    values = [s.value for s in PipelineStage]
    assert len(values) == 8
    assert len(set(values)) == 8  # 중복 없음


def test_pipeline_stage_values_pinned():
    """PipelineStage 8종 리터럴 값 핀 — FE lifecycle-stages.ts의 PIPELINE_STAGE_TO_LIFECYCLE
    키 전수와 대조되는 정본(apps/web/lib/lifecycle-stages.test.ts의 BE_PIPELINE_STAGES와 동일해야 함)."""
    assert {s.value for s in PipelineStage} == {
        "site_analysis",
        "design",
        "design_review",
        "cost",
        "feasibility",
        "tax",
        "esg",
        "report",
    }
