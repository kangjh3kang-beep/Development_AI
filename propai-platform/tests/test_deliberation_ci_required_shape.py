"""심의 CI 가 **필수로 등록 가능한 구조**인지, 그리고 **등록이 살아 있는지** 잠근다.

## 왜 (실측 2026-09-04 → 갱신 2026-09-05)

그냥 required 에 넣을 수 없었다 — 워크플로 레벨 `pull_request: paths` 스킵과 required 가
만나면 **문서 전용 PR 이 `Expected` 영구대기로 차단**된다(`ci.yml` 이 `#423` 에서 겪고 남긴
기록). 그래서 **먼저 구조를 바꾸고**(`changes` 잡 + 잡 레벨 `if`) 그 다음에 등록했다.

★**등록은 2026-09-05 에 완료됐다**(`PATCH` · 기존 4종 동봉 · 소실 0). 그리고 같은 날
`#986`·`#990` 이 이 검사가 **`skipping` 인 채로** 머지돼, *"GitHub 이 잡레벨 skip 을
required 충족으로 계수한다"* 는 전제가 **이 저장소에서 처음 실측**됐다.

★**휘발성이라 값을 적지 않는다** — 현재 목록은 재서 확인한다:

    gh api repos/kangjh3kang-beep/Development_AI/branches/main/protection \
      --jq '.required_status_checks.contexts[]'

## ★이 파일이 겪은 결함 — 부채 표지가 **자기 상수**였다

이 자리에는 `xfail(strict=True)` + `registered = False` 가 있었고, 계획서는
*"등록되면 XPASS 로 뒤집혀 부채 해소를 알린다"* 고 선언했다. **상수는 현실을 보지 않는다** —
등록이 끝난 뒤에도 XFAIL 인 채 *"아직 없다"* 는 **거짓을 초록 안에서** 말했다.

★★**그런데 선언대로 작동했다면 더 나빴다.** 이 파일은 필수 체크 `Backend (pytest)` 가
태우는 층이라, XPASS(=실패)가 되는 순간 **저장소 전역이 빨개지고 그 xfail 을 지우는 PR
자신이 막히는 교착**이 난다. → **부채 표지를 「필수 체크가 태우는 층」에 두지 마라.**

그래서 지금은 **상수가 아니라 실제 조회**로 판정하고, **못 재면 판정을 거부**한다(`skip`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deliberation-ci.yml"
_MAIN_WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

# 브랜치보호에 등록돼야 하는 잡 이름(`gh pr checks` 에 뜨는 그 이름).
REQUIRED_JOB_NAME = "Deliberation Engine (pytest)"


def _load(path: Path) -> dict:
    assert path.exists(), f"워크플로가 없다(경로가 바뀌었나): {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    """`on:` 을 꺼낸다 — PyYAML 이 `on` 을 **불리언 True 로 파싱**한다."""
    return doc.get("on") or doc.get(True) or {}


class Test수집기가살아있다:
    """★단언 **앞에** 생존을 증명한다 — 파일이 안 읽히면 아래는 전부 공허하다."""

    def test_두_워크플로가_읽힌다(self):
        for p in (_WF, _MAIN_WF):
            doc = _load(p)
            assert doc.get("jobs"), f"잡이 없다: {p.name}"

    def test_정본_패턴이_주_CI_에_실재한다(self):
        """★양성 대조군 — 내가 복사한 패턴이 이 저장소에 **실제로 있는** 것인지."""
        main = _load(_MAIN_WF)
        assert "changes" in main["jobs"], "주 CI 에 changes 잡이 없다 — 근거가 사라졌다"
        assert "paths" not in (_triggers(main).get("pull_request") or {}), (
            "주 CI 의 pull_request 에 paths 가 생겼다 — 내가 인용한 근거가 낡았다"
        )


class Test필수등록가능한구조다:
    def test_pull_request_에_paths_필터가_없다(self):
        """★이것이 있으면 required 등록 시 문서 PR 이 `Expected` 로 영구대기한다."""
        pr = _triggers(_load(_WF)).get("pull_request")
        assert not (pr or {}).get("paths"), (
            "pull_request 에 paths 가 있다 — 경로 판별은 잡 레벨 if 로 옮겨야 한다"
        )

    def test_경로판별이_잡레벨_if_로_옮겨졌다(self):
        jobs = _load(_WF)["jobs"]
        assert "changes" in jobs, "changes 잡이 없다"
        eng = next(j for j in jobs.values() if j.get("name") == REQUIRED_JOB_NAME)
        assert eng.get("needs") == "changes" or "changes" in (eng.get("needs") or [])
        assert "if" in eng and "changes.outputs" in str(eng["if"]), (
            f"엔진 잡에 잡 레벨 if 가 없다: {eng.get('if')!r}"
        )

    def test_판별잡이_fail_safe_다(self):
        """★**fail-open 이면 이 전환이 오히려 위험하다.**

        판별 잡이 실패했을 때 하위 잡이 skip 되면 GitHub 이 그것을 **required 충족**으로
        계수해 **무검증 머지**가 된다. `#423` R1 이 실제로 그 결함을 냈다.
        """
        run = _load(_WF)["jobs"]["changes"]["steps"][0]["run"]
        # 실패 경로마다 `engine=true`(전체 실행)로 귀결해야 한다.
        assert run.count("engine=true") >= 3, (
            "실패 경로가 전체 실행으로 귀결하지 않는다 — fail-open 은 무검증 머지를 만든다:\n" + run
        )
        assert "API 실패" in run, "API 실패 분기가 없다"

    def test_push_트리거는_paths_를_유지한다(self):
        """★음성 대조군 — 「전부 지우는」 변경과 구별한다.

        push 에는 required-check 함정이 없다. main 에서 불필요한 실행을 늘리지 않는다.
        """
        push = _triggers(_load(_WF)).get("push") or {}
        assert push.get("paths"), "push 의 paths 까지 지우면 main 에서 매번 돈다"


def _live_required_contexts() -> list[str] | None:
    """브랜치보호의 `required_status_checks.contexts` 를 **실측**한다.

    ★**못 재면 `None` 을 돌려준다 — 상수로 대체하지 않는다.**
    이 자리에 있던 `registered = False` 가 정확히 그 실수였다: 등록이 끝난 뒤에도
    상수는 뒤집히지 않아 **초록 안에서 «아직 없다»는 거짓**을 말했다(2026-09-05 실측).
    """
    # ★변이 기록(2026-09-05): 이 함수를 «항상 None» 으로 바꾸면 변이가 **SURVIVED** 한다.
    #   그것은 구멍이 아니라 **설계**다 — 「판정 불가」는 실패가 아니기 때문이다.
    #   ★정정(적대 리뷰 실측): 오프라인 이름 락은 이 함수를 **호출조차 하지 않으므로**
    #   그 변이와 **무관**하다(CAUGHT 가 아니다 — 처음엔 CAUGHT 라고 잘못 적었다).
    #   그 변이를 실제로 잡는 것은 아래 `test_조회불가일때_판정을_거부한다` 가 아니라,
    #   ★**상수 폴백 재유입**을 잡는 그 행위 락이다(다른 사건을 잡는다).
    import json
    import subprocess

    try:
        out = subprocess.run(
            [
                "gh", "api",
                "repos/kangjh3kang-beep/Development_AI/branches/main/protection",
                "--jq", ".required_status_checks.contexts // []",
            ],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        parsed = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def test_심의검사가_필수로_등록돼_있다():
    """★이 API 는 **치환**이다 — 기존 컨텍스트를 함께 보내지 않는 `PATCH` 한 번이면
    이 보호가 **조용히 사라진다.** 그 사건을 잡는 것이 이 락의 존재 이유다.

    ★**`xfail(strict=True)` 를 쓰지 않는다.** 이 파일은 필수 체크 `Backend (pytest)` 가
    태우는 층이라, XPASS 를 실패로 보고하면 등록되는 순간 **저장소 전역이 한 사이클 빨개진다**.
    ★**정정(2026-09-05 실측)**: 볼트는 이것을 *"그 xfail 을 지우는 PR 자신이 막히는 **교착**"*
    이라 적었고 나는 그것을 **재지 않고 승계**했다 — **거짓이다.** PR 체크는
    `refs/remotes/pull/N/merge` 에서 돌아 **고치는 PR 자신은 초록**이다(`#990` 잡 로그로 확인).
    실제 대가는 «다른 in-flight PR 이 한 사이클 빨감»이고 **자기 손으로 풀린다.**
    """
    contexts = _live_required_contexts()
    if contexts is None:
        pytest.skip(
            "★판정 불가 — 조회 결과를 리스트로 확정하지 못했다(rc·형태 미상). "
            "★원인을 열거하지 않는다: 참인 원인과 거짓인 원인이 같은 모양이 된다. "
            "★이 자리를 상수로 메우지 마라 — 그러면 낡는 순간 초록 안에서 거짓을 말한다."
        )
    assert REQUIRED_JOB_NAME in contexts, (
        f"필수 체크에서 {REQUIRED_JOB_NAME!r} 가 사라졌다 — 이 API 는 치환이라 "
        f"기존 컨텍스트를 빠뜨린 PATCH 한 번이면 이렇게 된다. 현재: {contexts!r}"
    )


def test_워크플로_잡이름이_등록된_컨텍스트와_같다():
    """워크플로가 보호규칙이 기다리는 이름의 잡을 **생산하는지** 본다.

    ★**이 락이 무엇을 더하지 않는지 먼저 적는다**(적대 리뷰 실측 2026-09-05):
    잡 이름만 바꾸는 변이는 위 `test_경로판별이_잡레벨_if_로_옮겨졌다`(`:83`)가
    **이미 잡는다** — 이 락은 그 **진부분집합**이라 게이트 탐지 증분이 **0** 이다.
    남는 값어치는 하나뿐이다: `:83` 이 나중에 **키 기준 조회로 리팩토링**되면
    그때부터 이 락만이 이름을 본다.

    ★**공동 개명은 오프라인에서 못 잡는다** — 잡 이름과 `REQUIRED_JOB_NAME` 을 **함께**
    바꾸면 두 오프라인 락 모두 통과한다. 그것을 잡는 것은 라이브 조회뿐인데 그것은
    CI 에서 skip 된다(실측: 루트 스위트 `1172/31/4` → `1173/32/3`). **★게이트 부채다.**

    ★기대값을 워크플로에서 파생시키지 **않는다** — 자기참조면 이름을 바꿔도 통과한다.
    ★공허 방지 단언은 두지 않는다: `X in []` 은 항상 False 라 멤버십 단언은
    **원리적으로 공허할 수 없다**(도달 불가 방어는 변이 점수만 부풀린다).
    """
    jobs = _load(_WF)["jobs"]
    names = [j.get("name") for j in jobs.values()]
    assert REQUIRED_JOB_NAME in names, (
        f"워크플로가 {REQUIRED_JOB_NAME!r} 라는 이름의 잡을 만들지 않는다. "
        f"브랜치보호는 그 이름으로 체크를 기다리므로 **모든 PR 이 Expected 로 막힌다**. "
        f"현재 잡 이름: {names!r}"
    )


def test_조회불가일때_판정을_거부한다(monkeypatch):
    """★**금지한 상수 폴백이 다시 들어오는 것을 잡는다 — 산문이 아니라 행위로.**

    적대 리뷰가 실증했다: 위 독스트링이 *"상수로 대체하지 않는다"* 고 **말만** 하고
    있어서, `_live_required_contexts() or [REQUIRED_JOB_NAME]` 한 줄을 넣으면
    **8/8 초록**이었다 — `registered = False` 와 **정확히 같은 결함의 복원**이다.

    그래서 «못 잴 때는 **판정을 거부한다**»를 **행위로** 못 박는다:
    조회가 `None` 이면 그 테스트는 **통과가 아니라 `skip`** 이어야 한다.
    """
    monkeypatch.setattr(
        sys.modules[__name__], "_live_required_contexts", lambda: None
    )
    with pytest.raises(pytest.skip.Exception):
        test_심의검사가_필수로_등록돼_있다()
