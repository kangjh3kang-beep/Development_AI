"""P0 — 실 VLLM 시트분류 어댑터. 기존 SheetClassifierAdapter 계약(classify(sheet)->str|None) 준수.

도면 이미지 + 표제란 텍스트 → VLLM이 시트역할 추정(설계도서 자동해석의 멀티모달 추출 진입점).
키/이미지/클라이언트 부재 시 graceful degrade(입력 신호 그대로, 날조 금지) → AT 키 없이 그린 유지.
INV-8(3원 합의)·INV-9(임의 기본값 금지)는 SheetRoleResolver가 보존 — VLLM은 1개 신호일 뿐.
"""
from __future__ import annotations

from typing import Protocol

from app.adapters.vision.sheet_classifier import MockSheetClassifier
from app.adapters.vision.titleblock_reader import TitleblockReader
from app.contracts.sheet_role import SheetRole
from app.settings import env_or_setting, settings


class VisionClient(Protocol):
    """VLLM 비전 호출 인터페이스(주입). 실 클라이언트는 이 시그니처를 구현."""

    def classify_sheet(self, image_ref: str, hint_text: str | None) -> str | None: ...


def _normalize(raw: object) -> str | None:
    """VLLM 출력 → SheetRole 이름(영문 enum) 또는 None. 미상은 None(임의 단정 금지, INV-9)."""
    if not raw:
        return None
    s = str(raw).strip().upper()
    if s in SheetRole.__members__:
        return s
    role = TitleblockReader().read_role(str(raw))  # 한국어 명칭(단면도 등) → role
    return role.value if role is not None else None


class VLLMSheetClassifier:
    """SheetClassifierAdapter 호환. vision_client 주입 시 실 VLLM, 아니면 입력 신호로 degrade."""

    def __init__(self, vision_client: VisionClient | None = None) -> None:
        self.vision_client = vision_client

    def classify(self, sheet: dict) -> str | None:
        image_ref = sheet.get("image_ref") or sheet.get("image")
        if self.vision_client is not None and image_ref:
            raw = self.vision_client.classify_sheet(image_ref, sheet.get("titleblock_text"))
            return _normalize(raw)
        # VLLM 미가용(키/이미지/클라이언트 부재) → 입력 분류신호 그대로(mock 동등). 날조 금지.
        return sheet.get("classifier_role")


class AnthropicVisionClient:
    """참조 실 클라이언트(Anthropic vision). lazy httpx + 키 검사. 미가용 시 None 반환(graceful)."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        # env 우선(시크릿 오버레이 반영) → settings 폴백.
        self.api_key = api_key or env_or_setting("ANTHROPIC_API_KEY")
        self.model = model or env_or_setting("VLLM_MODEL") or settings.VLLM_MODEL

    def classify_sheet(self, image_ref: str, hint_text: str | None) -> str | None:
        if not self.api_key:
            return None  # 키 없음 → 호출 안 함(상위 degrade)
        try:
            import httpx  # lazy — 미설치/오프라인이어도 패키지 import는 안전.
        except ImportError:
            return None
        prompt = (
            "다음 건축 도면 시트 이미지의 역할을 하나로 분류해 영문 코드만 답하라: "
            "SITE/PLAN/ELEVATION/SECTION/AREA_TABLE/PARKING/SUNLIGHT/DISTRICT_UNIT. "
            f"표제란 힌트: {hint_text or '(없음)'}."
        )
        from app.adapters.vision.image_source import build_content
        content = build_content(image_ref, prompt)  # 이미지면 멀티모달 [image, text]
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json={"model": self.model, "max_tokens": 16,
                      "messages": [{"role": "user", "content": content}]},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
        except Exception:
            return None  # 라이브 실패 → degrade(무음 단정 금지, 상위가 신호 결손 처리)


def build_sheet_classifier(vision_client: VisionClient | None = None):
    """설정 기반 시트 분류기 팩토리. 기본 mock(AT 그린). SHEET_CLASSIFIER=vllm 시 실 어댑터."""
    if env_or_setting("SHEET_CLASSIFIER") == "vllm":
        client = vision_client or AnthropicVisionClient()
        return VLLMSheetClassifier(vision_client=client)
    return MockSheetClassifier()
