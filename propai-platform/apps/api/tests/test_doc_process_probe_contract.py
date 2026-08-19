"""문서가 적은 **프로세스 존재 프로브**가 자기 자신을 매칭하지 않는지 잠근다.

★왜 (2026-08-19):
    `CLAUDE.md` 는 이 덫을 **이미** 표로 적고 있다(§배포 조회기 함정):

        | `pgrep -f safe-deploy` (자기매칭) | `safe[-]deploy` |

    2026-06-25 인계서도 같은 경고를 담고 있다. 그런데 **2026-08-17 통합자 인계서가
    그 금지된 형태를 그대로 실었다**(`pgrep -c -f safe-deploy`). 지침은 있었고,
    **강제하는 것이 없어서** 두 달 만에 같은 덫이 다음 사람에게 다시 전달됐다.

    ★실측 반증(2026-08-19 · 158 실서버, 배포가 **끝난** 상태):
        cat /tmp/deploy_status.txt        → DONE web=200 api=200 @ b6011b3f
        pgrep -c -f safe-deploy           → 1     ← "아직 돌고 있다"로 읽힌다
        ps -ef | grep -c "[s]afe-deploy.sh" → 0   ← 실제 프로세스는 없다
    그 `1` 은 **그 명령을 나른 ssh 원격 명령 자신**이다. 명령줄에 패턴 문자열이
    들어 있으니 스스로 매칭한다. 즉 이 프로브는 **영원히 0 이 되지 않는다** —
    다음 통합자는 끝난 배포를 무한정 기다린다(실제로 4분 헛돌았다).

★이 테스트가 잠그는 것은 문구가 아니라 **부류**다.
    `#678` 이 sw.js 프로브를 "실행으로" 잠갔듯, 여기서는 프로세스 프로브를 잠근다.
    다만 원격 호스트의 프로세스 표는 CI 에서 재현할 수 없으므로,
    **자기매칭이라는 기전 자체를 합성 프로세스 표에 실행**해 확인한다(아래 마지막 테스트).
    "문서에 좋은 말이 적혀 있다"가 아니라 "그 형태가 실제로 자기를 집는다"를 태운다.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests._scan_guard import assert_absent

_REPO = Path(__file__).resolve().parents[4]
_PLATFORM = _REPO / "propai-platform"

_DOC_ROOTS = [
    _REPO / "CLAUDE.md",
    _PLATFORM / "_workspace",
    _PLATFORM / "docs",
]

# ★"틀린 형태를 반례로 보여주는 줄"은 위반이 아니다 — 오히려 권장된다.
#   가드의 위양성도 결함이다(CLAUDE.md §회귀망 A.6): 이 표식이 없으면
#   `CLAUDE.md:60` 의 덫 표와 2026-06-25 인계서의 경고문이 **위반으로 신고된다**.
#   반례를 적을 때는 같은 줄에 아래 낱말 중 하나를 남겨라.
_COUNTEREXAMPLE_MARKERS = ("자기매칭", "거짓양성", "위양성", "함정", "반례", "금지", "쓰지 마")

# 대괄호가 없는 `pgrep -f <패턴>` / `ps … | grep <패턴>`.
#   `[s]afe` 처럼 대괄호를 쓰면 grep 자신의 명령줄과 어긋나 자기매칭이 사라진다.
# ★`(?!-)` 가 필요하다 — 없으면 **플래그를 패턴으로 오인**한다.
#   실측 위양성(2026-08-19, 이 파일을 쓰는 중 발생): `ps -ef | grep -c "[s]afe-deploy.sh"` 에서
#   플래그 소비군이 0회로 물러나며 `-c` 를 패턴으로 집어, **대괄호를 제대로 쓴 정답 줄**을
#   위반으로 신고했다. 가드의 위양성도 결함이다(CLAUDE.md §회귀망 A.6) —
#   정상 표기를 막는 가드는 다음 사람이 가드를 지우게 만든다.
_BAD_PGREP = re.compile(r"pgrep\s+(?:-\w+\s+)*-\w*f\w*\s+(?![\"']?\[)(?!-)[\w.*/-]+")
_BAD_PSGREP = re.compile(r"ps\s+[\w-]+\s*\|\s*grep\s+(?:-\w+\s+)*(?![\"']?\[)(?!-)[\w.*/-]+")


def _doc_files() -> list[Path]:
    out: list[Path] = []
    for root in _DOC_ROOTS:
        if root.is_file():
            out.append(root)
        elif root.is_dir():
            out.extend(sorted(root.rglob("*.md")))
    return out


def _scannable_text() -> tuple[str, int]:
    """반례 표식이 붙은 줄을 걷어낸 문서 본문과, 걷어낸 줄 수."""
    kept: list[str] = []
    dropped = 0
    for path in _doc_files():
        for raw in path.read_text(encoding="utf-8").splitlines():
            if any(m in raw for m in _COUNTEREXAMPLE_MARKERS):
                dropped += 1
                continue
            kept.append(f"{path.name}: {raw}")
    return "\n".join(kept), dropped


def test_문서에_자기매칭_프로세스_프로브가_없다() -> None:
    text, dropped = _scannable_text()
    assert dropped > 0, (
        "반례 표식이 붙은 줄이 **한 줄도** 걷히지 않았다 — 걸러내기가 죽었거나 "
        "CLAUDE.md 의 덫 표가 사라졌다. 이 상태의 '위반 0'은 믿을 수 없다."
    )
    # ★양성대조: 문서에 배포 스크립트 이름이 실제로 실려 있어야 검사기가 산 것이다.
    #   0건이면 경로가 틀렸거나 문서가 비었다 — "위반 0" 과 반드시 구분한다.
    assert_absent(
        text,
        pattern=_BAD_PGREP,
        positive_control=r"safe-deploy",
        min_positive=3,
        reason=(
            "문서가 **자기매칭하는 프로세스 프로브**를 싣고 있다. `pgrep -f X` 는 그 명령을 "
            "나른 ssh 원격 명령줄까지 매칭해 **영원히 0 이 되지 않는다** — 끝난 배포를 "
            "'진행 중'으로 읽게 만든다(2026-08-19 실측: 배포 DONE 상태에서 결과 1). "
            "대괄호 형태(`safe[-]deploy`)를 쓰거나, 프로세스 대신 **상태파일 전이**로 판정하라. "
            "틀린 형태를 반례로 보여주는 줄이라면 같은 줄에 '자기매칭'·'함정' 등을 남겨라."
        ),
        where="문서 프로세스 프로브",
    )
    assert_absent(
        text,
        pattern=_BAD_PSGREP,
        positive_control=r"safe-deploy",
        min_positive=3,
        reason=(
            "`ps … | grep X` 도 같은 덫이다 — grep 자신이 프로세스 표에 있다. "
            "`grep \"[X]…\"` 로 적어라."
        ),
        where="문서 프로세스 프로브(ps|grep)",
    )


def test_자기매칭이_실제로_일어난다는_것을_합성_표에_태운다() -> None:
    """★소스 검사가 아니라 **기전**을 실행한다.

    핵심은 "프로세스 표에 **그 프로브 자신의 명령줄**이 들어 있다"는 점이다. 그래서
    표는 프로브마다 달라야 한다 — 대괄호를 쓴 프로브는 표에도 대괄호가 찍힌다.

    ★이 테스트를 처음 쓸 때 두 프로브에 **같은 표**를 줬다가 "대괄호도 자기를 집는다"는
      결과를 얻었다. 처방이 틀린 것이 아니라 **모델이 틀렸다** — 그 상태로 통과시켰다면
      이 파일은 존재하지 않는 결함을 잠갔을 것이다(공허한 회귀망).
    """

    def ps_table(probe_cmdline: str) -> str:
        """배포는 **끝났고**, 표에는 프로브를 나른 ssh 명령만 남은 상황."""
        return (
            "ubuntu 1001 1 0 00:00 ? 00:00:00 /usr/bin/dockerd\n"
            "ubuntu 2002 1 0 00:00 ? 00:00:00 sshd: ubuntu@notty\n"
            f"ubuntu 2003 2002 0 00:00 ? 00:00:00 bash -c {probe_cmdline}\n"
        )

    def count(pattern: str, table: str) -> str:
        return subprocess.run(
            ["grep", "-c", pattern], input=table, capture_output=True, text=True
        ).stdout.strip()

    naive_pat = "safe-deploy"
    bracket_pat = "safe[-]deploy"

    # 각 프로브가 실제로 표에 남기는 자기 명령줄
    naive_hits = count(naive_pat, ps_table(f"pgrep -c -f {naive_pat}"))
    bracket_hits = count(bracket_pat, ps_table(f"pgrep -c -f {bracket_pat}"))

    assert naive_hits == "1", (
        f"자기매칭이 재현되지 않았다({naive_hits!r}) — 합성 표가 실제 모습을 잃었으면 "
        "이 테스트는 아무것도 보증하지 않는다."
    )
    assert bracket_hits == "0", (
        f"대괄호 형태가 여전히 집는다({bracket_hits!r}) — 처방이 처방이 아니다."
    )

    # ★대조군: 배포가 **진짜 돌 때**는 두 형태 모두 그것을 집어야 한다.
    #   이게 없으면 "대괄호는 아무것도 안 집는다"(무용지물)와 구분되지 않는다.
    running = "ubuntu 3003 1 0 00:00 ? 00:02:11 bash propai-platform/scripts/safe-deploy.sh web main\n"
    assert count(naive_pat, running) == "1", "양성대조 실패 — 실행 중 배포를 못 집는다."
    assert count(bracket_pat, running) == "1", (
        "★대괄호 형태가 **실행 중인 배포도 못 집는다** — 그렇다면 처방은 자기매칭을 없앤 것이 "
        "아니라 프로브를 죽인 것이다."
    )
