"""
GRESB ESG 자동 스코어링 서비스.
GRESB 2025 평가 항목 기반 점수 예측.
"""
import json
import logging
import os
from pathlib import Path

from apps.api.config import get_settings

logger = logging.getLogger(__name__)

# GRESB 2025 Scoring Components (simplified weights)
GRESB_COMPONENTS = {
    "management": {
        "weight": 30,
        "sub_items": {
            "esg_policy": 10,
            "governance": 10,
            "stakeholder_engagement": 5,
            "risk_management": 5,
        },
    },
    "performance": {
        "weight": 50,
        "sub_items": {
            "energy_intensity": 15,
            "ghg_emissions": 15,
            "water_usage": 10,
            "waste_management": 10,
        },
    },
    "development": {
        "weight": 20,
        "sub_items": {
            "green_certification": 10,
            "building_performance": 5,
            "community_impact": 5,
        },
    },
}

# Benchmark fallback values (Korean average for similar buildings)
_FALLBACK_BENCHMARKS = {
    "apartment": {"energy_kwh_sqm": 130, "ghg_kg_sqm": 62, "water_l_sqm": 500},
    "office": {"energy_kwh_sqm": 200, "ghg_kg_sqm": 95, "water_l_sqm": 700},
    "commercial": {"energy_kwh_sqm": 250, "ghg_kg_sqm": 120, "water_l_sqm": 800},
}

_DEFAULT_BENCHMARK_PATH = (
    Path(__file__).resolve().parents[3] / "config_data" / "gresb_benchmarks_2025.default.json"
)


def _load_benchmark_payload() -> dict:
    """환경 설정/파일 기반 GRESB 벤치마크를 로드한다."""
    settings = get_settings()
    configured = (settings.gresb_benchmarks_path or os.getenv("GRESB_BENCHMARKS_PATH", "")).strip()
    candidate_paths = [Path(configured)] if configured else []
    candidate_paths.append(_DEFAULT_BENCHMARK_PATH)

    for path in candidate_paths:
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                building_types = payload.get("building_types")
                if isinstance(building_types, dict) and building_types:
                    return payload
        except Exception:
            continue
    return {
        "version": "fallback",
        "source": "embedded defaults",
        "building_types": _FALLBACK_BENCHMARKS,
    }


def _normalize_benchmarks(raw: dict) -> dict:
    normalized: dict = {}
    for btype, values in raw.items():
        try:
            normalized[btype] = {
                "energy_kwh_sqm": float(values["energy_kwh_sqm"]),
                "ghg_kg_sqm": float(values["ghg_kg_sqm"]),
                "water_l_sqm": float(values["water_l_sqm"]),
            }
        except Exception:
            continue
    return normalized or dict(_FALLBACK_BENCHMARKS)


_BENCHMARK_PAYLOAD = _load_benchmark_payload()
BENCHMARKS = _normalize_benchmarks(_BENCHMARK_PAYLOAD.get("building_types", {}))
BENCHMARK_META = {
    "version": _BENCHMARK_PAYLOAD.get("version", "unknown"),
    "source": _BENCHMARK_PAYLOAD.get("source", "unknown"),
}


def refresh_benchmark_cache() -> dict:
    """환경/파일 변경 시 벤치마크 캐시를 갱신한다."""
    global _BENCHMARK_PAYLOAD, BENCHMARKS, BENCHMARK_META
    _BENCHMARK_PAYLOAD = _load_benchmark_payload()
    BENCHMARKS = _normalize_benchmarks(_BENCHMARK_PAYLOAD.get("building_types", {}))
    BENCHMARK_META = {
        "version": _BENCHMARK_PAYLOAD.get("version", "unknown"),
        "source": _BENCHMARK_PAYLOAD.get("source", "unknown"),
    }
    return BENCHMARKS


class GresbScoringService:
    """GRESB 점수 자동 계산."""

    def calculate_score(
        self,
        building_type: str = "apartment",
        energy_kwh_per_sqm: float | None = None,
        ghg_kg_per_sqm: float | None = None,
        water_l_per_sqm: float | None = None,
        has_esg_policy: bool = False,
        has_green_cert: bool = False,
        green_cert_level: str = "none",
        waste_recycling_pct: float = 0.0,
        renewable_energy_pct: float = 0.0,
        lca_total_carbon_kg: float | None = None,
        floor_area_sqm: float = 1000,
    ) -> dict:
        benchmark = BENCHMARKS.get(building_type, BENCHMARKS["apartment"])
        scores: dict = {}

        # 1. Management Score (30 points)
        mgmt_score = 0
        if has_esg_policy:
            mgmt_score += 10  # ESG policy
            mgmt_score += 5   # Governance (assumed if policy exists)
        mgmt_score += min(5, int(waste_recycling_pct / 20))  # Risk management proxy
        mgmt_score += 5 if renewable_energy_pct > 0 else 0   # Stakeholder engagement proxy
        scores["management"] = {"score": min(30, mgmt_score), "max": 30}

        # 2. Performance Score (50 points)
        perf_score = 0

        # Energy intensity (15 points) — lower is better
        if energy_kwh_per_sqm is not None:
            energy_ratio = energy_kwh_per_sqm / benchmark["energy_kwh_sqm"]
            if energy_ratio <= 0.5:
                perf_score += 15
            elif energy_ratio <= 0.75:
                perf_score += 12
            elif energy_ratio <= 1.0:
                perf_score += 9
            elif energy_ratio <= 1.25:
                perf_score += 6
            else:
                perf_score += 3
            scores["energy"] = {
                "value": energy_kwh_per_sqm,
                "benchmark": benchmark["energy_kwh_sqm"],
                "rating": (
                    "우수" if energy_ratio <= 0.75
                    else "보통" if energy_ratio <= 1.0
                    else "개선필요"
                ),
            }

        # GHG emissions (15 points)
        if ghg_kg_per_sqm is not None:
            ghg_ratio = ghg_kg_per_sqm / benchmark["ghg_kg_sqm"]
            if ghg_ratio <= 0.5:
                perf_score += 15
            elif ghg_ratio <= 0.75:
                perf_score += 12
            elif ghg_ratio <= 1.0:
                perf_score += 9
            elif ghg_ratio <= 1.25:
                perf_score += 6
            else:
                perf_score += 3
            scores["ghg"] = {
                "value": ghg_kg_per_sqm,
                "benchmark": benchmark["ghg_kg_sqm"],
                "rating": (
                    "우수" if ghg_ratio <= 0.75
                    else "보통" if ghg_ratio <= 1.0
                    else "개선필요"
                ),
            }

        # Water (10 points)
        if water_l_per_sqm is not None:
            water_ratio = water_l_per_sqm / benchmark["water_l_sqm"]
            perf_score += max(0, min(10, int(10 * (1.5 - water_ratio))))

        # Waste (10 points)
        perf_score += min(10, int(waste_recycling_pct / 10))

        scores["performance"] = {"score": min(50, perf_score), "max": 50}

        # 3. Development Score (20 points)
        dev_score = 0
        cert_points = {"none": 0, "basic": 4, "good": 7, "excellent": 10}
        dev_score += cert_points.get(green_cert_level, 0)

        if renewable_energy_pct >= 20:
            dev_score += 5
        elif renewable_energy_pct >= 10:
            dev_score += 3
        elif renewable_energy_pct > 0:
            dev_score += 1

        dev_score += 5  # Community impact (base score)
        scores["development"] = {"score": min(20, dev_score), "max": 20}

        # Total
        total = (
            scores["management"]["score"]
            + scores["performance"]["score"]
            + scores["development"]["score"]
        )

        # Grade
        if total >= 80:
            grade = "A"
            grade_label = "Green Star"
        elif total >= 60:
            grade = "B"
            grade_label = "우수"
        elif total >= 40:
            grade = "C"
            grade_label = "보통"
        else:
            grade = "D"
            grade_label = "개선필요"

        # Improvement recommendations
        recommendations = self._generate_recommendations(
            scores, building_type, energy_kwh_per_sqm,
            ghg_kg_per_sqm, renewable_energy_pct, green_cert_level,
        )

        return {
            "total_score": total,
            "max_score": 100,
            "grade": grade,
            "grade_label": grade_label,
            "components": scores,
            "benchmark_type": building_type,
            "benchmark_meta": BENCHMARK_META,
            "recommendations": recommendations,
            "potential_score": total + sum(
                r.get("potential_gain", 0) for r in recommendations
            ),
        }

    def _generate_recommendations(
        self, scores, building_type, energy, ghg, renewable, cert_level
    ):
        recs = []

        if scores.get("energy", {}).get("rating") != "우수":
            recs.append({
                "area": "에너지",
                "action": "고효율 공조 시스템 + LED 조명으로 에너지 강도 25% 절감",
                "potential_gain": 6,
                "cost_grade": "medium",
                "priority": 1,
            })

        if renewable is not None and renewable < 10:
            recs.append({
                "area": "재생에너지",
                "action": (
                    f"태양광 패널 설치로 재생에너지 비율 "
                    f"{renewable}% → 20% 향상"
                ),
                "potential_gain": 5,
                "cost_grade": "high",
                "priority": 2,
            })

        if cert_level in ("none", "basic"):
            recs.append({
                "area": "녹색인증",
                "action": "녹색건축 인증 '우수' 등급 취득 (LEED Gold 또는 G-SEED 우수)",
                "potential_gain": 7,
                "cost_grade": "medium",
                "priority": 3,
            })

        if scores["management"]["score"] < 20:
            recs.append({
                "area": "ESG 정책",
                "action": "ESG 정책 수립 + 거버넌스 체계 구축",
                "potential_gain": 10,
                "cost_grade": "low",
                "priority": 4,
            })

        return sorted(recs, key=lambda r: r["priority"])
