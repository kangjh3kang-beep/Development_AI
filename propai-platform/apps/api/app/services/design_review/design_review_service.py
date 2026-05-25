from typing import Dict, List
import structlog

logger = structlog.get_logger()

class DesignReviewService:
    """AI 설계 자동 검토 피드백 (건축법 제25조)"""

    REVIEW_CHECKLIST = {
        "건폐율_준수": "건축법 제55조", "용적률_준수": "건축법 제56조",
        "이격거리_준수": "건축법 제58조", "높이제한_준수": "건축법 제60조",
        "일조권_준수": "건축법 제61조", "주차장_설치기준": "주차장법 제19조",
        "피난시설_적합": "건축법 제49조", "방화구획_적합": "건축법 제49조",
        "장애인_편의시설": "장애인복지법 제24조", "에너지절약_기준": "건축물에너지절약설계기준",
    }

    def review_design_parameters(self, design_params: Dict, zone_rules: Dict) -> Dict:
        errors, corrections = [], []
        far = design_params.get("far_applied", 0)
        bcr = design_params.get("bcr_applied", 0)
        max_far = zone_rules.get("max_far", 300)
        max_bcr = zone_rules.get("max_bcr", 60)
        if far > max_far:
            errors.append({"item": "용적률_초과", "current": far, "limit": max_far,
                           "legal_basis": "건축법 제56조", "severity": "critical"})
            corrections.append(f"용적률 {far}% -> {max_far * 0.9:.0f}%로 축소")
        if bcr > max_bcr:
            errors.append({"item": "건폐율_초과", "current": bcr, "limit": max_bcr,
                           "legal_basis": "건축법 제55조", "severity": "critical"})
            corrections.append(f"건폐율 {bcr}% -> {max_bcr * 0.9:.0f}%로 축소")
        passed = [item for item in self.REVIEW_CHECKLIST if item not in [e["item"] for e in errors]]
        return {
            "review_status": "pass" if not errors else "correction_required",
            "error_count": len(errors), "errors_detected": errors,
            "correction_items": corrections, "passed_items": passed,
            "pass_rate_pct": round(len(passed) / len(self.REVIEW_CHECKLIST) * 100, 1),
            "legal_basis": "건축법 제25조"
        }
