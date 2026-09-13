"""★**사전 공약 없는 추첨은 거부된다** — 그리고 공고번호로는 결과를 예측할 수 없다.

## 무엇이 뚫려 있었나 (실측 2026-09-13)

`run_draw` 의 seed 는 이랬다:

    seed = seed or ann.announce_no or str(announcement_id)

  ①-a **호출자가 `seed` 를 보낼 수 있었다** — `POST /subscription/{ann}/draw` 의 body 로.
       동점자 순서가 seed 로 정해지므로, 오프라인에서 원하는 당첨자가 나올 때까지 굴린 뒤
       제출하면 **결과를 고를 수 있다.**
  ①-b 미지정이면 seed 가 **공고번호**였다. 공고번호는 공개값이다 —
       ***누구나 추첨 전에 당첨자를 계산할 수 있었다.***

★그런데 이 결함은 **아무 신호도 내지 않는다.** 추첨은 정상적으로 끝나고 기록도 남는다.
  그래서 자동 락이 필요하다.
"""

from __future__ import annotations

import inspect

import pytest

from app.services.sales.draw import commitment_store as cs
from app.services.sales.draw import vrng
from app.services.sales.draw import vrng as _vrng_mod
from app.services.sales.subscription import engine as sub_engine

NONCE = "7c" * 32


#: ★새 계약(`Revealed` 에 명부·pool 이 들어간다) 이후의 테스트용 공약 생성기.
#:   ***이 헬퍼는 바인딩 검사를 「통과」시키려고 있는 것이지 「검증」하는 것이 아니다*** —
#:   바인딩이 실제로 결과를 바꾸는지는 `test_draw_binding_effect_locks.py` 가 태운다.
_FAKE_ROSTER = ["app-1", "app-2", "app-3"]
_FAKE_POOL = ["unit-1", "unit-2", "unit-3"]


def _fake_revealed(nonce: str, *, beacon_round: int = 900):
    from app.services.sales.draw import binding as _b
    return cs.Revealed(nonce, _vrng_mod.commitment(nonce), beacon_round,
                       _b.normalize(_FAKE_ROSTER), _b.normalize(_FAKE_POOL),
                       _b.roster_hash(_FAKE_ROSTER), _b.pool_hash(_FAKE_POOL))


def _patch_binding(monkeypatch, mod):
    """`subscription_binding` 과 비콘을 고정한다(네트워크·DB 없이 태우기 위해)."""
    async def _bind(_db, _site, _ann):
        return list(_FAKE_ROSTER), list(_FAKE_POOL)
    monkeypatch.setattr(mod, "subscription_binding", _bind)
    monkeypatch.setattr(mod.beacon, "randomness_for", lambda *a, **k: "aa" * 32)


def test_caller_cannot_supply_a_seed():
    """★`run_draw` 가 **seed 를 더는 받지 않는다** — 시그니처로 잠근다.

    인자가 남아 있으면 누군가 다시 넘긴다. 「안 쓴다」는 주석은 잠금이 아니다.
    """
    params = list(inspect.signature(sub_engine.run_draw).parameters)
    assert "seed" not in params, f"seed 인자가 아직 있다: {params}"
    # 공허 방지 — 이 함수를 실제로 읽고 있는가
    assert "announcement_id" in params, params


def test_endpoint_does_not_forward_body_seed():
    """호출부(엔드포인트)도 body 의 seed 를 넘기지 않는다 — 시그니처만 고치면 호출부가 남는다."""
    import pathlib

    src = pathlib.Path(
        sub_engine.__file__).parents[3] / "api" / "endpoints" / "sales" / "lifecycle_p5.py"
    code = "\n".join(
        ln for ln in src.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#"))
    assert "run_draw(" in code, "대조군 실패 — 호출부를 못 읽었다"
    assert '.get("seed")' not in code, "엔드포인트가 여전히 body.seed 를 넘긴다"


def test_announce_no_is_no_longer_a_seed_source():
    """★**공고번호 폴백이 사라졌다** — 실행되는 줄에서 확인(주석은 경위를 적고 있으므로 배제)."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(sub_engine.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_draw")
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert "rules" in attrs, "대조군 실패 — run_draw 본문을 못 읽었다"
    assert "announce_no" not in attrs, (
        "run_draw 가 아직 announce_no 를 읽는다 — 공개값이 추첨 키가 된다"
    )


class _Ann:
    def __init__(self, rules):
        import uuid
        self.id = uuid.uuid4()
        self.status = "OPEN"
        self.announce_no = "2026-PUBLIC"
        self.rules = rules
        self.round_id = None
        self.contract_end = None


def _run_with(rules, *, commitment=None, monkeypatch=None):
    """공약 상태만 바꿔 `run_draw` 초입을 태운다(DB 없이 seed 결정 구간까지).

    ★공약은 이제 `rules` 가 아니라 **append-only 저장소**에서 온다(리뷰 M-1/M-2).
      `commitment` 로 그 저장소의 반환을 흉내낸다 — `None` 이면 「공약 없음」이다.
    """
    import asyncio

    class _Res:
        def __init__(self, obj):
            self._o = obj

        def scalar_one_or_none(self):
            return self._o

        def scalars(self):
            return []

        def first(self):
            return None

    class _DB:
        async def execute(self, *_a, **_k):
            return _Res(ann)

        async def flush(self):
            return None

    ann = _Ann(rules)

    async def _fake_reveal(_db, _scope, _ref):
        if commitment is None:
            raise ValueError("추첨 공약이 없습니다 — 추첨 전에 공약을 게시해야 합니다")
        nonce, commit_hash = commitment
        if not vrng.verify_commitment(nonce, commit_hash):
            raise ValueError("추첨 공약이 일치하지 않습니다 — 저장된 nonce 가 공약과 다릅니다")
        return _fake_revealed(nonce)

    async def _bind(_db, _site, _ann):
        return list(_FAKE_ROSTER), list(_FAKE_POOL)

    orig = sub_engine.reveal_commitment
    orig_bind = sub_engine.subscription_binding
    orig_beacon = sub_engine.beacon.randomness_for
    sub_engine.reveal_commitment = _fake_reveal
    sub_engine.subscription_binding = _bind
    sub_engine.beacon.randomness_for = lambda *a, **k: "aa" * 32
    try:
        return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            sub_engine.run_draw(_DB(), object(), ann.id))
    finally:
        sub_engine.reveal_commitment = orig
        sub_engine.subscription_binding = orig_bind
        sub_engine.beacon.randomness_for = orig_beacon


def test_draw_without_commitment_is_refused():
    """★**공약이 없으면 추첨하지 않는다**(fail-closed).

    종전에는 조용히 공고번호로 떨어졌다 — ***예측 가능한 값으로 조용히 떨어지는 것이
    가장 나쁜 실패다***(아무도 모른다).
    """
    with pytest.raises(ValueError) as e:
        _run_with({})
    msg = str(e.value)
    # ★★**두 갈래를 한 신호로 보지 않는다**(2026-09-13 변이 실측).
    #   종전엔 `"공약" in msg` 만 봤는데, 「공약이 **없습니다**」와 「공약이 **일치하지 않습니다**」가
    #   **둘 다 「공약」을 포함**해서 부재 가드를 지워도 **초록**이었다(변이 SURVIVED).
    #   ***한 신호가 두 사건을 덮으면 어느 것이 고장났는지 못 가른다.***
    assert "공약이 없습니다" in msg, msg
    assert "일치하지" not in msg, f"부재가 아니라 불일치로 떨어졌다 — 부재 가드가 죽었다: {msg}"


def test_tampered_nonce_is_refused():
    """★공약 이후 nonce 를 바꾸면 거부된다 — 서버가 뽑아 보고 갈아치우는 것을 막는다."""
    good = vrng.commitment(NONCE)
    with pytest.raises(ValueError) as e:
        _run_with({}, commitment=("aa" * 32, good))
    msg = str(e.value)
    assert "일치하지" in msg, msg
    assert "공약이 없습니다" not in msg, f"불일치가 아니라 부재로 떨어졌다: {msg}"


def test_matching_commitment_passes_the_gate():
    """★**두 모집단** — 옳은 공약은 게이트를 **통과**한다(거부만 단언하면 「항상 거부」도 통과한다).

    게이트를 넘은 뒤 DB 가 가짜라 다른 예외로 끝나는 것은 정상이다 —
    여기서 보는 것은 **공약 검증이 통과했는가** 하나다.
    """
    try:
        _run_with({}, commitment=(NONCE, vrng.commitment(NONCE)))
    except ValueError as e:
        assert "공약" not in str(e.value), f"옳은 공약인데 게이트에서 막혔다: {e}"
    except Exception:
        pass  # DB 가짜로 인한 다른 실패 — 이 테스트의 관심사가 아니다


# ─────────────────────────────────────────────────────────────────────────────
# ★독립 리뷰 M-4 — 내가 「고쳤다」고 선언한 **그 줄이 무잠금**이었다.
#   `seed = vrng.seed_key(nonce, ann_id).hex()` → `seed = str(announcement_id)` 로 바꿔도
#   **락 전부 초록**(SURVIVED). 내 락이 `announce_no` 라는 **이름의 부재**만 봤기 때문이다 —
#   결함(«공개값이 추첨 키가 된다»)은 **다른 공개값**으로 그대로 재현됐다.
#   ***「이름이 불리는가」가 아니라 「그 값을 누가 만드는가」를 잠근다.***
# ─────────────────────────────────────────────────────────────────────────────


def _ordered_ids(nonce: str, ids: list[str]) -> list[str]:
    """`run_draw` 가 쓰는 것과 **같은 정렬 키**로 동점자 순서를 만든다.

    ★프로덕션 함수(`_rank_pick`)를 그대로 태운다 — 사본을 만들면 그 사본의 동작을 단언하게 된다.
    """
    class _A:
        def __init__(self, i):
            self.id = i
            self.rank = 1
            self.gajeom_score = 10.0
    seed = vrng.seed_key(nonce, "ann-fixed").hex()
    win, _rest = sub_engine._rank_pick([_A(i) for i in ids], len(ids), seed)
    return [a.id for a in win]


def test_nonce_actually_determines_the_outcome():
    """★**두 모집단** — nonce 가 다르면 순서가 **달라지고**, 같으면 **같아야** 한다.

    이 단언이 없으면 seed 를 **공개값 아무거나**로 바꿔도 초록이다(리뷰 M-4 가 그것을 실증했다).
    """
    ids = [f"app-{i:03d}" for i in range(24)]
    a1 = _ordered_ids("11" * 32, ids)
    a2 = _ordered_ids("11" * 32, ids)
    b = _ordered_ids("22" * 32, ids)
    assert a1 == a2, "같은 nonce 인데 결과가 흔들린다 — 재현 불가"
    assert a1 != b, "nonce 를 바꿔도 순서가 같다 — nonce 가 결과를 만들지 않는다"
    # 공허 방지 — 실제로 섞이고 있는가(정렬만 하면 항상 같은 순서다)
    assert a1 != sorted(ids), "동점자 순서가 입력 정렬과 같다 — 추첨이 아니다"


def test_public_values_alone_cannot_reproduce_the_order():
    """★**공개값만으로는 못 맞힌다** — 공고번호·공고 id 로 만든 순서와 달라야 한다.

    ①-b 의 본질은 «공개값이 키였다» 이므로, 그 공개값으로 만든 순서가 실제 순서와 같으면
    고친 것이 아니다.
    """
    ids = [f"app-{i:03d}" for i in range(24)]
    real = _ordered_ids("ab" * 32, ids)

    class _A:
        def __init__(self, i):
            self.id = i
            self.rank = 1
            self.gajeom_score = 10.0
    for public in ("2026-PUBLIC", "ann-fixed"):
        guess = [a.id for a in sub_engine._rank_pick(
            [_A(i) for i in ids], len(ids), public)[0]]
        assert guess != real, f"공개값 {public!r} 만으로 순서를 맞혔다 — 사전 계산 가능하다"


def test_run_draw_feeds_the_nonce_derived_seed_into_ranking(monkeypatch):
    """★★**배선을 태운다** — `run_draw` 가 실제로 넘기는 seed 를 가로채 확인한다.

    ★앞의 두 락은 `_rank_pick` 을 **직접** 불렀다. 그래서 `run_draw` 안의
      `seed = vrng.seed_key(...)` 줄을 `seed = str(announcement_id)` 로 바꿔도 **초록**이었다
      (리뷰 M-4 · 보강 뒤에도 **두 번 더** SURVIVED — 한 번은 순수 함수만 태워서,
       한 번은 가짜 DB 가 신청서를 안 줘서 `_rank_pick` 이 **불리지 않아 skip** 됐다).
      ***순수 함수를 잠그는 것과 그것을 부르는 줄을 잠그는 것은 다른 일이고,
      「태웠다」와 「그 줄에 도달했다」도 다른 일이다.***
    """
    import asyncio
    import uuid

    seen: list[str] = []
    failures: list[str] = []
    real = sub_engine._rank_pick

    def _spy(apps, n, seed):
        seen.append(seed)
        return real(apps, n, seed)

    class _App:
        def __init__(self, i):
            self.id = f"app-{i:03d}"
            self.rank = 1
            self.gajeom_score = 10.0
            self.unit_type_id = "T1"
            self.supply_class = "GENERAL"
            self.eligibility = "OK"
            self.status = "APPLIED"
            self.announcement_id = None

    class _Unit:
        def __init__(self, i):
            self.id = f"u-{i}"
            self.status = "AVAILABLE"

    apps = [_App(i) for i in range(6)]

    class _Res:
        def __init__(self, payload, scalar=None):
            self._p = payload
            self._s = scalar

        def scalar_one_or_none(self):
            return self._s

        def scalars(self):
            return list(self._p)

        def first(self):
            return None

    class _DB:
        def __init__(self):
            self.n = 0

        async def execute(self, *_a, **_k):
            self.n += 1
            # 1번째: 공고(FOR UPDATE) · 그 다음: 신청서 목록
            return _Res(apps if self.n > 1 else [], ann if self.n == 1 else None)

        async def flush(self):
            return None

        async def commit(self):
            return None

        def add(self, *_a, **_k):
            return None

    async def _fake_units(_db, _site, _type, *, lock=False):
        return [_Unit(i) for i in range(3)]

    monkeypatch.setattr(sub_engine, "_rank_pick", _spy)
    monkeypatch.setattr(sub_engine, "_available_units", _fake_units)

    ann = _Ann({})
    ann.id = uuid.UUID("00000000-0000-0000-0000-0000000000aa")

    def _run(nonce):
        seen.clear()
        async def _rev(_db, _s, _r):
            return _fake_revealed(nonce)
        monkeypatch.setattr(sub_engine, "reveal_commitment", _rev)
        _patch_binding(monkeypatch, sub_engine)
        try:
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                sub_engine.run_draw(_DB(), object(), ann.id))
        except Exception as exc:          # noqa: BLE001 — 사유를 **남긴다**
            # ★`except: pass` 로 삼키지 않는다. 처음에 그렇게 했다가 가짜 객체의
            #   속성 이름 오타(`supply_type` ↔ `supply_class`)가 조용히 먹혀
            #   `_rank_pick` 이 **안 불리는데 원인을 모르는** 상태가 됐다.
            #   가짜 DB 로 인한 후속 실패는 관심사가 아니지만 **무엇이었는지는 남긴다.**
            failures.append(repr(exc))
        return list(seen)

    n1 = "11" * 32
    got1 = _run(n1)
    # ★공허 방지 — 이 단언이 없으면 「불리지 않아서 통과」가 된다(실제로 한 번 그랬다)
    assert got1, (
        "★_rank_pick 이 불리지 않았다 — 배선 축이 검증되지 않은 채 초록이 될 뻔했다. "
        f"중간 실패: {failures[:2]}"
    )
    # ★기대값을 **프로덕션과 같은 순서**로 파생한다 — 공약이 묶는 명부·pool 지문과 비콘이
    #   키에 들어간다(순서가 곧 계약이다). 손으로 적은 값이면 순서 변경을 못 본다.
    from app.services.sales.draw import binding as _b
    expect1 = vrng.seed_key(n1, str(ann.id),
                            _b.roster_hash(_FAKE_ROSTER), _b.pool_hash(_FAKE_POOL),
                            "drand:900:" + "aa" * 32).hex()
    assert got1[0] == expect1, (
        f"run_draw 가 nonce 유래 seed 를 안 넘긴다: {got1[0]!r} != {expect1!r}"
    )
    n2 = "22" * 32
    got2 = _run(n2)
    assert got2 and got2[0] != got1[0], "nonce 를 바꿔도 같은 seed 가 간다"
    assert got2[0] != str(ann.id), "공고 id 가 그대로 seed 로 간다 — 공개값이 키다"
