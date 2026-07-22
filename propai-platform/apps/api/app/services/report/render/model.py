"""정본 보고서 모델(도메인 무관) + Block 판별유니온.

도메인 서비스(수지·세금·시장…)는 계산 결과를 이 모델로 '조립'만 한다.
세 렌더러(PDF/PPTX/DOCX)는 이 모델 하나만 읽어 동일한 문서를 만든다.

★가짜값 금지: 값이 없으면 ``fmt_value`` 가 '—'(EMPTY_MARK)로 표기한다. 렌더러가 아니라
  '값을 문자열로 바꾸는 규칙'을 여기 한 곳에 두어 세 포맷이 완전히 동일하게 표기하게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .tokens import EMPTY_MARK


# ── 값 → 문자열 공용 규칙(★기존 pipeline_report_pdf._fmt 를 승격) ────
def fmt_value(v: Any) -> str:
    """숫자·불리언·None 을 사람이 읽는 문자열로. None→'—', bool→예/아니오, 큰 수→천단위 콤마."""
    if v is None:
        return EMPTY_MARK
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int, float)):
        try:
            # 정수형이면 소수점 제거, 1000 이상은 천단위 콤마
            if float(v).is_integer():
                iv = int(v)
                return f"{iv:,}" if abs(iv) >= 1000 else str(iv)
            return f"{v:,.1f}" if abs(v) >= 1000 else f"{v:.1f}"
        except (TypeError, ValueError, OverflowError):
            return str(v)
    s = str(v).strip()
    return s if s else EMPTY_MARK


# ── Block 판별유니온 ────────────────────────────────────────────────
# 각 Block 은 kind 로 구분한다. 렌더러는 kind 로 분기해 그린다.

@dataclass
class KVTableBlock:
    """키-값 2열표(핵심 요약·개요 등). rows=[(라벨, 값), ...]."""
    rows: list[tuple[str, Any]]
    title: str | None = None
    kind: Literal["kv"] = "kv"


@dataclass
class DataTableBlock:
    """일반 데이터표. headers=열 제목, rows=행(값 배열)."""
    headers: list[str]
    rows: list[list[Any]]
    caption: str | None = None
    numeric_cols: list[int] = field(default_factory=list)  # 우측정렬할 열 인덱스
    total_row: bool = False                                # 마지막 행을 합계(굵게)로
    title: str | None = None
    kind: Literal["table"] = "table"


@dataclass
class KPITile:
    """KPI 타일 1개. signal='safe'|'warn'|'danger'|None(임계 대비 색)."""
    label: str
    value: str
    basis: str | None = None       # 예: 'LTV 65% ≤ 70% 기준'
    signal: str | None = None      # tokens.SIGNAL 값(hex) 또는 None


@dataclass
class KPITileBlock:
    """KPI 타일 행(3~4개). R2: 결정지표는 크게, 나머지는 보조."""
    tiles: list[KPITile]
    kind: Literal["kpi"] = "kpi"


@dataclass
class Series:
    """차트 시리즈 1개."""
    name: str
    values: list[float]


@dataclass
class ChartBlock:
    """차트. chart_type: bar/line/pie/waterfall/tornado.

    벡터 우선(R6): bar/line/pie 는 네이티브 벡터, waterfall/tornado 는 PNG 폴백을 렌더러가 선택.
    """
    chart_type: Literal["bar", "line", "pie", "waterfall", "tornado"]
    title: str
    categories: list[str]
    series: list[Series]
    caption: str | None = None
    y_axis_label: str | None = None
    kind: Literal["chart"] = "chart"


@dataclass
class NarrativeBlock:
    """AI/전문가 서술 문단(들)."""
    paragraphs: list[str]
    title: str | None = None
    kind: Literal["narrative"] = "narrative"


@dataclass
class Evidence:
    """근거 계약(메모리 evidence 계약 재사용). verified 만 legal_link 노출."""
    value: str
    basis: str | None = None
    source: str | None = None
    provenance: str | None = None
    legal_link: str | None = None
    confidence: str | None = None   # high/med/low — low 는 앰버 태그(R4)


@dataclass
class EvidenceBlock:
    """근거 블록(R5: 상세는 부록으로). items=Evidence 목록."""
    items: list[Evidence]
    title: str | None = "근거"
    kind: Literal["evidence"] = "evidence"


@dataclass
class ImageBlock:
    """정적 이미지(지도 PNG 등). png=이미지 bytes."""
    png: bytes
    caption: str | None = None
    max_width_mm: float | None = None
    kind: Literal["image"] = "image"


@dataclass
class ChecklistBlock:
    """체크리스트. items=[(라벨, ok:bool 또는 상태문자열)]. 미확보는 정직 표기."""
    items: list[tuple[str, Any]]
    title: str | None = None
    kind: Literal["checklist"] = "checklist"


@dataclass
class GradeBadgeBlock:
    """등급 배지(양호/보통/유의/부실우려). grade=tokens.GRADE 키 또는 라벨."""
    grade: str
    label: str | None = None      # 배지 앞에 붙일 설명(예: '사업성 평가등급')
    kind: Literal["grade"] = "grade"


@dataclass
class DisclaimerBlock:
    """면책 문구."""
    text: str
    kind: Literal["disclaimer"] = "disclaimer"


Block = (
    KVTableBlock
    | DataTableBlock
    | KPITileBlock
    | ChartBlock
    | NarrativeBlock
    | EvidenceBlock
    | ImageBlock
    | ChecklistBlock
    | GradeBadgeBlock
    | DisclaimerBlock
)


# ── 문서 구조 ───────────────────────────────────────────────────────
@dataclass
class Section:
    """보고서 섹션. blocks 를 순서대로 렌더."""
    title: str
    blocks: list[Block] = field(default_factory=list)
    section_no: int | None = None


@dataclass
class ReportMeta:
    """표지·머리말에 쓰는 메타."""
    title: str                                  # 문서 유형(예: 프로젝트 통합 분석 보고서)
    subtitle: str | None = None
    project_address: str | None = None
    doc_no: str | None = None
    generated_at: str | None = None
    accent_color: str | None = None             # 도메인별 강조색(없으면 PRDS 딥틸)
    confidential: bool = True
    completeness: dict[str, Any] | None = None  # {total,filled,empty,pct} 정직 채움도
    # ★W1-A(v4.0 P13): 이 산출물의 승인등급(ApprovalState 값 — DRAFT/MACHINE_VALIDATED/
    #   EXPERT_REVIEWED/APPROVED/SUPERSEDED). 기본값 DRAFT — 기존 생성·다운로드 흐름은
    #   전혀 바뀌지 않는다(등급만 명시적으로 부착, 렌더러 시각화는 W1-C 스코프).
    approval_state: str = "DRAFT"

    def __post_init__(self) -> None:
        # ★R1 반영: 불법 등급 문자열("TOTALLY_INVALID" 등)이 보고서 표면까지 흘러가지 않게
        #   생성 시점에 조기 거부한다(정직표기 원칙). 저장 타입은 asdict 직렬화 안정성을 위해
        #   str 유지 — ApprovalState 로 정규화만 거친다.
        from app.services.approval.approval_state import ApprovalState
        self.approval_state = ApprovalState(self.approval_state).value


@dataclass
class ReportModel:
    """정본 보고서. exec_summary 는 1페이지째 두괄식 요약(선택)."""
    meta: ReportMeta
    sections: list[Section] = field(default_factory=list)
    exec_summary: Section | None = None
    disclaimer: str | None = None
