"""제3자 **공개 검증** — nonce 는 언제 열리고, 무엇이 절대 안 나가는가.

## 왜 이 파일이 있나

이 PR 은 *"검증기는 운영자가 자료를 손으로 건네줄 때만 돈다 — 그건 정의상 독립 검증이 아니다"*
라는 지적을 받았고, 한동안 **「제3자 독립 검증」이라는 주장을 철회**한 채로 있었다.
이제 그 손을 없앴다. 그러면 **새로운 위험 둘**이 생긴다:

  ① **너무 일찍 열기** — 진행 중에 nonce 가 나가면 ***남은 대상자의 결과가 즉시 계산된다.***
  ② **너무 많이 열기** — 무인증 경로로 **이름·연락처**가 나가면 되돌릴 수 없다.

이 파일은 그 둘을 잠근다.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib

from app.services.sales.draw import commitment_store as cs

_NONCE = "ab" * 32


class _Row:
    def __init__(self, cols):
        self.cols = cols

    def first(self):
        return self.cols


def _fake_db(*, finalized):
    """공약 1건을 가진 가짜 DB. `finalized` 로 **두 모집단**을 만든다."""
    class _D:
        def __init__(self):
            self.sql: list[str] = []

        async def execute(self, stmt, params=None):
            q = " ".join(str(stmt).split())
            self.sql.append(q)
            if "FROM sales_draw_commitments" in q and q.startswith("SELECT"):
                return _Row((
                    "cc" * 32, "2026-09-13T00:00", None, 900,
                    "p" * 64, "u" * 64, ["c1"], ["u1"],
                    "2026-09-13T01:00" if finalized else None,
                    _NONCE, "rr" * 32,
                    "anchored", "0xtx1", "anchored", "0xtx2",
                ))
            return _Row(None)

        async def commit(self):
            return None

    return _D()


def _get(finalized):
    return asyncio.new_event_loop().run_until_complete(
        cs.public_commitment(_fake_db(finalized=finalized), "dongho", "g1"))


# ── ① ★nonce 는 **끝난 뒤에만** 나간다 (두 모집단) ──────────────────────────
def test_nonce_is_absent_before_finalization():
    got = _get(finalized=False)
    assert got is not None
    assert "nonce" not in got, (
        "★추첨이 끝나기 전에 nonce 가 나간다 — 남은 대상자의 결과가 즉시 계산된다"
    )
    # 공약값 자체는 이때도 나가야 한다(그래야 추첨 **전에** 받아 둘 수 있다)
    assert got["commit_hash"] and got["beacon_round"] == 900


def test_nonce_is_present_after_finalization():
    """대조군 — 끝난 뒤엔 나간다. 안 나가면 **제3자 검증이 성립하지 않는다**
    (검증기가 `--nonce` 를 필수로 요구한다)."""
    got = _get(finalized=True)
    assert got.get("nonce") == _NONCE, got.keys()


def test_absence_is_absence_not_an_empty_string():
    """★빈 문자열로 두면 소비처가 «공개됐는데 값이 없다»로 오독한다 — **키 자체가 없어야** 한다."""
    got = _get(finalized=False)
    assert "nonce" not in got
    assert got["finalized_at"] is None


# ── ② ★공개 엔드포인트로 **개인정보가 나가지 않는다** ───────────────────────
def test_verification_bundle_never_selects_personal_columns():
    """★`name`·`phone` 을 **애초에 조회하지 않는다** — 나중에 지우는 것보다 안 읽는 것이 낫다.

    소스를 **AST 로** 본다(주석에 적힌 컬럼명에 속지 않기 위해).
    """
    src = inspect.getsource(cs.verification_bundle)
    literals = [n.value for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    sql = " ".join(x for x in literals if "SELECT" in x.upper())
    assert sql, "대조군 실패 — 조회문을 하나도 못 읽었다"
    for bad in ("name", "phone", "phone_e164", "customer_id"):
        assert bad not in sql.lower(), f"★공개 번들이 개인정보 컬럼을 조회한다: {bad} · {sql[:160]}"
    for need in ("seq", "assigned_unit_id", "draw_seed", "draw_pool"):
        assert need in sql, f"검증에 필요한 {need} 를 안 가져온다"


def test_public_endpoints_have_no_auth_dependency_and_gate_on_finalization():
    """★무인증인 것은 **의도**다(그래야 제3자가 검증한다). 그 대가로 **최종화 게이트**가 필수다.

    둘을 **같은 테스트에서** 단언한다 — 하나만 만족하면 그게 곧 사고다.
    """
    root = pathlib.Path(cs.__file__).resolve().parents[4] / "api" / "app" / "api" / "endpoints" / "sales"
    if not root.exists():
        root = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "endpoints" / "sales"
    found = 0
    for fname, func in (("actions.py", "draw_group_verify"),
                        ("lifecycle_p5.py", "subscription_draw_verify")):
        src = (root / fname).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func)
        found += 1
        # ★인자 어디에도 `sales_ctx` 의존성이 없어야 한다(AST 로 본다 — 주석에 안 속는다).
        assert "sales_ctx" not in ast.dump(fn.args), (
            f"{func}: 인증이 붙어 있다 — 그러면 제3자 독립 검증이 성립하지 않는다"
        )
        body = ast.get_source_segment(src, fn) or ""
        assert "finalized_at" in body, (
            f"★{func}: **최종화 게이트가 없다** — 진행 중인 추첨의 nonce 가 무인증으로 나간다"
        )
        assert "verification_bundle" in body, f"{func}: 번들을 안 쓴다"
    assert found == 2, found


def test_bundle_tells_the_verifier_how_to_run():
    """★값만 주고 **쓰는 법**을 안 주면 「손으로 건네주는」 상태가 반만 해소된다."""
    src = inspect.getsource(cs.verification_bundle)
    assert "verify_draw.py" in src
    for flag in ("--commit-hash", "--nonce", "--participants-hash", "--pool-hash",
                 "--beacon-round", "--taken"):
        assert flag in src, f"검증 명령에 {flag} 가 빠졌다 — 그대로 붙여넣으면 안 돈다"


def test_chain_verdict_is_three_valued():
    """★체인이 뭐라 하는지 — `True`/`False`/**`None`(모름)**. 셋을 뭉개면 «설정 없음»이
    «앞서지 않았다»로 읽힌다."""
    from app.services.sales.draw import anchor

    src = inspect.getsource(anchor.commit_preceded_reveal)
    assert "-> bool | None" in src, "세 값 계약이 시그니처에 없다"
    assert "return None" in src, "모름을 None 으로 말하지 않는다"
