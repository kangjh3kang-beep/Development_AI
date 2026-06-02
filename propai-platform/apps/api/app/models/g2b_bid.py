"""나라장터(G2B) 입찰/낙찰 데이터 모델."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID

from app.core.database import Base


class G2BBid(Base):
    """공공 입찰/낙찰 공고 정보."""

    __tablename__ = "g2b_bids"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── 공고 식별 ──
    bid_notice_no = Column(String(50), unique=True, nullable=False, comment="입찰공고번호")
    bid_notice_nm = Column(Text, nullable=False, comment="입찰공고명")
    bid_notice_ord = Column(String(10), nullable=True, comment="입찰공고차수")

    # ── 분류 ──
    bid_type = Column(String(20), nullable=False, comment="업무구분(공사/용역/물품/외자)")
    category_tags = Column(ARRAY(String), default=[], comment="AI 분류 태그(재개발,건축설계 등)")

    # ── 발주기관 ──
    org_name = Column(String(200), nullable=False, comment="발주기관명")
    org_type = Column(String(50), nullable=True, comment="기관유형(지자체/공공기관/공기업)")
    demand_org_name = Column(String(200), nullable=True, comment="수요기관명")

    # ── 금액 ──
    estimated_price = Column(Numeric(20, 0), nullable=True, comment="추정가격(KRW)")
    budget_amount = Column(Numeric(20, 0), nullable=True, comment="배정예산액(KRW)")

    # ── 일정 ──
    bid_begin_dt = Column(DateTime, nullable=True, comment="입찰개시일시")
    bid_close_dt = Column(DateTime, nullable=True, comment="입찰마감일시")
    open_dt = Column(DateTime, nullable=True, comment="개찰일시")
    notice_dt = Column(DateTime, nullable=True, comment="공고일시")

    # ── 지역 ──
    region_sido = Column(String(50), nullable=True, comment="시/도")
    region_sigungu = Column(String(50), nullable=True, comment="시/군/구")
    delivery_place = Column(Text, nullable=True, comment="납품장소/공사현장")

    # ── 입찰 조건 ──
    bid_method = Column(String(50), nullable=True, comment="입찰방식(일반/제한/지명 등)")
    contract_method = Column(String(50), nullable=True, comment="계약방법(총액/단가/턴키 등)")
    qualification = Column(Text, nullable=True, comment="입찰참가자격")

    # ── 상태 ──
    status = Column(String(30), default="active", comment="진행중/마감/낙찰/유찰")

    # ── 낙찰 정보 (수집 후 갱신) ──
    award_price = Column(Numeric(20, 0), nullable=True, comment="낙찰금액(KRW)")
    award_rate = Column(Numeric(6, 3), nullable=True, comment="낙찰가율(%)")
    award_company = Column(String(200), nullable=True, comment="낙찰업체명")
    award_dt = Column(DateTime, nullable=True, comment="낙찰일시")
    bid_count = Column(Integer, nullable=True, comment="투찰업체수")

    # ── 나라장터 연결 ──
    g2b_url = Column(Text, nullable=True, comment="나라장터 상세 페이지 URL")

    # ── AI 분석 결과 ──
    ai_risk_score = Column(Numeric(5, 2), nullable=True, comment="AI 리스크 스코어(0~100)")
    ai_recommended_bid_rate = Column(Numeric(6, 3), nullable=True, comment="AI 추천 투찰가율(%)")
    ai_analysis_summary = Column(Text, nullable=True, comment="AI 분석 요약")

    # ── 원본 데이터 ──
    raw_data = Column(JSON, default={}, comment="원본 API 응답 JSON")

    # ── 타임스탬프 ──
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_g2b_bids_bid_type", "bid_type"),
        Index("ix_g2b_bids_status", "status"),
        Index("ix_g2b_bids_region", "region_sido", "region_sigungu"),
        Index("ix_g2b_bids_bid_close_dt", "bid_close_dt"),
        Index("ix_g2b_bids_notice_dt", "notice_dt"),
    )


class G2BBidAnalysis(Base):
    """입찰 AI 정밀분석 히스토리 — 분석 결과를 영속화해 재조회·재분석·삭제한다."""

    __tablename__ = "g2b_bid_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bid_id = Column(UUID(as_uuid=True), nullable=False, comment="대상 입찰 공고 id")
    bid_notice_no = Column(String(50), nullable=True, comment="입찰공고번호(스냅샷)")
    bid_notice_nm = Column(Text, nullable=True, comment="입찰공고명(스냅샷)")

    # ── 분석 입력(편집 재분석용) ──
    params = Column(JSON, default={}, comment="분석 입력 파라미터(연면적/층수/구조/유형/마진 등)")

    # ── 요약 지표(목록 표시용) ──
    recommended_bid_rate = Column(Numeric(6, 3), nullable=True, comment="추천 투찰가율(%)")
    risk_score = Column(Numeric(5, 2), nullable=True, comment="리스크 스코어")
    expected_roi = Column(Numeric(8, 3), nullable=True, comment="예상 ROI(%)")
    summary = Column(Text, nullable=True, comment="AI 요약")

    # ── 전체 결과(재조회용) ──
    result = Column(JSON, default={}, comment="G2BBidAnalyzeResponse 전체 JSON")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_g2b_bid_analyses_bid_id", "bid_id"),
        Index("ix_g2b_bid_analyses_created_at", "created_at"),
    )


class G2BAwardStat(Base):
    """낙찰가율 집계 통계 (지역별/공종별 사전 계산)."""

    __tablename__ = "g2b_award_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stat_period = Column(String(10), nullable=False, comment="집계기간(YYYY-MM)")
    bid_type = Column(String(20), nullable=False, comment="업무구분")
    region_sido = Column(String(50), nullable=True, comment="시/도")
    avg_award_rate = Column(Numeric(6, 3), nullable=True, comment="평균 낙찰가율")
    min_award_rate = Column(Numeric(6, 3), nullable=True, comment="최저 낙찰가율")
    max_award_rate = Column(Numeric(6, 3), nullable=True, comment="최고 낙찰가율")
    bid_count = Column(Integer, default=0, comment="집계 건수")
    avg_competition_ratio = Column(Numeric(6, 2), nullable=True, comment="평균 경쟁률")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_g2b_award_stats_period_type", "stat_period", "bid_type"),
    )
