"""모델 성능 기록 모델.

AI 모델별 성능 메트릭을 추적한다.
MLflow와 연동하여 챔피언/챌린저 모델을 관리한다.
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TimestampMixin


class ModelPerformance(Base, TimestampMixin):
    __tablename__ = "model_performance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="모델명 (예: avm_xgboost, drone_yolov8)"
    )
    model_version: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="모델 버전"
    )
    mlflow_run_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="MLflow 실행 ID"
    )
    metrics: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        comment="성능 메트릭 {mape, rmse, f1, accuracy, recall, precision, ...}"
    )
    dataset_info: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="훈련/평가 데이터셋 정보"
    )
    is_champion: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="현재 운영 모델 여부"
    )
    hyperparameters: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="하이퍼파라미터"
    )
