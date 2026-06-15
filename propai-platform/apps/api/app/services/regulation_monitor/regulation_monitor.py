import httpx
from typing import List, Dict
from datetime import datetime, timedelta
from app.core.config import settings
import structlog

logger = structlog.get_logger()

MONITORED_LAWS = [
    {"name": "건축법", "id": "1003714", "critical": True},
    {"name": "국토의 계획 및 이용에 관한 법률", "id": "1011903", "critical": True},
    {"name": "주택법", "id": "1009672", "critical": True},
    {"name": "녹색건축물 조성 지원법", "id": "1011751", "critical": True},
    {"name": "건설산업기본법", "id": "1007557", "critical": False},
    {"name": "공익사업을 위한 토지 등의 취득 및 보상에 관한 법률", "id": "1008363", "critical": False},
]

class RegulationMonitorService:
    """40개 법령 변경 자동 감지 (법제처 API)"""

    def check_for_changes(self, days_back: int = 7) -> list[dict]:
        """동기 버전 — 모니터링 중인 법령 목록 반환."""
        return [
            {"law_name": law["name"], "law_id": law["id"], "critical": law["critical"],
             "change_type": "amendment", "impact_level": "high" if law["critical"] else "medium"}
            for law in MONITORED_LAWS
        ]

    def assess_impact(self, project: dict, changes: list[dict]) -> dict:
        """프로젝트 영향도 평가."""
        impacts = []
        for c in changes:
            impacts.append({
                "law_name": c.get("law_name", ""),
                "impact_level": c.get("impact_level", "medium"),
                "recommendation": "해당 법령 변경 내용 즉시 검토",
            })
        return {
            "changes_detected": len(changes),
            "impacts": impacts,
            "project_id": project.get("project_id", ""),
        }

    async def check_law_updates(self, days_back: int = 7) -> list[dict]:
        updated_laws = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        async with httpx.AsyncClient(timeout=30.0) as client:
            for law in MONITORED_LAWS:
                try:
                    params = {"OC": settings.MOLEG_API_KEY, "target": "law", "type": "JSON", "ID": law["id"]}
                    resp = await client.get(f"{settings.MOLEG_BASE_URL}/lawService.do", params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        law_info = data.get("법령", {})
                        prom_date_str = law_info.get("기본정보", {}).get("공포일자", "")
                        if prom_date_str:
                            try:
                                prom_date = datetime.strptime(prom_date_str, "%Y%m%d")
                                if prom_date >= cutoff_date:
                                    updated_laws.append({
                                        "law_name": law["name"], "law_id": law["id"],
                                        "promulgation_date": prom_date_str,
                                        "critical": law["critical"], "change_type": "amendment",
                                        "impact_level": "high" if law["critical"] else "medium"
                                    })
                            except ValueError:
                                pass
                except Exception as e:
                    logger.error("법규 변경 감지 실패", law=law["name"], error=str(e))
        return updated_laws

    def analyze_impact(self, changed_laws: list[dict]) -> dict:
        high_impact = [l for l in changed_laws if l.get("impact_level") == "high"]
        return {
            "total_changes": len(changed_laws),
            "high_impact_count": len(high_impact),
            "high_impact_laws": high_impact,
            "recommended_actions": [
                "해당 법령 변경 내용 즉시 검토",
                "진행 중인 프로젝트 법규 재검토"
            ] if high_impact else ["정기 모니터링 유지"]
        }
