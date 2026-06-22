"""basis_article 법령 본문 해소(resolve_text) + reg_graph ARTICLE 노드 설명가능성."""
from app.contracts.reg_graph import NodeKind
from app.contracts.rule import Rule
from app.services.explain.legal_refs import resolve_text
from app.services.reg_graph.builder import build_reg_graph


def test_resolve_text_exact_and_law_level():
    # 정확 키 → exact + 조문 본문.
    ex = resolve_text("국토계획법시행령§85")
    assert ex["match"] == "exact" and "용적률" in ex["summary"]
    # 거친 형식(조문번호 없는 법령명) → 법령 수준 해소(조문 미특정).
    law = resolve_text("국토계획법 시행령")
    assert law["match"] == "law_level" and law["law"].startswith("국토")
    bd = resolve_text("건축법 제46조/도시계획")
    assert bd["match"] == "law_level" and bd["ref_id"] == "건축법"
    # 미해소 → None(소비측에서 '본문 미해소'로 표면화).
    assert resolve_text("존재하지않는법령") is None
    assert resolve_text(None) is None


def test_reg_graph_article_resolved():
    rules = [
        Rule(rule_id="far_limit", target_variable="far_floor_area", basis_article="국토계획법 시행령"),
        Rule(rule_id="height_limit", target_variable="building_height", basis_article="건축법 시행령"),
    ]
    g = build_reg_graph(rules)
    arts = g.nodes_of_kind(NodeKind.ARTICLE)
    assert arts  # ARTICLE 노드 존재
    for a in arts:
        # 거친 basis_article도 법령 본문(summary)·출처 동반(ID만 흐르던 결손 해소).
        assert a.summary and a.source and a.resolved in ("exact", "law_level")
