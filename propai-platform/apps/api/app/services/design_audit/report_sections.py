"""설계심사(Design Audit) S4/S7 원자료 → 화면(웹)·PDF 공용 정규화 헬퍼.

배경(QA 레인B — 배관 봉합): design_audit_orchestrator가 내는 sections 원자료는
  · s4_incentives = {effective_far, donation_simulation, upzoning}  (dict)
  · efficiency_metrics = {efficiency_pct, core_ratio_pct, common_area_ratio_pct, basis, notes}  (dict)
인데, 라우터(_build_report_sections)가 이 dict를 그대로 `{"incentives": s4}` /
`{"evidence": eff}`로 실어 보내면 프론트(AuditReportView)는 `Array.isArray(sec.incentives)` /
`Array.isArray(sec.evidence)`가 항상 false가 돼 "표시할 결과가 없습니다"로 렌더된다
(형상 불일치 — dict를 배열 계약에 그대로 얹은 결함).

이 모듈은 그 변환을 한 곳에 모아 웹·PDF가 같은 함수를 재사용하게 한다:
  - efficiency_metrics_rows(): PDF KVTableBlock이 쓰던 `list(metrics.items())[:20]`과
    바이트 단위로 동일한 (key, value) 원시 행을 낸다(PDF 출력 무회귀 보장).
  - efficiency_metrics_to_evidence(): 위 원시 값을 웹 AuditEvidence[] 계약
    ([{label, value, basis}])으로 사람이 읽는 라벨과 함께 정규화한다.
  - s4_incentives_to_web(): s4_incentives dict → 웹 AuditSection 계약
    ({"incentives": AuditIncentive[], "upzoning_scenarios": [...]})으로 정규화한다.
    upzoning.scenarios[]는 UpzoningPotentialAnalyzer.analyze() 산출을 그대로
    통과시킨다(프론트 UpzoningScenarioList가 이미 이 snake_case 계약을 소비).

무날조: 원자료에 없는 값은 만들어내지 않는다. 원자료가 비었으면 빈 dict/리스트를 반환하고
호출부(라우터)가 "존재하는 원자료만" 섹션에 싣는다(빈 섹션 생성 금지 원칙 유지).
"""

from __future__ import annotations

from typing import Any

# 효율 지표 원시 키 → 사람이 읽는 한글 라벨(순서 고정 — 표시 순서).
_EFFICIENCY_LABELS: dict[str, str] = {
    "efficiency_pct": "전용률",
    "core_ratio_pct": "코어비율",
    "common_area_ratio_pct": "공용비율",
}


def efficiency_metrics_rows(metrics: dict[str, Any] | None) -> list[tuple[str, Any]]:
    """S7 efficiency_metrics dict → (key, value) 원시 행.

    ★design_audit_adapter._metrics()가 기존에 하던 `[(str(k), v) for k, v in
    list(metrics.items())[:20]]`와 완전히 동형이다 — PDF KVTableBlock 출력을
    바이트 단위로 보존하기 위해 라벨 번역·필터링을 전혀 하지 않는다(PDF 무회귀).
    """
    if not isinstance(metrics, dict):
        return []
    return [(str(k), v) for k, v in list(metrics.items())[:20]]


def efficiency_metrics_to_evidence(metrics: dict[str, Any] | None) -> list[dict[str, Any]]:
    """S7 efficiency_metrics dict → 웹 AuditEvidence[] 계약([{label, value, basis}]).

    - 값이 None인 지표는 생략(가짜 0 표기 금지).
    - notes(list[str])는 각각 "참고" 행으로 풀어낸다 — 미산출 사유(예: "코어면적 데이터
      없음")를 화면에서 정직하게 보이게 한다(빈 카드 대신 사유 표기).
    """
    if not isinstance(metrics, dict) or not metrics:
        return []
    basis = metrics.get("basis")
    rows: list[dict[str, Any]] = []
    for key, label in _EFFICIENCY_LABELS.items():
        v = metrics.get(key)
        if v is None:
            continue
        row: dict[str, Any] = {"label": label, "value": f"{v}%"}
        if key == "efficiency_pct" and basis:
            row["basis"] = basis
        rows.append(row)
    for note in metrics.get("notes") or []:
        if note:
            rows.append({"label": "참고", "value": str(note)})
    return rows


def s4_incentives_to_web(s4: dict[str, Any] | None) -> dict[str, Any]:
    """S4 s4_incentives dict({effective_far, donation_simulation, upzoning}) →
    웹 AuditSection 계약({"incentives": AuditIncentive[], "upzoning_scenarios": [...]}).

    - donation_simulation(far_incentive_calculator.calculate 출력)을 기부채납 인센티브
      카드 1건으로 정규화한다. skipped(용도지역 미매칭 등)면 사유만 담은 카드로 정직 표기.
    - upzoning.scenarios[]는 UpzoningPotentialAnalyzer 산출을 그대로 통과시킨다(프론트
      UpzoningScenarioList가 이미 이 snake_case 계약을 소비 — 여기서 재가공하지 않는다).
    - 표시할 내용이 전혀 없으면 빈 dict(호출부가 섹션 자체를 생략하도록).
    """
    if not isinstance(s4, dict):
        return {}
    effective = s4.get("effective_far") if isinstance(s4.get("effective_far"), dict) else {}
    donation = s4.get("donation_simulation") if isinstance(s4.get("donation_simulation"), dict) else {}
    upzoning = s4.get("upzoning") if isinstance(s4.get("upzoning"), dict) else {}

    incentives: list[dict[str, Any]] = []
    if donation:
        skip_reason = donation.get("skipped")
        if skip_reason:
            incentives.append({
                "name": "기부채납 용적률 인센티브",
                "description": str(skip_reason),
                "estimated": True,
            })
        elif donation.get("incentive_far") is not None:
            eff_pct = effective.get("effective_far_pct")
            base_far = donation.get("base_far")
            allowed_far = donation.get("allowed_far")
            max_far = donation.get("max_far")
            desc_parts: list[str] = []
            if eff_pct is not None:
                desc_parts.append(f"현재 실효 용적률 {eff_pct}%")
            if base_far is not None and allowed_far is not None:
                desc_parts.append(
                    f"기부채납 시 {base_far}% → 최대 {allowed_far}%"
                    + (f"(법정상한 {max_far}% 이내)" if max_far is not None else "")
                )
            incentives.append({
                "name": "기부채납 용적률 인센티브",
                "path": donation.get("legal_basis"),
                "description": " · ".join(desc_parts) or None,
                "bonus_far_pp": donation.get("incentive_far"),
                # 예상치(실현 보장 아님) — far_incentive_potential finding.note와 동일 취지 마커.
                "estimated": True,
            })

    scenarios = upzoning.get("scenarios") if isinstance(upzoning.get("scenarios"), list) else []

    out: dict[str, Any] = {}
    if incentives:
        out["incentives"] = incentives
    if scenarios:
        out["upzoning_scenarios"] = scenarios
    if upzoning.get("summary"):
        out["upzoning_summary"] = upzoning.get("summary")
    return out
