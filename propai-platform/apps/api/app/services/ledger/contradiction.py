"""Phase 2 결정론 모순 탐지 — prior(원장) vs 현재 분석의 모순을 자동 플래그한다.

순수 함수(LLM·DB 없음). 새 수치/판정을 만들지 않는다(비교·플래그 전용).
적용: design_audit(findings_brief) · comprehensive(site_analysis) · feasibility.
"""
from __future__ import annotations

from typing import Any

# status 위계(낮을수록 양호). 한/영 동의어 동일 랭크.
_STATUS_RANK: dict[str, int] = {
    "pass": 0, "ok": 0, "적합": 0, "정상": 0,
    "warning": 1, "warn": 1, "조건부적합": 1, "주의": 1,
    "fail": 2, "부적합": 2, "위반": 2, "error": 2,
}


def _norm_status(s: Any) -> str | None:
    if s is None:
        return None
    return str(s).strip().lower()


def _status_rank(s: Any) -> int | None:
    return _STATUS_RANK.get(_norm_status(s) or "")


def _flip_severity(prev: Any, now: Any) -> str:
    """status 플립 심각도(결정론): 악화 폭이 클수록 높음. 개선/미지는 low."""
    pr, nr = _status_rank(prev), _status_rank(now)
    if pr is None or nr is None:
        return "low"
    diff = nr - pr
    if diff >= 2:
        return "high"
    if diff == 1:
        return "medium"
    return "low"


def _numeric_severity(rel: float) -> str:
    if rel >= 0.20:           # inf 포함
        return "high"
    if rel >= 0.10:
        return "medium"
    return "low"


def detect_status_flips(prior_status: dict[str, Any], current_status: dict[str, Any]) -> list[dict[str, Any]]:
    """동일 키 status 변화 플래그(+severity). 키 정렬로 결정론."""
    flips: list[dict[str, Any]] = []
    for key in sorted(set(prior_status) & set(current_status)):
        pv, cv = prior_status[key], current_status[key]
        if _norm_status(pv) != _norm_status(cv):
            flips.append({"kind": "status_flip", "key": key, "prev": pv, "now": cv,
                          "severity": _flip_severity(pv, cv)})
    return flips


def detect_numeric_deltas(
    prior_numbers: dict[str, float], current_numbers: dict[str, float],
    *, rel_threshold: float = 0.10, abs_thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """동일 키 수치의 상대변화(또는 키별 절대임계) 초과 플래그(+severity). 결정론."""
    abs_thresholds = abs_thresholds or {}
    out: list[dict[str, Any]] = []
    for key in sorted(set(prior_numbers) & set(current_numbers)):
        pv, cv = float(prior_numbers[key]), float(current_numbers[key])
        delta = cv - pv
        denom = abs(pv)
        if denom > 1e-9:
            rel = abs(delta) / denom
        else:
            rel = 0.0 if abs(delta) <= 1e-9 else float("inf")
        key_abs = abs_thresholds.get(key)
        flagged = (key_abs is not None and abs(delta) >= key_abs) or rel >= rel_threshold
        if not flagged:
            continue
        out.append({"kind": "numeric_delta", "key": key, "prev": pv, "now": cv, "delta": delta,
                    "rel_change": None if rel == float("inf") else round(rel, 4),
                    "severity": _numeric_severity(rel)})
    return out


def extract_status(payload: Any) -> dict[str, str]:
    """payload에서 (식별자→status) 추출. findings_brief/findings + 최상위 verdict."""
    out: dict[str, str] = {}
    if not isinstance(payload, dict):
        return out
    for listkey in ("findings_brief", "findings"):
        items = payload.get(listkey)
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("status") is not None:
                    cid = it.get("check_id") or it.get("id") or it.get("name")
                    if cid is not None:
                        out[str(cid)] = it.get("status")
    if payload.get("verdict") is not None:
        out["__verdict__"] = payload.get("verdict")
    return out


def extract_numbers(payload: Any, *, _prefix: str = "", _out: dict[str, float] | None = None,
                    _depth: int = 0) -> dict[str, float]:
    """payload를 점경로 키로 평탄화해 수치만 추출(bool 제외, 깊이 제한). 결정론."""
    out = {} if _out is None else _out
    if _depth > 12 or isinstance(payload, bool):
        return out
    if isinstance(payload, (int, float)):
        if _prefix:
            out[_prefix] = float(payload)
        return out
    if isinstance(payload, dict):
        for k in payload:
            extract_numbers(payload[k], _prefix=f"{_prefix}.{k}" if _prefix else str(k),
                            _out=out, _depth=_depth + 1)
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            extract_numbers(v, _prefix=f"{_prefix}[{i}]", _out=out, _depth=_depth + 1)
    return out


def _unwrap(p: Any) -> dict[str, Any]:
    if isinstance(p, dict) and "payload" in p and isinstance(p.get("payload"), dict):
        return p["payload"]
    return p if isinstance(p, dict) else {}


def detect_contradictions(
    prior: Any, current: Any,
    *, rel_threshold: float = 0.10, abs_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """prior payload vs 현재 payload 모순(status 플립 + 수치 델타) 결정론 집계.

    prior/current는 원장 payload 또는 {'payload': ...} 래퍼 허용.
    반환: {contradictions, counts(by severity), max_severity, has_contradiction, note}.
    """
    pp, cc = _unwrap(prior), _unwrap(current)
    flips = detect_status_flips(extract_status(pp), extract_status(cc))
    deltas = detect_numeric_deltas(extract_numbers(pp), extract_numbers(cc),
                                   rel_threshold=rel_threshold, abs_thresholds=abs_thresholds)
    items = flips + deltas
    counts = {"low": 0, "medium": 0, "high": 0}
    for it in items:
        counts[it["severity"]] = counts.get(it["severity"], 0) + 1
    max_sev = next((s for s in ("high", "medium", "low") if counts.get(s)), None)
    return {
        "contradictions": items, "counts": counts, "max_severity": max_sev,
        "has_contradiction": bool(items),
        "note": "결정론 모순탐지(prior 대비 status 플립·수치 델타) — 판정/수치 비생성, 비교 전용",
    }
