#!/usr/bin/env python3
"""추첨 **제3자 검증기** — 운영자를 신뢰하지 않고 결과를 다시 계산한다.

## 쓰는 법

    python3 scripts/verify_draw.py \
        --commit-hash <추첨 전에 공개된 값> \
        --nonce       <추첨 후 공개된 값> \
        --group       <추첨그룹 id> \
        --candidate   <대상자 id> \
        --pool        <그 시점 pool(쉼표 구분 또는 JSON 배열)> \
        --expect      <실제 배정된 세대 id> \
        --beacon-round <공약에 못 박힌 drand 라운드(공개값)> \
        --participants-hash <공약이 묶은 명부 지문> \
        --pool-hash         <공약이 묶은 대상 세대 지문> \
        --start-counter     <추첨 응답의 start_counter · 기본 0>

## ★이 도구가 하는 것과 하지 않는 것

  한다      ①`sha256(nonce) == commit_hash` — 공약이 지켜졌나
            ②그 nonce·pool 로 **같은 세대가 나오는가** — 결과가 조작되지 않았나
            ③`--beacon-round` 를 주면 **그 라운드를 직접 drand 에서 가져와**(서로 다른 운영자
              2곳 대조) seed 에 섞는다 — ***이 값은 운영자가 만들지 않았고 공약 시점엔 세상에
              없었다.*** 즉 이 검증은 운영자가 준 자료만으로 닫히지 않는다.
  하지 않는다 **공약이 추첨보다 앞섰는지는 증명하지 못한다.** 그건 공약 게시 시각
            (`GET …/commitment` 의 `committed_at`)을 **추첨 전에 받아 둔 사람**만 말할 수 있다.
            ⇒ 대상자·입회인은 **추첨 전에 `commit_hash` 를 받아 두라.**

★이 파일은 표준 라이브러리만 쓴다 — 검증자가 이 저장소를 설치하지 않아도 돌아간다.
  같은 계산을 `openssl` 로도 할 수 있다(아래 `--show-openssl`).
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import urllib.request

_BITS = 32
_LIMIT = 1 << _BITS
_MAX_TRIES = 64
_MIN_NONCE_BYTES = 32


def _block(key: bytes, domain: str, counter: int) -> int:
    return int.from_bytes(
        hmac.new(key, f"{domain}:{counter}".encode(), hashlib.sha256).digest()[:4], "big")


def _below(key: bytes, domain: str, n: int, start: int = 0) -> tuple[int, int]:
    if n <= 0:
        raise ValueError(f"뽑을 대상이 없다(n={n})")
    bound = _LIMIT - (_LIMIT % n)
    counter = start
    for _ in range(_MAX_TRIES):
        v = _block(key, domain, counter)
        counter += 1
        if v < bound:
            return v % n, counter
    raise RuntimeError("거부 표집 연속 실패 — 구현 결함")


#: ★**프로덕션 `app/services/sales/draw/beacon.py` 의 복제본**이다. 이 파일은 저장소를 설치하지
#:   않은 제3자가 돌려야 해서 임포트할 수 없다 — **의도적 중복**이다.
#:   그래서 `tests/test_draw_verifier_agrees_with_production.py` 가 **두 구현이 같은 문자열을
#:   만드는지** 잠근다. 이 형식이 갈리면 검증기는 *"결과가 다르다"* 고 말하는데, 실제로 다른 것은
#:   **결과가 아니라 내 기여값 문자열**이다 — ***가장 나쁜 종류의 거짓 신고다.***
_BEACON_ENDPOINTS = ("https://api.drand.sh", "https://drand.cloudflare.com")
_UA = "propai-draw-verifier/1.0 (+fairness-audit)"
#: drand 기본 체인의 해시 — ★URL 에 박아 「조용한 체인 교체」를 막는다(프로덕션과 동일해야 한다).
_CHAIN_HASH = "8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce"


def operator_of(base: str) -> str:
    """엔드포인트 → 운영자. ★프로덕션 `beacon.operator_of` 와 **같은 규칙**이어야 한다 —
    「2곳」이 아니라 **「서로 다른 운영자 2곳」**이 대조의 정의다(같은 운영자 예비는 대조가 아니다)."""
    return "cloudflare" if "cloudflare" in base else "drand.sh"


def _beacon_randomness(rnd: int) -> str:
    """라운드를 **서로 다른 운영자 2곳**에서 가져와 대조한다. 갈리거나 한쪽뿐이면 **거부**."""
    got: dict[str, str] = {}
    errors: list[str] = []
    for base in _BEACON_ENDPOINTS:
        try:
            req = urllib.request.Request(f"{base}/{_CHAIN_HASH}/public/{rnd}", headers={"User-Agent": _UA})
            # 고정 https 목록만 부른다(사용자 입력 URL 아님).
            with urllib.request.urlopen(req, timeout=12) as r:
                d = json.loads(r.read().decode())
            if int(d["round"]) != rnd:
                errors.append(f"{base}: 다른 라운드({d.get('round')})")
                continue
            got[base] = str(d["randomness"]).lower()
        except Exception as exc:                                 # noqa: BLE001
            errors.append(f"{base}: {type(exc).__name__}")
    operators = {operator_of(b) for b in got}
    if len(operators) < 2:
        raise RuntimeError(
            f"라운드 {rnd} 를 **서로 다른 운영자 2곳**에서 못 가져왔다"
            f"(성공 {len(got)}곳 · 운영자 {sorted(operators)}) — 사유 {errors}")
    if len(set(got.values())) != 1:
        raise RuntimeError(f"라운드 {rnd} 의 값이 엔드포인트마다 다르다: {got}")
    return next(iter(got.values()))


def beacon_contribution(rnd: int, randomness: str) -> str:
    """seed 에 섞이는 기여값 문자열. ★프로덕션 `beacon.seed_contributions` 와 **같아야** 한다."""
    return f"drand:{int(rnd)}:{randomness}"


def dongho_contributions(group: str, candidate: str, participants_hash: str,
                         pool_hash: str, beacon_part: str | None) -> list[str]:
    """★기여값의 **순서**까지 포함한 정본. 프로덕션 `draw_engine.draw_for_candidate` 와 같아야 한다.

    ***순서가 바뀌면 다른 키다.*** 문자열만 맞추고 **위치**를 안 잠그면, 검증기가 정직한 추첨을
    **「결과가 다르다」= 조작 의심**으로 신고한다(독립 적대 리뷰 2026-09-13 실측 — `append` 를
    `insert(0, …)` 로 바꾼 변이가 **생존**했고 정직한 추첨이 `u-03` → `u-13` 으로 갈렸다).
    ***정직한 추첨을 조작으로 신고하는 것이 이 도구가 낼 수 있는 가장 나쁜 거짓이다.***
    """
    parts = [group, candidate, participants_hash, pool_hash]
    if beacon_part is not None:
        parts.append(beacon_part)
    return parts


def _seed_key(nonce_hex: str, *contributions: str) -> bytes:
    return hmac.new(bytes.fromhex(nonce_hex), ":".join(contributions).encode(),
                    hashlib.sha256).digest()


def main() -> int:
    ap = argparse.ArgumentParser(description="동·호 추첨 제3자 검증기")
    ap.add_argument("--commit-hash", required=True)
    ap.add_argument("--nonce", required=True)
    ap.add_argument("--group", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--pool", required=True, help="쉼표 구분 또는 JSON 배열")
    ap.add_argument("--expect", required=True, help="실제 배정된 세대 id")
    ap.add_argument("--participants-hash", required=True,
                    help="GET …/commitment 의 participants_hash(공약이 묶은 명부 지문)")
    ap.add_argument("--pool-hash", required=True,
                    help="GET …/commitment 의 pool_hash(공약이 묶은 대상 세대 지문)")
    ap.add_argument("--start-counter", type=int, default=0,
                    help="추첨 응답·원장의 start_counter — ★선점 경합이 있었으면 0 이 아니다")
    ap.add_argument("--beacon-round", type=int, default=None,
                    help="공약에 못 박힌 drand 라운드(GET …/commitment 의 beacon_round)")
    ap.add_argument("--beacon-randomness", default=None,
                    help="그 라운드의 값을 직접 주면 **네트워크 없이** 계산한다(오프라인 검증)")
    ap.add_argument("--show-openssl", action="store_true", help="같은 계산의 openssl 명령을 찍는다")
    a = ap.parse_args()

    ok = True

    # ① 공약 — 이것이 깨지면 나머지는 볼 필요가 없다
    if len(a.nonce) < _MIN_NONCE_BYTES * 2:
        print(f"✘ nonce 가 너무 짧다({len(a.nonce)//2}바이트 < {_MIN_NONCE_BYTES}) — "
              "공약에서 전수탐색이 가능하다")
        ok = False
    actual = hashlib.sha256(bytes.fromhex(a.nonce)).hexdigest()
    if not hmac.compare_digest(actual, a.commit_hash.lower()):
        print(f"✘ 공약 불일치\n    공개된 공약 {a.commit_hash}\n    nonce 의 해시 {actual}")
        return 1
    print(f"✔ 공약 일치 — sha256(nonce) = {actual}")

    # ② 결과 재현
    raw = a.pool.strip()
    pool = json.loads(raw) if raw.startswith("[") else [s.strip() for s in raw.split(",")]
    pool = sorted(x for x in pool if x)
    # ★비콘 기여값 — **조용히 빼지 않는다.** 빼고 계산하면 결과가 안 맞는데, 그때 이 도구는
    #   *"결과가 다르다"*(= 조작 의심)라고 말하게 된다. 실제 원인은 **내가 입력을 덜 넣은 것**이다.
    beacon_part: str | None = None
    if a.beacon_round is not None:
        if a.beacon_randomness:
            value = a.beacon_randomness.lower()
            print(f"  비콘 라운드 {a.beacon_round} — ★**직접 조회하지 않고 주어진 값을 썼다**"
                  "(오프라인). 이 값이 옳은지는 이 실행이 증명하지 않는다")
        else:
            try:
                value = _beacon_randomness(a.beacon_round)
            except RuntimeError as exc:
                print(f"✘ 비콘을 신뢰할 수 있게 가져오지 못했다 — {exc}")
                print("   ★비콘 없이 계산하면 결과가 어긋나는데, 그것은 조작이 아니라 **입력 부족**이다. "
                      "그래서 진행하지 않는다")
                return 2
            print(f"  비콘 라운드 {a.beacon_round} = {value[:32]}… (운영자 2곳 대조 통과)")
        beacon_part = beacon_contribution(a.beacon_round, value)
    else:
        print("  ★`--beacon-round` 가 없다 — **비콘을 섞지 않고** 계산한다. 그 추첨이 비콘을 썼다면 "
              "결과가 일부러 어긋난다(`GET …/commitment` 의 `beacon_round` 를 확인하라)")
    parts = dongho_contributions(a.group, a.candidate, a.participants_hash,
                                 a.pool_hash, beacon_part)
    key = _seed_key(a.nonce, *parts)
    domain = f"dongho:{a.group}:{a.candidate}"
    # ★`--start-counter` — 프로덕션은 선점 경합 시 카운터를 **이어받는다**. 0 으로 고정하면
    #   **경합이 있던 정직한 추첨**을 조작으로 신고한다(리뷰 MED-5 실측).
    idx, _nxt = _below(key, domain, len(pool), start=a.start_counter)
    got = pool[idx]
    print(f"  pool {len(pool)}건 · 도메인 {domain} · 시작 카운터 {a.start_counter}")
    print(f"  재계산 결과 = {got}")
    if got != a.expect:
        print(f"✘ **결과가 다르다** — 기록된 배정 {a.expect}")
        ok = False
    else:
        print(f"✔ 결과 일치 — {got}")

    if a.show_openssl:
        print("\n같은 계산을 openssl 로:")
        print(f"  printf '{domain}:0' | openssl dgst -sha256 -mac HMAC "
              f"-macopt hexkey:{key.hex()} -hex")

    print("\n★이 도구는 「공약이 추첨보다 앞섰는지」는 증명하지 못한다 — "
          "그건 추첨 전에 commit_hash 를 받아 둔 사람만 말할 수 있다.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
