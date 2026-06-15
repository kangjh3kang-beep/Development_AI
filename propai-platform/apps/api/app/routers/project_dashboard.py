from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, Any
from app.core.database import get_db
from app.services.auth.auth_service import get_current_user


async def _fetch_project_lite(db: AsyncSession, project_id: str) -> dict | None:
    """실제 projects 테이블 컬럼만 raw SQL로 조회(ORM 컬럼불일치 회피).
    실 테이블: building_type/floor_above/floor_below/total_area_sqm/address
    (organization_id·project_type 없음)."""
    try:
        row = (await db.execute(text(
            "SELECT building_type, total_area_sqm, floor_above, floor_below, address "
            "FROM projects WHERE id = CAST(:pid AS uuid)"),
            {"pid": str(project_id)})).first()
    except Exception:  # noqa: BLE001 — 비-UUID 등
        return None
    if not row:
        return None
    return {
        "building_type": row[0],
        "total_area_sqm": float(row[1]) if row[1] else 0.0,
        "floor_above": int(row[2]) if row[2] else 0,
        "floor_below": int(row[3]) if row[3] else 0,
        "address": row[4],  # 분양가 지역시세(regional_pricing) 매칭용 — 없으면 None
    }

# P1-1 보안: 전 라우트 인증 강제(무인증 IDOR — 임의 project_id 건축개요·수지·일정 노출 차단).
# (projects 테이블에 organization_id가 없어 테넌트별 소유권 스코핑은 소유권/멤버십 모델 확립 후 후속.)
router = APIRouter(
    prefix="/projects",
    tags=["project_dashboard"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(get_current_user)],
)

def _building_type_code(project_type: str | None) -> str:
    """Project.project_type(한글/임의) → estimate-overview building_type 코드."""
    s = (project_type or "").lower()
    if "오피스텔" in (project_type or "") or "officetel" in s:
        return "officetel"
    if any(k in (project_type or "") for k in ("지식산업", "창고", "물류")) or "warehouse" in s:
        return "warehouse"
    if "office" in s or ("업무" in (project_type or "")):
        return "office"
    if any(k in (project_type or "") for k in ("연립", "다세대", "빌라")) or "townhouse" in s:
        return "townhouse"
    if "단독" in (project_type or "") or "single" in s:
        return "single_house"
    return "apartment"


async def _resolve_overview(db: AsyncSession, project_id: str, proj: dict) -> dict | None:
    """프로젝트(연면적·유형·층수) + 최신 design_versions(매스·층수)에서 건축개요를 구성.
    설계 연면적 우선, 없으면 projects.total_area_sqm 사용. 산출 불가면 None."""
    from app.routers.cost import _resolve_design_mass

    gfa = 0.0
    floors_above = int(proj.get("floor_above") or 0) or 1
    floors_below = int(proj.get("floor_below") or 0)
    mass = await _resolve_design_mass(db, str(project_id))
    if mass and mass.get("num_floors"):
        floors_above = int(mass["num_floors"])
    # 설계 연면적(design_versions) 우선 조회
    try:
        row = (await db.execute(text(
            "SELECT total_floor_area_sqm, floor_count FROM design_versions "
            "WHERE project_id = :pid ORDER BY version_number DESC LIMIT 1"),
            {"pid": str(project_id)})).first()
        if row:
            if row[0]:
                gfa = float(row[0])
            if row[1] and floors_above <= 1:
                floors_above = int(row[1])
    except Exception:  # noqa: BLE001
        pass
    if gfa <= 0 and proj.get("total_area_sqm"):
        gfa = float(proj["total_area_sqm"])
    if gfa <= 0:
        return None
    bt = proj.get("building_type")
    return {
        "building_type": bt if bt else _building_type_code(None),
        "total_gfa_sqm": gfa,
        "floor_count_above": max(1, floors_above),
        "floor_count_below": floors_below,
        "structure_type": "RC",
    }


@router.get("/{project_id}/bim-takeoff")
async def get_bim_takeoff(project_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """실 QTO 엔진(/cost/estimate-overview)으로 프로젝트 건축개요 기반 항목별 물량·공사비 산출.
    (목업 고정배열 제거 — 프로젝트별 연면적·유형·설계 매스로 변별)"""
    proj = await _fetch_project_lite(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    overview = await _resolve_overview(db, project_id, proj)
    if not overview:
        # 건축개요 미확정 — 무목업 정직 표기(빈 항목)
        return {
            "status": "no_data",
            "project_id": project_id,
            "items": [],
            "summary": {"total_direct_cost": 0, "note": "건축개요(연면적) 미확정 — 부지/설계 분석 필요"},
        }

    from app.routers.cost import OverviewCostRequest, estimate_overview
    est = await estimate_overview(OverviewCostRequest(project_id=project_id, **overview), db)
    return {
        "status": "success",
        "project_id": project_id,
        "items": est.get("items", []),
        "geometry": est.get("geometry"),
        "qto_source": est.get("qto_source"),
        "summary": {
            "total_direct_cost": est.get("direct_won", 0),
            "total_won": est.get("total_won", 0),
        },
    }

@router.post("/{project_id}/simulate-feasibility")
async def run_feasibility_simulation(project_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """실계산 사업성 시뮬레이션 (스텁 오케스트레이터 청산 — WP-11).

    - 공사비: /cost/estimate-overview와 동일 엔진(건축개요 적산) 재사용.
    - 분양수입: regional_pricing(지역 시세 단일출처) × 분양면적(전용률 75% 가정 — 출처 표기).
    - 분포: 실 MonteCarloService(시드 고정, 10,000회).
    - 건축개요 미확정 시 가짜 고정값(구 1.28B 폴백) 대신 no_data 정직 응답.
    - 응답 계약(results.npv_mean_krw/var_5_krw/profitability_index + 구 키) 유지.
    """
    proj = await _fetch_project_lite(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    overview = await _resolve_overview(db, project_id, proj)
    if not overview:
        return {
            "status": "no_data",
            "project_id": project_id,
            "results": None,
            "message": "건축개요(연면적) 미확정 — 부지/설계 분석 후 시뮬레이션할 수 있습니다.",
        }

    try:
        from app.routers.cost import OverviewCostRequest, estimate_overview

        est = await estimate_overview(OverviewCostRequest(project_id=project_id, **overview), db)
        total_cost = float(est.get("total_won") or 0)
        if total_cost <= 0:
            return {
                "status": "no_data",
                "project_id": project_id,
                "results": None,
                "message": "공사비 산출 불가(적산 결과 0) — 건축개요 확인 필요",
            }

        # 분양수입 — regional_pricing 단일출처(시군구→시도→전국 기본값 순 매칭).
        # 공사비 역산 금지(토지비 미반영 구조적 적자) — 파이프라인 수지 단계와 동일 원칙.
        from app.services.feasibility.regional_pricing import get_regional_sale_price_per_pyeong

        address = (proj.get("address") or "").strip()
        sale_price_per_pyeong = get_regional_sale_price_per_pyeong(address=address)
        sale_price_source = "regional_market_table" if address else "national_default_no_address"
        efficiency_pct = 75.0  # 분양 전용률 — 설계 미확정 시 표준 가정값(아래 inputs에 출처 표기)
        sellable_pyeong = overview["total_gfa_sqm"] / 3.305785 * (efficiency_pct / 100.0)
        expected_revenue = sellable_pyeong * float(sale_price_per_pyeong)

        # 공기(월) — 동일 파일의 결정론적 표준공기 추정 재사용(프로젝트별 변별)
        period_months = int(round(_estimate_schedule(
            gfa_sqm=overview["total_gfa_sqm"],
            floors_above=overview["floor_count_above"],
            floors_below=overview["floor_count_below"],
        )["total_months"]))

        from app.services.finance.monte_carlo_service import MonteCarloService

        mc = MonteCarloService().run_simulation(
            total_cost_krw=total_cost,
            expected_revenue_krw=expected_revenue,
            construction_period_months=period_months,
        )

        npv_mean = int(mc["npv_mean_krw"])
        npv_std = int(mc["npv_std_krw"])
        # 파라메트릭 VaR(5%) — 시뮬 분포 평균·표준편차 정규근사의 하위 5% 분위수(z=1.645)
        var_5 = int(npv_mean - 1.645 * npv_std)
        profitability_index = round((npv_mean + total_cost) / total_cost, 4)
        roi_percent = round(npv_mean / total_cost * 100, 2)

        return {
            "status": "success",
            "project_id": project_id,
            "results": {
                "npv_mean_krw": npv_mean,
                "npv_std_krw": npv_std,
                "npv_p10_krw": mc["npv_p10_krw"],
                "npv_p90_krw": mc["npv_p90_krw"],
                "probability_positive_npv": mc["probability_positive_npv"],
                "var_5_krw": var_5,
                "value_at_risk_5": var_5,  # 구 응답 키 하위호환
                "roi_percent": roi_percent,  # 구 응답 키 하위호환 — NPV/총공사비 기준
                "profitability_index": profitability_index,
                "n_simulations": mc["n_simulations"],
                "converged": mc["converged"],
                # 입력·출처 정직 표기(provenance) — 가정값·시세 출처를 응답에 동봉
                "inputs": {
                    "total_cost_krw": int(total_cost),
                    "cost_source": "estimate_overview",
                    "qto_source": est.get("qto_source"),
                    "unit_price_source": est.get("unit_price_source"),
                    "expected_revenue_krw": int(expected_revenue),
                    "sale_price_per_pyeong_won": int(sale_price_per_pyeong),
                    "sale_price_source": sale_price_source,
                    "efficiency_pct_assumed": efficiency_pct,
                    "construction_period_months": period_months,
                    "address_used": address or None,
                },
                "message": "실계산: 건축개요 적산 공사비 + 지역시세 분양수입 기반 몬테카를로 NPV 시뮬레이션",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("프로젝트 대시보드 오류: %s", e, exc_info=True)
        return {
            "status": "error",
            "message": "프로젝트 분석 중 오류가 발생했습니다."
        }

def _estimate_schedule(gfa_sqm: float, floors_above: int, floors_below: int) -> dict[str, Any]:
    """결정론적 공정 추정(표준공기 기반) — 실 Gantt 엔진 부재 시.
    규모(연면적·층수)로 총공기(월)를 산정하고 표준 공종 순서·비중으로 분배한다.
    프로젝트별로 결과가 달라지며, '추정(표준공기 기반)' 라벨로 정직 표기.

    표준공기 모델(건축):
      - 기초 공기 6개월 + 지상층당 0.55개월 + 지하층당 1.0개월
      - 연면적 보정: 30,000㎡ 초과분 10,000㎡당 +1개월
    공종 비중(총공기 대비): 착공·가설 8% / 토공·흙막이 14% / 기초·지하 18%
                          / 골조(지상) 32% / 외장·창호 12% / MEP(기계·전기) 10% / 마감·준공 6%
    """
    total_months = 6.0 + max(0, floors_above) * 0.55 + max(0, floors_below) * 1.0
    if gfa_sqm > 30000:
        total_months += (gfa_sqm - 30000) / 10000.0
    total_months = round(max(6.0, min(60.0, total_months)), 1)

    # 비중 합 = 1.0
    phases = [
        ("착공·가설공사", 0.08),
        ("토공·흙막이", 0.14),
        ("기초·지하구조", 0.18),
        ("지상 골조공사(RC)", 0.32),
        ("외장·창호", 0.12),
        ("기계·전기설비(MEP)", 0.10),
        ("마감·준공검사", 0.06),
    ]
    # 지하층이 없으면 토공·기초 비중 축소분을 골조로 이전
    if floors_below <= 0:
        phases = [
            ("착공·가설공사", 0.10),
            ("토공·정지", 0.10),
            ("기초공사", 0.12),
            ("지상 골조공사(RC)", 0.38),
            ("외장·창호", 0.13),
            ("기계·전기설비(MEP)", 0.11),
            ("마감·준공검사", 0.06),
        ]

    cum = 0.0
    tasks = []
    for name, frac in phases:
        start_month = round(cum * total_months) + 1
        dur_months = round(frac * total_months, 1)
        tasks.append({
            "task": name,
            "start": f"Month {start_month}",
            "dur_months": dur_months,
            "dur": round(frac * 100, 1),  # 간트 막대 폭(총공기 대비 %) — 프론트 호환
            "complete": False,
        })
        cum += frac
    return {
        "total_months": total_months,
        "method": "결정론적 표준공기 추정(규모·층수 기반). 실 공정관리 엔진 도입 시 대체.",
        "tasks": tasks,
    }


@router.get("/{project_id}/construction/schedule")
async def get_construction_schedule(project_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """프로젝트 실데이터(연면적·층수·유형)로 결정론적 공정(공기) 추정.
    (목업 고정 task 제거 — 프로젝트별 변별. '추정(표준공기 기반)' 라벨)"""
    proj = await _fetch_project_lite(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    overview = await _resolve_overview(db, project_id, proj)
    if not overview:
        return {
            "status": "no_data",
            "project_id": project_id,
            "tasks": [],
            "note": "건축개요(연면적·층수) 미확정 — 부지/설계 분석 필요",
        }

    sched = _estimate_schedule(
        gfa_sqm=overview["total_gfa_sqm"],
        floors_above=overview["floor_count_above"],
        floors_below=overview["floor_count_below"],
    )
    return {
        "status": "success",
        "estimated": True,
        "project_id": project_id,
        "total_months": sched["total_months"],
        "method": sched["method"],
        "tasks": sched["tasks"],
    }
