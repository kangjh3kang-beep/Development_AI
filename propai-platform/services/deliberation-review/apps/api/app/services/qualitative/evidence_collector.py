"""L3-C — 정성 평가 입력 수집. 기존 계층 산출(R0.5 요소분류/R1.5 산정/L3-B 시뮬) 재사용.

새 사실 생성 금지(INV-31 정신) — 모든 fact는 기존 계층 출처(source_layer)를 동반.
"""
from __future__ import annotations

from pydantic import BaseModel

# 정성 평가가 참조 가능한 기존 산출 계층(새 사실 생성 금지).
EXISTING_LAYERS = ("R0.5", "R1.5", "L3-B")


class Fact(BaseModel):
    fact_id: str
    feature: str
    value: object | None = None
    source_layer: str


class EvidenceCollector:
    def collect(self, project: dict) -> list[Fact]:
        facts: list[Fact] = []
        for el in project.get("semantic_elements", []):
            facts.append(Fact(fact_id=f"se-{el.get('element_id')}", feature=el.get("semantic_type", ""),
                              value=el, source_layer="R0.5"))
        for q in project.get("legal_quantities", []):
            facts.append(Fact(fact_id=f"lq-{q.get('variable_id')}", feature=q.get("variable_id", ""),
                              value=q.get("value"), source_layer="R1.5"))
        for m in project.get("sim_metrics", []):
            facts.append(Fact(fact_id=f"sm-{m.get('metric_id')}", feature=m.get("metric_id", ""),
                              value=m.get("value"), source_layer="L3-B"))
        return facts
