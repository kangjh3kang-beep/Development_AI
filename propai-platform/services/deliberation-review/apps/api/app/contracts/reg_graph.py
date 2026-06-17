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
