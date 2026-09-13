"""★**존재가 아니라 효과**를 잠근다 — 독립 적대 리뷰가 넣은 변이 7/7 이 생존한 뒤에 쓴 락.

이전 판(`test_draw_beacon_contract.py`)은 *"`seed_contributions` 가 **불렸는가**"* 를 AST 로 봤다.
리뷰어가 **소비만** 끊자(`*beacon_parts` 삭제) **139건이 전부 초록**이었다 — 호출 노드는 그대로
남아 있었기 때문이다. ***AST 로 잠글 수 있는 것은 「값의 출처」뿐이고, 「그 값이 쓰였는가」가 아니다.***

그래서 이 파일은 **엔진을 실제로 태워** *「그 값이 바뀌면 결과가 바뀌는가」* 를 본다.
가짜 DB 는 **쿼리별로 라우팅**한다 — 인자를 버리는 스텁은 그 자체가 잠금의 상한이 된다.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
import uuid

import pytest

from app.services.sales.draw import binding, vrng
from app.services.sales.draw import commitment_store as cs
from app.services.sales.draw import draw_engine as de

_NONCE = "ab" * 32
_GROUP = "11111111-1111-1111-1111-111111111111"
_CAND = "22222222-2222-2222-2222-222222222222"
_POOL = [f"unit-{i:03d}" for i in range(24)]
_ROSTER = [_CAND, "33333333-3333-3333-3333-333333333333"]


class _Row(tuple):
    pass


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return []


class _DB:
    """★쿼리를 **읽고 라우팅**하는 가짜 DB. 인자를 버리면 그 층은 원리적으로 무잠금이 된다."""

    def __init__(self, roster=None, assigned=(), hold_wins=True):
        self.roster = list(_ROSTER if roster is None else roster)
        self.assigned = set(assigned)
        self.hold_wins = hold_wins
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())
        self.sql.append(q)
        # ★원문 쿼리를 보고 라우팅한다(추측하지 않는다). 어느 것도 안 맞으면 아래에서 빈 결과가
        #   나가는데, 그러면 「대상자를 찾을 수 없다」로 죽어 **락이 공허해진다** — 그래서
        #   `test_unchanged_roster_passes_control` 이 대조군으로 그 상태를 잡아 준다.
        if "SELECT seq, name, assigned_unit_id FROM sales_draw_candidates" in q:
            return _Res([(1, "홍길동", None)])
        if "SELECT id FROM sales_draw_candidates" in q:
            return _Res([(r,) for r in self.roster])
        if "SELECT assigned_unit_id FROM sales_draw_candidates" in q:
            return _Res([(a,) for a in self.assigned])
        if "UPDATE sales_unit_inventory" in q:
            return _Res([("ok",)] if self.hold_wins else [])
        if "SELECT dong, ho" in q:
            return _Res([("101", "1501")])
        return _Res([])

    async def commit(self):
        return None

    async def flush(self):
        return None

    def add(self, *_a, **_k):
        return None


def _revealed(*, beacon_round=None, participants=None, pool=None):
    parts = list(_ROSTER if participants is None else participants)
    pool = list(_POOL if pool is None else pool)
    return cs.Revealed(_NONCE, vrng.commitment(_NONCE), beacon_round,
                       binding.normalize(parts), binding.normalize(pool),
                       binding.roster_hash(parts), binding.pool_hash(pool))


def _run_draw(monkeypatch, rev, *, beacon_value="aa" * 32, db=None):
    async def _rev(_db, _scope, _ref):
        return rev

    monkeypatch.setattr(de, "reveal_commitment", _rev)
    monkeypatch.setattr(de.beacon, "randomness_for",
                        lambda rnd, *a, **k: beacon_value, raising=True)

    async def _ev(*_a, **_k):
        return {"id": "ev"}

    monkeypatch.setattr(de, "append_event", _ev)
    return asyncio.new_event_loop().run_until_complete(
        de.draw_for_candidate(db or _DB(), uuid.uuid4(), _GROUP, _CAND))


# ── ① ★비콘 값이 **엔진을 통과해** 결과를 바꾸는가 (리뷰 M-1) ──────────────
def test_beacon_value_changes_the_dongho_result_through_the_engine(monkeypatch):
    """★`*beacon_parts` 를 seed_key 에서 **빼면 이 테스트가 빨개져야** 한다.

    종전 락은 `beacon.seed_contributions` 를 **직접** 태워서, 엔진이 그 결과를 버려도 초록이었다.
    """
    rev = _revealed(beacon_round=900)
    got = {_run_draw(monkeypatch, rev, beacon_value=f"{i:02x}" * 32)["assigned_unit"]["id"]
           for i in range(1, 14)}
    assert len(got) > 1, (
        f"★비콘 값을 13가지로 바꿔도 배정이 하나뿐이다({got}) — "
        "엔진이 비콘 기여값을 **seed 에 안 쓰고 있다**(불리기만 한다)"
    )


def test_dongho_result_is_deterministic_for_the_same_beacon(monkeypatch):
    """대조군 — 같은 입력이면 **같은 결과**여야 한다(안 그러면 ①이 그냥 무작위를 본 것)."""
    rev = _revealed(beacon_round=900)
    a = _run_draw(monkeypatch, rev, beacon_value="cc" * 32)["assigned_unit"]["id"]
    b = _run_draw(monkeypatch, rev, beacon_value="cc" * 32)["assigned_unit"]["id"]
    assert a == b, "재현 불가능하면 제3자 검증 자체가 성립하지 않는다"


# ── ② ★명부·pool 지문이 **결과를 바꾸는가**(게이트 말고 seed 축) ────────────
def test_participants_hash_changes_the_result(monkeypatch):
    """지문을 seed 에서 빼면 빨개진다 — 게이트만 있으면 게이트를 우회하는 경로가 남는다."""
    base = _revealed(beacon_round=900)
    got = {_run_draw(monkeypatch, _revealed(beacon_round=900, participants=[_CAND, f"x-{i}"]),
                     db=_DB(roster=[_CAND, f"x-{i}"]))["assigned_unit"]["id"]
           for i in range(12)}
    assert len(got) > 1, f"명부 지문이 seed 에 닿지 않는다 — 결과 {got}"
    assert base.participants_hash != binding.roster_hash([_CAND, "x-0"])


def test_pool_hash_changes_the_result(monkeypatch):
    got = set()
    for i in range(12):
        pool = _POOL + [f"extra-{i}"]
        # pool 자체가 커지면 모집단이 달라지므로, **지문만** 다르고 모집단은 같은 상황을 만든다.
        rev = cs.Revealed(_NONCE, vrng.commitment(_NONCE), 900,
                          binding.normalize(_ROSTER), binding.normalize(_POOL),
                          binding.roster_hash(_ROSTER), binding.pool_hash(pool))
        got.add(_run_draw(monkeypatch, rev)["assigned_unit"]["id"])
    assert len(got) > 1, f"pool 지문이 seed 에 닿지 않는다 — 결과 {got}"


# ── ③ ★공약 이후 명부가 바뀌면 **거부**한다 (리뷰 MAJOR-1 의 본체) ──────────
def test_roster_added_after_commit_is_refused(monkeypatch):
    """★이것이 「75회 등록해 원하는 세대 뽑기」를 막는 자리다."""
    rev = _revealed(beacon_round=900)
    with pytest.raises(ValueError) as e:
        _run_draw(monkeypatch, rev, db=_DB(roster=[*_ROSTER, "새로-끼워넣은-사람"]))
    assert "명부가 바" in str(e.value), str(e.value)


def test_unchanged_roster_passes_control(monkeypatch):
    """대조군 — 명부가 그대로면 통과한다(③이 「늘 거부」가 아님을 가른다)."""
    out = _run_draw(monkeypatch, _revealed(beacon_round=900))
    assert out["assigned_unit"]["id"] in _POOL


# ── ④ ★pool 은 **공약된 목록**에서 온다 — 라이브 AVAILABLE 재조회 금지 ──────
def test_engine_does_not_requery_live_available_pool():
    """★`_remaining_units` 를 다시 쓰면 추첨 직전 HOLD 로 결과를 고를 수 있다(리뷰 MAJOR-2).

    AST 로 **`draw_for_candidate` 안의 호출만** 본다(모듈 전체 grep 은 다른 함수에 뚫린다).
    """
    src = pathlib.Path(de.__file__).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "draw_for_candidate")
    called = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "_remaining_units" not in called, (
        "★추첨이 라이브 가용 세대를 다시 조회한다 — 공약된 pool 이 모집단이어야 한다"
    )
    assert "reveal_commitment" in called, "공약을 안 읽는다"
    body = ast.get_source_segment(src, fn) or ""
    assert "rev.pool_ids" in body, "공약된 pool 을 모집단으로 쓰지 않는다"


def test_hold_contention_records_the_start_counter(monkeypatch):
    """★선점 경합이 나면 카운터가 올라가고, **그 시작값이 응답에 실려야** 검증기가 재현한다."""
    rev = _revealed(beacon_round=900)
    out = _run_draw(monkeypatch, rev)
    assert "start_counter" in out, f"시작 카운터가 응답에 없다 — 검증기가 재현 불가: {sorted(out)}"
    assert isinstance(out["start_counter"], int)


# ── ⑤ ★비콘 없는 공약은 **거부**된다 (리뷰 M-5/M-6) ─────────────────────────
def test_null_beacon_round_is_refused(monkeypatch):
    """`UPDATE … SET beacon_round=NULL` 로 비콘을 끄는 통로를 막았는가."""
    with pytest.raises(Exception) as e:   # noqa: PT011 — BeaconError 는 RuntimeError 하위
        _run_draw(monkeypatch, _revealed(beacon_round=None))
    assert "비콘" in str(e.value), str(e.value)


def test_reveal_refuses_a_commitment_without_binding():
    """옛 형식(명부·pool 없음) 공약으로는 뽑지 않는다 — 호환이 보장을 끄는 값이 아니다."""
    class _R:
        def first(self):
            return (_NONCE, vrng.commitment(_NONCE), 900, None, None, None, None)

    class _D:
        async def execute(self, *_a, **_k):
            return _R()

    with pytest.raises(ValueError) as e:
        asyncio.new_event_loop().run_until_complete(cs.reveal_commitment(_D(), "dongho", "x"))
    assert "묶고 있지 않습니다" in str(e.value), str(e.value)


# ── ⑥ ★검증기의 기여값 **순서**까지 프로덕션과 같은가 (리뷰 M-7) ────────────
def test_verifier_contribution_order_matches_production():
    """★문자열만 맞추고 **위치**를 안 잠그면 정직한 추첨이 「조작」으로 신고된다.

    프로덕션 `draw_for_candidate` 의 `seed_key(...)` 인자 **순서를 AST 로 뽑아** 검증기의
    `dongho_contributions` 가 만드는 순서와 대조한다 — ***목록이 아니라 파생이다.***
    """
    import importlib.util

    src = pathlib.Path(de.__file__).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "draw_for_candidate")
    call = next(c for c in ast.walk(fn)
                if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "seed_key")
    prod_order = []
    for arg in call.args[1:]:                       # 0번은 nonce
        seg = ast.get_source_segment(src, arg) or ""
        prod_order.append(seg.replace(" ", ""))
    assert prod_order, "seed_key 인자를 못 뽑았다(공허 방지)"

    here = pathlib.Path(de.__file__).resolve()
    vp = next((p / "scripts" / "verify_draw.py" for p in here.parents
               if (p / "scripts" / "verify_draw.py").exists()), None)
    assert vp is not None, (
        "★검증기를 못 찾았다 — 층수를 하드코딩하면 **skip 으로 조용히 넘어가** "
        "「두 구현이 같은 계약인가」가 미검증으로 남는다(전례 있음)"
    )
    spec = importlib.util.spec_from_file_location("verify_draw_order", vp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ver_order = mod.dongho_contributions("G", "C", "PH", "UH", "BEACON")

    # 프로덕션 표현식 → 검증기가 넣는 값의 **역할**로 사상한다(이름이 아니라 자리를 대조).
    role = {"str(group_id)": "G", "str(candidate_id)": "C",
            "rev.participants_hash": "PH", "rev.pool_hash": "UH", "*beacon_parts": "BEACON"}
    mapped = [role.get(x) for x in prod_order]
    assert None not in mapped, (
        f"★프로덕션 seed_key 인자에 **검증기가 모르는 항목**이 생겼다: {prod_order} — "
        "검증기를 같이 고치지 않으면 정직한 추첨이 「결과가 다르다」로 신고된다"
    )
    assert mapped == ver_order, f"순서가 다르다 — 프로덕션 {mapped} ↔ 검증기 {ver_order}"


# ── ⑦ ★UA 가 **차단되는 모양**이면 코드가 거부하는가 (리뷰 M-5) ─────────────
def test_blocked_user_agent_shape_is_refused(monkeypatch):
    from app.services.sales.draw import beacon

    monkeypatch.setattr(beacon, "_UA", "Python-urllib/3.13")
    with pytest.raises(beacon.BeaconError) as e:
        beacon._http_json("https://api.drand.sh/x")
    assert "차단되는 모양" in str(e.value), str(e.value)


def test_current_user_agent_passes_control():
    """대조군 — 지금 값은 통과한다(⑦이 「늘 거부」가 아님)."""
    from app.services.sales.draw import beacon

    beacon._assert_ua_is_not_blocked(beacon._UA)


# ── ⑧ ★425/503 핸들러 **순서** (리뷰 M-2) ──────────────────────────────────
@pytest.mark.parametrize(("path", "func"), [
    ("app/api/endpoints/sales/actions.py", "draw_run"),
    ("app/api/endpoints/sales/lifecycle_p5.py", "draw"),
])
def test_not_ready_handler_precedes_the_superclass(path, func):
    """★`except BeaconError` 가 먼저 오면 **425 분기는 도달 불가**가 되고, 「대기」가 「장애」로
    뭉쳐진다 — 상태코드 집합만 단언하면 **죽은 425 도 통과**한다(리뷰가 변이로 실증)."""
    root = pathlib.Path(__file__).resolve().parents[1]
    tree = ast.parse((root / path).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func)
    order: list[str] = []
    for tr in ast.walk(fn):
        if not isinstance(tr, ast.Try):
            continue
        for h in tr.handlers:
            names = {m.id for m in ast.walk(h.type) if isinstance(m, ast.Name)} if h.type else set()
            for n in ("BeaconNotReadyError", "BeaconError"):
                if n in names:
                    order.append(n)
    assert order.count("BeaconNotReadyError") == 1 and order.count("BeaconError") == 1, order
    assert order.index("BeaconNotReadyError") < order.index("BeaconError"), (
        f"{func}: 상위 예외가 먼저라 **425 가 도달 불가**다 — 순서 {order}"
    )


# ── ⑨ ★`revealed_at` 이 **실제로 값을 쓰는가** (리뷰 MED-1) ─────────────────
def test_reveal_actually_writes_a_time_not_a_noop():
    """★종전 락은 `UPDATE`·`revealed_at`·`COALESCE` **문자열 존재**만 봤다.
    `COALESCE(revealed_at, revealed_at)`(아무것도 안 씀)로 바꿔도 초록이었다."""
    src = inspect.getsource(cs.reveal_commitment)
    line = next(ln for ln in src.splitlines() if "COALESCE(revealed_at" in ln)
    rest = line[line.index("COALESCE(") + len("COALESCE("):]
    depth, end = 1, None                       # ★괄호 균형으로 자른다 — `now()` 의 괄호에 걸리면
    for i, ch in enumerate(rest):              #   `now(` 로 잘려 **정상 코드를 결함으로 신고**한다
        depth += (ch == "(") - (ch == ")")
        if depth == 0:
            end = i
            break
    assert end is not None, f"COALESCE 괄호를 못 닫았다: {line}"
    args = [a.strip() for a in rest[:end].split(",")]
    assert args[0] == "revealed_at", args
    assert args[1] != "revealed_at", (
        "★두 번째 인자가 `revealed_at` 이면 **아무것도 기록되지 않는다** — no-op 이다"
    )
    assert "now()" in args[1], f"시각을 쓰지 않는다: {args}"


# ── ⑩ ★`latest_round` 도 **운영자 2곳**을 요구하는가 (리뷰 M-3/M-4) ─────────
_API, _CF, _API2 = "https://api.drand.sh", "https://drand.cloudflare.com", "https://api2.drand.sh"


def _latest_fetcher(values: dict[str, int]):
    """`{엔드포인트: 그 곳이 보고하는 latest}`. 목록에 없는 곳은 **죽는다**."""
    def fetch(url: str) -> dict:
        base = next((b for b in values if url.startswith(b + "/")), None)
        if base is None:
            raise OSError(f"연결 불가(가짜): {url}")
        return {"round": values[base], "randomness": "aa" * 32}
    return fetch


def test_latest_round_refuses_a_single_operator():
    """★한 곳만 살아 있으면 **거부**한다.

    종전에는 «첫 번째로 응답한 곳»을 그대로 썼다. `fetch_round` 는 운영자 2곳을 요구하는데
    `latest_round` 는 안 해서 **경계를 한쪽만 잠갔고**, 「미래 라운드인가」 판정이 전부 이 값에
    걸려 있다 ⇒ 한 곳이 뒤처지거나 거짓말하면 공약이 **이미 공개된 라운드**를 못 박는다.
    """
    from app.services.sales.draw import beacon

    with pytest.raises(beacon.BeaconError) as e:
        beacon.latest_round((_API, _CF), _latest_fetcher({_API: 1000}))
    assert "운영자" in str(e.value), str(e.value)


def test_latest_round_two_mirrors_of_one_operator_is_not_enough():
    """★같은 운영자 예비 두 곳은 대조가 아니다 — 그 운영자가 거짓말하면 **함께** 거짓말한다."""
    from app.services.sales.draw import beacon

    with pytest.raises(beacon.BeaconError):
        beacon.latest_round((_API, _API2), _latest_fetcher({_API: 1000, _API2: 1000}))


def test_latest_round_refuses_a_lagging_operator():
    """★실측 시나리오: 한 곳이 1000라운드(≈8.3시간) 뒤처지면 **거부**한다."""
    from app.services.sales.draw import beacon

    with pytest.raises(beacon.BeaconError) as e:
        beacon.latest_round((_API, _CF), _latest_fetcher({_API: 1000, _CF: 2000}))
    assert "어긋" in str(e.value), str(e.value)


def test_latest_round_takes_the_max_within_tolerance_control():
    """대조군 — 정상 편차(전파 지연)는 통과하고, ★**앞선 값**을 쓴다.

    ***틀릴 수밖에 없다면 안전한 쪽으로 틀려라*** — 뒤처진 값을 따라가면 「과거를 미래라 부르는」
    쪽으로 틀리고, 그 방향이 보장을 깨는 방향이다.
    """
    from app.services.sales.draw import beacon

    got = beacon.latest_round((_API, _CF), _latest_fetcher({_API: 1999, _CF: 2000}))
    assert got == 2000, f"뒤처진 값을 따라갔다: {got}"


def test_commit_uses_the_cross_checked_latest():
    """★`commit_draw` 의 「미래인가」 판정이 **그 교차검증된 값**을 쓰는가 — 단일 출처로 되돌리면
    이 테스트가 빨개진다(고친 것을 잠그지 않으면 다음 판에 되돌아온다)."""
    class _R:
        def first(self):
            return None

    class _D:
        async def execute(self, *_a, **_k):
            return _R()

        async def commit(self):
            return None

    f = _latest_fetcher({_API: 1000})            # 한 운영자만 — 교차검증이면 거부여야 한다
    with pytest.raises(Exception) as e:          # noqa: PT011
        asyncio.new_event_loop().run_until_complete(
            cs.commit_draw(_D(), "s", "dongho", "r",
                           participants=_ROSTER, pool_ids=_POOL, fetch=f))
    assert "운영자" in str(e.value), str(e.value)
