"""공통 비용 블록 — 토지비/공사비/금융비/기타비 계산 위임."""

from __future__ import annotations

from typing import Any

from app.services.feasibility.construction_cost_engine import calculate_total_construction_cost
from app.services.feasibility.finance_cost_engine import calculate_total_finance_cost
from app.services.feasibility.land_cost_engine import calculate_total_land_cost
from app.services.feasibility.modules.base_module import ModuleInput
from app.services.tax.integrated_tax_engine import calculate_all_taxes
from app.services.tax.project_charges import parse_bool_flag


def compute_land_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 토지비 계산.

    취득세·전용부담금은 통합 세금 엔진(compute_taxes → A01~A03, A08/A09)이
    grand_total_won에 계상하므로 여기서는 제외한다 (이중계상 방지).
    """
    return calculate_total_land_cost(
        total_area_sqm=inp.total_land_area_sqm,
        official_price_per_sqm=inp.official_price_per_sqm,
        price_multiplier=inp.price_multiplier,
        land_category=inp.land_category,
        house_count=inp.house_count,
        is_adjusted_area=inp.is_adjusted_area,
        compensation_won=inp.params.get("compensation_won", 0),
        include_taxes_and_fees=False,
    )


def compute_construction_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 공사비 계산.

    공사비 정밀 분석 결과를 params.construction_cost_override_won 로 주입하면
    수지·사업성(ROI)이 그 공사비를 그대로 사용한다(3자 단일 데이터원 정합).

    ★적산→수지 배선(P2): 층수(inp.floors 또는 params.floor_count_above)·지하층수
    (params.floor_count_below)·구조유형(params.structure_type) 제공 시 적산
    estimate-overview와 동일한 공용 개산식으로 산정(구조계수·지하할증·조경).
    미제공 시 종전 `연면적 × ₩/㎡` 그대로(무회귀).
    """
    override = inp.params.get("construction_cost_override_won")
    if override and float(override) > 0:
        total = int(float(override))
        return {
            "direct": {"total_direct_cost_won": total},
            "indirect": {"total_indirect_cost_won": 0},
            "total_construction_cost_won": total,
            "source": "cost_analysis_override",
        }
    structure_type = inp.params.get("structure_type")
    return calculate_total_construction_cost(
        total_gfa_sqm=inp.total_gfa_sqm,
        building_type=inp.building_type,
        unit_cost_per_sqm=inp.params.get("unit_cost_per_sqm"),
        cost_index_factor=inp.params.get("cost_index_factor", 1.0),
        floor_count_above=(int(inp.floors) if inp.floors else 0) or _param_int(inp, "floor_count_above") or None,
        floor_count_below=_param_int(inp, "floor_count_below") or None,
        structure_type=str(structure_type).strip() if structure_type else None,
    )


def compute_finance_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 금융비 계산."""
    return calculate_total_finance_cost(
        bridge_amount_won=inp.bridge_amount_won,
        bridge_rate=inp.bridge_rate,
        bridge_months=inp.bridge_months,
        pf_amount_won=inp.pf_amount_won,
        pf_rate=inp.pf_rate,
        pf_months=inp.pf_months,
        midpay_amount_won=inp.midpay_amount_won,
        midpay_rate=inp.midpay_rate,
        midpay_months=inp.midpay_months,
    )


def compute_other_cost(inp: ModuleInput) -> dict[str, Any]:
    """기타경비 계산."""
    marketing = inp.params.get("marketing_cost_won", 0)
    management = inp.params.get("management_cost_won", 0)
    reserve = inp.params.get("reserve_cost_won", 0)
    return {
        "marketing_won": marketing,
        "management_won": management,
        "reserve_won": reserve,
        "total_other_cost_won": marketing + management + reserve,
    }


def _param_int(inp: ModuleInput, key: str) -> int:
    """params의 수치 입력을 int로 안전 변환(문자열 숫자 허용, 비수치·음수는 0)."""
    try:
        value = int(float(inp.params.get(key) or 0))
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def apply_auto_estimates(
    inp: ModuleInput,
    land: dict[str, Any],
    construction: dict[str, Any],
    finance: dict[str, Any],
    other: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """금융비·소프트비 자동추정(파라미터 미입력 시에만) — 전 모듈 공용.

    ★감사 결함 수지10 봉합(2026-07-15): 이 로직이 generic_module에만 있어 M01 재개발·
    M02 재건축·M04 지역주택·M08 오피스텔은 params 미입력 시 finance=0·other=0으로
    총사업비가 과소계상돼 ROI가 비현실적으로 과대(과거 "ROI 566%" 패턴)됐다.
    공용 추출로 5개 경로가 같은 표준 가정을 쓴다(한 곳 수정→전역 수렴).
    사용자 명시 입력이 있으면 그 값 우선 — auto_estimated 플래그로 정직 표기.

    Returns: (finance, other) — 자동추정 적용(또는 원본 그대로) dict 쌍.
    """
    # ★리뷰 R1-MEDIUM: 전액 자기자본 사업(의도적 금융비 0)의 표현 경로 — params.all_equity
    #   명시 시 금융비 자동추정을 억제한다(소프트비 추정은 유지 — 자기자본과 무관).
    all_equity = bool(inp.params.get("all_equity"))
    base_cost = float(land["total_land_cost_won"]) + float(construction["total_construction_cost_won"])
    if not all_equity and float(finance.get("total_finance_cost_won") or 0) <= 0 and base_cost > 0:
        months = float(inp.project_months or 30)
        pf_amt = base_cost * 0.70  # 표준 LTV 70%
        # ★W5(갭 감사 P2 봉합): 분할실행(progressive drawdown) 평균잔액 ~50% 기저 —
        #   종전 전액·단리 기저는 정밀입력 경로(finance_cost_engine 분할실행)의 ~2배라
        #   "정밀 입력할수록 ROI가 좋아지는" 역설을 만들었다. 실행 곡선 평균잔액 근사 0.5.
        est_finance = round(pf_amt * 0.055 * (months / 12.0) * 0.5)
        finance = {**finance, "total_finance_cost_won": est_finance, "auto_estimated": True,
                   "estimate_basis": (
                       f"PF 차입 {pf_amt:,.0f}원(토지+공사 LTV70%)×5.5%×{months:.0f}개월"
                       "×평균잔액 50%(분할실행 근사) 자동추정(미입력)"
                   )}
    if float(other.get("total_other_cost_won") or 0) <= 0 and base_cost > 0:
        est_other = round(base_cost * 0.07)  # 설계·감리·분양대행·금융수수료·예비비 통칭 7%
        other = {**other, "total_other_cost_won": est_other, "auto_estimated": True,
                 "estimate_basis": f"소프트비 = (토지+공사) {base_cost:,.0f}원 × 7% 자동추정(설계·감리·분양대행·예비비 통칭, 미입력)"}
    return finance, other


def compute_taxes(
    inp: ModuleInput,
    total_sale_won: int = 0,
    *,
    development_cost_won: int = 0,
) -> dict[str, Any]:
    """세금 일괄 계산.

    ★부담금 상시-0 봉합: A10 개발부담금·C07 기반시설부담금은 엔진에 구현돼 있었으나
    이 배선이 인자를 전달하지 않아 어떤 경로에서도 수지에 기여할 수 없었다(상시 0원).
    - A10: 종료시점 지가(end_land_value_won)는 감정 필요값이라 자동 추정하지 않는다(무날조)
      — params 제공 시에만 활성. 개시지가 기본값=토지 매입가(권위 출처),
      개발비용 기본값=모듈이 계산한 공사비(development_cost_won 인자).
    - C07: 기반시설부담구역 지정 여부(params.in_infra_charge_zone) 게이트를 전달.
    모든 채널의 기본값은 기존 결과와 완전 동일(미제공 시 무회귀).
    """
    purchase_won = int(inp.total_land_area_sqm * inp.official_price_per_sqm * inp.price_multiplier)
    end_land_value_won = _param_int(inp, "end_land_value_won")
    return calculate_all_taxes(
        purchase_won=purchase_won,
        land_category=inp.land_category,
        house_count=inp.house_count,
        is_adjusted=inp.is_adjusted_area,
        area_sqm=inp.total_land_area_sqm,
        official_price_per_sqm=inp.official_price_per_sqm,
        end_land_value_won=end_land_value_won,
        start_land_value_won=_param_int(inp, "start_land_value_won") or purchase_won,
        development_cost_won=_param_int(inp, "development_cost_won") or max(0, development_cost_won),
        project_years=max(0.5, (inp.project_months or 36) / 12.0),
        region_type=inp.region_type,
        sido_name=inp.sido_name,
        sigungu_name=inp.sigungu_name,
        total_households=inp.total_households,
        total_sale_amount_won=total_sale_won,
        total_gfa_sqm=inp.total_gfa_sqm,
        building_type=inp.building_type,
        total_units=inp.total_households,
        # ★C01(부가세 전용 85㎡ 판정) 주의 — avg_area_pyeong은 생산처별 의미 분열 상태:
        #   공급평(build_module_input·precheck) vs 전용평(프론트 수동폼·orchestration·baseline).
        #   여기(공유 소비처)서 전용률을 일괄 환산하면 전용평 경로가 이중 축소돼 과세대상
        #   (전용 85~113㎡)이 날조 면세로 뒤집힌다(2026-07-15 리뷰 라이브 재현). 규약 통일
        #   전까지 임의 환산 금지 — 공급평 생산 경로의 과세 방향(보수) 결함은 통일 후 교정.
        avg_area_sqm=inp.avg_area_pyeong * 3.305785 if inp.avg_area_pyeong else 85.0,
        in_infra_charge_zone=parse_bool_flag(inp.params.get("in_infra_charge_zone")),
    )
