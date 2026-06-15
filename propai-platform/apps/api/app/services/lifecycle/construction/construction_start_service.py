from typing import Dict, List
from datetime import datetime
import structlog

logger = structlog.get_logger()

CONSTRUCTION_START_CHECKLIST = [
    {"item": "착공신고서 제출", "law": "건축법 제21조", "required": True},
    {"item": "공사감리 계약 체결", "law": "건축법 제25조", "required": True},
    {"item": "건설공사 안전관리계획서 제출", "law": "건설기술진흥법 제62조", "required": True},
    {"item": "가설울타리 설치", "law": "건설현장 안전기준", "required": True},
    {"item": "공사안전표지판 설치", "law": "산업안전보건법", "required": True},
    {"item": "환경영향평가 이행확인", "law": "환경영향평가법", "required": False},
    {"item": "문화재 지표조사 완료", "law": "문화재보호법 제91조", "required": False},
    {"item": "지하시설물 조사 완료", "law": "지하시설물 안전관리 기준", "required": True},
    {"item": "교통영향평가 이행계획 확인", "law": "도시교통정비 촉진법", "required": False},
    {"item": "품질관리계획서 제출", "law": "건설기술진흥법 제55조", "required": True},
]

class ConstructionStartService:
    """AI 착공 지원 (건축법 제21조 + 건설기술진흥법 제62조)"""

    def generate_checklist(self, project_type: str, project_cost_krw: float) -> dict:
        required = [i for i in CONSTRUCTION_START_CHECKLIST if i["required"]]
        optional = [i for i in CONSTRUCTION_START_CHECKLIST if not i["required"]]
        safety_plan_required = project_cost_krw >= 50_000_000_000
        return {
            "project_type": project_type,
            "safety_plan_required": safety_plan_required,
            "safety_plan_basis": "건설기술진흥법 제62조 (50억원 이상)",
            "required_items": required, "optional_items": optional,
            "total_checklist_count": len(CONSTRUCTION_START_CHECKLIST),
            "estimated_preparation_days": 14,
            # 프론트(시공 체크리스트) 호환 키
            "checklist": [
                {"category": i.get("law", "법정"), "item": i["item"], "required": i["required"]}
                for i in CONSTRUCTION_START_CHECKLIST
            ],
            "total_items": len(CONSTRUCTION_START_CHECKLIST),
        }

    def auto_generate_safety_plan(self, project_id: str, project_name: str,
                                   floor_count: int, excavation_depth_m: float) -> dict:
        high_risk_works = []
        if floor_count >= 11:
            high_risk_works.append("11층 이상 고층 공사")
        if excavation_depth_m >= 10:
            high_risk_works.append(f"굴착 깊이 {excavation_depth_m}m 토사 붕괴 위험")
        if floor_count >= 5 or excavation_depth_m >= 5:
            high_risk_works.append("중장비 사용 작업")
        return {
            "project_id": project_id,
            "plan_name": f"{project_name} 안전관리계획서",
            "legal_basis": "건설기술진흥법 제62조",
            "high_risk_works": high_risk_works,
            "safety_officer_required": True,
            "generated_at": datetime.utcnow().isoformat()
        }
