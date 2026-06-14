"""자가성장 엔진 — 플랫폼 텔레메트리 ORM (설계서 §2.2).

3개 테이블을 정의한다(모두 append-only, 보존정책 prune 외 UPDATE/DELETE 금지):
- platform_events   : 원시 이벤트 스트림(고볼륨 → bigserial PK, llm_usage_log 선례).
- platform_insights : 주기 배치 분석 결과(조치 트리거의 입력).
- ai_feedback       : 사용자 교정/평가(👍/👎 + 교정 텍스트, 학습 신호).

비로그인/익명 허용을 위해 tenant_id 는 NULL 허용으로 둔다(analysis_ledger 선례).
PII 는 저장하지 않는다: 사용자 식별은 user_hash(HMAC-SHA256)로만 보관한다.

⚠️ 이 ORM 의 메타데이터는 마이그레이션(v62_5_self_growth_tables)과
schema_guard 의 정합 기준이다. 컬럼/인덱스 변경 시 셋을 함께 갱신할 것.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base


class PlatformEvent(Base):
    """원시 이벤트 스트림(append-only). 모든 수집 이벤트의 단일 적재처.

    고볼륨이므로 PK 는 bigserial(llm_usage_log 선례). event_id 는 클라이언트
    멱등키로 UNIQUE(중복 전송 dedup). tenant_id 는 익명 허용 NULL.
    """

    __tablename__ = "platform_events"

    # 고볼륨 → bigserial(자동 증가 정수). llm_usage_log 선례.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 클라이언트 멱등키: 같은 event_id 재전송은 중복 적재되지 않는다(UNIQUE).
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="클라이언트 멱등키(dedup)"
    )
    # 익명 세션 허용 → NULL 가능.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="테넌트(익명이면 NULL)"
    )
    # user_id 의 HMAC-SHA256. 원본 user_id 는 저장하지 않는다(PII 익명화).
    user_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="user_id HMAC(PII 익명화)"
    )
    # 프론트 세션 식별(브라우저 sessionStorage UUID).
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # page_view/click/api_call/api_error/js_error/web_vital/llm_call/verify_result/fallback/heal_action
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # web/api/worker
    surface: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 프론트 라우트 또는 API 경로(쿼리스트링 제거·정규화).
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # info/warn/error/critical
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LLM service 명(base_interpreter.name 과 정합).
    service: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 익명화된 상세(스택트레이스 정규화·입력요약). PII 키 마스킹 후 저장.
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # web sw 버전 / api 빌드 식별.
    app_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ⚠️ 컬럼레벨 index=True 금지: 자동 생성명(ix_*)이 schema_guard/마이그레이션의
    #   명시명(idx_pe_created)과 달라 환경별 인덱스 이중 생성을 유발한다.
    #   인덱스는 아래 __table_args__ 에서 schema_guard 와 동일한 이름으로만 정의한다.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_pe_type_created", "event_type", "created_at"),
        Index("idx_pe_tenant_created", "tenant_id", "created_at"),
        Index("idx_pe_route_status", "route", "status_code"),
        Index("idx_pe_service_created", "service", "created_at"),
        # 단일 created_at 인덱스(schema_guard idx_pe_created 와 동일명으로 통일).
        Index("idx_pe_created", "created_at"),
        # 멱등(중복전송 차단). NULL event_id 는 UNIQUE 제약에서 충돌하지 않는다.
        Index("uq_pe_event_id", "event_id", unique=True),
    )


class PlatformInsight(Base):
    """분석 결과(주기 배치 산출물). 조치 트리거의 입력.

    phase_f 모델의 metrics_json + narrative 패턴을 차용(코드베이스 일관성).
    """

    __tablename__ = "platform_insights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 전체집계는 NULL, 테넌트별은 값.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # usage_pattern/funnel/churn_risk/error_cluster/fallback_rate/quality_drop/latency_regression
    insight_type: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 정량지표(예: error_rate, p95_latency, fallback_pct).
    metrics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # info/warn/critical (조치 등급 결정).
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LLM/규칙 기반 요약(대시보드 표시).
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 권고 조치(heal/correct/propose_pr/none).
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    # open/acknowledged/acted/dismissed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open"
    )
    # 컬럼레벨 index=True 금지(이중 생성 방지) — 아래 __table_args__ 명시명으로 통일.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_pi_type_created", "insight_type", "created_at"),
        Index("idx_pi_severity_status", "severity", "status"),
        # 단일 created_at 인덱스(schema_guard idx_pi_created 와 동일명으로 통일).
        Index("idx_pi_created", "created_at"),
    )


class AIFeedback(Base):
    """사용자 교정/평가(👍/👎 + 자유 교정). 학습 신호(영구 보존).

    content_hash 는 analysis_ledger.content_hash 와 조인키 — 어떤 버전 분석에
    대한 만족/불만인지 정밀 추적한다.
    """

    __tablename__ = "ai_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 컬럼레벨 index=True 금지(이중 생성 방지) — 아래 __table_args__ 명시명으로 통일.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    user_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="PII 익명화"
    )
    # llm_output/analysis/recommendation
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    service: Mapped[str | None] = mapped_column(Text, nullable=True)
    # analysis_ledger.analysis_type 와 정합(원장 연결).
    analysis_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # analysis_ledger.content_hash 와 조인키.
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # up/down
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 사용자 교정 텍스트(학습 신호).
    correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 1~5 선택.
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # tenant_id 단일 인덱스(schema_guard idx_af_tenant 와 동일명으로 통일).
        Index("idx_af_tenant", "tenant_id"),
        Index("idx_af_service_verdict_created", "service", "verdict", "created_at"),
        Index("idx_af_analysis_hash", "analysis_type", "content_hash"),
    )


__all__ = ["PlatformEvent", "PlatformInsight", "AIFeedback"]
