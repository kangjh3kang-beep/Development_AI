"""수지 예산 라인아이템 표준 템플릿 (설계도 §12 FeasibilityTemplate).

BudgetExecutionPanel(§13)의 빈 그룹 골격을 실무 표준 라인아이템으로 프리셋한다.

★무목업: 금액은 넣지 않는다(각 항목 금액은 사용자 입력·분석엔진이 채움). 라벨(구조)과 산정근거
힌트(note)만 제공한다. 각종부담금은 개발방식(공동주택 여부)에 따라 실제 부과 대상만 포함하며,
부담금 코드는 utility/sale stage 엔진과 정합한다(B01~B08 = utility_stage, C07·C08 = sale_stage).

★그룹은 프론트 BudgetExecutionPanel.GROUPS와 1:1 유지(신규 그룹은 양쪽 동기).
"""
from __future__ import annotations

from typing import Any

# 개발방식 라벨 — unit_standards.EXCLUSIVE_AREA_RATIO 주석과 정합(M01~M15).
METHOD_LABELS: dict[str, str] = {
    "M01": "재개발", "M02": "재건축", "M03": "역세권개발", "M04": "지역주택조합",
    "M05": "임대협동조합", "M06": "일반분양", "M07": "주상복합", "M08": "오피스텔",
    "M09": "지식산업센터", "M10": "단독주택", "M11": "전원주택", "M12": "타운하우스",
    "M13": "도시형생활주택", "M14": "공공임대", "M15": "민간리츠",
}

# 공동주택 계열(학교용지부담금·광역교통부담금 부과 대상 — 학교용지법·대도시권광역교통관리법).
# 비주거(M08 오피스텔·M09 지산)·소규모 단독계열(M10~M12)은 두 부담금 대상 아님(해당 시 개별 추가).
_APARTMENT_METHODS = {"M01", "M02", "M03", "M04", "M05", "M06", "M07", "M13", "M14", "M15"}

# 공통 표준 라인아이템: (group, label, note). 금액 없음(무목업).
_COMMON: list[tuple[str, str, str]] = [
    # 토지비
    ("토지비", "토지매입비", "실거래가·감정평가 기준"),
    ("토지비", "취득세", "토지 취득세 4.6%(농특세·지방교육세 포함)"),
    ("토지비", "중개수수료", "법정 상한 요율"),
    ("토지비", "법무사·등기비(취득)", "소유권이전 등기 대행"),
    # 공사비
    ("공사비", "직접공사비(도급)", "표준건축비·적산(BOQ) 기준"),
    ("공사비", "철거·해체비", "기존 건축물·지장물"),
    ("공사비", "지장물 이설비", "전기·통신·상하수도 이설"),
    ("공사비", "예술장식품", "건축비의 1%(건축물 미술작품·문화예술진흥법)"),
    # 설계감리비
    ("설계감리비", "설계비", "건축·구조·설비 설계"),
    ("설계감리비", "감리비", "공사감리(건축법)"),
    ("설계감리비", "인허가 대행비", "인허가·심의 대행"),
    ("설계감리비", "측량·지질조사비", "경계측량·지반조사"),
    # 판매관리비
    ("판매관리비", "분양대행 수수료", "분양대행사 용역"),
    ("판매관리비", "광고·홍보비", "분양 광고·마케팅"),
    ("판매관리비", "모델하우스", "견본주택 건립·운영"),
    ("판매관리비", "분양보증 수수료", "HUG 분양보증(주택도시보증공사)"),
    # 보존등기비
    ("보존등기비", "등록면허세(보존등기)", "소유권보존 등기"),
    ("보존등기비", "국민주택채권 매입", "등기 시 채권 매입"),
    # 일반관리비
    ("일반관리비", "일반관리비", "시행사 운영·인건비"),
    ("일반관리비", "신탁 수수료", "부동산신탁(관리·처분·분양관리)"),
    # 제세금
    ("제세금", "재산세", "보유 기간 재산세"),
    ("제세금", "종합부동산세", "보유 기간 종부세"),
    ("제세금", "법인세(처분)", "처분 이익 법인세"),
    # 금융비
    ("금융비", "PF 대출이자", "본 PF 대출이자(ECOS 기준금리 연동)"),
    ("금융비", "중도금 대출이자", "수분양자 중도금 대출 이자"),
    ("금융비", "대출 취급수수료", "PF 취급·주선 수수료"),
    # 예비비
    ("예비비", "예비비", "총사업비의 통상 3~5%"),
]

# 각종부담금(부담금 엔진 코드와 정합). apartment_only=True 는 공동주택 계열만.
_CHARGES: list[dict[str, Any]] = [
    {"label": "광역교통시설부담금", "note": "대도시권광역교통관리법(코드 B01)", "apartment_only": True},
    {"label": "학교용지부담금", "note": "학교용지 확보 특례법(코드 B02·공동주택 0.4%)", "apartment_only": True},
    {"label": "상수도 원인자부담금", "note": "수도법(코드 B03)", "apartment_only": False},
    {"label": "하수도 원인자부담금", "note": "하수도법(코드 B04)", "apartment_only": False},
    {"label": "전기 인입부담금", "note": "한전 시설분담금(코드 B05)", "apartment_only": False},
    {"label": "도시가스 인입부담금", "note": "도시가스 공급규정(코드 B06)", "apartment_only": False},
    {"label": "기반시설부담금", "note": "국토계획법 §67~69(코드 C07·부담구역 지정 시)", "apartment_only": False},
    {"label": "개발부담금", "note": "개발이익환수법(개발이익 환수)", "apartment_only": False},
]


def _line(group: str, label: str, note: str) -> dict[str, Any]:
    # budget_won=0(무목업 — 금액은 사용자/분석엔진이 채움).
    return {"group": group, "label": label, "budget_won": 0, "note": note}


def get_budget_template(method: str | None = None) -> dict[str, Any]:
    """개발방식별 수지 예산 표준 라인아이템 프리셋을 반환한다.

    금액 없음(무목업). 각종부담금은 개발방식(공동주택 여부)에 따라 부과 대상만 포함.
    미지정/미등록 method 는 공통 세트(비-공동주택 부담금)로 폴백(임의 합성 금지).
    """
    m = (method or "").strip().upper()
    is_apartment = m in _APARTMENT_METHODS
    items: list[dict[str, Any]] = [_line(g, lbl, note) for (g, lbl, note) in _COMMON]
    for c in _CHARGES:
        if c["apartment_only"] and not is_apartment:
            continue
        items.append(_line("각종부담금", c["label"], c["note"]))
    # 그룹 순서를 프론트 GROUPS와 동일하게 정렬(안정 정렬 — 입력 순서 보존).
    order = {g: i for i, g in enumerate([
        "토지비", "공사비", "설계감리비", "각종부담금", "판매관리비",
        "보존등기비", "일반관리비", "제세금", "금융비", "예비비",
    ])}
    items.sort(key=lambda it: order.get(it["group"], 99))
    return {
        "method": m or None,
        "method_label": METHOD_LABELS.get(m),
        "is_apartment": is_apartment,
        "items": items,
        "basis": "무목업 — 라벨·구조만 제공, 금액은 사용자 입력/분석엔진이 채움. 부담금 코드는 부담금 엔진과 정합.",
    }
