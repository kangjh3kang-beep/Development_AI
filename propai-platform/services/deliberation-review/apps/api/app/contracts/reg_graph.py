"""P3 — 규제 지식그래프 계약. 조문↔룰↔변수↔완화를 노드/엣지로(학술 KG 정합).

근거추적(어느 조문이 어느 룰을 ground, 룰이 어느 변수/완화를 touch)을 질의 가능 그래프로.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NodeKind(str, Enum):
    ARTICLE = "ARTICLE"
    RULE = "RULE"
    VARIABLE = "VARIABLE"
    RELAXATION = "RELAXATION"


class RegNode(BaseModel):
    id: str
    kind: NodeKind
    label: str | None = None
    # ARTICLE 노드 법령 해소(설명가능성, legal_refs). 미해소 시 resolved=None(label만 — 표면화).
    law: str | None = None
    article: str | None = None
    summary: str | None = None
    effective_date: str | None = None
    source: str | None = None
    resolved: str | None = None  # exact | law_level | None
    # VARIABLE 노드: 용도지역에서 독립 해소한 국가 규제 상한(입력 echo 아님·데이터파일/미러 1차출처). 플랫폼 한도 divergence 관측원(P5).
    limit_value: float | None = None
    limit_unit: str | None = None   # 예: "%"
    limit_source: str | None = None  # 예: "국토계획법 시행령 §85 상한:제2종일반주거지역"


class RegEdge(BaseModel):
    src: str
    dst: str
    rel: str  # GROUNDS(art→rule) | TARGETS(rule→var) | RELAXES(rule→relax) | REQUIRES(relax→rule)


class RegGraph(BaseModel):
    nodes: list[RegNode] = Field(default_factory=list)
    edges: list[RegEdge] = Field(default_factory=list)

    def nodes_of_kind(self, kind: NodeKind) -> list[RegNode]:
        return [n for n in self.nodes if n.kind == kind]

    def out_edges(self, node_id: str, rel: str | None = None) -> list[RegEdge]:
        return [e for e in self.edges if e.src == node_id and (rel is None or e.rel == rel)]

    def in_edges(self, node_id: str, rel: str | None = None) -> list[RegEdge]:
        return [e for e in self.edges if e.dst == node_id and (rel is None or e.rel == rel)]

    def rules_for_article(self, article: str) -> list[str]:
        return [e.dst for e in self.out_edges(f"art:{article}", "GROUNDS")]

    def articles_for_rule(self, rule_id: str) -> list[str]:
        return [e.src for e in self.in_edges(f"rule:{rule_id}", "GROUNDS")]

    def relaxations_for_rule(self, rule_id: str) -> list[str]:
        return [e.dst for e in self.out_edges(f"rule:{rule_id}", "RELAXES")]
