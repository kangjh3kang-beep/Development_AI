"""심의 CI 가 **필수로 등록 가능한 구조**인지 잠근다.

## 왜 (실측 2026-09-04)

브랜치보호 `required_status_checks` 는 **4종**뿐이고 `Deliberation Engine (pytest)` 는 **없다**.
즉 그 검사가 **빨간 채로도 머지가 막히지 않는다.**

그런데 **그냥 required 에 넣을 수 없다** — 워크플로 레벨 `pull_request: paths` 스킵과
required 가 만나면 **문서 전용 PR 이 `Expected` 영구대기로 차단**된다(`ci.yml` 이 `#423` 에서
겪고 남긴 기록). 그래서 **먼저 구조를 바꾸고**(`changes` 잡 + 잡 레벨 `if`) 그 다음에 등록한다.

★**이 파일은 그 「먼저」만 잠근다.** 등록 자체는 저장소 설정이라 코드로 못 잠근다 —
그 부채를 아래 `xfail` 로 **초록 안에 보이게** 남긴다(커밋 메시지에만 적으면 안 드러난다).

## ★근거의 출처

`#423 path-aware CI` 가 주 CI 에 같은 전환을 했고, 그때 심의는 **self-trigger 만** 받고
이 전환에서 빠졌다. 같은 기록에 **실해 증거**도 있다 —
*"타 세션에서 `#425` 가 CI FAIL 채로 머지된 실사고 발생 — 보호 있었으면 구조적 불가"*.
"""

from __future__ import annotations

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


@pytest.mark.xfail(
    reason=(
        "★부채 — `Deliberation Engine (pytest)` 가 브랜치보호 required_status_checks 에 "
        "**아직 없다**. 그 등록은 저장소 설정 변경이라 코드로 잠글 수 없다. "
        "이 구조 전환이 그 등록의 **전제**이고, 등록 전까지 이 검사는 머지를 막지 못한다. "
        "`#423` 도 같은 자리에서 사용자 실행 대기로 남겼고 그 뒤 필수 4종이 등록됐다 — "
        "작동한 전례가 있는 경로다. 등록되면 이 xfail 이 XPASS 로 뒤집혀 부채 해소를 알린다.",
    ),
    strict=True,
)
def test_심의검사가_필수로_등록돼_있다():
    """★**부채를 초록 안에 보이게** 남긴다 — 커밋 메시지에만 적으면 드러나지 않는다.

    등록되면 이 테스트가 XPASS 가 되어 `strict=True` 로 **실패**한다 →
    다음 사람이 이 `xfail` 을 지우면 된다(부채가 조용히 남지 않는다).
    """
    # 네트워크·토큰 없이 판정할 수 없으므로 **현재 상태를 사실대로** 적는다.
    # 2026-09-04 실측: gh api .../branches/main/protection 의 contexts 4종에 없음.
    registered = False
    assert registered, "브랜치보호에 등록되면 이 줄을 지우고 xfail 도 지운다"
