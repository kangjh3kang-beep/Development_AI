"""파생형 락 — **analyzer 가 내보내는 metrics 키는 그려지거나, 사유와 함께 면제되어야 한다.**

## 왜 필요한가

`GrowthDashboard.InsightMetrics` 는 `metrics_json` 을 **insight_type 별 손수 `switch`** 로 그린다.
그래서 백엔드가 키를 늘려도 **화면은 조용히 모른다** — 이 저장소의 단골 형태(*"정의만 하고 소비처 0"*)다.

★역설이 이 락의 존재 이유다: `analyzer.py:468~479` 는 커버리지를 **전 타입에** 박으면서
*"타입별 손수 분기는 새 타입을 자동으로 누락시킨다"* 고 **적어 두었다.**
**생산자가 방어한 그 함정을 소비자가 저질렀다** — `analysis_coverage` 는 라이브에서
`fallback_rate judged=0/2 (하한 10)`(= **판정 불가**)를 싣고 있었는데 화면 참조가 **0건**이었다.

## 설계 — 「전부 그려라」로 잠그지 않는다

*"모든 키를 그려야 한다"* 로 강제하면 **정상적인 디자인 판단을 막는다**(가드의 위양성도 결함).
실제로 `fallback`·`signature` 는 **사유와 함께 의도적으로 면제**돼 있다
(*"산문이 이미 말하고 그 문장이 카드 바로 아래 렌더된다"*).

그래서 **둘 중 하나**를 강제한다:
  ① 렌더러가 그 키를 **읽는다**, 또는
  ② `_EXEMPT` 에 **사유와 함께** 적혀 있다.
그리고 **죽은 면제**(더 이상 생산되지 않는 키를 면제)는 **실패**시킨다 —
면제가 쌓이면 그 자체가 다음 사람을 속인다.

## ★이 락의 한계(명시)

`metrics_json` 에 `**metrics` 처럼 **스프레드로 합쳐지는 키**는 정적으로 못 읽는다
(실측: `fail_pct`·`down_pct` 가 `_classify_quality` 반환값에서 온다).
→ **리터럴 키만** 모집단으로 삼는다. **이 락은 하한이다.**
★그리고 축은 **`analyzer.py` 한 파일**이다. `improvement_proposal`·`heal_*` 등 다른 모듈이
생산하는 타입은 **미측정**이다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_API = Path(__file__).resolve().parents[1]
_WEB = _API.parents[0] / "web"
_ANALYZER = _API / "app" / "services" / "growth" / "analyzer.py"
_PR_TASK = _API / "app" / "tasks" / "growth_pr_task.py"
_AGENT = _API / "app" / "services" / "growth" / "improvement_agent.py"
_DASH = _WEB / "components" / "settings" / "GrowthDashboard.tsx"

#: 그리지 않기로 **결정한** 키 → 사유. 사유 없는 면제는 문법적으로 불가능하다(dict 값 필수).
#: ★죽은 면제는 아래 테스트가 실패시킨다.
_EXEMPT: dict[str, str] = {
    "fallback": "분자(폴백 건수)는 _rule_narrative 산문이 이미 말하고 그 문장이 카드 바로 아래 렌더된다",
    "signature": "군집 해시는 사람이 읽을 값이 아니다 — route+status_code 로 식별된다",
    "sample": "라이브에서 빈 문자열이었다(수집부가 아직 안 싣는다) — 값이 실리면 면제를 지워라",
    "producer_build_id": "어느 빌드가 썼는지는 조사자용이다 — 운영 화면의 정보 밀도를 낮춘다",
    "verify_total": "raw 카운트 대신 fail_pct(백분율)를 그린다",
    "fail": "raw 카운트 대신 fail_pct(백분율)를 그린다",
    "warn": "raw 카운트 대신 fail_pct(백분율)를 그린다",
    "feedback_total": "raw 카운트 대신 down_pct(백분율)를 그린다",
    "down": "raw 카운트 대신 down_pct(백분율)를 그린다",
}

#: 전 타입에 주입되는 공통 키(analyzer.py 가 INSERT 시점에 박는다).
_COMMON = ("producer_build_id", "analysis_coverage")

_JSX_COMMENT = re.compile(r"\{\s*/\*.*?\*/\s*\}", re.S)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<![:\w])//[^\n]*")


class ScannerDeadError(RuntimeError):
    """추출기가 죽었다 — **위반이 아니다.**

    `AssertionError` 와 **다른 예외**로 던진다. 뭉치면 *"검사기가 죽었다"* 가
    *"깨끗하다"* 로 읽힌다(`tests/_scan_guard.py` 가 같은 규율을 강제한다).
    """


def _produced() -> dict[str, set[str]]:
    """analyzer.py 가 만드는 insight dict 의 `metrics_json` **리터럴 키**를 ast 로 파생."""
    tree = ast.parse(_ANALYZER.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        names = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if "insight_type" not in names or "metrics_json" not in names:
            continue
        itype = None
        keys: set[str] = set()
        for k, v in zip(node.keys, node.values, strict=False):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            if k.value == "insight_type" and isinstance(v, ast.Constant):
                itype = v.value
            elif k.value == "metrics_json" and isinstance(v, ast.Dict):
                # ★`**spread` 는 키가 None 으로 온다 — 정적으로 못 읽으므로 **세지 않는다**.
                keys = {
                    mk.value
                    for mk in v.keys
                    if isinstance(mk, ast.Constant) and isinstance(mk.value, str)
                }
        if itype and keys:
            out.setdefault(itype, set()).update(keys)
    if not out:
        raise ScannerDeadError(
            "analyzer.py 에서 insight dict 를 하나도 못 읽었다 — 구조가 바뀌었다(위반 아님)."
        )
    return out


def _dash_code() -> str:
    """대시보드에서 **주석 3종(줄·블록·JSX)** 을 걷은 실행 소스."""
    src = _DASH.read_text(encoding="utf-8")
    for rx in (_JSX_COMMENT, _BLOCK_COMMENT):
        src = rx.sub(lambda m: "\n" * m.group(0).count("\n"), src)
    return _LINE_COMMENT.sub("", src)


def _referenced() -> set[str]:
    """대시보드 **실행 줄**이 참조하는 metrics 키."""
    src = _DASH.read_text(encoding="utf-8")
    for rx in (_JSX_COMMENT, _BLOCK_COMMENT):
        src = rx.sub(lambda m: "\n" * m.group(0).count("\n"), src)
    src = _LINE_COMMENT.sub("", src)
    refs: set[str] = set()
    refs |= set(re.findall(r'\bm\s*\[\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\]', src))
    refs |= set(re.findall(r"\bm\.([A-Za-z_][A-Za-z0-9_]*)", src))
    refs |= set(re.findall(r'\(\s*m\s*,\s*"([A-Za-z_][A-Za-z0-9_]*)"', src))
    # `(m as Record<string, unknown>).analysis_coverage` 형태도 잡는다.
    refs |= set(re.findall(r"\bunknown>\s*\)\s*\.([A-Za-z_][A-Za-z0-9_]*)", src))
    if not refs:
        raise ScannerDeadError("대시보드에서 metrics 참조를 하나도 못 읽었다(위반 아님).")
    return refs


def test_extractors_are_alive() -> None:
    """★공허한 초록 방지 — 추출이 죽어서 '위반 0'이 되는 것과 진짜 0을 구별한다."""
    assert _ANALYZER.is_file() and _DASH.is_file()
    produced = _produced()
    refs = _referenced()
    assert len(produced) >= 4, f"타입을 {len(produced)}종만 읽었다 — 파생이 죽었다: {sorted(produced)}"
    # 양성 대조군: 양쪽 모두 반드시 갖고 있어야 하는 값.
    assert "fallback_rate" in produced, "analyzer 에서 fallback_rate 를 못 찾았다"
    assert "service" in {k for ks in produced.values() for k in ks}
    assert "service" in refs and "fallback_pct" in refs


def test_every_produced_key_is_drawn_or_exempted_with_a_reason() -> None:
    """생산되는 키는 **그려지거나 · 사유와 함께 면제**되어야 한다."""
    produced = _produced()
    refs = _referenced()
    owners: dict[str, list[str]] = {}
    for itype, keys in produced.items():
        for k in keys:
            owners.setdefault(k, []).append(itype)
    for k in _COMMON:
        owners.setdefault(k, []).append("(전 타입 공통)")

    orphan = sorted(k for k in owners if k not in refs and k not in _EXEMPT)
    assert not orphan, (
        "analyzer 가 내보내는데 화면이 안 읽고 면제도 없는 키: "
        + ", ".join(f"{k}({'/'.join(owners[k])})" for k in orphan)
        + ". 그리거나, _EXEMPT 에 **사유와 함께** 적어라."
    )


def test_no_dead_exemption() -> None:
    """★죽은 면제는 실패 — 면제가 쌓이면 그 자체가 다음 사람을 속인다."""
    produced = _produced()
    live = {k for ks in produced.values() for k in ks} | set(_COMMON)
    dead = sorted(k for k in _EXEMPT if k not in live)
    assert not dead, (
        f"더 이상 생산되지 않는 키를 면제하고 있다: {dead}. _EXEMPT 에서 지워라."
    )


def test_exemption_reasons_are_not_empty() -> None:
    """사유 없는 면제는 면제가 아니라 침묵이다."""
    blank = sorted(k for k, why in _EXEMPT.items() if len(why.strip()) < 10)
    assert not blank, f"사유가 비었거나 너무 짧은 면제: {blank}"


def test_coverage_is_surfaced_type_agnostically() -> None:
    """★배선 — 커버리지는 **타입별 switch 밖**에서 붙어야 한다.

    analyzer 가 커버리지를 전 타입에 박은 이유가 *"타입별 손수 분기는 새 타입을 자동으로
    누락시킨다"* 이므로, 소비 쪽이 그것을 `case` 안에 넣으면 **같은 함정을 되만든다.**
    """
    src = _DASH.read_text(encoding="utf-8")
    for rx in (_JSX_COMMENT, _BLOCK_COMMENT):
        src = rx.sub(lambda m: "\n" * m.group(0).count("\n"), src)
    src = _LINE_COMMENT.sub("", src)

    idx = src.find("analysis_coverage")
    assert idx > 0, "대시보드가 analysis_coverage 를 안 읽는다 — 판정 불가가 화면에 안 나온다."
    head = src[:idx]
    opened = head.count("switch (insight.insight_type)")
    assert opened >= 1, "InsightMetrics 의 switch 를 못 찾았다 — 구조가 바뀌었다(위반 아님)."
    # switch 블록이 닫힌 뒤에 있어야 한다: 마지막 `case ` 보다 뒤이고, 어떤 `case` 안도 아니다.
    last_case = head.rfind("case ")
    between = head[last_case:] if last_case > 0 else ""
    assert "}" in between and between.count("}") >= 2, (
        "analysis_coverage 가 특정 case 안에 있는 것으로 보인다 — switch 밖으로 빼라.\n"
        f"검사한 꼬리: {between[-200:]!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ★pr_status 라벨 파리티 (2026-08-27)
#
# 라이브 실측: `improvement_proposal` **53건 전부** `pr_status="artifact_only"` 인데
# 화면은 **영문 원문을 그대로** 찍고 있었다. `artifact_only` = *"GH_TOKEN 이 없어 PR 미생성"*
# 인데 운영자는 그것이 정상 축약인지 장애인지 알 수 없다.
# `#808`(인사이트 7종이 라벨 없이 raw 로 떴다)과 **같은 결함 클래스**의 다른 축이다.
# ─────────────────────────────────────────────────────────────────────────────

_PR_LABEL_KEY = re.compile(r"^\s*([a-z_]+)\s*:\s*\"", re.M)


def _pr_status_values() -> set[str]:
    """백엔드가 쓰는 pr_status 값을 **두 생산지**에서 파생한다.

    ① `growth_pr_task._mark_pr_status(db, id, "<값>")` 호출부
    ② `improvement_agent` 의 초기값 `"pr_status": "<값>"`
    ★한 곳만 보면 초기값(`draft_only`)을 놓친다 — 실제로 그 값은 태스크가 아니라
      제안 생성 시점에 박힌다.
    """
    out: set[str] = set()
    out |= set(re.findall(r'_mark_pr_status\([^,]+,\s*[^,]+,\s*"([a-z_]+)"',
                          _PR_TASK.read_text(encoding="utf-8")))
    out |= set(re.findall(r'"pr_status":\s*"([a-z_]+)"',
                          _AGENT.read_text(encoding="utf-8")))
    if not out:
        raise ScannerDeadError("pr_status 값을 하나도 못 읽었다 — 표기가 바뀌었다(위반 아님).")
    return out


def _pr_label_keys() -> set[str]:
    src = _dash_code()
    start = src.find("const PR_STATUS_LABELS")
    end = src.find("};", start) if start >= 0 else -1
    if start < 0 or end < 0:
        raise ScannerDeadError("PR_STATUS_LABELS 블록을 못 찾았다(위반 아님).")
    keys = set(_PR_LABEL_KEY.findall(src[start:end]))
    if not keys:
        raise ScannerDeadError("PR_STATUS_LABELS 에서 키를 하나도 못 읽었다(위반 아님).")
    return keys


def test_pr_status_extractors_are_alive() -> None:
    """★공허한 초록 방지 + 양성 대조군."""
    vals = _pr_status_values()
    keys = _pr_label_keys()
    assert len(vals) >= 4, f"값을 {len(vals)}개만 읽었다: {sorted(vals)}"
    assert "artifact_only" in vals, "라이브 53/53 이 쓰는 값을 못 읽었다 — 추출기 사망"
    assert "draft_only" in vals, "초기값 축(improvement_agent)을 못 읽었다"
    assert "artifact_only" in keys


def test_every_pr_status_has_a_korean_label() -> None:
    """백엔드가 쓰는 상태 코드는 전부 한글 라벨이 있어야 한다."""
    missing = sorted(_pr_status_values() - _pr_label_keys())
    assert not missing, (
        f"영문 raw 로 화면에 뜨는 pr_status: {missing}. "
        "PR_STATUS_LABELS 에 추가하라 — #808 과 같은 결함 클래스다."
    )


def test_pr_status_labels_have_no_phantom() -> None:
    """역방향(느슨) — 아무도 안 내는 라벨은 표를 신뢰할 수 없게 만든다."""
    phantom = sorted(_pr_label_keys() - _pr_status_values())
    assert not phantom, f"라벨표에만 있고 백엔드가 안 내는 상태: {phantom}"


def test_pr_status_is_rendered_through_the_label() -> None:
    """★배선 — 라벨표가 **있는 것**과 렌더가 **태우는 것**은 다른 명제다."""
    code = _dash_code()
    assert 'value: prStatusLabel(prStatus)' in code, (
        "PR 상태 행이 라벨 함수를 안 태운다 — 표는 있는데 화면엔 여전히 raw 다."
    )
