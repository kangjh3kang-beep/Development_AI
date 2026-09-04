"""기부체납 용적률 인센티브 계산기.

국토의 계획 및 이용에 관한 법률 시행령 제46조 기반.
공공시설 기부채납 시 용적률 상한 완화 계산.

용적률 체계:
- 기본용적률: 조례에서 정하는 용적률 (법정상한의 약 2/3 수준)
- 허용용적률: 기부체납 등 인센티브 적용 후 상한
- 상한용적률: 국토계획법 시행령 별표에 정한 절대 상한

계산식: 인센티브 = 기본용적률 x (1 + 기부체납비율 x alpha)
alpha계수: 주거 1.5, 상업 1.2, 준공업 1.3
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 용도지역명 → 카테고리 매핑 ──
ZONE_CATEGORY_MAP: dict[str, str] = {
    # 주거
    "제1종전용주거지역": "주거",
    "제2종전용주거지역": "주거",
    "제1종일반주거지역": "주거",
    "제2종일반주거지역": "주거",
    "제3종일반주거지역": "주거",
    "준주거지역": "주거",
    # 상업
    "중심상업지역": "상업",
    "일반상업지역": "상업",
    "근린상업지역": "상업",
    "유통상업지역": "상업",
    # 공업
    "전용공업지역": "공업",
    "일반공업지역": "공업",
    "준공업지역": "공업",
    # 녹지
    "보전녹지지역": "녹지",
    "생산녹지지역": "녹지",
    "자연녹지지역": "녹지",
    # 관리
    "보전관리지역": "녹지",
    "생산관리지역": "녹지",
    "계획관리지역": "녹지",
    "농림지역": "녹지",
    "자연환경보전지역": "녹지",
    # 특수구역
    "역세권개발구역": "상업",
    "도시재생활성화구역": "주거",
}

# ── 카테고리별 alpha 계수 ──
ALPHA_COEFFICIENTS: dict[str, float] = {
    "주거": 1.5,
    "상업": 1.2,
    "공업": 1.3,
    "녹지": 1.0,
}

# ── 용도지역별 법정 상한 용적률 (auto_zoning_service.py ZONE_LIMITS 기반) ──
NATIONAL_FAR_LIMITS: dict[str, float] = {
    "제1종전용주거지역": 100,
    "제2종전용주거지역": 150,
    "제1종일반주거지역": 200,
    "제2종일반주거지역": 250,
    "제3종일반주거지역": 300,
    "준주거지역": 500,
    "중심상업지역": 1500,
    "일반상업지역": 1300,
    "근린상업지역": 900,
    "유통상업지역": 1100,
    "전용공업지역": 300,
    "일반공업지역": 350,
    "준공업지역": 400,
    "보전녹지지역": 80,
    "생산녹지지역": 100,
    "자연녹지지역": 100,
    "보전관리지역": 80,
    "생산관리지역": 80,
    "계획관리지역": 100,
    "농림지역": 80,
    "자연환경보전지역": 80,
    "역세권개발구역": 700,
    "도시재생활성화구역": 500,
}


def get_zone_category(zone_type: str) -> str:
    """용도지역명에서 카테고리(주거/상업/공업/녹지)를 반환."""
    # 정확 매칭
    if zone_type in ZONE_CATEGORY_MAP:
        return ZONE_CATEGORY_MAP[zone_type]
    # 부분 매칭
    for key, cat in ZONE_CATEGORY_MAP.items():
        if key in zone_type or zone_type in key:
            return cat
    # 키워드 기반 폴백
    if "주거" in zone_type:
        return "주거"
    if "상업" in zone_type:
        return "상업"
    if "공업" in zone_type or "공업" in zone_type:
        return "공업"
    return "녹지"


def calculate(
    zone_type: str,
    ordinance_far: float,
    donation_ratio_pct: float,
    national_far: float | None = None,
) -> dict[str, Any]:
    """기부체납 비율에 따른 용적률 인센티브를 계산.

    Args:
        zone_type: 용도지역명 (예: "제2종일반주거지역")
        ordinance_far: 조례 기본용적률 (%) — 조례에서 정한 기본값
        donation_ratio_pct: 기부체납 비율 (%) — 대지면적 대비 기부체납 면적
        national_far: 법정 상한 용적률 (%) — None이면 자동 조회

    Returns:
        dict: base_far, allowed_far, max_far, incentive_far,
              donation_ratio, alpha, zone_category, legal_basis,
              simulation_table
        zone 미매칭(법정 상한 미확인) 시: {"skipped": <사유>, "zone_type", "zone_category",
              "simulation_table": []} — 임의 상한을 발명하지 않는다(무날조).
    """
    category = get_zone_category(zone_type)
    alpha = ALPHA_COEFFICIENTS.get(category, 1.0)

    # 법정 상한 (절대 상한) — ★무날조(WP-U1d): zone 미매칭이면 250% 임의값을 발명하지 않고
    # 시뮬 미산정(skipped) 정직 반환. 과거엔 여기서 250.0을 지어내 ①미매칭 zone(개발제한구역
    # 등)에 가짜 상한 기준 시뮬을 만들었고, ②base_far>250이면 반대로 상한이 기준보다 낮아져
    # allowed_far를 깎는 자기모순 왜곡까지 발생했다(실측: base 300 → allowed 250).
    max_far = national_far if national_far is not None else NATIONAL_FAR_LIMITS.get(zone_type)
    if max_far is None:
        return {
            "skipped": (
                f"용도지역 미매칭('{zone_type}') — 법정 상한 미확인으로 기부체납 인센티브 "
                "시뮬레이션을 산정하지 않습니다(임의 상한 발명 금지·무날조)."
            ),
            "zone_type": zone_type,
            "zone_category": category,
            "simulation_table": [],
        }

    # 기본용적률 = 조례값
    base_far = ordinance_far

    # 기부체납 비율 → 소수
    donation_ratio = donation_ratio_pct / 100.0

    # 인센티브 계산: 기본용적률 x 기부체납비율 x alpha
    incentive_far = base_far * donation_ratio * alpha

    # 허용용적률 = 기본 + 인센티브, 단 상한 초과 불가
    allowed_far = min(base_far + incentive_far, max_far)

    # 실제 적용되는 인센티브 (상한 cap 반영)
    effective_incentive = allowed_far - base_far

    # 시뮬레이션 테이블: 기부체납 0~30% (5% 단위)
    simulation_table: list[dict[str, Any]] = []
    for pct in range(0, 35, 5):
        ratio = pct / 100.0
        sim_incentive = base_far * ratio * alpha
        sim_allowed = min(base_far + sim_incentive, max_far)
        simulation_table.append({
            "donation_ratio_pct": pct,
            "incentive_far": round(sim_incentive, 2),
            "allowed_far": round(sim_allowed, 2),
            "capped": (base_far + sim_incentive) > max_far,
            "gain_from_base_pct": round((sim_allowed - base_far) / base_far * 100, 2) if base_far > 0 else 0,
        })

    return {
        "base_far": round(base_far, 2),
        "allowed_far": round(allowed_far, 2),
        "max_far": round(max_far, 2),
        "incentive_far": round(effective_incentive, 2),
        "donation_ratio": round(donation_ratio, 4),
        "donation_ratio_pct": donation_ratio_pct,
        "alpha": alpha,
        "zone_category": category,
        "zone_type": zone_type,
        "legal_basis": "국토의 계획 및 이용에 관한 법률 시행령 제46조 (기부채납 용적률 완화)",
        "simulation_table": simulation_table,
    }
