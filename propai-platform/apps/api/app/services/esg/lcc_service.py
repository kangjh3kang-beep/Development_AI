import structlog

logger = structlog.get_logger()

class LCCService:
    """LCC 생애주기비용 분석 (ISO 15686-5:2017)"""

    def calculate_lcc(self, construction_cost_krw: float = 0, annual_maintenance_krw: float = 0,
                      annual_energy_krw: float = 0, lifecycle_years: int = 50,
                      discount_rate: float = 0.03, inflation_rate: float = 0.02,
                      **kwargs) -> dict:
        if isinstance(construction_cost_krw, dict):
            d = construction_cost_krw
            construction_cost_krw = d.get("initial_cost_krw", d.get("construction_cost_krw", 0))
            annual_maintenance_krw = d.get("annual_maintenance_krw", annual_maintenance_krw)
            annual_energy_krw = d.get("annual_energy_krw", annual_energy_krw)
            lifecycle_years = d.get("analysis_period_years", d.get("lifecycle_years", lifecycle_years))
            discount_rate = d.get("discount_rate_nominal", d.get("discount_rate", discount_rate))
            inflation_rate = d.get("inflation_rate", inflation_rate)

        real_discount_rate = (1 + discount_rate) / (1 + inflation_rate) - 1
        pv_maintenance = pv_energy = pv_replacement = 0.0
        yearly_cashflow = {}
        for t in range(1, lifecycle_years + 1):
            df = 1 / ((1 + real_discount_rate) ** t)
            pv_maintenance += annual_maintenance_krw * df
            pv_energy += annual_energy_krw * df
            if t in [15, 25, 35, 45]:
                replacement = construction_cost_krw * 0.05
                pv_replacement += replacement * df
            yearly_cashflow[t] = {"maintenance": annual_maintenance_krw,
                                  "energy": annual_energy_krw, "pv_factor": round(df, 6)}
        total_lcc = construction_cost_krw + pv_maintenance + pv_energy + pv_replacement
        return {
            "construction_cost_krw": int(construction_cost_krw),
            "pv_maintenance_krw": int(pv_maintenance),
            "maintenance_npv_krw": int(pv_maintenance),
            "pv_energy_krw": int(pv_energy),
            "pv_replacement_krw": int(pv_replacement),
            "total_lcc_krw": int(total_lcc),
            "total_lcc_npv_krw": int(total_lcc),
            "lifecycle_years": lifecycle_years,
            "real_discount_rate": round(real_discount_rate, 4),
            "standard": "ISO 15686-5:2017",
            "formula": "LCC = sum(C_t/(1+d)^t)"
        }
