"""매각/분양 서비스."""
from typing import Dict, List


class SalesService:
    """부동산 매각 + ROI 분석 + 시장 타이밍."""

    def record_sale(self, unit_data: dict, sale_details: dict) -> dict:
        return {
            "unit_id": unit_data.get("unit_id", ""),
            "sale_type": sale_details.get("sale_type", "outright"),
            "sale_price": sale_details.get("price", 0),
            "sale_date": sale_details.get("date", "2025-06-01"),
            "buyer_type": sale_details.get("buyer_type", "individual"),
            "commission_pct": sale_details.get("commission_pct", 0.5),
        }

    def calculate_roi(self, purchase_price: float, sale_price: float,
                      holding_years: float, total_costs: float = 0) -> dict:
        net_profit = sale_price - purchase_price - total_costs
        roi = (net_profit / purchase_price * 100) if purchase_price > 0 else 0
        annual_roi = roi / holding_years if holding_years > 0 else roi
        return {
            "purchase_price": purchase_price, "sale_price": sale_price,
            "net_profit": round(net_profit), "roi_pct": round(roi, 2),
            "annual_roi_pct": round(annual_roi, 2),
        }

    def analyze_market_timing(self, price_history: list[dict]) -> dict:
        if len(price_history) < 2:
            return {"recommendation": "hold", "price_change_pct": 0, "trend": "insufficient_data"}
        first = price_history[0].get("price", 0)
        last = price_history[-1].get("price", 0)
        change = ((last - first) / first * 100) if first > 0 else 0
        if change > 10:
            rec = "sell"
        elif change < -5:
            rec = "hold"
        else:
            rec = "monitor"
        return {"recommendation": rec, "price_change_pct": round(change, 1), "trend": "up" if change > 0 else "down"}

    def generate_settlement(self, sale_data: dict) -> dict:
        gross = sale_data.get("sale_price", 0)
        commission = gross * sale_data.get("commission_pct", 0.5) / 100
        tax = gross * 0.06
        return {
            "gross_price": gross, "commission": round(commission),
            "tax": round(tax), "net_proceeds": round(gross - commission - tax),
        }
