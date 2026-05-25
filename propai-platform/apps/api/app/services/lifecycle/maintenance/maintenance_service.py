"""유지보수 관리 서비스."""
from datetime import datetime, timezone
from typing import Dict, List


class MaintenanceService:
    """건물 유지보수 계획 + 실행 + 비용 추적."""

    DEFAULT_COMPONENTS = [
        {"component": "엘리베이터", "interval_months": 3, "priority": "high"},
        {"component": "소방설비", "interval_months": 6, "priority": "high"},
        {"component": "공조설비", "interval_months": 6, "priority": "medium"},
        {"component": "외벽", "interval_months": 60, "priority": "low"},
        {"component": "방수", "interval_months": 120, "priority": "medium"},
    ]

    def create_plan(self, project_id: str, components: List[Dict] = None) -> Dict:
        comps = components or self.DEFAULT_COMPONENTS
        return {"project_id": project_id, "components": comps, "total_components": len(comps)}

    def schedule_maintenance(self, plan: Dict) -> List[Dict]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            {**c, "next_due": now}
            for c in plan.get("components", [])
        ]

    def record_maintenance(self, record: Dict) -> Dict:
        return {
            "component": record.get("component", ""),
            "performed_at": datetime.now(timezone.utc).isoformat(),
            "cost": record.get("cost", 0),
            "status": "completed",
        }

    def calculate_costs(self, records: List[Dict], period_months: int = 12) -> Dict:
        total = sum(r.get("cost", 0) for r in records)
        monthly = total / period_months if period_months > 0 else 0
        return {
            "total_cost": total, "period_months": period_months,
            "monthly_avg": round(monthly), "record_count": len(records),
        }
