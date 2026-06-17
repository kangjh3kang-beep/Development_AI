"""P-A — 도면 자동해석 추출기. 도면 시트 → 구조화 요소(ExtractedElement).

vision_client 주입 + image_ref 있으면 실 VLLM 비전 추출, 아니면 element_hints 폴백(결정론),
둘 다 없으면 추출 불가를 notes로 표면화(날조 금지). sheet_classifier.py의 degrade 패턴과 동일 철학.
"""
from __future__ import annotations

from typing import Protocol

from app.contracts.drawing_extraction import (
    DrawingExtraction,
    DrawingSheet,
    ExtractedElement,
    normalize_semantic_hint,
)
from app.core.confidence import clamp01
from app.settings import env_or_setting, settings


class DrawingVisionClient(Protocol):
    """도면 이미지 → 요소 목록 추출 인터페이스(주입). 실 클라이언트가 구현."""

    def extract_elements(self, image_ref: str, hint_text: str | None) -> list[dict] | None: ...


def _measurements(d: dict) -> dict:
    """제외 산정 측정치 매핑 — 미상 키는 None 유지(무음 추정 금지)."""
    return {
        "length": d.get("length"), "depth": d.get("depth"),
        "underground": d.get("underground"), "accessory": d.get("accessory"),
    }


def _from_hints(sheet: DrawingSheet) -> list[ExtractedElement]:
    out: list[ExtractedElement] = []
    for i, h in enumerate(sheet.element_hints):
        out.append(ExtractedElement(
            element_id=f"{sheet.sheet_id}-h{i}",
            semantic_hint=normalize_semantic_hint(h.get("semantic_hint")),
            hint_strength=clamp01(float(h.get("hint_strength", 0.0) or 0.0)),
            area=h.get("area"),
            quantity=h.get("quantity"),
            **_measurements(h),
            provenance={"sheet": sheet.sheet_id, "src": "hint", "role": sheet.sheet_role},
        ))
    return out


def _from_vision(sheet: DrawingSheet, raw: list[dict]) -> list[ExtractedElement]:
    out: list[ExtractedElement] = []
    for i, r in enumerate(raw):
        out.append(ExtractedElement(
            element_id=f"{sheet.sheet_id}-v{i}",
            semantic_hint=normalize_semantic_hint(r.get("type") or r.get("semantic_hint")),
            hint_strength=clamp01(float(r.get("confidence", 0.0) or 0.0)),
            area=r.get("area"),
            quantity=r.get("quantity"),
            **_measurements(r),
            provenance={"sheet": sheet.sheet_id, "src": "vision", "role": sheet.sheet_role},
        ))
    return out


class DrawingExtractor:
    """도면 시트들 → DrawingExtraction. 결정론(동일 입력 동일 출력), 날조 금지."""

    def __init__(self, vision_client: DrawingVisionClient | None = None) -> None:
        self.vision_client = vision_client

    def extract(self, sheets: list[DrawingSheet]) -> DrawingExtraction:
        elements: list[ExtractedElement] = []
        area_tables: list[dict] = []
        notes: list[str] = []
        used_vision = False
        used_hints = False
        for sh in sheets:
            if sh.area_table and sh.area_table.get("outer_area") is not None:
                area_tables.append({"target": sh.area_table.get("target", "building_area"),
                                    "outer_area": float(sh.area_table["outer_area"]),
                                    "sheet": sh.sheet_id})
            if self.vision_client is not None and sh.image_ref:
                raw = self.vision_client.extract_elements(sh.image_ref, sh.titleblock_text or sh.sheet_role)
                if raw:
                    used_vision = True
                    elements.extend(_from_vision(sh, raw))
                    continue
                notes.append(f"{sh.sheet_id}: 비전 추출 실패/빈 → 힌트 폴백")
            if sh.element_hints:
                used_hints = True
                elements.extend(_from_hints(sh))
            elif not (self.vision_client is not None and sh.image_ref):
                notes.append(f"{sh.sheet_id}: 이미지/힌트 없음 → 추출 불가(날조 금지)")
        source = "VLLM_VISION" if used_vision else ("HINTS" if used_hints else "none")
        return DrawingExtraction(source=source, elements=elements, area_tables=area_tables, notes=notes)


class AnthropicDrawingVisionClient:
    """참조 실 클라이언트(Anthropic vision). lazy httpx + 키 검사. 미가용 시 None(graceful)."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or env_or_setting("ANTHROPIC_API_KEY")
        self.model = model or env_or_setting("VLLM_MODEL") or settings.VLLM_MODEL

    def extract_elements(self, image_ref: str, hint_text: str | None) -> list[dict] | None:
        if not self.api_key:
            return None
        try:
            import httpx
        except ImportError:
            return None
        prompt = (
            "다음 건축 도면 이미지에서 식별 가능한 요소를 JSON 배열로만 추출하라. "
            "각 항목 키: type(PILOTIS/BALCONY/EAVE/BASEMENT/PARKING/CORE_STAIR/EXT_WALL/"
            "PLOT_BOUNDARY/BUILDING_LINE 중 하나, 미상은 UNKNOWN), confidence(0~1), "
            "area(㎡, 알 수 없으면 생략), quantity(개수, 생략 가능). "
            f"표제란/역할 힌트: {hint_text or '(없음)'}."
        )
        from app.adapters.vision.image_source import build_content
        from app.adapters.vision.vision_cache import cache_key, get_or_call
        content = build_content(image_ref, prompt)  # 이미지면 멀티모달 [image, text]

        def _call() -> list[dict] | None:
            try:
                resp = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                    json={"model": self.model, "max_tokens": 1024, "temperature": 0,  # 결정론(샘플링 제거)
                          "messages": [{"role": "user", "content": content}]},
                    timeout=40.0,
                )
                resp.raise_for_status()
                text = resp.json()["content"][0]["text"]
                import json as _json
                parsed = _json.loads(text[text.find("["): text.rfind("]") + 1])
                return parsed if isinstance(parsed, list) else None
            except Exception:
                return None  # 라이브 실패 → degrade(상위가 힌트 폴백/결손 처리)
        # 동일 도면 재분석 시 캐시 적중 → 재현성·비용절감(temperature=0과 함께 INV-1 복원).
        return get_or_call(cache_key(self.model, image_ref, prompt), _call)


def build_drawing_extractor(vision_client: DrawingVisionClient | None = None) -> DrawingExtractor:
    """설정 기반 도면 추출기 팩토리. 기본=힌트 폴백(결정론). SHEET_CLASSIFIER=vllm 시 실 비전."""
    if env_or_setting("SHEET_CLASSIFIER") == "vllm":
        client = vision_client or AnthropicDrawingVisionClient()
        return DrawingExtractor(vision_client=client)
    return DrawingExtractor(vision_client=vision_client)
