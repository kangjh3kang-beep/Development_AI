#!/usr/bin/env python3
"""추첨 **제3자 검증기** — 운영자를 신뢰하지 않고 결과를 다시 계산한다.

## 쓰는 법

    python3 scripts/verify_draw.py \
        --commit-hash <추첨 전에 공개된 값> \
        --nonce       <추첨 후 공개된 값> \
        --group       <추첨그룹 id> \
        --candidate   <대상자 id> \
        --pool        <그 시점 pool(쉼표 구분 또는 JSON 배열)> \
        --expect      <실제 배정된 세대 id>

## ★이 도구가 하는 것과 하지 않는 것

  한다      ①`sha256(nonce) == commit_hash` — 공약이 지켜졌나
            ②그 nonce·pool 로 **같은 세대가 나오는가** — 결과가 조작되지 않았나
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
    key = _seed_key(a.nonce, a.group, a.candidate)
    domain = f"dongho:{a.group}:{a.candidate}"
    idx, _nxt = _below(key, domain, len(pool))
    got = pool[idx]
    print(f"  pool {len(pool)}건 · 도메인 {domain}")
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
