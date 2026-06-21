"""실무 체크리스트 — 규칙기반 판정(무과금·LLM 미사용).

각 judge 함수는 상류 서비스 출력(dict)을 받아 ChecklistItem dict 를 만든다.
판정값(pass/warn/tentative/missing)은 trust.verdict·cost_viable·게이트(developability)
등 '이미 산출된 값'에서 파생되므로 LLM 호출이 전혀 없다(R3·R4 무과금 경로).

미확보(상류 unavailable/None)는 status="missing"으로 정직 고지(R1 무목업).
"""

from __future__ import annotations

from typing import Any


def _item(step: str, label: str, status: str, value: Any = None,
          kpi: str | None = None, note: str | None = None) -> dict[str, Any]:
    return {"step": step, "label": label, "status": status,
            "value": value, "kpi": kpi, "note": note}


# ── 분양대행 ──

def judge_sales_price(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """적정분양가(거래사례 앵커+신뢰루프). trust.verdict 로 pass/warn/missing."""
    if not suggest or suggest.get("data_source") != "live":
        return _item("price", label, "missing", None, "신뢰도·tier",
                     (suggest or {}).get("note") or "주변 실거래 미확보로 적정분양가 산출 보류(무목업).")
    trust = suggest.get("trust") or {}
    verdict = trust.get("verdict")
    tiers = suggest.get("tiers") or []
    base = next((t for t in tiers if t.get("tier") == "base"), tiers[0] if tiers else {})
    value = {
        "base_per_pyeong_10k": base.get("per_pyeong_10k"),
        "confidence": trust.get("confidence"),
        "tiers": [{"tier": t.get("tier"), "per_pyeong_10k": t.get("per_pyeong_10k")} for t in tiers],
    }
    status = "pass" if verdict == "pass" else ("warn" if verdict == "warn" else "tentative")
    return _item("price", label, status, value, "신뢰도·tier",
                 suggest.get("note"))


def judge_sales_cost(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """원가 회수(2차 가드). cost_validation.conservative_viable 로 판정."""
    cv = (suggest or {}).get("cost_validation")
    if not cv:
        return _item("cost", label, "missing", None, "원가비율",
                     "원가엔진 미가용 — 시장기반 분양가는 유효하나 원가 회수 검증은 생략(정직).")
    viable = cv.get("conservative_viable")
    status = "pass" if viable else "warn"
    return _item("cost", label, status,
                 {"floor_per_pyeong_10k": cv.get("viable_price_floor_per_pyeong_10k"),
                  "cost_basis": cv.get("cost_basis")},
                 "원가비율", cv.get("warning"))


def judge_sales_strategy(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """분양전략(프리미엄 tier 선택). 신뢰도 높으면 공격 권고, 낮으면 보수 권고."""
    if not suggest or suggest.get("data_source") != "live":
        return _item("strategy", label, "missing", None, "tier 선택",
                     "시세 미확보로 전략 도출 보류(무목업).")
    conf = ((suggest.get("trust") or {}).get("confidence")) or 0
    if conf >= 0.7:
        rec, status = "공격적(시장 우위)", "pass"
    elif conf >= 0.4:
        rec, status = "기준(균형)", "warn"
    else:
        rec, status = "보수적(신뢰도 낮음)", "tentative"
    return _item("strategy", label, status, {"recommended_tier": rec, "confidence": conf},
                 "tier 선택", "신뢰도 기반 프리미엄 tier 권고(시장가는 변동 가능).")


def judge_sales_subscription(label: str, suggest: dict[str, Any] | None) -> dict[str, Any]:
    """청약·계약 가능성 — 실거래 표본수(수요 시그널)로 근사 판정."""
    ref = (suggest or {}).get("market_reference") or {}
    dong_n = (ref.get("dong") or {}).get("n") or 0
    sigu_n = (ref.get("sigungu") or {}).get("n") or 0
    n = max(int(dong_n), int(sigu_n))
    if n <= 0:
        return _item("subscription", label, "missing", None, "수요 시그널",
                     "주변 거래 표본 미확보 — 청약 수요 추정 보류(무목업).")
    status = "pass" if n >= 30 else ("warn" if n >= 10 else "tentative")
    return _item("subscription", label, status, {"trade_samples": n}, "수요 시그널",
                 "주변 실거래 표본수를 수요 활성도 대리지표로 사용(직접 청약경쟁률 아님).")


# ── 도시계획 ──

def judge_urban_zone(label: str, gate: dict[str, Any] | None,
                     site: dict[str, Any] | None) -> dict[str, Any]:
    """용도지역·특이부지 게이트. gate_decision(BLOCK/TENTATIVE/PASS)로 판정."""
    if not gate:
        zt = (site or {}).get("zone_type")
        if not zt:
            return _item("zone", label, "missing", None, "developability",
                         "용도지역 미확보 — 부지분석에서 주소를 확정하세요(무목업).")
        return _item("zone", label, "pass", {"zone_type": zt}, "developability",
                     "특이사항 없는 일상 개발부지.")
    decision = gate.get("decision")  # PASS|TENTATIVE|BLOCK (runner 가 gate_decision 결과를 넣음)
    dev = gate.get("developability")
    status = {"PASS": "pass", "TENTATIVE": "tentative", "BLOCK": "missing"}.get(decision, "warn")
    return _item("zone", label, status,
                 {"developability": dev, "resolvable": gate.get("resolvable"),
                  "decision": decision},
                 "developability", gate.get("honest_disclosure"))


def judge_urban_method(label: str, methods: list[dict[str, Any]] | None) -> dict[str, Any]:
    """개발방식 판정(AHP 랭킹 1위)."""
    if not methods:
        return _item("method", label, "missing", None, "최적 방식",
                     "개발방식 평가 미확보(무목업).")
    top = methods[0]
    return _item("method", label, "pass",
                 {"recommended": top.get("method"), "score": top.get("score"),
                  "top3": [m.get("method") for m in methods[:3]]},
                 "최적 방식", "AHP 가중평가(수익성·기간·위험·인허가) 1위.")


def judge_urban_incentive(label: str, incentives: list[str] | None) -> dict[str, Any]:
    """인센티브(종상향·용적완화) — 추출 결과 유무로 판정."""
    if not incentives:
        return _item("incentive", label, "warn", [], "상향 잠재",
                     "현 데이터로 적용 가능한 인센티브 수단을 특정하지 못함 — 지구단위·조례 확인 필요.")
    return _item("incentive", label, "pass", incentives, "상향 잠재",
                 "적용 가능성 있는 상향수단(전제조건 충족 필요).")


def judge_urban_permit(label: str, permit: dict[str, Any] | None,
                       gate: dict[str, Any] | None) -> dict[str, Any]:
    """인허가 리스크·로드맵 — 게이트가 BLOCK/TENTATIVE면 리스크 상향."""
    if not permit:
        return _item("permit", label, "missing", None, "리스크 등급",
                     "인허가 분석 미확보(무목업).")
    decision = (gate or {}).get("decision")
    if decision == "BLOCK":
        risk, status = "상(차단 필지 존재)", "missing"
    elif decision == "TENTATIVE":
        risk, status = "중(선행절차 전제)", "tentative"
    else:
        risk, status = "하~중", "pass"
    methods = permit.get("methods") or []
    return _item("permit", label, status,
                 {"risk": risk, "summary": permit.get("summary"),
                  "method_count": len(methods)},
                 "리스크 등급", permit.get("recommendation"))
