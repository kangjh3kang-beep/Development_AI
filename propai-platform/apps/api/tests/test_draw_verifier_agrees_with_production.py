"""★**검증기가 프로덕션과 갈리면 「검증 가능」이 거짓이 된다.**

`scripts/verify_draw.py` 는 **의도적인 사본**이다 — 검증자가 이 저장소를 설치하지 않고도
돌릴 수 있어야 하므로 표준 라이브러리만 쓰고 `vrng` 를 임포트하지 않는다.
★그 대가로 **두 구현이 조용히 갈릴 수 있다.** 이 파일이 그 둘을 **같은 입력으로 대조**한다.

이 저장소에는 같은 형태의 선례가 있다 — 「문서에 적힌 프로브를 실제 산출물에 실행해 잠근다」.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from app.services.sales.draw import binding, vrng

_VERIFIER = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "verify_draw.py"


#: ★공약이 묶는 **명부·pool 지문**도 키에 들어간다 — 두 구현이 **같은 순서로** 넣어야 한다.
def _hashes(roster: list[str], pool: list[str]) -> tuple[str, str]:
    return binding.roster_hash(roster), binding.pool_hash(pool)


def _production(nonce: str, group: str, cand: str, pool: list[str],
                p_hash: str, u_hash: str, taken: set[str] | None = None) -> str:
    """프로덕션의 선점-경합 재시도를 그대로 흉내 낸다 — 뽑은 세대가 **이미 남이 가져갔으면**
    카운터를 이어받아 다시 뽑는다(`draw_for_candidate` 의 while 루프와 같은 모양)."""
    taken = taken or set()
    key = vrng.seed_key(nonce, group, cand, p_hash, u_hash)
    counter = 0
    for _ in range(len(pool) + 1):
        got, counter = vrng.pick(key, f"dongho:{group}:{cand}", pool, start=counter)
        if got not in taken:
            return got
    raise AssertionError("pool 전부가 taken — 픽스처 모순")


def _verifier(nonce: str, group: str, cand: str, pool: list[str], expect: str,
              p_hash: str, u_hash: str, taken: set[str] | None = None):
    return subprocess.run(
        [sys.executable, str(_VERIFIER),
         "--commit-hash", vrng.commitment(nonce), "--nonce", nonce,
         "--group", group, "--candidate", cand,
         "--pool", json.dumps(pool), "--expect", expect,
         "--participants-hash", p_hash, "--pool-hash", u_hash,
         "--taken", ",".join(sorted(taken or set()))],
        capture_output=True, text=True, check=False)


def test_verifier_file_exists_and_is_standalone():
    """검증기는 **이 저장소를 설치하지 않고** 돌아야 한다 — `vrng` 임포트 금지."""
    assert _VERIFIER.exists(), f"검증기가 없다: {_VERIFIER}"
    src = _VERIFIER.read_text(encoding="utf-8")
    assert "hmac" in src, "대조군 실패 — 검증기를 못 읽었다"
    assert "from app." not in src and "import app" not in src, (
        "검증기가 저장소 코드를 임포트한다 — 외부 감사자가 못 돌린다"
    )


@pytest.mark.parametrize("n", range(12))
def test_verifier_and_production_agree(n):
    """★**두 구현이 같은 답을 낸다** — 여러 입력으로(한 입력만 맞으면 우연일 수 있다)."""
    nonce = f"{n:02x}" * 32
    group, cand = f"G-{n}", f"C-{n * 7}"
    pool = [f"u-{i}" for i in range(3 + n)]
    roster = [f"cand-{i}" for i in range(2 + n)]
    p_hash, u_hash = _hashes(roster, pool)
    # ★**선점 경합이 있던 추첨도 섞어 태운다** — 정직한 추첨을 검증기가 「조작」으로 신고하던
    #   자리다(R1 MED-5). 그런데 카운터를 **숫자로 받으면** 무엇이든 인증된다(R2 MAJOR-4)
    #   ⇒ 검증기는 **이미 선점된 세대 목록**을 받아 카운터를 **유도**한다.
    taken = set(pool[: n % 3])
    expected = _production(nonce, group, cand, pool, p_hash, u_hash, taken)
    out = _verifier(nonce, group, cand, pool, expected, p_hash, u_hash, taken)
    assert out.returncode == 0, (
        f"검증기가 프로덕션 결과를 재현하지 못한다:\n{out.stdout}\n{out.stderr}"
    )
    assert "결과 일치" in out.stdout, out.stdout


def test_verifier_rejects_a_tampered_result():
    """★**두 모집단** — 틀린 결과를 주면 **거부**해야 한다(항상 통과하면 검증이 아니다)."""
    nonce = "ab" * 32
    pool = ["u-a", "u-b", "u-c", "u-d"]
    p_hash, u_hash = _hashes(["c1", "c2"], pool)
    real = _production(nonce, "G", "C", pool, p_hash, u_hash)
    wrong = next(u for u in pool if u != real)
    out = _verifier(nonce, "G", "C", pool, wrong, p_hash, u_hash)
    assert out.returncode != 0, f"조작된 결과를 통과시켰다:\n{out.stdout}"
    assert "결과가 다르다" in out.stdout, out.stdout


def test_verifier_rejects_a_broken_commitment():
    """공약이 안 맞으면 **결과를 보기 전에** 멈춘다."""
    nonce = "cd" * 32
    out = subprocess.run(
        [sys.executable, str(_VERIFIER), "--commit-hash", "00" * 32, "--nonce", nonce,
         "--group", "G", "--candidate", "C", "--pool", "u-a,u-b", "--expect", "u-a",
         "--participants-hash", "0" * 64, "--pool-hash", "1" * 64],
        capture_output=True, text=True, check=False)
    assert out.returncode != 0
    assert "공약 불일치" in out.stdout, out.stdout


def test_verifier_rejects_a_weak_nonce():
    """짧은 nonce 는 **공약이 맞아도** 거부한다 — 전수탐색이 가능하기 때문이다."""
    weak = "ab" * 8   # 8바이트
    out = subprocess.run(
        [sys.executable, str(_VERIFIER), "--commit-hash", vrng.commitment(weak),
         "--nonce", weak, "--group", "G", "--candidate", "C",
         "--pool", "u-a,u-b", "--expect", "u-a",
         "--participants-hash", "0" * 64, "--pool-hash", "1" * 64],
        capture_output=True, text=True, check=False)
    assert "너무 짧다" in out.stdout, out.stdout


def test_verifier_requires_the_binding_hashes():
    """★공약이 묶은 **명부·pool 지문을 안 주면 돌지 않는다**.

    선택 인자로 두면 *"안 줘도 도는"* 경로가 생기고, 그 실행은 **다른 키**를 계산하면서
    정직한 추첨을 「결과가 다르다」로 신고한다 — ***가장 나쁜 종류의 거짓 신고다.***
    """
    out = subprocess.run(
        [sys.executable, str(_VERIFIER), "--commit-hash", "00" * 32, "--nonce", "ab" * 32,
         "--group", "G", "--candidate", "C", "--pool", "u-a", "--expect", "u-a"],
        capture_output=True, text=True, check=False)
    assert out.returncode != 0, out.stdout
    assert "participants-hash" in (out.stderr + out.stdout), out.stderr[-300:]


def test_verifier_cannot_certify_an_arbitrary_unit():
    """★★**검증기가 아무 세대나 인증해서는 안 된다**(R2 리뷰 MAJOR-4 실측).

    종전에는 `--start-counter` 가 **운영자가 주는 무제한 자유변수**라, 나머지 입력을 정직하게 두고
    그 숫자만 바꿔 **임의의 6개 세대를 전부 「✔ 일치」로 통과**시킬 수 있었다.
    ***거짓 음성을 고치려다 무조건 거짓 양성을 만든 것이다.***

    지금은 카운터를 **유도**한다 — 건너뛴 세대가 전부 `--taken` 에 있어야 한다.
    `--taken` 은 「이미 배정된 세대」라 **원장·화면과 대조 가능한 공개 사실**이고,
    거짓으로 채우면 그 대조에서 드러난다. **아무 데도 대조할 수 없던 숫자와는 다르다.**
    """
    nonce = "9f" * 32
    pool = [f"u-{i:02d}" for i in range(20)]
    roster = [f"c-{i}" for i in range(5)]
    p_hash, u_hash = _hashes(roster, pool)
    real = _production(nonce, "G", "C", pool, p_hash, u_hash)

    certified = []
    for target in pool:
        if target == real:
            continue
        # `--taken` 을 **비운 채** 아무 세대나 주장해 본다 — 전부 거부돼야 한다.
        out = _verifier(nonce, "G", "C", pool, target, p_hash, u_hash, taken=None)
        if out.returncode == 0:
            certified.append(target)
    assert not certified, (
        f"★정직한 답이 {real} 인데 검증기가 {len(certified)}개의 다른 세대를 인증했다: {certified[:5]}"
    )


def test_skipping_must_be_forced_not_chosen():
    """★건너뜀은 **강제된 것**이어야 한다 — `--taken` 밖의 세대를 건너뛰면 거부."""
    nonce = "7c" * 32
    pool = [f"u-{i:02d}" for i in range(12)]
    p_hash, u_hash = _hashes(["c1"], pool)
    first = _production(nonce, "G", "C", pool, p_hash, u_hash)
    second = _production(nonce, "G", "C", pool, p_hash, u_hash, taken={first})
    assert first != second, "픽스처가 두 모집단을 못 만든다"
    # 첫 번째를 taken 으로 **선언하지 않은 채** 두 번째를 주장 → 거부돼야 한다
    out = _verifier(nonce, "G", "C", pool, second, p_hash, u_hash, taken=None)
    assert out.returncode != 0, f"강제되지 않은 건너뜀을 통과시켰다:\n{out.stdout}"
    # 대조군 — 첫 번째가 이미 선점됐다고 **선언하면** 통과한다
    ok = _verifier(nonce, "G", "C", pool, second, p_hash, u_hash, taken={first})
    assert ok.returncode == 0, ok.stdout
