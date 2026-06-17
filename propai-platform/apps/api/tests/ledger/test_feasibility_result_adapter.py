"""Phase 1: feasibility 수지결과 → 원장 payload 순수매퍼."""
from app.services.ledger.ledger_adapters import feasibility_result_to_ledger


def test_feasibility_result_payload_shape():
    out = feasibility_result_to_ledger({
        "development_type": "다세대", "total_revenue_won": 5_000_000_000,
        "net_profit_won": 800_000_000, "profit_rate_pct": 16.0, "npv_won": 600_000_000, "grade": "B",
    })
    assert out["kind"] == "feasibility"
    assert out["schema_version"] == "feasibility/v1"
    assert out["grade"] == "B"
    assert out["net_profit_won"] == 800_000_000
    # 비교핵심 findings_brief 존재
    assert any(f["check_id"] == "PROFIT_RATE" for f in out["findings_brief"])
