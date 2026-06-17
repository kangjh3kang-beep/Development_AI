"""P3 — 규제 지식그래프 빌더. R3 룰(+완화) + R2 미러 룰셋 → RegGraph.

엣지: 조문 GROUNDS 룰, 룰 TARGETS 변수, 룰 RELAXES 완화, 완화 REQUIRES 전제룰.
결정론(동일 입력 동일 그래프). 인용접지(L5)·근거추적(INV-10)과 결합.
"""
from __future__ import annotations

from app.contracts.reg_graph import NodeKind, RegEdge, RegGraph, RegNode
from app.contracts.rule import Rule
from app.services.explain.legal_refs import resolve_text


def build_reg_graph(rules: list[Rule], mirror_rules: list[dict] | None = None) -> RegGraph:
    nodes: dict[str, RegNode] = {}
    edges: list[RegEdge] = []

    def add(node_id: str, kind: NodeKind, label: str | None = None) -> None:
        if node_id in nodes:
            return
        extra: dict = {}
        if kind == NodeKind.ARTICLE and label:  # 조문 ID → 법령 본문 해소(설명가능성)
            r = resolve_text(label)
            if r:
                extra = {"law": r["law"], "article": r["article"], "summary": r["summary"],
                         "effective_date": r.get("effective_date"), "source": r["source"],
                         "resolved": r["match"]}
        nodes[node_id] = RegNode(id=node_id, kind=kind, label=label, **extra)

    for r in rules:
        rid = f"rule:{r.rule_id}"
        add(rid, NodeKind.RULE, r.rule_id)

        if r.target_variable:
            vid = f"var:{r.target_variable}"
            add(vid, NodeKind.VARIABLE, r.target_variable)
            edges.append(RegEdge(src=rid, dst=vid, rel="TARGETS"))

        if r.basis_article:
            aid = f"art:{r.basis_article}"
            add(aid, NodeKind.ARTICLE, r.basis_article)
            edges.append(RegEdge(src=aid, dst=rid, rel="GROUNDS"))

        for relax in r.relaxations:
            xid = f"relax:{relax.relaxation_id}"
            add(xid, NodeKind.RELAXATION, relax.relaxation_id)
            edges.append(RegEdge(src=rid, dst=xid, rel="RELAXES"))
            if relax.prerequisite_rule_id:
                pid = f"rule:{relax.prerequisite_rule_id}"
                add(pid, NodeKind.RULE, relax.prerequisite_rule_id)
                edges.append(RegEdge(src=xid, dst=pid, rel="REQUIRES"))
            if relax.basis_article:
                aid2 = f"art:{relax.basis_article}"
                add(aid2, NodeKind.ARTICLE, relax.basis_article)
                edges.append(RegEdge(src=aid2, dst=xid, rel="GROUNDS"))

    # 미러 룰셋의 조문 출처(검증된 1차출처)도 노드로 결합.
    for mr in mirror_rules or []:
        ref = mr.get("ref")
        if ref:
            add(f"art:{ref}", NodeKind.ARTICLE, ref)

    return RegGraph(nodes=list(nodes.values()), edges=edges)
