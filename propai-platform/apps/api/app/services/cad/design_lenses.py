"""다각 렌즈 평가(P5) — 생성된 설계를 4관점에서 결정론 채점(할루시네이션 없음).

수익성·거주성·법규·시공성 4렌즈를 커널 산출값(summary)과 법규 위반(violations)으로만
점수화한다. LLM이 아니라 계산값으로 채점하므로 가짜 점수가 없다. 각 렌즈는 점수(0~100)+
근거(커널값 인용)+개선 힌트를 제공해 사용자–LLM 협업의 '다각' 관점을 만든다.
"""

from __future__ import annotations

from typing import Any

from .design_spec import legal_limits_for


def _clamp(x: float, lo: float = 0, hi: float = 100) -> int:
    return int(max(lo, min(hi, round(x))))


def evaluate_lenses(spec: dict[str, Any], summary: dict[str, Any],
                    violations: list[dict[str, Any]]) -> dict[str, Any]:
    """설계를 4관점에서 채점. 반환: {lenses:[{lens,label,score,basis,hint}], overall}."""
    lim = legal_limits_for(spec.get("zone_code", "2R"))
    far = float(summary.get("far_percent") or 0)
    units = int(summary.get("total_units") or 0)
    floors = int(summary.get("num_floors") or 1)
    gfa = float(summary.get("total_floor_area_sqm") or 0)
    cores = int(summary.get("core_count") or 1)
    errs = sum(1 for v in violations if v.get("severity") == "error")
    warns = sum(1 for v in violations if v.get("severity") == "warn")

    lenses: list[dict[str, Any]] = []

    # 1) 수익성 — 법정 용적률 활용도 + 세대 확보
    far_cap = lim.floor_area_ratio * 100
    far_use = (far / far_cap) if far_cap > 0 else 0
    lenses.append({
        "lens": "yield", "label": "수익성", "score": _clamp(far_use * 100),
        "basis": f"용적률 {far:.0f}%/법정 {far_cap:.0f}% 활용 {far_use * 100:.0f}% · {units}세대",
        "hint": "용적률 여유분을 층수·세대로 활용" if far_use < 0.95 else "용적률 거의 최대 활용",
    })

    # 2) 거주성 — 세대당 연면적(여유) + 코어 접근성
    avg_unit = (gfa / units) if units > 0 else 0
    liv = min(1.0, avg_unit / 90) * 100  # 세대당 연면적 90㎡ 기준 만점
    lenses.append({
        "lens": "livability", "label": "거주성", "score": _clamp(liv),
        "basis": f"세대당 연면적 약 {avg_unit:.0f}㎡(전용은 그보다 작음) · 코어 {cores}개",
        "hint": "중대형 평형 비중↑로 거주성 강화" if liv < 60 else "거주 면적 양호",
    })

    # 3) 법규 — 위반 없으면 만점, 중대 -25/경고 -8
    comp = 100 - errs * 25 - warns * 8
    lenses.append({
        "lens": "compliance", "label": "법규", "score": _clamp(comp),
        "basis": (f"위반 중대 {errs}건·경고 {warns}건" if (errs or warns) else "법정 한도 내 적합"),
        "hint": "위반 항목 우선 해소" if errs else ("경고 항목 점검" if warns else "법규 적합"),
    })

    # 4) 시공성 — 층수 과다·코어 과다 시 난이도↑(정형·중층이 유리)
    floor_pen = max(0, floors - 15) * 2
    core_pen = max(0, cores - 3) * 5
    const = 92 - floor_pen - core_pen
    lenses.append({
        "lens": "constructability", "label": "시공성", "score": _clamp(const),
        "basis": f"{floors}층·코어 {cores}개 규모",
        "hint": "층수 분산/정형화로 공기·공비 절감" if const < 70 else "시공 난이도 적정",
    })

    overall = round(sum(latem["score"] for latem in lenses) / len(lenses))
    return {"lenses": lenses, "overall": overall}
