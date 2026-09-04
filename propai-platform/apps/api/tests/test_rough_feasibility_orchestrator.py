"""사업성 개략수지 통합 오케스트레이터 테스트.

네트워크·엔진 의존부(통합컨텍스트·추천·탁상감정·분양단가·엔진비율)만 stub으로 대체하고,
순수 계산 엔진(land_cost_engine·construction_cost_engine·aggregation_engine·cashflow)은
실제로 돌려 조합·20%마진·overrides·DCF·정직degrade를 검증한다.

검증 항목:
 ① 20% 마진 필드 산출        (test_margin_20pct_field)
 ② overrides 교체 재계산      (test_overrides_replace_and_recompute)
 ③ 미확보 축 degraded_notes   (test_missing_axis_degrades)
 ④ 월별 DCF rows 생성         (test_monthly_dcf_rows)
 ⑤ N=1 / 다필지               (test_single_parcel / test_multiparcel_seeds_integrated_area)
 라우터 스모크                (test_router_rough_scenario_smoke)
"""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.feasibility import rough_feasibility_orchestrator as orch
from app.services.feasibility.modules.base_module import ModuleInput

# ─────────────────────────────────────────────────────────────────────────────
# 공용 stub 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


def _module_input(dev: str = "M06", land_area: float = 1000.0,
                  far: float = 200.0, official: float = 3_000_000) -> ModuleInput:
    gfa = land_area * far / 100.0
    return ModuleInput(
        development_type=dev,
        total_land_area_sqm=land_area,
        official_price_per_sqm=official,
        price_multiplier=1.1,
        total_gfa_sqm=gfa,
        total_households=max(1, int(gfa / 84)),
        avg_sale_price_per_pyeong=15_000_000,
        avg_area_pyeong=34.0,
        sale_ratio=0.95,
        equity_won=10_000_000_000,
    )


def _fake_reco(*, land_area: float = 1000.0, far: float = 200.0, dev: str = "M06",
               official: float = 3_000_000, area_reliable: bool = True,
               land_reliable: bool = True) -> dict:
    """auto_recommend_top3 반환 형태를 흉내낸 최소 dict."""
    rec = {
        "development_type": dev,
        "type_name": "일반분양",
        "feasibility": {"total_cost_won": 1, "total_revenue_won": 1, "net_profit_won": 0},
        "unit_summary": {"total_gfa_sqm": land_area * far / 100.0,
                         "total_households": 100, "avg_area_pyeong": 34.0},
        "input_used": _module_input(dev, land_area, far, official),
        "composite_score": 80.0,
    }
    return {
        "address": "서울특별시 강남구 역삼동 736",
        "zone_type": "제2종일반주거지역",
        "land_area_sqm": land_area,
        "effective_far_pct": far,
        "recommendations": [rec],
        "all_results": [rec],
        "land_price_reliable": land_reliable,
        "area_reliable": area_reliable,
        "scenario_status": "actual",
    }


def _stub_happy(monkeypatch, *, sale_price=40_000_000, integrated=None,
                desk_ok=True, appraised=5_000_000, stub_saleprice=True):
    """행복경로 stub 일괄 설치 — 통합/추천/탁상감정/분양단가/엔진비율.

    stub_saleprice=False면 _resolve_sale_price_per_pyeong는 stub하지 않아, 실거래(MOLIT)
    직접조회 경로(HIGH-1)를 실제로 태울 수 있다(하위 _sigungu5_from_address·_trade_per_pyeong를
    테스트에서 개별 stub).
    """

    async def _fake_integrated(parcels):
        return integrated

    async def _fake_auto(**kwargs):
        _fake_auto.calls.append(kwargs)
        return _fake_reco()

    _fake_auto.calls = []

    async def _fake_desk(**kwargs):
        if not desk_ok:
            return {"ok": False}
        return {"ok": True, "appraised_price_per_sqm": appraised,
                "appraised_total_won": int(appraised * (kwargs.get("area_sqm") or 0)),
                "evidence": {"evidence": [{"label": "채택 단가"}]},
                "source": "NED 토지특성", "confidence": 0.8}

    async def _fake_price(*, db, site_id, dev_type, region, address):
        if sale_price is None:
            return None, "unavailable", "분양단가 미확보", "분양단가: 실거래·지역시세 모두 실패 — 미산출(무목업)"
        return int(sale_price), "지역 시세 테이블(sigungu)", "지역×유형 시장표준 시세", None

    def _fake_ratios(input_used):
        return 0.08, 0.04, None

    monkeypatch.setattr(orch, "build_integrated_context", _fake_integrated)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)
    monkeypatch.setattr(orch, "desk_appraisal", _fake_desk)
    if stub_saleprice:
        monkeypatch.setattr(orch, "_resolve_sale_price_per_pyeong", _fake_price)
    monkeypatch.setattr(orch, "_engine_cost_ratios", _fake_ratios)
    return _fake_auto


# ─────────────────────────────────────────────────────────────────────────────
# ① 20% 마진 필드
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_margin_20pct_field(monkeypatch):
    _stub_happy(monkeypatch)
    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")

    summary = out["summary"]
    margin = out["margin"]
    assert summary["total_cost_won"] is not None and summary["total_cost_won"] > 0
    # developer_profit = 총사업비 × 0.20
    assert margin["rate_pct"] == 20.0
    assert margin["developer_profit_won"] == round(summary["total_cost_won"] * 0.20)
    # 목표매출(역산) = 총사업비 × 1.2
    assert margin["target_revenue_won"] == round(summary["total_cost_won"] * 1.2)
    # 실분양수입 기반 net_profit·roi 도 별도 존재(마진과 분리)
    assert summary["net_profit_won"] == summary["total_revenue_won"] - summary["total_cost_won"]
    assert summary["grade"] in "ABCDEF"
    # 총사업비 = 토지+공사+금융+제경비+부담금(B/C단계 시행사 부담).
    # (종전 불변식 '토지+공사+금융+제경비'는 부담금 상시-0 결함을 그대로 고정한 것 — 교정.
    #  취득세는 토지비에 포함돼 charges_won에 미포함(이중계상 없음))
    cb = out["cost_breakdown"]
    assert cb["charges_won"] is not None and cb["charges_won"] > 0
    assert (cb["land_won"] + cb["construction_won"] + cb["finance_won"] + cb["other_won"]
            + cb["charges_won"] == summary["total_cost_won"])
    # charges 블록 정합: 합계 = 공사단계 + 분양단계, 수분양자 부담분은 합계에서 제외 확인
    charges = out["charges"]
    assert charges["total_won"] == cb["charges_won"]
    assert charges["total_won"] == charges["construction_stage_won"] + charges["sale_stage_won"]
    buyer_items_sum = sum(
        it["amount_won"] for it in charges["items"] if it.get("borne_by") == "buyer"
    )
    assert charges["buyer_borne_total_won"] == buyer_items_sum
    assert charges["total_won"] + buyer_items_sum == sum(it["amount_won"] for it in charges["items"])
    # 리뷰 P2-2: C01 부가세 면세기준은 '전용 85㎡' — M06 표준 전용 84㎡는 면세여야 한다.
    # (공급면적 112㎡를 잘못 전달하면 분양수입의 ~2.4%가 날조 과세로 계상됨)
    c01 = next(it for it in charges["items"] if it["code"] == "C01")
    assert c01["amount_won"] == 0


@pytest.mark.asyncio
async def test_margin_rate_override(monkeypatch):
    _stub_happy(monkeypatch)
    out = await orch.build_rough_scenario(
        address="서울특별시 강남구 역삼동 736", overrides={"margin_rate_pct": 15},
    )
    assert "margin_rate_pct" in out["overrides_applied"]
    assert out["margin"]["rate_pct"] == 15
    assert out["margin"]["developer_profit_won"] == round(out["summary"]["total_cost_won"] * 0.15)


# ─────────────────────────────────────────────────────────────────────────────
# ② overrides 교체 후 재계산
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_overrides_replace_and_recompute(monkeypatch):
    _stub_happy(monkeypatch)
    base = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")

    out = await orch.build_rough_scenario(
        address="서울특별시 강남구 역삼동 736",
        overrides={
            "land_cost_won": 9_000_000_000,
            "construction_unit_won": 3_500_000,
            "sale_price_per_pyeong": 55_000_000,
            "construction_months": 30,
        },
    )
    applied = out["overrides_applied"]
    for k in ("land_cost_won", "construction_unit_won", "sale_price_per_pyeong", "construction_months"):
        assert k in applied

    # 토지비: 사용자 지정값으로 교체 + source 표기
    assert out["land_cost"]["total_won"] == 9_000_000_000
    assert out["land_cost"]["source"] == "user_override"
    # 분양단가: 사용자 지정값으로 교체
    assert out["revenue"]["sale_price_per_pyeong"] == 55_000_000
    assert out["revenue"]["source"] == "user_override"
    # 공사비 단가: 사용자 지정단가 반영(직접단가 == override)
    assert out["construction_cost"]["unit_per_sqm_won"] == 3_500_000
    assert out["construction_cost"]["source"] == "user_override"
    # 재계산으로 총사업비가 baseline과 달라짐
    assert out["summary"]["total_cost_won"] != base["summary"]["total_cost_won"]


# ─────────────────────────────────────────────────────────────────────────────
# ③ 미확보 축 → degraded_notes (무목업)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_missing_axis_degrades(monkeypatch):
    # 탁상감정 실패 + 공시지가 0 → 토지비 미확보. 분양단가 실패 → 분양수입 미확보.
    async def _fake_auto(**kwargs):
        return _fake_reco(official=0, land_reliable=False)

    _stub_happy(monkeypatch, sale_price=None, desk_ok=False)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)

    out = await orch.build_rough_scenario(address="강원도 어딘가 산 1")

    assert out["land_cost"]["total_won"] is None
    assert out["revenue"]["total_won"] is None
    # 핵심 축 결측 → 총사업비·마진·현금흐름 미산출(가짜 0 금지)
    assert out["summary"]["total_cost_won"] is None
    assert out["margin"]["developer_profit_won"] is None
    assert out["cashflow"] is None
    assert out["degraded_notes"], "미확보 사유가 degraded_notes에 남아야 함"


@pytest.mark.asyncio
async def test_no_recommendations_block(monkeypatch):
    """특이부지 BLOCK 등으로 후보 미생성 → 정직 강등 응답(키 고정)."""
    async def _fake_integrated(parcels):
        return None

    async def _fake_auto(**kwargs):
        return {
            "address": "서울 어딘가",
            "zone_type": "자연녹지지역",
            "land_area_sqm": 500,
            "recommendations": [],
            "all_results": [],
            "honest_disclosure": "통상 절차로 해결 불가능한 제약이 포함되어 개발규모를 산정하지 않습니다.",
            "special_parcel": {"developability": "BLOCKED"},
        }

    monkeypatch.setattr(orch, "build_integrated_context", _fake_integrated)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)

    out = await orch.build_rough_scenario(address="서울 어딘가")
    assert out["summary"]["total_cost_won"] is None
    assert out["cashflow"] is None
    assert out["degraded_notes"]
    assert out.get("special_parcel", {}).get("developability") == "BLOCKED"


# ─────────────────────────────────────────────────────────────────────────────
# ④ 월별 DCF rows
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_monthly_dcf_rows(monkeypatch):
    _stub_happy(monkeypatch)
    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")

    cf = out["cashflow"]
    assert cf is not None
    rows = cf["monthly_rows"]
    assert isinstance(rows, list) and len(rows) > 0
    for r in rows[:3]:
        assert {"month", "inflow", "outflow", "cumulative"} <= set(r.keys())
    # summary: npv·irr·peak·payback 키 노출(값은 상황따라 None 가능)
    assert isinstance(out["summary"]["npv_won"], int)
    assert "irr_pct" in out["summary"]
    assert "payback_month" in out["summary"]
    assert "peak_negative_cashflow" in cf["summary"]
    # ★소비처 배선 회귀가드(P2): orchestrator가 실제로 무차입 NPV를 쓰는지 — 출력 npv_won이
    #   레버드 rows 재계산 NPV보다 작아야 한다(자기자본/대출 유입 미포함). 레버드 인라인으로
    #   되돌리면 이 단언이 실패해 회귀를 잡는다(헬퍼 단위테스트가 못 잡던 배선 갭 봉합).
    _r_ann = cf["summary"]["discount_rate_annual_pct"] / 100
    _rm = (1 + _r_ann) ** (1 / 12) - 1
    _npv_levered = round(sum(
        float((rr.get("inflow", 0) or 0) - (rr.get("outflow", 0) or 0))
        / ((1 + _rm) ** (rr.get("month", 0) or 0)) for rr in rows))
    if cf["summary"].get("equity_in_total", 0) > 0:
        assert out["summary"]["npv_won"] < _npv_levered


@pytest.mark.asyncio
async def test_discount_rate_override_changes_npv(monkeypatch):
    _stub_happy(monkeypatch)
    base = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")
    hi = await orch.build_rough_scenario(
        address="서울특별시 강남구 역삼동 736", overrides={"discount_rate_pct": 20},
    )
    assert "discount_rate_pct" in hi["overrides_applied"]
    assert hi["cashflow"]["summary"]["discount_rate_annual_pct"] == 20.0
    # 할인율↑ → NPV 변화(동일 현금흐름)
    assert hi["summary"]["npv_won"] != base["summary"]["npv_won"]


def test_npv_uses_unlevered_fcf_not_levered_rows():
    """★P0 회귀가드: NPV는 무차입 프로젝트 FCF(unlevered_netflows) 할인이어야 한다.

    레버드 월별 rows의 net(=inflow−outflow)에는 자기자본·대출 유입이 양(+)으로 담겨,
    할인하면 자기자본 전액이 순가치로 새어 NPV가 과대된다(은행 KPI 왜곡). 이 테스트가
    없어서 오염 NPV가 CI를 통과했었다(리뷰 P2). unlevered 스트림과 레버드 rows를 대조해 고정.
    """
    from app.services.feasibility.cashflow_generator import (
        CashflowGenerator,
        npv_from_netflows,
    )

    cf = CashflowGenerator().generate_monthly_cashflow(
        land_cost=5_000_000_000, construction_cost=5_000_000_000, construction_months=12,
        total_revenue=15_000_000_000, sale_start_month=12, sale_duration_months=6,
        equity_ratio=1.0,
    )
    unl = cf["unlevered_netflows"]
    # 무차입 FCF: 월0은 토지 유출(음수)·자기자본 유입 없음.
    assert unl[0] == -5_000_000_000
    # 레버드 rows에는 자기자본 유입이 존재(오염원).
    assert cf["summary"]["equity_in_total"] > 0

    npv_unlevered = npv_from_netflows(unl, 0.06)
    rm = (1.06) ** (1 / 12) - 1
    npv_levered = round(sum(
        float(r.get("net") if r.get("net") is not None
              else (r.get("inflow", 0) or 0) - (r.get("outflow", 0) or 0))
        / ((1 + rm) ** (r.get("month", 0) or 0)) for r in cf["rows"]))
    # ★핵심: 무차입 NPV < 레버드(오염) NPV — 자기자본 할인분만큼 작다(오염 제거 증명).
    assert npv_unlevered < npv_levered
    # 빈 스트림은 정직 None.
    assert npv_from_netflows([], 0.06) is None


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ N=1 / 다필지
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_single_parcel(monkeypatch):
    """단일(통합 None) — 추천이 산출한 면적/용도/실효FAR 사용."""
    _stub_happy(monkeypatch, integrated=None)
    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")
    assert out["inputs"]["land_area_sqm"] == 1000.0
    assert out["inputs"]["parcel_count"] == 1
    # GFA = 면적 × 실효FAR / 100 = 1000 × 200 / 100 = 2000
    assert out["inputs"]["gfa_sqm"] == 2000.0


@pytest.mark.asyncio
async def test_multiparcel_seeds_integrated_area(monkeypatch):
    """다필지 — 통합면적/우세용도/blended FAR가 inputs·시드에 반영."""
    integrated = {"total_area_sqm": 2000.0, "dominant_zone": "제3종일반주거지역",
                  "blended_far_eff_pct": 250.0, "parcel_count": 3}
    fake_auto = _stub_happy(monkeypatch, integrated=integrated)

    parcels = [{"area_sqm": 800}, {"area_sqm": 700}, {"area_sqm": 500}]
    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736", parcels=parcels)

    assert out["inputs"]["land_area_sqm"] == 2000.0
    assert out["inputs"]["zone_type"] == "제3종일반주거지역"
    assert out["inputs"]["effective_far_pct"] == 250.0
    assert out["inputs"]["parcel_count"] == 3
    # GFA = 2000 × 250 / 100 = 5000
    assert out["inputs"]["gfa_sqm"] == 5000.0
    # 추천 호출에 통합면적이 시드로 전달됨
    assert fake_auto.calls and fake_auto.calls[0]["land_area_sqm"] == 2000.0


@pytest.mark.asyncio
async def test_a2_usable_adopted_for_gfa_gross_for_land_cost(monkeypatch):
    """★A-2(배선 P1 — usable 면적 전파) 회귀 — GFA/개발규모는 usable(land_area_effective_sqm),
    토지비 산정은 gross(total_area_sqm) 채택(comprehensive_analysis_service F2/P0-2(c)와 동일
    이원화 원칙 — test_f2_land_cost_gross_basis.py 스타일). 도로 지목 혼입 다필지:
    gross=2000㎡(대 1600+도로 400), usable=1600㎡(도로 제외)."""
    integrated = {
        "total_area_sqm": 2000.0, "land_area_effective_sqm": 1600.0,
        "dominant_zone": "제3종일반주거지역", "blended_far_eff_pct": 200.0, "parcel_count": 2,
    }
    _stub_happy(monkeypatch, integrated=integrated)

    # 실제 토지비 계산(land_cost_engine)까지는 타되, _resolve_land_cost가 받은 land_area 인자를
    # 스파이로 캡쳐해 '토지비는 gross로 호출됐다'를 산식 복제 없이 검증한다.
    land_cost_calls: list[float] = []
    orig_resolve = orch._resolve_land_cost

    async def _spy_resolve_land_cost(*, address, land_area, official_price, land_price_reliable):
        land_cost_calls.append(land_area)
        return await orig_resolve(
            address=address, land_area=land_area, official_price=official_price,
            land_price_reliable=land_price_reliable,
        )

    monkeypatch.setattr(orch, "_resolve_land_cost", _spy_resolve_land_cost)

    out = await orch.build_rough_scenario(
        address="서울특별시 강남구 역삼동 736",
        parcels=[{"area_sqm": 1600, "land_category": "대"}, {"area_sqm": 400, "land_category": "도로"}],
    )

    # GFA/개발규모(land_area_sqm) = usable(1600) 채택.
    assert out["inputs"]["land_area_sqm"] == 1600.0
    assert out["inputs"]["gfa_sqm"] == 3200.0  # 1600 * 200 / 100

    # 이원화 근거 additive 노출(양 면적 병기).
    basis = out["inputs"]["land_area_basis"]
    assert basis["gross_sqm"] == 2000.0
    assert basis["usable_sqm"] == 1600.0
    assert basis["gfa_sqm_basis"] == "usable"
    assert basis["land_cost_basis"] == "gross"

    # 토지비 산정에는 gross(2000)가 전달됐다 — usable(1600) 아님(취득원가 축소 방지).
    assert land_cost_calls == [2000.0]


@pytest.mark.asyncio
async def test_dev_type_specified_uses_it(monkeypatch):
    """dev_type 지정 시 해당 유형 사용(자동 Top1 대체 아님)."""
    async def _fake_auto(**kwargs):
        r = _fake_reco()
        # all_results에 M08 후보 추가
        alt = dict(r["recommendations"][0])
        alt = {**alt, "development_type": "M08", "type_name": "오피스텔",
               "input_used": _module_input("M08", 1000.0, 200.0, 3_000_000)}
        base = r
        base["all_results"] = [r["recommendations"][0], alt]
        return base

    _stub_happy(monkeypatch)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)

    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736", dev_type="M08")
    assert out["inputs"]["dev_type"] == "M08"


# ─────────────────────────────────────────────────────────────────────────────
# ★HIGH-1: site_id 없이 주변 실거래(MOLIT)로 분양단가를 1순위로 (사용자요구 핵심)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_high1_trade_sale_price_without_site_id(monkeypatch):
    """site_id 없이도 주소→시군구5→주변 실거래(MOLIT)로 분양단가를 잡는다(초록·비추정)."""
    from app.services.sales.pricing.suggest import _JEONYULRYUL, _PREMIUM

    _stub_happy(monkeypatch, stub_saleprice=False)  # 분양단가만 실경로로

    async def _fake_sigungu5(address):
        return "11680"  # 강남구 시군구 5자리(주소 지오코딩 대체)

    async def _fake_trade(sigungu5, dong, prop_type):
        # 전용 평당가 중앙값(만원): 동 6,000(표본 30) / 시군구 5,800(표본 120)
        return {"dong": {"median": 6000, "n": 30}, "sigungu": {"median": 5800, "n": 120}}

    monkeypatch.setattr(orch, "_sigungu5_from_address", _fake_sigungu5)
    monkeypatch.setattr("app.services.sales.pricing.suggest._trade_per_pyeong", _fake_trade)

    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")
    rev = out["revenue"]
    # 실거래(MOLIT) 출처 — 초록 배지 대상(추정·비실거래 토큰 없음)
    assert rev["source"] == "주변 실거래(MOLIT)"
    assert "추정" not in rev["source"] and "비실거래" not in rev["source"]
    # 분양단가 = 동 중앙값(전용) × 전용률 × 신축 프리미엄 → 공급 평당가(원/평)
    expected = int(round(6000 * _JEONYULRYUL * _PREMIUM["base"] * 10000))
    assert rev["sale_price_per_pyeong"] == expected
    # 실거래 경로는 '추정' degraded를 남기지 않는다(정직)
    assert not any("추정" in n for n in out["degraded_notes"])


@pytest.mark.asyncio
async def test_high1_small_sample_falls_back_to_regional_estimate(monkeypatch):
    """실거래 표본 부족(<_MIN_TRADE_SAMPLES)이면 지역 시세표로 폴백하고 '추정'을 명시한다."""
    _stub_happy(monkeypatch, stub_saleprice=False)

    async def _fake_sigungu5(address):
        return "11680"

    async def _tiny_trade(sigungu5, dong, prop_type):
        return {"dong": {"median": 6000, "n": 2}, "sigungu": {"median": 5800, "n": 3}}  # 표본<5

    monkeypatch.setattr(orch, "_sigungu5_from_address", _fake_sigungu5)
    monkeypatch.setattr("app.services.sales.pricing.suggest._trade_per_pyeong", _tiny_trade)

    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")
    rev = out["revenue"]
    # 지역 시세표 폴백 → source에 '추정·비실거래' 명시(초록 오표기 방지)
    assert "추정" in rev["source"] or "비실거래" in rev["source"]
    assert any("실거래 미확보" in n and "추정" in n for n in out["degraded_notes"])


@pytest.mark.asyncio
async def test_high1_geocode_fail_falls_back_to_regional_estimate(monkeypatch):
    """지오코딩 실패로 시군구를 못 얻으면 지역 시세표 추정 폴백(모든 regional 경로가 '추정' 고지)."""
    _stub_happy(monkeypatch, stub_saleprice=False)

    async def _no_sigungu(address):
        return None  # 지오코딩 실패

    monkeypatch.setattr(orch, "_sigungu5_from_address", _no_sigungu)

    out = await orch.build_rough_scenario(address="강원도 춘천시 어딘가 100")
    rev = out["revenue"]
    assert rev["total_won"] is not None  # 폴백값은 존재(무중단)
    assert "추정" in rev["source"] or "비실거래" in rev["source"]
    assert any("추정" in n for n in out["degraded_notes"])


# ─────────────────────────────────────────────────────────────────────────────
# ★HIGH-2: 공시지가 미확보 표준단가를 '공시지가'라 부르지 않기(무목업)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_high2_unreliable_official_price_not_called_gongsijiga(monkeypatch):
    """land_price_reliable=False면 묵시 표준단가를 '공시지가'로 표기하지 않고 정직 강등한다."""
    async def _fake_auto(**kwargs):
        return _fake_reco(official=1_500_000, land_reliable=False)  # 묵시 표준단가(1.5M)

    _stub_happy(monkeypatch, desk_ok=False)  # 탁상감정 실패 → 폴백 경로
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)

    out = await orch.build_rough_scenario(address="강원도 어딘가 산 1")
    land = out["land_cost"]
    assert land["total_won"] is not None  # 값(표준 가정단가)은 유지
    # ★값을 '공시지가 N원/㎡'로 라벨하지 않음(구 버그: 미확보 1.5M을 공시지가로 표기).
    assert not re.search(r"공시지가\s*[\d,]+\s*원/㎡", land["basis"] or "")
    assert "표준 가정단가" in (land["basis"] or "")     # 값은 '표준 가정단가'로 정직 라벨
    assert "실지가 아님" in (land["source"] or "")       # 출처도 '실지가 아님' 명시
    assert "공시지가" not in re.sub(r"공시지가\s*미확보", "", land["source"] or "")  # '미확보' 외 공시지가 표기 없음
    assert any("공시지가 미확보" in n and "실지가 아님" in n for n in out["degraded_notes"])


@pytest.mark.asyncio
async def test_high2_reliable_official_price_labeled_gongsijiga(monkeypatch):
    """대비: 실제 공시지가 확보(reliable=True)면 정직하게 '공시지가'로 표기(무회귀)."""
    async def _fake_auto(**kwargs):
        return _fake_reco(official=3_000_000, land_reliable=True)

    _stub_happy(monkeypatch, desk_ok=False)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)

    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")
    land = out["land_cost"]
    assert "공시지가" in (land["source"] or "")
    assert "실지가 아님" not in (land["source"] or "")


# ─────────────────────────────────────────────────────────────────────────────
# ★MEDIUM-4/5/6
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_medium4_equity_ratio_wired_to_dcf(monkeypatch):
    """equity/총사업비가 DCF equity_ratio에 실제 배선(항상 30% 고정 아님)."""
    _stub_happy(monkeypatch)
    low = await orch.build_rough_scenario(
        address="서울특별시 강남구 역삼동 736", equity_won=1_000_000_000)
    high = await orch.build_rough_scenario(
        address="서울특별시 강남구 역삼동 736", equity_won=50_000_000_000)
    eq_low = low["cashflow"]["summary"]["equity_amount"]
    eq_high = high["cashflow"]["summary"]["equity_amount"]
    # 자기자본이 다르면 DCF 자기자본 투입액도 달라져야 함(하드코딩 30%였다면 동일).
    assert eq_low != eq_high
    assert eq_high > eq_low


@pytest.mark.asyncio
async def test_medium5_region_defaults_to_empty(monkeypatch):
    """region 기본값이 '서울'이 아니라 ''(지방 과대 회피 — 주소 시도추론 위임)."""
    fake_auto = _stub_happy(monkeypatch)
    await orch.build_rough_scenario(address="강원도 춘천시 어딘가 100")
    assert fake_auto.calls[0]["region"] == ""


@pytest.mark.asyncio
async def test_medium6_construction_months_floor_guard(monkeypatch):
    """construction_months override가 0이어도 max(1,·)로 하한 가드(엔진 분모 0 방지)."""
    _stub_happy(monkeypatch)
    out = await orch.build_rough_scenario(
        address="서울특별시 강남구 역삼동 736", overrides={"construction_months": 0},
    )
    assert "construction_months" in out["overrides_applied"]
    assert out["cashflow"] is not None
    assert len(out["cashflow"]["monthly_rows"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# ★H1(QA REQUEST CHANGES): 세대수 가정(total_households) additive 노출
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_h1_total_households_assumed_positive(monkeypatch):
    """세대수 가정(GFA÷유형 표준 전용면적, unit_standards SSOT)이 inputs에 양수로 노출된다.

    프론트(STEP3 리스크시뮬)가 이 값을 세대수 SSOT 폴백으로 소비해, 설계 확정 전에도
    avg_area_pyeong 산식(세대수가 소거됨)으로 매출이 0으로 오탐하지 않게 한다.
    """
    _stub_happy(monkeypatch)
    out = await orch.build_rough_scenario(address="서울특별시 강남구 역삼동 736")
    assert isinstance(out["inputs"]["total_households"], int)
    assert out["inputs"]["total_households"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# 라우터 스모크
# ─────────────────────────────────────────────────────────────────────────────
def _make_client(monkeypatch):
    from app.core.database import get_db
    from app.routers import v2_feasibility

    async def _fake_scenario(**kwargs):
        return {
            "address": kwargs.get("address"),
            "inputs": {"land_area_sqm": 1000.0, "dev_type": "M06", "gfa_sqm": 2000.0},
            "land_cost": {"total_won": 5_000_000_000},
            "construction_cost": {"total_won": 5_000_000_000},
            "revenue": {"total_won": 16_000_000_000},
            "margin": {"developer_profit_won": 2_400_000_000, "rate_pct": 20.0},
            "summary": {"total_cost_won": 12_000_000_000, "net_profit_won": 4_000_000_000,
                        "roi_pct": 33.3, "npv_won": 3_000_000_000, "irr_pct": 25.0,
                        "payback_month": 30},
            "cashflow": {"monthly_rows": [{"month": 0}], "summary": {}},
            "overrides_applied": [],
            "degraded_notes": [],
        }

    monkeypatch.setattr(v2_feasibility, "build_rough_scenario", _fake_scenario)

    app = FastAPI()
    app.include_router(v2_feasibility.router)

    async def _override_db():
        yield None

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def test_router_rough_scenario_smoke(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/api/v2/feasibility/rough-scenario", json={
        "address": "서울특별시 강남구 역삼동 736",
        "region": "서울",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_cost_won"] == 12_000_000_000
    assert data["margin"]["developer_profit_won"] == 2_400_000_000
    assert "monthly_rows" in data["cashflow"]


def test_router_rough_scenario_with_overrides(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post("/api/v2/feasibility/rough-scenario", json={
        "address": "서울특별시 강남구 역삼동 736",
        "overrides": {"sale_price_per_pyeong": 50_000_000},
        "site_id": str(uuid.uuid4()),
    })
    assert resp.status_code == 200
    assert resp.json()["inputs"]["dev_type"] == "M06"
