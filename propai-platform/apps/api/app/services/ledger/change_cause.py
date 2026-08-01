"""변경 원인 분류 — "값이 달라졌다"를 "왜 달라졌는지"로 바꾼다(순수 함수·LLM/DB 없음).

## 왜 필요한가 (쉬운 설명)

이전 분석과 지금 분석의 숫자가 다르면 지금까지는 전부 **"모순"** 이라고 표시했다. 그런데
실제로 화면에 뜬 사례를 보면 진짜 모순은 하나도 없었다:

- 대지면적 176,458㎡ → 152,826㎡ : 사용자가 **필지를 3개에서 2개로 다시 골랐다**(입력이 다름)
- 학교 수 5 → 1 : 우리가 **중복집계 버그를 고쳤다**(플랫폼이 더 정확해진 것)

둘 다 "모순"이 아닌데 빨간 경고로 뜨니, 사용자는 *지금 숫자가 의심스럽다*고 오해한다. 사실은
반대(입력이 다르거나, 지금이 더 정확)다. 그래서 **비교 전에 원인부터 가린다.**

## 어떻게 가리나

이미 원장 payload에 **입력 지문**(`signature_parts` — 주소·PNU·필지수·LLM여부·옵션)이 들어
있는데 그동안 비교에 쓰지 않았다. 이 지문을 먼저 대조하면:

- 지문이 다르다 → `INPUT_CHANGED`. **애초에 다른 대상을 잰 것**이라 비교 자체가 성립하지 않는다.
- 지문 같고 스키마 버전이 다르다 → `VERSION_CHANGED`. 계산 방식이 바뀐 것.
- 둘 다 같은데 값이 다르다 → `UNEXPLAINED`. **이때만 진짜 확인이 필요하다.**

## 정직 원칙 (중요)

- `INPUT_CHANGED`일 때 **어느 쪽이 맞다고 말하지 않는다.** 서로 다른 대상이라 우열이 없고,
  이 함수는 각 숫자가 어느 입력에서 나왔는지까지는 분해하지 못한다(예: 학교 수 감소가 필지
  변경 때문인지 dedup 수정 때문인지 구분 불가) → "직접 비교 불가"라고만 말한다.
- 원천 데이터 갱신(공시지가 고시 등)은 **현재 payload에 신선도 메타가 없어 탐지할 수 없다.**
  없는 근거로 분류를 만들지 않고, `UNEXPLAINED` 사유 문장에 가능성으로만 적는다(날조 금지).
"""

from __future__ import annotations

from typing import Any

# ── 원인 코드(안정 식별자 — 프론트 표시 분기·테스트가 이 값에 의존) ──
CAUSE_INPUT_CHANGED = "INPUT_CHANGED"
CAUSE_VERSION_CHANGED = "VERSION_CHANGED"
CAUSE_UNEXPLAINED = "UNEXPLAINED"
CAUSE_NONE = "NONE"  # 변화 자체가 없음

# signature_parts 인덱스 → 사람이 읽는 입력 항목명.
# ★계약: build_signature_parts()의 고정 순서(0~4)와 1:1. idx5+(호출부 전용 extra_parts)는
#   프론트가 재계산할 수 없어 비교에서 제외한다(use-analysis-history.ts와 동일 규칙).
_SIGNATURE_LABELS: tuple[str, ...] = ("주소", "필지(PNU)", "선택 필지 수", "AI 해석 사용", "분석 옵션")
_SIGNATURE_COMPARABLE = len(_SIGNATURE_LABELS)


def _unwrap(p: Any) -> dict[str, Any]:
    """원장 payload 래퍼({'payload': ...}) 허용 — contradiction._unwrap과 동일 규칙."""
    if isinstance(p, dict) and "payload" in p and isinstance(p.get("payload"), dict):
        return p["payload"]
    return p if isinstance(p, dict) else {}


def _signature_parts(payload: dict[str, Any]) -> list[str] | None:
    """payload에서 입력 지문 추출. 없으면 None(구버전 기록 — 분류 불가로 정직 처리)."""
    parts = payload.get("signature_parts")
    if isinstance(parts, list) and parts:
        return [str(p) for p in parts]
    return None


def diff_signature(prior: Any, current: Any) -> list[dict[str, Any]] | None:
    """두 분석의 입력 지문을 항목별로 대조한다.

    반환: 달라진 항목 목록 [{index, label, prev, now}]. 지문이 같으면 빈 리스트.
    한쪽이라도 지문이 없으면 **None**(모름 — 같다고 단정하지 않는다).
    """
    pp, cc = _signature_parts(_unwrap(prior)), _signature_parts(_unwrap(current))
    if pp is None or cc is None:
        return None
    changed: list[dict[str, Any]] = []
    # 비교는 계약된 고정 파트(0~4)까지만. 길이가 짧은 기록(구버전)도 있으므로 실제 길이로 자른다.
    limit = min(_SIGNATURE_COMPARABLE, len(pp), len(cc))
    for i in range(limit):
        if pp[i] != cc[i]:
            changed.append({"index": i, "label": _SIGNATURE_LABELS[i], "prev": pp[i], "now": cc[i]})
    return changed


def _schema_version(payload: dict[str, Any]) -> str | None:
    v = payload.get("schema_version")
    return str(v) if v is not None else None


def classify_change_cause(prior: Any, current: Any, *, has_changes: bool) -> dict[str, Any]:
    """이전↔현재 분석 사이 값 변화의 **원인**을 결정론으로 분류한다.

    has_changes: 값 차이가 실제로 검출됐는지(detect_contradictions 결과). False면 CAUSE_NONE.

    반환 계약:
      cause          — 위 CAUSE_* 중 하나
      headline       — 카드 제목에 쓰는 한 문장(비전문가 언어)
      reason         — 왜 그렇게 판정했는지(근거 문장)
      comparable     — 두 분석을 직접 비교해도 되는가(False면 우열 판단 금지)
      trust_hint     — 어느 쪽을 믿을지에 대한 정직한 안내(모르면 "판단 불가"라고 말한다)
      changed_inputs — 달라진 입력 항목(INPUT_CHANGED일 때만 채워짐)
      needs_review   — 사용자가 실제로 확인해야 하는가(UNEXPLAINED만 True)
    """
    pp, cc = _unwrap(prior), _unwrap(current)

    if not has_changes:
        return {
            "cause": CAUSE_NONE,
            "headline": "이전 분석과 동일합니다",
            "reason": "같은 입력으로 다시 분석했고 주요 수치가 모두 같습니다.",
            "comparable": True, "trust_hint": "두 분석 결과가 일치합니다.",
            "changed_inputs": [], "needs_review": False,
        }

    sig_diff = diff_signature(pp, cc)

    # ── ① 입력이 달라진 경우 — 애초에 다른 대상이라 비교 불가 ──
    if sig_diff:
        labels = ", ".join(d["label"] for d in sig_diff)
        detail = " / ".join(f"{d['label']}: {d['prev']} → {d['now']}" for d in sig_diff)
        return {
            "cause": CAUSE_INPUT_CHANGED,
            "headline": f"분석 조건이 바뀌었습니다 ({labels})",
            "reason": (
                f"이전 분석과 입력이 다릅니다 — {detail}. "
                "서로 다른 대상을 분석한 것이므로 수치가 달라지는 것이 정상입니다."
            ),
            "comparable": False,
            "trust_hint": (
                "두 결과는 각각의 조건에서 모두 유효합니다. 어느 쪽이 더 정확한지 따지는 비교 "
                "대상이 아니며, 지금 조건에 맞는 결과는 최신 분석입니다."
            ),
            "changed_inputs": sig_diff,
            "needs_review": False,
        }

    # ── ② 입력 동일 + 계산 방식(스키마) 변경 — 최신이 더 정확 ──
    pv, cv = _schema_version(pp), _schema_version(cc)
    if pv and cv and pv != cv:
        return {
            "cause": CAUSE_VERSION_CHANGED,
            "headline": "분석 방식이 개선되었습니다",
            "reason": (
                f"입력은 같지만 분석 기준이 바뀌었습니다({pv} → {cv}). "
                "계산 방식이 갱신되면 같은 대상이라도 결과 수치가 달라질 수 있습니다."
            ),
            "comparable": False,
            "trust_hint": "개선된 기준으로 계산한 최신 분석이 더 정확합니다.",
            "changed_inputs": [], "needs_review": False,
        }

    # ── ③ 입력·기준 동일한데 값이 다름 — 유일하게 확인이 필요한 경우 ──
    # ★정직: 지문을 못 읽은 경우(sig_diff is None)도 여기로 온다. "같다"고 단정할 근거가 없으므로
    #   확인 필요로 두되, 사유에 근거 부족을 명시한다(없는 확신을 만들지 않는다).
    unknown_input = sig_diff is None
    reason = (
        "이전 분석의 입력 정보가 기록되지 않아 조건이 같았는지 확인할 수 없습니다."
        if unknown_input else
        "입력과 분석 기준이 모두 같은데 수치가 달라졌습니다."
    )
    return {
        "cause": CAUSE_UNEXPLAINED,
        "headline": "확인이 필요한 차이가 있습니다",
        "reason": (
            f"{reason} 원천 데이터(공시지가 고시 등)가 갱신되었을 수 있으나, "
            "현재 기록만으로는 원인을 특정할 수 없습니다."
        ),
        "comparable": True,
        "trust_hint": "어느 쪽이 정확한지 판단하려면 아래 항목의 근거·출처를 직접 확인하세요.",
        "changed_inputs": [], "needs_review": True,
    }
