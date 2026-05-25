from typing import Dict, List
import structlog

logger = structlog.get_logger()

class RiskService:
    """AI 리스크 등급화 (ISO 31000:2018) Risk = P * I * E"""

    RISK_MATRIX = {
        "허가 지연": {"likelihood": 0.6, "impact": 0.8, "category": "인허가"},
        "공사비 초과": {"likelihood": 0.5, "impact": 0.9, "category": "원가"},
        "공정 지연": {"likelihood": 0.4, "impact": 0.7, "category": "공정"},
        "부동산 시장 침체": {"likelihood": 0.3, "impact": 0.9, "category": "시장"},
        "금리 상승": {"likelihood": 0.4, "impact": 0.8, "category": "금융"},
        "자재 수급 불안": {"likelihood": 0.3, "impact": 0.6, "category": "자재"},
        "안전사고 발생": {"likelihood": 0.2, "impact": 1.0, "category": "안전"},
        "법규 변경": {"likelihood": 0.2, "impact": 0.7, "category": "법규"},
        "민원 발생": {"likelihood": 0.4, "impact": 0.5, "category": "민원"},
        "자연재해": {"likelihood": 0.1, "impact": 0.9, "category": "환경"},
    }

    def calculate_risk_scores(self) -> Dict:
        risks = []
        for risk_name, params in self.RISK_MATRIX.items():
            score = params["likelihood"] * params["impact"]
            level = "critical" if score > 0.6 else "high" if score > 0.4 else "medium" if score > 0.2 else "low"
            risks.append({
                "risk_name": risk_name, "category": params["category"],
                "likelihood": params["likelihood"], "impact": params["impact"],
                "risk_score": round(score, 3), "risk_level": level,
            })
        risks.sort(key=lambda x: x["risk_score"], reverse=True)
        return {
            "total_risks": len(risks),
            "critical_count": len([r for r in risks if r["risk_level"] == "critical"]),
            "high_count": len([r for r in risks if r["risk_level"] == "high"]),
            "risks": risks, "standard": "ISO 31000:2018"
        }
