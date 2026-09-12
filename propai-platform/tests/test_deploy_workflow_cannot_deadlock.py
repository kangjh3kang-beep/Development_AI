"""배포 워크플로가 **한 번 안 눌리면 영구 정지**하지 않는지, 그리고 **158 에 api 를 굽지
않는지** 잠근다.

## 왜 (실측 2026-09-10)

`Deploy to Oracle Cloud` 최근 **100건 → cancelled 99 · pending 1 · 성공 0**
(★대조군 `CI` 30건 → success 27 ⇒ 조회기 생존. 「성공 0」은 조회 실패가 아니다).

원인은 하나다. 2026-08-20 01:04 에 시작된 run `32319697071` 이 `oracle-production` 의
`required_reviewers` 게이트에서 **20일째 `waiting`** 이었고, 워크플로가
`concurrency: {group: oracle-deploy, cancel-in-progress: false}` 라 **그 실행이 그룹을
점유**했다. `false` 는 «먼저 온 것이 이긴다» 이므로 뒤이은 배포는 전부 대기로 밀렸고,
**그룹당 대기는 1개**뿐이라 다음 푸시가 앞의 대기를 취소했다 — 그래서 99건이 `cancelled` 다.

★**개입 실험으로 인과를 확증했다**: 묵은 실행을 취소하자 20일간 `pending` 이던 실행이
**즉시 `in_progress`** 로 전이했다.

★★**그리고 처방이 함정이었다.** 가장 먼저 떠오르는 행동은 *"대기 중인 걸 승인한다"* 인데,
그 실행의 head 는 당시 main 보다 **308커밋 뒤**라 **승인이 곧 대규모 롤백**이었다.
올바른 순서는 «묵은 실행 취소 → 새 실행 승인» 이다.

## ★처방은 「최신이 이긴다」가 아니라 **「실행을 만들지 않는다」** 다

초판은 `cancel-in-progress: true` 만으로 고치려 했다. **하중 전제가 미검증이었다** —
GitHub 이 `waiting`(환경 승인 대기) 실행을 concurrency 로 취소하는지 문서가 말하지 않는다
(문서는 `pending`·`in progress` 만 서술). 안 한다면 그 변경은 **아무것도 고치지 못한다.**

그래서 **증명 가능한 것**으로 바꿨다 — `on: push` 를 지웠다. 실행 생성원이 사라지면
누적도 사라진다(트리거 정의만으로 성립한다 · 플랫폼 의미론을 추측하지 않는다).
근거: 푸시 트리거의 측정된 성적은 **400건 중 성공 0**(cancelled 308 + failure 92).

## ★두 번째 결함 — 게이트가 그것을 **가리고 있었다**

`DEPLOY_TARGET` 기본값이 `both` 였고, `workflow_dispatch` 의 **드롭다운 기본값도 `both`**
였다(후자가 **사람이 실제로 누르는 값**이다). 이 워크플로는 **158(프론트) 전용**이고
`safe-deploy.sh both` 는 `build_one api` + `recreate_one api` 로 **158 에 api 컨테이너를
만든다**(`:146,211`). 그리고 `propai-platform/nginx.conf:24-26` 이 `/api/` 를
**168 로 직결**하므로 158 의 api 는 **트래픽을 0 받는다**.

★**초판이 여기서 거짓을 적었다**(적대 리뷰가 실측 반증):
*"한 번도 실행되지 못해서다 · 승인하는 순간 처음 터진다"* → **둘 다 틀렸다.**
페이징하면 2026-08-12~08-20 에 배포 잡이 **92회 실행**됐고 전부
`Validate Oracle deployment secrets` 에서 죽었다. `ORACLE_*` 시크릿은 **미등록**이다
(실측: repo·env 조회 0건 — 초판은 이것을 *"읽을 수 없어 미측정"* 이라 적었는데
**읽을 수 있었다**. 안 재 본 것을 「불가」로 적은 것이다).
⇒ 타깃 수정은 **긴급 봉합이 아니라 예방**이다.

★형제 `test_deliberation_ci_required_shape.py` 가 기록한 함정을 그대로 쓴다 —
**PyYAML 은 `on:` 을 불리언 `True` 로 파싱한다.**
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# ★형제 관례를 따른다 — `tests._scan_guard` **패키지 임포트**
#   (`test_coord_summary_contract.py:40` · `test_scan_guard_self.py:12`).
from tests._scan_guard import code_lines


def _shell_code(text: str) -> str:
    """셸 소스에서 **줄 주석 + 줄끝 주석**을 걷는다.

    ★★`_scan_guard.code_lines` 는 **줄 전체 주석만** 걷는다 — 그 파일이 자기 독스트링에
      *"여기서는 줄 주석만 처리한다고 명시한다"* 라고 **적어 뒀는데 내가 안 읽고 썼다.**
      그래서 `… ;;  # legacy was: both) recreate_one api …` 같은 **줄끝 주석 위장**에
      뚫렸다(적대 리뷰 실측 SURVIVED). ***모듈이 자기 근거로 적어 둔 한계도 읽어야 한다.***

    ★**한계를 정직하게 적는다**: 따옴표 안의 `#` 은 구분하지 못한다(휴리스틱). 그래서 아래
      `test_shell_comment_stripper_is_alive` 가 **양성·음성 대조군**으로 이 함수의 생존을
      먼저 증명한다 — 스트리퍼가 죽으면 그 위의 모든 "발견"이 조용히 거짓이 된다.
    """
    return "\n".join(ln.split(" #", 1)[0] for ln in code_lines(text, comment_prefixes=("#",)).splitlines())


def test_shell_comment_stripper_is_alive() -> None:
    """★대조군 먼저 — 스트리퍼가 죽으면 아래 근거 검사가 「위반 0」으로 조용히 통과한다."""
    stripped = _shell_code("a=1  # both) recreate_one api\n# both) recreate_one api\nb=2")
    assert "recreate_one api" not in stripped, "줄끝/줄전체 주석이 안 걷혔다 — 스트리퍼 사망"
    assert "a=1" in stripped and "b=2" in stripped, "실행 라인까지 지웠다 — 스트리퍼 과잉"

_WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy-cloudflare.yml"
# ★`both` 가 실제로 158 에 api 를 굽는다는 근거 파일 — 주장을 파일 존재로 붙잡아 둔다.
_DEPLOY_SH = Path(__file__).resolve().parents[1] / "scripts" / "safe-deploy.sh"


def _doc() -> dict:
    assert _WF.exists(), f"배포 워크플로가 없다(경로가 바뀌었나): {_WF}"
    return yaml.safe_load(_WF.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    """`on:` 을 꺼낸다 — PyYAML 이 `on` 을 **불리언 True 로 파싱**한다(형제 락의 기록)."""
    return doc.get("on") or doc.get(True) or {}


def _deploy_target_exprs(doc: dict) -> list[str]:
    """`DEPLOY_TARGET` 을 쓰는 **모든** 잡의 표현식.

    ★초판은 **첫 번째로 찾은 잡**만 보고 반환했다(목록형 축). 잡이 늘어 앞쪽 잡이 올바른
    값을 가지면 **뒤쪽 진짜 배포 잡이 `both` 여도 초록**이다 — 적대 리뷰가 가짜 선행 잡으로
    실증했다. ***파생의 축을 「첫 하나」로 두지 마라.***
    """
    jobs = doc.get("jobs") or {}
    assert jobs, "jobs 가 비었다 — 조회기 사망"
    found = [
        str(env["DEPLOY_TARGET"])
        for env in ((job or {}).get("env") or {} for job in jobs.values())
        if "DEPLOY_TARGET" in env
    ]
    assert found, "DEPLOY_TARGET 을 쓰는 잡이 없다 — 배선이 사라졌나"
    return found


def test_push_deploy_cannot_be_blocked_forever_by_a_stale_waiting_run() -> None:
    """★최신이 이긴다 — 미승인 대기 하나가 이후 배포를 영구히 죽이지 못한다."""
    doc = _doc()
    conc = doc.get("concurrency")
    # ★공허 진리 가드 — 키가 없으면 아래 단언이 «없으니 통과» 로 새어 나간다.
    assert isinstance(conc, dict), f"concurrency 블록이 없다(구조가 바뀌었나): {conc!r}"
    # ★그룹 **정체성**까지 못 박는다. 초판은 «비어 있지 않음» 만 봐서 `oracle-deploy-${{ github.run_id }}`
    #   처럼 실행마다 갈리는 값으로 바꿔도 통과했다(변이 SURVIVED) — 그러면 상호배제가 통째로 사라진다.
    assert conc.get("group") == "oracle-deploy", (
        f"concurrency.group 이 {conc.get('group')!r} 다. 실행마다 갈리는 값이면 상호배제가 사라진다."
    )
    assert conc.get("cancel-in-progress") is True, (
        "cancel-in-progress 가 참이 아니다. 이 값이 거짓이면 **가장 오래된 미승인 대기가 이긴다** — "
        "실측: 그 상태로 20일간 성공 0/100(cancelled 99). 되돌리려면 계획서 "
        "_workspace/PLAN_deploy_gate_never_unblocks_2026-09-10.md §2-b 의 근거부터 반증하라."
    )


def test_no_automatic_trigger_can_pile_runs_onto_the_approval_gate() -> None:
    """★★실행 생성원 자체를 없앤다 — 이것이 교착을 푸는 **증명 가능한** 축이다.

    `cancel-in-progress` 에 기대면 «GitHub 이 `waiting` 을 취소하는가» 라는 **미검증 전제**에
    올라탄다. 자동 트리거가 없으면 누적이 원리적으로 불가능하다.
    """
    trig = _triggers(_doc())
    assert trig, "트리거가 통째로 비었다 — 조회기 사망"
    assert "workflow_dispatch" in trig, "수동 실행 경로까지 사라졌다 — 배포할 방법이 없다"
    for auto in ("push", "pull_request", "schedule", "release"):
        assert auto not in trig, (
            f"자동 트리거 {auto!r} 가 되살아났다. 승인 게이트(`oracle-production` ·"
            " required_reviewers)와 자동 트리거가 만나면 **승인이 한 번 안 눌릴 때 영구 정지**한다"
            " — 실측 400건 중 성공 0(cancelled 308 + failure 92)."
            " 되살리려면 워크플로 `on:` 주석의 4단계(시크릿 등록 → 게이트 재검토 → 트리거 복원 →"
            " waiting 취소 여부 실측)를 먼저 밟아라."
        )


def test_every_job_defaults_to_web_because_158_must_have_zero_api() -> None:
    """★158 기본 타깃은 `web` — `both` 는 프론트 서버에 api 컨테이너를 만든다.

    ★**두 자리를 함께 본다**: env 폴백과 **dispatch 드롭다운 기본값**. 후자가 사람이
    실제로 누르는 값인데 초판은 그것을 안 봤다(변이 SURVIVED).
    """
    doc = _doc()

    # ── ① env 폴백 — 모든 잡 ──
    exprs = _deploy_target_exprs(doc)
    for expr in exprs:
        m = re.search(r"(?:github\.event\.)?inputs\.target\s*\|\|\s*'([^']+)'", expr)
        assert m, f"DEPLOY_TARGET 폴백 형태를 못 찾았다 — 조회기 사망: {expr!r}"
        assert m.group(1) == "web", (
            f"어떤 잡의 기본 타깃이 {m.group(1)!r} 다. 이 워크플로는 **158 전용**이고 "
            "`safe-deploy.sh both` 는 158 에 api 컨테이너를 만든다(:146,211). "
            "그런데 nginx.conf:24-26 이 /api/ 를 168 로 직결하므로 그 컨테이너는 **트래픽 0** 이다."
        )

    # ── ② ★dispatch 드롭다운 기본값 — 사람이 실제로 누르는 값 ──
    target = ((_triggers(doc).get("workflow_dispatch") or {}).get("inputs") or {}).get("target") or {}
    assert target, "workflow_dispatch 의 target 입력이 사라졌다 — 조회기 사망"
    assert target.get("default") == "web", (
        f"dispatch 기본값이 {target.get('default')!r} 다. 이것이 `Run workflow` 드롭다운에 "
        "미리 선택되는 값이라, 운영자가 그대로 누르면 158 에서 `both` 가 돈다. "
        "env 폴백만 고치고 여기를 두면 **형제 축이 그대로 남는다**(실측 SURVIVED)."
    )

    # ── ③ 근거가 실재하는지 — ★주석에 뚫리지 않게 걷어내고 본다 ──
    assert _DEPLOY_SH.exists(), f"safe-deploy.sh 가 없다(경로가 바뀌었나): {_DEPLOY_SH}"
    sh_raw = _DEPLOY_SH.read_text(encoding="utf-8")
    sh_code = _shell_code(sh_raw)
    # ★공허 진리 가드 — 반드시 있어야 할 것이 스캔에 잡히는가(조회기 생존).
    assert "recreate_one web" in sh_code, "safe-deploy.sh 스캔이 비었다 — 조회기 사망"
    assert re.search(r"\bboth\)\s*.*\brecreate_one api\b", sh_code), (
        "safe-deploy.sh 의 `both` 분기가 더는 api 를 재생성하지 않는다(★주석 제외 후 판정) — "
        "그렇다면 위 단언의 **근거가 바뀐 것**이니 이 락의 사유부터 다시 쓰라."
    )


def test_explicit_dispatch_can_still_choose_both_or_api() -> None:
    """★과잉 처방 금지 — 168 경로와 preflight 가드의 모집단을 지우지 않는다.

    기본값만 고쳤지 **선택지를 없애지 않았다**는 것을 잠근다. 이 단언이 없으면 다음 사람이
    *"both 가 위험하다"* 만 읽고 선택지를 지워 **정상 경로를 막는다**(위양성도 결함이다).
    """
    doc = _doc()
    dispatch = _triggers(doc).get("workflow_dispatch") or {}
    options = ((dispatch.get("inputs") or {}).get("target") or {}).get("options") or []
    assert options, "workflow_dispatch 의 target 선택지가 비었다 — 조회기 사망"
    for keep in ("web", "api", "both"):
        assert keep in options, f"dispatch 선택지에서 {keep!r} 가 사라졌다 — 정상 경로를 막는다"
