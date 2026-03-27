"""AI 공사현장 안전관리 서비스 (G116).

YOLOv8 기반 안전모/조끼 미착용 감지.
- 5프레임 스킵 최적화로 GPU/CPU 과부하 방지
- asyncio.to_thread()로 추론 논블로킹 처리
- cv2.VideoCapture 리소스 누수 방지 (finally 블록)
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
UTC = timezone.utc
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from apps.api.config import get_settings
from apps.api.database.models.safety_violation import SafetyViolation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 5프레임 스킵 — 매 6번째 프레임만 추론
_FRAME_SKIP = 5

# 감지 대상 클래스 (YOLOv8 커스텀 모델 기준)
_VIOLATION_CLASSES: dict[int, str] = {
    0: "helmet_off",
    1: "vest_off",
}

# 최소 신뢰도 임계값
_MIN_CONFIDENCE = 0.45


def _load_yolo_model() -> object:
    """YOLOv8 모델을 로드한다. 지연 로딩으로 메모리 절약."""
    from ultralytics import YOLO

    settings = get_settings()
    model_path = getattr(settings, "yolo_safety_model_path", "yolov8n.pt")
    model = YOLO(model_path)
    logger.info("YOLOv8 안전관리 모델 로드 완료", model=model_path)
    return model


# 모듈 수준 싱글톤 (최초 호출 시 로드)
_yolo_model: object | None = None


def _get_model() -> object:
    global _yolo_model
    if _yolo_model is None:
        _yolo_model = _load_yolo_model()
    return _yolo_model


def _run_inference_on_frame(frame: object) -> list[dict]:
    """YOLOv8 추론을 동기적으로 실행한다.

    이 함수는 반드시 asyncio.to_thread()를 통해 호출해야 한다.
    """
    model = _get_model()
    results = model(frame, verbose=False)  # type: ignore[operator]

    violations: list[dict] = []
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if cls_id in _VIOLATION_CLASSES and conf >= _MIN_CONFIDENCE:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                violations.append({
                    "violation_type": _VIOLATION_CLASSES[cls_id],
                    "confidence": round(conf, 4),
                    "bbox": {
                        "x": round(x1),
                        "y": round(y1),
                        "w": round(x2 - x1),
                        "h": round(y2 - y1),
                    },
                })
    return violations


def _extract_frames_with_skip(rtsp_url: str, max_frames: int = 300) -> list:
    """RTSP 스트림에서 5프레임 스킵으로 프레임을 추출한다.

    반드시 finally에서 cap.release()를 호출하여 리소스 누수를 방지한다.
    """
    import cv2

    cap = cv2.VideoCapture(rtsp_url)
    frames: list = []
    frame_count = 0

    try:
        if not cap.isOpened():
            logger.error("RTSP 스트림 열기 실패", url=_sanitize_url(rtsp_url))
            return frames

        while len(frames) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            # 5프레임 스킵 최적화: 매 6번째 프레임만 처리
            if frame_count % (_FRAME_SKIP + 1) == 0:
                frames.append(frame)

            frame_count += 1
    finally:
        # OpenCV 리소스 누수 방지 — 예외 발생 시에도 반드시 해제
        cap.release()
        logger.debug("VideoCapture 해제 완료", total_read=frame_count, extracted=len(frames))

    return frames


def _sanitize_url(url: str) -> str:
    """로그에 RTSP 비밀번호가 노출되지 않도록 마스킹."""
    return re.sub(r"://[^@]+@", "://***@", url)


class SafetyService:
    """공사현장 AI 안전관리 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def analyze_stream(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        camera_id: str,
        rtsp_url: str,
        max_frames: int = 300,
    ) -> list[SafetyViolation]:
        """RTSP 스트림을 분석하여 안전 위반을 감지하고 DB에 기록한다.

        모든 추론은 asyncio.to_thread()로 실행하여
        FastAPI의 메인 비동기 루프를 차단하지 않는다.
        """
        logger.info(
            "안전관리 스트림 분석 시작",
            camera_id=camera_id,
            url=_sanitize_url(rtsp_url),
        )

        # 프레임 추출 — CPU 블로킹이므로 to_thread
        frames = await asyncio.to_thread(
            _extract_frames_with_skip, rtsp_url, max_frames,
        )

        if not frames:
            logger.warning("추출된 프레임 없음", camera_id=camera_id)
            return []

        # 프레임별 추론 — GPU/CPU 블로킹이므로 to_thread
        all_violations: list[SafetyViolation] = []
        now = datetime.now(UTC)

        for frame in frames:
            detections = await asyncio.to_thread(_run_inference_on_frame, frame)

            for det in detections:
                violation = SafetyViolation(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    camera_id=camera_id,
                    violation_type=det["violation_type"],
                    confidence=det["confidence"],
                    bbox_json=det["bbox"],
                    detected_at=now,
                )
                self.db.add(violation)
                all_violations.append(violation)

        if all_violations:
            await self.db.commit()
            for v in all_violations:
                await self.db.refresh(v)

        logger.info(
            "안전관리 분석 완료",
            camera_id=camera_id,
            violations=len(all_violations),
        )
        return all_violations

    async def analyze_single_frame(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        camera_id: str,
        image_bytes: bytes,
    ) -> list[SafetyViolation]:
        """단일 이미지 프레임을 분석한다 (REST API용)."""
        import numpy as np

        # bytes → numpy array → OpenCV format (to_thread로 디코딩)
        def _decode_and_infer() -> list[dict]:
            import cv2

            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is None:
                return []
            return _run_inference_on_frame(frame)

        detections = await asyncio.to_thread(_decode_and_infer)

        violations: list[SafetyViolation] = []
        now = datetime.now(UTC)

        for det in detections:
            violation = SafetyViolation(
                tenant_id=tenant_id,
                project_id=project_id,
                camera_id=camera_id,
                violation_type=det["violation_type"],
                confidence=det["confidence"],
                bbox_json=det["bbox"],
                detected_at=now,
            )
            self.db.add(violation)
            violations.append(violation)

        if violations:
            await self.db.commit()
            for v in violations:
                await self.db.refresh(v)

        return violations
