"""Phase 2a — 결과예측(승인 가능성) 결정론 휴리스틱. ★정밀 확률(%) 미생성(학습모델 없이 날조 금지).

단계 산출(완결성 status·부합도 conformance·검증 verification_status)을 등급(높음/보통/낮음/미상)으로 결정론 매핑.
각 예측에 도출근거(rationale)+투입신호(basis)+한계(caveat) 동반(설명가능성). pluggable ML은 후속(데이터·배포팀).
"""
from __future__ import annotations

from typing import Any

from app.contracts.permit_result import OutcomePrediction

# 종합 승인 가능성 우선순위(가장 보수적 신호 우선): 낮음(명백 저조) > 미상(완결성 부족) > 보통 > 높음.
_OVERALL_PRECEDENCE = ["낮음", "미상", "보통", "높음"]


def predict_stage(stage: Any, predictor: str = "heuristic_v1") -> OutcomePrediction:
    """단계 승인 가능성 등급 — 완결성·부합도·검증의 결정론 휴리스틱. 정밀 확률 미생성(등급+근거+한계)."""
    status = getattr(stage, "status", "")
    conf = getattr(stage, "conformance", "")
    verif = getattr(stage, "verification_status", "")
    basis = [f"완결성={status}", f"부합도={conf}", f"검증={verif}"]
    # ★HELD는 conformance의 '미상/측정 불가 보류' 센티넬(status뿐 아니라 conformance도 검사) — 미상을
    #   약긍정(보통)으로 세탁 금지(무음 금지). 입력 미비 또는 기준 측정 불가 → 미상으로 표면화.
    if status in ("NEEDS_INPUT", "HELD") or conf == "HELD":
        like, why = "미상", "필요 입력/산출물 미비 또는 기준 측정 불가(보류) — 예측 불가, 보완 후 재평가"
    elif conf == "미흡" or verif == "BLOCKED":
        like, why = "낮음", "기준 미흡 또는 검증 차단 — 보완 없이는 승인 가능성 낮음"
    elif conf == "부합" and verif == "CONFIRMED":
        like, why = "높음", "기준 부합 + 검증 확정 — 승인 가능성 높음"
    else:
        like, why = "보통", "조건부/추가검토 — 보완·심의 결과에 따라 가변"
    return OutcomePrediction(likelihood=like, predictor=predictor, rationale=why, basis=basis)


def overall_outcome(likelihoods: list[str]) -> str:
    """단계 예측들의 종합 승인 가능성 — 보수적 우선순위(낮음>미상>보통>높음). 예측 없으면 미상."""
    present = set(likelihoods)
    for level in _OVERALL_PRECEDENCE:
        if level in present:
            return level
    return "미상"
