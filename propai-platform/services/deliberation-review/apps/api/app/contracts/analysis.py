"""심의분석 파이프라인 입출력 계약. 11계층 오케스트레이션의 단일 진입/산출 스키마.

AnalysisInput: 원시 입력(Preflight~정성 각 계층이 소비). 미제공 계층은 graceful skip(무음 아님, skipped 표면화).
AnalysisResult: 전 계층 산출 번들 + 최종 구획 리포트. 동일 입력+스냅샷 동일 결과(input_hash).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.contracts.bim import BimElement
from app.contracts.cross_validation import CrossValidation
from app.contracts.finding import Finding
from app.contracts.land_card import LandCard
from app.contracts.legal_quantity import LegalQuantity
from app.contracts.precedent import PrecedentStat
from app.contracts.preflight import PreflightContext
from app.contracts.qualitative import QualAssessment
from app.contracts.reg_graph import RegGraph
from app.contracts.report import ReviewReport
from app.contracts.sim_metric import SimMetric


class AnalysisInput(BaseModel):
    # Preflight / version axis
    pnu: str
    application_date: date | None = None
    axis_date: date | None = None
    snapshot_id: str = "snap-1"
    drawing: dict = Field(default_factory=dict)
    model_version: str = "engine-v1"

    # P-A 멀티모달 도면 자동해석 입력: 도면 시트(이미지/표제란/힌트) → 자동 요소추출.
    drawings: list[dict] = Field(default_factory=list)  # [{sheet_id, image_ref?, sheet_role?, element_hints?}]
    # P1 이중경로 추출 입력: ifc(BIM STEP 텍스트) 우선, 없으면 elements(2D/VLLM/도면자동추출).
    ifc: str | None = None
    elements: list[dict] = Field(default_factory=list)

    # R1.5 법정 산정
    calc_targets: list[dict] = Field(default_factory=list)  # [{target, payload, elements:[CalcElement]}]
    # R3 판정
    rules: list[dict] = Field(default_factory=list)         # [{rule, measured, limit, relaxation_states, ...}]
    # L3-B 공학 시뮬
    sim_inputs: dict = Field(default_factory=dict)          # {sunlight, egress, parking, view}
    # L4 유사사례
    issue: str | None = None
    corpus: list[dict] = Field(default_factory=list)
    # L5 검증(미러/인용)
    mirror_rules: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    # 다중출처 교차검증: [{fact_key, sources:[{source, value, ref}]}]. law.go.kr 키 있으면 자동 합류.
    cross_facts: list[dict] = Field(default_factory=list)
    # 대지 규제 카드 자동수집(VWORLD NED 토지특성+토지이용계획). pnu 기반.
    collect_land_card: bool = False
    land_year: str | None = None
    # 지오코딩: 도면 대지위치(지번/도로명 주소) → PNU 자동 도출(진입점). pnu 미상 시 활용.
    address: str | None = None
    # 주변 건물 스카이라인 수집(VWORLD lt_c_bldginfo) — 일조/경관 시뮬 입력. address(좌표) 필요.
    collect_surrounding: bool = False
    surrounding_radius_m: int = 150
    # 신축안 층수 — 주변 스카이라인 대비 돌출도(경관심의 참고). collect_surrounding 함께 사용.
    proposed_floors: int | None = None
    # L3-C 정성
    qual_facts: list[dict] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    run_id: str | None = None  # 영속화 시 부여(조회 키)
    snapshot_id: str
    input_hash: str
    drawing_source: str | None = None      # P-A: VLLM_VISION | HINTS | none (도면 자동해석 경로)
    drawing_elements_n: int = 0            # 도면에서 자동추출된 요소 수
    calc_targets_source: str | None = None  # P-A.2: INPUT | DRAWING_AUTO | None (산정 입력 출처)
    extraction_source: str | None = None  # P1: BIM | VLLM | none
    bim_elements: list[BimElement] = Field(default_factory=list)
    preflight: PreflightContext | None = None
    legal_quantities: list[LegalQuantity] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    sim_metrics: list[SimMetric] = Field(default_factory=list)
    precedent: PrecedentStat | None = None
    precedent_source: str | None = None    # P-C: VECTOR_SEARCH | None (유사사례 검색 경로)
    mirror_source: str | None = None       # P-E: INPUT | SUPPLY_STORE | None (규제 미러 출처)
    cross_validations: list[CrossValidation] = Field(default_factory=list)  # 다중출처 합의 결과
    land_card: LandCard | None = None      # 대지 규제 카드(VWORLD NED 자동수집)
    geocoded: dict | None = None           # 지오코딩 결과(주소→pnu/좌표)
    surrounding_context: dict | None = None  # 주변 건물 스카이라인(일조/경관 시뮬 입력)
    qualitative: list[QualAssessment] = Field(default_factory=list)
    reg_graph: RegGraph | None = None  # P3 규제 지식그래프(조문↔룰↔변수↔완화)
    report: ReviewReport
    skipped: list[str] = Field(default_factory=list)  # 미제공/거부 계층(무음 금지)
