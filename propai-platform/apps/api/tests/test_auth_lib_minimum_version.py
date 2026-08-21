"""인증 라이브러리를 **취약한 버전으로 되돌리지 못하게** 잠근다.

`python-jose 3.3.0` 에는 `PYSEC-2024-232` — **알고리즘 혼동**(OpenSSH ECDSA 키 등
다른 키 형식과의 혼동)이 있다. 이건 DoS 가 아니라 **인증 우회 계열**이다.
이 저장소의 인증은 전부 `from jose import jwt` 를 쓰므로 직격이다.

★올리는 데 대가가 있었다: `python-jose 3.4.0` 은 `pyasn1<0.5.0` 을 요구하고
  그 대역(0.4.8)에는 **DoS 4건**이 있다. pyasn1 수정본은 0.6.x 라 **제약상 올릴 수 없다**.
  건수로는 손해(+4, -3)지만 **인증 우회 > DoS** 라 올리는 쪽이 옳다고 판단했다.
  숫자가 아니라 내용으로 정한 것이다 — 되돌리려는 사람은 이 대가를 알고 결정하라.
"""

from __future__ import annotations

import pathlib
import re

_API = pathlib.Path(__file__).resolve().parents[1]
_MANIFESTS = ("requirements.txt", "requirements.oracle.txt")
_MIN = (3, 4, 0)


def _pinned(text: str, pkg: str) -> tuple[int, ...] | None:
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        m = re.match(rf'^{re.escape(pkg)}(\[[^\]]*\])?==([0-9]+(?:\.[0-9]+)*)', s, re.I)
        if m:
            return tuple(int(x) for x in m.group(2).split("."))
    return None


def test_모든_매니페스트에서_python_jose_가_3_4_0_이상이다() -> None:
    검사됨 = 0
    for fn in _MANIFESTS:
        p = _API / fn
        assert p.exists(), f"매니페스트가 없다: {fn} — 이 락은 아무것도 검증하지 않는다"
        ver = _pinned(p.read_text(encoding="utf-8"), "python-jose")
        assert ver is not None, (
            f"{fn} 에서 python-jose 핀을 찾지 못했다. 제거됐거나 표기가 바뀌었다면 "
            "인증 경로를 확인하고 이 락을 갱신하라"
        )
        assert ver >= _MIN, (
            f"{fn}: python-jose {'.'.join(map(str, ver))} 는 **알고리즘 혼동**"
            f"(PYSEC-2024-232)이 있는 대역이다. {'.'.join(map(str, _MIN))} 이상이어야 한다"
        )
        검사됨 += 1
    # ★공허 진리 방지 — 매니페스트를 하나도 안 봤는데 '위반 0'이면 무의미하다.
    assert 검사됨 == len(_MANIFESTS), f"매니페스트 {검사됨}/{len(_MANIFESTS)}개만 검사됐다"


def test_배포_매니페스트와_개발_매니페스트의_인증버전이_같다() -> None:
    """★한쪽만 올리면 **CI 는 초록인데 프로덕션은 취약**한 상태가 된다.
    이 저장소는 실제로 '감사한 매니페스트'와 '배포한 매니페스트'가 갈렸던 적이 있다(#721).
    """
    versions = {fn: _pinned((_API / fn).read_text(encoding="utf-8"), "python-jose") for fn in _MANIFESTS}
    assert len(set(versions.values())) == 1, (
        f"매니페스트마다 python-jose 버전이 다르다 — 한쪽만 취약해진다: {versions}"
    )
