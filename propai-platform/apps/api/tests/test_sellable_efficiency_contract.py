"""(G4) 전용률 상수 FE/BE 계약 고정 — 이중 하드코딩 드리프트 CI 게이트.

app/services/feasibility/unit_standards.py의 SELLABLE_EFFICIENCY_BY_BUILDING_TYPE와
apps/web/lib/orchestration/node-body-builders.ts의 SELLABLE_EFFICIENCY_BY_TYPE는
같은 "건물유형별 전용률(연면적 대비 분양/전용면적 비율)" 표를 프론트·백엔드 양쪽에
각자 하드코딩한 것이다.

P2 갱신(2026-07-11): 파이썬 내 이중정의(project_pipeline._SELLABLE_EFFICIENCY_BY_TYPE)는
unit_standards로 수렴되었다(값 불변, 정본만 일원화). 다만 파이썬↔TypeScript 교차언어
import는 불가하므로, 프론트 상수와의 동기는 여전히 두 계약 테스트가 각자의 실값을 명시
핀해 드리프트가 생기면 CI에서 즉시 잡히는 방식을 유지한다. 한쪽 값을 바꾸면 반드시 이
테스트와 apps/web/lib/orchestration/node-body-builders.test.ts의 "G4 계약" describe를
함께 갱신할 것.

라이브 대조 결과(2026-07-11, 구현 시점 실값 대조): 아래 5항목·기본값 전부 프론트와
일치(불일치 0건) — unit_standards.py vs node-body-builders.ts:79-87.
"""
import inspect

from app.services.feasibility.unit_standards import (
    DEFAULT_SELLABLE_EFFICIENCY,
    SELLABLE_EFFICIENCY_BY_BUILDING_TYPE,
    get_sellable_efficiency,
)
from app.services.pipeline import project_pipeline


def test_sellable_efficiency_by_type_pinned_values():
    """건물유형별 전용률 5항목이 프론트 SELLABLE_EFFICIENCY_BY_TYPE와 동일 값으로 핀됨."""
    assert SELLABLE_EFFICIENCY_BY_BUILDING_TYPE == {
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
    assert DEFAULT_SELLABLE_EFFICIENCY == 0.75


def test_get_sellable_efficiency_delegates_to_table():
    # 함수도 표와 동일 값을 반환 — 표만 바꾸고 함수 갱신을 잊는 드리프트 방지.
    for building_type, expected in SELLABLE_EFFICIENCY_BY_BUILDING_TYPE.items():
        assert get_sellable_efficiency(building_type) == expected
    assert get_sellable_efficiency("미등록유형") == DEFAULT_SELLABLE_EFFICIENCY


def test_project_pipeline_imports_unit_standards_sellable_efficiency():
    """project_pipeline이 자체 이중정의 대신 unit_standards 정본 함수를 쓰는지 배선 확인.

    (P2 파이썬 내 이중정의 해소) project_pipeline 소스가 unit_standards의
    get_sellable_efficiency를 import해서 사용하고, 구 자체 이중정의 상수
    (_SELLABLE_EFFICIENCY_BY_TYPE)가 되살아나지 않았는지 확인한다.
    """
    source = inspect.getsource(project_pipeline)
    assert "from app.services.feasibility.unit_standards import get_sellable_efficiency" in source
    # 구 이중정의 딕셔너리 재정의/직접 참조(.get 호출)가 되살아나지 않았는지 확인.
    # (설명용 주석에서 이름을 언급하는 것 자체는 허용 — 실제 딕셔너리 리터럴/호출만 금지)
    assert "_SELLABLE_EFFICIENCY_BY_TYPE: dict" not in source
    assert "_SELLABLE_EFFICIENCY_BY_TYPE.get(" not in source
