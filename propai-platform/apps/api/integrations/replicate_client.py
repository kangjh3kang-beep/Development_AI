"""Replicate API 클라이언트.

SDXL 기반 평면도 이미지 생성 — 설계 서비스에서 사용.
"""

from apps.api.integrations.base_client import BaseAPIClient


class ReplicateClient(BaseAPIClient):
    service_name = "replicate"
    base_url = "https://api.replicate.com/v1"
    timeout = 120.0  # 이미지 생성은 시간이 걸림

    def _default_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.settings.replicate_api_token}",
            "Content-Type": "application/json",
        }

    async def run_sdxl(self, prompt: str, negative_prompt: str = "") -> dict:
        return await self._request(
            "POST", "/predictions",
            json_data={
                "version": "39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
                "input": {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "width": 1024,
                    "height": 1024,
                    "num_outputs": 1,
                },
            },
        )
