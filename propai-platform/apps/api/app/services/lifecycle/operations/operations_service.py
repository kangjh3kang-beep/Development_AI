"""운영 관리 서비스."""
from datetime import UTC, datetime


class OperationsService:
    """건물 운영 로그 + 점검 + 비용 관리."""

    def log_operation(self, project_id: str, log_type: str, details: dict) -> dict:
        return {
            "project_id": project_id,
            "log_type": log_type,
            "description": details.get("description", ""),
            "performed_by": details.get("performed_by", "system"),
            "performed_at": datetime.now(UTC).isoformat(),
            "cost": details.get("cost", 0),
        }

    def schedule_inspections(self, components: list[dict]) -> list[dict]:
        return [
            {
                "component": c.get("component", ""),
                "inspection_type": c.get("type", "regular"),
                "frequency": c.get("interval_months", 6),
                "next_date": datetime.now(UTC).isoformat(),
            }
            for c in components
        ]

    def calculate_operating_costs(self, logs: list[dict]) -> dict:
        total = sum(log.get("cost", 0) for log in logs)
        by_type: dict[str, float] = {}
        for log in logs:
            lt = log.get("log_type", "other")
            by_type[lt] = by_type.get(lt, 0) + log.get("cost", 0)
        return {"total_cost": total, "by_type": by_type, "log_count": len(logs)}

    def generate_operations_report(self, project_id: str, logs: list[dict]) -> dict:
        costs = self.calculate_operating_costs(logs)
        incidents = sum(1 for log in logs if log.get("log_type") == "incident")
        return {
            "project_id": project_id, "report_type": "operations",
            "period": "monthly", "costs": costs, "incident_count": incidents,
        }
