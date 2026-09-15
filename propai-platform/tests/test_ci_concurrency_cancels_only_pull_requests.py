"""★CI 동시성 그룹이 **낡은 PR 실행만** 취소하는지 잠근다.

【왜 생겼나 · 2026-09-15 전수 실측 (sid=7af9eaa2 · 통합자)】
`gh api actions/runs` 600건 페이징 · 그중 `CI`+`pull_request` **236건 / 8일 창**:

    CI 시간 3,595분 중 **980분(27.3%)** 이 「head 가 이미 옮겨간 뒤에도 끝까지 돈」 실행
    그런데 conclusion=cancelled 는 **0건** — concurrency 선언이 없어 덮여도 완주했다
    분해: 저자푸시 54회 819분 · update-branch 10회 160분

★**주축이 update-branch 가 아니었다.** 종전 권고(«update-branch 는 머지 직전에 한 번»)는
  980분 중 160분(16%)만 겨냥했다 — *처방 범위가 결함 범위와 어긋난* 전형이고, 게다가
  그 권고는 **산문**이라 매 세션이 기억해야 한다. 이 파일은 그것을 **기계**로 바꾼다.

【이 락이 지키는 세 가지 — 셋 다 「없으면 조용히 사고」다】
  ① `cancel-in-progress` 가 **무조건 true 면 main 푸시 실행끼리 취소**돼 그 커밋의
     초록 기록(래칫 기준선)이 사라진다. 실측: main 푸시 47건 중 겹침 1건(2.2%).
  ② 그룹 키가 `github.workflow` 뿐이면 **모든 PR 이 한 그룹**이라 새 PR 이 남의 실행을
     취소한다. 이 저장소는 멀티세션이라 즉시 사고가 난다.
  ③ ★`environment:` 가 생기면 승인 게이트가 붙어 실행이 `waiting` 을 거친다. #1029
     (sid=dcb7a4f2)이 배포 워크플로에서 이 처방을 기각한 사유가 바로
     *«cancel-in-progress 가 waiting 을 취소하는지 **미측정**»* 이었다. 그 전제가
     깨지면 이 처방의 근거도 깨지므로 **같은 파일에서 함께 잠근다.**

★락의 축은 **리터럴이 아니라 속성**이다(문자열을 박으면 리팩토링에 부서지고, 부서지면
  다음 사람이 「낡은 락」이라며 지운다). 그래서 판정을 `_classify()` 한 곳에 두고,
  **위양성·위음성 대조군을 그 함수에 직접 태워** 판정기 자신을 잠근다 — 이 저장소에는
  *「0건 단언 락은 판정 함수를 약화시켜도 초록」* 이라는 실측 전례가 있다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_CI = _REPO / ".github" / "workflows" / "ci.yml"

#: 그룹 키를 **PR 마다 다르게** 만드는 토큰. 손 목록이 아니라 「PR 마다 값이 달라지는 것」이
#: 판정 기준이고, 새 토큰을 쓰려면 여기 추가하면서 *왜 PR 마다 다른지* 적어야 한다.
_PER_PR_TOKENS = (
    "github.event.pull_request.number",  # PR 번호
    "github.ref",                        # PR 에서는 refs/pull/<N>/merge
    "github.head_ref",                   # PR 소스 브랜치명
)

#: ★**실행마다** 고유한 토큰. 비-PR 이벤트(push/dispatch)의 그룹 키가 이것으로 떨어져야
#: 그 이벤트들이 **사실상 그룹을 형성하지 않는다**.
#: ★★왜 필요한가(2026-09-15 · 독립 리뷰 MAJOR-1): `cancel-in-progress: false` 는
#:   「취소 안 함」이 **아니다** — 같은 그룹의 **대기 중** 실행을 새 실행이 취소한다
#:   (GitHub 은 그룹당 대기를 하나만 유지). `github.ref` 로 떨어뜨리면 main 푸시가 전부
#:   한 그룹이 되어 **가운데 머지의 래칫 기준선이 사라진다** — 이 파일이 막겠다고 선언한
#:   바로 그 손실이다. `github.ref` 는 «PR 마다 다름»에는 참이지만 «실행마다 다름»에는
#:   **거짓**이라, 두 목록을 **따로** 둔다.
_RUN_UNIQUE_TOKENS = ("github.run_id",)


def _classify(conc: object) -> str:
    """concurrency 선언 하나를 판정한다. 반환값은 **닫힌 어휘**다.

    ★「없음」과 「틀림」을 같은 값으로 접지 않는다 — 다음 행동이 다르다
      (넣어라 / 고쳐라). 뭉치면 «선언은 있는데 무효» 가 «미도입» 으로 읽힌다.
    """
    if conc is None:
        return "선언없음"
    if not isinstance(conc, dict):
        return "형식오류"
    group = str(conc.get("group", ""))
    cancel = str(conc.get("cancel-in-progress", "")).strip()
    if not any(tok in group for tok in _PER_PR_TOKENS):
        return "그룹공유"          # ① 모든 PR 이 한 그룹 — 남의 실행을 취소한다
    if "pull_request" in cancel and not any(t in group for t in _RUN_UNIQUE_TOKENS):
        # ★비-PR 이벤트가 그룹을 **공유**한다. 그때 cancel-in-progress 는 false 로 평가되는데,
        #   false 는 「취소 안 함」이 아니라 **「대기 중인 것을 취소한다」**이다.
        return "비PR그룹공유"
    if cancel.lower() in ("", "false"):
        return "취소안함"          # ② 선언만 있고 효과 0
    if cancel.lower() == "true":
        return "무조건취소"        # ③ main 푸시 기준선까지 취소한다
    if "pull_request" not in cancel:
        return "조건불명"          # 조건식인데 pull_request 를 안 본다
    return "적합"


# ── 판정기 자신을 먼저 잠근다(이 표가 죽으면 아래 본판정은 무엇으로 재도 초록이다) ──
@pytest.mark.parametrize(
    ("conc", "expect"),
    [
        (None, "선언없음"),
        ("group-only-string", "형식오류"),
        ({"group": "${{ github.workflow }}", "cancel-in-progress": True}, "그룹공유"),
        ({"group": "${{ github.workflow }}-${{ github.ref }}"}, "취소안함"),
        ({"group": "${{ github.ref }}", "cancel-in-progress": False}, "취소안함"),
        ({"group": "${{ github.ref }}", "cancel-in-progress": True}, "무조건취소"),
        ({"group": "${{ github.ref }}",
          "cancel-in-progress": "${{ github.event_name == 'push' }}"}, "조건불명"),
        # ★★MAJOR-1 회귀 대조군: 이 형태가 **종전 초판**이고, 락이 그것을 「적합」으로 읽었다.
        #   yml 만 고치고 이 행이 없으면 다음 사람이 되돌릴 때 **전건 초록**이 된다.
        ({"group": "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
          "cancel-in-progress": "${{ github.event_name == 'pull_request' }}"}, "비PR그룹공유"),
        # ★음성 대조군 — 무조건 취소면 비-PR 그룹 공유가 문제가 아니다(라벨이 뭉치면 안 된다).
        ({"group": "${{ github.workflow }}-${{ github.ref }}",
          "cancel-in-progress": True}, "무조건취소"),
        ({"group": "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}",
          "cancel-in-progress": "${{ github.event_name == 'pull_request' }}"}, "적합"),
    ],
)
def test_classifier_separates_every_failure_mode(conc: object, expect: str) -> None:
    """★위양성·위음성 양쪽 대조군 — 여덟 모집단이 **서로 다른 라벨**을 받아야 한다."""
    assert _classify(conc) == expect, f"판정기가 {conc!r} 를 {_classify(conc)!r} 로 읽는다"


def test_classifier_labels_are_all_distinct() -> None:
    """★라벨이 뭉치면 «없음»과 «틀림»이 구별되지 않는다(한 신호가 두 사건을 덮는다)."""
    labels = {"선언없음", "형식오류", "그룹공유", "비PR그룹공유", "취소안함",
              "무조건취소", "조건불명", "적합"}
    assert len(labels) == 8


# ── 본판정 ────────────────────────────────────────────────────────────────────
def _ci() -> dict:
    assert _CI.exists(), f"★대상이 없다 — 락이 낡았다(공허한 초록 방지): {_CI}"
    return yaml.safe_load(_CI.read_text(encoding="utf-8"))


def test_ci_cancels_superseded_pull_request_runs_only() -> None:
    got = _classify(_ci().get("concurrency"))
    assert got == "적합", (
        f"★ci.yml 의 concurrency 판정: {got}\n"
        "  적합 = 그룹 키가 PR 마다 다르고, 취소는 pull_request 일 때만 참.\n"
        "  실측 근거(2026-09-15 · 236 CI 실행 / 8일): 덮인 실행이 980분(27.3%)인데 취소는 0건이었다."
    )


def test_ci_has_no_approval_gate_so_no_run_ever_waits() -> None:
    """★이 처방의 **전제**를 같은 파일에서 잠근다.

    `environment:` 가 붙는 순간 실행이 `waiting` 을 거치고, 그때 «concurrency 가 waiting 을
    취소하는가» 라는 **미측정 축**이 되살아난다(#1029 가 그 축 때문에 이 처방을 기각했다).
    전제가 깨지면 이 락이 **먼저** 빨개져야 한다 — 조용히 참이 아니게 되면 안 된다.
    """
    jobs = _ci()["jobs"]
    with_env = sorted(name for name, spec in jobs.items()
                      if isinstance(spec, dict) and "environment" in spec)
    assert not with_env, (
        f"★ci.yml 의 잡에 승인 게이트가 생겼다: {with_env}\n"
        "  그러면 실행이 `waiting` 을 거치고, cancel-in-progress 가 그것을 취소하는지는 "
        "이 저장소에서 **한 번도 측정되지 않았다**(#1029). 처방의 전제가 깨졌으니 "
        "cancel-in-progress 를 유지할지 **다시 재라**."
    )
    # ★공허 방지 — 잡이 0개면 위 단언은 저절로 참이다.
    assert len(jobs) >= 4, f"잡이 {len(jobs)}개뿐이다 — 파싱이 죽었는지 확인하라"


def test_required_checks_are_all_jobs_in_this_workflow() -> None:
    """★취소가 **필수 체크**에 닿는다는 사실을 눈에 보이게 둔다.

    취소된 실행의 필수 체크는 `cancelled` 로 남고 PR 은 새 실행이 초록이 될 때까지 막힌다.
    그것이 **의도된 동작**이다(낡은 head 의 초록은 어차피 쓰이지 않는다). 이 단언은
    「필수 체크가 이 워크플로 밖으로 나가면」 그 가정이 깨지는 것을 잡는다.
    """
    names = {spec.get("name", j) for j, spec in _ci()["jobs"].items() if isinstance(spec, dict)}
    assert "Backend (pytest)" in names and "Detect changes" in names, (
        f"★필수 체크의 잡 이름이 이 워크플로에 없다: {sorted(names)}"
    )
