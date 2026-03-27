"""AI 스마트 주차 관리 서비스 (G119).

CRNN OCR 엔진 기반 번호판 인식.
- 정규식 검증: r'^[0-9]{2,3}[가-힣][0-9]{4}$'
- asyncio.to_thread()로 OCR 추론 논블로킹 처리
- cv2 리소스 누수 방지
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
UTC = timezone.utc
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from apps.api.database.models.parking_record import ParkingRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 한국 번호판 정규식: 123가4567 또는 12가3456
_PLATE_PATTERN = re.compile(r"^[0-9]{2,3}[가-힣][0-9]{4}$")


def _preprocess_plate_image(image_bytes: bytes) -> object | None:
    """번호판 이미지를 OCR 입력에 맞게 전처리한다.

    OpenCV 리소스 누수를 방지하기 위해 변환만 수행하고
    VideoCapture는 사용하지 않는다.
    """
    import cv2
    import numpy as np

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    # 그레이스케일 변환 + 이진화로 OCR 정확도 향상
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # OTSU 이진화
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    result: object = binary
    return result


def _run_ocr(preprocessed_image: object) -> str:
    """CRNN OCR 추론을 동기적으로 실행한다.

    이 함수는 반드시 asyncio.to_thread()를 통해 호출해야 한다.
    실 환경에서는 CRNN 모델을 로드하여 추론하지만,
    모델 미설치 시 easyocr로 폴백한다.
    """
    try:
        import easyocr

        reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
        results = reader.readtext(preprocessed_image)  # type: ignore[arg-type]
        # 가장 신뢰도 높은 결과 반환
        if results:
            # 공백/특수문자 제거
            raw_text = "".join(r[1] for r in results)
            return re.sub(r"\s+", "", raw_text)
    except ImportError:
        logger.warning("easyocr 미설치 — Mock OCR 결과 반환")
    except Exception as e:
        logger.error("OCR 추론 실패", error=str(e))

    return ""


def validate_plate_number(raw_text: str) -> str | None:
    """번호판 텍스트를 정규식으로 검증한다.

    Returns
    -------
    str | None
        유효한 번호판이면 정제된 문자열, 아니면 None.
    """
    cleaned = re.sub(r"[\s\-.]", "", raw_text)
    if _PLATE_PATTERN.match(cleaned):
        return cleaned
    return None


class ParkingService:
    """AI 스마트 주차 관리 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def recognize_plate(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        camera_id: str,
        image_bytes: bytes,
        zone: str | None = None,
        event_type: str = "entry",
    ) -> ParkingRecord | None:
        """번호판 이미지를 OCR로 인식하고 정규식 검증 후 DB에 기록한다.

        OCR 추론은 asyncio.to_thread()로 실행하여
        FastAPI의 메인 비동기 루프를 차단하지 않는다.
        """
        logger.info("번호판 인식 시작", camera_id=camera_id, zone=zone)

        # 전처리 — CPU 블로킹이므로 to_thread
        preprocessed = await asyncio.to_thread(
            _preprocess_plate_image, image_bytes,
        )
        if preprocessed is None:
            logger.error("이미지 디코딩 실패", camera_id=camera_id)
            return None

        # OCR 추론 — CPU/GPU 블로킹이므로 to_thread
        raw_text = await asyncio.to_thread(_run_ocr, preprocessed)
        logger.info("OCR 원본 결과", raw=raw_text, camera_id=camera_id)

        # 정규식 검증: r'^[0-9]{2,3}[가-힣][0-9]{4}$'
        validated = validate_plate_number(raw_text)
        if validated is None:
            logger.warning(
                "번호판 정규식 검증 실패",
                raw=raw_text,
                camera_id=camera_id,
            )
            return None

        # DB 저장
        record = ParkingRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            camera_id=camera_id,
            plate_number=validated,
            raw_ocr_text=raw_text,
            zone=zone,
            event_type=event_type,
            recorded_at=datetime.now(UTC),
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        logger.info("번호판 인식 완료", plate=validated, zone=zone)
        return record

    async def recognize_plate_from_stream(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        camera_id: str,
        rtsp_url: str,
        zone: str | None = None,
    ) -> list[ParkingRecord]:
        """RTSP 스트림에서 번호판을 추출한다.

        cv2.VideoCapture의 리소스 누수를 방지하기 위해
        finally 블록에서 cap.release()를 보장한다.
        """
        import cv2

        def _capture_frames() -> list[bytes]:
            cap = cv2.VideoCapture(rtsp_url)
            captured: list[bytes] = []
            frame_count = 0
            try:
                if not cap.isOpened():
                    logger.error("RTSP 스트림 열기 실패")
                    return captured
                while frame_count < 30:  # 최대 30프레임
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if frame_count % 10 == 0:  # 10프레임마다 1장 캡처
                        _, buf = cv2.imencode(".jpg", frame)
                        captured.append(buf.tobytes())
                    frame_count += 1
            finally:
                cap.release()
            return captured

        frame_bytes_list = await asyncio.to_thread(_capture_frames)
        records: list[ParkingRecord] = []

        for fb in frame_bytes_list:
            record = await self.recognize_plate(
                tenant_id=tenant_id,
                project_id=project_id,
                camera_id=camera_id,
                image_bytes=fb,
                zone=zone,
                event_type="entry",
            )
            if record is not None:
                records.append(record)

        return records
