"""R0.5 — 시트 분류기 어댑터(YOLOv8 자리). 인터페이스 + dev mock.

실제 모델 추론은 후속 페이즈에서 동일 인터페이스로 주입. mock은 입력의 classifier_role 신호 반환.
"""
from __future__ import annotations

from typing import Protocol


class SheetClassifierAdapter(Protocol):
    def classify(self, sheet: dict) -> str | None: ...


class MockSheetClassifier:
    def classify(self, sheet: dict) -> str | None:
        return sheet.get("classifier_role")
