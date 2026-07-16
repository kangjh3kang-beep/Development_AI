"""v61 공사비 라우터 — IFC 물량 + 원가계산 + 몬테카를로 + 기성.

prefix: /api/v1/cost
"""

from __future__ import annotations

import contextlib
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_deps import enforce_llm_quota
from app.core.rbac import Role, require_role
from app.services.auth.auth_service import get_current_user
from app.services.bim.bim_service import BIMService
from app.services.cost.cost_monte_carlo import CostMonteCarlo
from app.services.cost.origin_cost_calculator import OriginCostCalculator
from apps.api.database.session import get_db

# P0-4 보안: cost 전 라우트 인증 강제(무인증 기성 영속 + 무결성 해시체인 적재 오염 차단).
# 라우터 레벨 의존성 → 모든 cost 라우트(기성/원가/BOQ/몬테카를로)가 유효 JWT 요구.
# (project_id가 사용자 tenant 소유인지 검증하는 테넌트 스코핑은 P1 후속.)
router = APIRouter(
    prefix="/api/v1/cost",
    tags=["v61 공사비"],
    dependencies=[Depends(get_current_user)],
)
cost_calc = OriginCostCalculator()
bim_service = BIMService()
logger = structlog.get_logger(__name__)
# P1 T1(공공고시 단가 주입) 관리자 게이트 — mass_templates.py 선례 재사용(require_role(Role.ADMIN)).
require_admin = require_role(Role.ADMIN)


async def _enforce_llm_if_needed(db: AsyncSession, use_llm: bool) -> None:
    """use_llm=True일 때만 LLM 한도 게이트 적용(무과금 경로는 통과) — personas.py 선례와 동일 계약."""
    if not use_llm:
        return
    await enforce_llm_quota(db)

# ── 건축개요 기반 공사비 추정(수지·사업성과 단일 데이터원 연동) ──
# ★P2: 구조계수 정의를 공용 개산식 SSOT(overview_estimator.STRUCT_COST_FACTOR)로 이관.
#   기존 참조처 호환을 위해 별칭 유지(값 이원화 금지 — 수정은 overview_estimator에서).
from app.services.cost.overview_estimator import STRUCT_COST_FACTOR as _STRUCT_FACTOR

# ── BIM 물량(bim_quantities) 공종코드 → 단가 SSOT(UnitPriceRepository) 키 매핑 ──
# ifc_work_map 의 leaf 코드만 단가에 대응(부모 집계코드 A01/A05 는 미가격 — 중복합산 방지).
# 매핑 없는 코드(기계/전기/마감 등)는 단가 미보유로 0원·priced=false 정직 표기.
# ★P2 T2 조사 결과(갭 해소 시도 — 무날조): UnitPriceRepository.get_prices()는
# standard_quantity_estimator.UNIT_PRICES_2026 의 6개 키(concrete/rebar/formwork/
# masonry/waterproof/window)만 순회 반환한다(DB에 다른 material_code가 더 있어도
# 이 6키 밖은 조회 API가 반환하지 않음). 아래 8개 매핑이 이미 6키를 전부 소진했으므로
# (콘크리트류 3·조적 1·방수류 2·창호 1 = 실질 6키 전량 사용), IFC_WORK_MAP 19코드 중
# 나머지 11개(A01·A05 부모 집계코드 2개는 의도적 제외 — 중복합산 방지 / A05-01·A05-02·
# A05-04·A07·A08·A09·B01·B02·C01 9개는 대응 단가키 자체가 없음)는 발명 없이는 매핑
# 불가 — 정직하게 unpriced 유지(코드 하단 unpriced_codes로 노출됨).
_BIM_WORKCODE_TO_PRICE_KEY: dict[str, str] = {
    "A01-01": "formwork",   # 거푸집
    "A01-02": "rebar",      # 철근
    "A01-03": "concrete",   # 콘크리트
    "A02": "concrete",      # 기초공사 → 콘크리트
    "A03": "masonry",       # 조적공사
    "A04": "waterproof",    # 방수공사
    "A05-03": "window",     # 창호프레임
    "A06": "waterproof",    # 지붕공사 → 방수
}


class OverviewCostRequest(BaseModel):
    """건축개요(연면적·지상/지하 층수·구조·용도) 기반 공사비 추정 요청."""
    building_type: str = "apartment"
    total_gfa_sqm: float = Field(gt=0)
    floor_count_above: int = Field(1, ge=1)
    floor_count_below: int = Field(0, ge=0)
    structure_type: str = "RC"
    unit_cost_per_sqm: int | None = None  # 직접공사비 단가 override(원/㎡)
    # 기하(geometry) 정밀 적산용 — 설계 매스 치수(있으면 실치수, 없으면 연면적·층수로 역산)
    project_id: str | None = None
    building_width_m: float | None = None
    building_depth_m: float | None = None
    floor_height_m: float = 3.0
    # P1 T3: 기본형건축비 고시 대조(baseline_check)용 평균 전용면적(㎡). 미입력 시 대조 생략(정직).
    avg_unit_sqm: float | None = None
    # P3: 시니어 적산(QS) 자문 opt-in(기본 false=무과금·미첨부) — True 시 senior_consultation additive.
    with_senior: bool = Field(default=False, description="시니어 적산(QS) 자문 첨부 여부(기본 false)")


def _overview_evidence(
    *,
    unit: int,
    structure_type: str,
    expected: dict[str, Any],
    gfa_above: float,
    gfa_below: float,
    qto_source: str,
    unit_price_source: str,
) -> list[dict[str, Any]]:
    """공사비 추정 근거 트레이스(label·value·basis). EvidencePanel 소비형.

    공사비는 기술법규(건축법 등)가 아니라 산업표준·원가관리 기반이라 법령키는 붙이지
    않는다(legal_ref_key 미부착 — 가짜 근거 금지). 산식·출처만 정직하게 기록한다.
    """
    won = lambda v: f"{int(v):,}원"  # noqa: E731 — 간단 포맷 헬퍼
    items: list[dict[str, Any]] = [
        {
            "label": "기준단가(구조계수 적용)",
            "value": f"{unit:,}원/㎡",
            "basis": f"건축개요 기반 표준단가(2026 기준) × 구조계수({structure_type}={_STRUCT_FACTOR.get(structure_type, 1.0)})",
        },
        {
            "label": "지상 공사비",
            "value": won(expected.get("aboveground_won", 0)),
            "basis": f"지상면적 {gfa_above:,.0f}㎡ × 기준단가",
        },
        {
            "label": "지하 공사비",
            "value": won(expected.get("underground_won", 0)),
            "basis": f"지하면적 {gfa_below:,.0f}㎡ × 기준단가 × 30% 할증(지하·주차 특수성)",
        },
        {
            "label": "조경 공사비",
            "value": won(expected.get("landscape_won", 0)),
            "basis": "(지상+지하 공사비) × 조경비율 1.5%",
        },
        {
            "label": "간접비(설계·감리·예비·일반관리)",
            "value": won(expected.get("indirect_won", 0)),
            "basis": "직접공사비 기준 표준요율(2026): 설계·감리·예비·일반관리 합계",
        },
        {
            "label": "기하 정밀적산(QTO) 기준",
            "value": "BIM 실치수" if qto_source == "bim" else "연면적·층수 역산(derived)",
            "basis": "설계 매스(BIM) 실치수 우선, 없으면 연면적·층수로 역산한 항목별 물량",
        },
        {
            "label": "항목 단가 출처",
            "value": "DB 단가(standard_quantity_estimator)" if unit_price_source == "db" else "하드코딩 fallback",
            "basis": "단가 SSOT(material_unit_prices) 1건 이상 반영 시 DB, 전부 미반영이면 fallback",
        },
    ]
    return items


async def _resolve_design_mass(db: AsyncSession, project_id: str) -> dict[str, Any] | None:
    """프로젝트 최신 design_versions의 매스 치수(폭·깊이·층수)를 조회(없으면 None)."""
    import uuid as _uuid

    from sqlalchemy import text

    try:
        pid = _uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return None
    try:
        row = (await db.execute(text(
            "SELECT floor_count, total_floor_area_sqm, design_data_json FROM design_versions "
            "WHERE project_id = :pid ORDER BY version_number DESC LIMIT 1"), {"pid": str(pid)})).first()
        if not row:
            return None
        dj = row[2] or {}
        mass = dj.get("mass") if isinstance(dj, dict) else {}
        mass = mass or {}
        return {
            "building_width_m": mass.get("building_width_m"),
            "building_depth_m": mass.get("building_depth_m"),
            "num_floors": mass.get("num_floors") or row[0],
            "floor_height_m": mass.get("floor_height_m"),
        }
    except Exception:  # noqa: BLE001
        return None


@router.post("/estimate-overview", summary="건축개요 기반 공사비 추정(지상/지하/조경/간접·최저~최대 + 기하 QTO)")
async def estimate_overview(req: OverviewCostRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """선택한 건축개요로 지상·지하·조경 직접공사비 + 간접비(설계·감리·예비·일반관리)를
    산정하고, 건설물가 변동을 반영한 최저~최대 예상 공사비 레인지를 반환한다.
    (도면/BIM 완성 프로젝트는 향후 항목별 정밀 적산으로 대체) — 수지·사업성과 동일 개요 사용."""
    from app.services.feasibility.construction_cost_engine import (
        DEFAULT_DIRECT_COST_PER_SQM,
        calculate_indirect_cost,
    )
    PY = 3.305785
    base_unit = req.unit_cost_per_sqm or DEFAULT_DIRECT_COST_PER_SQM.get(
        req.building_type, DEFAULT_DIRECT_COST_PER_SQM["apartment"])
    gfa = req.total_gfa_sqm
    # ★P2(적산→수지 배선): 인라인 산식(구조계수·지하 바닥판 비례·지하 30% 할증·조경 1.5%)을
    #   공용 개산식 SSOT(overview_estimator)로 이관 — 수지 construction_cost_engine이 같은
    #   함수를 소비한다(한 곳 수정 → 양 모듈 동시 반영). 산식·절사 순서 종전 동일(무회귀).
    from app.services.cost.overview_estimator import (
        estimate_overview_direct_cost,
        split_gfa_below,
    )
    gfa_above, gfa_below = split_gfa_below(gfa, req.floor_count_above, req.floor_count_below)

    def scenario(factor: float) -> dict[str, Any]:
        ov = estimate_overview_direct_cost(
            total_gfa_sqm=gfa,
            base_unit_cost_per_sqm=base_unit,
            structure_type=req.structure_type,
            floor_count_above=req.floor_count_above,
            floor_count_below=req.floor_count_below,
            scenario_factor=factor,
        )
        ind = calculate_indirect_cost(direct_cost_won=ov["direct_won"])
        total = ov["direct_won"] + ind["total_indirect_cost_won"]
        return {
            "unit_cost_per_sqm": ov["unit_cost_per_sqm"],
            "aboveground_won": ov["aboveground_won"], "underground_won": ov["underground_won"],
            "landscape_won": ov["landscape_won"],
            "direct_won": ov["direct_won"],
            "design_fee_won": ind["design_fee_won"], "supervision_fee_won": ind["supervision_fee_won"],
            "contingency_won": ind["contingency_won"], "general_expense_won": ind["general_expense_won"],
            "indirect_won": ind["total_indirect_cost_won"],
            "total_won": total,
            "per_pyeong_won": int(total / (gfa / PY)) if gfa > 0 else 0,
        }

    expected = scenario(1.0)

    # ── 기하(geometry) 기반 정밀 적산 — 설계 매스 실치수 우선, 없으면 연면적·층수로 역산 ──
    from app.services.cost.geometry_qto import derive_dims_from_gfa, geometry_takeoff
    qto_source = "derived"
    W, Dd, Hh = req.building_width_m, req.building_depth_m, req.floor_height_m
    nf_above = req.floor_count_above
    if req.project_id:
        m = await _resolve_design_mass(db, req.project_id)
        if m and m.get("building_width_m") and m.get("building_depth_m"):
            W, Dd = float(m["building_width_m"]), float(m["building_depth_m"])
            if m.get("num_floors"):
                nf_above = int(m["num_floors"])
            if m.get("floor_height_m"):
                Hh = float(m["floor_height_m"])
            qto_source = "bim"
    if not (W and Dd):
        W, Dd = derive_dims_from_gfa(gfa_above, nf_above)
    # ★WP-D 세션3 배선(additive): 실측 매스(qto_source="bim")일 때 QTO를 BimIR 경유로 흐르게 한다
    #   (bimir_from_mass→geometry_takeoff_from_bimir). BimIR가 매스 왕복 무손실이라 동일 치수로
    #   geometry_takeoff를 호출 → 항목별 물량·금액이 바이트까지 동일(세션2 수치 동일성 게이트가 근거).
    #   어떤 이유로든 실패하면 기존 직접 경로로 폴백한다(무회귀·예외격리). 파생 매스는 기존 경로 그대로.
    geometry: dict[str, Any] | None = None
    qto_path = "direct"
    if qto_source == "bim":
        try:
            from app.services.bim.bimir_adapters import bimir_from_mass
            from app.services.cost.geometry_qto import geometry_takeoff_from_bimir

            _bimir_model = bimir_from_mass({
                "building_width_m": W, "building_depth_m": Dd,
                "num_floors": nf_above, "floor_height_m": Hh,
            })
            geometry = geometry_takeoff_from_bimir(
                _bimir_model, floors_below=req.floor_count_below, structure_type=req.structure_type,
            )
            qto_path = "bimir"
        except Exception:  # noqa: BLE001 — BimIR 경로 실패 시 기존 직접 경로로 폴백
            geometry = None
    if geometry is None:
        geometry = geometry_takeoff(
            width_m=W, depth_m=Dd, floors_above=nf_above, floors_below=req.floor_count_below,
            floor_height_m=Hh, structure_type=req.structure_type,
        )
    geometry["source"] = qto_source
    geometry["qto_path"] = qto_path  # additive: BimIR 경유 여부(라이브 검증 근거)

    # 항목별 정밀 적산(QTO) — 레미콘·철근·거푸집·조적·방수·창호·기계·전기(물량×단가).
    # 건축개요(연면적·층수·구조) 기반. 설계/BIM 완성 시 실 매스로 정밀화 가능.
    items_qto: list[dict[str, Any]] = []
    unit_price_source = "fallback"
    try:
        from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator

        # 단가 SSOT(UnitPriceRepository) 1회 async 조회 주입 — DB 실패 시 None 폴백
        # (estimator가 기존 동기 fallback resolve로 회귀, 회귀 0).
        unit_prices: dict[str, dict[str, Any]] | None = None
        try:
            from app.services.cost.unit_price_repository import UnitPriceRepository
            unit_prices = await UnitPriceRepository().get_prices()
        except Exception:  # noqa: BLE001
            unit_prices = None
        if unit_prices and any(
            (p or {}).get("price_source") not in (None, "fallback") for p in unit_prices.values()
        ):
            unit_price_source = "db"

        _BT_KR = {"apartment": "공동주택", "officetel": "오피스텔", "office": "근린생활시설",
                  "townhouse": "다세대주택", "single_house": "다세대주택", "warehouse": "근린생활시설"}
        raw = StandardQuantityEstimator().estimate(
            building_type=_BT_KR.get(req.building_type, "공동주택"),
            total_gfa_sqm=gfa, floor_count_above=req.floor_count_above,
            floor_count_below=req.floor_count_below, structure_type=req.structure_type,
            prices=unit_prices,
        )
        # 공종분류 SSOT(work_breakdown) — work_code(A체계) → 표준 대공종(wb_code/wb_name) additive.
        from app.services.cost.work_breakdown import resolve as _resolve_wb

        for it in raw:
            unit_sum = float(it.get("mat_unit", 0)) + float(it.get("labor_unit", 0)) + float(it.get("exp_unit", 0))
            wb = _resolve_wb(it.get("work_code", ""), system="numeric")
            items_qto.append({
                "name": it.get("item_name"), "spec": it.get("spec"), "unit": it.get("unit"),
                "quantity": it.get("quantity"), "unit_cost_won": int(unit_sum),
                "cost_won": int(float(it.get("quantity", 0)) * unit_sum),
                # 단가 출처 정직 표기(DB 출처명 또는 "fallback") — additive 필드.
                "price_source": it.get("price_source", "fallback"),
                "price_basis_year": it.get("price_basis_year", 2026),
                # P2 T2: 공종분류 SSOT 대공종(additive) — 매핑 없으면 정직 None.
                "wb_code": wb["wb_code"],
                "wb_name": wb["wb_name"],
            })
    except Exception:  # noqa: BLE001
        items_qto = []
        unit_price_source = "fallback"

    # ── 전역정책 Phase0: 근거·신선도 공용 블록(build_evidence_block 경유) ──
    # 공사비는 법령근거가 없으므로 legal_ref_keys는 비운다(정직 — 가짜 법령키 발명 금지).
    # provenance=설계 매스(design_versions)·단가DB(material_unit_prices) 출처. 모두 graceful.
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        ev_block = build_evidence_block(
            items=_overview_evidence(
                # 종전 int(unit)=int(base×구조계수)와 동일값(factor 1.0의 int 절사 단가).
                unit=expected["unit_cost_per_sqm"], structure_type=req.structure_type, expected=expected,
                gfa_above=gfa_above, gfa_below=gfa_below,
                qto_source=qto_source, unit_price_source=unit_price_source,
            ),
            legal_ref_keys=[],  # 공사비 추정은 산업표준·원가관리 기반(법령 근거 없음)
            # 단가DB·설계매스 출처(레지스트리 미등록 — provenance가 registered:false로 정직 표기).
            sources=["material_unit_prices", "design_versions"],
        )
    except Exception:  # noqa: BLE001 — 공용블록 실패해도 공사비 결과 무손상
        ev_block = {"evidence": [], "legal_refs": [], "provenance": [], "trust": None}

    # ── P1 T3: 기본형건축비 고시 대조(baseline_check, additive) ──
    # 주택(아파트) 용도 + 평균 전용면적 입력 시에만 대조(정직 — 임의 추정 금지). 그 외는 생략.
    baseline_check: dict[str, Any] | None = None
    if req.building_type == "apartment" and req.avg_unit_sqm:
        try:
            from app.services.cost.basic_building_cost import get_baseline

            bl = get_baseline(req.floor_count_above, req.avg_unit_sqm)
            calc_unit = expected["unit_cost_per_sqm"]
            baseline_check = {
                "baseline_won_per_sqm": bl["value"],
                "calc_won_per_sqm": calc_unit,
                "deviation_pct": (
                    round((calc_unit - bl["value"]) / bl["value"] * 100, 2) if bl["value"] else None
                ),
                "basis": bl["basis"], "legal_link": bl["legal_link"], "confidence": bl["confidence"],
            }
        except Exception:  # noqa: BLE001 — 대조 실패해도 공사비 결과 무손상(블록 생략)
            baseline_check = None

    # ── P3: 시니어 적산(QS) 자문(with_senior opt-in, additive) ──
    # 산출 가능분만 전달(무목업) — 기준선편차(주택+평균전용면적)·예비비율·단가 tier 신뢰도.
    # ★무회귀: attach_senior_consultation은 절대 raise 안 함(consultation_hook 계약).
    senior_consultation: dict[str, Any] | None = None
    if req.with_senior:
        try:
            from app.services.senior_agents.consultation_hook import attach_senior_consultation

            qs_inputs: dict[str, Any] = {
                "cost_per_sqm": expected.get("unit_cost_per_sqm"),
                "floors": req.floor_count_above,
                "is_housing": req.building_type == "apartment",
                "contingency_reserve_won": expected.get("contingency_won"),
                "total_project_cost_won": expected.get("total_won"),
            }
            if req.building_type == "apartment" and req.avg_unit_sqm:
                qs_inputs["avg_unit_sqm"] = req.avg_unit_sqm
            if items_qto:
                t3_count = sum(
                    1 for it in items_qto if (it.get("price_source") or "fallback") == "fallback")
                qs_inputs["tier_t3_count"] = t3_count
                qs_inputs["tier_item_count"] = len(items_qto)
            senior_consultation = attach_senior_consultation("적산", qs_inputs)
        except Exception:  # noqa: BLE001 — 시니어 자문 첨부 실패는 공사비 결과 무손상(graceful)
            senior_consultation = None

    # ★성장루프 조인키: 표시 엔드포인트도 원장에 요약 적재(best-effort·멱등) 후
    #   최상위 `ledger_hash`를 노출 — 프론트 피드백(👍/👎)이 이 해시로 원장과 조인된다.
    from app.services.ledger.analysis_ledger_service import attach_ledger_hash
    from app.services.ledger.ledger_adapters import record_user_analysis
    wb = await record_user_analysis(
        analysis_type="cost_overview",
        summary={
            "building_type": req.building_type, "structure_type": req.structure_type,
            "total_gfa_sqm": gfa,
            "floor_count_above": req.floor_count_above, "floor_count_below": req.floor_count_below,
            "expected_total_won": expected["total_won"],
            "range_min_won": scenario(0.92)["total_won"], "range_max_won": scenario(1.12)["total_won"],
            "qto_source": qto_source, "unit_price_source": unit_price_source,
        },
        project_id=req.project_id, source="cost_overview",
    )

    return attach_ledger_hash({
        "building_type": req.building_type, "structure_type": req.structure_type,
        "total_gfa_sqm": gfa, "gfa_above_sqm": round(gfa_above, 1), "gfa_below_sqm": round(gfa_below, 1),
        **expected,
        "range": {
            "min_won": scenario(0.92)["total_won"],
            "expected_won": expected["total_won"],
            "max_won": scenario(1.12)["total_won"],
        },
        "items": items_qto,
        "geometry": geometry,
        "qto_source": qto_source,
        # 항목 단가 출처 요약 — DB 단가 1건 이상 반영 시 "db", 전부 하드코딩 fallback이면 "fallback".
        "unit_price_source": unit_price_source,
        "note": "건축개요 기반 표준 추정(지상/지하/조경/간접) + 기하(geometry) 정밀 적산. 설계 매스(BIM) 있으면 실치수로 자동 정밀화.",
        # 산출 근거·신선도(evidence/legal_refs/provenance) — additive, 기존 키 무손상.
        "evidence": ev_block["evidence"],
        "legal_refs": ev_block["legal_refs"],
        "provenance": ev_block["provenance"],
        # P1 T3: 기본형건축비 고시 대조(주택+평균전용면적 입력 시만, additive).
        **({"baseline_check": baseline_check} if baseline_check is not None else {}),
        # P3: 시니어 적산(QS) 자문(with_senior opt-in 시만, additive).
        **({"senior_consultation": senior_consultation} if senior_consultation is not None else {}),
    }, wb)


async def _load_bim_quantities(db: AsyncSession, project_id: str) -> list[dict[str, Any]]:
    """프로젝트 bim_quantities 를 공종코드 단위로 합산 조회(없으면 빈 리스트)."""
    import uuid as _uuid

    from sqlalchemy import text

    try:
        pid = _uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return []
    rows = (await db.execute(text(
        "SELECT work_code, "
        "       COALESCE(MAX(unit), '') AS unit, "
        "       COALESCE(SUM(quantity), 0) AS quantity, "
        "       COUNT(*) AS line_count "
        "FROM bim_quantities WHERE project_id = :pid AND work_code IS NOT NULL "
        "GROUP BY work_code ORDER BY work_code"), {"pid": str(pid)})).mappings().all()
    return [dict(r) for r in rows]


@router.get(
    "/{project_id}/bim-quantities/origin-cost",
    summary="BIM 물량(bim_quantities) + 단가 SSOT → 원가계산 12단계(공종코드 결합·정직성)",
)
async def bim_quantities_origin_cost(
    project_id: str, db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """저장된 BIM 물량을 단가 SSOT와 결합해 OriginCostCalculator 12단계 원가를 산정한다.

    bim_quantities 0건이면 가짜 0원 대신 `status="no_bim_quantities"` 로 정직 응답한다.
    단가 미보유 공종(기계/전기/마감 등)은 0원·priced=false 로 표기(중복합산·허위값 없음)."""
    grouped = await _load_bim_quantities(db, project_id)
    if not grouped:
        # 정직성: 물량 없음 → 가짜값 없이 빈 상태 반환(프론트가 안내 표시).
        return {
            "project_id": project_id,
            "status": "no_bim_quantities",
            "message": "이 프로젝트에 저장된 BIM 물량(bim_quantities)이 없습니다. IFC 분석을 먼저 실행하세요.",
            "items": [],
            "priced_item_count": 0,
            "unpriced_work_codes": [],
        }

    # 단가 SSOT 1회 조회(DB 우선·실패 시 fallback) — 출처 정직 표기.
    unit_prices: dict[str, dict[str, Any]] = {}
    unit_price_source = "fallback"
    try:
        from app.services.cost.unit_price_repository import UnitPriceRepository
        unit_prices = await UnitPriceRepository().get_prices()
        if any((p or {}).get("price_source") not in (None, "fallback") for p in unit_prices.values()):
            unit_price_source = "db"
    except Exception:  # noqa: BLE001
        unit_prices = {}
        unit_price_source = "fallback"

    from app.services.cost.ifc_work_map import IFC_WORK_MAP
    from app.services.cost.work_breakdown import resolve as _resolve_wb

    # work_code → 표시명(ifc_work_map 역참조, 첫 매칭).
    code_to_name: dict[str, str] = {}
    for _ifc_type, mappings in IFC_WORK_MAP.items():
        for wc, wn in mappings:
            code_to_name.setdefault(wc, wn)

    cost_items: list[dict[str, Any]] = []
    priced_items: list[dict[str, Any]] = []
    unpriced_codes: list[str] = []
    for g in grouped:
        wc = g.get("work_code") or ""
        qty = float(g.get("quantity") or 0)
        unit = g.get("unit") or ""
        price_key = _BIM_WORKCODE_TO_PRICE_KEY.get(wc)
        price = unit_prices.get(price_key) if price_key else None
        # P2 T2: 공종분류 SSOT 대공종(additive) — 단가 유무와 무관하게 항상 부착.
        wb = _resolve_wb(wc, system="ifc")
        if price and price_key:
            mat_u = float(price.get("mat_unit", 0))
            labor_u = float(price.get("labor_unit", 0))
            exp_u = float(price.get("exp_unit", 0))
            item = {
                "work_code": wc,
                "item_name": code_to_name.get(wc, wc),
                "spec": price.get("spec", ""),
                "unit": price.get("unit") or unit,
                "quantity": qty,
                "mat_unit": mat_u,
                "labor_unit": labor_u,
                "exp_unit": exp_u,
            }
            cost_items.append(item)
            priced_items.append({
                **item,
                "amount": int(qty * (mat_u + labor_u + exp_u)),
                "price_source": price.get("price_source", "fallback"),
                "price_key": price_key,
                "priced": True,
                "wb_code": wb["wb_code"],
                "wb_name": wb["wb_name"],
            })
        else:
            # 단가 미보유(매핑 없음 또는 단가 조회 실패) — 정직 표기(0원·priced=false).
            unpriced_codes.append(wc)
            priced_items.append({
                "work_code": wc, "item_name": code_to_name.get(wc, wc),
                "unit": unit, "quantity": qty, "amount": 0,
                "price_source": None, "price_key": None, "priced": False,
                "wb_code": wb["wb_code"],
                "wb_name": wb["wb_name"],
            })

    calc = cost_calc.calculate(cost_items)
    return {
        "project_id": project_id,
        "status": "ok",
        "items": priced_items,
        "priced_item_count": len(cost_items),
        "unpriced_work_codes": unpriced_codes,
        "unit_price_source": unit_price_source,
        "cost": calc,
        "total_project_cost": calc.get("total_project_cost", 0),
        "note": "BIM 물량×단가 SSOT 12단계 원가(추정). 단가 미보유 공종은 0원(priced=false) — 전문 적산사 검토 권장.",
    }


# ── 요청 스키마 ──

class IFCUploadRequest(BaseModel):
    """IFC 요소(사전 추출 JSON) 업로드 — 공종코드 매핑 + bim_quantities 영속 입력.

    실 IFC 파일 파싱(multipart)은 /api/v1/bim/analyze 담당. 본 계약은 요소 JSON 리스트다.
    """
    elements: list[dict[str, Any]] = Field(
        ..., description="IFC 요소 리스트 [{element_type, quantity, ...}]")


class CostCalculateRequest(BaseModel):
    """원가계산 요청."""
    items: list[dict[str, Any]] = Field(
        ..., description="공사비 항목 리스트")
    rates: dict[str, float] | None = Field(
        None, description="커스텀 법정요율 (None이면 2026 기본)")
    # 과금(R4) — 기본 false(무과금). True일 때만 CostInterpreter(LLM) 해석을 시도하고
    # enforce_llm_quota 게이트를 적용한다(personas.py 선례와 동일 계약).
    use_llm: bool = Field(default=False, description="AI(LLM) 원가 해석 포함 여부(기본 false=무과금)")
    # P3: 시니어 적산(QS) 자문 opt-in(기본 false=무과금·미첨부) — True 시 senior_consultation additive.
    with_senior: bool = Field(default=False, description="시니어 적산(QS) 자문 첨부 여부(기본 false)")


class MonteCarloRequest(BaseModel):
    """몬테카를로 시뮬레이션 요청."""
    base_result: dict[str, Any] = Field(
        ..., description="OriginCostCalculator 결과")
    iterations: int = Field(10000, ge=100, le=100000)
    seed: int = Field(42)


class BillingCreateRequest(BaseModel):
    """기성 생성 요청."""
    billing_no: int = Field(..., ge=1)
    period_from: str
    period_to: str
    planned_value: float = Field(0, ge=0)
    earned_value: float = Field(0, ge=0)
    actual_cost: float = Field(0, ge=0)
    work_entries: list[dict[str, Any]] = Field(default_factory=list)


class FeasibilityRequest(BaseModel):
    """원가→수지분석 연동 요청."""
    total_project_cost: float = Field(..., gt=0)
    total_revenue: float = Field(..., gt=0)
    project_months: int = Field(36, ge=1)


# ── 응답 스키마 ──


class IFCUploadResponse(BaseModel):
    """IFC 업로드 결과."""
    project_id: str
    mapped_items: list[dict[str, Any]]
    item_count: int
    unique_work_codes: list[str]
    # 실제 bim_quantities 에 영속된 행 수(origin-cost 체인 기여분). DB 미가용/부트스트랩
    # 실패 시 0 — 매핑은 반환하되 영속 실패를 정직 표기(가짜 성공 없음).
    persisted_rows: int = 0


class CostCalculateResponse(BaseModel):
    """원가계산 결과."""
    project_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    subtotals: dict[str, Any] = Field(default_factory=dict)
    total: float = 0.0

    # LLM(Claude) 원가 해석 (CostInterpreter, 키 설정 시 채워짐)
    ai_cost_analysis: str | None = None
    ai_ve_suggestions: str | None = None
    ai_material_advice: str | None = None
    ai_schedule_impact: str | None = None
    ai_risk_factors: str | None = None

    class Config:
        extra = "allow"


class MonteCarloResponse(BaseModel):
    """몬테카를로 시뮬레이션 결과."""
    project_id: str
    mean: float = 0.0
    std: float = 0.0
    p10: float = 0.0
    p50: float = 0.0
    p90: float = 0.0

    class Config:
        extra = "allow"


class BillingCreateResponse(BaseModel):
    """기성 생성 결과."""
    project_id: str
    billing_no: int
    period: str
    planned_value: float
    earned_value: float
    actual_cost: float
    evm_spi: float
    evm_cpi: float
    status: str
    work_entries_count: int


class BillingSummaryResponse(BaseModel):
    """누적 기성 현황."""
    project_id: str
    total_billings: int
    cumulative_pv: float
    cumulative_ev: float
    cumulative_ac: float
    overall_spi: float
    overall_cpi: float
    status: str


class FeasibilityResultResponse(BaseModel):
    """수지분석 연동 결과."""
    project_id: str
    total_cost: float
    total_revenue: float
    gross_profit: float
    profit_rate_pct: float
    monthly_return: float
    irr_estimate: float


# ── 엔드포인트 ──

@router.post("/{project_id}/upload-ifc", response_model=IFCUploadResponse)
async def upload_ifc(
    project_id: str,
    req: IFCUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """IFC 요소(JSON) 공종코드 매핑 + bim_quantities 영속.

    ★정직 계약(이름-동작 정합·체인 연결): 사전 추출된 IFC 요소 리스트(req.elements)를
      공종코드로 매핑하고 그 결과를 bim_quantities 테이블에 영속한다 → GET
      /{project_id}/bim-quantities/origin-cost(단가 SSOT 12단계 원가) 체인에 실제로 기여한다.
      (수정 전에는 매핑만 하고 미영속이라 origin-cost 가 항상 no_bim_quantities 로 단절됐음.)
    실 IFC 파일 자체 업로드·파싱(multipart)은 /api/v1/bim/analyze(ifcopenshell 실파싱)가
      담당한다 — 본 엔드포인트는 요소 JSON 계약을 유지한다. DB 미가용·부트스트랩 실패 시
      매핑 결과는 그대로 반환하되 persisted_rows=0 으로 정직 표기(가짜 성공 없음).

    ★PR#315 M1(소유권 검증): 형제 라우터 boq_auto.create_from_project_draft 와 동일하게
      assert_project_owned 로 project_id의 tenant 소유권을 검사한다(IDOR 방지) — 이 호출은
      try/except 밖에서 수행해 403 이 graceful 삼킴에 묻히지 않게 한다(보안검사 무력화 금지).
      project_id가 UUID가 아니거나 프로젝트 행이 없으면 계약대로 통과(정직 — 데모/테스트 경로).
    ★PR#315 H1(전역 전파방지): 실제 DB 쓰기는 analyze/generate 와 동일한 공용 헬퍼
      replace_bim_quantities 를 경유한다 — 같은 프로젝트를 재업로드해도 물량이 배가되지 않는다."""
    from app.services.auth.project_ownership import assert_project_owned

    await assert_project_owned(project_id, db, current_user)  # tenant 불일치 → 403

    mapped = bim_service.extract_quantities_with_work_codes(req.elements)

    # 매핑 결과를 bim_quantities 로 영속(origin-cost 체인 연결). 실패해도 매핑 응답은
    # 정상 반환한다(graceful) — DB 미가용/신규 DB 부트스트랩 실패 시 persisted_rows=0.
    persisted_rows = 0
    try:
        from app.services.cost.bim_quantity_writer import replace_bim_quantities

        tenant_id = getattr(current_user, "tenant_id", None)
        persisted_rows = await replace_bim_quantities(db, project_id, tenant_id, mapped)
        if persisted_rows:
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — 영속 실패는 매핑 응답을 막지 않는다
        with contextlib.suppress(Exception):
            await db.rollback()
        logger.warning(
            "upload-ifc bim_quantities 영속 실패(매핑 응답 무영향)",
            project_id=project_id,
            error=str(exc),
        )
        persisted_rows = 0

    return {
        "project_id": project_id,
        "mapped_items": mapped,
        "item_count": len(mapped),
        "unique_work_codes": list({m["work_code"] for m in mapped}),
        "persisted_rows": persisted_rows,
    }


@router.post("/{project_id}/calculate", response_model=CostCalculateResponse)
async def calculate_cost(
    project_id: str, req: CostCalculateRequest, db: AsyncSession = Depends(get_db),
):
    """원가계산서를 생성한다."""
    result = cost_calc.calculate(req.items, rates=req.rates)

    # LLM(Claude) 원가 해석 — use_llm=True일 때만 시도(과금 게이트 적용). 실패해도
    # 산정 결과는 정상 반환(graceful fallback). use_llm=False면 해석 필드는 생략(무날조).
    ai: dict[str, Any] = {}
    if req.use_llm:
        await _enforce_llm_if_needed(db, req.use_llm)
        try:
            from app.services.ai.cost_interpreter import CostInterpreter

            gfa = sum(float(it.get("quantity", 0) or 0) for it in req.items) or 0
            interp = await CostInterpreter().generate_interpretation({
                "total_cost": result.get("total_project_cost", 0),
                "cost_per_sqm": (
                    round(result.get("total_project_cost", 0) / gfa) if gfa else 0
                ),
                "cost_items": [
                    {
                        "category": k,
                        "amount": v,
                        "ratio_pct": (
                            round(v / result.get("total_project_cost", 1) * 100, 1)
                            if result.get("total_project_cost")
                            else 0
                        ),
                    }
                    for k, v in (result.get("category_totals", {}) or {}).items()
                ],
                "cost_breakdown": {
                    "material_cost": result.get("direct_material_cost"),
                    "labor_cost": result.get("total_labor_cost"),
                    "expense_cost": result.get("direct_expense_cost"),
                    "overhead_cost": result.get("general_mgmt"),
                    "profit": result.get("profit"),
                },
            })
            if isinstance(interp, dict):
                ai = interp
        except Exception:
            ai = {}

    # ── P3: 시니어 적산(QS) 자문(with_senior opt-in, additive) ──
    # 12단계 원가계산 집계(applied_rates·category_totals)가 입력이므로 일반관리비율/이윤율
    # 법정상한(R2)·공종구성비(R5) 실산출 가능. ★무회귀: attach_senior_consultation은 raise 안 함.
    senior_consultation: dict[str, Any] | None = None
    if req.with_senior:
        try:
            from app.services.senior_agents.consultation_hook import attach_senior_consultation

            applied_rates = result.get("applied_rates") or {}
            qs_inputs: dict[str, Any] = {
                "general_mgmt_rate": applied_rates.get("general_mgmt"),
                "profit_rate": applied_rates.get("profit"),
                "category_totals": result.get("category_totals"),
            }
            senior_consultation = attach_senior_consultation("적산", qs_inputs)
        except Exception:  # noqa: BLE001 — 시니어 자문 첨부 실패는 원가계산 결과 무손상(graceful)
            senior_consultation = None

    return {
        "project_id": project_id,
        **result,
        "ai_cost_analysis": ai.get("cost_analysis"),
        "ai_ve_suggestions": ai.get("ve_suggestions"),
        "ai_material_advice": ai.get("material_advice"),
        "ai_schedule_impact": ai.get("schedule_impact"),
        "ai_risk_factors": ai.get("risk_factors"),
        **({"senior_consultation": senior_consultation} if senior_consultation is not None else {}),
    }


@router.post("/{project_id}/monte-carlo", response_model=MonteCarloResponse)
async def run_monte_carlo(project_id: str, req: MonteCarloRequest):
    """공사비 몬테카를로 시뮬레이션."""
    mc = CostMonteCarlo(req.base_result, iters=req.iterations, seed=req.seed)
    result = mc.run()
    return {
        "project_id": project_id,
        **result,
    }


@router.post("/{project_id}/billing/create", response_model=BillingCreateResponse)
async def create_billing(project_id: str, req: BillingCreateRequest):
    """기성을 생성한다 (EVM SPI/CPI 자동 산출)."""
    pv = req.planned_value
    ev = req.earned_value
    ac = req.actual_cost

    spi = round(ev / pv, 4) if pv > 0 else 0.0
    cpi = round(ev / ac, 4) if ac > 0 else 0.0

    return {
        "project_id": project_id,
        "billing_no": req.billing_no,
        "period": f"{req.period_from} ~ {req.period_to}",
        "planned_value": pv,
        "earned_value": ev,
        "actual_cost": ac,
        "evm_spi": spi,
        "evm_cpi": cpi,
        "status": "on_track" if spi >= 0.9 and cpi >= 0.9 else "at_risk",
        "work_entries_count": len(req.work_entries),
    }


@router.get("/{project_id}/billing/summary", response_model=BillingSummaryResponse)
async def billing_summary(project_id: str):
    """누적 기성 현황을 반환한다."""
    return {
        "project_id": project_id,
        "total_billings": 0,
        "cumulative_pv": 0,
        "cumulative_ev": 0,
        "cumulative_ac": 0,
        "overall_spi": 1.0,
        "overall_cpi": 1.0,
        "status": "no_data",
    }


# ── D2: 기성고 EVM 실구현 — PV/EV/AC·SPI/CPI·과다청구 이상탐지·해시체인 ──


class BillingRegisterRequest(BaseModel):
    """회차별 기성 등록(progress_billings 영속)."""
    round: int = Field(..., ge=1, description="기성 회차")
    work_type: str | None = Field(None, description="공종(표준단가 대조 키)")
    contract_amount: float = Field(0, ge=0, description="해당 공종 계약액(원)")
    claimed_amount: float = Field(0, ge=0, description="청구액(원)")
    claimed_qty: float | None = Field(None, description="청구 물량")
    unit_price: float | None = Field(None, description="청구 단가(원/단위)")
    contract_unit_price: float | None = Field(None, description="계약 단가(원/단위, 단가이탈 기준)")
    progress_pct: float = Field(0, ge=0, le=100, description="누적 계획 공정률(%)")
    period_from: str | None = None
    period_to: str | None = None
    contract_total: float | None = Field(None, description="전체 계약총액(없으면 회차 계약액 합)")


@router.post("/{project_id}/billing", summary="D2 기성 등록(영속+EVM 누적+과다청구 이상탐지+해시체인)")
async def register_billing_d2(project_id: str, req: BillingRegisterRequest) -> dict[str, Any]:
    """회차별 기성을 영속하고, 등록 즉시 트리거된 과다청구 경고를 반환한다."""
    from app.services.cost import billing_service

    return await billing_service.register_billing(
        project_id=project_id,
        billing_no=req.round,
        work_type=req.work_type,
        contract_amount=req.contract_amount,
        claimed_amount=req.claimed_amount,
        claimed_qty=req.claimed_qty,
        unit_price=req.unit_price,
        contract_unit_price=req.contract_unit_price,
        progress_pct=req.progress_pct,
        period_from=req.period_from,
        period_to=req.period_to,
        contract_total=req.contract_total,
    )


@router.get("/{project_id}/billing", summary="D2 기성 목록+EVM summary+곡선+이상경고")
async def get_billing_d2(project_id: str, contract_total: float | None = None) -> dict[str, Any]:
    """기성 회차 목록 + EVM(PV/EV/AC·SPI/CPI·누적곡선) + 과다청구 이상경고."""
    from app.services.cost import billing_service

    return await billing_service.get_billing_summary(
        project_id=project_id, contract_total=contract_total)


@router.get("/{project_id}/billing/anomaly", summary="D2 과다청구 이상탐지(단독)")
async def get_billing_anomaly_d2(project_id: str, contract_total: float | None = None) -> dict[str, Any]:
    """과다청구 이상탐지 단독 조회(단가이탈·누적초과·SPI/CPI·급증)."""
    from app.services.cost import billing_service

    return await billing_service.get_anomalies(
        project_id=project_id, contract_total=contract_total)


@router.post("/{project_id}/feasibility", response_model=FeasibilityResultResponse)
async def cost_to_feasibility(project_id: str, req: FeasibilityRequest):
    """원가계산서→수지분석 연동."""
    profit = req.total_revenue - req.total_project_cost
    profit_rate = round(profit / req.total_revenue * 100, 2) if req.total_revenue > 0 else 0
    monthly_return = round(profit / req.project_months) if req.project_months > 0 else 0

    return {
        "project_id": project_id,
        "total_cost": req.total_project_cost,
        "total_revenue": req.total_revenue,
        "gross_profit": round(profit),
        "profit_rate_pct": profit_rate,
        "monthly_return": monthly_return,
        "irr_estimate": round(profit_rate / req.project_months * 12, 2),
    }


# ── CM 상세적산(MVP): BOQ 영속화 · 대안설계 원가비교(D1) · 시장가 3중(D4) ──


class BoqRequest(BaseModel):
    """BOQ(상세적산) 생성·영속화 요청 — 건축개요 기반."""
    building_type: str = "apartment"
    total_gfa_sqm: float = Field(gt=0)
    floor_count_above: int = Field(1, ge=1)
    floor_count_below: int = Field(0, ge=0)
    structure_type: str = "RC"
    tenant_id: str | None = None
    persist: bool = True
    # 과금(R4) — 기본 false(무과금). True일 때만 CostInterpreter(LLM) 해석을 시도하고
    # enforce_llm_quota 게이트를 적용한다(personas.py 선례와 동일 계약).
    use_llm: bool = Field(default=False, description="AI(LLM) BOQ 해석 포함 여부(기본 false=무과금)")


class AlternativeVariant(BaseModel):
    """대안설계 변형 — base 대비 override(구조/층수 등)."""
    label: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class AlternativesRequest(BaseModel):
    """D1 대안설계 A/B 원가비교 요청."""
    base_params: dict[str, Any] = Field(default_factory=dict)
    variants: list[AlternativeVariant] = Field(default_factory=list)


class SavingScenariosRequest(BaseModel):
    """P4 T1 절감 시나리오 Top-N 요청 — base_params는 alternatives와 동일 계약."""
    base_params: dict[str, Any] = Field(default_factory=dict)
    top_n: int = Field(5, ge=1, le=10, description="상위 절감 후보 개수(기본 5, 최대 10)")


class ChangeForecastRequest(BaseModel):
    """P4 T2 설계변경 예측공사비 요청 — base_params는 alternatives와 동일 계약.
    risks는 opt-in(FE가 /design-risk/predict 결과의 risks[]를 그대로 전달, 서버간 강결합 없음)."""
    base_params: dict[str, Any] = Field(default_factory=dict)
    risks: list[dict[str, Any]] = Field(default_factory=list, description="design_change_predictor risks[](opt-in)")


class CostReportRequest(BaseModel):
    """P5 적산 보고서 생성 요청 — FE가 조회한 산출물을 그대로 전달(가용분만 조립).

    도메인별-자체엔드포인트 패턴(bank_report.py:117)을 따른다: 어댑터가 부재 데이터의
    섹션을 통째로 생략하므로 전 필드 Optional(무날조)."""
    project_name: str | None = None
    overview: dict[str, Any] | None = None
    boq: dict[str, Any] | None = None
    senior_consultation: dict[str, Any] | None = None
    saving_scenarios: dict[str, Any] | None = None
    change_forecast: dict[str, Any] | None = None


@router.post("/{project_id}/boq", summary="상세적산 BOQ 생성·영속화(D4 시장가 3중·정직성 표기)")
async def create_boq(
    project_id: str, req: BoqRequest, db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """건축개요로 BOQ(공종별 물량·단가·금액)를 생성하고 cost_estimate(+item)에 영속화한다.
    각 항목에 standard/market(KCCI)/actual:null 3중 단가(D4)와 출처·신뢰구간을 부착한다."""
    from app.services.cost.boq_builder import build_boq
    from app.services.cost.cost_estimate_repository import save_estimate

    boq = await build_boq(
        building_type=req.building_type, total_gfa_sqm=req.total_gfa_sqm,
        floor_count_above=req.floor_count_above, floor_count_below=req.floor_count_below,
        structure_type=req.structure_type, qto_source="derived",
    )
    estimate_id: str | None = None
    ledger_wb = None                       # 성장루프 조인키(ledger_hash) 노출용 append 결과
    if req.persist:
        saved = await save_estimate(
            project_id=project_id, tenant_id=req.tenant_id,
            header=boq["header"], items=boq["items"],
            summary=boq["summary"], badges=boq["badges"],
        )
        estimate_id = saved.get("estimate_id")
        # Phase 1: 원가추정 SSOT 합류(best-effort — append_analysis가 예외 흡수, 무중단)
        from app.services.ledger.ledger_adapters import record_cost_estimate
        ledger_wb = await record_cost_estimate(
            summary=boq["summary"], header=boq["header"], estimate_id=estimate_id,
            tenant_id=req.tenant_id, project_id=project_id,
        )

    # D6 AI 해석(BOQ) — use_llm=True일 때만 시도(과금 게이트 적용). 실패해도 결과는
    # 정상 반환(graceful). use_llm=False면 해석 필드는 생략(무날조).
    ai_analysis: str | None = None
    if req.use_llm:
        await _enforce_llm_if_needed(db, req.use_llm)
        try:
            from app.services.ai.cost_interpreter import CostInterpreter
            calc = boq.get("_calc", {})
            interp = await CostInterpreter().generate_interpretation({
                "project_name": project_id,
                "building_type": req.building_type,
                "total_gfa_sqm": req.total_gfa_sqm,
                "floor_count": req.floor_count_above,
                "total_cost": calc.get("total_project_cost", 0),
                "cost_per_sqm": round(calc.get("total_project_cost", 0) / req.total_gfa_sqm)
                if req.total_gfa_sqm else 0,
                "cost_items": [
                    {"category": it["name"], "amount": it["amount"]} for it in boq["items"]
                ],
            })
            if isinstance(interp, dict):
                ai_analysis = interp.get("cost_analysis")
        except Exception:  # noqa: BLE001
            ai_analysis = None

    # ★성장루프 조인키: 원장 content_hash 를 최상위 `ledger_hash` 로 노출(공용 헬퍼 — 프론트 피드백 키잉).
    from app.services.ledger.analysis_ledger_service import attach_ledger_hash
    return attach_ledger_hash({
        "ok": True,
        "estimate_id": estimate_id,
        "items": boq["items"],
        "summary": boq["summary"],
        "badges": boq["badges"],
        "ai_cost_analysis": ai_analysis,
    }, ledger_wb)


@router.get("/estimate/{estimate_id}", summary="BOQ 단건 조회(영속화된 원가계산서)")
async def get_boq(estimate_id: str) -> dict[str, Any]:
    """영속화된 BOQ(헤더+항목)를 조회한다."""
    from app.services.cost.cost_estimate_repository import get_estimate
    est = await get_estimate(estimate_id)
    if not est:
        raise HTTPException(status_code=404, detail="estimate not found")
    return {"ok": True, **est}


@router.get("/{project_id}/estimates", summary="프로젝트 BOQ 목록(최신순)")
async def list_boq(project_id: str) -> dict[str, Any]:
    """프로젝트의 영속화된 BOQ 목록을 반환한다."""
    from app.services.cost.cost_estimate_repository import list_estimates
    return {"ok": True, "items": await list_estimates(project_id)}


@router.post("/{project_id}/alternatives", summary="D1 대안설계 A/B 원가비교(변형별 델타·영향공종)")
async def cost_alternatives(project_id: str, req: AlternativesRequest) -> dict[str, Any]:
    """base_params 대비 각 변형(구조/층수 등 override)의 원가를 재산정하여
    총액 델타·델타%·영향공종을 반환한다(추정).

    P4 T1(전파방지): 실 계산 로직은 alternatives_engine(공용 서비스)으로 추출했다 —
    saving_scenarios.py(절감 Top-N)·change_forecast.py(설계변경 예측공사비)가 라우터를
    다시 호출하지 않고 이 서비스를 직접 재사용한다(같은 계산 두 번 구현 금지)."""
    from app.services.cost.alternatives_engine import (
        build_boq_for_params,
        diff_variant,
        merge_params,
    )

    bp = merge_params(req.base_params, {})
    if bp["total_gfa_sqm"] <= 0:
        raise HTTPException(status_code=422, detail="base_params.total_gfa_sqm > 0 필요")

    base_boq = await build_boq_for_params(bp)
    base_total = int(base_boq["summary"]["total"])
    base_by_code = {it["code"]: it["amount"] for it in base_boq["items"]}

    variants_out: list[dict[str, Any]] = []
    for v in req.variants:
        vp = merge_params(req.base_params, v.overrides)
        vb = await build_boq_for_params(vp)
        variants_out.append(diff_variant(bp, base_total, base_by_code, vp, vb, v.label))

    return {
        "ok": True,
        "base": {"total": base_total},
        "variants": variants_out,
        "note": "대안별 원가는 건축개요 기반 추정(±12%) — 전문 적산사 검토 권장.",
    }


@router.post("/{project_id}/saving-scenarios", summary="P4 T1 절감 시나리오 Top-N(변형 자동생성+일괄 delta 랭킹)")
async def cost_saving_scenarios(project_id: str, req: SavingScenariosRequest) -> dict[str, Any]:
    """base_params로 결정론 절감 후보(구조/층수/GFA)를 자동 생성해 alternatives 엔진으로
    일괄 재산정하고, 절감액(음수 delta) 내림차순 Top-N을 반환한다(무과금·결정론).

    project_id는 응답 식별용(계산은 base_params만 사용 — DB 조회 없음)."""
    from app.services.cost.alternatives_engine import merge_params
    from app.services.cost.saving_scenarios import build_variant_candidates, rank_savings

    bp = merge_params(req.base_params, {})
    if bp["total_gfa_sqm"] <= 0:
        raise HTTPException(status_code=422, detail="base_params.total_gfa_sqm > 0 필요")

    candidates = build_variant_candidates(req.base_params)
    result = await rank_savings(req.base_params, candidates, top_n=req.top_n)

    return {"ok": True, "project_id": project_id, **result}


@router.post("/{project_id}/change-forecast", summary="P4 T2 설계변경 예측공사비(MC 밴드+리스크 공종 delta)")
async def cost_change_forecast(project_id: str, req: ChangeForecastRequest) -> dict[str, Any]:
    """base_params로 몬테카를로 추가공사비 밴드(p10/50/90)를 항상 산출하고, risks(opt-in —
    design_change_predictor 결과)가 있으면 공종(WB) 단위 delta 시나리오를 함께 반환한다.

    design_risk 서비스와 직접 결합하지 않는다 — FE가 /design-risk/predict 결과의 risks[]를
    그대로 전달하는 입력 주입 방식(서버간 강결합 신설 금지)."""
    from app.services.cost.alternatives_engine import merge_params
    from app.services.cost.change_forecast import forecast_change_cost

    bp = merge_params(req.base_params, {})
    if bp["total_gfa_sqm"] <= 0:
        raise HTTPException(status_code=422, detail="base_params.total_gfa_sqm > 0 필요")

    result = await forecast_change_cost(req.base_params, req.risks)

    return {"ok": True, "project_id": project_id, **result}


@router.post("/{project_id}/report", summary="P5 적산 보고서 — PDF·PPTX·DOCX(가용 산출만 조립)")
async def cost_estimation_report(
    project_id: str, req: CostReportRequest, format: str = "pdf",
) -> Response:
    """적산 산출물(개산·BOQ·시니어 QS·절감·설계변경 예측)을 정본 보고서엔진 경유로
    PDF/PPTX/DOCX 렌더한다(도메인별-자체엔드포인트 패턴 — bank_report.py:117 선례).

    project_id는 파일명 식별용(계산엔 미사용) — 다른 엔드포인트 프리픽스와의 일관성 유지."""
    from app.services.report.render import build_report_model_from_cost_estimation, render_report

    model = build_report_model_from_cost_estimation(req.model_dump())
    payload, media_type, ext = render_report(model, format)
    return Response(
        content=payload, media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="cost_estimation_report_{project_id}.{ext}"'
        },
    )


@router.get("/unit-prices", summary="단가 SSOT 조회(D4 standard/market/actual 3중)")
async def get_unit_prices() -> dict[str, Any]:
    """단가 SSOT(material_unit_prices DB 우선·fallback) 목록 — standard/market/actual 3중."""
    from app.services.cost.boq_builder import _KEY_TO_KCCI, _kcci_market_source_label, _kcci_market_unit
    from app.services.cost.unit_price_repository import UnitPriceRepository

    prices = await UnitPriceRepository().get_prices()
    items: list[dict[str, Any]] = []
    for key, p in prices.items():
        std = int(p["mat_unit"] + p["labor_unit"] + p["exp_unit"])
        market = _kcci_market_unit(key) if key in _KEY_TO_KCCI else None
        items.append({
            "code": key, "name": p["spec"], "unit": p["unit"],
            "standard": std, "market": market, "actual": None,
            "source": p["price_source"], "basis_year": p["price_basis_year"],
            "region": p.get("region"),
            # P2 T4: 재료/노무/경비 3분해(repository에 이미 존재 — 라우트에서 노출만, additive).
            "mat_unit": p["mat_unit"], "labor_unit": p["labor_unit"], "exp_unit": p["exp_unit"],
            # T5 정직화: market(KCCI)은 결정론 시뮬레이션 — 실 시세 API 아님(값 있을 때만 라벨).
            "market_source": _kcci_market_source_label(key) if market is not None else None,
            # P1 T4(단가 4계층) — additive: tier(T1_public/T2_standard/T3_fallback)·출처 URL.
            "tier": p.get("tier"), "source_url": p.get("source_url"),
        })
    return {
        "ok": True, "items": items,
        "note": (
            "standard=표준품셈/단가DB, market=KCCI 변동모델(결정론 시뮬레이션·실시세 API 아님), "
            "actual=실적 데이터 없음. 참고용·전문 적산사 검토 권장."
        ),
    }


class IngestPublicPricesRequest(BaseModel):
    """P1 T1 — 조달청 표준시장단가 주입 요청(관리자 전용)."""
    prdct_clsfc_no: str | None = Field(None, description="조달청 품목분류번호(선택 — 미지정 시 전체)")
    keyword: str | None = Field(None, description="품명 검색 키워드(선택)")
    max_pages: int = Field(3, ge=1, le=10, description="조회할 최대 페이지 수(페이지당 100건)")


@router.post(
    "/admin/ingest-public-prices",
    dependencies=[Depends(require_admin)],
    summary="조달청 표준시장단가 → 단가 SSOT 주입(P1 T1·관리자 전용)",
)
async def ingest_public_prices_route(
    req: IngestPublicPricesRequest, db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """조달청 가격정보현황서비스(data.go.kr 15129415)에서 표준시장단가를 조회해

    material_unit_prices에 멱등 upsert한다(단가 4계층 리졸버의 T1·최우선 계층).
    서비스키 미보유/API 실패 시 0건·정직 사유 반환(서버 동작 무영향)."""
    from app.services.cost.public_price_ingest import ingest_public_prices

    return await ingest_public_prices(
        db, prdct_clsfc_no=req.prdct_clsfc_no, keyword=req.keyword, max_pages=req.max_pages,
    )


def _boq_estimate_to_excel_rows(est: dict[str, Any]) -> list[list[Any]]:
    """영속화된 BOQ(estimate)를 Excel 행렬로 변환한다.

    BOQ 항목은 재료/노무/경비가 이미 결합된 단가(unit_price)이므로 OriginCostCalculator의
    12단계 재계산(to_excel_data)에 넣지 않고, 실제 저장된 항목·요약을 그대로 표기한다
    (가짜 12단계 분해를 발명하지 않음 — 정직성).
    """
    header = ["공종코드", "품명", "규격/공종", "물량", "단위", "단가(원)", "금액(원)", "단가출처"]
    rows: list[list[Any]] = [header]
    for it in est.get("items", []):
        rows.append([
            it.get("code", ""),
            it.get("name", ""),
            it.get("work_type", ""),
            f"{it.get('quantity', 0):,.2f}",
            it.get("unit", ""),
            f"{it.get('unit_price', 0):,.0f}",
            f"{it.get('amount', 0):,.0f}",
            it.get("price_source", ""),
        ])
    summary = est.get("summary") or {}
    rows.append(["", "", "", "", "", "", "", ""])
    rows.append(["직접공사비 소계", "", "", "", "", "", f"{summary.get('direct', 0):,.0f}", ""])
    rows.append(["간접비 소계", "", "", "", "", "", f"{summary.get('indirect', 0):,.0f}", ""])
    rows.append(["총 공사비", "", "", "", "", "", f"{summary.get('total', 0):,.0f}",
                 f"신뢰등급 {summary.get('confidence_grade', '-')}"])
    return rows


@router.get("/{project_id}/export-excel", response_class=Response)
async def export_excel(project_id: str, estimate_id: str | None = None):
    """영속화된 BOQ(원가계산서)를 Excel 파일로 내보낸다.

    estimate_id 지정 시 해당 건, 미지정 시 프로젝트의 최신 영속 BOQ를 사용한다.
    영속 BOQ가 없으면 가짜 샘플 대신 404로 정직 응답한다(무목업)."""
    from app.services.cost.cost_estimate_repository import get_estimate, list_estimates
    from app.services.export.excel_export_service import ExcelExportService

    eid = estimate_id
    if not eid:
        latest = await list_estimates(project_id, limit=1)
        eid = latest[0]["estimate_id"] if latest else None
    est = await get_estimate(eid) if eid else None
    if not est:
        raise HTTPException(
            status_code=404,
            detail="영속화된 BOQ(원가계산서)가 없습니다. 먼저 상세적산(BOQ)을 생성·저장하세요.",
        )

    rows = _boq_estimate_to_excel_rows(est)

    export_svc = ExcelExportService()
    file_bytes, content_type = export_svc.cost_sheet_to_xlsx(rows)

    ext = "xlsx" if "spreadsheet" in content_type else "csv"
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="cost_sheet_{project_id}.{ext}"'
        },
    )
