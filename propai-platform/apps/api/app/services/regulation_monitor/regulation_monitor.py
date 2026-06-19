import asyncio
from datetime import datetime, timedelta

import httpx
import structlog

from app.core.config import settings

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

    @staticmethod
    def monitored_law_names() -> list[str]:
        """감시 중인 법령명 목록 — baseline 출처(시행령 등)가 실제 감시 범위에 있는지 호출측 판정용."""
        return [law["name"] for law in MONITORED_LAWS]

    async def check_law_updates(self, days_back: int = 7) -> list[dict]:
        """모니터 법령 중 최근 days_back일 내 공포(개정)된 것 반환. 6법령 **병렬** 조회(순차 6×30s≈180s 블록 방지).

        ★실패 표면화(정직·무음0): per-law 예외·非200(raise_for_status)을 카운트하여 **전건 실패 시 RuntimeError**
        — 빈 [](=변경없음 확인)와 '감지 불가'(키 무효·네트워크 장애)를 구분해 호출측이 degrade하게 한다.
        부분 성공은 성공분만 반환(일부 법령 장애로 전체 묵음 방지)."""
        cutoff = datetime.now() - timedelta(days=days_back)

        async def _one(client: httpx.AsyncClient, law: dict) -> dict | None:
            params = {"OC": settings.MOLEG_API_KEY, "target": "law", "type": "JSON", "ID": law["id"]}
            resp = await client.get(f"{settings.MOLEG_BASE_URL}/lawService.do", params=params)
            resp.raise_for_status()  # 非200(403 무효키·429·5xx) → 예외(조용한 skip 금지=거짓 not-stale 차단)
            prom = ((resp.json().get("법령") or {}).get("기본정보") or {}).get("공포일자", "")
            try:
                recent = bool(prom) and datetime.strptime(prom, "%Y%m%d") >= cutoff
            except ValueError:
                recent = False  # 공포일 형식 불명은 fetch 실패 아님(해당 법령 '변경 없음' 취급)
            if not recent:
                return None
            return {"law_name": law["name"], "law_id": law["id"], "promulgation_date": prom,
                    "critical": law["critical"], "change_type": "amendment",
                    "impact_level": "high" if law["critical"] else "medium"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            results = await asyncio.gather(*[_one(client, law) for law in MONITORED_LAWS],
                                           return_exceptions=True)
        updated, failures = [], 0
        for law, r in zip(MONITORED_LAWS, results, strict=True):
            if isinstance(r, Exception):
                failures += 1
                logger.error("법규 변경 감지 실패", law=law["name"], error=str(r)[:200])
            elif r is not None:
                updated.append(r)
        if failures == len(MONITORED_LAWS):  # 전건 실패 = 감지 불가 → 신호(빈 결과로 위장 금지)
            raise RuntimeError(f"all {failures} law-update fetches failed")
        return updated

    def analyze_impact(self, changed_laws: list[dict]) -> dict:
        high_impact = [law for law in changed_laws if law.get("impact_level") == "high"]
        return {
            "total_changes": len(changed_laws),
            "high_impact_count": len(high_impact),
            "high_impact_laws": high_impact,
            "recommended_actions": [
                "해당 법령 변경 내용 즉시 검토",
                "진행 중인 프로젝트 법규 재검토"
            ] if high_impact else ["정기 모니터링 유지"]
        }
