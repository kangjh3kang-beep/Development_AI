import httpx
from typing import List, Dict
from datetime import datetime, timedelta
from app.core.config import settings
import structlog

logger = structlog.get_logger()

# ── 부동산개발 관련 모니터링 대상 법령 (법령 정본 60종 — legal_reference_registry 정본 커버리지) ──
# id: 법제처(국가법령정보센터) lawService.do 호출용 6자리 법령 ID. 실접속 확인된 ID만 보유하며,
#   ID 미확보 법령은 id=None으로 정직 표기한다(가짜 ID로 죽은 API 호출 금지 — 무목업 원칙).
#   ID 보유 법령만 check_law_updates에서 실제 공포일자 폴링 대상이 된다.
# ★검증 강화(2026-06-24): 법령ID는 lawService.do 본문의 '법령명_한글'이 대상 법령명과 '정확히 일치'함을
#   전수 확인한 ID만 사용한다(이전엔 '기본정보 존재'만 확인 → 다른 법을 가리키는 ID가 통과하던 잠복결함).
#   이 강화 검증으로 기존 2건의 오ID 정정: 주택법 000243→001809(000243은 민간임대주택법),
#   지방세법 001006→001649(001006은 지방교부세법). 전 60종 본문명 일치·폴링 가능.
MONITORED_LAWS = [
    # ── 핵심(critical) — 용도지역·건축·주택·정비 직결 ──
    {"name": "건축법", "id": "001823", "critical": True},
    {"name": "국토의 계획 및 이용에 관한 법률", "id": "009294", "critical": True},
    {"name": "주택법", "id": "001809", "critical": True},
    {"name": "녹색건축물 조성 지원법", "id": "011557", "critical": True},
    {"name": "도시 및 주거환경정비법", "id": "009410", "critical": True},
    {"name": "빈집 및 소규모주택 정비에 관한 특례법", "id": "012805", "critical": True},
    {"name": "도시개발법", "id": "002024", "critical": True},
    {"name": "집합건물의 소유 및 관리에 관한 법률", "id": "001262", "critical": True},
    {"name": "건축물의 분양에 관한 법률", "id": "009760", "critical": True},
    # ── 기존 일반 — 토지보상·환경·소방·인프라·세금 ──
    {"name": "건설산업기본법", "id": "001808", "critical": False},
    {"name": "공익사업을 위한 토지 등의 취득 및 보상에 관한 법률", "id": "009295", "critical": False},
    {"name": "환경영향평가법", "id": "002016", "critical": False},
    {"name": "소방시설 설치 및 관리에 관한 법률", "id": "009503", "critical": False},
    {"name": "도로법", "id": "001821", "critical": False},
    {"name": "하수도법", "id": "001815", "critical": False},
    {"name": "수도권정비계획법", "id": "000266", "critical": False},
    {"name": "지방세법", "id": "001649", "critical": False},
    {"name": "재건축초과이익 환수에 관한 법률", "id": "010209", "critical": False},
    {"name": "농지법", "id": "000479", "critical": False},
    {"name": "산지관리법", "id": "009412", "critical": False},
    # ── 정본66 확장(2026-06-24) — 토지·개발 ──
    {"name": "개발이익 환수에 관한 법률", "id": "001829", "critical": False},
    {"name": "개발제한구역의 지정 및 관리에 관한 특별조치법", "id": "002018", "critical": False},
    {"name": "산업입지 및 개발에 관한 법률", "id": "001839", "critical": False},
    {"name": "택지개발촉진법", "id": "000242", "critical": False},
    {"name": "역세권의 개발 및 이용에 관한 법률", "id": "011184", "critical": False},
    {"name": "도시재생 활성화 및 지원에 관한 특별법", "id": "011869", "critical": False},
    {"name": "도시재정비 촉진을 위한 특별법", "id": "010088", "critical": False},
    {"name": "도심 복합개발 지원에 관한 법률", "id": "014616", "critical": False},
    # ── 주택·건축물 관리 ──
    {"name": "공공주택 특별법", "id": "009595", "critical": False},
    {"name": "민간임대주택에 관한 특별법", "id": "000243", "critical": False},
    {"name": "공동주택관리법", "id": "012345", "critical": False},
    {"name": "건축물관리법", "id": "013478", "critical": False},
    {"name": "부동산개발업의 관리 및 육성에 관한 법률", "id": "010446", "critical": False},
    # ── 부동산 거래·등기·가격공시 ──
    {"name": "부동산 가격공시에 관한 법률", "id": "001827", "critical": False},
    {"name": "부동산 거래신고 등에 관한 법률", "id": "012480", "critical": False},
    {"name": "부동산등기법", "id": "001697", "critical": False},
    {"name": "감정평가 및 감정평가사에 관한 법률", "id": "012481", "critical": False},
    # ── 세금 ──
    {"name": "소득세법", "id": "001565", "critical": False},
    {"name": "종합부동산세법", "id": "009873", "critical": False},
    {"name": "인지세법", "id": "001568", "critical": False},
    # ── 임대차 ──
    {"name": "상가건물 임대차보호법", "id": "009276", "critical": False},
    {"name": "주택임대차보호법", "id": "001248", "critical": False},
    # ── 환경·재해·폐기물 ──
    {"name": "가축분뇨의 관리 및 이용에 관한 법률", "id": "010297", "critical": False},
    {"name": "자연재해대책법", "id": "000959", "critical": False},
    {"name": "폐기물관리법", "id": "001771", "critical": False},
    # ── 문화·교육·경관 ──
    {"name": "문화유산의 보존 및 활용에 관한 법률", "id": "001607", "critical": False},
    {"name": "매장유산 보호 및 조사에 관한 법률", "id": "011152", "critical": False},
    {"name": "교육환경 보호에 관한 법률", "id": "012494", "critical": False},
    {"name": "경관법", "id": "010447", "critical": False},
    {"name": "학교용지 확보 등에 관한 특례법", "id": "000894", "critical": False},
    # ── 교통·주차·안전 ──
    {"name": "도시교통정비 촉진법", "id": "001754", "critical": False},
    {"name": "주차장법", "id": "001814", "critical": False},
    {"name": "철도안전법", "id": "009766", "critical": False},
    {"name": "화재의 예방 및 안전관리에 관한 법률", "id": "014189", "critical": False},
    # ── 공간정보·규제·국공유재산·건설기술 ──
    {"name": "공간정보의 구축 및 관리 등에 관한 법률", "id": "011023", "critical": False},
    {"name": "토지이용규제 기본법", "id": "010071", "critical": False},
    {"name": "국유재산법", "id": "001598", "critical": False},
    {"name": "공유재산 및 물품 관리법", "id": "010000", "critical": False},
    {"name": "건설기술 진흥법", "id": "001807", "critical": False},
    # ── 편의증진 (법제처 본문명은 가운뎃점 ㆍ 사용, ID는 본문 검증됨) ──
    {"name": "장애인·노인·임산부 등의 편의증진 보장에 관한 법률", "id": "000186", "critical": False},
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
