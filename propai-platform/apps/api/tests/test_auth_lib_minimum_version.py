"""인증 라이브러리를 **취약한 버전으로 되돌리지 못하게** 잠근다.

`python-jose 3.3.0` 에는 `PYSEC-2024-232` — **알고리즘 혼동**(OpenSSH ECDSA 키 등
다른 키 형식과의 혼동)이 있다. 이건 DoS 가 아니라 **인증 우회 계열**이다.
이 저장소의 인증은 전부 `from jose import jwt` 를 쓰므로 직격이다.

★종전에 이 자리에 적혀 있던 것: *"`python-jose 3.4.0` 은 `pyasn1<0.5.0` 을 요구하고
  그 대역(0.4.8)에는 DoS 4건이 있다. pyasn1 수정본은 0.6.x 라 **제약상 올릴 수 없다**."*
  당시 판단(인증 우회 > DoS)은 **옳았다.** 그러나 *"올릴 수 없다"* 는 **버전에 매인 사실**이었고
  아무도 다시 재지 않아 `Security Scan` 이 **2026-08-24 이후 상시 빨간 채로** 남았다.

★2026-08-28 재측정 — **그 대가는 이제 치르지 않아도 된다.**

    python-jose 3.4.0 -> pyasn1<0.5.0,>=0.4.1   ⟹ 0.4.8 (PYSEC-2026-2263/3455/3456/3457)
    python-jose 3.5.0 -> pyasn1>=0.5.0          ⟹ 0.6.4 ✅ (pip --dry-run --report 실측)

  ★**`pyasn1==0.6.4` 를 직접 핀하는 처방은 해석 불가다**(3.4.0 의 캡과 충돌한다).
    고칠 자리는 pyasn1 이 아니라 **여기(python-jose)** 였다. 먼저 떠오르는 처방이 아니다.

★그래서 하한은 **3.5.0** 이고, 이유가 **둘**이다 — 3.4.0 미만은 **인증 우회**(PYSEC-2024-232),
  3.5.0 미만은 **pyasn1 DoS 4건**. 되돌리려는 사람은 **둘 다** 되살린다는 뜻이다.

★교훈(이 파일이 스스로 밟았다): **모듈이 자기 근거로 적어 둔 전제도 검증 대상이다.**
  잘 쓰인 설명일수록 결론처럼 읽혀 아무도 다시 재지 않는다.
"""

from __future__ import annotations

import pathlib
import re

_API = pathlib.Path(__file__).resolve().parents[1]
_MANIFESTS = ("requirements.txt", "requirements.oracle.txt")
_MIN = (3, 5, 0)


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
            f"{fn}: python-jose {'.'.join(map(str, ver))} 는 취약 대역이다 — "
            f"3.4.0 미만은 **알고리즘 혼동**(PYSEC-2024-232, 인증 우회), "
            f"3.5.0 미만은 **pyasn1<0.5.0 캡**으로 PYSEC-2026-2263/3455/3456/3457 "
            f"(DoS 4건)을 강제한다. {'.'.join(map(str, _MIN))} 이상이어야 한다"
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


def test_pyasn1_을_직접_핀해서_우회하지_않는다() -> None:
    """★하지 않기로 한 것을 잠근다 — 다음 사람이 **쉬운 길**로 가는 것을 기계가 막는다.

    `Security Scan` 을 초록으로 만드는 가장 빨라 보이는 길은 `pyasn1==0.6.4` 를
    매니페스트에 직접 적는 것이다. 그러면 `python-jose 3.4.0` 의 `pyasn1<0.5.0` 과
    **충돌해 설치가 깨진다**(CI 는 pip-audit 만 보므로 초록으로 보일 수 있다).
    올바른 자리는 python-jose 하한이다.
    """
    검사됨 = 0
    for fn in _MANIFESTS:
        text = (_API / fn).read_text(encoding="utf-8")
        ver = _pinned(text, "pyasn1")
        assert ver is None or ver >= (0, 5, 0), (
            f"{fn}: pyasn1 을 {'.'.join(map(str, ver))} 로 직접 핀했다. "
            "python-jose 하한을 올리는 것이 옳은 자리다(직접 핀은 캡과 충돌한다)"
        )
        검사됨 += 1
    assert 검사됨 == len(_MANIFESTS), f"매니페스트 {검사됨}/{len(_MANIFESTS)}개만 검사됐다"


def test_추출기가_살아있다() -> None:
    """★대조군 — `_pinned` 가 죽으면 위의 「위반 0」이 전부 공허해진다."""
    assert _pinned("python-jose[cryptography]==3.5.0  # 주석", "python-jose") == (3, 5, 0)
    assert _pinned("pyasn1==0.6.4", "pyasn1") == (0, 6, 4)
    # 주석 처리된 줄은 핀이 아니다(주석에 뚫리지 않는지).
    assert _pinned("# python-jose[cryptography]==3.3.0", "python-jose") is None
    # 없는 패키지는 None(있다고 지어내지 않는지).
    assert _pinned("fastapi==0.1.0", "python-jose") is None


def test_하한_자체가_내려가지_않는다() -> None:
    """★`_MIN` 을 낮추는 변이가 **생존**했다(2026-08-28 실측) — 이 락이 그것을 막는다.

    위 테스트들은 *"매니페스트 >= `_MIN`"* 을 볼 뿐이라, `_MIN` 을 (3,4,0) 으로 되돌려도
    매니페스트가 3.5.0 인 동안은 **초록**이다. 즉 **잠근 것은 배선이고 의미는 안 잠겼다** —
    그 상태에서 누가 매니페스트를 3.4.0 으로 내리면 아무도 못 막는다.

    그래서 하한을 **리터럴로 못 박는다.** 내리려면 이 줄을 지워야 하고, 지우려면
    아래 사유를 읽게 된다.

    사유(둘 다 되살아난다):
      · 3.4.0 미만 → PYSEC-2024-232 **알고리즘 혼동(인증 우회)**
      · 3.5.0 미만 → `pyasn1<0.5.0` 캡 → PYSEC-2026-2263/3455/3456/3457 **DoS 4건**
    """
    assert _MIN >= (3, 5, 0), (
        f"python-jose 하한이 {_MIN} 로 내려갔다. 3.5.0 미만은 pyasn1 을 <0.5.0 으로 캡해 "
        "PYSEC-2026-2263/3455/3456/3457 을 되살린다(Security Scan 이 다시 상시 빨개진다)"
    )
    # ★상한도 함께 — 하한만 걸면 반대쪽이 무제한이 된다(경계는 한 쌍이다).
    #   비현실적으로 높은 값을 박아 두면 「존재하지 않는 버전 요구」로 설치가 깨진다.
    assert _MIN < (4, 0, 0), f"하한 {_MIN} 은 존재하지 않는 메이저다 — 설치가 깨진다"
