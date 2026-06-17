"""AT-4/AT-5 — 룰 순환 의존 crash 금지+위원 degrade, 위상정렬(전제→의존 순)."""
from app.contracts.rule import Rule
from app.services.judge.rule_graph import RuleGraph

CYCLIC_SET = [
    Rule(rule_id="A", depends_on=["B"]),
    Rule(rule_id="B", depends_on=["A"]),
]

DEP_SET = [
    Rule(rule_id="DEPENDENT", depends_on=["PREREQ"]),
    Rule(rule_id="PREREQ"),
]


def test_cyclic_rule_dependency_degrades():
    g = RuleGraph(rules=CYCLIC_SET)
    assert g.has_cycle() is True
    assert g.degraded_to_committee() is True
    assert g.eval_order()  # crash 없이 비차단 반환


def test_topological_eval_order():
    order = RuleGraph(rules=DEP_SET).eval_order()
    assert order.index("PREREQ") < order.index("DEPENDENT")
