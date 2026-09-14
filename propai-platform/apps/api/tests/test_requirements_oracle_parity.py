"""**운영 이미지가 실제로 설치하는 것**과 정본 requirements 의 괴리를 막는다.

## 왜 (2026-09-13 실측 — 같은 뿌리로 **두 건**이 이미 나 있었다)

`Dockerfile.oracle` 은 **`requirements.oracle.txt`** 를 `requirements.txt` 라는 이름으로 복사해
설치한다. 즉 ***`apps/api/requirements.txt` 에만 넣은 패키지는 운영에 도달하지 않는다.***

  · **`eth-account`** — 추첨 온체인 앵커링(#1047)을 넣으며 `requirements.txt` 에만 추가했다.
    통합자가 배포 후 *"컨테이너에 `eth_account` 없음"* 으로 잡았다(대조군 `httpx` 있음 ⇒ 진짜 부재).
  · **`defusedxml`** — 온비드 XML 파서가 **무방비로** 지연 임포트한다(`onbid_client.py:731`).
    운영 이미지에 없으므로 ***그 경로는 호출될 때 `ModuleNotFoundError` 로 죽는다.***
    (내가 만든 결함이 아니라 **같은 클래스의 선재 결함**이다 — 전역 스윕으로 발견했다.)

★***"내가 잰 것이, 사용자가 실제로 쓰는 그것인가"*** — 나는 **내가 찾은 파일**에 넣었고
  그것은 **운영이 쓰는 파일이 아니었다.**

## 이 락의 축

**목록을 손으로 관리하지 않는다.** 두 파일에서 패키지 집합을 **파생**하고,
차이는 `requirements.oracle.txt` 안의 `# ORACLE-EXCLUDE: <패키지> — <사유>` 선언으로만 허용한다.
⇒ 새 패키지를 정본에 넣으면 **여기에 넣거나 사유를 적거나** 둘 중 하나를 **강제**당한다.
★사유를 요구하는 이유: 제외는 **결정**이고, 결정에는 근거가 있어야 다음 사람이 되짚는다.
"""
from __future__ import annotations

import pathlib
import re

_API = pathlib.Path(__file__).resolve().parents[1]
_MAIN = _API / "requirements.txt"
_ORACLE = _API / "requirements.oracle.txt"
_DOCKER = _API.parents[1] / "Dockerfile.oracle"

_EXCLUDE_RE = re.compile(r"^#\s*ORACLE-EXCLUDE:\s*([A-Za-z0-9_.\-]+)\s*—\s*(\S.*)$")


def _packages(path: pathlib.Path) -> set[str]:
    """핀·마커·주석을 걷어낸 **패키지 이름 집합**(정규화: 소문자 · `_`→`-`)."""
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[;]", line, maxsplit=1)[0].strip()
        if name:
            out.add(name.lower().replace("_", "-"))
    return out


def _exclusions() -> dict[str, str]:
    got: dict[str, str] = {}
    for raw in _ORACLE.read_text(encoding="utf-8").splitlines():
        m = _EXCLUDE_RE.match(raw.strip())
        if m:
            got[m.group(1).lower().replace("_", "-")] = m.group(2).strip()
    return got


def test_dockerfile_really_installs_the_oracle_file():
    """★이 락의 **전제**부터 잠근다 — Dockerfile 이 다른 파일을 쓰게 바뀌면 이 락 전체가 헛것이다."""
    src = _DOCKER.read_text(encoding="utf-8")
    assert "requirements.oracle.txt" in src, (
        f"★{_DOCKER.name} 이 oracle requirements 를 안 쓴다 — 이 락이 겨누는 대상이 사라졌다"
    )
    assert re.search(r"pip install[^\n]*-r\s+requirements\.txt", src), (
        "설치 줄을 못 찾았다(대조군 실패 — Dockerfile 을 못 읽었거나 형태가 바뀌었다)"
    )


def test_every_main_package_is_shipped_or_explicitly_excluded():
    """★정본에 있는 패키지는 **운영 이미지에 있거나, 사유와 함께 제외 선언**돼 있어야 한다."""
    main, oracle, exc = _packages(_MAIN), _packages(_ORACLE), _exclusions()
    # 공허 방지 — 파싱이 죽으면 차집합이 비어 「위반 0」이 된다
    assert len(main) > 40, f"정본 파싱 실패(공허 방지): {len(main)}개"
    assert len(oracle) > 40, f"oracle 파싱 실패(공허 방지): {len(oracle)}개"

    missing = sorted(p for p in main - oracle if p not in exc)
    assert not missing, (
        "★정본에만 있고 운영 이미지에 없으며 **제외 선언도 없다** — 이 패키지들은 "
        f"***운영에 도달하지 않는다***: {missing}\n"
        "  → `requirements.oracle.txt` 에 추가하거나, "
        "`# ORACLE-EXCLUDE: <패키지> — <사유>` 로 **결정을 적어라**"
    )


def test_exclusions_all_carry_a_reason_and_are_real():
    """제외 선언이 **사유 없이** 늘어나면 그건 목록이 아니라 도피처다."""
    main, oracle, exc = _packages(_MAIN), _packages(_ORACLE), _exclusions()
    assert exc, "제외 선언을 하나도 못 읽었다(대조군 실패)"
    for pkg, why in exc.items():
        assert len(why) >= 8, f"{pkg}: 사유가 너무 짧다({why!r})"
    # ★**죽은 제외**도 결함이다 — 이미 넣었거나 정본에서 사라진 것을 제외로 남겨 두지 않는다
    dead = sorted(p for p in exc if p not in main or p in oracle)
    assert not dead, (
        f"★죽은 제외 선언(정본에 없거나 이미 운영에 들어 있다): {dead} — 지워라"
    )


def test_the_two_regressions_that_caused_this_lock_are_fixed():
    """★이 락을 낳은 **두 건**이 실제로 고쳐졌는지 못 박는다(회귀 방지).

    ***락만 넣고 원인을 안 고치면 다음 사람이 「이미 다뤄진 문제」로 읽는다.***
    """
    oracle = _packages(_ORACLE)
    for pkg, why in (("eth-account", "추첨 온체인 앵커링(#1047)"),
                     ("defusedxml", "온비드 XML 파서가 무방비로 지연 임포트한다")):
        assert pkg in oracle, f"★{pkg} 가 운영 이미지에 없다 — {why}"


def test_oracle_only_packages_are_intentional():
    """운영에만 있고 정본에 없는 것 — **정본이 진실의 전부가 아니게** 되므로 드러내 둔다."""
    main, oracle = _packages(_MAIN), _packages(_ORACLE)
    extra = sorted(oracle - main)
    # 현재 알려진 것만 허용한다(늘어나면 이 테스트가 그 사실을 말한다)
    known = {"minio"}
    assert set(extra) <= known, (
        f"★운영 이미지에만 있는 새 패키지: {sorted(set(extra) - known)} — "
        "정본에도 넣든지, 왜 운영에만 있는지 여기 적어라"
    )
