"""파생형 락 — **백엔드 리스크 사다리의 모든 등급이 화면 배지 표에 있어야 한다.**

## 왜 필요한가

`comprehensive_analysis_service._research_dev_plans` 는 `risk_level` 을
`protection_zone_severity.SEVERITY_ORDER` 사다리에서 고른다(5종). 화면
(`ComprehensiveAnalysisPanel.RISK_LEVEL_TONE`)은 그것을 **손으로 적은 표**로 색에 옮긴다.

실측(2026-08-27, `origin/main` 5a79f510): 사다리 **5종** vs 표 **4종** — `"중간"` 이 빠져 있었고
폴백이 `RISK_LEVEL_TONE["낮음"]`(= `--status-success`, 초록)이었다. 그래서
**제한보호구역 필지의 `중간` 리스크가 `낮음` 과 똑같은 초록 배지**로 칠해졌다.
배지 텍스트는 `종합 리스크 중간` 으로 옳았고 **색만 안전을 말했다** — 조용한 오표기다.

## ★오라클을 왜 이것으로 골랐나

라벨표의 정합성을 **라벨표 자신**으로 검사하면 동어반복이다(볼트 agent-lessons:81).
`SEVERITY_ORDER` 는 **라벨과 무관한 목적**(`severity_rank` 사다리 비교)으로 유지되므로,
등급을 추가하려면 **반드시** 그 튜플을 건드려야 한다 → 그때 이 락이 표를 강제로 묻는다.

## 방향별 엄격도 (볼트 agent-lessons:577)

- **방향① 사다리 → 표**: **엄격**. 산출되는 등급에 색이 없으면 폴백으로 샌다 = 실결함.
- **방향② 표 → 사다리**: **느슨**(유령 적발 목적뿐). 표에만 있는 키를 신고한다.
  역방향까지 엄격 패턴으로 보면 표기 하나 놓칠 때마다 **없는 유령**을 만든다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_WEB = _API.parents[0] / "web"

_SEVERITY_SSOT = _API / "app" / "services" / "regulation" / "protection_zone_severity.py"
_PANEL = _WEB / "lib" / "risk-level-style.ts"
_CONSUMER = _WEB / "components" / "analysis" / "ComprehensiveAnalysisPanel.tsx"
_BANNER = _WEB / "components" / "precheck" / "DominantConstraintBanner.tsx"

# 표 리터럴의 키만 뽑는다. 값(클래스 문자열)은 보지 않는다 — 문안은 계약이 아니다.
_KEY = re.compile(r'^\s*"([^"]+)"\s*:', re.M)
# 등급 → 톤 매핑의 **값**(톤 이름). 두 등급이 같은 톤이면 화면에서 구별 불가다.
_KV = re.compile(r'^\s*"([^"]+)"\s*:\s*"([a-z]+)"\s*,', re.M)

# ★주석 3종을 모두 걷는다. 처음엔 `//`·`/*` 만 걷었다가 **JSX 주석 `{/* … */}` 에 뚫려**
#   검사기가 주석 줄을 배지 렌더 줄로 집었다(이 테스트를 처음 돌렸을 때 실제로 그랬다).
#   소스 검사가 주석에 뚫리는 것은 이 저장소가 반복해 데인 형태다.
_JSX_COMMENT = re.compile(r"\{\s*/\*.*?\*/\s*\}", re.S)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<![:\w])//[^\n]*")


def _code_lines(path: Path | None = None) -> list[str]:
    """실행되는 줄만. 주석(줄·블록·JSX)을 제거한 뒤 줄로 나눈다."""
    src = (path or _PANEL).read_text(encoding="utf-8")
    # 줄 수를 보존하도록 주석은 개행만 남기고 지운다(줄 인덱스가 원본과 어긋나지 않게).
    def _blank(m: re.Match[str]) -> str:
        return "\n" * m.group(0).count("\n")

    src = _JSX_COMMENT.sub(_blank, src)
    src = _BLOCK_COMMENT.sub(_blank, src)
    src = _LINE_COMMENT.sub("", src)
    return src.splitlines()


class ScannerDeadError(RuntimeError):
    """추출기가 죽었다 — **위반이 아니다.**

    ★`AssertionError` 와 **다른 예외**로 던진다. 뭉치면 *"검사기가 죽었다"* 가
    *"깨끗하다"* 로 읽힌다(`tests/_scan_guard.py` 가 같은 규율을 강제한다).
    ★그리고 `()` 를 돌려주면 부분집합 단언이 **공허한 참**이 되어 소비 테스트가 전부
    초록이 된다(동료 세션 실측 지적 · 2026-08-27). 그래서 **여기서 즉시 죽인다.**
    """


def _ladder() -> tuple[str, ...]:
    """파이썬 SSOT 에서 SEVERITY_ORDER 를 **ast 로** 읽는다(정규식이 주석·독스트링에 뚫리지 않게)."""
    tree = ast.parse(_SEVERITY_SSOT.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        )
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "SEVERITY_ORDER":
                value = node.value
                if isinstance(value, ast.Tuple | ast.List):
                    return tuple(
                        e.value
                        for e in value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    )
    raise ScannerDeadError(
        f"{_SEVERITY_SSOT.name} 에서 SEVERITY_ORDER 리터럴을 못 읽었다 — "
        "재대입·동적 생성(tuple(...))으로 바뀌었을 수 있다. 추출기를 고쳐라(위반 아님)."
    )


def _table_keys() -> tuple[str, ...]:
    """RISK_LEVEL_TONE 리터럴 **블록 안**의 키만 센다.

    ★블록 경계로 자르지 않으면 파일 전체의 모든 `"키":` 줄을 세게 된다
    (2026-08-25 실측: 같은 실수로 11을 31로 보고했다).
    """
    # ★주석을 먼저 걷는다. 종전엔 원문을 그대로 봐서 `/* … */` 안으로 등급 행을
    #   옮기는 변이가 **생존**했다(적대 리뷰 M-E · 2026-08-27). `_code_lines` 를
    #   만들어 놓고 키 추출에는 안 쓴 것이 원인이다 — 도구가 있는데 안 쓴 자리.
    src = "\n".join(_code_lines())
    start = src.find("export const RISK_LEVEL_TONE")
    end = src.find("};", start) if start >= 0 else -1
    if start < 0 or end < 0:
        raise ScannerDeadError(
            f"{_PANEL.name} 에서 RISK_LEVEL_TONE 블록을 못 찾았다 — 선언이 바뀌었다(위반 아님)."
        )
    keys = tuple(_KEY.findall(src[start:end]))
    if not keys:
        raise ScannerDeadError("RISK_LEVEL_TONE 블록은 찾았는데 키가 0개다 — 키 정규식이 죽었다.")
    return keys


def test_extractors_are_alive() -> None:
    """★공허한 초록 방지 — 추출이 죽어서 '위반 0'이 되는 것과 진짜 0을 구별한다."""
    assert _SEVERITY_SSOT.is_file(), f"SSOT 부재: {_SEVERITY_SSOT}"
    assert _PANEL.is_file(), f"패널 부재: {_PANEL}"

    ladder = _ladder()
    keys = _table_keys()
    assert len(ladder) >= 4, f"사다리 추출 실패(={ladder}) — ast 파싱이 죽었다"
    assert len(keys) >= 4, f"표 키 추출 실패(={keys}) — 블록 경계 탐색이 죽었다"

    # 양성 대조군: 양쪽 모두 반드시 갖고 있어야 하는 값.
    assert "낮음" in ladder, "사다리에 '낮음'이 없다 — 추출기가 다른 것을 읽었다"
    assert "낮음" in keys, "표에 '낮음'이 없다 — 추출기가 다른 것을 읽었다"


def test_every_produced_severity_has_a_badge_color() -> None:
    """방향① **엄격** — 백엔드가 낼 수 있는 등급은 전부 표에 있어야 한다."""
    ladder = _ladder()
    keys = set(_table_keys())
    missing = [s for s in ladder if s not in keys]
    assert not missing, (
        f"리스크 사다리 {list(ladder)} 중 화면 배지 표에 없는 등급: {missing}. "
        "표에 없으면 폴백으로 흘러가 **실제 위험이 다른 색으로** 보인다. "
        f"{_PANEL.name} 의 RISK_LEVEL_TONE 에 추가하라."
    )


def test_badge_table_has_no_phantom_grade() -> None:
    """방향② **느슨** — 표에만 있고 사다리에 없는 유령 등급을 적발한다."""
    ladder = set(_ladder())
    phantom = [k for k in _table_keys() if k not in ladder]
    assert not phantom, (
        f"배지 표에만 있고 리스크 사다리에는 없는 등급: {phantom}. "
        "유령 항목은 표 자체를 신뢰할 수 없게 만든다(2026-08-24 실측: 7종 중 3종이 유령이었다)."
    )


def test_unknown_grade_does_not_fall_back_to_a_safe_color() -> None:
    """★미지 등급이 **안전색**으로 떨어지지 않는지 — 이 결함의 심장이다.

    표에 없는 등급의 폴백이 `RISK_LEVEL_TONE["낮음"]`(success 초록)이면,
    새 등급이 생기는 순간 그것이 **조용히 '안전'으로 분류**된다.
    """
    code = "\n".join(_code_lines())
    assert 'RISK_LEVEL_TONE["낮음"]' not in code, (
        "미지 등급의 폴백이 '낮음'(안전색)이다 — 모르는 값을 낮추지 마라. "
        "중립 스타일로 폴백하라(riskLevelStyle)."
    )
    assert "riskLevelStyle" in code, (
        "riskLevelStyle 헬퍼가 사라졌다 — 폴백 판정이 다시 인라인으로 흩어졌다."
    )


def test_the_badge_line_is_wired_to_the_helper() -> None:
    """★배선 — 헬퍼가 **있는 것**과 배지가 **그것을 태우는 것**은 다른 명제다.

    ★창을 **줄 수가 아니라 구조**로 잡는다. 종전엔 `lines[idx-3:idx+1]` 고정이라
    **공백 3줄만 넣어도 빨개졌다**(적대 리뷰 M-F — 위양성). Prettier 실행이나
    className 변수 추출 같은 **정상 리팩터가 필수 CI 를 거짓 메시지로** 빨갛게 만든다.
    이제 배지 텍스트가 든 JSX 요소의 **여는 태그까지 거슬러 올라가** 그 안을 본다.
    """
    lines = _code_lines(_CONSUMER)
    hits = [i for i, ln in enumerate(lines) if "종합 리스크 {" in ln]
    assert hits, (
        "배지 렌더 줄('종합 리스크 {…}')을 못 찾았다 — 조회기가 죽었거나 UI 가 바뀌었다. "
        "주석은 이미 제거된 상태이므로 이 0건은 주석 탓이 아니다."
    )
    assert len(hits) == 1, f"배지 렌더 줄이 {len(hits)}곳이다 — 창 판정이 모호해진다: {hits}"

    # 텍스트 줄에서 **여는 `<span`** 까지 거슬러 올라간다(공백·줄바꿈에 무관).
    idx = hits[0]
    open_at = None
    for k in range(idx, max(-1, idx - 60), -1):
        if "<span" in lines[k]:
            open_at = k
            break
    assert open_at is not None, (
        f"배지 텍스트({idx + 1}행) 위 60줄 안에서 여는 <span> 을 못 찾았다 — "
        "마크업이 크게 바뀌었다. 위반이 아니라 이 검사가 낡은 것일 수 있다."
    )
    element = "\n".join(lines[open_at : idx + 1])
    assert "riskLevelStyle(" in element, (
        "종합 리스크 배지 요소가 riskLevelStyle 을 태우지 않는다 — "
        "헬퍼는 있는데 배선이 끊겼다.\n"
        f"검사한 요소({open_at + 1}~{idx + 1}행):\n{element}"
    )


def test_each_grade_gets_a_distinct_tone() -> None:
    """★CRITICAL 락 — **두 등급이 같은 톤이면 화면에서 구별할 수 없다.**

    적대 리뷰(2026-08-27)가 `"중간"` 의 색을 초록으로 바꾸는 변이로 **락 14개를 전부
    통과**시켰다. 원인은 계약이 **색 문자열의 철자**로만 단언돼 있었던 것 —
    같은 초록을 다른 철자로 쓰면 전부 통과했다. 이제 표의 값이 **닫힌 톤 이름**이라
    같은 톤이면 여기서 죽는다.
    """
    src = "\n".join(_code_lines())
    start = src.find("export const RISK_LEVEL_TONE")
    end = src.find("};", start) if start >= 0 else -1
    if start < 0 or end < 0:
        raise ScannerDeadError("RISK_LEVEL_TONE 블록을 못 찾았다(위반 아님).")
    pairs = _KV.findall(src[start:end])
    if not pairs:
        raise ScannerDeadError("등급→톤 쌍을 하나도 못 읽었다 — 표기가 바뀌었다(위반 아님).")

    tones = [t for _g, t in pairs]
    dup = sorted({t for t in tones if tones.count(t) > 1})
    assert not dup, (
        f"두 등급 이상이 같은 톤을 쓴다: {dup} (표: {pairs}). "
        "사다리가 가른 등급을 화면이 못 가른다."
    )
    assert len(pairs) == len(_ladder()), (
        f"등급→톤 쌍 {len(pairs)}개 vs 사다리 {len(_ladder())}종 — 개수가 어긋난다."
    )


def test_tone_palette_has_no_duplicate_color() -> None:
    """★톤 이름이 달라도 **값이 같으면** 구별성은 여전히 0이다.

    위 테스트는 *"등급마다 다른 톤 이름"* 을 잠근다. 이 테스트는 그 톤 이름들이
    **실제로 다른 클래스 문자열**인지를 잠근다 — 둘을 나눠야 「이름만 다른 같은 색」이
    빠져나가지 못한다.
    """
    src = "\n".join(_code_lines())
    start = src.find("const RISK_TONE = {")
    end = src.find("} as const;", start) if start >= 0 else -1
    if start < 0 or end < 0:
        raise ScannerDeadError("RISK_TONE 팔레트를 못 찾았다(위반 아님).")
    body = src[start:end]
    values = re.findall(r'^\s*[a-z]+:\s*"([^"]+)"', body, re.M)
    if len(values) < 5:
        raise ScannerDeadError(f"톤 값을 {len(values)}개만 읽었다 — 표기가 바뀌었다(위반 아님).")
    dup = sorted({v for v in values if values.count(v) > 1})
    assert not dup, f"서로 다른 톤이 **같은 클래스 문자열**을 쓴다: {dup}"


@pytest.mark.parametrize("grade", ["중간"])
def test_regression_the_grade_that_was_missing(grade: str) -> None:
    """회귀 고정 — 이 결함을 만든 바로 그 등급.

    ★파생형(위 두 테스트)만 있으면 사다리와 표를 **동시에** 줄일 때 초록이 된다.
    이 앵커가 그 경로를 막는다.
    """
    assert grade in _ladder(), f"사다리에서 '{grade}' 가 사라졌다(제한보호구역 등급)"
    assert grade in _table_keys(), f"배지 표에서 '{grade}' 가 사라졌다"


# ─────────────────────────────────────────────────────────────────────────────
# ★우회로 락 (동료 세션 적대 검토 · 2026-08-27)
#
# 위 테스트들은 *"지금 사다리 5종이 표에 다 있다"* 만 잠근다. 그런데 **등급을 늘리는 경로가
# `SEVERITY_ORDER` 를 반드시 거치지 않는다** — `_ZONE_SEVERITY` 에 새 등급 문자열을 적으면
# 사다리를 안 건드리고도 그 값이 API 로 나간다. 그때 `severity_rank` 는 예외가 아니라
# **`-1` 을 조용히** 돌려주므로(실측: `except ValueError: return -1`) 아무도 안 깨진다.
# → 그러면 위 락의 **전제 자체가 거짓**이 된다. 여기서 그 전제를 잠근다.
# ─────────────────────────────────────────────────────────────────────────────


def _produced_severities() -> set[str]:
    """등급 **생산지**의 리터럴을 ast 로 전수한다(손으로 센 목록이 상한이 되지 않게)."""
    tree = ast.parse(_SEVERITY_SSOT.read_text(encoding="utf-8"))
    out: set[str] = set()

    # ① _ZONE_SEVERITY: ((키워드, 등급), ...) 의 두 번째 원소
    for node in ast.walk(tree):
        names = (
            [node.target]
            if isinstance(node, ast.AnnAssign)
            else getattr(node, "targets", [])
            if isinstance(node, ast.Assign)
            else []
        )
        for t in names:
            if isinstance(t, ast.Name) and t.id == "_ZONE_SEVERITY":
                if isinstance(node.value, ast.Tuple | ast.List):
                    for e in node.value.elts:
                        if isinstance(e, ast.Tuple) and len(e.elts) == 2:
                            v = e.elts[1]
                            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                                out.add(v.value)

    # ② _flight_safety_severity: 함수가 **직접 반환**하는 문자열 리터럴
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_flight_safety_severity":
            for r in ast.walk(node):
                if isinstance(r, ast.Return) and isinstance(r.value, ast.Constant):
                    if isinstance(r.value.value, str):
                        out.add(r.value.value)

    if not out:
        raise ScannerDeadError(
            "등급 생산지에서 리터럴을 하나도 못 읽었다 — _ZONE_SEVERITY 표기가 바뀌었다(위반 아님)."
        )
    return out


def test_every_grade_producer_stays_inside_the_ssot_ladder() -> None:
    """★우회로 — 등급을 만드는 모든 경로가 `SEVERITY_ORDER` 안이어야 한다.

    밖으로 나가면 `severity_rank` 가 **-1 을 조용히** 주고, 그 값이 화면 표에도 없어
    폴백으로 흘러간다. 즉 이 락이 깨지면 **표 파리티 락의 전제가 무너진다.**
    """
    ladder = set(_ladder())
    produced = _produced_severities()
    outside = sorted(produced - ladder)
    assert not outside, (
        f"사다리 밖 등급이 생산된다: {outside}. "
        "SEVERITY_ORDER 에 넣어 순위를 정의하라 — 넣지 않으면 severity_rank 가 -1 을 "
        "조용히 돌려주고 화면에서도 폴백으로 샌다."
    )


def test_ladder_has_no_dead_grade() -> None:
    """★양성 대조군 — 사다리에만 있고 **아무도 안 내는** 등급.

    현재 실측 **0**(2026-08-27). 0 이 아니게 되면 사다리에 죽은 등급이 생긴 것이고,
    그때는 위 테스트의 '부분집합' 통과가 **의미가 약해진다**(모집단이 갈라진다).
    """
    dead = sorted(set(_ladder()) - _produced_severities())
    assert not dead, (
        f"사다리에 있으나 아무 생산지도 내지 않는 등급: {dead}. "
        "죽은 등급이면 지우고, 다른 곳에서 낸다면 _produced_severities 의 축을 넓혀라."
    )


def test_sibling_surface_shares_the_same_judgment() -> None:
    """★전역 전파방지 — **같은 등급이 두 화면에서 다른 색이면 안 된다.**

    배너(`DominantConstraintBanner`)는 종전 자기 `switch` 로 5등급을 **3색**으로 접었다
    (`극히 높음`=`높음`=error · `중간`=`보통`=warning). 배지가 5색이 되는 순간
    **같은 필지가 두 화면에서 다른 색**이 된다(동료 통합자 지적 · 2026-08-27).

    이 저장소 규율은 *"공용 함수·표준 계약으로 추출해 한 곳을 고치면 전역이 따라오게"* 다.
    그래서 **판정을 공유하는지**를 잠근다 — 색 값이 아니라 **판정 함수 사용**을 본다
    (색은 이미 프론트 락이 축별로 구별성을 단언한다).
    """
    code = "\n".join(_code_lines(_BANNER))
    assert "riskLevelTextClass" in code, (
        "배너가 공용 판정(riskLevelTextClass)을 안 쓴다 — 로컬 판정으로 되돌아갔다면 "
        "같은 등급이 배지와 다른 색이 된다."
    )

    # ★**이름이 나오는 것**과 **로컬 판정이 없는 것**은 다른 명제다.
    #   처음엔 `'case "중간"' not in code` 로 잠갔는데, 삼항으로 되돌리는 변이가
    #   **생존**했다(`severity === "중간" ? … : …`) — `case` 라는 **표기 하나**만 봤기 때문이다.
    #   이 세션이 내내 적은 그 형태를, 그것을 막으려는 락에서 재현했다.
    #   → 표기가 아니라 **구조**로 잠근다: 배너는 등급 이름을 **아예 몰라야 한다.**
    leaked = [g for g in _ladder() if f'"{g}"' in code or f"'{g}'" in code]
    assert not leaked, (
        f"배너 실행 코드에 등급 리터럴이 있다: {leaked}. "
        "배너는 등급 이름을 몰라야 한다 — 판정은 lib/risk-level-style 한 곳이다. "
        "(switch·삼항·객체표 어느 표기든 여기서 걸린다)"
    )
