"""시장조사 및 타겟 분석을 위한 표준화된 데이터 모델 (DemographicProfile).

1단계(공공데이터: SGIS, KOSIS)와 2단계(민간데이터: K-Atlas)의 데이터를 
모두 수용할 수 있도록 설계된 어댑터(Adapter) 패턴의 핵심 Pydantic 스키마입니다.
추후 2단계에서 유료 데이터 연동 시 이 스키마의 optional 필드들이 채워집니다.
"""

from typing import Optional, List
from pydantic import BaseModel, Field

class MigrationData(BaseModel):
    """인구 이동망 데이터 (1단계 SGIS 기반)"""
    target_adm_cd: str = Field(..., description="대상 행정구역 코드")
    year: str = Field(..., description="조회 연도")
    total_inflow: int = Field(0, description="총 전입 인구")
    total_outflow: int = Field(0, description="총 전출 인구")
    net_migration: int = Field(0, description="순이동 인구")
    top_inflow_regions: List[dict] = Field(default_factory=list, description="주요 전입 출발지 Top 3")
    # 데이터 출처 플래그: 'live'(실데이터) | 'fallback'(합성·대체값) | 'mock'(개발용) | 'unavailable'(데이터 없음·정직표기)
    # 옵셔널·하위호환: 기존 응답을 깨지 않으면서 실데이터/가짜값을 구분하기 위한 가산 필드.
    data_source: Optional[str] = Field(None, description="데이터 출처 구분 플래그")

class PopulationData(BaseModel):
    """거주 인구 및 가구 특성 (1단계 SGIS 기반)"""
    target_adm_cd: str = Field(..., description="대상 행정구역 코드")
    year: str = Field(..., description="조회 연도")
    total_population: int = Field(0, description="총 인구")
    age_distribution: dict = Field(default_factory=dict, description="연령대별 인구 분포")
    household_types: dict = Field(default_factory=dict, description="가구원수별 분포 (1인가구 등)")
    # 데이터 출처 플래그(위 MigrationData 와 동일 의미). 옵셔널·하위호환 가산 필드.
    data_source: Optional[str] = Field(None, description="데이터 출처 구분 플래그")

class MacroIncomeData(BaseModel):
    """거시적 소득 지표 (1단계 KOSIS 기반).

    KosisClient(kosis_client.py)가 실제로 만드는 dict 구조와 키를 일치시킨다.
    (불일치 시 Pydantic 검증은 통과해도 model_dump 단계에서 소득 데이터가 통째로 유실된다.)
    """
    sigungu_cd: str = Field(..., description="시군구 단위 코드")
    year: str = Field(..., description="조회 연도")
    avg_income_10k: int = Field(0, description="시군구 평균 연소득(만원)")
    median_income_10k: int = Field(0, description="시군구 중위 연소득(만원)")
    income_bracket_ratio: dict = Field(default_factory=dict, description="소득 구간별 비율(%)")
    # 데이터 출처 플래그(MigrationData 와 동일 의미). 옵셔널·하위호환 가산 필드.
    data_source: Optional[str] = Field(None, description="데이터 출처 구분 플래그")

class MicroFinancialData(BaseModel):
    """초정밀 금융/소비/소유 지표 (2단계 K-Atlas API 연동 시 활성화)"""
    # 기본 정보
    gisId: Optional[str] = Field(None, description="지리정보 ID (블록/행정동)")
    cntCust: Optional[int] = Field(None, description="인구수")
    avgAge: Optional[float] = Field(None, description="평균 연령")
    
    # 소득 지표
    avgInc: Optional[float] = Field(None, description="평균 월소득(만원)")
    medianInc: Optional[int] = Field(None, description="중위 월소득(만원)")
    cntCustInc20b: Optional[int] = Field(None, description="월 소득 200만원 이하 대상자 수")
    cntCustInc80b: Optional[int] = Field(None, description="월 소득 800만원 이상 대상자 수")
    
    # 직업 분포
    cntCustEmp: Optional[int] = Field(None, description="급여소득자 수")
    cntCustSoho: Optional[int] = Field(None, description="자영업자 수")
    cntCustExpt: Optional[int] = Field(None, description="전문직 종사자 수")
    
    # 여력 및 부채 (대출/카드)
    sumLoanAmt: Optional[int] = Field(None, description="대출잔액 합계(원)")
    sumLoanHLoanAmt: Optional[int] = Field(None, description="주택담보대출 잔액 합계(원)")
    sumCardAvgAmt3m: Optional[int] = Field(None, description="3개월 평균 카드소비금액 합계(원)")
    avrCreditscore: Optional[float] = Field(None, description="평균 신용평점")
    cntCustDlq30d: Optional[int] = Field(None, description="30일 미만 연체 보유자 수")
    
    # 실거주 및 소유 형태
    cntCustMyHomeLive: Optional[int] = Field(None, description="자가거주자 수")
    cntCustLess: Optional[int] = Field(None, description="전세 및 월세 거주자 수")
    cntCustHOwn: Optional[int] = Field(None, description="주택보유자 수")
    avgHOwnHold: Optional[int] = Field(None, description="평균 주택보유 건수")

class DemographicProfile(BaseModel):
    """통합 인구/소득 프로파일. 백엔드 파이프라인의 최종 산출물"""
    source_phase: int = Field(1, description="데이터 출처 단계 (1: 공공데이터, 2: 민간 확장데이터)")
    migration: MigrationData
    population: PopulationData
    macro_income: MacroIncomeData
    micro_finance: Optional[MicroFinancialData] = Field(None, description="2단계 민간 제휴 데이터")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_phase": 1,
                "migration": {"target_adm_cd": "11680", "year": "2026", "total_inflow": 12500, "total_outflow": 11200, "net_migration": 1300, "top_inflow_regions": []},
                "population": {"target_adm_cd": "11680", "year": "2026", "total_population": 45000, "age_distribution": {}, "household_types": {}},
                "macro_income": {"sigungu_cd": "11680", "year": "2026", "avg_income_10k": 4620, "median_income_10k": 3800, "income_bracket_ratio": {}},
                "micro_finance": None
            }
        }
