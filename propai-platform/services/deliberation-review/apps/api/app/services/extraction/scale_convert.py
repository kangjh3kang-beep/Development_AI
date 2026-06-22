"""INC-4 — 도면 픽셀/도면단위 측정치 → 실척 결정론 환산(축척 결합).

비전/벡터가 픽셀·도면단위로 area_px/length_px를 줄 때, 축척 분모(scale_denominator)로 실척
면적/길이를 결정론적으로 환산한다(area = area_px × denom², length = length_px × denom).
축척이 assumed(USER/CADASTRAL 역검증)이면 환산 결과의 신뢰가 제한됨을 provenance로 표면화(무음0).
축척 미확정(scale None)이면 무변환(픽셀값 그대로 두고 산정 미승계 — 날조 금지).
"""
from __future__ import annotations

from app.contracts.drawing_extraction import DrawingExtraction
from app.contracts.preflight import ScaleResult


def real_area(area_drawing: float, scale_denominator: float) -> float:
    """도면단위 면적 → 실척 면적(분모² 배). 결정론."""
    return float(area_drawing) * (float(scale_denominator) ** 2)


def real_length(length_drawing: float, scale_denominator: float) -> float:
    """도면단위 길이 → 실척 길이(분모 배). 결정론."""
    return float(length_drawing) * float(scale_denominator)


def apply_scale(ext: DrawingExtraction, scale: ScaleResult | None) -> DrawingExtraction:
    """추출요소의 픽셀단위 측정치를 실척으로 환산(실척 area/length가 비어 있을 때만). scale 없으면 무변환."""
    if scale is None:
        return ext
    denom = scale.scale_denominator
    for e in ext.elements:
        converted = False
        if e.area is None and e.area_px is not None:
            e.area = round(real_area(e.area_px, denom), 4)
            converted = True
        if e.length is None and e.length_px is not None:
            e.length = round(real_length(e.length_px, denom), 4)
            converted = True
        if converted:
            e.provenance["scale_denominator"] = denom
            e.provenance["scale_source"] = scale.source.value
            if scale.assumed:  # 가정 축척 — 환산 신뢰 제한 표면화(무음0)
                e.provenance["scale_assumed"] = True
    return ext
