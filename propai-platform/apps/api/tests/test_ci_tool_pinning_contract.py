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

★★2026-08-30 — **이 파일이 잡지 못한 축이 있었다: `uses:` (GitHub Actions).**
  같은 사고가 **다른 매체**에서 그대로 재발했다:

      Security Scan / Gitleaks 잡
        같은 커밋 09b270fb  08-28 **success**  →  08-30 **failure** (26건)
        코드 변경 **0**. 원인은 `uses: gitleaks/gitleaks-action@v2` 의 **이동 태그**.

  이 파일의 독스트링은 *"워크플로 전체에서 핀 없는 설치 줄"* 이라 적었지만 실제 탐지는
  `pip install` **한 매체**만 봤다 — **처방을 적용한 범위가 결함이 사는 범위보다 좁았다**
  (CLAUDE.md §D20). 그래서 `uses:` 축을 **같은 파일에 추가**한다(새 파일을 만들지 않는다).

  ★`actions/*` 는 예외다 — GitHub 공식 인프라 액션이고 **규칙(findings)을 만들지 않는다**.
    핀이 필요한 것은 **판정을 만드는 서드파티**다(스캐너·서명·SBOM).
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


def test_병렬_실행과_핀이_한_쌍으로_움직인다() -> None:
    """`-n auto` 를 쓰면 xdist·execnet 이 **반드시 핀돼 있어야** 한다 — 양방향으로 잠근다.

    ★한쪽만 걸면 반대쪽이 무제한이 된다(CLAUDE.md D.19 — 상한만 걸었더니 하한이 0으로 붕괴).
      · `-n auto` 만 있고 핀이 없으면 → 도구 릴리스가 코드 변경 0으로 CI 를 뒤집는다
        (이 파일이 존재하는 바로 그 이유다)
      · 핀만 있고 `-n auto` 가 사라지면 → 측정으로 얻은 1.95배가 조용히 사라진다
        (CI 실측: 직렬 750초 → 병렬 385초, 9392 passed 완전 일치)

    ★전이 의존성(execnet)까지 본다. xdist 만 핀하면 이 파일의 존재 이유가 반만 지켜진다.
    """
    dev = Path(__file__).resolve().parents[1] / "requirements-dev.txt"
    dev_text = dev.read_text(encoding="utf-8")
    ci = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    # 주석 줄 제외 — 이 PR 의 주석에 `-n auto` 라는 문구가 설명으로 들어 있다.
    ci_code = "\n".join(ln for ln in ci.splitlines() if not ln.strip().startswith("#"))

    uses_parallel = re.search(r"pytest[^\n]*\s-n\s+auto", ci_code) is not None
    pinned = {t: (f"{t}==" in dev_text) for t in ("pytest-xdist", "execnet")}

    if uses_parallel:
        missing = [t for t, ok in pinned.items() if not ok]
        assert not missing, (
            f"CI 가 `-n auto` 로 병렬 실행하는데 {missing} 이(가) 핀되지 않았다. "
            "도구 릴리스 하나가 코드 변경 0으로 CI 를 뒤집을 수 있다."
        )
    else:
        assert not any(pinned.values()), (
            "xdist/execnet 이 핀돼 있는데 CI 는 병렬로 돌지 않는다 — 측정으로 얻은 1.95배가 "
            "조용히 사라진 상태다. 되돌린 것이 의도라면 핀도 함께 지워라."
        )


# ── `uses:` 축(2026-08-30 추가) ────────────────────────────────────────────────

#: `uses: owner/repo@ref` — 주석 줄은 제외한다(위 `_code_lines` 와 같은 규율).
_USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)@(?P<ref>\S+)")

#: GitHub 공식 인프라 액션 — **판정(findings)을 만들지 않으므로** 메이저 태그를 허용한다.
#: ★예외에는 사유를 적는다(죽은 면제를 초록으로 두지 않기 위해 아래 대조군이 이 집합을 태운다).
_ACTIONS_ORG_EXEMPT = "actions"

#: 핀으로 인정 — 40자 SHA 또는 `vN.N.N` 이상의 구체 버전. 맨 `vN` 은 **이동 태그**다.
_REF_PINNED = re.compile(r"^([0-9a-f]{40}|v?\d+\.\d+(\.\d+)?([-.+]\S+)?)$")


def _uses_entries():
    out = []
    for f in _workflow_files():
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            m = _USES.match(line)
            if m:
                out.append((f.name, i, m.group("owner"), m.group("repo"), m.group("ref")))
    return out


def test_uses_수집기가_살아있다() -> None:
    """★대조군 — 0건을 찾고 「위반 0」이라 말하지 않는다."""
    entries = _uses_entries()
    assert len(entries) >= 5, f"`uses:` 를 {len(entries)}개만 찾았다 — 수집기 사망"
    assert any(o != _ACTIONS_ORG_EXEMPT for _f, _i, o, _r, _ref in entries), (
        "서드파티 액션을 하나도 못 찾았다 — 아래 검사가 공허해진다"
    )


def test_서드파티_액션이_이동태그를_쓰지_않는다() -> None:
    """★2026-08-30 실사고 — `gitleaks-action@v2` 가 **코드 변경 0으로** 게이트를 빨갛게 만들었다.

    같은 커밋 `09b270fb` 가 08-28 success / 08-30 failure(26건). 스캐너 규칙이 넓어진 것이고,
    **26/26 이 위양성**이었다(테스트 더미·객체 키·`CHANGE_ME_…` 플레이스홀더).
    """
    bad = [
        f"{f}:{i} {o}/{r}@{ref}"
        for f, i, o, r, ref in _uses_entries()
        if o != _ACTIONS_ORG_EXEMPT and not _REF_PINNED.match(ref)
    ]
    assert not bad, (
        "판정을 만드는 서드파티 액션이 **이동 태그**를 쓴다 — 새 릴리스가 코드 변경 0으로 "
        f"게이트를 빨갛게 만든다: {bad}"
    )


@pytest.mark.parametrize(
    ("ref", "pinned"),
    [
        ("v2", False),          # ★이번 사고의 그 형태
        ("v0", False),
        ("main", False),
        ("v2.3.9", True),
        ("ff98106e4c7b2bc287b24eaf42907196329070c7", True),
    ],
)
def test_ref_판정기_대조군(ref: str, pinned: bool) -> None:
    """★검사기가 **양방향**으로 작동하는지 — 「전부 통과」·「전부 차단」 구현을 잡는다."""
    assert bool(_REF_PINNED.match(ref)) is pinned


def test_공식액션_예외가_죽지_않았다() -> None:
    """★죽은 면제를 초록으로 두지 않는다 — `actions/*` 가 실제로 쓰이고 있는가."""
    owners = {o for _f, _i, o, _r, _ref in _uses_entries()}
    assert _ACTIONS_ORG_EXEMPT in owners, (
        "`actions/*` 예외의 대상이 사라졌다 — 면제를 지워라(남기면 다음 사람이 오독한다)"
    )
