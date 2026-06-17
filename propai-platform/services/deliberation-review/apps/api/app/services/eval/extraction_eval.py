"""P4 — 추출 평가 러너. 골든셋 대비 시트역할/요소분류 정확도(정확도·유형별·불일치) 산출.

결정론(LLM 미사용 mock 추출 기준). 골든셋 = 품질 회귀 바(엔진이 통과해야 함).
"""
from __future__ import annotations

import json
import pathlib
from collections.abc import Callable

from app.contracts.eval import EvalReport, GoldenItem
from app.services.element.element_classifier import ElementClassifier
from app.services.sheet.sheet_role_resolver import SheetRoleResolver

_GOLDEN_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "eval" / "golden_set.json"


def evaluate(kind: str, golden: list[GoldenItem], predict: Callable[[dict], str]) -> EvalReport:
    correct = 0
    per_type: dict[str, dict] = {}
    mismatches: list[dict] = []
    for g in golden:
        predicted = predict(g.input)
        bucket = per_type.setdefault(g.expected, {"total": 0, "correct": 0})
        bucket["total"] += 1
        if predicted == g.expected:
            correct += 1
            bucket["correct"] += 1
        else:
            mismatches.append({"item_id": g.item_id, "expected": g.expected, "predicted": predicted})
    total = len(golden)
    for bucket in per_type.values():
        bucket["accuracy"] = round(bucket["correct"] / bucket["total"], 4) if bucket["total"] else 0.0
    return EvalReport(
        kind=kind, total=total, correct=correct,
        accuracy=round(correct / total, 4) if total else 0.0,
        per_type=per_type, mismatches=mismatches,
    )


def _predict_sheet_role(inp: dict) -> str:
    a = SheetRoleResolver().resolve(inp)
    return a.role.value if a.role is not None else "NONE"


def _predict_element(inp: dict) -> str:
    els = ElementClassifier().classify({"elements": [inp]})
    return els[0].semantic_type.value if els else "NONE"


def run_eval(golden_path: pathlib.Path | None = None) -> dict[str, EvalReport]:
    data = json.loads((golden_path or _GOLDEN_PATH).read_text(encoding="utf-8"))
    return {
        "sheet_role": evaluate(
            "sheet_role", [GoldenItem(**g) for g in data.get("sheet_role", [])], _predict_sheet_role
        ),
        "element": evaluate(
            "element", [GoldenItem(**g) for g in data.get("element", [])], _predict_element
        ),
    }
