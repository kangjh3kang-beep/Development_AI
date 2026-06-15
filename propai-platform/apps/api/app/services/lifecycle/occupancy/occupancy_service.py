"""입주/임대 관리 서비스."""
from typing import Dict, List


class OccupancyService:
    """입주자 관리 + 임대 + 공실률 추적."""

    def register_tenant(self, unit_id: str, tenant_data: dict) -> dict:
        return {
            "unit_id": unit_id,
            "tenant_name": tenant_data.get("name", ""),
            "lease_start": tenant_data.get("lease_start", "2025-01-01"),
            "lease_end": tenant_data.get("lease_end", "2026-12-31"),
            "monthly_rent": tenant_data.get("monthly_rent", 1_000_000),
            "deposit": tenant_data.get("deposit", 10_000_000),
            "status": "active",
        }

    def manage_lease(self, lease: dict, action: str) -> dict:
        result = {**lease}
        if action == "renew":
            result["status"] = "renewed"
        elif action == "terminate":
            result["status"] = "terminated"
        elif action == "extend":
            result["status"] = "extended"
        return result

    def calculate_occupancy_rate(self, units: list[dict]) -> dict:
        total = len(units)
        occupied = sum(1 for u in units if u.get("status") in ("occupied", "active"))
        vacant = total - occupied
        rate = (occupied / total * 100) if total > 0 else 0
        return {
            "total_units": total, "occupied": occupied, "vacant": vacant,
            "occupancy_rate": round(rate, 1), "vacancy_rate": round(100 - rate, 1),
        }

    def track_rent_collection(self, payments: list[dict]) -> dict:
        total_due = sum(p.get("due", 0) for p in payments)
        total_paid = sum(p.get("paid", 0) for p in payments)
        outstanding = total_due - total_paid
        rate = (total_paid / total_due * 100) if total_due > 0 else 100
        return {
            "total_due": total_due, "total_paid": total_paid,
            "outstanding": outstanding, "collection_rate": round(rate, 1),
        }
