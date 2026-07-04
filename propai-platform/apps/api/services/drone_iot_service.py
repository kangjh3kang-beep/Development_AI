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

    async def _detect_defects(self, image_url: str) -> list[dict] | dict:
        """Roboflow API로 하자를 탐지한다.

        Returns:
            list[dict]: 탐지된 하자 목록.
            dict: 서비스 미설정 시 상태 정보 딕셔너리.
        """
        import httpx

        if not self.settings.roboflow_api_key:
            logger.warning("Roboflow API 키 미설정 — 서비스 미설정 상태 반환")
            return {
                "status": "service_not_configured",
                "message": "드론 하자탐지 서비스가 설정되지 않았습니다. ROBOFLOW_API_KEY 환경변수를 설정하세요.",
                "detections": [],
                "service_available": False,
            }

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
        service_status: dict | None = None

        for url in image_urls:
            detections = await self._detect_defects(url)
            if isinstance(detections, dict):
                # 서비스 미설정 상태 dict — 가짜 빈 탐지값으로 위장하지 않고
                # 상태를 응답에 정직하게 전파한다(순회 시 TypeError 방지 가드).
                service_status = detections
                continue
            for d in detections:
                severity = self._classify_severity(d["defect_type"], d["confidence"])
                d["severity"] = severity
                d["image_url"] = url
                severity_count[severity] += 1
                all_defects.append(d)

        # 심각도 요약 + (미설정 시) 서비스 상태 정직 전파 — 기존 4개 심각도 키는 그대로 유지
        severity_summary: dict = dict(severity_count)
        if service_status is not None:
            severity_summary["service_available"] = service_status.get("service_available", False)
            severity_summary["status"] = service_status.get("status", "service_not_configured")
            severity_summary["message"] = service_status.get("message", "")
            logger.warning(
                "하자 탐지 서비스 미설정 — 탐지 생략·상태 전파",
                status=severity_summary["status"],
            )

        # DB 저장
        inspection = DroneInspection(
            tenant_id=tenant_id,
            project_id=project_id,
            flight_id=flight_id,
            images_processed=len(image_urls),
            defects_found=len(all_defects),
            defects=all_defects,
            severity_summary=severity_summary,
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
            severity_summary=severity_summary,
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
