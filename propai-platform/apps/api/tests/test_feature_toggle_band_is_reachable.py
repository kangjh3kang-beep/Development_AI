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


def _producible_severities() -> set[str]:
    """`_classify_quality` 를 **실제로 태워서** 낼 수 있는 severity 를 모은다.

    ★소스를 읽지 않는다 — 함수를 부르므로 분기 변경이 반영된다.
    ★★**전수가 아니라 15점 표본이다**(독립 리뷰 지적). `warn=0` 을 고정했고
      `fail ∈ {0, vtotal}` 만 본다. 실측: `analyzer.py` 의 `or`→`and` 는 CAUGHT 이지만
      **`>`→`>=` 는 SURVIVED** 다. ⇒ 이 헬퍼는 «생산 가능 집합의 하한»을 주지
      «분기 전수»를 주지 않는다. **그 한계를 여기 적어 둔다**(면역을 거짓 주장하지 않는다).
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

    quality_sql = [s for s in _sql_literals() if "quality_drop" in s]
    assert quality_sql, "소비처에서 quality_drop 질의를 못 찾았다(조회기 사망)"
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


def test_producer_emits_the_insight_type_the_consumer_queries() -> None:
    """생산처가 만드는 `insight_type` 과 소비처가 조회하는 문자열이 같은가(오타 잠금)."""
    a_src = Path(inspect.getfile(A)).read_text(encoding="utf-8")
    emitted = [
        n.value for n in ast.walk(ast.parse(a_src))
        if isinstance(n, ast.Constant) and n.value == "quality_drop"
    ]
    assert emitted, "analyzer 가 quality_drop 을 발행하지 않는다 — 소비처 질의가 영원히 빈다"
    assert any("quality_drop" in s for s in _sql_literals()), \
        "소비처가 quality_drop 을 조회하지 않는다"


@pytest.mark.xfail(strict=True, reason=(
    "★부채(미잠금) — `effector_firing.py` 표의 **산문 근거**가 코드와 어긋나도 "
    "기계가 잡지 못한다. 위 셋은 **계약**을 잠그지만 표의 설명문은 자연어라 "
    "판정이 의미 층위에 있다. 표를 고쳐도 다음 사람이 새 근거를 잘못 적는 것은 막지 못한다."
))
def test_prose_rationale_in_effector_firing_is_machine_checked() -> None:
    raise AssertionError("산문 근거를 기계로 검증하는 장치가 없다")
