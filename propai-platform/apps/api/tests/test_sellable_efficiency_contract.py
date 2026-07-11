"""(G4) 전용률 상수 FE/BE 계약 고정 — 이중 하드코딩 드리프트 CI 게이트.

apps/api/app/services/pipeline/project_pipeline.py의 _SELLABLE_EFFICIENCY_BY_TYPE와
apps/web/lib/orchestration/node-body-builders.ts의 SELLABLE_EFFICIENCY_BY_TYPE는
같은 "건물유형별 전용률(연면적 대비 분양/전용면적 비율)" 표를 프론트·백엔드 양쪽에
각자 하드코딩한 것이다(정본 미수렴 — P1에서 unit_standards 공용 노출로 정리 예정).

P0 실용안: 상수를 한쪽으로 이전하지 않고, 두 계약 테스트가 각자의 실값을 명시 핀해
드리프트가 생기면 CI에서 즉시 잡히게 한다. 한쪽 값을 바꾸면 반드시 이 테스트와
apps/web/lib/orchestration/node-body-builders.test.ts의 "G4 계약" describe를 함께 갱신할 것.

라이브 대조 결과(2026-07-11, 구현 시점 실값 대조): 아래 5항목·기본값 전부 프론트와
일치(불일치 0건) — project_pipeline.py:92-98 vs node-body-builders.ts:79-87.
"""
from app.services.pipeline.project_pipeline import (
    _DEFAULT_SELLABLE_EFFICIENCY,
    _SELLABLE_EFFICIENCY_BY_TYPE,
)


def test_sellable_efficiency_by_type_pinned_values():
    """건물유형별 전용률 5항목이 프론트 SELLABLE_EFFICIENCY_BY_TYPE와 동일 값으로 핀됨."""
    assert _SELLABLE_EFFICIENCY_BY_TYPE == {
        "아파트": 0.75,
        "다세대주택": 0.78,
        "오피스텔": 0.70,
        "공동주택": 0.76,
        "근린생활시설": 0.70,
    }


def test_sellable_efficiency_default_pinned():
    """유형 미상 기본 전용률(실사용 명명 상수)이 프론트 DEFAULT_SELLABLE_EFFICIENCY와 동일하게 핀됨.

    ★.get(x, 0.75) == 0.75 식의 동어반복 검증 금지 — 테스트가 스스로 기본값을 넘기면
    실호출부의 기본값 드리프트를 못 잡는다. 실사용 상수를 리터럴로 직접 핀한다(QA 지적 반영).
    """
    assert _DEFAULT_SELLABLE_EFFICIENCY == 0.75
