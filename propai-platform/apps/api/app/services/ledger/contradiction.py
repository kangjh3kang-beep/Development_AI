"""Phase 2 결정론 모순 탐지 — prior(원장) vs 현재 분석의 모순을 자동 플래그한다.

순수 함수(LLM·DB 없음). 새 수치/판정을 만들지 않는다(비교·플래그 전용).
적용: design_audit(findings_brief) · comprehensive(site_analysis) · feasibility.
"""
from __future__ import annotations

import re
from typing import Any

# 그룹당 노출하는 원본(비정규화) 키 표본 최대 개수(전량 노출은 표시 폭발 재발 — 상한 고정).
_GROUP_SAMPLE_KEYS_MAX = 3
# 점경로 키의 배열 인덱스(예: scenarios[0])를 감지하는 정규식 — [*]로 정규화한다.
_ARRAY_INDEX_RE = re.compile(r"\[\d+\]")

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
        rel = abs(delta) / denom if denom > 1e-09 else 0.0 if abs(delta) <= 1e-09 else float("inf")
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


def _normalize_key(key: str) -> str:
    """점경로 키의 배열 인덱스([0]·[12] 등)를 [*]로 정규화 — 표시 폭발 집계 전용.

    쉬운 설명: 하나의 근본 변경(예: 종상향 시나리오 재산정)이 scenarios[0]..scenarios[9]처럼
    숫자만 다른 leaf 10~20개로 흩어지면 화면에 모순 20개가 뜬다(실제로는 원인 1개). 인덱스
    숫자만 지우면 "같은 자리(패턴)"를 알아볼 수 있어 그 leaf들을 한 그룹으로 묶을 수 있다.
    """
    return _ARRAY_INDEX_RE.sub("[*]", key)


def _group_contradictions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """모순 항목을 (정규화 키, prev, now) 동일 기준으로 묶어 표시 폭발을 해소한다.

    기존 `contradictions`(leaf 단위 전량)는 그대로 두고(하위호환), 여기서는 집계용 `groups`만
    별도로 만든다. prev/now가 서로 다른 leaf(예: 시나리오별 실제 다른 수치)는 여전히 별도
    그룹으로 남는다 — 이 함수는 "같은 자리 + 같은 값 변화"만 묶어 무손실로 압축한다.
    """
    order: list[tuple[str, str, str]] = []
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for it in items:
        raw_key = str(it.get("key", ""))
        norm_key = _normalize_key(raw_key)
        # prev/now는 항상 스칼라(status 문자열 또는 float)이나, 방어적으로 문자열화해
        # 그룹핑 키로 쓴다(비교연산자 없이도 안전하게 동치 판정).
        group_key = (norm_key, str(it.get("prev")), str(it.get("now")))
        if group_key not in buckets:
            buckets[group_key] = []
            order.append(group_key)
        buckets[group_key].append(it)

    groups: list[dict[str, Any]] = []
    for gk in order:
        members = buckets[gk]
        rep = members[0]
        groups.append({
            "key_pattern": gk[0],
            "leaf_count": len(members),
            "prev": rep.get("prev"),
            "now": rep.get("now"),
            "rel_change": rep.get("rel_change"),
            "severity": rep.get("severity"),
            "sample_keys": [str(m.get("key")) for m in members[:_GROUP_SAMPLE_KEYS_MAX]],
        })
    return groups


def detect_contradictions(
    prior: Any, current: Any,
    *, rel_threshold: float = 0.10, abs_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """prior payload vs 현재 payload 모순(status 플립 + 수치 델타) 결정론 집계.

    prior/current는 원장 payload 또는 {'payload': ...} 래퍼 허용.
    반환: {contradictions, counts(by severity), max_severity, has_contradiction,
    groups(additive — 정규화 키+prev+now 동일 leaf 묶음), group_counts(그룹 기준 severity 집계),
    max_severity_by_group(그룹 기준 최고 심각도), note}.
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

    groups = _group_contradictions(items)
    group_counts = {"low": 0, "medium": 0, "high": 0}
    for g in groups:
        sev = g.get("severity")
        if sev in group_counts:
            group_counts[sev] += 1
    max_sev_grouped = next((s for s in ("high", "medium", "low") if group_counts.get(s)), None)

    return {
        "contradictions": items, "counts": counts, "max_severity": max_sev,
        "has_contradiction": bool(items),
        "groups": groups, "group_counts": group_counts,
        "max_severity_by_group": max_sev_grouped,
        "note": "결정론 모순탐지(prior 대비 status 플립·수치 델타) — 판정/수치 비생성, 비교 전용",
    }
