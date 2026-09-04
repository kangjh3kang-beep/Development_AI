"""PRDS(PropAI Report Design System) 디자인 토큰 — 세 포맷의 단일 출처.

철학: "적을수록 신뢰(Less, but trustworthy)".
- 은행 심사역·투자심의위원 같은 비전문 의사결정자가 1페이지 두괄식 요약으로 Go/No-Go를 판단.
- 장식(그림자·그라디언트·불필요한 색) 제거, 잉크는 데이터·근거에.
- 색은 '의미'(등급·리스크·임계치)에만. 브랜드색(딥틸)은 위계에만 절제 사용.

★이 파일은 순수 상수 + 순수 헬퍼만 담는다(reportlab/pptx/docx 임포트 금지).
  각 렌더러가 아래 HEX·pt 값을 자기 라이브러리 색/폰트로 변환해 쓴다 → '한 곳 수정, 세 포맷 반영'.

근거: _workspace/report_engine/05_design_system.json (PRDS) + 06_rams_audit.json (Rams 6정제 반영).
"""

from __future__ import annotations

# ── 색 (의미 토큰, R6: 원시→의미 2계층) ─────────────────────────────
# 브랜드/위계
BRAND = "#0e7490"          # 딥틸 — 표 헤더·H2·헤더바
BRAND_DARK = "#155e75"     # 강조 테두리
LINK = "#0369a1"           # 근거 링크(하이퍼링크)
# 잉크/중립
INK = "#0f172a"            # 본문·제목
SECONDARY = "#475569"      # 보조 텍스트
MUTED = "#64748b"          # 캡션·출처
LINE = "#cbd5e1"           # 괘선 0.4pt
ZEBRA = "#f1f5f9"          # 행 교대 배경
PANEL = "#f8fafc"          # 요약/근거 박스 배경
WHITE = "#ffffff"

# 의미 토큰(렌더러는 되도록 아래 이름으로 접근) — R6
COLOR = {
    "header": BRAND,        # 표 헤더 배경
    "header_text": WHITE,
    "h2": BRAND,            # 섹션 제목
    "rule": BRAND,          # 섹션 상단 룰
    "ink": INK,
    "secondary": SECONDARY,
    "muted": MUTED,
    "line": LINE,
    "zebra": ZEBRA,
    "panel": PANEL,
    "link": LINK,
    "white": WHITE,
}

# 등급 4단계(FSC 사업성 평가): 텍스트색 + 배경 tint
GRADE = {
    "good": {"fg": "#166534", "bg": "#dcfce7", "label": "양호"},
    "normal": {"fg": "#155e75", "bg": "#cffafe", "label": "보통"},
    "caution": {"fg": "#92400e", "bg": "#fef3c7", "label": "유의"},
    "distress": {"fg": "#991b1b", "bg": "#fee2e2", "label": "부실우려"},
}

# 신호등(임계치: LTV·DSCR·분양률 등)
SIGNAL = {
    "safe": "#16a34a",     # 안전/GO
    "warn": "#d97706",     # 주의(앰버 — R4: 저신뢰/추정도 이 톤으로 '명확히')
    "danger": "#dc2626",   # 위험/NO-GO
}
AMBER = SIGNAL["warn"]      # R4: 추정·미검증(confidence=low) 태그색

# 보조 도표 계열(차트 시리즈 구분) — 4색 순서
SERIES_COLORS = ["#0e7490", "#64748b", "#0369a1", "#94a3b8", "#155e75", "#d97706"]


# ── 타이포 스케일 (pt, leading=행간) — R3: 본문/표/숫자는 고딕 ────────
# 각 값 = (size_pt, leading_pt, bold)
TYPE = {
    "title": (24, 28, True),        # 표지 타이틀
    "h1": (16, 20, True),           # 섹션 디바이더
    "h2": (13, 16, True),           # 섹션 제목(딥틸)
    "h3": (11, 14, True),           # 소제목
    "body": (9.5, 14, False),       # 본문(PDF). PPTX/DOCX는 +1
    "table": (8.5, 11, False),      # 표 셀
    "table_header": (8.5, 11, True),
    "kpi_value": (24, 26, True),    # KPI 수치(tabular). R2: 결정지표는 크게
    "kpi_label": (8, 10, False),    # KPI 라벨(muted)
    "caption": (7.5, 11, False),    # 캡션/출처(muted)
    "disclaimer": (7.5, 11, False),
}

# 폰트(R3): 명조는 표제 위계 한정, 본문·표·숫자는 고딕
FONT_KR_SERIF_PDF = "HYSMyeongJo-Medium"   # reportlab CID 명조(표지·대제목)
FONT_KR_GOTHIC = "맑은 고딕"                 # PPTX/DOCX EastAsian(본문·표) — 뷰어 로컬폰트 안전
FONT_FALLBACK = "Helvetica"                 # 라틴·숫자·명조 폴백


# ── 레이아웃 (mm / inch) ────────────────────────────────────────────
PAGE = {
    "a4_w_mm": 210, "a4_h_mm": 297,
    "margin_top_mm": 16, "margin_bottom_mm": 16, "margin_side_mm": 15,
    "body_w_mm": 180,                # 본문폭(210 - 15*2)
    "kv_label_mm": 55, "kv_value_mm": 125,   # K-V 2열표 비율(기존 유지)
}
PPTX = {"w_in": 13.33, "h_in": 7.5, "safe_in": 0.6, "header_in": 1.1, "footer_y_in": 7.1, "footer_h_in": 0.4}
DOCX = {"margin_cm": 2.0}

# ── 문구(공통 상수) ─────────────────────────────────────────────────
BRANDING = "사통팔땅 · AI 부동산 인텔리전스"
DISCLAIMER_TEXT = (
    "※ 본 보고서는 공개데이터·AI 분석 기반의 참고 자료이며, 투자 권유나 보증이 아닙니다. "
    "미래 추정치는 시장·정책 변동에 따라 실제와 다를 수 있으며, 최종 판단·책임은 이용자에게 있습니다. "
    "무단 배포를 금합니다."
)
CONFIDENTIAL_LABEL = "대외비 (CONFIDENTIAL)"
EMPTY_MARK = "—"   # 빈값/무자료(가짜값 생성 금지)

# ── 승인등급 라벨(W1-C · v4.0 P12) — 세 포맷 공용, ApprovalState 값 → 한국어 표기 ──────
APPROVAL_LABEL = {
    "DRAFT": "내부 초안 (INTERNAL DRAFT)",
    "MACHINE_VALIDATED": "기계검증",
    "EXPERT_REVIEWED": "전문가검토",
    "APPROVED": "승인본",
    "SUPERSEDED": "폐기",
}


# ── 순수 헬퍼 ───────────────────────────────────────────────────────
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    """'#0e7490' → (14,116,144). 렌더러가 자기 라이브러리 색 객체로 변환할 때 사용."""
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def grade_style(grade: str) -> dict:
    """등급 키('good'/'normal'/'caution'/'distress' 또는 한글/영문 라벨) → GRADE 스타일 dict."""
    key = (grade or "").strip().lower()
    if key in GRADE:
        return GRADE[key]
    # 한글/영문 라벨 매핑(관대)
    label_map = {
        "양호": "good", "우수": "good", "low": "good",
        "보통": "normal", "medium": "normal", "적정": "normal",
        "유의": "caution", "주의": "caution", "high": "caution",
        "부실우려": "distress", "위험": "distress", "very_high": "distress", "부적합": "distress",
    }
    return GRADE.get(label_map.get(key, "normal"), GRADE["normal"])


def signal_for(value: float | None, threshold: float | None, higher_is_worse: bool = True) -> str | None:
    """임계치 대비 신호등 색 반환(값/임계 없으면 None → 색 강조 안 함).

    higher_is_worse=True: 값이 임계 이상이면 위험(예 LTV). 임계의 90%부터 주의(앰버).
    """
    if value is None or threshold is None:
        return None
    try:
        v, t = float(value), float(threshold)
    except (TypeError, ValueError):
        return None
    if t == 0:
        return None
    ratio = v / t
    if higher_is_worse:
        if v >= t:
            return SIGNAL["danger"]
        if ratio >= 0.9:
            return SIGNAL["warn"]
        return SIGNAL["safe"]
    # 낮을수록 나쁨(예 DSCR·분양률)
    if v <= t:
        return SIGNAL["danger"]
    if ratio <= 1.1:
        return SIGNAL["warn"]
    return SIGNAL["safe"]
