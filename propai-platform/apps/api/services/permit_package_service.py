"""인허가 서류 패키지 생성 서비스.

건축허가/개발행위허가/사용승인 서류 체크리스트 생성.
인허가 진행 상태 추적, 예상 소요 기간 산출.
동시성: PDF 디스크 기록은 고유 임시파일 + 원자적 rename 으로 경합 자체를 제거.
"""

from __future__ import annotations

import io
import os
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from apps.api.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 인허가 유형별 필요 서류 체크리스트 (정적 기준표 — 법령·실무 기준 요약, LLM/외부API 미사용)
# ★이중화 주의(SSOT 미통합): 인허가 제출서류 기준표가 지금 두 곳에 나뉘어 있다.
#   ① 이 파일: '인허가 유형별'(건축허가/개발행위허가/사용승인) 서류 목록
#   ② app/services/permit/permit_guide_service.py: '시설물(건축물 용도)별'(단독주택/공동주택 등)
#      절차+제출서류 (쉬운 규제안내서, GET /permits/guide)
#   관점이 달라(유형별 vs 시설물별) 당장은 각자 쓰이지만, 장기적으로는 서류 기준표를
#   app/services/permit/ 아래 공용 상수 한 곳으로 모아 두 서비스가 같은 원천(SSOT)을 읽게
#   통합해야 한다. 그 전까지는 서류 항목을 고칠 일이 생기면 반드시 두 곳을 함께 확인할 것
#   (버그수정 전역정책 — 같은 패턴 이중화 방치 금지).
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


def _render_package_pdf(project_id: str, checklist: dict, duration: dict) -> bytes:
    """체크리스트+예상기간 실데이터를 실제 PDF 바이트로 렌더한다(reportlab).

    플랫폼 공용 PDF 패턴(decision_brief_pdf 동형)을 그대로 따른다:
    - 한글 CID 폰트(HYSMyeongJo-Medium) 등록, 실패 시 Helvetica 폴백
    - 모든 동적 문자열은 공용 esc(XML 이스케이프)로 감싸 크래시·마크업 주입 차단
    - 데이터가 비면 '미확보(정직 고지)' 표기(가짜값으로 채우지 않음)
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from app.services.common.pdf_escape import esc as _esc

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        font = "HYSMyeongJo-Medium"
    except Exception:  # noqa: BLE001 — 한글폰트 미가용 환경은 Helvetica 폴백(플랫폼 동형)
        font = "Helvetica"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName=font, fontSize=18)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=font, fontSize=13,
                        textColor=colors.HexColor("#7c3aed"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)

    story: list = []

    def _table(header: list[str], rows: list[list[str]], widths: list[float]) -> None:
        # 공용 _table 동형 — rows 비면 '미확보(정직 고지)' 1행으로(가짜로 채우지 않음).
        raw = [header, *rows] if rows else [header, ["미확보(정직 고지)"] + [""] * (len(header) - 1)]
        data = [[_esc(cell) for cell in row] for row in raw]
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    permit_type = str(checklist.get("permit_type") or "-")
    story.append(Paragraph(_esc(f"인허가 서류 패키지 — {permit_type}"), h1))
    story.append(Paragraph(
        _esc(f"프로젝트: {project_id} · 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}"),
        body))
    story.append(Spacer(1, 6))

    # ── 1. 필요 서류 체크리스트(정적 기준표 실데이터) ──
    story.append(Paragraph("1. 필요 서류 체크리스트", h2))
    rows = [
        [
            str(it.get("id") or "-"),
            str(it.get("name") or "-"),
            "필수" if it.get("required") else "조건부",
            "적용" if it.get("applicable") else "해당없음",
            str(it.get("description") or ""),
        ]
        for it in (checklist.get("items") or [])
    ]
    _table(["번호", "서류명", "구분", "적용", "비고"],
           rows, [16 * mm, 44 * mm, 16 * mm, 18 * mm, 76 * mm])
    story.append(Paragraph(
        _esc(f"총 {checklist.get('total_items', 0)}건 중 적용 {checklist.get('required_items', 0)}건"
             f" (조건부 {checklist.get('optional_items', 0)}건)"),
        body))
    story.append(Spacer(1, 6))

    # ── 2. 예상 처리 기간(내부 기준표 참고치 — 정직 고지 포함) ──
    story.append(Paragraph("2. 예상 처리 기간", h2))
    _table(["항목", "값"], [
        ["지역", str(duration.get("region") or "-")],
        ["영업일 기준", f"{duration.get('business_days', '-')}일"],
        ["달력일 환산", f"{duration.get('calendar_days', '-')}일"],
    ], [70 * mm, 90 * mm])
    story.append(Paragraph(
        "※ 내부 기준표 기반 참고치입니다. 실제 처리기간은 지자체·서류보완·심의 여부에 따라"
        " 달라질 수 있습니다.", body))
    story.append(Spacer(1, 6))

    # ── 3. 인허가 진행 단계(참고) ──
    story.append(Paragraph("3. 인허가 진행 단계", h2))
    story.append(Paragraph(_esc(" → ".join(duration.get("stages") or _PERMIT_STAGES)), body))

    doc.build(story)
    return buf.getvalue()


class PermitPackageService:
    """인허가 서류 패키지 생성 서비스."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
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
            applicable = bool(item["required"])
            desc = str(item.get("description") or "")
            if not applicable:
                # 조건부 서류 적용 판단(정적 기준표의 조건 문구 키워드와 1:1 매칭)
                if (
                    ("200㎡" in desc and building_area_sqm >= 200)
                    or ("공공건축물" in desc and is_public)
                    or ("농지" in desc and is_agricultural)
                ):
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
        """인허가 서류 패키지 PDF를 실제로 생성한다.

        과거에는 경로 문자열만 돌려주고 파일은 만들지 않는 목업이었다(무목업 원칙 위반).
        지금은 정적 기준표 실데이터(체크리스트+예상기간)를 reportlab 으로 실제 렌더해
        pdf_bytes(라우터 스트리밍 응답용)와 실파일(pdf_path)을 함께 만든다.

        동시성: 같은 project_id 동시 요청이 같은 경로에 반쯤 쓴 파일을 남기지 않도록
        고유 임시파일에 쓴 뒤 os.replace(원자적 rename)로 최종 경로에 옮긴다.
        (과거의 인스턴스 필드 락은 요청마다 새 인스턴스라 실효가 없었음 — 안전 착각 제거.)
        """
        logger.info("인허가 PDF 생성 시작", project_id=project_id)
        permit_type = payload.get("permit_type", "건축허가")
        region = str(payload.get("region") or "default")
        checklist = self.generate_checklist(
            permit_type,
            building_area_sqm=float(payload.get("building_area_sqm") or 0),
            is_public=bool(payload.get("is_public")),
            is_agricultural=bool(payload.get("is_agricultural")),
        )
        duration = self.estimate_permit_duration(permit_type, region)

        # 실제 PDF 렌더(reportlab) — 정적 기준표 실데이터만 담는다(가짜값 생성 없음).
        pdf_bytes = _render_package_pdf(str(project_id), checklist, duration)

        # 파일 경로에 들어갈 project_id 는 경로조작('../') 차단을 위해 안전문자만 남긴다.
        safe_id = re.sub(r"[^0-9A-Za-z가-힣_-]", "_", str(project_id))[:64] or "package"
        final_path = f"/tmp/permit_{safe_id}.pdf"
        pdf_path: str | None
        try:
            # 반환하는 경로가 실존 파일이 되도록 실제로 기록한다(빈 약속 금지).
            # 고유 임시파일 → 원자적 rename: 동시 요청이 있어도 최종 파일은 항상 온전한 1본.
            tmp_path = f"{final_path}.{uuid.uuid4().hex[:8]}.tmp"
            with open(tmp_path, "wb") as f:  # noqa: PTH123
                f.write(pdf_bytes)
            os.replace(tmp_path, final_path)
            pdf_path = final_path
        except OSError:  # 디스크 기록 실패해도 bytes 응답은 유효 — 경로만 정직하게 None
            pdf_path = None

        return {
            "pdf_path": pdf_path,
            "pdf_bytes": pdf_bytes,
            "project_id": project_id,
            "permit_type": permit_type,
            "region": region,
            "document_count": checklist["required_items"],
            "size_bytes": len(pdf_bytes),
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
