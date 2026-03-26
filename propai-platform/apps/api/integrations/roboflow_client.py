"""Roboflow API 클라이언트.

YOLOv8 기반 건설 하자 탐지 — 드론 서비스에서 사용.
"""

from apps.api.integrations.base_client import BaseAPIClient


class RoboflowClient(BaseAPIClient):
    service_name = "roboflow"
    base_url = "https://detect.roboflow.com"
    timeout = 60.0  # 이미지 분석이라 타임아웃 여유

    async def detect_defects(self, image_url: str, model_id: str = "construction-defects/1") -> dict:
        return await self._request(
            "POST", f"/{model_id}",
            params={"api_key": self.settings.roboflow_api_key},
            json_data={"image": image_url},
        )
