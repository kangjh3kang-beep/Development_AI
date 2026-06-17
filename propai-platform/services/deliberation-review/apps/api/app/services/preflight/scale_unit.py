"""R0 — 축척/단위 확정(ScaleUnitResolver). fallback chain, 전 chain 실패 시 진행 거부.

치수엔티티 역산 > 축척표기 > 사용자입력 > 공부 대지면적 역검증. 전부 실패 → PreflightRefused(INV-5).
축척 분모는 입력에서 산출(코드 하드코딩 금지).
"""
from __future__ import annotations

from app.contracts.enums import ScaleSource
from app.contracts.preflight import ScaleResult
from app.core.errors import PreflightRefused


class ScaleUnitResolver:
    def resolve(self, drawing: dict | None) -> ScaleResult:
        d = drawing or {}

        if d.get("dim_entities"):
            denom = self._from_dimensions(d["dim_entities"])
            if denom is not None:
                return ScaleResult(
                    scale_denominator=denom, source=ScaleSource.DIMENSION, assumed=False
                )

        if d.get("scale_text"):
            denom = self._parse_scale_text(d["scale_text"])
            if denom is not None:
                return ScaleResult(
                    scale_denominator=denom, source=ScaleSource.NOTATION, assumed=False
                )

        if d.get("user_scale"):
            return ScaleResult(
                scale_denominator=float(d["user_scale"]),
                source=ScaleSource.USER,
                assumed=True,
            )

        if d.get("cadastral_area"):
            denom = self._cross_check(d)
            if denom is not None:
                return ScaleResult(
                    scale_denominator=denom,
                    source=ScaleSource.CADASTRAL_CROSSCHECK,
                    assumed=True,
                )

        raise PreflightRefused(
            "scale unresolved: no dimension/notation/user/cadastral evidence"
        )

    @staticmethod
    def _from_dimensions(dim_entities: dict) -> float | None:
        """모형길이/도면길이 비로 축척 역산. 결손이면 None."""
        paper = dim_entities.get("paper_length")
        model = dim_entities.get("model_length")
        if not paper or not model:
            return None
        return float(model) / float(paper)

    @staticmethod
    def _parse_scale_text(text: str) -> float | None:
        """'1:100' → 100.0. 형식 불일치면 None."""
        if ":" not in text:
            return None
        try:
            return float(text.split(":", 1)[1].strip())
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _cross_check(drawing: dict) -> float | None:
        """공부 대지면적 대비 도면 면적 역검증(후속 페이즈에서 정밀화)."""
        cadastral = drawing.get("cadastral_area")
        drawn = drawing.get("drawn_area")
        if not cadastral or not drawn:
            return None
        return (float(cadastral) / float(drawn)) ** 0.5
