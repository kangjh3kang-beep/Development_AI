"""인허가 사례(건축HUB) Pydantic 스키마 — 요청/응답 모델.

건축HUB 주택인허가(HsPmsHubService)·건축인허가(ArchPmsHubService) 기본개요 raw item을
정규화한 사례 레코드와 분위수 요약 모델을 정의한다.

원칙: 모든 사례 필드는 Optional — 원천에 없는 값은 None으로 정직하게 표기(가짜값 금지).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PermitCaseRecord(BaseModel):
    """인허가 사례 1건 (건축HUB 기본개요 정규화).

    원천 필드 매핑: platArea→land_area_sqm, archArea→building_area_sqm,
    totArea→total_floor_area_sqm, bcRat→bcr_pct, vlRat→far_pct,
    grndFlrCnt/ugrndFlrCnt→floors_above/below, mainPurpsCdNm→main_use,
    pmsDay→permit_date, stcnsDay→construction_start_date, useAprDay→approval_date.
    """

    land_area_sqm: Optional[float] = None        # 대지면적(㎡)
    building_area_sqm: Optional[float] = None    # 건축면적(㎡)
    total_floor_area_sqm: Optional[float] = None # 연면적(㎡)
    bcr_pct: Optional[float] = None              # 건폐율(%)
    far_pct: Optional[float] = None              # 용적률(%)
    floors_above: Optional[int] = None           # 지상층수
    floors_below: Optional[int] = None           # 지하층수
    main_use: Optional[str] = None               # 주용도명
    permit_date: Optional[str] = None            # 허가일(ISO YYYY-MM-DD)
    construction_start_date: Optional[str] = None  # 착공일(ISO YYYY-MM-DD)
    approval_date: Optional[str] = None          # 사용승인일(ISO YYYY-MM-DD)


class PermitCaseSummary(BaseModel):
    """인허가 사례 분위수 요약.

    표본 5건 미만이면 분위수는 None(미산출) — 응답 note에 사유 표기.
    """

    count: int = 0                                # 정규화 사례 수
    bcr_p25: Optional[float] = None               # 건폐율 25분위(%)
    bcr_p50: Optional[float] = None               # 건폐율 중앙값(%)
    bcr_p75: Optional[float] = None               # 건폐율 75분위(%)
    far_p25: Optional[float] = None               # 용적률 25분위(%)
    far_p50: Optional[float] = None               # 용적률 중앙값(%)
    far_p75: Optional[float] = None               # 용적률 75분위(%)
    main_use_top3: list[str] = Field(default_factory=list)  # 주용도 상위 3개
    recent_24m_count: int = 0                     # 최근 24개월 허가 건수
    # 인허가 소요기간(데이터계획 #2) — 표본 5건 미만이면 None(과대해석 방지).
    permit_to_start_days_p50: Optional[int] = None     # 허가→착공 소요일 중앙값
    permit_to_approval_days_p50: Optional[int] = None  # 허가→사용승인 소요일 중앙값


class PermitCaseResponse(BaseModel):
    """인허가 사례 조회 응답."""

    cases: list[PermitCaseRecord] = Field(default_factory=list)
    summary: PermitCaseSummary = Field(default_factory=PermitCaseSummary)
    total: int = 0                                # 페이지네이션 전 전체 사례 수
    source: str = "building_hub"                  # 데이터 출처(건축HUB)
    note: Optional[str] = None                    # 빈결과·표본부족 등 정직 사유
