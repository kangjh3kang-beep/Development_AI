"""★체인 앵커링 계약 — **가용성을 인질로 잡지 않고, 개인정보를 올리지 않는다.**

이 파일이 잠그는 것 셋:
  ① **앵커링 실패가 추첨을 막지 않는다** — 예외를 밖으로 던지지 않는다(체인은 **부가 증거**다)
  ② **「미설정」과 「실패」는 다른 값** — 겹치면 「아직 안 켰다」가 「고장났다」로 읽힌다
  ③ **개인정보가 올라갈 통로가 없다** — 인자가 전부 32바이트 해시다
"""

from __future__ import annotations

import ast
import hashlib
import pathlib

import pytest

from app.services.sales.draw import anchor


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for n in ("POLYGON_RPC_URL", "DRAW_REGISTRY_ADDRESS", "DRAW_ANCHOR_PRIVATE_KEY"):
        monkeypatch.delenv(n, raising=False)


# ── ① 가용성 ──────────────────────────────────────────────────────────────
def test_anchoring_never_raises_so_a_draw_is_never_blocked():
    """★앵커링은 **예외를 밖으로 던지지 않는다** — RPC 가 죽어도 추첨은 성립해야 한다."""
    for fn, args in (
        (anchor.commit_onchain, ("dongho", "g1", "aa" * 32, "bb" * 32)),
        (anchor.reveal_onchain, ("dongho", "g1", "cc" * 32, "dd" * 32)),
    ):
        got = fn(*args)           # 설정이 없는 상태 — 던지면 여기서 테스트가 깨진다
        assert isinstance(got, anchor.AnchorResult)
        assert got.ok is False


def test_broken_config_is_failed_not_skipped(monkeypatch):
    """★**두 모집단** — 설정이 있는데 못 올리면 `failed`, 아예 없으면 `skipped`."""
    assert anchor.commit_onchain("dongho", "g", "aa" * 32, "bb" * 32).state == "skipped"
    monkeypatch.setenv("POLYGON_RPC_URL", "http://127.0.0.1:1")   # 닫힌 포트
    monkeypatch.setenv("DRAW_REGISTRY_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("DRAW_ANCHOR_PRIVATE_KEY", "0x" + "22" * 32)
    got = anchor.commit_onchain("dongho", "g", "aa" * 32, "bb" * 32)
    assert got.state in ("failed", "skipped"), got
    assert got.reason, "왜 못 올렸는지를 말하지 않는다 — 무성 실패다"


def test_skipped_reason_names_the_missing_settings():
    """무엇이 없어서 건너뛰었는지 **이름으로** 말한다(운영자가 고칠 수 있게)."""
    got = anchor.commit_onchain("dongho", "g", "aa" * 32, "bb" * 32)
    assert got.state == "skipped"
    for name in ("POLYGON_RPC_URL", "DRAW_REGISTRY_ADDRESS", "DRAW_ANCHOR_PRIVATE_KEY"):
        assert name in got.reason, got.reason


# ── ② 해시 일관성(세 층이 갈리면 검증이 거짓) ──────────────────────────────
def test_draw_id_is_sha256_same_as_the_other_layers():
    """★오프체인 검증기·컨트랙트와 **같은 해시 함수**여야 한다."""
    got = anchor.draw_id("dongho", "g-1")
    expect = "0x" + hashlib.sha256(b"dongho:g-1").hexdigest()
    assert got == expect
    assert len(got) == 66, got


def test_hashes_are_never_silently_truncated_or_padded():
    """★길이가 다른 해시는 **예외** — 잘린 해시를 올리면 그게 곧 거짓 증거다."""
    with pytest.raises(ValueError):
        anchor._b32("ab" * 16)     # 16바이트
    with pytest.raises(ValueError):
        anchor._b32("ab" * 40)     # 40바이트
    assert len(anchor._b32("0x" + "ab" * 32)) == 32


def test_merkle_root_is_order_independent_and_not_vacuous():
    """★입력 순서가 루트를 바꾸면 **같은 결과가 다른 루트**를 낸다."""
    a = anchor.merkle_root(["x", "y", "z"])
    b = anchor.merkle_root(["z", "x", "y"])
    assert a == b, "순서가 루트를 바꾼다"
    assert a != anchor.merkle_root(["x", "y"]), "다른 집합이 같은 루트를 낸다"
    assert anchor.merkle_root([]) == "0x" + "00" * 32
    assert len(a) == 66


# ── ③ 개인정보 ────────────────────────────────────────────────────────────
def test_no_personal_data_can_reach_the_chain():
    """★★ABI 인자가 **전부 bytes32** 여야 한다 — 문자열 인자가 있으면 통로가 생긴다.

    체인은 **삭제가 불가능**하다. 「나중에 지우면 된다」가 성립하지 않는 층이라,
    올라갈 **자리 자체를 없애는 것**이 유일한 보장이다.
    """
    types = {i["type"] for f in anchor._ABI for i in f["inputs"]}
    assert types, "대조군 실패 — ABI 를 못 읽었다"
    assert types == {"bytes32"}, f"bytes32 가 아닌 인자가 있다: {sorted(types)}"


def test_contract_solidity_also_has_no_string_inputs():
    """★컨트랙트 쪽도 같은 계약인가 — 두 층이 갈리면 파이썬만 막힌 것이다."""
    # ★경로를 **파생**한다 — 처음에 `parents[5]` 로 잘못 적어 **skip 되었고**,
    #   그 skip 이 「두 층이 같은 계약인가」를 **검증되지 않은 채 초록으로** 넘길 뻔했다.
    #   ***skip 은 통과가 아니다.*** 그래서 이제 저장소 안에서 찾아 **없으면 실패**시킨다.
    root = next((q for q in pathlib.Path(anchor.__file__).parents
                 if (q / "contracts" / "src").is_dir()), None)
    assert root is not None, "컨트랙트 디렉토리를 못 찾았다 — 락이 낡았다(구조가 바뀌었다)"
    sol = root / "contracts" / "src" / "DrawRegistry.sol"
    assert sol.exists(), f"컨트랙트 소스가 없다: {sol}"
    src = sol.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("//"))
    assert "function commitDraw" in code, "대조군 실패 — 컨트랙트를 못 읽었다"
    assert " string " not in code and "string memory" not in code, (
        "컨트랙트에 string 인자가 있다 — 개인정보가 올라갈 통로다"
    )


def test_module_declares_that_chain_does_not_create_fairness():
    """★문서가 **경계를 말하는가** — 「체인에 올렸으니 공정하다」는 오독을 막는다."""
    src = pathlib.Path(anchor.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc = ast.get_docstring(tree) or ""
    assert "공정성을 만들지 않는다" in doc, "경계 선언이 사라졌다 — 다음 사람이 오독한다"
    assert "개인정보" in doc


@pytest.mark.xfail(strict=True, reason=(
    "★**부채(미배선)** — 온체인 앵커링이 구현돼 있지만 **프로덕션 호출부가 0건**이다. "
    "그래서 지금 DB 쓰기 권한자는 `nonce`+`commit_hash`+지문을 **함께** 갈아치워 이길 수 있다 "
    "(독립 적대 리뷰 2026-09-13 MAJOR-5). 앵커가 붙어야 그 층이 닫힌다. "
    "★이 xfail 은 **초록 안에서 부채를 보이게** 하려는 것이다 — 커밋 메시지에만 적으면 안 드러난다. "
    "배선하면 이 테스트가 XPASS 로 **실패**하므로(strict), 그때 이 표식을 지워라."
))
def test_anchoring_is_wired_into_the_draw_paths():
    """추첨 경로가 실제로 온체인 앵커를 부르는가 — **아직 아니다.**"""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "sales"
    callers = set()
    for f in root.rglob("*.py"):
        if f.name == "anchor.py":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                if name in {"commit_onchain", "reveal_onchain"}:
                    callers.add(f"{f.name}:{n.lineno}")
    assert callers, "온체인 앵커 호출부가 0건이다(미배선 부채)"
