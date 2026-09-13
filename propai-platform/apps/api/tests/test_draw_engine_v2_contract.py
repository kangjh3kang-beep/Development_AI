"""★②(동·호 즉석추첨) v2 계약 — **공약 + 언어 독립 + pool 전문 + v1 공존**.

종전 v1 은 `random.Random(secrets.token_hex(8)).choice(sorted(pool))` 였고 결함 셋이 겹쳤다:
  ① **사전 공약 없음** — 뽑아 보고 롤백 후 재시도해도 원장엔 **성공분 하나만** 남는다
  ② **CPython 구현 종속** — 다른 언어·다른 버전으로 **재현 불가**
  ③ **pool 해시 64비트 절단** + pool 원본 미저장 — 그 시점 pool 을 복원할 수 없다
"""

from __future__ import annotations

import ast
import pathlib

_ENGINE = pathlib.Path(__file__).resolve().parents[1] / (
    "app/services/sales/draw/draw_engine.py")


def _live_names() -> set[str]:
    """**실행되는 줄**의 이름만 — 주석이 v1 의 경위를 적고 있으므로 문자열 grep 은 뚫린다."""
    tree = ast.parse(_ENGINE.read_text(encoding="utf-8"))
    return ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            | {a.name.split(".")[0] for n in ast.walk(tree)
               if isinstance(n, ast.Import) for a in n.names})


def test_selection_uses_vrng_not_python_random():
    """★`random.Random` 이 **실행 경로에서** 사라졌는가(주석에는 남아 있어도 된다)."""
    names = _live_names()
    assert "vrng" in names, "대조군 실패 — 실행 이름을 하나도 못 읽었다"
    assert "pick" in names, "vrng.pick 을 쓰지 않는다"
    assert "random" not in names, f"아직 표준 random 을 쓴다: {sorted(n for n in names if 'rand' in n)}"


def test_commitment_is_required_for_dongho_draw():
    """★공약 저장소를 **거친다** — 공약 없는 추첨은 그 함수가 거부한다(fail-closed)."""
    names = _live_names()
    assert "reveal_commitment" in names, "②가 공약을 읽지 않는다 — grinding 을 못 막는다"


def test_pool_hash_is_not_truncated_and_pool_is_stored():
    """★해시 **절단 금지** + pool **전문 저장**(감사자가 그 시점 pool 을 복원해야 한다)."""
    src = _ENGINE.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "hexdigest()" in code, "대조군 실패 — 해시 계산부를 못 읽었다"
    assert "hexdigest()[:16]" not in code, "pool 해시가 아직 64비트로 절단된다"
    assert "draw_pool" in code, "pool 원본을 저장하지 않는다"


def test_seed_is_not_regenerated_on_contention():
    """★★선점 경합 재시도에서 **seed 를 새로 뽑지 않는다** — 그게 곧 grinding 통로다.

    v1 은 루프 안에서 `seed = secrets.token_hex(8)` 을 **매번** 새로 뽑았다. 공약을 도입해도
    루프가 seed 를 갈면 공약이 무의미해진다 ⇒ 카운터만 이어받아야 한다.
    """
    tree = ast.parse(_ENGINE.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "draw_for_candidate")
    whiles = [n for n in ast.walk(fn) if isinstance(n, ast.While)]
    assert whiles, "대조군 실패 — 재시도 루프를 못 찾았다"
    # ★**튜플 대입도 대입이다**. 처음엔 `t.id` 만 봤다가 `a, counter = vrng.pick(...)` 를
    #   놓쳐 **코드가 옳은데 락이 빨개졌다**(내 조회기가 틀린 경우다).
    def _targets(node):
        for t_ in node.targets:
            for sub in ast.walk(t_):
                if isinstance(sub, ast.Name):
                    yield sub.id

    assigned_in_loop = {
        name for w in whiles for n in ast.walk(w)
        if isinstance(n, ast.Assign) for name in _targets(n)}
    # 공허 방지 — 루프가 실제로 무언가를 대입하는가
    assert assigned_in_loop, "대조군 실패 — 루프에서 대입을 하나도 못 읽었다"
    assert "seed" not in assigned_in_loop, (
        "재시도 루프 안에서 seed 를 다시 만든다 — 공약이 무의미해진다"
    )
    assert "counter" in assigned_in_loop, "카운터를 이어받지 않는다 — 같은 세대를 반복 시도한다"


def test_v1_coexistence_is_pinned_in_schema():
    """★「신규 공고부터」 — 옛 배정은 v1 로 재현되고 **신규 그룹은 v2 로 못 박힌다**."""
    src = _ENGINE.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "algo_version" in code, "알고리즘 버전을 기록하지 않는다 — 과거 재현 근거가 사라진다"
    assert "'v2'" in code, "신규 그룹이 v2 로 못 박히지 않는다"
    assert "DEFAULT 'v1'" in code, "옛 행이 v1 로 읽히지 않는다(기록 부재 = v1)"


def test_seed_column_is_wide_enough_for_the_new_key():
    """★`varchar(32)` 에 64 hex 를 넣으면 **조용히 잘린다** — 재현이 깨진다."""
    src = _ENGINE.read_text(encoding="utf-8")
    assert "ALTER COLUMN draw_seed TYPE varchar(128)" in src, (
        "draw_seed 컬럼을 넓히지 않았다 — VRNG 키(64 hex)가 잘린다"
    )
