"""계약 관리 서비스."""
from typing import Dict, List


class ContractService:
    """공사 계약 + 기성금 지급 스케줄 관리."""

    def create_contract(self, project_id: str, contract_type: str, details: Dict) -> Dict:
        return {
            "project_id": project_id,
            "contract_type": contract_type,
            "contractor_name": details.get("contractor_name", ""),
            "amount": details.get("amount", 0),
            "status": "draft",
        }

    def schedule_payments(self, total_amount: float, milestones: List[Dict]) -> List[Dict]:
        payments = []
        for m in milestones:
            pct = m.get("pct", 0)
            amount = int(total_amount * pct / 100)
            payments.append({
                "name": m.get("name", ""),
                "pct": pct,
                "amount": amount,
                "due_date": m.get("due_date", ""),
                "status": "scheduled",
            })
        return payments
