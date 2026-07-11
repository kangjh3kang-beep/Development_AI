"""유형별 세대·면적 표준(SSOT) — 세대수 산정 계수의 단일 출처 (W1-3).

배경: comprehensive(공급면적 카드)와 feasibility_v2(Top3 추천)가 서로 다른
전용면적·전용률 테이블을 각자 보유해, 동일 GFA에서 세대수가 30% 안팎 어긋나던
이중정의 결함(구 "40 vs 323" 버그 클래스)이 있었다. 본 모듈이 유일한 정본이며
두 소비처 모두 여기서 import 한다(regional_pricing 단일출처와 동일 패턴).

값 채택 근거: 유형별 세분 테이블(comprehensive 계열, M01~M15 전수)을 정본으로
채택 — 일괄 폴백(0.75) 방식보다 주상복합(0.60)·지식산업센터(0.55)·도시형생활주택
(0.65) 등 특수유형의 현실 전용률을 반영한다. 전용면적도 오피스텔 28㎡(원룸형 주력
21~28㎡)·도시형 26㎡(주력 20~30㎡) 등 시장 통계에 부합하는 세분값 유지.

무날조: 미등록 유형은 임의 합성 없이 보수적 공동주택 표준(84㎡·0.75·FAR 250)으로
폴백하며, 신규 유형 추가 시 반드시 이 표에 등재한다(테이블 간 키 불일치 금지 —
tests/test_unit_standards_ssot.py 가 15유형 전수·소비처 동일성을 게이트).
"""
from __future__ import annotations

# ── 개발방식별 전용율 (전용면적 / 공급면적) ──
EXCLUSIVE_AREA_RATIO: dict[str, float] = {
    "M01": 0.75,  # 재개발 (공동주택)
    "M02": 0.75,  # 재건축 (공동주택)
    "M03": 0.65,  # 역세권개발
    "M04": 0.75,  # 지역주택조합
    "M05": 0.70,  # 임대협동조합
    "M06": 0.75,  # 일반분양 (공동주택)
    "M07": 0.60,  # 주상복합
    "M08": 0.55,  # 오피스텔
    "M09": 0.55,  # 지식산업센터
    "M10": 0.85,  # 단독주택
    "M11": 0.85,  # 전원주택
    "M12": 0.80,  # 타운하우스
    "M13": 0.65,  # 도시형생활주택
    "M14": 0.70,  # 공공임대
    "M15": 0.75,  # 민간리츠
}

# ── 개발방식별 평균 전용면적 (m2) ──
AVG_EXCLUSIVE_AREA_SQM: dict[str, float] = {
    "M01": 84, "M02": 84, "M03": 59, "M04": 84, "M05": 49,
    "M06": 84, "M07": 102, "M08": 28, "M09": 50, "M10": 165,
    "M11": 200, "M12": 130, "M13": 26, "M14": 59, "M15": 84,
}

# ── 개발방식별 일반적(전형) 용적률 (%) ──
TYPICAL_FAR_PCT: dict[str, float] = {
    "M01": 250, "M02": 300, "M03": 400, "M04": 250, "M05": 200,
    "M06": 250, "M07": 400, "M08": 500, "M09": 400, "M10": 100,
    "M11": 80, "M12": 150, "M13": 300, "M14": 250, "M15": 300,
}

# 미등록 유형 보수 폴백(공동주택 표준) — 임의 합성 금지, 신규 유형은 표에 등재할 것.
DEFAULT_AVG_EXCLUSIVE_AREA_SQM: float = 84
DEFAULT_EXCLUSIVE_RATIO: float = 0.75
DEFAULT_TYPICAL_FAR_PCT: float = 250


def get_avg_exclusive_area_sqm(dev_type: str) -> float:
    """유형별 평균 전용면적(㎡). 미등록 유형은 84㎡ 보수 폴백."""
    return AVG_EXCLUSIVE_AREA_SQM.get(dev_type, DEFAULT_AVG_EXCLUSIVE_AREA_SQM)


def get_exclusive_ratio(dev_type: str) -> float:
    """유형별 전용률(전용/공급). 미등록 유형은 0.75 보수 폴백."""
    return EXCLUSIVE_AREA_RATIO.get(dev_type, DEFAULT_EXCLUSIVE_RATIO)


def get_typical_far_pct(dev_type: str) -> float:
    """유형별 전형 용적률(%). 미등록 유형은 250% 보수 폴백."""
    return TYPICAL_FAR_PCT.get(dev_type, DEFAULT_TYPICAL_FAR_PCT)


# ── 건물유형별 분양(전용)면적 / 연면적(GFA) 비율 (P2 전용률 정본 수렴, 2026-07-11) ──
# ★위 EXCLUSIVE_AREA_RATIO/get_exclusive_ratio(전용/공급, M코드)와는 분모가 다른
# 별개 물리량이므로 절대 병합 금지(값도 상이 — 예: 오피스텔 0.55 vs 0.70). 연면적(GFA)은
# 주차장 등 기타공용면적을 포함하므로, "분양(전용)면적÷연면적" 비율이 "전용면적÷공급면적"
# 전용률보다 통상 낮게 나온다.
#
# 정본: 이 표가 유일 소스 — project_pipeline._run_design은 여기서 get_sellable_efficiency를
# import해 사용한다(구 자체 이중정의 _SELLABLE_EFFICIENCY_BY_TYPE는 제거됨).
# 프론트 미러(apps/web/lib/orchestration/node-body-builders.ts의
# SELLABLE_EFFICIENCY_BY_TYPE)는 교차언어라 import 불가 — 값 동기는
# tests/test_sellable_efficiency_contract.py ↔ node-body-builders.test.ts의
# "G4 계약" describe로 고정한다. 한쪽을 바꾸면 반드시 반대쪽과 두 계약 테스트를 함께 갱신할 것.
SELLABLE_EFFICIENCY_BY_BUILDING_TYPE: dict[str, float] = {
    "아파트": 0.75,
    "다세대주택": 0.78,
    "오피스텔": 0.70,
    "공동주택": 0.76,
    "근린생활시설": 0.70,
}

# 유형 미상 시 기본 분양/연면적 비율 — 프론트 DEFAULT_SELLABLE_EFFICIENCY와 동치 계약(위 주석 참조).
DEFAULT_SELLABLE_EFFICIENCY: float = 0.75


def get_sellable_efficiency(building_type: str) -> float:
    """건물유형별 분양(전용)/연면적(GFA) 비율. 미등록 유형은 표준 0.75 보수 폴백."""
    return SELLABLE_EFFICIENCY_BY_BUILDING_TYPE.get(building_type, DEFAULT_SELLABLE_EFFICIENCY)
