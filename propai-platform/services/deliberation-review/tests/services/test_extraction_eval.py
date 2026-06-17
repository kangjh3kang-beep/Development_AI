"""P4 — 추출 평가: 산식 정확성(불일치/유형별) + 골든셋 회귀 바(엔진 통과)."""
from app.contracts.eval import GoldenItem
from app.services.eval.extraction_eval import evaluate, run_eval


def test_evaluate_math_with_mismatch():
    golden = [
        GoldenItem(item_id="a", kind="t", input={"v": "X"}, expected="X"),
        GoldenItem(item_id="b", kind="t", input={"v": "X"}, expected="X"),
        GoldenItem(item_id="c", kind="t", input={"v": "Y"}, expected="X"),  # predict=Y, expected X → 불일치
        GoldenItem(item_id="d", kind="t", input={"v": "X"}, expected="Z"),  # predict=X, expected Z → 불일치
    ]
    rep = evaluate("t", golden, predict=lambda inp: inp["v"])
    assert rep.total == 4 and rep.correct == 2
    assert rep.accuracy == 0.5
    assert {m["item_id"] for m in rep.mismatches} == {"c", "d"}
    assert rep.per_type["X"]["accuracy"] == round(2 / 3, 4)


def test_golden_set_regression_bar():
    reports = run_eval()
    # 골든셋 회귀 바: mock 추출이 골든셋을 전부 통과해야 함(정확도 1.0).
    assert reports["sheet_role"].total >= 4
    assert reports["sheet_role"].accuracy == 1.0, reports["sheet_role"].mismatches
    assert reports["element"].total >= 3
    assert reports["element"].accuracy == 1.0, reports["element"].mismatches
