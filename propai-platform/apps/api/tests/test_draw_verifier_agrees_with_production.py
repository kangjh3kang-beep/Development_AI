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
                p_hash: str, u_hash: str, start: int = 0) -> str:
    key = vrng.seed_key(nonce, group, cand, p_hash, u_hash)
    got, _ = vrng.pick(key, f"dongho:{group}:{cand}", pool, start=start)
    return got


def _verifier(nonce: str, group: str, cand: str, pool: list[str], expect: str,
              p_hash: str, u_hash: str, start: int = 0):
    return subprocess.run(
        [sys.executable, str(_VERIFIER),
         "--commit-hash", vrng.commitment(nonce), "--nonce", nonce,
         "--group", group, "--candidate", cand,
         "--pool", json.dumps(pool), "--expect", expect,
         "--participants-hash", p_hash, "--pool-hash", u_hash,
         "--start-counter", str(start)],
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
    # ★시작 카운터도 **0 이 아닌 값**을 섞어 태운다 — 선점 경합이 있던 정직한 추첨을
    #   검증기가 「조작」으로 신고하던 자리다(리뷰 MED-5).
    start = n % 3
    expected = _production(nonce, group, cand, pool, p_hash, u_hash, start)
    out = _verifier(nonce, group, cand, pool, expected, p_hash, u_hash, start)
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
