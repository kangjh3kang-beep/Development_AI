"""드론 IoT 하자 탐지 서비스.

MQTT(EMQX) 기반 드론 데이터 수신 + YOLOv8(Roboflow) 하자 탐지.
목표: F1 ≥ 0.80 (CoVe O6).

흐름:
1. MQTT 토픽에서 드론 이미지/GPS 수신
2. Roboflow Inference API로 하자 탐지
3. 탐지 결과를 DB + TimescaleDB에 저장
4. 심각도별 알림 (DroneAlertEvent SSE)
"""

from uuid import UUID

import structlog
from packages.schemas.events import DroneAlertEvent
from packages.schemas.models import DroneInspectionResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.drone_inspection import DroneInspection

logger = structlog.get_logger(__name__)


class DroneIoTService:
    """드론 IoT 하자 탐지 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def _detect_defects(self, image_url: str) -> list[dict]:
        """Roboflow API로 하자를 탐지한다."""
        import httpx

        if not self.settings.roboflow_api_key:
            logger.warning("Roboflow API 키 미설정 — Mock 탐지 결과 반환")
            return []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://detect.roboflow.com/construction-defects/1",
                    params={"api_key": self.settings.roboflow_api_key},
                    json={"image": image_url},
                )
                resp.raise_for_status()
                data = resp.json()

            predictions = data.get("predictions", [])
            return [
                {
                    "defect_type": p.get("class", "unknown"),
                    "confidence": p.get("confidence", 0.0),
                    "bbox": {
                        "x": p.get("x", 0),
                        "y": p.get("y", 0),
                        "w": p.get("width", 0),
                        "h": p.get("height", 0),
                    },
                }
                for p in predictions
            ]
        except Exception as e:
            logger.error("하자 탐지 API 호출 실패", error=str(e))
            return []

    def _classify_severity(self, defect_type: str, confidence: float) -> str:
        """하자 유형과 신뢰도에 따라 심각도를 분류한다."""
        critical_types = {"structural_crack", "collapse_risk", "foundation_damage"}
        high_types = {"water_leak", "reinforcement_exposure", "concrete_spalling"}

        if defect_type in critical_types and confidence >= 0.7:
            return "EMERGENCY"
        elif defect_type in high_types or confidence >= 0.85:
            return "HIGH"
        elif confidence >= 0.6:
            return "MEDIUM"
        return "LOW"

    async def inspect(
        self,
        project_id: UUID,
        tenant_id: UUID,
        image_urls: list[str],
        flight_id: str | None = None,
    ) -> DroneInspectionResponse:
        """드론 점검을 수행한다."""
        logger.info("드론 점검 시작", project_id=str(project_id), images=len(image_urls))

        all_defects: list[dict] = []
        severity_count = {"EMERGENCY": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

        for url in image_urls:
            detections = await self._detect_defects(url)
            for d in detections:
                severity = self._classify_severity(d["defect_type"], d["confidence"])
                d["severity"] = severity
                d["image_url"] = url
                severity_count[severity] += 1
                all_defects.append(d)

        # DB 저장
        inspection = DroneInspection(
            tenant_id=tenant_id,
            project_id=project_id,
            flight_id=flight_id,
            images_processed=len(image_urls),
            defects_found=len(all_defects),
            defects=all_defects,
            severity_summary=severity_count,
            model_version="yolov8-roboflow-v1",
        )
        self.db.add(inspection)
        await self.db.commit()
        await self.db.refresh(inspection)

        logger.info(
            "드론 점검 완료",
            defects=len(all_defects),
            severity=severity_count,
        )

        return DroneInspectionResponse(
            id=inspection.id,
            project_id=inspection.project_id,
            inspection_date=inspection.created_at,
            defects_found=inspection.defects_found,
            defects=all_defects,
            severity_summary=severity_count,
            images_processed=inspection.images_processed,
            created_at=inspection.created_at,
        )

    def create_alert_events(self, inspection_id: str, defects: list[dict]) -> list[DroneAlertEvent]:
        """EMERGENCY/HIGH 하자에 대한 알림 이벤트를 생성한다."""
        alerts = []
        for d in defects:
            if d.get("severity") in ("EMERGENCY", "HIGH"):
                alerts.append(DroneAlertEvent(
                    inspection_id=inspection_id,
                    severity=d["severity"],
                    defect_type=d["defect_type"],
                    location=d.get("bbox", {}),
                    image_url=d.get("image_url"),
                ))
        return alerts
