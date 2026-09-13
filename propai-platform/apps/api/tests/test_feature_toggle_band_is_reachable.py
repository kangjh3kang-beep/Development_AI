"""`feature_toggle` 후보 밴드가 **생산처로부터 도달 가능한가** — 상수·소스에서 파생.

## 왜 이 파일이 생겼나 (2026-09-13)

`effector_firing.py` 의 표가 `feature_toggle` 의 0건을 **★진짜 발견**이라 적으면서
그 이유를 이렇게 설명했다:

> `down_pct >= 40` 이 필요한데 `analyzer._classify_quality` 는 20% 위에서만 `quality_drop` 을 낸다

★**결론(「조건 미충족」)은 맞고 근거가 틀렸다.** `> 20` 은 `>= 40` 을 **포함**한다 —
`down_pct=45` 는 20 도 넘으므로 발행되고 소비처도 통과한다. 경로는 **도달 가능**하다.
0건의 진짜 이유는 «그런 서비스가 없었다»는 **데이터 조건**이다.

★★**왜 이 오진이 위험한가**: 그 문장을 읽은 사람은 *"두 임계가 어긋났으니 맞추자"* 로 가고,
맞추는 방향은 `FEATURE_DISABLE_ERROR_PCT` **40 → 20** 이다. 그러면 `llm_narrative` 가
**절반의 down 비율에서 자동 비활성**된다 — ***없는 모순을 고치려고 프로덕션 안전 임계를 푼다.***
(CLAUDE.md: *"가장 먼저 떠오른 길이 지표를 느슨하게 하는 것이었다"*.)

## 이 락이 잠그는 것 — 산문이 아니라 **계약**

주석은 고쳐도 또 낡는다. 그래서 그 표가 *가리키려던* 진짜 취약점을 잠근다:

**생산처가 실제로 내는 severity ⊆ 소비처가 받는 severity.**
`_classify_quality` 는 `"warn"` **하나만** 낸다(critical 분기가 없다 — 형제
`error_cluster`·`fallback_rate` 와 다르다). 소비처를 `severity='critical'` 로 좁히면
**이 효과기는 조용히 도달 불가**가 된다. 그것이 진짜 «구조적 도달 불가»이고, 지금은 아니다.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.services.growth import analyzer as A
from app.services.growth import feature_flags as FF

_CONSUMER_SRC = Path(inspect.getfile(FF)).read_text(encoding="utf-8")


def _sql_literals() -> list[str]:
    """소비처가 **실제로 실행하는** SQL 문자열만 모은다 — `text(...)` 의 인자.

    ★종전 판은 *"실행되는 문자열 상수"* 라 적고 **독스트링만** 걸렀다. 그건 **거짓 면역
      주장**이었다(CLAUDE.md §C-11): 죽은 모듈 상수나 실행 경로 밖의 맨 문자열에
      `quality_drop` 이 들어 있으면 **그것을 소비처 질의로 집었다**(독립 리뷰 실측 —
      미끼를 죽은 상수·함수 중간 문자열에 넣은 두 경우 **SURVIVED**).
    ⇒ 이제 **`text()` 호출의 인자**만 본다. 인접 문자열 리터럴은 파서가 이미 하나로
      합치므로 여러 줄 SQL 도 단일 `Constant` 로 잡힌다.
    """
    return [
        n.args[0].value
        for n in ast.walk(ast.parse(_CONSUMER_SRC))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "text"
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and isinstance(n.args[0].value, str)
    ]


def _gate_sql() -> str:
    """소비 게이트 질의 **하나**를 특정한다 — 두 락이 **같은 축**을 쓴다(R3 MEDIUM-A).

    ★종전엔 `test_consumer_…` 는 `len==1` 로 특정하고 `test_producer_…` 는 **합집합**이라,
      같은 파일 안에서 같은 문제를 두 방식으로 풀고 있었다.
    """
    gate = [s for s in _sql_literals() if "quality_drop" in s and "status='open'" in s]
    assert len(gate) == 1, (
        f"게이트 질의를 유일하게 특정하지 못했다({len(gate)}건) — 질의가 늘었으면 이 락의 축을 다시 정해야 한다"
    )
    return gate[0]


def _producible_severities() -> set[str]:
    """`_classify_quality` 를 **실제로 태워서** 낼 수 있는 severity 를 모은다.

    ★소스를 읽지 않는다 — 함수를 부르므로 분기 변경이 반영된다.
    ★★**한계는 「표본」이 아니라 「구조」다**(R2 MAJOR-C 정정).
      종전엔 *"15점 표본이라 `>`→`>=` 를 못 잡는다"* 고 적었다. **그 진단이 틀렸다** —
      *"더 촘촘히 하면 된다"* 는 **틀린 처방**을 지시한다.
      실제 이유: **`_classify_quality` 함수 안에서** severity 대입은 `severity = "warn"` **한 곳뿐**이다.
      ★★R3 정정: 종전엔 *"`analyzer.py` 에서 한 곳뿐"* 이라 **모듈 범위로 넓게** 적었는데 **거짓**이다 —
        모듈에는 severity/sev 대입이 **8곳**이고 그중 `:1005` 는 `'critical'` 을 낸다.
        **결론은 옳고 범위가 틀렸다**(R1 「표본 오진」을 고치며 새 전제를 또 한 칸 넓게 적었다).
      그러므로 `_classify_quality` **술어 안의 어떤 변이도** 생산 가능 집합을
      `⊆ {"warn"}` 밖으로 내보낼 수 없다 — **표본을 무한히 늘려도 원리적으로 못 잡는다.**
    ⇒ 이 헬퍼가 잠그는 것은 **「생산 집합이 소비 집합에 담기는가」** 하나다.
      술어(`>` ↔ `>=`, `or` ↔ `and`)는 **이 락의 축이 아니다** — 그 축은 형제
      `test_growth_analysis_coverage.py` · `test_growth_reason_reaches_surface.py` 가 잡는다
      (R2 실측: 파생 10파일로 넓혀야 CAUGHT 이고, **잡는 것은 그 형제들**이다).
    ★***「이 헬퍼가 잡는다」고 읽히게 적지 않는다*** — 그게 이 PR 이 고치러 온 결함이다.
    """
    out: set[str] = set()
    floor = A.QUALITY_MIN_SAMPLES
    for down_pct_target in (0, 25, 50, 75, 100):
        ftotal = max(floor, 20)
        down = round(ftotal * down_pct_target / 100)
        for vtotal, fail in ((0, 0), (max(floor, 20), 0), (max(floor, 20), max(floor, 20))):
            sev, _m = A._classify_quality(fail, 0, vtotal, down, ftotal)
            if sev is not None:
                out.add(sev)
    return out


def test_consumer_accepts_every_severity_the_producer_can_emit() -> None:
    """★핵심 계약: 생산처가 내는 severity 를 소비처가 **전부** 받는가."""
    produced = _producible_severities()
    assert produced, "생산처가 아무 severity 도 못 냈다 — 수집기가 죽었다(공허한 참 방지)"

    # ★게이트 질의 **하나만** 고른다 — 합집합을 쓰면 같은 함수의 **두 번째 `text()`** 가
    #   판정을 뭉갠다(R2 MEDIUM-A 실측: 살아 있는 미끼 질의를 한 줄 더하면 SURVIVED).
    #   게이트는 `quality_drop` + `status='open'` 을 **함께** 담은 리터럴이다.
    quality_sql = [_gate_sql()]
    # ★하드코딩 후보 목록을 쓰지 않는다 — `severity IN (...)` 절에서 **파생**한다.
    #   목록을 쓰면 새 severity 어휘가 조용히 통과한다(독립 리뷰 MINOR).
    accepted: set[str] = set()
    for s in quality_sql:
        for clause in re.findall(r"severity\s+IN\s*\(([^)]*)\)", s, re.I):
            accepted |= set(re.findall(r"'([^']+)'", clause))
    assert accepted, f"소비처가 받는 severity 집합을 못 뽑았다: {quality_sql}"

    missing = produced - accepted
    assert not missing, (
        f"★생산처가 내는 severity {sorted(missing)} 를 소비처가 거부한다 — "
        f"feature_toggle 이 **구조적으로 도달 불가**가 된다. "
        f"생산={sorted(produced)} 소비={sorted(accepted)}"
    )


def _emitted_insight_types() -> tuple[set[str], set[str]]:
    """생산처가 발행하는 `insight_type` 을 AST 로 파생한다 → `(확정, 판정불가)`.

    ★R3 MAJOR-2: 종전 판은 **`Constant` 값만** 모아서, 값이 **`Call`** 인 발행
      (`analyzer.py` 의 `"insight_type": insight_type_for_latency(sev)`)을 **못 봤다.**
      그래서 파생 집합에 `latency_regression`·`latency_baseline` 이 **빠졌는데**,
      라이브에는 그 둘이 **438건·49건(최신 0.0h·5.6h)로 활발히 생산 중**이다.
      ⇒ 그 상태에서 소비 게이트가 그 타입을 조회하면 이 락은
      *"생산처가 **발행하지 않는다** · 영원히 0행"* 이라는 **거짓 메시지**를 냈을 것이다.
      ***이 PR 이 고치러 온 결함(거짓 근거)을 락의 실패 메시지가 재생산한다.***
    ⇒ 그래서 **「발행 안 함」과 「내 수집기가 못 봄」을 가른다.** 후자는 **판정 불가**다.
    """
    src = Path(inspect.getfile(A)).read_text(encoding="utf-8")
    known: set[str] = set()
    undecidable: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values, strict=False):
            if not (isinstance(k, ast.Constant) and k.value == "insight_type"):
                continue
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                known.add(v.value)
            else:                      # Call · Name · f-string … → 파생 불가
                undecidable.add(ast.unparse(v))
    return known, undecidable


def _producer_functions_with_live_call_sites() -> set[str]:
    """`_analyze_*` 중 **실제로 호출되는** 것만 — 존재가 아니라 **배선**을 본다.

    ★R3 MAJOR-1: 종전 락은 emit dict 리터럴이 **소스에 있는가**만 봤다. 그래서
      `run_analysis` 의 `insights.extend(await _analyze_quality_drop(...))` **호출부를 지워도**
      리터럴이 남아 초록이었다(실측 `::VERDICT=SURVIVED`) — 그러면 그 타입은
      **영원히 한 행도 생산되지 않는데**, 그것이 바로 이 락이 막겠다고 적은 상태다.
    """
    src = Path(inspect.getfile(A)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    called: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id.startswith("_analyze_"):
            called.add(n.func.id)
    return called


def _producer_of(itype: str) -> str | None:
    """그 `insight_type` 을 발행하는 `_analyze_*` 함수 이름(AST 파생)."""
    src = Path(inspect.getfile(A)).read_text(encoding="utf-8")
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        if not fn.name.startswith("_analyze_"):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values, strict=False):
                    if (isinstance(k, ast.Constant) and k.value == "insight_type"
                            and isinstance(v, ast.Constant) and v.value == itype):
                        return fn.name
    return None


def test_producer_emits_the_insight_type_the_consumer_queries() -> None:
    """★게이트가 조회하는 타입에 **살아 있는 생산 배선**이 있는가.

    ★잠그는 것: ①그 타입을 발행하는 `_analyze_*` 가 존재하고 ②그것이 **실제로 호출된다**.
    ★**잠그지 않는 것**(정직 표기): 게이트를 **다른, 그러나 생산되는 타입**으로 바꿔치기하는 것은
      못 잡는다(R3 MEDIUM-B 실측 — `quality_drop`→`error_cluster` 변이는 이 락을 통과한다).
      그건 «배선이 끊겼나»가 아니라 «의미가 맞나»라 기계 판정 밖이다.
      ⇒ 계획서 §5 의 *"문자열 **동일성**"* 표기는 과대였다. 실제는 **일방 포함 + 배선**이다.
    """
    known, undecidable = _emitted_insight_types()
    assert known, "발행 dict 에서 insight_type 을 하나도 못 뽑았다(수집기 사망)"

    gate = _gate_sql()
    queried = {m for m in re.findall(r"insight_type\s*=\s*'([^']+)'", gate)}
    assert queried, f"게이트에서 insight_type 값을 못 뽑았다: {gate!r}"

    for itype in sorted(queried):
        if itype not in known:
            # ★「발행 안 함」과 「수집기가 못 봄」을 가른다 — 후자는 단정하지 않는다.
            assert not undecidable, (
                f"★판정 불가 — 게이트가 조회하는 {itype!r} 가 상수 발행 목록에 없고, "
                f"소스에 **파생 불가한 발행식**이 있다({sorted(undecidable)}). "
                f"「발행하지 않는다」고 단정하지 않는다."
            )
            raise AssertionError(
                f"★게이트가 조회하는 {itype!r} 를 생산처가 발행하지 않는다 — 그 질의는 영원히 0행이다. "
                f"발행={sorted(known)}"
            )
        fn = _producer_of(itype)
        assert fn, f"{itype!r} 의 생산 함수를 특정하지 못했다(수집기 사망)"
        assert fn in _producer_functions_with_live_call_sites(), (
            f"★{itype!r} 의 생산자 {fn!r} 가 **어디서도 호출되지 않는다** — "
            f"발행 리터럴은 남아 있지만 한 행도 생산되지 않는다. 게이트는 영원히 0행이다."
        )


def test_the_candidate_window_is_pinned_against_loosening() -> None:
    """★게이트의 **결정적 축**(`timedelta(hours=N)`)을 느슨해지는 방향으로 못 늘리게 한다.

    ★왜 이 축인가(같은 커밋의 라이브 실측): 네 술어 중 **이 축 하나가 4/4 를 떨어뜨린다**
      (행 나이 461~479시간). 나머지 셋은 형제가 상수로 핀하는데(`FEATURE_DISABLE_ERROR_PCT`·
      `FEATURE_MIN_SAMPLES`) **이 축만 이름 없는 인라인 리터럴이라 아무도 안 잠갔다.**
      실측(R3): `hours=6` → `hours=600` 변이가 **SURVIVED**. 600시간이면 **19~20일 된 인사이트**가
      자동 피처 비활성 후보에 들어온다 — CLAUDE.md 가 이름 붙인
      ***«가장 먼저 떠오르는 길 = 지표를 느슨하게 하기»*** 그 자체다.
    ★런타임을 바꾸지 않으려고 **상수 추출 대신 AST 로 리터럴을 핀**한다(이 PR 은 런타임 0줄을 유지한다).
    """
    src = Path(inspect.getfile(FF)).read_text(encoding="utf-8")
    found: list[int] = []
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "timedelta"):
            for kw in node.keywords:
                if kw.arg == "hours" and isinstance(kw.value, ast.Constant):
                    found.append(kw.value.value)
    assert found, "timedelta(hours=…) 를 하나도 못 찾았다(조회기 사망)"
    assert max(found) <= 6, (
        f"★후보 창이 느슨해졌다: hours={sorted(found)} — 창을 늘리면 **낡은 인사이트**가 "
        f"자동 피처 비활성 후보가 된다. 늘려야 할 근거가 생기면 **이 단언을 함께 고치고 "
        f"그 근거를 여기 적어라**(그게 요점이다)."
    )


@pytest.mark.xfail(strict=True, reason=(
    "★부채(미잠금) — `effector_firing.py` 표의 **산문 근거**가 코드와 어긋나도 "
    "기계가 잡지 못한다. 위 락들은 **계약**을 잠그지만 표의 설명문은 자연어라 "
    "판정이 의미 층위에 있다. 표를 고쳐도 다음 사람이 새 근거를 잘못 적는 것은 막지 못한다."
))
def test_prose_rationale_in_effector_firing_is_machine_checked() -> None:
    raise AssertionError("산문 근거를 기계로 검증하는 장치가 없다")
