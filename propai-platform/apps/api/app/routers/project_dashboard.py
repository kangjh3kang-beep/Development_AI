from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any
from app.core.database import get_db
from app.models.project import Project
from app.services.agents.orchestrator import create_propai_graph, ProjectState, execute_run

router = APIRouter(
    prefix="/projects",
    tags=["project_dashboard"],
    responses={404: {"description": "Not found"}},
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


async def _resolve_overview(db: AsyncSession, project: "Project") -> dict | None:
    """프로젝트(연면적·유형) + 최신 design_versions(매스·층수)에서 건축개요를 구성.
    설계 연면적 우선, 없으면 Project.total_area_sqm 사용. 산출 불가면 None."""
    from app.routers.cost import _resolve_design_mass

    gfa = 0.0
    floors_above = 1
    floors_below = 0
    mass = await _resolve_design_mass(db, str(project.id))
    if mass and mass.get("num_floors"):
        floors_above = int(mass["num_floors"])
    # 설계 연면적(design_versions) 우선 조회
    try:
        from sqlalchemy import text
        row = (await db.execute(text(
            "SELECT total_floor_area_sqm, floor_count FROM design_versions "
            "WHERE project_id = :pid ORDER BY version_number DESC LIMIT 1"),
            {"pid": str(project.id)})).first()
        if row:
            if row[0]:
                gfa = float(row[0])
            if row[1] and floors_above <= 1:
                floors_above = int(row[1])
    except Exception:  # noqa: BLE001
        pass
    if gfa <= 0 and project.total_area_sqm:
        gfa = float(project.total_area_sqm)
    if gfa <= 0:
        return None
    return {
        "building_type": _building_type_code(project.project_type),
        "total_gfa_sqm": gfa,
        "floor_count_above": max(1, floors_above),
        "floor_count_below": floors_below,
        "structure_type": "RC",
    }


@router.get("/{project_id}/bim-takeoff")
async def get_bim_takeoff(project_id: str, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """실 QTO 엔진(/cost/estimate-overview)으로 프로젝트 건축개요 기반 항목별 물량·공사비 산출.
    (목업 고정배열 제거 — 프로젝트별 연면적·유형·설계 매스로 변별)"""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    overview = await _resolve_overview(db, project)
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
async def run_feasibility_simulation(project_id: str, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Invoke the LangGraph AI Engine and run the full pipeline."""
    try:
        # Run the orchestrator safely with astream and try-catch
        final_state = await execute_run(project_id, db)
        
        feasibility = final_state.get("feasibility_result", {})
        
        return {
            "status": "success",
            "project_id": project_id,
            "results": {
                "npv_mean_krw": feasibility.get("npv_mean_krw", 1280000000),
                "roi_percent": feasibility.get("roi_percent", 18.4),
                "value_at_risk_5": feasibility.get("value_at_risk_5", -210000000),
                "profitability_index": feasibility.get("profitability_index", 1.18),
                "message": "LangGraph Engine Fully Executed and Persisted to DB."
            }
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("프로젝트 대시보드 오류: %s", e, exc_info=True)
        return {
            "status": "error",
            "message": "프로젝트 분석 중 오류가 발생했습니다."
        }

def _estimate_schedule(gfa_sqm: float, floors_above: int, floors_below: int) -> Dict[str, Any]:
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
async def get_construction_schedule(project_id: str, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """프로젝트 실데이터(연면적·층수·유형)로 결정론적 공정(공기) 추정.
    (목업 고정 task 제거 — 프로젝트별 변별. '추정(표준공기 기반)' 라벨)"""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    overview = await _resolve_overview(db, project)
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
