"""CI 도구 버전 핀 계약 — **같은 명령이라도 버전이 다르면 결과가 다르다.**

★왜 (2026-08-16 실사고):
    ci.yml 이 `pip install ruff` 로 **버전 없이** 설치해 실행마다 최신을 받았다.
    그날 로컬 `ruff 0.15.7` 은 All checks passed 인데 CI `0.16.3` 은 **I001 로 실패**했다.
    **명령은 같았다** (`python -m ruff check .`). 다른 것은 오직 버전이었다.

    위험의 크기: 린터가 규칙을 하나 추가하면 **코드 변경 0으로 전 PR 이 빨개진다.**
    원인이 자기 diff 에 없어 진단이 길고, 그동안 CI 한 사이클(≈16분)씩 태운다.

★CLAUDE.md 의 "게이트는 CI 와 같은 명령으로"는 이 반쪽을 **못 덮는다** — 명령을 맞춰도 뚫린다.
  규율은 **"같은 명령 + 같은 버전"** 이어야 하고, 이 테스트가 그 후반부를 잠근다.

★목록형이 아니라 **파생형**이다. "ruff 를 핀했는가"를 보면 다음에 추가되는 도구가 그대로
  빠져나간다(실제로 이번 스윕에서 `bandit`·`pip-audit` 두 형제가 같은 상태로 발견됐다).
  그래서 **워크플로 전체에서 핀 없는 설치 줄**을 찾는다 — 새 워크플로도 자동으로 감시망에 든다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# `pip install <무엇>` 에서 <무엇>을 집는다(줄 끝·백슬래시 연결 고려).
_PIP_INSTALL = re.compile(r"\bpip\s+install\s+(?P<args>[^\n]*)")

# 핀으로 인정하는 형태 — 아래 중 하나면 통과.
#   -r/-c <파일>      : 요구사항·제약 파일 경유(정본이 버전을 갖는다)
#   -e <경로>         : 로컬 편집설치(버전 개념이 다르다)
#   <pkg>==<버전>     : 직접 핀. `"gdal==$(gdal-config --version)"` 처럼 **동적 핀**도 포함한다
#                       (시스템 버전에 맞추는 것이 의도이고, 그 이유가 ci.yml 주석에 있다)
#   --upgrade pip     : pip 자체 최신화(의도된 예외)
_PINNED = (
    re.compile(r"(^|\s)-(r|c)\s"),
    re.compile(r"(^|\s)-e(\s|$)"),
    re.compile(r"=="),
    re.compile(r"--upgrade\s+pip(\s|$)"),
)


def _workflow_files() -> list[Path]:
    return sorted(p for p in _WORKFLOWS.glob("*.yml") if p.is_file())


def _install_lines(text: str) -> list[str]:
    """주석 줄은 제외한다 — 주석 속 `pip install ruff` 는 실행되지 않는다.

    ★이 저장소는 "소스 검사가 주석에 뚫린다"로 여러 번 데였는데, 여기서는 **반대 방향**이다:
      주석을 코드로 읽으면 **정상 코드를 위반으로 신고**한다(위양성도 결함이다).
      실제로 이 PR 의 ci.yml 주석에 `pip install ruff` 라는 문구가 들어 있다.
    """
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if _PIP_INSTALL.search(stripped):
            out.append(stripped)
    return out


def test_워크플로에_핀_없는_pip_설치가_없다() -> None:
    files = _workflow_files()
    # 공허 진리 가드 — 파일이 0개면 "위반 0"은 아무 뜻이 없다.
    assert files, f"워크플로 파일을 하나도 못 찾았다: {_WORKFLOWS}"

    all_lines = [(p.name, ln) for p in files for ln in _install_lines(p.read_text(encoding="utf-8"))]
    # ★양성 대조 — 검사 대상이 **실재**해야 한다. 0건이면 정규식이 죽은 것이지
    #   "핀 없는 설치가 없다"가 아니다(이 세션에서 그 형태의 위양성이 다섯 번 났다).
    assert len(all_lines) >= 3, (
        f"`pip install` 줄을 {len(all_lines)}건만 찾았다 — 탐지기가 죽었을 가능성이 크다. "
        "정규식이나 경로를 확인하라(대조군 실패는 통과가 아니다)."
    )

    unpinned = [
        f"{name}: {line}"
        for name, line in all_lines
        if not any(p.search(line) for p in _PINNED)
    ]
    assert not unpinned, (
        "워크플로가 **버전 없이** 도구를 설치한다 — 도구 릴리스 하나가 코드 변경 0으로 CI 를 "
        "뒤집을 수 있다. requirements-dev.txt 에 핀하고 `-r` 로 설치하라:\n  "
        + "\n  ".join(unpinned)
    )


def test_dev_요구사항_파일이_실제로_핀돼_있다() -> None:
    dev = Path(__file__).resolve().parents[1] / "requirements-dev.txt"
    assert dev.exists(), f"{dev} 가 없다 — 위 테스트가 가리키는 정본이 부재하면 처방이 공허하다."
    entries = [
        ln.strip()
        for ln in dev.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert entries, "requirements-dev.txt 에 항목이 없다(주석뿐이면 잠금이 아니다)."
    unpinned = [e for e in entries if "==" not in e]
    assert not unpinned, f"정확 핀(==)이 아닌 항목: {unpinned}"


@pytest.mark.parametrize(
    ("line", "should_flag"),
    [
        # ★대조군 — 탐지기가 **진짜 위반을 잡는지** 먼저 보인다.
        #   "위반 0"을 믿으려면 같은 도구가 위반을 잡는 걸 봐야 한다.
        ("pip install ruff", True),
        ("pip install bandit", True),
        ("pip install pip-audit", True),
        # 그리고 **정상을 위반으로 찍지 않는지**(위양성도 결함이다).
        ("pip install -r requirements-dev.txt", False),
        ("pip install -r apps/api/requirements.txt", False),
        ('pip install "gdal==$(gdal-config --version)"', False),
        ("python -m pip install --upgrade pip", False),
        ("pip install -e '.[dev]'", False),
    ],
)
def test_탐지기_대조군(line: str, should_flag: bool) -> None:
    flagged = not any(p.search(line) for p in _PINNED)
    assert flagged is should_flag, f"판정이 기대와 다르다: {line!r} → flagged={flagged}"
