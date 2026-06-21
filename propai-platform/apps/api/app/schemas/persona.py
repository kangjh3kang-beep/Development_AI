"""실무 전문가 페르소나 — 요청/응답(핸드오프 reportContract) 스키마.

페르소나 백엔드는 '백지'가 아니라 '오케스트레이션 레이어'다(분양대행=suggest_base_price·
market_report 재사용, 도시계획=permit/development/regulation/special_parcel primitive 폴백).
응답(PersonaReport)은 하류(OrchestratorPanel·PDF builder·다른 페르소나)가 동일 스키마로
소비하는 핸드오프 계약이다(R11). status=tentative면 확정 % 미표기(R12).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PersonaAnalyzeRequest(BaseModel):
    """페르소나 분석 요청. use_llm 기본 false(무과금) — 명시 선택 시에만 LLM·과금(R4)."""

    project_id: str | None = Field(default=None, description="프로젝트 ID(있으면 소속 부지 해석)")
    site_id: str | None = Field(default=None, description="분양현장 site_id(분양대행 적정분양가 산정)")
    address: str | None = Field(default=None, description="대표 주소(없으면 프로젝트에서 해석)")
    parcels: list[str] | None = Field(default=None, description="다필지 주소 목록(도시계획 통합분석)")
    bcode: str | None = Field(default=None, description="법정동코드(분양대행 실거래 조회)")
    pnu: str | None = Field(default=None, description="필지고유번호(시장보고서·규제분석 정밀조회)")
    equity_won: int | None = Field(default=None, description="자기자본(원) — 향후 지불여력 보강용")
    # ── 설계·시공 페르소나 SSOT 입력(프론트 useProjectContextStore에서 캡처) ──
    # 시공(constructor)은 total_gfa_sqm 가 없으면 estimate_overview(gt=0) 호출 불가 → E2E 불능.
    # 설계(designer)는 land_area_sqm·zone_code 가 없으면 폴백 일반박스로 퇴화. 그래서 명시 공급한다.
    # 미확보 시 runner 가 정직 고지(폴백/추정/partial) — 가짜값 금지(무목업).
    total_gfa_sqm: float | None = Field(default=None, description="연면적(㎡) — 시공 공사비 견적 입력")
    land_area_sqm: float | None = Field(default=None, description="대지면적(㎡) — 설계 매스/유닛믹스 입력")
    zone_code: str | None = Field(default=None, description="용도지역 코드(1R/2R/3R/GC/NC/QI/QR) — 설계 매스·법규한도 비교")
    building_type: str | None = Field(default=None, description="건물유형(apartment 등) — 시공 평단가 분기")
    # R11 핸드오프 — 다른 페르소나 PersonaReport dict 묶음(선택). 디벨로퍼 종합이 소비.
    report_contracts: dict[str, Any] | None = Field(
        default=None, description="페르소나간 핸드오프 reportContract({persona_key: PersonaReport}) — 디벨로퍼 종합 소비",
    )
    use_llm: bool = Field(default=False, description="LLM 내러티브·전문가패널 포함 여부(기본 false=무과금)")


class ChecklistItem(BaseModel):
    """실무 체크리스트 1줄 — 규칙기반 판정(무과금)."""

    step: str
    label: str
    status: str = Field(description="pass|warn|tentative|missing")
    value: Any | None = None
    kpi: str | None = None
    note: str | None = None


class PersonaReport(BaseModel):
    """페르소나 분석 산출물(핸드오프 reportContract, R11).

    status: confirmed(확정) | tentative(잠정·확정% 억제) | partial(일부 미확보).
    """

    persona_key: str
    name_ko: str
    project_id: str | None = None
    site_id: str | None = None
    address: str | None = None
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    honesty_notes: list[str] = Field(default_factory=list)
    status: str = "partial"
    billing: dict[str, Any] = Field(default_factory=dict)
