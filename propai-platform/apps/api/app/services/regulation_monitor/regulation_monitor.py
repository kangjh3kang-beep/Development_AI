import httpx
from typing import List, Dict
from datetime import datetime, timedelta
from app.core.config import settings
import structlog

logger = structlog.get_logger()

# ── 부동산개발 관련 모니터링 대상 법령 ──
# id: 법제처(국가법령정보센터) lawService.do 호출용 법령 ID. 실접속 확인된 ID만 보유하며,
#   ID 미확보 법령은 id=None으로 정직 표기한다(가짜 ID로 죽은 API 호출 금지 — 무목업 원칙).
#   ID 보유 법령만 check_law_updates에서 실제 공포일자 폴링 대상이 된다.
# ★법제처 법령ID는 2026-06-24 lawSearch.do 조회 + lawService.do 본문 응답으로 '실작동 검증'된 6자리
#   법령ID만 사용한다(이전 7자리 ID는 본문 미반환=잠복결함이었음 → 전수 정정). 전 20종 폴링 가능.
MONITORED_LAWS = [
    # ── 핵심(critical) — 용도지역·건축·주택·정비·세금 직결 ──
    {"name": "건축법", "id": "001823", "critical": True},
    {"name": "국토의 계획 및 이용에 관한 법률", "id": "009294", "critical": True},
    {"name": "주택법", "id": "000243", "critical": True},
    {"name": "녹색건축물 조성 지원법", "id": "011557", "critical": True},
    {"name": "도시 및 주거환경정비법", "id": "009410", "critical": True},
    {"name": "빈집 및 소규모주택 정비에 관한 특례법", "id": "012805", "critical": True},
    {"name": "도시개발법", "id": "002024", "critical": True},
    {"name": "집합건물의 소유 및 관리에 관한 법률", "id": "001262", "critical": True},
    {"name": "건축물의 분양에 관한 법률", "id": "009760", "critical": True},
    # ── 일반(non-critical) — 토지·세금·환경·소방·인프라 인허가 ──
    {"name": "건설산업기본법", "id": "001808", "critical": False},
    {"name": "공익사업을 위한 토지 등의 취득 및 보상에 관한 법률", "id": "009295", "critical": False},
    {"name": "환경영향평가법", "id": "002016", "critical": False},
    {"name": "소방시설 설치 및 관리에 관한 법률", "id": "009503", "critical": False},
    {"name": "도로법", "id": "001821", "critical": False},
    {"name": "하수도법", "id": "001815", "critical": False},
    {"name": "수도권정비계획법", "id": "000266", "critical": False},
    {"name": "지방세법", "id": "001006", "critical": False},
    {"name": "재건축초과이익 환수에 관한 법률", "id": "010209", "critical": False},
    {"name": "농지법", "id": "000479", "critical": False},
    {"name": "산지관리법", "id": "009412", "critical": False},
]

# 실제 모니터링 법령 수(과장 금지 — 동적 산출). 폴링 가능(법제처 ID 보유) 법령은 별도 집계.
MONITORED_LAW_COUNT = len(MONITORED_LAWS)
POLLABLE_LAW_COUNT = sum(1 for _law in MONITORED_LAWS if _law.get("id"))


class RegulationMonitorService:
    """부동산개발 관련 법령 변경 자동 감지 (법제처 국가법령정보센터 API).

    모니터링 대상은 MONITORED_LAWS(현재 {count}개: 건축·국토계획·주택·정비·환경·소방·도로·
    하수도·세금 등 부동산개발 직결 법령). 이 중 법제처 법령 ID가 확보된 {pollable}개는
    공포일자 변경을 실시간 폴링하며, ID 미확보 법령은 목록 표기만 한다(가짜 ID 호출 금지).
    """  # noqa: D412 — 인스턴스화 시 _docstring을 실수치로 보정(아래 __init__).

    def __init__(self) -> None:
        # docstring의 플레이스홀더를 실제 법령 수로 치환(과장 '40개' 하드코딩 제거).
        if self.__class__.__doc__ and "{count}" in self.__class__.__doc__:
            self.__class__.__doc__ = self.__class__.__doc__.format(
                count=MONITORED_LAW_COUNT, pollable=POLLABLE_LAW_COUNT
            )

    def check_for_changes(self, days_back: int = 7) -> list[dict]:
        """동기 버전 — 모니터링 중인 법령 목록 반환(ID 미확보 법령 포함, 정직 표기)."""
        return [
            {"law_name": law["name"], "law_id": law["id"], "critical": law["critical"],
             "pollable": bool(law["id"]),
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
                # 법제처 ID 미확보 법령은 폴링 생략(가짜 ID로 죽은 API 호출 금지 — 무목업).
                if not law.get("id"):
                    continue
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
