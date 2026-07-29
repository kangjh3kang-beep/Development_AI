"""골든 strata 층화축 — 입력 차원 레지스트리 seed (계획 §12.6).

★1차 층화축 = **토지속성 조합**(지목 × 용도지역 × 산지구분 …). 사업유형은 2차축.
자연녹지 임야라도 보전산지=개발 극히제한 vs 준보전산지=개발행위허가 가능으로 결과값이
뒤바뀌므로, 조합이 1급 커버리지 차원이다.

W0는 **구조를 옳게** 시드하되 값은 얇게(thin) 담는다. 커버리지 원장의 분모 =
**토지속성조합 × 결정변수**(§12.1 교정2·§12.6 스키마4)라는 구조를 여기에 박제하고,
test_coverage_ledger가 이 구조(양 축 존재·카디널리티>0·조건부 트리)를 검증한다.

이 모듈은 값이 아니라 **차원의 존재·조건부 관계**를 고정한다(수시변동 데이터에 안 낡음).
"""

from __future__ import annotations

from typing import Any

# ── 축그룹 A(토지본원) — Tier K(항상 known: VWorld/토지이음 무료) ──
# 28 법정 지목의 seed subset(W0 얇게 — 조합 커버는 W1 샘플러가 확장).
JIMOK: tuple[str, ...] = ("임야", "전", "답", "대", "도로", "구거", "잡종지")

# 용도지역 seed subset(녹지·관리·주거·상업 대표).
ZONE: tuple[str, ...] = (
    "자연녹지지역", "생산녹지지역", "보전녹지지역",
    "계획관리지역", "생산관리지역", "보전관리지역",
    "제1종일반주거지역", "제2종일반주거지역", "제3종일반주거지역",
    "준주거지역", "일반상업지역", "농림지역",
)

# ── 축그룹 C(지목-조건부 세부) — Tier C/S. 산지구분은 지목=임야일 때만 유효 ──
# None = 산지구분 미확정(NEEDS_OFFICIAL_SURVEY 정직표기 — 산림청 공식데이터 유료/미확보).
SANJI_GUBUN: tuple[str | None, ...] = (
    "보전산지_임업용", "보전산지_공익용", "준보전산지", "산지전용제한지역", None,
)

# 농지구분(전/답 조건부).
NONGJI_GUBUN: tuple[str | None, ...] = ("농업진흥구역", "농업보호구역", "진흥지역밖", None)

# ── 조건부 트리(§12.6 스키마1) — naive 곱이 아니라 상위차원 조건부 ──
# 무의미 조합("대 × 보전산지")을 미샘플해 조합폭발을 통제한다.
CONDITIONAL: dict[str, dict[str, tuple[str, ...]]] = {
    "sanji_gubun": {"requires_jimok": ("임야",)},
    "nongji_gubun": {"requires_jimok": ("전", "답")},
}

# ── 결정변수(§12.6 스키마4) — 커버리지 분모의 한 축. 고위험 결정변수를 flip하는 조합이
#    고가치 타깃(§12.6 스키마4). ──
DECISION_VARS: tuple[str, ...] = (
    "개발가부", "실효FAR", "실효BCR", "인허가경로", "부담금집합",
    "매출상한", "세제", "리스크등급", "확보율", "자금수지",
)

# ── 2차 층화축: 사업유형(§12.1 교정1). W0는 placeholder scaffold(미채움 정직표기) ──
BIZ_MODELS: tuple[str, ...] = (
    "신축", "재건축", "재개발", "가로주택정비", "역세권활성화", "도시개발", "산업단지",
)


def is_dimension_applicable(dimension: str, jimok: str | None) -> bool:
    """조건부 트리 판정 — 산지구분/농지구분은 상위 지목 조건 충족 시에만 유효 차원."""
    cond = CONDITIONAL.get(dimension)
    if cond is None:
        return True  # 조건부 아님 → 항상 적용
    return jimok in cond.get("requires_jimok", ())


def landattr_combination_axes() -> dict[str, tuple]:
    """토지속성 조합의 축 정의(1차 층화축). 조합 카디널리티는 조건부 트리로 통제되므로
    naive 곱이 아니다(is_dimension_applicable 참조).
    """
    return {
        "jimok": JIMOK,
        "zone": ZONE,
        "sanji_gubun": SANJI_GUBUN,
        "nongji_gubun": NONGJI_GUBUN,
    }


def coverage_denominator_shape() -> dict[str, Any]:
    """커버리지 원장 분모의 **구조**(값 아님) — 토지속성조합 × 결정변수.

    test_coverage_ledger가 이 구조를 assert한다(coverage %가 낮아도 구조는 옳게).
    bare "100%" 금지 원칙의 자리 — known-unknowns를 별도로 추적할 자리(W4).
    """
    return {
        "primary_axis": "landattr_combination",  # 1차축 = 토지속성 조합
        "secondary_axis": "biz_model",           # 2차축 = 사업유형
        "landattr_axes": landattr_combination_axes(),
        "decision_vars": DECISION_VARS,
        "conditional_tree": CONDITIONAL,
        # 분모 = (유효 토지속성조합) × (결정변수). W0는 축의 존재만 보장.
        "denominator_kind": "landattr_combination x decision_var",
    }
