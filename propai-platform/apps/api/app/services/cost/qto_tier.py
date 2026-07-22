"""적산(積算) Q1~Q4 산정등급 SSOT — W3-3(P9): 사실 분류표, 새 계산 아님.

플랫폼의 적산 파이프라인은 이미 "물량이 어디서 왔는지"를 항목별로 정직하게 표기하고
있다(qty_source=user/bim/parametric — boq_bim_merge, qto_source=bim/derived — boq_builder,
driver=gfa/households/landscape_area/fixed — boq_parametric_engine). 그러나 이 신호들이
"Q1~Q4 성숙도 등급"으로 명시 집계되지 않아, 견적 하나에 실측/파라메트릭/계수/예비비가
얼마나 섞여 있는지 한눈에 드러나지 않는다(P9 갭).

이 모듈은 그 기존 신호를 Q1~Q4 로 **재-표기**할 뿐이다(억지 재계산·가짜 물량 발명 금지):

  Q1_MEASURED   — 직접 물량. 사용자 직접 입력(현장 확정 수량) 또는 BIM 요소 실측
                  (bim_quantities 1:1 매칭·boq_bim_merge qty_source='bim').
  Q2_PARAMETRIC — 파라메트릭. 연면적(GFA)·세대수·조경면적 등 프로젝트 파라미터에
                  비례한 산식(boq_parametric_engine 스케일링, standard_quantity_estimator
                  ㎡당 표준물량, geometry_takeoff 매스치수×표준 부재두께).
  Q3_FACTORED   — 계수(비율). 직접비/노무비 등 원가 기준에 법정요율·비율을 곱한
                  실비 항목(OriginCostCalculator 12단계 요율, 설계비·감리비·일반관리비).
  Q4_ALLOWANCE  — 예비비/버퍼. 확정 원가가 아닌 불확실성 대비 준비금(예비비·contingency).
  UNKNOWN       — 위 신호가 전혀 없는 항목(억지 분류 금지 — 정직 미상 표기).

판정은 항목에 이미 존재하는 필드(qty_source/qto_source/driver)나, OriginCostCalculator·
construction_cost_engine 처럼 이름이 고정된 계산 결과 키에 대한 **고정 매핑**으로만 이뤄진다.
새로운 확률/추정치를 만들지 않는다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class QtoTier(StrEnum):
    """적산 항목의 산정방식 등급(Q1~Q4) — P9 상세사양 문언과 동일."""

    Q1_MEASURED = "Q1_MEASURED"
    Q2_PARAMETRIC = "Q2_PARAMETRIC"
    Q3_FACTORED = "Q3_FACTORED"
    Q4_ALLOWANCE = "Q4_ALLOWANCE"
    UNKNOWN = "UNKNOWN"


TIER_LABELS: dict[QtoTier, str] = {
    QtoTier.Q1_MEASURED: "Q1 직접물량(실측)",
    QtoTier.Q2_PARAMETRIC: "Q2 파라메트릭(비례산식)",
    QtoTier.Q3_FACTORED: "Q3 계수(법정요율·비율)",
    QtoTier.Q4_ALLOWANCE: "Q4 예비비(버퍼·확정원가 아님)",
    QtoTier.UNKNOWN: "미상(산정경로 신호 없음)",
}

# ── 항목(dict) 레벨 분류 신호 — 첫 일치 우선 ──

# boq_bim_merge.merge_bim 의 qty_source(항목별 부착) → (tier, 근거 라벨).
# ★R1 정직화: user 와 bim 은 둘 다 Q1(직접 물량)이지만 근거가 다르다 — user 는 "현장
# 실측"이 아니라 "사용자가 직접 입력한 확정 수량"(계약서·수기 산출 등)이라, 라벨에
# '실측'을 쓰지 않는다(P9 스펙은 Q1을 '직접 물량'으로만 정의하고 실측/확정을 세분하지
# 않으므로 tier 재분류는 하지 않되, tier_basis 문구만 정직하게 구분한다 — 무날조).
_QTY_SOURCE_INFO: dict[str, tuple[QtoTier, str]] = {
    "user": (QtoTier.Q1_MEASURED, "사용자 확정 수량(현장 실측 아님 — 확정치)"),
    "bim": (QtoTier.Q1_MEASURED, "BIM 요소 실측 물량(1:1 매칭, boq_bim_merge)"),
    "parametric": (QtoTier.Q2_PARAMETRIC, "실적 원단위 스케일링(gfa/세대/조경 비례)"),
}

# boq_builder.build_boq 의 qto_source(항목 전체 공통값).
_QTO_SOURCE_TIER: dict[str, QtoTier] = {
    "bim": QtoTier.Q1_MEASURED,        # 저장된 bim_quantities 실측 집계
    "derived": QtoTier.Q2_PARAMETRIC,  # 연면적×㎡당 표준물량(standard_quantity_estimator)
}

# boq_parametric_engine.assign_driver 의 드라이버(전부 파라메트릭 계열 — 발명 아님).
_DRIVER_TIER: dict[str, QtoTier] = {
    "gfa": QtoTier.Q2_PARAMETRIC,
    "households": QtoTier.Q2_PARAMETRIC,
    "landscape_area": QtoTier.Q2_PARAMETRIC,
    "fixed": QtoTier.Q2_PARAMETRIC,  # 횟수성 가설항목(비례 없음) — 그래도 표본 스케일 계열
}

# 항목명 키워드(qty_source/qto_source/driver 신호가 없는 항목의 최후 폴백 — 실제 관측 문자열).
# ★R1 LOW③ 한계: 이름 키워드 매칭은 구조화 신호(qty_source 등)가 전혀 없을 때만 쓰는
# 최후 수단 휴리스틱이다 — 부분 문자열 매칭이라 오탐 가능(예: 실제로는 계수 산정이
# 아닌 항목이 우연히 '이윤분배금' 처럼 힌트 문자열을 포함하면 오분류될 수 있다).
# 구조화 신호가 있는 모든 실제 소비처(boq_bim_merge/boq_builder/boq_parametric_engine)는
# 이 폴백에 도달하지 않는다 — 이름 매칭은 향후 새 소비처의 임시 안전망일 뿐, 상시
# 신뢰 경로로 승격하지 말 것.
_ALLOWANCE_NAME_HINTS: tuple[str, ...] = ("contingency", "예비비", "우발상황비", "allowance")
_FACTORED_NAME_HINTS: tuple[str, ...] = (
    "design_fee", "supervision_fee", "general_expense",
    "설계비", "감리비", "일반관리비", "이윤", "부가세", "부가가치세",
)


def classify_item(item: dict[str, Any]) -> dict[str, Any]:
    """BOQ/QTO 항목(dict) 하나를 Q1~Q4 로 분류한다(사실 재-표기 — 새 계산 아님).

    신호 우선순위(첫 일치): qty_source → qto_source → driver → 항목명 키워드 → UNKNOWN.
    반환: {"tier": QtoTier, "tier_basis": str(판정 근거)}.
    """
    qty_source = item.get("qty_source")
    if qty_source in _QTY_SOURCE_INFO:
        tier, note = _QTY_SOURCE_INFO[qty_source]
        return {"tier": tier, "tier_basis": f"qty_source={qty_source!r} — {note}"}

    qto_source = item.get("qto_source")
    if qto_source in _QTO_SOURCE_TIER:
        tier = _QTO_SOURCE_TIER[qto_source]
        return {"tier": tier, "tier_basis": f"qto_source={qto_source!r} — {TIER_LABELS[tier]}"}

    driver = item.get("driver")
    if driver in _DRIVER_TIER:
        tier = _DRIVER_TIER[driver]
        note = "고정수량(비례 없음, 표본 수량 유지)" if driver == "fixed" else f"{driver} 비례 산식"
        return {"tier": tier, "tier_basis": f"driver={driver!r} — {note}"}

    name = str(item.get("name") or item.get("item_name") or item.get("code") or "").strip()
    name_lower = name.lower()
    for hint in _ALLOWANCE_NAME_HINTS:
        if hint in name_lower or hint in name:
            tier = QtoTier.Q4_ALLOWANCE
            return {"tier": tier, "tier_basis": f"항목명 '{hint}' 매칭(최후 폴백 휴리스틱) — {TIER_LABELS[tier]}"}
    for hint in _FACTORED_NAME_HINTS:
        if hint in name_lower or hint in name:
            tier = QtoTier.Q3_FACTORED
            return {"tier": tier, "tier_basis": f"항목명 '{hint}' 매칭(최후 폴백 휴리스틱) — {TIER_LABELS[tier]}"}

    return {
        "tier": QtoTier.UNKNOWN,
        "tier_basis": "산정경로 신호(qty_source/qto_source/driver/항목명) 없음 — 실코드 근거 부족(억지 분류 금지)",
    }


# ── 원가계산서(OriginCostCalculator.calculate) 결과 키 — 고정 매핑 ──
# 집계값(direct_cost·total_labor_cost·net_construction_cost·construction_cost_pre_vat·
# total_project_cost 등)은 서로 다른 tier 항목의 합이라 단일 tier 로 표기할 수 없어
# 매핑에서 **제외**한다(억지 분류 금지 — origin_cost_calculator.py 자체는 무변경).
# ★R1 HIGH 수정(이중계상): insurance_total 은 아래 6개 보험료 항목(industrial_acc_ins~
# retirement_fund)의 **소계**다 — 이 6개와 insurance_total 을 동시에 매핑하면 같은 금액이
# Q3 버킷에 두 번 더해진다(리뷰어 실증: Q3 금액 +15.5%·분포 3.1pp 왜곡). "집계값은 매핑
# 제외" 원칙을 insurance_total 에도 동일 적용해 명단에서 제거한다(개별 6항목만 유지 —
# 소계는 net_construction_cost 등과 마찬가지로 파생값이지 원본 계수 라인이 아니다).
ORIGIN_COST_KEY_TIER: dict[str, QtoTier] = {
    "indirect_labor_cost": QtoTier.Q3_FACTORED,   # 직접노무비 × 14.40%(RATES_2026)
    "industrial_acc_ins": QtoTier.Q3_FACTORED,    # 노무비 × 3.50%
    "employment_ins": QtoTier.Q3_FACTORED,        # 노무비 × 0.90%
    "health_ins": QtoTier.Q3_FACTORED,            # 노무비 × 3.595%
    "national_pension": QtoTier.Q3_FACTORED,      # 노무비 × 4.75%
    "long_term_care": QtoTier.Q3_FACTORED,        # 노무비 × 0.4724%
    "retirement_fund": QtoTier.Q3_FACTORED,       # 노무비 × 2.10%
    # "insurance_total" 은 위 6개 보험료의 소계(집계값) — 이중계상 방지를 위해 매핑 제외.
    "safety_health": QtoTier.Q3_FACTORED,         # (재료비+노무비) × 2.07%
    "env_preserve": QtoTier.Q3_FACTORED,          # (재료비+노무비) × 0.16%
    "general_mgmt": QtoTier.Q3_FACTORED,          # 순공사원가 × 5.50%
    "profit": QtoTier.Q3_FACTORED,                # (노무비+경비+일반관리비) × 15%
    "vat": QtoTier.Q3_FACTORED,                   # 공사비(세전) × 10%
}


def classify_origin_cost_keys(calc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """OriginCostCalculator.calculate() 결과에서 분류 가능한 키만 tier 를 부착한다.

    origin_cost_calculator.py 는 변경하지 않는다(호출부에서 결과 dict 를 받아 후처리).
    """
    out: dict[str, dict[str, Any]] = {}
    for key, tier in ORIGIN_COST_KEY_TIER.items():
        if key in calc:
            out[key] = {
                "amount_won": calc[key],
                "tier": tier,
                "tier_basis": f"{key} = 법정요율(RATES_2026) × 원가기준 — {TIER_LABELS[tier]}",
            }
    return out


def summarize_tiers(
    items: list[dict[str, Any]],
    *,
    amount_key: str = "amount",
    extra_tier_amounts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """항목 리스트(+선택적 계수항목)의 Q1~Q4 분포를 요약한다(견적 성숙도 지표).

    items 는 비파괴(원본 dict는 변경하지 않음) — 항목별 tier/tier_basis 를 부착한
    사본 목록을 tagged_items 로 함께 반환한다.
    extra_tier_amounts: classify_origin_cost_keys() 등 "이름이 곧 tier 인" 계산결과
        (원가계산서 요율항목 등)를 items 와 같은 분포에 합산하고 싶을 때 전달한다.
    """
    by_tier: dict[str, dict[str, Any]] = {
        t.value: {"count": 0, "amount_won": 0.0} for t in QtoTier
    }
    tagged: list[dict[str, Any]] = []
    for it in items:
        cls = classify_item(it)
        tagged.append({**it, **cls})
        bucket = by_tier[cls["tier"].value]
        bucket["count"] += 1
        # ★R1 LOW② 방어적 폴백: amount_key(기본 'amount')가 없으면 'cost_won'(geometry_qto
        # 계열 관례 필드명)으로 재시도한다 — 호출자가 geometry_takeoff류 항목을 amount_key
        # 지정 없이 넘기면 조용히 0으로 잠식(무기여 착시)되는 것을 방지(값 자체는 무변경,
        # 우선순위는 amount_key 그대로 — cost_won 은 amount_key 부재 시에만 참조).
        amt = it.get(amount_key)
        if amt is None and amount_key != "cost_won":
            amt = it.get("cost_won")
        if isinstance(amt, (int, float)) and not isinstance(amt, bool):
            bucket["amount_won"] += float(amt)

    if extra_tier_amounts:
        for info in extra_tier_amounts.values():
            tier = info.get("tier")
            key = tier.value if isinstance(tier, QtoTier) else str(tier)
            bucket = by_tier.setdefault(key, {"count": 0, "amount_won": 0.0})
            bucket["count"] += 1
            amt = info.get("amount_won")
            if isinstance(amt, (int, float)) and not isinstance(amt, bool):
                bucket["amount_won"] += float(amt)

    total_amount = sum(v["amount_won"] for v in by_tier.values())
    total_count = sum(v["count"] for v in by_tier.values())
    for t, v in by_tier.items():
        v["pct_amount"] = round(v["amount_won"] / total_amount * 100, 1) if total_amount > 0 else None
        v["pct_count"] = round(v["count"] / total_count * 100, 1) if total_count > 0 else None

    dominant_tier: str | None = None
    if total_amount > 0:
        dominant_tier = max(by_tier.items(), key=lambda kv: kv[1]["amount_won"])[0]
    elif total_count > 0:
        dominant_tier = max(by_tier.items(), key=lambda kv: kv[1]["count"])[0]

    return {
        "tagged_items": tagged,
        "by_tier": by_tier,
        "dominant_tier": dominant_tier,
        "unknown_count": by_tier[QtoTier.UNKNOWN.value]["count"],
        "item_count": total_count,
        "note": (
            "Q1~Q4 는 산정방식의 사실 분류(직접물량/파라메트릭/계수/예비비) — 새 계산 아님. "
            "UNKNOWN 은 산정경로 신호 부재(억지 분류 금지). amount_won 이 0/부재인 항목(예: "
            "공내역서 초안 — 단가 빈칸)은 pct_amount 대신 pct_count 로 성숙도를 판단할 것."
        ),
    }
