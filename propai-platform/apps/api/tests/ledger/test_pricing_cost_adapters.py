"""Phase 1: pricing/cost 산출 → 원장 payload 순수매퍼(W1 미배선 합류)."""
from app.services.ledger.ledger_adapters import cost_estimate_to_ledger, pricing_revenue_to_ledger


def test_pricing_revenue_payload():
    out = pricing_revenue_to_ledger(
        {"round_id": "r1", "units_priced": 40, "total_revenue_10k": 120000, "avg_unit_10k": 3000,
         "by_type": {"84A": {"count": 20, "total_10k": 60000}}}, round_id="r1")
    assert out["kind"] == "sales_revenue"
    assert out["schema_version"] == "sales_revenue/v1"
    assert out["round_id"] == "r1"
    assert any(f["check_id"] == "TOTAL_REVENUE" for f in out["findings_brief"])


def test_cost_estimate_payload():
    out = cost_estimate_to_ledger(
        summary={"direct": 100, "indirect": 30, "total": 130, "confidence_grade": "B"},
        header={"building_type": "공동주택", "structure_type": "RC", "total_gfa_sqm": 5000.0},
        estimate_id="e1")
    assert out["kind"] == "cost_estimate"
    assert out["estimate_id"] == "e1"
    assert any(f["check_id"] == "TOTAL_COST" for f in out["findings_brief"])
