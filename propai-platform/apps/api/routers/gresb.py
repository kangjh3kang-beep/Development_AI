
from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.app.services.esg.gresb_scoring_service import (
    BENCHMARK_META,
    BENCHMARKS,
    GRESB_COMPONENTS,
    GresbScoringService,
)

router = APIRouter()


class GresbScoreRequest(BaseModel):
    building_type: str = "apartment"
    energy_kwh_per_sqm: float | None = None
    ghg_kg_per_sqm: float | None = None
    water_l_per_sqm: float | None = None
    has_esg_policy: bool = False
    has_green_cert: bool = False
    green_cert_level: str = "none"
    waste_recycling_pct: float = 0.0
    renewable_energy_pct: float = 0.0
    lca_total_carbon_kg: float | None = None
    floor_area_sqm: float = 1000


@router.post("/score")
async def calculate_gresb_score(req: GresbScoreRequest):
    service = GresbScoringService()
    result = service.calculate_score(**req.model_dump())
    # 표준 근거 블록(#5): GRESB 실제 산출 점수·등급·산식·벤치마크 출처를 가산.
    # graceful(실패해도 점수 결과는 정상 반환)·무목업(실값/실산식만, 빈 패널 금지).
    if isinstance(result, dict):
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            items = []
            # 총점(0~100) — 관리30+성과50+개발20 구성요소 합산(GRESB 2025 가중치).
            if result.get("total_score") is not None:
                items.append({
                    "label": "GRESB 총점",
                    "value": result.get("total_score"),
                    "basis": "관리(30)+성과(50)+개발(20) 구성요소 합산 / 만점 100 (GRESB 2025 가중치)",
                })
            # 등급(A~D) — 총점 임계(>=80 A·>=60 B·>=40 C) 판정.
            if result.get("grade") is not None:
                items.append({
                    "label": "GRESB 등급",
                    "value": f"{result.get('grade')} ({result.get('grade_label')})",
                    "basis": "총점 임계 판정(>=80 A/Green Star, >=60 B, >=40 C, 그외 D)",
                })
            # 구성요소별 점수 — 산출된 항목만(에너지·온실가스는 벤치마크 대비 강도 비율).
            comps = result.get("components") or {}
            for key, label in (("management", "관리 점수"), ("performance", "성과 점수"),
                               ("development", "개발 점수")):
                comp = comps.get(key) or {}
                if comp.get("score") is not None:
                    items.append({
                        "label": label,
                        "value": f"{comp.get('score')}/{comp.get('max')}",
                        "basis": "GRESB 2025 세부 배점 합산",
                    })
            energy = comps.get("energy") or {}
            if energy.get("value") is not None and energy.get("benchmark") is not None:
                items.append({
                    "label": "에너지 강도(kWh/㎡)",
                    "value": energy.get("value"),
                    "basis": (
                        f"벤치마크 {energy.get('benchmark')} 대비 강도 비율 판정"
                        f"({result.get('benchmark_type')}) — {energy.get('rating')}"
                    ),
                })
            ghg = comps.get("ghg") or {}
            if ghg.get("value") is not None and ghg.get("benchmark") is not None:
                items.append({
                    "label": "온실가스 강도(kgCO2e/㎡)",
                    "value": ghg.get("value"),
                    "basis": (
                        f"벤치마크 {ghg.get('benchmark')} 대비 강도 비율 판정"
                        f"({result.get('benchmark_type')}) — {ghg.get('rating')}"
                    ),
                })
            # 잠재 점수 — 개선 권고 적용 시 가산 가능 점수(현재점수+권고별 potential_gain).
            if result.get("potential_score") is not None:
                items.append({
                    "label": "개선 후 잠재 점수",
                    "value": result.get("potential_score"),
                    "basis": "현재 총점 + 개선 권고별 잠재 가산점(potential_gain) 합",
                })
            if items:
                # 벤치마크 메타(버전·출처)를 산식 출처로 함께 노출(무목업 — 실 메타만).
                meta = result.get("benchmark_meta") or {}
                src_label = "GRESB 2025 벤치마크"
                if meta.get("version") or meta.get("source"):
                    src_label = (
                        f"GRESB 벤치마크({meta.get('version', 'unknown')} / "
                        f"{meta.get('source', 'unknown')})"
                    )
                result["evidence"] = build_evidence_block(
                    items=items,
                    legal_ref_keys=["green_building", "energy_efficiency",
                                    "zeb_certification", "building_energy_rating"],
                    sources=[src_label],
                )
        except Exception:  # noqa: BLE001 — 근거 블록 실패는 결과를 막지 않음.
            pass
    return result


@router.get("/benchmarks")
async def get_benchmarks():
    return {
        "benchmarks": BENCHMARKS,
        "components": GRESB_COMPONENTS,
        "meta": BENCHMARK_META,
    }
