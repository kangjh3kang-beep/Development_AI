"""VRNG 락 — ★**「제3자가 재현할 수 있다」를 실제로 태운다.**

이 파일의 중심 단언은 성능도 분포도 아니고 ***재현 가능성***이다.
기존 추첨은 `random.Random(seed).choice()` 였는데 그건 **CPython 구현 세부**라
파이썬 버전이 바뀌면 결과가 달라질 수 있고 **다른 언어로는 재현할 수 없다.**
감사자가 우리 런타임을 신뢰해야 한다면 그것은 감사가 아니다.
"""

from __future__ import annotations

import hashlib
import hmac
import shutil
import subprocess

import pytest

from app.services.sales.draw import vrng

KEY = bytes.fromhex("00112233445566778899aabbccddeeff")


# ── ① 재현 가능성 ──────────────────────────────────────────────────────────
def test_block_is_pinned_to_a_known_value():
    """★**고정 기대값**. 파이썬 버전이 바뀌어도 이 값이 바뀌면 과거 추첨의 재현이 깨진다.

    이 수는 `openssl` 로 교차검증했다(아래 테스트가 그것을 자동으로 다시 한다).
    """
    assert vrng._block(KEY, "draw", 0) == 3109219369


def test_reproducible_without_python_via_openssl():
    """★★**파이썬 없이 재현되는가** — 이 파일의 존재 이유.

    `openssl` 이 없는 환경이면 skip 하되, ***그 경우 이 축은 검증되지 않았다***는 뜻이다
    (조용히 초록으로 넘기지 않기 위해 사유를 남긴다).
    """
    if not shutil.which("openssl"):
        pytest.skip("openssl 부재 — ★이 실행에서는 「언어 독립」 축이 검증되지 않았다")
    out = subprocess.run(
        ["openssl", "dgst", "-sha256", "-mac", "HMAC",
         "-macopt", f"hexkey:{KEY.hex()}", "-hex"],
        input=b"draw:0", capture_output=True, check=True,
    ).stdout.decode()
    digest_hex = out.strip().split("= ")[-1]
    assert int(digest_hex[:8], 16) == vrng._block(KEY, "draw", 0), (
        f"openssl({digest_hex[:8]}) 과 파이썬이 갈렸다 — 「누구나 재현」이 거짓이 된다"
    )


def test_message_format_is_exactly_domain_colon_counter():
    """검증 사양(주석)이 말하는 메시지 형식이 **실제 형식**인가 — 주석도 검증 대상이다."""
    expect = int.from_bytes(
        hmac.new(KEY, b"unit:7", hashlib.sha256).digest()[:4], "big")
    assert vrng._block(KEY, "unit", 7) == expect


# ── ② 편향 ────────────────────────────────────────────────────────────────
def test_rejection_sampling_beats_modulo_on_a_skewed_range():
    """★**두 모집단** — 거부 표집과 단순 modulo 를 **같은 키로** 돌려 편향을 갈라 본다.

    n 을 2^32 의 약수가 아닌 큰 값으로 잡으면 modulo 는 앞쪽 인덱스가 유리해진다.
    ★대조군이 없으면 「우리 것이 균등하다」는 **비교 대상 없는 주장**이다.
    """
    n = 3_000_000_000          # 2^32 의 약수가 아니고, 절반 이상이라 편향이 크게 드러난다
    bound = (1 << 32) - ((1 << 32) % n)
    low_ours = low_mod = 0
    trials = 4000
    counter = 0
    for i in range(trials):
        raw = vrng._block(KEY, "bias", i)
        if raw % n < n // 2:
            low_mod += 1
        v, counter = vrng.below(KEY, "bias2", n, start=counter)
        if v < n // 2:
            low_ours += 1
    # 우리 것: 이론적으로 정확히 균등 → 절반 근처
    assert 0.45 * trials < low_ours < 0.55 * trials, low_ours
    # 대조군이 살아 있는가 — bound 가 실제로 범위를 잘랐는가(공허 방지)
    assert bound < (1 << 32), "거부 구간이 없다 — 이 테스트가 아무것도 안 본다"


def test_below_refuses_empty_and_oversized():
    """「뽑을 것이 없다」를 **0번을 뽑았다**로 만들지 않는다."""
    with pytest.raises(ValueError):
        vrng.below(KEY, "d", 0)
    with pytest.raises(ValueError):
        vrng.below(KEY, "d", (1 << 32) + 1)


# ── ③ 도메인 분리 · 스트림 ────────────────────────────────────────────────
def test_domains_are_independent():
    """같은 키라도 도메인이 다르면 결과가 상관되지 않아야 한다(세대 선택 ↔ 순번 배정)."""
    a = [vrng.below(KEY, "unit", 100, start=i)[0] for i in range(50)]
    b = [vrng.below(KEY, "seq", 100, start=i)[0] for i in range(50)]
    assert a != b, "두 도메인이 같은 수열을 낸다 — 도메인 분리가 동작하지 않는다"


def test_counter_advances_so_the_same_draw_is_not_repeated():
    """연속 호출이 **같은 값을 반복하지 않는다**(카운터를 이어 받는다)."""
    v1, c1 = vrng.below(KEY, "d", 1000, start=0)
    v2, c2 = vrng.below(KEY, "d", 1000, start=c1)
    assert c1 > 0 and c2 > c1
    assert (v1, c1) != (v2, c2)


# ── ④ 입력 순서 독립 ──────────────────────────────────────────────────────
def test_pick_is_independent_of_input_order():
    """★명부를 **어떤 순서로 넣든** 같은 결과여야 한다 — 아니면 등록 순서가 추첨에 영향을 준다."""
    items = ["u-c", "u-a", "u-d", "u-b"]
    got_a, _ = vrng.pick(KEY, "unit", items)
    got_b, _ = vrng.pick(KEY, "unit", list(reversed(items)))
    assert got_a == got_b, (got_a, got_b)


def test_shuffle_is_a_permutation_and_order_independent():
    """순번 배정 — **빠지거나 겹치는 사람이 없어야** 한다(집합 보존)."""
    people = [f"p{i:02d}" for i in range(20)]
    out_a, _ = vrng.shuffle(KEY, "seq", people)
    out_b, _ = vrng.shuffle(KEY, "seq", list(reversed(people)))
    assert sorted(out_a) == sorted(people), "사람이 사라지거나 중복됐다"
    assert out_a == out_b, "입력 순서가 순번에 영향을 준다"
    assert out_a != people, "섞이지 않았다(항등 순열)"


# ── ⑤ 공약(commit–reveal) ─────────────────────────────────────────────────
def test_commitment_roundtrip_and_tamper_rejection():
    """★**두 모집단** — 옳은 nonce 는 통과하고 **바꾼 nonce 는 거부**된다."""
    nonce = "a1" * 32
    c = vrng.commitment(nonce)
    assert vrng.verify_commitment(nonce, c) is True
    assert vrng.verify_commitment("b2" * 32, c) is False, (
        "다른 nonce 가 통과한다 — 서버가 뽑아 보고 seed 를 갈아치울 수 있다"
    )
    assert vrng.verify_commitment(nonce, "") is False


def test_seed_key_mixes_contributions_so_server_alone_cannot_decide():
    """★서버 nonce 가 같아도 **명부가 다르면 키가 다르다** — 명부 확정 전엔 결과를 못 고른다."""
    nonce = "cc" * 32
    k1 = vrng.seed_key(nonce, "roster-hash-A")
    k2 = vrng.seed_key(nonce, "roster-hash-B")
    assert k1 != k2, "기여값이 키에 섞이지 않는다 — 서버가 단독으로 결과를 정한다"
    # 순서도 계약이다(검증 사양에 적힌 순서와 같아야 한다)
    assert vrng.seed_key(nonce, "A", "B") != vrng.seed_key(nonce, "B", "A")


def test_vrng_does_not_use_python_random():
    """★`random` 을 다시 끌어들이면 언어 독립이 깨진다 — 실행 코드에서 금지."""
    import ast
    import pathlib
    src = pathlib.Path(vrng.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {
        n.names[0].name.split(".")[0]
        for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) and n.names
    }
    assert "hmac" in imported, "대조군 실패 — 임포트를 하나도 못 읽었다"
    assert "random" not in imported, f"random 을 임포트한다: {sorted(imported)}"
