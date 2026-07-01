"""인허가 서류 패키지 생성 서비스.

건축허가/개발행위허가/사용승인 서류 체크리스트 생성.
인허가 진행 상태 추적, 예상 소요 기간 산출.
B03: Race Condition 제어 (동시 다발 PDF 생성 시 I/O 병목 방어).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from apps.api.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 인허가 유형별 필요 서류 체크리스트
_PERMIT_CHECKLISTS = {
    "건축허가": [
        {"id": "BA-01", "name": "건축계획서", "required": True, "description": "건축물 개요, 배치도, 평면도 포함"},
        {"id": "BA-02", "name": "구조안전확인서", "required": True, "description": "구조기술사 작성"},
        {"id": "BA-03", "name": "소방설계도", "required": True, "description": "소방시설 설치계획"},
        {"id": "BA-04", "name": "에너지절약계획서", "required": True, "description": "건축물 에너지효율등급"},
        {"id": "BA-05", "name": "토지이용계획확인서", "required": True, "description": "용도지역 확인"},
        {"id": "BA-06", "name": "지적측량성과도", "required": True, "description": "경계측량 결과"},
        {"id": "BA-07", "name": "건축사 설계도서", "required": True, "description": "건축사 서명 날인"},
        {"id": "BA-08", "name": "조경계획서", "required": False, "description": "대지면적 200㎡ 이상 시"},
        {"id": "BA-09", "name": "교통영향평가서", "required": False, "description": "연면적 기준 해당 시"},
        {"id": "BA-10", "name": "환경영향평가서", "required": False, "description": "일정 규모 이상 시"},
        {"id": "BA-11", "name": "일조권 검토서", "required": False, "description": "주거지역 인접 시"},
        {"id": "BA-12", "name": "장애물 없는 생활환경 인증", "required": False, "description": "공공건축물 해당 시"},
    ],
    "개발행위허가": [
        {"id": "DA-01", "name": "토지이용계획서", "required": True, "description": "개발 사업 계획"},
        {"id": "DA-02", "name": "환경영향평가서", "required": True, "description": "환경 영향 검토"},
        {"id": "DA-03", "name": "배수계획서", "required": True, "description": "우수/오수 배수 계획"},
        {"id": "DA-04", "name": "도로계획서", "required": True, "description": "진입도로 계획"},
        {"id": "DA-05", "name": "측량성과도", "required": True, "description": "지적 경계 확인"},
        {"id": "DA-06", "name": "재해영향평가서", "required": False, "description": "산사태 위험지역 시"},
        {"id": "DA-07", "name": "교통영향평가서", "required": False, "description": "대규모 개발 시"},
        {"id": "DA-08", "name": "농지전용허가서", "required": False, "description": "농지 포함 시"},
    ],
    "사용승인": [
        {"id": "UC-01", "name": "준공도면", "required": True, "description": "준공 설계도서"},
        {"id": "UC-02", "name": "감리완료보고서", "required": True, "description": "책임감리원 작성"},
        {"id": "UC-03", "name": "시공자 확인서", "required": True, "description": "시공자 자체 검사"},
        {"id": "UC-04", "name": "에너지효율등급 인증서", "required": True, "description": "에너지 성능 확인"},
        {"id": "UC-05", "name": "소방완공검사필증", "required": True, "description": "소방서 발급"},
        {"id": "UC-06", "name": "구조안전확인서", "required": True, "description": "준공 구조 점검"},
        {"id": "UC-07", "name": "실내공기질 측정결과", "required": True, "description": "포름알데히드 등"},
        {"id": "UC-08", "name": "정화조 준공신고서", "required": False, "description": "정화조 설치 시"},
        {"id": "UC-09", "name": "승강기 검사필증", "required": False, "description": "엘리베이터 설치 시"},
        {"id": "UC-10", "name": "녹색건축 인증서", "required": False, "description": "공공건축물 해당 시"},
    ],
}

# 인허가 유형별 예상 처리 기간 (영업일)
_PERMIT_DURATION_DAYS = {
    "건축허가": {"서울": 25, "경기": 20, "default": 15},
    "개발행위허가": {"서울": 35, "경기": 30, "default": 20},
    "사용승인": {"서울": 15, "경기": 12, "default": 10},
}

# 인허가 진행 단계
_PERMIT_STAGES = [
    "서류준비",
    "접수완료",
    "서류보완요청",
    "검토중",
    "현장조사",
    "위원회심의",
    "허가결정",
    "허가서발급",
]


class PermitPackageService:
    """인허가 서류 패키지 생성 서비스."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._pdf_lock = asyncio.Lock()
        self.settings = get_settings()

    def generate_checklist(
        self,
        permit_type: str,
        *,
        building_area_sqm: float = 0,
        is_public: bool = False,
        is_agricultural: bool = False,
    ) -> dict:
        """인허가 유형별 필요 서류 체크리스트를 생성한다."""
        checklist = _PERMIT_CHECKLISTS.get(permit_type)
        if checklist is None:
            raise ValueError(f"지원하지 않는 인허가 유형: {permit_type}. "
                           f"사용 가능: {list(_PERMIT_CHECKLISTS.keys())}")

        items = []
        for item in checklist:
            applicable = item["required"]
            if not applicable:
                # 조건부 서류 적용 판단
                if "200㎡" in item.get("description", "") and building_area_sqm >= 200 or "공공건축물" in item.get("description", "") and is_public or "농지" in item.get("description", "") and is_agricultural:
                    applicable = True

            items.append({
                **item,
                "applicable": applicable,
                "submitted": False,
            })

        required_count = sum(1 for i in items if i["applicable"])
        return {
            "permit_type": permit_type,
            "total_items": len(items),
            "required_items": required_count,
            "optional_items": len(items) - required_count,
            "items": items,
        }

    async def generate_permit_pdf(self, project_id: str, payload: dict) -> dict:
        """인허가 서류 패키지 PDF를 생성한다 (B03: Race Condition 방어)."""
        async with self._pdf_lock:
            logger.info("인허가 PDF 생성 시작", project_id=project_id)
            permit_type = payload.get("permit_type", "건축허가")
            checklist = self.generate_checklist(permit_type)

            pdf_path = f"/tmp/permit_{project_id}.pdf"
            # 실제 PDF 생성 로직 (reportlab 등)
            await asyncio.sleep(0.1)  # I/O 시뮬레이션 (최소화)

            return {
                "pdf_path": pdf_path,
                "project_id": project_id,
                "permit_type": permit_type,
                "document_count": checklist["required_items"],
                "generated_at": datetime.now().isoformat(),
            }

    @staticmethod
    def estimate_permit_duration(permit_type: str, region: str = "default") -> dict:
        """인허가 예상 처리 기간을 산출한다 (영업일)."""
        durations = _PERMIT_DURATION_DAYS.get(permit_type)
        if durations is None:
            raise ValueError(f"지원하지 않는 인허가 유형: {permit_type}")

        days = durations.get(region, durations["default"])
        # 영업일 -> 달력일 변환 (주말 제외, 약 1.4배)
        calendar_days = int(days * 1.4)

        return {
            "permit_type": permit_type,
            "region": region,
            "business_days": days,
            "calendar_days": calendar_days,
            "stages": _PERMIT_STAGES,
        }

    @staticmethod
    def track_permit_status(
        current_stage: str,
    ) -> dict:
        """인허가 진행 상태를 추적한다."""
        if current_stage not in _PERMIT_STAGES:
            return {"stage": current_stage, "progress": 0, "remaining_stages": _PERMIT_STAGES}

        idx = _PERMIT_STAGES.index(current_stage)
        total = len(_PERMIT_STAGES)
        return {
            "current_stage": current_stage,
            "stage_index": idx + 1,
            "total_stages": total,
            "progress_pct": round((idx + 1) / total * 100, 1),
            "remaining_stages": _PERMIT_STAGES[idx + 1:],
            "is_complete": current_stage == _PERMIT_STAGES[-1],
        }

    @staticmethod
    def validate_documents(checklist_items: list[dict]) -> dict:
        """서류 완성도를 검증한다."""
        total = len(checklist_items)
        submitted = sum(1 for i in checklist_items if i.get("submitted"))
        required = [i for i in checklist_items if i.get("applicable")]
        required_submitted = sum(1 for i in required if i.get("submitted"))
        missing_required = [i["name"] for i in required if not i.get("submitted")]

        completeness = round(submitted / max(total, 1) * 100, 1)
        required_completeness = round(required_submitted / max(len(required), 1) * 100, 1)

        return {
            "total_documents": total,
            "submitted": submitted,
            "required_total": len(required),
            "required_submitted": required_submitted,
            "completeness_pct": completeness,
            "required_completeness_pct": required_completeness,
            "missing_required": missing_required,
            "is_ready": len(missing_required) == 0,
        }
