"""INC-2 — 룰/지표 id → 사람친화 라벨(title/recommendation). 결정론 룰→라벨(LLM 미사용).

비전문가 가독성·설명가능성. 라벨은 data/rule_labels.json 주입(INV-3, 코드 리터럴 0). 미등록 id는
None 반환 → 소비측이 item_id 폴백(무음 날조 금지 — 없는 라벨을 지어내지 않음).
"""
from __future__ import annotations

import json
import pathlib

_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "rule_labels.json"
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        raw = json.loads(_PATH.read_text(encoding="utf-8"))
        _cache = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _cache


def label_for(item_id: str | None) -> dict | None:
    """item_id(rule_id/metric_id) → {title, recommendation} 또는 None(미등록)."""
    if not item_id:
        return None
    return _load().get(item_id)
