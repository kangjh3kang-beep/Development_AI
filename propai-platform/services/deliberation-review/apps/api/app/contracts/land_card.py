"""대지 규제 카드 계약 — PNU 1건의 토지 기본정보(자동수집 1차출처).

심의/설계 자동분석의 입력 전제를 1차출처로 고정: 지목·면적·형상·경사·도로접면·용도지역(중첩)·
이용상황·공시지가. 결손 필드는 None으로 표면화(무음 단정 금지). source/stdr_year로 신선도 추적.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LandCard(BaseModel):
    pnu: str
    jimok: str | None = None              # 지목(대/전/답…)
    use_zone: str | None = None           # 대표 용도지역(제1종일반주거…)
    use_zones_all: list[str] = Field(default_factory=list)  # 중첩 용도지역/지구 전체
    use_situation: str | None = None      # 이용상황(연립…)
    slope: str | None = None              # 지세/경사(완경사…)
    shape: str | None = None              # 형상(정방형/부정형…)
    road_contact: str | None = None       # 도로접면(소로한면…)
    area: float | None = None             # 대지(필지)면적(㎡)
    land_price: float | None = None       # 개별공시지가(원/㎡)
    stdr_year: str | None = None          # 기준연도(신선도 vintage)
    max_age_days: int | None = None       # INC-12 허용 연한(stdr_year 대비 노후 판정 기준)
    existing_building: dict | None = None  # 기존 건물 제원(연면적/건폐율/용적률/층수/용도)
    remaining_capacity: dict | None = None  # 잔여 개발용량(현행 법정한도−기존, 증축/재건축 적정성)
    upzoning: dict | None = None           # 종상향 시나리오(단계별 용적률) + 가능성 신호(촉진/제약)
    sources: list[str] = Field(default_factory=list)  # 채워진 출처(vworld_landchar/landuse/building)
    notes: list[str] = Field(default_factory=list)

    def is_stale(self, as_of: date | None) -> bool:
        """stdr_year(기준연도) 대비 as_of(신청일)가 max_age_days 초과로 노후인가(결정론). 미평가 시 False."""
        if as_of is None or self.max_age_days is None or not self.stdr_year:
            return False
        try:
            vintage = date(int(self.stdr_year), 1, 1)
        except (TypeError, ValueError):
            return False
        return (as_of - vintage).days > self.max_age_days
