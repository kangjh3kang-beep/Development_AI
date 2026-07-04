"""ProjectPipeline 재분석(rerun) 회귀 테스트 — WP-23 (축1-W3).

WP-01에서 구현된 ``ProjectPipeline.run(options=...)`` 의 재실행 배선과
WP-14의 ``/pipeline/rerun-stage`` 라우터 조립을 검증한다.

검증 항목(스펙 6 + 라우터 조립):
  ① previous_stage_data 복원 시 기본값(500㎡/BCR60/FAR200)이 쓰이지 않음
  ② stage_overrides 반영 + 각 단계 data["applied_overrides"] 기록
  ③ cost 오버라이드 시 cost_per_pyeong 재계산 + cost_source="user_override"
  ④ feasibility 분양가 오버라이드 시 sale_price_source="user" + 이익 재산출
  ⑤ report가 SKIPPED+data 단계를 summary에 포함
  ⑥ 옵션 미전달 시 기존 전체 실행과 동일(하위호환)
  ⑦ 라우터 rerun-stage 조립 — skip_stages/stage_overrides 주입 + summary 응답

설계 원칙(결정성·정직성·오프라인):
  - previous_stage_data 는 *손으로 만든* 합성 페이로드를 쓴다. 실제 ``_run_site_analysis`` 는
    LandInfoService/MOLIT/VWORLD/LLM 등 외부 호출을 시도(모두 try/except 폴백이라 동작은
    하지만 네트워크 지연·수치 흔들림 유발)하므로, 재실행 단계만 검증하는 본 테스트는
    skip 단계를 합성 payload로 복원해 *완전 오프라인·결정적*으로 만든다.
  - 합성 payload 의 키 형상은 파이프라인이 실제 산출하는 stage.data 키와 일치시킨다
    (``_restore_previous`` 가 읽는 키: site=zone_type/land_area_sqm/max_bcr/max_far/...,
    design=total_gfa_sqm/floor_count_above/sellable_efficiency_pct/..., cost=total_construction_cost/...).
  - 기본값(500/60/200)과 *명확히 다른* 값을 써서, 복원이 폴백으로 덮이지 않았음을
    수치로 식별한다.
  - ⑥ 하위호환만 옵션 없는 *전체* 실행을 1회 수행한다(오프라인 폴백 경로로 완주).
"""

import os
import sys

import pytest

# propai-platform 루트 + apps/api 를 path에 추가 (conftest와 동일 관행 — 단독 실행 호환).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pipeline.project_pipeline import (  # noqa: E402
    PipelineStatus,
    ProjectPipeline,
)

# asyncio_mode="auto" (pyproject) — async 테스트 함수는 마커 없이 자동 수집된다.

_ADDRESS = "서울특별시 강남구 역삼동 123-45"
_STAGES = ["site_analysis", "design", "cost", "feasibility", "tax", "esg", "report"]

# ── 기본값(폴백)과 명확히 다른 합성 입력 ──
_LAND_AREA = 800.0          # ≠ 500 폴백
_BCR = 50.0                 # ≠ 60 폴백
_FAR = 300.0                # ≠ 200 폴백
_GFA = _LAND_AREA * _FAR / 100   # 2400 (= FAR200 폴백 1600 과 다름)
_GFA_PYEONG = _GFA / 3.3058
_EFFICIENCY_PCT = 76.0      # 공동주택 전용률(%)
_OFFICIAL_PRICE = 9_000_000.0    # land_cost>0 보장 → estimate_land_price 우회
_PREV_TOTAL_COST = 8_000_000_000.0
_PREV_CPP = round(_PREV_TOTAL_COST / _GFA_PYEONG)


# ──────────────────────────────────────────────────────────────
# 헬퍼 — 합성 previous_stage_data (오프라인·결정적)
# ──────────────────────────────────────────────────────────────


def _prev_site_data() -> dict:
    """이전 부지분석 stage.data — 파이프라인 산출 키 형상과 일치."""
    return {
        "zone_type": "제3종일반주거지역",
        "max_bcr": _BCR,
        "max_far": _FAR,
        "land_area_sqm": _LAND_AREA,
        "official_land_price": _OFFICIAL_PRICE,
        "pnu_codes": [],   # 빈값 — MOLIT lawd_cd 미생성(네트워크 우회). 재실행 단계엔 무관.
        "zoning": {
            "effective_bcr": _BCR,
            "effective_far": _FAR,
            "max_height_m": 0.0,
        },
        "coordinates": None,
    }


def _prev_design_data() -> dict:
    """이전 설계 stage.data — feasibility 가 sellable_efficiency_pct 를 복원본에서 읽는다."""
    return {
        "building_type": "공동주택",
        "total_gfa_sqm": _GFA,
        "building_area_sqm": _LAND_AREA * _BCR / 100,
        "floor_count_above": 8,
        "floor_count_below": 1,
        "unit_count": 40,
        "avg_unit_sqm": 45.0,
        "sellable_efficiency_pct": _EFFICIENCY_PCT,
    }


def _prev_cost_data() -> dict:
    """이전 공사비 stage.data."""
    return {
        "total_construction_cost": _PREV_TOTAL_COST,
        "direct_cost": _PREV_TOTAL_COST * 0.7,
        "cost_per_pyeong": _PREV_CPP,
        "total_gfa_pyeong": _GFA_PYEONG,
        "construction_months": 24,
        "cost_breakdown": {"direct_cost": round(_PREV_TOTAL_COST * 0.7)},
        "material_item_count": 12,
    }


def _previous_stage_data(*stages: str) -> list[dict]:
    """지정 단계들의 합성 stage.data 를 list[{stage,data}] 형태로 반환."""
    builders = {
        "site_analysis": _prev_site_data,
        "design": _prev_design_data,
        "cost": _prev_cost_data,
    }
    return [
        {"stage": name, "data": builders[name]()}
        for name in stages
        if name in builders
    ]


async def _run(options: dict | None = None):
    """주소 + (선택)옵션으로 파이프라인을 실행한다(project_id="" → DB 저장 우회)."""
    return await ProjectPipeline().run(_ADDRESS, project_id="", options=options)


def _skip_before(stage: str) -> list[str]:
    """지정 단계 이전 단계 목록(재실행 시 SKIP 대상)."""
    return _STAGES[: _STAGES.index(stage)]


def _offline_site_data() -> dict:
    """전체 실행(⑥)용 부지 입력 — zone_type+조례값 포함으로 실측/조례 네트워크를 우회한다.

    zone_type 가 있어 ``_fetch_real_site_data`` 를 건너뛰고, ordinance_bcr/far 가 있어
    ``OrdinanceService`` 조회도 생략된다. 남은 ``LandInfoService.collect_comprehensive`` 는
    테스트가 monkeypatch 로 빈 dict 스텁으로 대체한다(아래 _patch_offline).
    AI 해석은 키 부재 시 즉시 폴백(네트워크 無)이라 그대로 둔다.
    """
    return {
        "zone_type": "제3종일반주거지역",
        "land_area_sqm": _LAND_AREA,
        "max_bcr": _BCR,
        "max_far": _FAR,
        "ordinance_bcr": _BCR,
        "ordinance_far": _FAR,
        "ordinance_source": "test",
        "official_land_price": _OFFICIAL_PRICE,
    }


def _patch_offline(monkeypatch) -> None:
    """전체 파이프라인을 오프라인·결정적으로 만들기 위한 외부 의존 스텁.

    ``_run_site_analysis`` / ``_fetch_real_site_data`` 가 호출하는 외부 수집기 3종을
    빠른 폴백(빈 dict) async 스텁으로 대체한다. 이로써 site_data 유무에 관계없이
    네트워크 없이 결정적으로 완주한다:
      - LandInfoService.collect_comprehensive → {} (보충 없음 = pre_collected 그대로)
      - AutoZoningService.analyze_by_address  → {} (용도지역 미수집 = 가정 기본값 경로)
      - OrdinanceService.get_ordinance_limits → 법정상한 폴백(조례 미조회)
    MOLIT 실거래는 pnu 미제공으로 자동 생략, AI 해석은 키 부재로 즉시 폴백된다.
    """
    from app.services.land_intelligence import land_info_service as lis
    from app.services.land_intelligence import ordinance_service as ords
    from app.services.zoning import auto_zoning_service as azs

    async def _empty_comprehensive(self, address, pnu=None):  # noqa: ANN001, ARG001
        return {}

    async def _empty_zoning(self, address):  # noqa: ANN001, ARG001
        return {}

    async def _fallback_ordinance(self, address, zone_type):  # noqa: ANN001, ARG001
        # 조례 미조회 시 라우터/서비스가 기대하는 '법정상한 폴백' 형상.
        return {"ordinance_bcr": None, "ordinance_far": None, "source": "법정상한"}

    monkeypatch.setattr(
        lis.LandInfoService, "collect_comprehensive", _empty_comprehensive
    )
    monkeypatch.setattr(
        azs.AutoZoningService, "analyze_by_address", _empty_zoning
    )
    monkeypatch.setattr(
        ords.OrdinanceService, "get_ordinance_limits", _fallback_ordinance
    )

    # 부지분석 LLM 해석은 본 테스트 관심 밖(rerun/하위호환 계약과 무관)이며 키 환경에 따라
    # ainvoke 타임아웃(최대 90s)으로 느려질 수 있어 no-op 으로 대체한다(데이터 무영향).
    async def _noop_site_ai(self, state):  # noqa: ANN001, ARG001
        return None

    monkeypatch.setattr(ProjectPipeline, "_attach_site_ai", _noop_site_ai)


# ──────────────────────────────────────────────────────────────
# ① previous_stage_data 복원 — 기본값(500/60/200) 미사용
# ──────────────────────────────────────────────────────────────


async def test_previous_stage_data_복원시_기본값_미사용():
    """skip된 site/design 단계를 previous_stage_data로 복원하면
    단계간 payload(SiteToDesign/DesignToCost)가 폴백이 아닌 이전값을 갖는다."""
    opts = {
        "skip_stages": _skip_before("cost"),
        "previous_stage_data": _previous_stage_data("site_analysis", "design"),
        "stop_after": "cost",  # 비용 단계까지만 — 빠르고 결정적
    }
    rerun = await _run(opts)

    # SiteToDesign payload 가 폴백(500/60/200)이 아닌 복원값을 가진다.
    site_payload = rerun.site_to_design
    assert site_payload is not None
    assert site_payload.land_area_sqm == _LAND_AREA   # 800 ≠ 500
    assert site_payload.max_bcr == _BCR               # 50 ≠ 60
    assert site_payload.max_far == _FAR               # 300 ≠ 200
    assert site_payload.zone_type == "제3종일반주거지역"

    # DesignToCost payload 복원 — 이전 설계 연면적/세대수가 그대로 전달된다.
    design_payload = rerun.design_to_cost
    assert design_payload is not None
    assert design_payload.total_gfa_sqm == _GFA       # 2400 (FAR200 폴백 1600 아님)
    assert design_payload.floor_count_above == 8
    assert design_payload.unit_count == 40

    # cost 단계가 복원 payload(GFA 2400)로 실제 재계산된다 → total_pyeong>0.
    cost_data = rerun.stages["cost"].data
    assert cost_data["total_gfa_pyeong"] == pytest.approx(_GFA_PYEONG, rel=1e-6)
    assert cost_data["cost_per_pyeong"] > 0   # 폴백 GFA=0 였다면 0 이었을 값

    # skip 단계는 SKIPPED, cost 는 COMPLETED 로 실제 재계산된다.
    assert rerun.stages["site_analysis"].status == PipelineStatus.SKIPPED
    assert rerun.stages["design"].status == PipelineStatus.SKIPPED
    assert rerun.stages["cost"].status == PipelineStatus.COMPLETED


async def test_previous_stage_data_없으면_payload_폴백():
    """대조군 — previous_stage_data 없이 cost 부터 재실행하면 복원이 없어
    design_to_cost 가 생성되지 않아(None) cost 가 기본 payload(GFA=0)로 동작한다.

    이는 ①의 '복원이 실제로 작동함'을 반증 대조로 고정한다.
    """
    opts = {"skip_stages": _skip_before("cost"), "stop_after": "cost"}
    rerun = await _run(opts)

    # design skip + 미복원 → design_to_cost 생성 안 됨.
    assert rerun.design_to_cost is None
    # _run_cost 는 DesignToCostPayload() 기본값(total_gfa_sqm=0) → total_pyeong 0 → cpp 0.
    assert rerun.stages["cost"].data.get("cost_per_pyeong") == 0


# ──────────────────────────────────────────────────────────────
# ② stage_overrides 반영 + applied_overrides 기록
# ──────────────────────────────────────────────────────────────


async def test_stage_overrides_반영_및_applied_overrides_기록():
    """stage_overrides 가 해당 단계에 반영되고 data["applied_overrides"]에 기록된다."""
    override_gfa = 5000.0
    opts = {
        "skip_stages": _skip_before("design"),
        "previous_stage_data": _previous_stage_data("site_analysis"),
        "stage_overrides": {
            "design": {"total_gfa_sqm": override_gfa, "floor_count_above": 12},
        },
        "stop_after": "design",
    }
    rerun = await _run(opts)

    design_data = rerun.stages["design"].data
    applied = design_data.get("applied_overrides")
    assert isinstance(applied, dict)
    assert applied.get("total_gfa_sqm") == override_gfa
    assert applied.get("floor_count_above") == 12

    # 실제 산출 데이터·다음 단계 payload 에도 반영된다.
    assert design_data["total_gfa_sqm"] == override_gfa
    assert design_data["floor_count_above"] == 12
    assert rerun.design_to_cost.total_gfa_sqm == override_gfa
    assert rerun.design_to_cost.floor_count_above == 12


async def test_stage_overrides_비숫자값은_미적용_정직():
    """잘못된(비숫자) 오버라이드는 적용도 기록도 되지 않는다(정직성·단계 미실패).

    복원된 site(land 800 × FAR 300) 기반 자동 산출값(GFA 2400)이 유지된다.
    """
    opts = {
        "skip_stages": _skip_before("design"),
        "previous_stage_data": _previous_stage_data("site_analysis"),
        "stage_overrides": {"design": {"total_gfa_sqm": "아주 큰 값"}},
        "stop_after": "design",
    }
    rerun = await _run(opts)

    design_data = rerun.stages["design"].data
    assert rerun.stages["design"].status == PipelineStatus.COMPLETED
    # 비숫자 오버라이드는 applied_overrides 에 들어가지 않는다.
    assert "total_gfa_sqm" not in design_data.get("applied_overrides", {})
    # 자동 산출값(복원 site 기반 = 800 × 3.0)으로 유지된다.
    assert design_data["total_gfa_sqm"] == pytest.approx(_GFA)


# ──────────────────────────────────────────────────────────────
# ③ cost 오버라이드 — cost_per_pyeong 재계산 + cost_source="user_override"
# ──────────────────────────────────────────────────────────────


async def test_cost_오버라이드시_평당가_재계산_및_출처표기():
    """총공사비 오버라이드 시 cost_per_pyeong 가 재계산되고 cost_source="user_override"."""
    override_total = 12_000_000_000.0  # 120억
    opts = {
        "skip_stages": _skip_before("cost"),
        "previous_stage_data": _previous_stage_data("site_analysis", "design"),
        "stage_overrides": {"cost": {"total_construction_cost": override_total}},
        "stop_after": "cost",
    }
    rerun = await _run(opts)

    cost_data = rerun.stages["cost"].data
    assert cost_data["total_construction_cost"] == override_total

    # cost_per_pyeong = round(total / total_gfa_pyeong) 로 정합 재계산된다.
    total_pyeong = cost_data["total_gfa_pyeong"]
    assert total_pyeong == pytest.approx(_GFA_PYEONG, rel=1e-6)
    expected_cpp = round(override_total / total_pyeong)
    assert cost_data["cost_per_pyeong"] == expected_cpp
    # 평당가가 이전값과 실제로 달라졌다(재계산 증명).
    assert cost_data["cost_per_pyeong"] != _PREV_CPP

    # 출처 정직 표기 + 적용 기록.
    assert cost_data.get("cost_source") == "user_override"
    assert cost_data["applied_overrides"]["total_construction_cost"] == override_total

    # 다음 단계 payload 에도 재계산된 값이 전달된다.
    assert rerun.cost_to_feasibility.cost_per_pyeong == expected_cpp
    assert rerun.cost_to_feasibility.total_construction_cost == override_total


# ──────────────────────────────────────────────────────────────
# ④ feasibility 분양가 오버라이드 — sale_price_source="user" + 이익 재산출
# ──────────────────────────────────────────────────────────────


async def test_feasibility_분양가_오버라이드시_출처_user_및_이익_재산출():
    """분양가 오버라이드 시 sale_price_source="user" 로 표기되고 순이익이 재산출된다.

    market_reval 가용 여부에 의존하지 않도록, 동일 previous_stage_data 위에서
    '오버라이드 없는 기준 실행' 대비 '오버라이드 실행'의 분양가/이익 변화를 비교한다.
    """
    prev = _previous_stage_data("site_analysis", "design", "cost")
    skip = _skip_before("feasibility")

    # 기준 실행(분양가 오버라이드 없음) — 자동 산정 분양가/이익.
    baseline = await _run(
        {"skip_stages": skip, "previous_stage_data": prev, "stop_after": "feasibility"}
    )
    base_feas = baseline.stages["feasibility"].data
    base_price = base_feas["avg_sale_price_per_pyeong"]
    base_profit = base_feas["net_profit"]
    base_revenue = base_feas["total_revenue"]
    assert base_feas["sale_price_source"] != "user"  # 자동 출처
    assert "applied_overrides" not in base_feas       # 오버라이드 없음

    # 기준 분양가와 *명확히 다른* 사용자 지정가 — 매출/이익 변화를 관측 가능하게.
    user_price = base_price * 2.0 + 1_000_000
    override = await _run(
        {
            "skip_stages": skip,
            "previous_stage_data": prev,
            "stage_overrides": {
                "feasibility": {"avg_sale_price_per_pyeong": user_price}
            },
            "stop_after": "feasibility",
        }
    )
    feas = override.stages["feasibility"].data

    # 출처 정직 표기 + 지정가 반영.
    assert feas["sale_price_source"] == "user"
    assert feas["avg_sale_price_per_pyeong"] == user_price
    assert feas["applied_overrides"]["avg_sale_price_per_pyeong"] == user_price
    # 사용자 지정가에는 시장 블렌딩 신뢰도가 적용되지 않는다(정직성).
    assert feas.get("sale_price_confidence") is None

    # 이익 재산출 — 분양가가 올랐으니 매출/순이익이 기준보다 커진다.
    assert feas["total_revenue"] > base_revenue
    assert feas["net_profit"] > base_profit
    assert feas["net_profit"] != base_profit
    # 수익률도 매출 변화에 따라 재계산된다(수치형).
    assert isinstance(feas["profit_rate_pct"], (int, float))


# ──────────────────────────────────────────────────────────────
# ⑤ report — SKIPPED+data 단계를 summary에 포함
# ──────────────────────────────────────────────────────────────


async def test_report_summary는_SKIPPED_복원단계_포함():
    """report 가 COMPLETED 뿐 아니라 복원된 SKIPPED 단계의 data 도 summary에 포함한다."""
    opts = {
        "skip_stages": _skip_before("cost"),
        "previous_stage_data": _previous_stage_data("site_analysis", "design"),
        # stop_after 미지정 → report 단계까지 실행
    }
    rerun = await _run(opts)

    report_data = rerun.stages["report"].data
    assert report_data, "report 단계가 실행되어 data가 있어야 함"
    summary = report_data.get("summary", {})

    # 재계산된 단계.
    assert "cost" in summary
    assert "feasibility" in summary
    # 복원된 SKIPPED 단계도 유실 없이 포함된다.
    assert "site_analysis" in summary, "복원된 SKIPPED site_analysis 가 summary에 포함되어야 함"
    assert "design" in summary, "복원된 SKIPPED design 이 summary에 포함되어야 함"
    # 복원값이 그대로 노출(폴백 아님).
    assert summary["site_analysis"].get("land_area_sqm") == _LAND_AREA
    assert summary["design"].get("total_gfa_sqm") == _GFA

    # SKIPPED 단계지만 보고서에 포함됨 — 상태/데이터 일관성.
    assert rerun.stages["site_analysis"].status == PipelineStatus.SKIPPED
    assert rerun.stages["site_analysis"].data  # 복원 데이터 보존


async def test_report_summary는_data없는_SKIPPED는_제외():
    """복원 data 가 없는 SKIPPED 단계는 summary에서 제외된다(가짜 빈칸 방지)."""
    # previous_stage_data 없이 cost 부터 재실행 → site/design 은 data 없는 SKIPPED.
    rerun = await _run({"skip_stages": _skip_before("cost")})

    summary = rerun.stages["report"].data.get("summary", {})
    # data 없는 SKIPPED 단계는 summary에 들어가지 않는다.
    assert "site_analysis" not in summary
    assert "design" not in summary
    # 재계산된 단계는 포함.
    assert "cost" in summary


# ──────────────────────────────────────────────────────────────
# ⑥ 옵션 미전달 — 기존 전체 실행과 동일(하위호환)
# ──────────────────────────────────────────────────────────────


async def test_옵션_재실행키_미전달시_전체실행_하위호환(monkeypatch):
    """재실행 옵션(skip_stages/stage_overrides/previous_stage_data) 미전달 시
    7단계 전체가 정상 실행되고 오버라이드 흔적이 전혀 없다.

    site_data 만 주입(+외부 수집기 스텁)해 오프라인·결정적으로 완주한다 —
    skip/override/previous 키가 없으므로 '재실행 아님 = 기존 전체 실행' 경로다.
    """
    _patch_offline(monkeypatch)
    state = await ProjectPipeline().run(
        _ADDRESS, project_id="", options={"site_data": _offline_site_data()}
    )

    assert state.status == PipelineStatus.COMPLETED
    # 7단계 모두 SKIPPED 가 아니다(전체 실행).
    for name in _STAGES:
        sr = state.stages[name]
        assert sr.status != PipelineStatus.SKIPPED, f"{name} 단계가 skip되면 안 됨"
        assert sr.status in (PipelineStatus.COMPLETED, PipelineStatus.FAILED)
    # 핵심 계산 단계는 정상 완료된다(오프라인 가용 경로).
    for name in ("design", "cost", "feasibility"):
        assert state.stages[name].status == PipelineStatus.COMPLETED

    # 재실행 전용 흔적이 없어야 한다(하위호환 — 기존 동작 불변).
    for name in _STAGES:
        assert "applied_overrides" not in state.stages[name].data, (
            f"{name}에 applied_overrides가 없어야 함"
        )
    assert "cost_source" not in state.stages["cost"].data
    assert state.stages["feasibility"].data.get("sale_price_source") != "user"


async def test_옵션_None과_빈dict_동일동작(monkeypatch):
    """options=None 과 options={} 는 동일하게 전체 실행된다(하위호환 경계).

    재실행 키가 없어 _restore_previous/_stage_overrides_for 가 모두 no-op 임을 고정한다.
    site_data 만 다를 뿐 두 호출의 단계 집합/오버라이드 부재는 동일해야 한다.
    """
    _patch_offline(monkeypatch)
    site_opts = {"site_data": _offline_site_data()}
    s_none = await ProjectPipeline().run(_ADDRESS, project_id="", options=None)
    s_site = await ProjectPipeline().run(_ADDRESS, project_id="", options=site_opts)

    assert s_none.status == s_site.status == PipelineStatus.COMPLETED
    # 어느 경로든 단계를 skip 하지 않는다(전체 실행).
    none_skipped = {n for n in _STAGES if s_none.stages[n].status == PipelineStatus.SKIPPED}
    site_skipped = {n for n in _STAGES if s_site.stages[n].status == PipelineStatus.SKIPPED}
    assert none_skipped == site_skipped == set()
    # 두 경로 모두 재실행 흔적이 없다.
    for state in (s_none, s_site):
        for name in _STAGES:
            assert "applied_overrides" not in state.stages[name].data


# ──────────────────────────────────────────────────────────────
# ⑦ 라우터 rerun-stage 조립 — options 주입 + summary 응답 (WP-14)
# ──────────────────────────────────────────────────────────────


async def test_라우터_rerun_stage_조립과_summary():
    """라우터가 previous_result.stages → previous_stage_data, stage_overrides 병합,
    skip_stages 산출, 응답 summary(SKIPPED 복원 포함)를 올바르게 조립한다."""
    from app.routers.pipeline import StageRerunRequest, rerun_stage

    prev_stages = _previous_stage_data("site_analysis", "design")
    override_total = 15_000_000_000.0
    req = StageRerunRequest(
        address=_ADDRESS,
        project_id="",
        stage="cost",
        overrides={"total_construction_cost": override_total},  # 단일 overrides(하위호환)
        previous_result={"stages": prev_stages},
    )
    resp = await rerun_stage(req)

    # 응답 형상 — PipelineRunResponse 호환(stages + summary) + rerun_from/report.
    assert resp["rerun_from"] == "cost"
    assert resp["status"] == PipelineStatus.COMPLETED.value
    assert isinstance(resp["stages"], list) and resp["stages"]
    assert "summary" in resp
    assert "report" in resp

    # 단일 overrides 가 stage_overrides[cost]로 병합되어 재계산에 반영된다.
    cost_stage = next(s for s in resp["stages"] if s["stage"] == "cost")
    assert cost_stage["data"]["total_construction_cost"] == override_total
    assert cost_stage["data"].get("cost_source") == "user_override"

    # 복원된 skip 단계는 응답에서 completed 로 표기(기존 응답 계약 보존).
    site_stage = next(s for s in resp["stages"] if s["stage"] == "site_analysis")
    assert site_stage["status"] == PipelineStatus.COMPLETED.value
    assert site_stage["data"].get("land_area_sqm") == _LAND_AREA

    # summary 에 복원된 SKIPPED 단계와 재계산 단계가 모두 포함된다.
    summary = resp["summary"]
    assert "site_analysis" in summary
    assert "design" in summary
    assert "cost" in summary


async def test_라우터_stage_overrides_다단계_병합():
    """다단계 stage_overrides 와 단일 overrides 가 병합되어 각 단계에 반영된다."""
    from app.routers.pipeline import StageRerunRequest, rerun_stage

    user_price = 30_000_000.0  # 평당 3000만원(명확히 높은 지정가)
    req = StageRerunRequest(
        address=_ADDRESS,
        project_id="",
        stage="cost",
        overrides={"total_construction_cost": 10_000_000_000.0},
        stage_overrides={
            "feasibility": {"avg_sale_price_per_pyeong": user_price},
        },
        previous_result={"stages": _previous_stage_data("site_analysis", "design")},
    )
    resp = await rerun_stage(req)

    cost_stage = next(s for s in resp["stages"] if s["stage"] == "cost")
    feas_stage = next(s for s in resp["stages"] if s["stage"] == "feasibility")

    # cost(단일 overrides) + feasibility(stage_overrides) 동시 반영.
    assert cost_stage["data"]["total_construction_cost"] == 10_000_000_000.0
    assert feas_stage["data"]["avg_sale_price_per_pyeong"] == user_price
    assert feas_stage["data"]["sale_price_source"] == "user"


async def test_라우터_유효하지_않은_단계는_400():
    """알 수 없는 stage 는 400 HTTPException 으로 정직 거부된다."""
    from fastapi import HTTPException

    from app.routers.pipeline import StageRerunRequest, rerun_stage

    req = StageRerunRequest(address=_ADDRESS, stage="unknown_stage")
    with pytest.raises(HTTPException) as exc:
        await rerun_stage(req)
    assert exc.value.status_code == 400
