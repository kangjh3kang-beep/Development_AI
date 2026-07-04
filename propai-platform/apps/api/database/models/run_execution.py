"""C2R/HITL run 추적 테이블(run_execution) — SQLAlchemy ORM(정본).

C2R 파이프라인의 실행 단위를 추적하는 레코드. 4-track DAG·검증 오버레이·HITL 승인이
공유하는 run 단위로, 멱등키(idempotency_key)로 재실행 중복을 막고, 산출물은
artifact_uri(propai://...#sha256=)로 가리킨다. 상태는 RunStateEnum 값(문자열)으로 저장한다.

★스키마 생성 경로(중요): 이 프로젝트는 부팅 시 `alembic upgrade`를 강제하지 않는다
  (safe-deploy·Dockerfile CMD·main.py 어디에도 없음 — 서비스별 ensure_schema 안전망에 의존).
  따라서 이 테이블은 (1) 정본 마이그레이션 `v62_8_run_execution` + (2)
  `run_store.ensure_schema`(부팅/소비 시 멱등 create_all)의 이중 안전망으로 생성한다.
  둘 다 이 ORM 메타데이터를 단일 진실원천으로 쓰므로 스키마 드리프트가 없다.
"""

from __future__ import annotations

import uuid
from typing import Any

from packages.schemas.run_state import RunStateEnum
from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TimestampMixin


class RunExecution(Base, TimestampMixin):
    """C2R run 추적 레코드(run_execution). created_at/updated_at 은 TimestampMixin 제공."""

    __tablename__ = "run_execution"

    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # 상위 run(재실행/파생 계보). FK는 걸지 않는다(느슨한 결합·삭제 순서 자유).
    parent_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 4-track DAG 트랙명(예: legal|design|bim|validation). P0에선 자유 문자열.
    track: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # S0~S9 가이드런 단계.
    s_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # RunStateEnum 값(문자열 저장). 기본 draft.
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RunStateEnum.DRAFT.value
    )
    # 입력 정규화 해시(sha256) — 멱등/재현.
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 산출물 URI: propai://{tenant}/{project}/{run}/{name}#sha256=... (artifact_store 계약).
    artifact_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # HITL 승인 게이트 상태(구조화).
    approval_gate_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # 멱등키 — 같은 입력의 재요청이 run을 중복 생성하지 않도록(UNIQUE).
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    __table_args__ = (
        # 프로젝트별 상태 조회 가속(대시보드/필터).
        Index("ix_run_execution_project_state", "project_id", "state"),
    )
