"""시니어 적산(QS)전문가 정량 평가기 — 기준선편차·법정요율·단가신뢰도·예비비·공종구성비.

quantity_surveyor spec(qs.baseline_deviation·qs.indirect_rate_compliance·
qs.unit_price_reliability·qs.contingency_reserve·qs.category_composition)을 실제 입력으로
평가한다. 결정론·무DB: 필요한 입력이 없으면 해당 평가는 생략(가짜 수치 금지·정직 강등).

입력(context['inputs']):
  - cost_per_sqm·floors·avg_unit_sqm·is_housing(기본 True): 기본형건축비 기준선 편차.
  - general_mgmt_rate·profit_rate(분율 0~1): 12단계 원가계산 적용요율(origin_cost_calculator
    applied_rates 재사용) — 일반관리비율·이윤율 법정 상한 검증.
  - tier_t3_count·tier_item_count: BOQ 항목 중 T3(내장폴백) 단가 비중.
  - contingency_reserve_won·total_project_cost_won: 예비비율.
  - category_totals(dict[str, float]): 공종별(WB 또는 원시 work_code) 소계 — 최대 비중 공종 점검.
"""

from __future__ import annotations

from app.services.cost.cost_monte_carlo import RISK as _MC_RISK
from app.services.cost.origin_cost_calculator import RATES_2026
from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    num,
)

# ── 기본형건축비 기준선 편차 임계(R1) ──
BASELINE_DEVIATION_WARN = 0.15   # |편차| 15% 초과 → WARN
BASELINE_DEVIATION_BLOCK = 0.30  # |편차| 30% 초과 → BLOCK

# ── 일반관리비율·이윤율 법정 상한(R2) — origin_cost_calculator RATES_2026 재사용(이중정의 금지) ──
GENERAL_MGMT_RATE_CAP = 0.06       # 일반관리비율 법정 상한(건설업 6%)
PROFIT_RATE_CAP = RATES_2026["profit"]  # 이윤율 법정 상한(15% — 2026 적용요율과 동일 상한)

# ── 단가 tier 신뢰도(R3) ──
TIER_T3_RATIO_WARN = 0.50  # T3(내장폴백) 비중 50% 초과 → WARN

# ── 예비비율(R4) — cost_monte_carlo design_chg 리스크분포 재사용(이중정의 금지) ──
CONTINGENCY_RATIO_WARN = 0.03  # 예비비율 3% 미만 → WARN

# ── 공종구성비 이상(R5) ──
CATEGORY_SHARE_WARN = 0.60  # 단일 공종 비중 60% 초과 → WARN(실무 통상 골조 30~45% 내외)


def _eval_baseline_deviation(inputs: dict) -> RuleEvaluation | None:
    """㎡당 공사비 vs 기본형건축비 기준선(get_baseline 재사용) — |편차| 임계 판정(결측 생략)."""
    cost_per_sqm = num(inputs, "cost_per_sqm")
    floors = num(inputs, "floors")
    avg_unit_sqm = num(inputs, "avg_unit_sqm")
    is_housing = inputs.get("is_housing", True) if isinstance(inputs, dict) else True
    if cost_per_sqm is None or floors is None or avg_unit_sqm is None or not is_housing:
        return None
    if cost_per_sqm <= 0 or floors <= 0 or avg_unit_sqm <= 0:
        return None

    from app.services.cost.basic_building_cost import get_baseline

    baseline = get_baseline(int(floors), avg_unit_sqm)
    bv = baseline.get("value")
    if bv is None:
        return None  # 기준선 미가용(구간 미시드) — 정직 생략(무날조)

    dev = (cost_per_sqm - bv) / bv
    verdict = BLOCK if abs(dev) > BASELINE_DEVIATION_BLOCK else (
        WARN if abs(dev) > BASELINE_DEVIATION_WARN else PASS)
    return RuleEvaluation(
        rule_id="qs.baseline_deviation", label="기본형건축비 기준선 편차",
        value=round(dev * 100, 2), unit="%", verdict=verdict,
        threshold=f"|편차|≤{BASELINE_DEVIATION_WARN*100:.0f}%(WARN)·≤{BASELINE_DEVIATION_BLOCK*100:.0f}%(BLOCK)",
        basis=baseline.get("basis", "국토교통부 기본형건축비 고시"),
        detail=(f"실행단가 {cost_per_sqm:,.0f}원/㎡ vs 기준선 {bv:,.0f}원/㎡ "
                f"(편차 {dev*100:+.2f}%)"))


def _eval_indirect_rate_compliance(inputs: dict) -> list[RuleEvaluation]:
    """일반관리비율·이윤율 법정 상한(applied_rates 재사용) — 초과 시 BLOCK(결측 생략)."""
    out: list[RuleEvaluation] = []
    gm = num(inputs, "general_mgmt_rate")
    if gm is not None and gm >= 0:
        out.append(RuleEvaluation(
            rule_id="qs.general_mgmt_cap", label="일반관리비율",
            value=round(gm * 100, 2), unit="%",
            verdict=BLOCK if gm > GENERAL_MGMT_RATE_CAP else PASS,
            threshold=f"≤{GENERAL_MGMT_RATE_CAP*100:.0f}%",
            basis=("국가를 당사자로 하는 계약에 관한 법률 시행규칙 제7조(원가계산에 의한 예정가격의 "
                   "결정기준) 일반관리비율 상한"),
            detail=(f"적용 일반관리비율 {gm*100:.2f}% vs 법정 상한 {GENERAL_MGMT_RATE_CAP*100:.0f}%"
                    + (" — 상한 초과" if gm > GENERAL_MGMT_RATE_CAP else ""))))
    profit = num(inputs, "profit_rate")
    if profit is not None and profit >= 0:
        out.append(RuleEvaluation(
            rule_id="qs.profit_cap", label="이윤율",
            value=round(profit * 100, 2), unit="%",
            verdict=BLOCK if profit > PROFIT_RATE_CAP else PASS,
            threshold=f"≤{PROFIT_RATE_CAP*100:.0f}%",
            basis=("기획재정부 계약예규 정부 입찰·계약 집행기준(원가계산에 의한 예정가격 작성준칙) "
                   "이윤율 상한"),
            detail=(f"적용 이윤율 {profit*100:.2f}% vs 법정 상한 {PROFIT_RATE_CAP*100:.0f}%"
                    + (" — 상한 초과" if profit > PROFIT_RATE_CAP else ""))))
    return out


def _eval_unit_price_reliability(inputs: dict) -> RuleEvaluation | None:
    """단가 tier 분포(T3 비중) — 50% 초과 시 WARN(결측·분모0 생략)."""
    t3 = num(inputs, "tier_t3_count")
    total = num(inputs, "tier_item_count")
    if t3 is None or total is None or total <= 0 or t3 < 0:
        return None
    t3 = min(t3, total)  # 비정합 클램프(T3 개수는 전체를 넘을 수 없음)
    ratio = t3 / total
    return RuleEvaluation(
        rule_id="qs.unit_price_reliability", label="단가 T3(내장폴백) 비중",
        value=round(ratio * 100, 1), unit="%",
        verdict=WARN if ratio > TIER_T3_RATIO_WARN else PASS,
        threshold=f"≤{TIER_T3_RATIO_WARN*100:.0f}%",
        basis="PropAI 단가 SSOT(unit_price_repository) T1~T3 계층 정책",
        detail=(f"T3(내장폴백) {t3:.0f}/{total:.0f}항목({ratio*100:.1f}%)"
                + (" — 공공고시·시장단가 교차검증 권장" if ratio > TIER_T3_RATIO_WARN else "")))


def _eval_contingency_reserve(inputs: dict) -> RuleEvaluation | None:
    """예비비율(총사업비 대비) — 3% 미만 WARN(결측·분모0 생략)."""
    contingency = num(inputs, "contingency_reserve_won")
    total = num(inputs, "total_project_cost_won")
    if contingency is None or total is None or total <= 0 or contingency < 0:
        return None
    ratio = contingency / total
    mc_mode = _MC_RISK["design_chg"][1] * 100  # 설계변경 삼각분포 최빈치(%)
    return RuleEvaluation(
        rule_id="qs.contingency_reserve", label="예비비율",
        value=round(ratio * 100, 2), unit="%",
        verdict=WARN if ratio < CONTINGENCY_RATIO_WARN else PASS,
        threshold=f"≥{CONTINGENCY_RATIO_WARN*100:.0f}%",
        basis=f"PropAI 공사비 몬테카를로 리스크모델(설계변경 삼각분포 최빈 {mc_mode:.0f}%)",
        detail=(f"예비비 {contingency:,.0f}원 / 총사업비 {total:,.0f}원 = {ratio*100:.2f}% "
                f"vs 최소 {CONTINGENCY_RATIO_WARN*100:.0f}%"
                + (" — 설계변경 리스크 대비 과소" if ratio < CONTINGENCY_RATIO_WARN else "")))


def _eval_category_composition(inputs: dict) -> RuleEvaluation | None:
    """공종별 소계 구성비 — 단일 공종 60% 초과 WARN(결측·항목부족 생략)."""
    totals = inputs.get("category_totals") if isinstance(inputs, dict) else None
    if not isinstance(totals, dict):
        return None
    amounts: dict[str, float] = {}
    for k, v in totals.items():
        if isinstance(v, bool):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            amounts[str(k)] = f
    if len(amounts) < 2:
        return None  # 집계 불충분(무목업)
    total = sum(amounts.values())
    if total <= 0:
        return None
    top_key, top_amt = max(amounts.items(), key=lambda kv: kv[1])

    try:
        from app.services.cost.work_breakdown import WB_CATEGORIES
        name = WB_CATEGORIES.get(top_key, top_key)
    except Exception:  # noqa: BLE001 — 표시명 조회 실패해도 판정 자체는 유지
        name = top_key

    share = top_amt / total
    return RuleEvaluation(
        rule_id="qs.category_composition", label="최대 공종 구성비",
        value=round(share * 100, 1), unit="%",
        verdict=WARN if share > CATEGORY_SHARE_WARN else PASS,
        threshold=f"≤{CATEGORY_SHARE_WARN*100:.0f}%(단일 공종)",
        basis="한국 건축공사 표준 대공종(WB) 구성비 실무 관례(골조공사 통상 30~45% 내외)",
        detail=(f"{name}({top_key}) {top_amt:,.0f}원 / 총 {total:,.0f}원 = {share*100:.1f}%"
                + (" — 물량·단가 오류 또는 특수구조 여부 확인 권장" if share > CATEGORY_SHARE_WARN else "")))


def evaluate_qs(inputs: dict) -> list[RuleEvaluation]:
    """기준선편차·법정요율·단가신뢰도·예비비·공종구성비 게이트(결측 생략·무목업)."""
    out: list[RuleEvaluation] = []
    if not isinstance(inputs, dict):
        return out

    bd = _eval_baseline_deviation(inputs)
    if bd is not None:
        out.append(bd)
    out.extend(_eval_indirect_rate_compliance(inputs))
    upr = _eval_unit_price_reliability(inputs)
    if upr is not None:
        out.append(upr)
    cr = _eval_contingency_reserve(inputs)
    if cr is not None:
        out.append(cr)
    cc = _eval_category_composition(inputs)
    if cc is not None:
        out.append(cc)
    return out
