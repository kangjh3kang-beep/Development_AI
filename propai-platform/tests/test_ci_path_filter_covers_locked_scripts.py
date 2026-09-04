"""★CI 경로 필터가 **락이 태우는 파일**을 실제로 감시하는지 잠근다.

【왜 생겼나 · 2026-09-03 적대 리뷰 실측】
`ci.yml` 의 `Detect changes` 가 `platform` 여부를 경로 필터로 정하고, `Backend (pytest)` 잡이
그 결과에 걸린다. 그 잡 안에 **루트 계약 스위트**(`propai-platform/tests`)가 들어 있다.
그런데 필터 ERE 가 `^(propai-platform/|\\.github/workflows/ci\\.yml$)` 였고, 이 저장소의 락은
`scripts/*.sh` 를 태운다 — 즉 **그 스크립트만 고친 PR 은 잡이 skip 되고, GitHub 은 skip 된
필수 잡을 「충족」으로 계수**한다(fail-open 무검증 머지).

★이 저장소에 같은 클래스의 전례가 있다: *"면제를 남기면 락은 skip 이라 무잠금"*.
★그리고 **이 파일 자신이 그 함정에 들어 있었다** — `scripts/coord.sh` 를 잠그는 락을 만들면서
  그 경로가 CI 감시 밖이라는 것을 몰랐다. 적대 리뷰가 저장소 경계 **밖으로** 범위를 넓혀 찾았다.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CI = _REPO / ".github" / "workflows" / "ci.yml"

# ★락이 태우는 저장소 루트 밖(=`propai-platform/` 밖) 경로를 **테스트 파일에서 파생**시킨다.
#   손으로 열거하면 그 목록이 곧 상한이 된다.
_TESTS_DIR = Path(__file__).resolve().parent


def _filter_ere() -> str:
    src = _CI.read_text(encoding="utf-8")
    m = re.search(r"grep -qE '([^']+)' <<<\"\$FILES\"", src)
    assert m, "★ci.yml 에서 경로 필터 ERE 를 못 찾았다 — 락이 낡았다(공허한 초록 방지)"
    return m.group(1)


def _paths_locked_outside_platform() -> set[str]:
    """루트 계약 스위트가 참조하는 `propai-platform/` **밖** 경로를 모은다(파생)."""
    out: set[str] = set()
    for f in _TESTS_DIR.glob("test_*.py"):
        for m in re.finditer(r'"(scripts/[A-Za-z0-9_./-]+)"', f.read_text(encoding="utf-8")):
            out.add(m.group(1))
        # `_REPO / "scripts" / "coord.sh"` 형태
        for m in re.finditer(r'_REPO\s*/\s*"(scripts)"\s*/\s*"([A-Za-z0-9_.-]+)"',
                             f.read_text(encoding="utf-8")):
            out.add(f"{m.group(1)}/{m.group(2)}")
    return out


def test_scanner_alive_we_found_paths_to_check() -> None:
    """★공허 진리 방지 — 검사할 경로가 0건이면 아래 단언이 저절로 참이다."""
    got = _paths_locked_outside_platform()
    assert got, ("★루트 스위트에서 `scripts/…` 참조를 하나도 못 찾았다. 파생이 죽었는지 확인하라 "
                 "(락이 실제로 그 경로를 안 태우게 됐다면 이 테스트를 지워도 된다).")
    # ★집합 전체만 보면 «특정 대상이 감시망에서 빠지는» **부분 공허**를 못 잡는다
    #   (3차 리뷰 실측: 한 파생 경로를 죽여도 다른 파일의 리터럴이 대신 채워 SURVIVED).
    assert "scripts/coord.sh" in got, f"★이 PR 이 잠그는 그 스크립트가 파생 집합에 없다: {sorted(got)}"


def test_ci_path_filter_matches_every_locked_script() -> None:
    """★필터가 그 경로들을 **전부** 매치한다 — 하나라도 빠지면 그 PR 은 무검증으로 머지된다."""
    ere = _filter_ere()
    rx = re.compile(ere)
    missed = sorted(p for p in _paths_locked_outside_platform() if not rx.match(p))
    assert not missed, (
        f"★CI 경로 필터가 락 대상을 감시하지 않는다: {missed}\n"
        f"  필터 ERE: {ere}\n"
        "  그 경로만 고친 PR 은 Backend (pytest) 잡이 skip 되고, skip 된 필수 잡은 「충족」으로 "
        "계수돼 **무검증 머지**가 된다.")


def test_filter_still_matches_platform_and_itself() -> None:
    """★음성/양성 대조군 — 필터를 넓힌 것이 기존 매치를 깨지 않았는지(양방향).

    ★거부 축도 본다: 필터가 **모든 것**을 매치하면 «전부 실행» 이라 이 검사가 무의미해진다.
    """
    rx = re.compile(_filter_ere())
    for ok in ("propai-platform/apps/web/x.tsx", ".github/workflows/ci.yml", "scripts/coord.sh"):
        assert rx.match(ok), f"★필터가 {ok} 를 놓친다"
    for no in ("README.md", "docs/x.md", "coordination/PROTOCOL.md"):
        assert not rx.match(no), f"★필터가 {no} 까지 매치한다 — 「전부 실행」이면 이 검사가 무의미하다"
