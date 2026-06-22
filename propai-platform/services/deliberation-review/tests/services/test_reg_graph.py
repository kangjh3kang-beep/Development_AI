"""P3 — 규제 지식그래프: 노드/엣지 구성·질의(조문↔룰↔변수↔완화)·파이프라인 배선."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.contracts.reg_graph import NodeKind
from app.contracts.rule import Relaxation, Rule
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.reg_graph.builder import build_reg_graph

_RULES = [
    Rule(rule_id="far_limit", target_variable="far_floor_area", basis_article="국토계획법 시행령",
         relaxations=[Relaxation(relaxation_id="far_relax", prerequisite_rule_id="public_space")]),
    Rule(rule_id="height_limit", target_variable="building_height", basis_article="건축법 시행령"),
]


def test_graph_nodes_and_edges():
    g = build_reg_graph(_RULES)
    kinds = {n.kind for n in g.nodes}
    assert NodeKind.RULE in kinds and NodeKind.VARIABLE in kinds
    assert NodeKind.ARTICLE in kinds and NodeKind.RELAXATION in kinds
    rels = {e.rel for e in g.edges}
    assert {"GROUNDS", "TARGETS", "RELAXES", "REQUIRES"} <= rels


def test_graph_queries():
    g = build_reg_graph(_RULES)
    assert "rule:far_limit" in g.rules_for_article("국토계획법 시행령")
    assert "art:건축법 시행령" in g.articles_for_rule("height_limit")
    assert "relax:far_relax" in g.relaxations_for_rule("far_limit")


def test_variable_node_gets_national_limit_when_zone_given():
    # P5 — use_zone 제공 시 VARIABLE 노드에 데이터파일 1차출처 국가 상한 부착(입력 limit echo 아님).
    g = build_reg_graph(_RULES, use_zone="제2종일반주거지역")
    far_var = next(n for n in g.nodes if n.id == "var:far_floor_area")
    assert far_var.limit_value == 250.0 and far_var.limit_unit == "%"
    assert "시행령" in (far_var.limit_source or "")
    h_var = next(n for n in g.nodes if n.id == "var:building_height")  # 국가상한 비대상 → 미부착
    assert h_var.limit_value is None


def test_variable_node_no_limit_without_zone():
    g = build_reg_graph(_RULES)  # zone 미제공 → 한도 미부착(기존 동작 보존·결정론)
    assert next(n for n in g.nodes if n.id == "var:far_floor_area").limit_value is None


def test_pipeline_reg_graph_wired():
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1), drawing={"scale_text": "1:100"},
        rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                         "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
        mirror_rules=[{"ref": "건축법 시행령"}],
    ))
    assert r.reg_graph is not None
    assert any(n.kind == NodeKind.ARTICLE for n in r.reg_graph.nodes)
    assert "rule:far_limit" in r.reg_graph.rules_for_article("국토계획법 시행령")
