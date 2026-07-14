"""접도·도로 기반(access_basis) 응답 스키마 — 명세 P4 'Statutory Road·Access'.

WP-A: special_parcel 내 실존 판정 룰군(㉗ _rule_by_road §44·_rule_by_road_law 도로법·
_rule_by_fire_performance 소방 + 신설 세분 룰 막다른/자루형/소방접근)을 재사용·합성해,
도로 접근을 legal / physical / emergency 3상태로 분리한 전용 표면으로 승격한다.

설계 원칙:
- 각 상태(AccessStateResult)·최종(AccessAssessment)은 근거계약(BaseEvidenceResponse)을 상속해
  evidence·legal_refs·provenance·trust를 additive로 부착한다(URL은 레지스트리 출력만).
- 판정 불가(도로접면·도로폭·통로폭 미상 등)는 정직 상태 REQUIRES_AUTHORITY_CONFIRMATION로,
  확정 PASS를 만들지 않는다("법정도로 근거 없는 PASS 0"). 날조·낙관 폴백 금지.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.evidence import BaseEvidenceResponse

# 접근 상태(명세 P4) — 법정 접도(legal)·현황 물리적 접근(physical)·소방/응급 접근(emergency).
AccessState = Literal["legal", "physical", "emergency"]

# 상태별 판정 결과 — 정직 상태값(REQUIRES_AUTHORITY_CONFIRMATION = 확정 불가, 관할 확인 전제).
AccessStatus = Literal["PASS", "CONDITIONAL", "BLOCKED", "REQUIRES_AUTHORITY_CONFIRMATION"]

# 종합 게이트(special_parcel.gate_decision 반환) — 시나리오 산출 정책.
AccessGate = Literal["PASS", "TENTATIVE", "BLOCK"]


class AccessFinding(BaseModel):
    """단일 판정 근거(㉗ 룰군 또는 세분 룰이 반환한 factor 1건)."""

    category: str = Field(..., description="판정 요인명(예: 막다른 도로(길이별 최소 너비))")
    developability: str = Field(..., description="개발가능성 등급(special_parcel _RANK 값)")
    status: AccessStatus = Field(..., description="정직 상태값")
    implications: list[str] = Field(default_factory=list, description="정직 고지 문장")
    permit_prerequisites: list[str] = Field(default_factory=list, description="선행/확인 절차")
    legal_basis: list[str] = Field(default_factory=list, description="근거 법령(텍스트)")
    legal_ref_keys: list[str] = Field(default_factory=list, description="verified 법령링크 키")


class AccessStateResult(BaseEvidenceResponse):
    """3상태 중 한 상태(legal/physical/emergency)의 종합 판정 + 근거계약."""

    state: AccessState
    state_label: str = Field(..., description="상태 한글 라벨")
    status: AccessStatus
    developability: str = Field(..., description="상태 종합 개발가능성 등급")
    resolvable: str = Field(..., description="해결가능성 YES/CONDITIONAL/NO")
    summary: str = Field(..., description="상태 정직 요약")
    findings: list[AccessFinding] = Field(default_factory=list)


class AccessAssessmentRequest(BaseModel):
    """접도·도로 판정 요청 — 부지분석 result와 동형 필드(모두 optional·미상 허용).

    ★extra='allow': 부지분석 result를 그대로 넘겨도 되도록 추가 필드를 허용한다(통과 소비).
    """

    model_config = ConfigDict(extra="allow")

    address: str | None = Field(None, description="주소(메타·에코)")
    pnu: str | None = Field(None, description="PNU(메타·에코)")
    sigungu: str | None = Field(None, description="시군구(조례 링크 치환용)")
    planned_gfa_sqm: float | None = Field(None, description="계획 연면적(접도요건 tier)")
    # ── 법정 접도(legal) ──
    road_side: str | None = Field(None, description="도로접면(광대/중로/소로/세로(가)/세로(불)/맹지)")
    road_contact: bool | None = Field(None, description="도로 접함 여부(False=맹지)")
    road_width_m: float | None = Field(None, description="접한 도로 폭(m)")
    road_type: str | None = Field(None, description="도로 종류(국도/지방도/막다른/현황도로 등)")
    abutting_road_name: str | None = Field(None, description="접한 도로명")
    road_abutting_zone: bool | None = Field(None, description="도로법 접도구역 여부")
    special_districts: list[str] | None = Field(None, description="구역·지구(접도구역 등)")
    dead_end_road: bool | None = Field(None, description="막다른 도로 여부")
    dead_end_length_m: float | None = Field(None, description="막다른 도로 길이(m)")
    is_urban_area: bool | None = Field(None, description="도시지역 여부(막다른 도로 읍·면 예외)")
    # ── 현황 물리적 접근(physical) ──
    is_current_road: bool | None = Field(None, description="현황도로(사실상 도로) 여부")
    flag_lot: bool | None = Field(None, description="자루형(旗竿) 대지 여부")
    lot_shape: str | None = Field(None, description="대지 형상(자루형 등)")
    access_corridor_width_m: float | None = Field(None, description="자루형 통로부(자루목) 너비(m)")
    # ── 소방·응급·공사차량(emergency) ──
    fire_truck_access_width_m: float | None = Field(None, description="소방차 접근로 폭(m)")
    emergency_access_required: bool | None = Field(None, description="소방활동 공간 검토 필요 명시")
    floors: float | None = Field(None, description="지상 층수(소방활동 규모)")
    total_floor_area_sqm: float | None = Field(None, description="연면적(소방활동 규모)")


class AccessAssessment(BaseEvidenceResponse):
    """접도·도로 기반 종합 판정(P4) — 3상태 분리 + 종합 게이트 + 정직 고지."""

    is_assessed: bool = Field(True, description="판정 수행 여부")
    access_developability: str = Field(..., description="3상태 중 가장 제약 큰 등급(종합)")
    gate: AccessGate = Field(..., description="종합 게이트(gate_decision) — PASS/TENTATIVE/BLOCK")
    status: AccessStatus = Field(..., description="종합 정직 상태값")
    severity_label: str = Field(..., description="종합 등급 한글 라벨")
    resolvable: str = Field(..., description="종합 해결가능성 YES/CONDITIONAL/NO")
    legal: AccessStateResult
    physical: AccessStateResult
    emergency: AccessStateResult
    warnings: list[str] = Field(default_factory=list, description="정직 경고 문장(프론트 표기)")
    honest_disclosure: str = Field(..., description="종합 정직 고지")
    note: str = Field(
        "접도·도로 판정(규칙기반). 법정도로·현황도로 인정·접도구역·소방 접근은 토지이용계획확인원·"
        "현황측량·관할 지자체(도로관리청·소방서) 확인으로 확정하십시오.",
        description="종합 안내",
    )
    echo: dict[str, Any] = Field(default_factory=dict, description="요청 메타 에코(address/pnu)")
