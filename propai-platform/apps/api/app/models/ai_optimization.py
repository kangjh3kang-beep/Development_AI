"""AI 최적화 모델 — SLSQP/Pareto 실행 결과 + AI 권고."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class OptimizationRun(Base):
    """최적화 실행 기록."""
    __tablename__ = "optimization_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    algorithm = Column(String(30), nullable=False, comment="SLSQP/Pareto/Greedy")
    objective = Column(String(50), nullable=False, comment="max_profit/max_roi/pareto")
    constraints = Column(JSON, default={}, comment="제약 조건")
    status = Column(String(20), default="running", comment="running/completed/failed")
    iterations = Column(Integer, default=0)
    elapsed_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class OptimizationResult(Base):
    """최적화 결과 — Pareto 해 포함."""
    __tablename__ = "optimization_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("optimization_runs.id"), nullable=False, index=True)
    is_pareto_optimal = Column(String(5), default="false", comment="true/false")
    variables = Column(JSON, nullable=False, comment="최적 변수값")
    profit_rate = Column(Numeric(8, 4), default=0)
    roi = Column(Numeric(8, 4), default=0)
    npv_won = Column(Numeric(20, 0), default=0)
    risk_score = Column(Numeric(6, 4), nullable=True)
    label = Column(String(100), nullable=True, comment="사용자 레이블")


class AIRecommendation(Base):
    """AI 권고 — 6규칙 진단 결과."""
    __tablename__ = "ai_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    rule_code = Column(String(10), nullable=False, comment="R001~R006")
    rule_name = Column(String(200), nullable=False)
    severity = Column(String(20), nullable=False, comment="info/warning/critical")
    message = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=True)
    current_value = Column(Numeric(14, 4), nullable=True)
    threshold_value = Column(Numeric(14, 4), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
