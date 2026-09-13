"""검증 가능한 난수(VRNG) — **추첨 결과를 제3자가 재현할 수 있게** 만드는 최소 도구.

## ★적용 범위 — **이 모듈은 아직 ①(청약 당첨자 추첨)에만 배선돼 있다**

솔직하게 적는다(독립 리뷰 M-3):

  · ①`subscription/engine.py::run_draw` — **`seed_key`·`verify_commitment` 만** 쓴다.
  · ②`draw/draw_engine.py::draw_for_candidate`(**동·호 즉석추첨**) — **아직 이 모듈을 안 쓴다.**
    `random.Random(secrets.token_hex(8)).choice(...)` 가 그대로 살아 있고 pool 해시도
    **64비트로 절단**된 채다.
  · 그래서 `below`·`pick`·`shuffle` 은 지금 **테스트만 부른다**(프로덕션 소비처 0).

★***계획서가 ②를 「주 사용처」라 불렀는데 고친 것은 ①이다.*** 이 사실을 여기 적어 두지 않으면
  다음 사람이 「동·호 추첨에 VRNG 가 적용됐다」로 읽는다 — **그것이 허위 완결성이다.**
  ②의 전환은 별도 작업이고, 그 부채는 `test_draw_engine_still_unmigrated.py` 가
  **초록 안에서 보이게**(xfail) 들고 있다.

## 왜 `random.Random` 을 쓰지 않는가 (실측 2026-09-13)

①의 종전 seed 유도와 ②의 세대 선택은 모두 파이썬 표준 `random` 계열에 기대고 있었다.
②는 `random.Random(seed).choice(sorted(pool))` 다(**현재도 그렇다** — 위 적용 범위 참조). 그 방식의 문제는
«무작위성» 이 아니라 **재현 가능성**이다:

  · `random.Random(str)` 의 시딩은 **CPython 구현 세부**다(문자열 → sha512 → 정수).
  · `choice` 는 `_randbelow_with_getrandbits` 를 쓰고 그 내부도 구현 세부다.
  ⇒ **파이썬 버전이 바뀌면 같은 seed 가 다른 결과**를 낼 수 있고, **파이썬이 아닌 도구로는
    아예 재현할 수 없다.** 추첨 감사자가 우리 런타임을 신뢰해야 한다면 그건 감사가 아니다.

여기서는 **HMAC-SHA256** 만 쓴다. 어떤 언어·어떤 버전에서도 같은 값이 나오고,
검증자는 파이썬 없이 `openssl`·자바스크립트·엑셀 매크로로도 재현할 수 있다.

## 편향 — modulo 를 쓰지 않는다

`int(digest, 16) % n` 은 **모듈로 편향**을 만든다(2^256 이 n 으로 나누어떨어지지 않으므로
앞쪽 인덱스가 미세하게 유리하다). 세대 수가 적으면 무시할 만하지만 ***「무시할 만하다」는
공정성 주장을 하는 자리에서 할 말이 아니다.*** 그래서 **거부 표집(rejection sampling)** 을 쓴다:
범위를 n 의 배수로 잘라 그 밖의 값은 **버리고 다음 카운터로** 넘어간다.

## 도메인 분리

같은 seed 로 「세대 선택」과 「순번 배정」을 하면 두 결과가 **상관**된다.
`domain` 문자열로 스트림을 갈라 그런 결합을 막는다.
"""
from __future__ import annotations

import hashlib
import hmac

#: 한 번의 뽑기에서 허용하는 최대 재시도(거부 표집). 2^32 범위에서 n ≤ 2^31 이면
#: 한 번에 실패할 확률이 1/2 미만이라, 64회 연속 실패 확률은 2^-64 이하다.
#: ★그런데도 상한을 두는 이유: 무한 루프를 **원리적으로** 막기 위해서다(상한이 없으면
#:   버그가 생겼을 때 추첨이 응답하지 않는다). 상한에 닿으면 **조용히 값을 내지 않고 예외**다.
_MAX_TRIES = 64

#: nonce 최소 길이(바이트). ★**공약을 사전 공개하는 모델에서는 nonce 가 곧 비밀**이라
#:   짧으면 commit 으로부터 **전수탐색**이 가능하다(독립 리뷰 D-2: `"00"` 도 검증을 통과했다).
_MIN_NONCE_BYTES = 32

#: ★**변이 생존 기록**(2026-09-13 기계 감사 · 23변이/생존 5 → 보강 후 4).
#:   남은 생존 넷은 전부 **예외 메시지 문구**다(`below` 의 두 ValueError · `RuntimeError` 두 줄).
#:   **구멍이 아니다** — 계약은 «예외를 던진다」이지 그 문장의 철자가 아니고, 문구를 단언하면
#:   다듬을 때마다 깨지는 취약한 락이 된다. 예외 **발생 자체**는 락이 태운다.
#:   ★다섯 번째 생존은 **진짜 구멍이었다**: `ordered = sorted(items)` → `ordered = 0,`(튜플)로
#:     바꿔도 초록이었다 — 내 락이 «두 입력 순서의 결과가 같다」만 보고 **뽑힌 값이 입력에서
#:     왔는가**를 안 봤기 때문이다(둘 다 `0` 이면 같다). 소속·도달범위 단언을 추가해 닫았다.

#: 한 카운터가 만드는 난수의 비트 폭. HMAC-SHA256 출력 앞 4바이트를 쓴다.
_BITS = 32
_LIMIT = 1 << _BITS


def _block(key: bytes, domain: str, counter: int) -> int:
    """`HMAC-SHA256(key, "<domain>:<counter>")` 의 **앞 4바이트**를 정수로.

    ★검증자가 재현할 형태를 여기 적는다(이 주석이 곧 감사 사양이다):

        printf 'draw:0' | openssl dgst -sha256 -mac HMAC -macopt hexkey:<KEY_HEX> -hex

    메시지는 `f"{domain}:{counter}"` 의 **UTF-8 바이트**이고 **개행을 붙이지 않는다**
    (그래서 `echo` 가 아니라 `printf` 다 — `<<<` 는 개행을 붙이고 인자를 **파일명으로** 읽는다).
    ★2026-09-13 정정: 종전에 적어 둔 `openssl … <<< -n "draw:0"` 은 **실행되지 않는다**
      (`draw:0: No such file or directory`). ***「감사 사양」이라 선언해 놓고 그 명령을 한 번도
      돌려 보지 않았다*** — 그래서 아래 락이 **이 주석의 명령을 그대로 셸에 태운다.**
    """
    msg = f"{domain}:{counter}".encode()
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    return int.from_bytes(digest[:4], "big")


def below(key: bytes, domain: str, n: int, *, start: int = 0) -> tuple[int, int]:
    """`[0, n)` 에서 **편향 없이** 하나를 뽑는다. 반환 `(값, 다음 카운터)`.

    `start` 는 카운터 시작값 — 같은 key·domain 으로 **연속해서** 뽑을 때 이전 반환값을
    그대로 넘기면 스트림이 이어진다(같은 값을 두 번 뽑지 않는다).

    ★`n <= 0` 은 **예외**다. 0을 돌려주면 «뽑을 것이 없었다」가 «0번을 뽑았다」로 읽힌다.
    """
    if n <= 0:
        raise ValueError(f"뽑을 대상이 없다(n={n}) — 이 자리에서 값을 지어내지 않는다")
    if n > _LIMIT:
        raise ValueError(f"대상이 {_BITS}비트 범위를 넘는다(n={n}) — 구현을 넓혀야 한다")
    # 거부 표집: 범위를 n 의 배수로 잘라 그 밖은 버린다(모듈로 편향 제거).
    bound = _LIMIT - (_LIMIT % n)
    counter = start
    for _ in range(_MAX_TRIES):
        v = _block(key, domain, counter)
        counter += 1
        if v < bound:
            return v % n, counter
    raise RuntimeError(
        f"거부 표집이 {_MAX_TRIES}회 연속 실패했다(n={n}) — 확률적으로 불가능에 가깝다. "
        "구현 결함을 의심하라(조용히 편향된 값을 내지 않는다)"
    )


def pick(key: bytes, domain: str, items: list[str], *, start: int = 0) -> tuple[str, int]:
    """정렬된 목록에서 하나를 뽑는다. 반환 `(항목, 다음 카운터)`.

    ★**호출부가 정렬해서 넘긴다**고 가정하지 않는다 — 여기서 정렬한다.
      입력 순서가 결과를 바꾸면 «명부를 어떻게 넣었는가」가 추첨에 영향을 준다.
    """
    ordered = sorted(items)
    idx, nxt = below(key, domain, len(ordered), start=start)
    return ordered[idx], nxt


def shuffle(key: bytes, domain: str, items: list[str], *, start: int = 0) -> tuple[list[str], int]:
    """정렬된 목록을 **재현 가능하게** 섞는다(Fisher–Yates). 반환 `(순서, 다음 카운터)`.

    추첨 **순번(seq)** 배정에 쓴다 — 종전에는 `MAX(seq)+1`, 즉 **등록 순서**가 곧 순번이라
    먼저 등록한 쪽이 더 많은 선택지를 봤다.
    """
    out = sorted(items)
    counter = start
    for i in range(len(out) - 1, 0, -1):
        j, counter = below(key, domain, i + 1, start=counter)
        out[i], out[j] = out[j], out[i]
    return out, counter


def seed_key(nonce_hex: str, *contributions: str) -> bytes:
    """추첨 키를 만든다 — 서버 nonce 에 **다른 기여값들을 섞는다**.

    ★서버 nonce 단독으로 키가 결정되면 **서버가 단독으로 결과를 정한다**.
      명부 해시·외부 비콘 같은 기여값을 섞으면 어느 한쪽도 혼자 정하지 못한다.
      (Phase 1 에서 비콘을 붙인다. 지금은 명부 해시만 섞여도 «서버가 명부 확정 전에
       결과를 고를 수 없다」가 성립한다.)

    기여값은 **주어진 순서대로** 이어 붙인다 — 순서가 바뀌면 다른 키다(그래서 호출부가
    순서를 고정하고, 검증 사양에도 그 순서를 적는다).
    """
    material = ":".join(contributions).encode()
    return hmac.new(bytes.fromhex(nonce_hex), material, hashlib.sha256).digest()


def commitment(nonce_hex: str) -> str:
    """공약값 — 추첨 **전에** 공개하고, 추첨 **후에** nonce 를 밝혀 대조한다.

    이것이 없으면 서버는 뽑아 보고 마음에 안 들면 다시 뽑을 수 있고(**grinding**),
    원장에는 **성공한 seed 하나만** 남아 그 사실이 보이지 않는다.
    """
    return hashlib.sha256(bytes.fromhex(nonce_hex)).hexdigest()


def is_strong_nonce(nonce_hex: str) -> bool:
    """nonce 가 **전수탐색을 버틸 만큼** 긴가(그리고 16진인가).

    ★독립 리뷰 D-2 실측: 종전에는 `draw_nonce="00"`(8비트)도 공약 검증을 통과했다.
      공약을 미리 공개하는 모델에서 그건 **commit 에서 nonce 를 되찾을 수 있다**는 뜻이고,
      그러면 추첨 전에 결과가 계산된다 — 이 모듈이 없애려던 바로 그 성질이다.
    """
    s = (nonce_hex or "").strip()
    if len(s) % 2 or len(s) < _MIN_NONCE_BYTES * 2:
        return False
    try:
        bytes.fromhex(s)
    except ValueError:
        return False
    return True


def verify_commitment(nonce_hex: str, commit_hex: str) -> bool:
    """공약 검증. ★`==` 가 아니라 `compare_digest` — 타이밍 차이로 정보를 흘리지 않는다.

    ★**약한 nonce 는 검증 이전에 거부**한다 — 해시가 맞아도 그 nonce 로는 공정성이 성립하지 않는다.
    """
    if not is_strong_nonce(nonce_hex):
        return False
    return hmac.compare_digest(commitment(nonce_hex), (commit_hex or "").lower())
