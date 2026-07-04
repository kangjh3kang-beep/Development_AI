"""특수 프로젝트 (재건축/리모델링) 서비스."""


class SpecialProjectService:
    """재건축 적격성 평가 + 리모델링 계획."""

    SAFETY_GRADES = {
        "A": "양호", "B": "경미한 손상", "C": "보통",
        "D": "상당한 손상", "E": "위험",
    }

    def evaluate_reconstruction(self, building_data: dict) -> dict:
        age = building_data.get("age_years", 30)
        grade = building_data.get("safety_grade", "D")
        eligible = age >= 30 and grade in ("D", "E")
        action = "재건축 추진" if eligible else "유지보수 권고"
        return {
            "age_years": age, "safety_grade": grade,
            "grade_description": self.SAFETY_GRADES.get(grade, ""),
            "recommended_action": action,
            "reconstruction_eligible": eligible,
            "legal_basis": "도시 및 주거환경정비법 제2조",
        }

    def plan_remodeling(self, project_data: dict, scope: str) -> dict:
        area = project_data.get("area_sqm", 1000)
        costs = {"interior": 800_000, "structural": 2_000_000, "exterior": 1_200_000}
        timelines = {"interior": 3, "structural": 12, "exterior": 6}
        cost_per_sqm = costs.get(scope, 1_000_000)
        return {
            "scope": scope, "estimated_cost": area * cost_per_sqm,
            "timeline_months": timelines.get(scope, 6), "area_sqm": area,
        }

    def estimate_special_costs(self, project_type: str, area_sqm: float) -> dict:
        rates = {"reconstruction": 3_500_000, "remodeling": 1_500_000, "maintenance": 500_000}
        cost_per_sqm = rates.get(project_type, 2_000_000)
        return {
            "project_type": project_type, "area_sqm": area_sqm,
            "cost_per_sqm": cost_per_sqm, "total_cost": area_sqm * cost_per_sqm,
        }

    def track_approval(self, approval_data: dict) -> dict:
        total = approval_data.get("total_steps", 5)
        completed = approval_data.get("completed_steps", 0)
        return {
            "total_steps": total, "completed_steps": completed,
            "progress_pct": round(completed / total * 100, 1) if total > 0 else 0,
            "current_step": approval_data.get("current_step", "접수"),
        }
