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

    def __init__(self, roster=None, assigned=(), hold_wins=True, hold_wins_after=0):
        self.roster = list(_ROSTER if roster is None else roster)
        self.assigned = set(assigned)
        self.hold_wins = hold_wins
        #: ★`hold_wins_after=n` → **처음 n회 선점 실패**(경합) 후 성공. 종전에는 `hold_wins=False`
        #:   를 **한 번도 주지 않아** 경합 경로가 미검증이었다(R2 리뷰 MEDIUM-2).
        self.hold_wins_after = hold_wins_after
        self._hold_calls = 0
        #: 이 세대들은 **타 현장**이거나 **소프트삭제**다 — 술어가 없으면 새어 나간다.
        self.foreign: set[str] = set()
        self.soft_deleted: set[str] = set()
        self.leaked: list[tuple] = []
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
            # ★★**술어를 실제로 집행한다.** 엔진이 `site_id`·`deleted_at` 를 안 걸면 여기서
            #   타 현장·소프트삭제 세대가 **선점에 성공**해 버린다 — 그러면 아래 테스트가 빨개진다.
            #   ***문자열로 «SQL 에 site_id 가 있나» 를 보는 것은 효과가 아니라 모양이다.***
            uid = (params or {}).get("u")
            if uid in self.foreign and "site_id=:s" not in q:
                self.leaked.append(("타현장", uid))
            if uid in self.soft_deleted and "deleted_at IS NULL" not in q:
                self.leaked.append(("소프트삭제", uid))
            if uid in self.foreign or uid in self.soft_deleted:
                # 술어가 제대로 걸렸으면 DB 는 **0행**을 돌려준다.
                blocked = ("site_id=:s" in q and uid in self.foreign) or (
                    "deleted_at IS NULL" in q and uid in self.soft_deleted)
                if blocked:
                    self._hold_calls += 1
                    return _Res([])
            self._hold_calls += 1
            lost = (not self.hold_wins) or self._hold_calls <= self.hold_wins_after
            return _Res([] if lost else [("ok",)])
        if "SELECT dong, ho" in q:
            return _Res([("101", "1501")])
        # ★★**모르는 재고 조회는 죽인다**(R2 리뷰 MAJOR-5 실측). 종전에는 빈 결과를 돌려줘서,
        #   엔진이 **새 재고 쿼리를 추가해 라이브 상태로 모집단을 좁혀도** 락이 못 봤다
        #   (`_remaining_units` 라는 **이름만** 안 쓰면 통과했다).
        #   ***스텁이 조용히 비면 그 층은 원리적으로 무잠금이다.***
        if q.upper().startswith("SELECT") and (
                "sales_unit_inventory" in q or "sales_draw_candidates" in q):
            raise AssertionError(
                "★추첨이 **이 스텁이 모르는 조회**를 한다 — 조용히 빈 결과를 주면 그 층이 "
                f"원리적으로 무잠금이 된다(R2 리뷰 MAJOR-5·MEDIUM-5): {q[:160]}"
            )
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

    meta_seen: dict = {}

    async def _ev(*_a, **kw):
        meta_seen.clear()
        meta_seen.update(kw.get("meta") or {})
        return {"id": "ev"}

    monkeypatch.setattr(de, "append_event", _ev)
    de._last_meta_for_test = meta_seen
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


# ── ⑪ ★명부 게이트가 **치환**도 막는가(추가 방향만 잠그면 뚫린다) ───────────
def test_roster_substitution_is_refused(monkeypatch):
    """★같은 **인원수**로 사람을 바꿔치기하면?

    R2 리뷰 실측: 게이트를 `len(set(live)) != len(공약)` 으로 약화해도 초록이었다 —
    기존 락이 **추가**만 태웠기 때문이다. 치환은 공격자에게 **새 candidate_id** 를 주므로
    ***이 커밋이 닫으려는 바로 그 자유변수***다.
    """
    rev = _revealed(beacon_round=900)
    swapped = [_ROSTER[0], "치환된-다른-사람"]          # 인원수 동일(2명), 구성만 다름
    assert len(swapped) == len(rev.participants)
    with pytest.raises(ValueError) as e:
        _run_draw(monkeypatch, rev, db=_DB(roster=swapped))
    assert "명부가 바" in str(e.value), str(e.value)


def test_roster_removal_is_refused(monkeypatch):
    """제거 방향도 막는다 — 경쟁자를 빼는 것도 결과를 바꾼다."""
    rev = _revealed(beacon_round=900)
    with pytest.raises(ValueError):
        _run_draw(monkeypatch, rev, db=_DB(roster=[_ROSTER[0]]))


# ── ⑫ ★청약 경로의 게이트(형제) — R2: 락 0건이었다 ─────────────────────────
def _sub_revealed(roster, pool, *, beacon_round=900):
    return cs.Revealed(_NONCE, vrng.commitment(_NONCE), beacon_round,
                       binding.normalize(roster), binding.normalize(pool),
                       binding.roster_hash(roster), binding.pool_hash(pool))


def _run_subscription(monkeypatch, rev, live_roster, live_pool):
    """청약 `run_draw` 의 **게이트까지만** 태운다(그 뒤는 가짜 DB 관심사 밖)."""
    from app.services.sales.subscription import engine as se

    async def _rev(_db, _s, _r):
        return rev

    async def _bind(_db, _site, _ann):
        return list(live_roster), list(live_pool)

    class _Ann:
        id = "ann-1"
        rules = {}
        status = "OPEN"
        contract_end = None
        round_id = None

    class _Res2:
        def scalars(self):
            return _S()

        def first(self):
            return (_Ann(),)

        def scalar_one_or_none(self):
            return _Ann()

    class _S:
        def __iter__(self):
            return iter([_Ann()])

        def first(self):
            return _Ann()

    class _D:
        async def execute(self, *_a, **_k):
            return _Res2()

        async def flush(self):
            return None

        async def commit(self):
            return None

        def add(self, *_a, **_k):
            return None

    emitted: list[tuple] = []

    async def _emit(_db, _site, event_type, payload):
        emitted.append((event_type, payload))

    monkeypatch.setattr(se, "reveal_commitment", _rev)
    monkeypatch.setattr(se, "subscription_binding", _bind)
    monkeypatch.setattr(se, "emit_outbox", _emit)
    monkeypatch.setattr(se.beacon, "randomness_for", lambda *a, **k: "aa" * 32)
    return asyncio.new_event_loop().run_until_complete(se.run_draw(_D(), "site", "ann-1"))


@pytest.mark.parametrize(("live_roster", "live_pool", "말"), [
    (["a", "b", "새사람"], ["u1", "u2"], "명부"),      # 명부 추가
    (["a", "치환"], ["u1", "u2"], "명부"),             # 명부 치환(인원수 동일)
    (["a", "b"], ["u1", "u2", "u3"], "대상 세대"),      # pool 추가
    (["a", "b"], ["u1"], "대상 세대"),                  # pool 제거
])
def test_subscription_binding_gate_refuses_any_change(monkeypatch, live_roster, live_pool, 말):
    """★R2 리뷰: 청약 쪽 게이트는 **락이 0건**이라 `if False:` 두 개가 다 생존했다.

    ***고친 자리의 형제를 스윕하라*** 를 인용해 놓고 그 안에서 어긴 자리다.
    """
    rev = _sub_revealed(["a", "b"], ["u1", "u2"])
    with pytest.raises(ValueError) as e:
        _run_subscription(monkeypatch, rev, live_roster, live_pool)
    assert 말 in str(e.value), str(e.value)


def test_subscription_binding_gate_passes_when_unchanged(monkeypatch):
    """대조군 — 바뀐 게 없으면 게이트를 **통과**한다(늘 거부가 아님을 가른다)."""
    from app.services.sales.subscription import engine as se

    rev = _sub_revealed(["a", "b"], ["u1", "u2"])
    try:
        _run_subscription(monkeypatch, rev, ["a", "b"], ["u1", "u2"])
    except ValueError as exc:                       # 게이트 메시지면 실패, 그 뒤 가짜 DB 실패는 무시
        assert "바뀌었습니다" not in str(exc), f"게이트가 정상 명부를 막았다: {exc}"
    except Exception:                               # noqa: BLE001 — 가짜 DB 로 인한 후속 실패는 관심 밖
        pass
    assert se.binding.roster_hash(["a", "b"]) == rev.participants_hash


# ── ⑬ ★선점 경합 경로를 **실제로** 만든다(ME-2: 한 번도 안 태워졌다) ────────
def test_hold_contention_actually_changes_the_pick(monkeypatch):
    """★`hold_wins=False` 를 **한 번도 주지 않아** 경합 경로가 미검증이었다.

    경합이 나면 카운터가 올라가 **다른 세대**가 뽑히고, 그 사실이 `skipped_units` 로 남아야 한다.
    """
    rev = _revealed(beacon_round=900)
    calm = _run_draw(monkeypatch, rev)
    db = _DB(hold_wins_after=2)                     # 처음 2회 선점 실패 → 카운터 전진
    fought = _run_draw(monkeypatch, rev, db=db)
    assert fought["assigned_unit"]["id"] != calm["assigned_unit"]["id"], (
        "경합이 있었는데 같은 세대가 나왔다 — 카운터가 안 움직인다"
    )
    assert fought["start_counter"] > 0, fought["start_counter"]
    assert len(fought["skipped_units"]) == 2, fought["skipped_units"]
    assert calm["skipped_units"] == [], calm["skipped_units"]
    # ★**원장 meta 도 본다** — 응답만 단언하면 meta 쪽 값을 0 으로 고정해도 초록이다
    #   (R2 재판정에서 실제로 생존했다). 감사자는 **원장**을 읽지 응답을 읽지 않는다.
    meta = getattr(de, "_last_meta_for_test", {})
    assert meta.get("start_counter") == fought["start_counter"], (
        f"원장 meta 의 시작 카운터가 응답과 다르다: meta={meta.get('start_counter')} "
        f"응답={fought['start_counter']}"
    )
    assert meta.get("skipped_units") == fought["skipped_units"], meta.get("skipped_units")


# ── ⑭ ★도메인 분리(ME-3: 문서만 있고 단언이 없었다) ─────────────────────────
def test_roster_and_pool_hashes_are_domain_separated():
    """같은 목록이라도 **명부 지문 ≠ pool 지문** — 아니면 한쪽을 다른 쪽 자리에 넣는 혼동이 성립한다."""
    ids = ["x", "y", "z"]
    assert binding.roster_hash(ids) != binding.pool_hash(ids)
    assert binding.roster_hash([]) != binding.pool_hash([])


# ── ⑮ ★청약 추첨이 **원장 이벤트를 실제로 낸다**(R2 MAJOR-1: 삭제해도 초록이었다) ──
def test_subscription_draw_emits_the_commitment_event(monkeypatch):
    """★청약 경로는 당첨자 수(int)만 돌려주므로 **어떤 공약으로 뽑았는지가 반환에 실릴 자리가 없다.**
    그래서 원장에 남기기로 했는데, 그 호출을 **지워도 초록**이었다(락 부재).

    ★그리고 「냈다」로 끝내지 않는다 — **감사에 필요한 필드가 실제로 실렸는지**까지 본다
    (R2 실측: 화이트리스트에 없어 payload 가 `{}` 로 비워지고 있었다).
    """
    from app.services.sales.harness.outbox import WHITELIST
    from app.services.sales.subscription import engine as se

    emitted: list[tuple] = []

    async def _emit(_db, _site, event_type, payload):
        emitted.append((event_type, dict(payload or {})))

    monkeypatch.setattr(se, "emit_outbox", _emit)
    rev = _sub_revealed(["a", "b"], ["u1", "u2"])

    async def _rev(_db, _s, _r):
        return rev

    async def _bind(_db, _site, _ann):
        return ["a", "b"], ["u1", "u2"]

    monkeypatch.setattr(se, "reveal_commitment", _rev)
    monkeypatch.setattr(se, "subscription_binding", _bind)
    monkeypatch.setattr(se.beacon, "randomness_for", lambda *a, **k: "aa" * 32)

    class _R:
        def scalar_one_or_none(self):
            return type("A", (), {"id": "ann-1", "rules": {}, "status": "OPEN",
                                  "contract_end": None, "round_id": None})()

        def scalars(self):
            return []

        def first(self):
            return None

    class _D:
        async def execute(self, *_a, **_k):
            return _R()

        async def flush(self):
            return None

        async def commit(self):
            return None

        def add(self, *_a, **_k):
            return None

    try:
        asyncio.new_event_loop().run_until_complete(se.run_draw(_D(), "site", "ann-1"))
    except Exception as exc:                        # noqa: BLE001 — 가짜 DB 후속 실패는 관심 밖
        assert "바뀌었습니다" not in str(exc), exc

    names = [e for e, _ in emitted]
    assert "DrawCommitmentRevealed" in names, (
        f"★공약 공개를 원장에 안 남긴다 — 사후 감사자가 대조할 것이 없다: {names}"
    )
    payload = next(p for e, p in emitted if e == "DrawCommitmentRevealed")
    allow = WHITELIST["DrawCommitmentRevealed"]
    for k in ("commit_hash", "beacon_round", "participants_hash", "pool_hash"):
        assert k in payload, f"{k} 를 안 싣는다: {sorted(payload)}"
        assert k in allow, f"★{k} 가 화이트리스트 밖이라 **기록되는 순간 버려진다**"
    assert "nonce" not in payload, "★nonce 를 원장에 실으면 누구나 사전 계산한다"


def test_already_assigned_units_are_excluded_from_the_population(monkeypatch):
    """★이미 배정된 세대는 모집단에서 빠지는가 — `_DB(assigned=…)` 를 **비어 있지 않게** 준다.

    R2 리뷰 MEDIUM-5: 이 라우트는 **한 번도 비어 있지 않은 값으로 태워진 적이 없어서**,
    쿼리를 깨도(스텁이 라우팅을 못 해도) 초록이었다. ***쓰이지 않는 분기는 잠금이 아니다.***
    """
    rev = _revealed(beacon_round=900)
    free = _run_draw(monkeypatch, rev)["assigned_unit"]["id"]
    # 그 세대를 「이미 배정됨」으로 두면 **다른 세대**가 나와야 한다
    again = _run_draw(monkeypatch, rev, db=_DB(assigned=[free]))["assigned_unit"]["id"]
    assert again != free, f"이미 배정된 세대가 또 배정됐다(이중배정): {free}"
    assert again in _POOL


# ── ⑯ ★내가 만든 회귀를 잠근다 — 타 현장·소프트삭제 세대 (R2 MAJOR-3) ──────
def test_foreign_site_unit_cannot_be_held(monkeypatch):
    """★모집단을 라이브 조회에서 공약 pool 로 바꾸면서 `site_id` 술어가 **사라졌다**.

    `set_pool` 이 타 현장 uuid 를 그대로 받아 저장했기 때문에, 공약 pool 에 그 id 가 들어가면
    **타 현장 세대가 HOLD** 됐다(이 저장소에 같은 클래스 IDOR 사고가 두 건 기록돼 있다).
    ***모집단을 바꾸면 그 모집단이 지키던 술어도 함께 옮겨야 한다.***
    """
    rev = _revealed(beacon_round=900)
    db = _DB()
    db.foreign = set(_POOL)                      # pool 전부가 타 현장이라면 **하나도 못 잡아야** 한다
    with pytest.raises(ValueError) as e:
        _run_draw(monkeypatch, rev, db=db)
    assert "남은 가용 세대가 없습니다" in str(e.value), str(e.value)
    assert not db.leaked, f"★타 현장 세대가 새어 나갔다: {db.leaked[:3]}"


def test_soft_deleted_unit_cannot_be_held(monkeypatch):
    """`CRUDBase.delete` 는 `deleted_at` 만 세우고 **`status` 는 안 건드린다** —
    즉 삭제된 세대가 `status='AVAILABLE'` 로 남는다. 술어가 없으면 그게 배정된다."""
    rev = _revealed(beacon_round=900)
    db = _DB()
    db.soft_deleted = set(_POOL)
    with pytest.raises(ValueError):
        _run_draw(monkeypatch, rev, db=db)
    assert not db.leaked, f"★삭제된 세대가 새어 나갔다: {db.leaked[:3]}"


def test_live_units_still_pass_control(monkeypatch):
    """대조군 — 정상 세대는 그대로 배정된다(⑯이 「늘 거부」가 아님을 가른다)."""
    out = _run_draw(monkeypatch, _revealed(beacon_round=900))
    assert out["assigned_unit"]["id"] in _POOL


# ── ⑰ ★`set_pool` 이 입력을 검증하는가 (공약 이전 층) ───────────────────────
def test_set_pool_rejects_units_outside_the_site():
    """★여기서 막지 않으면 **뒤의 어느 층도 그 사실을 모른다**."""
    class _R:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _D:
        def __init__(self, ok):
            self.ok = ok

        async def execute(self, stmt, params=None):
            q = " ".join(str(stmt).split())
            if q.startswith("SELECT id FROM sales_unit_inventory"):
                return _R([(u,) for u in self.ok])
            return _R([])

        async def commit(self):
            return None

    loop = asyncio.new_event_loop()
    with pytest.raises(ValueError) as e:
        loop.run_until_complete(de.set_pool(_D(ok=["u1"]), "site", "g", ["u1", "남의-세대"]))
    assert "이 현장에 없거나 삭제된" in str(e.value), str(e.value)
    # 대조군 — 전부 이 현장 것이면 통과한다
    got = loop.run_until_complete(de.set_pool(_D(ok=["u1", "u2"]), "site", "g", ["u1", "u2"]))
    assert got["pool_size"] == 2, got


# ── ⑱ ★저장되는 pool 이 **정렬**돼 있는가(원장 재현성) ──────────────────────
def test_stored_pool_is_sorted_for_reproducible_hash(monkeypatch):
    """`pool_hash` 는 `",".join(pool)` 의 해시다 — **순서가 곧 값**이다.

    `sorted()` 를 `list()` 로 바꾸면 집합 순회 순서가 프로세스마다 달라져
    **같은 추첨의 원장 해시가 재현되지 않는다**(당첨자는 그대로라 눈에 안 띈다).
    """
    import hashlib

    out = _run_draw(monkeypatch, _revealed(beacon_round=900))
    meta = getattr(de, "_last_meta_for_test", {})
    pool = meta.get("pool")
    if pool is None:                                # meta 에 없으면 응답의 해시로 검산한다
        pool = sorted(_POOL)
    assert out["pool_hash"] == hashlib.sha256(",".join(sorted(pool)).encode()).hexdigest(), (
        "★기록된 pool_hash 가 **정렬된 pool** 의 해시가 아니다 — 프로세스마다 값이 달라진다"
    )


# ── ⑲ ★청약 공약 pool 이 **그 공고가 뽑는 타입**으로 좁혀졌는가 (R2 MAJOR-7) ──
def test_subscription_pool_is_scoped_to_the_drawn_unit_types():
    """★종전에는 **현장 전체 가용 세대**였다. 추첨은 신청이 있는 타입만 도는데 공약은 전부를 묶어,
    **무관한 세대 하나만 상태가 바뀌어도** 추첨이 영구 거부됐다(정상 업무가 전부 그 통로였다).
    ***위양성도 결함이다 — 게이트가 공격만 막고 정상 운영도 막으면 그건 결함이다.***
    """
    from app.services.sales.subscription import engine as se

    class _App:
        def __init__(self, i, type_id):
            self.id = f"app-{i}"
            self.unit_type_id = type_id

    class _Unit:
        def __init__(self, i, type_id):
            self.id = f"unit-{i}"
            self.type_id = type_id

    drawn, other = "TYPE-A", "TYPE-B"
    apps = [_App(1, drawn), _App(2, drawn)]
    units = {drawn: [_Unit(1, drawn), _Unit(2, drawn)], other: [_Unit(9, other)]}
    seen_types: list = []

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

    class _Res3:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

    class _D:
        async def execute(self, stmt, params=None):
            q = " ".join(str(stmt).split())
            if "sales_subscription_applications" in q or "unit_type_id" in q:
                return _Res3(apps)
            # 재고 조회 — WHERE 에 type_id IN 이 있으면 그 타입만, 없으면 전부(=결함 상태)
            if "type_id IN" in q or "type_id IN" in q.replace("  ", " "):
                seen_types.append("scoped")
                return _Res3(units[drawn])
            seen_types.append("site-wide")
            return _Res3(units[drawn] + units[other])

    roster, pool = asyncio.new_event_loop().run_until_complete(
        se.subscription_binding(_D(), "site", "ann"))
    assert len(roster) == 2, roster
    assert "unit-9" not in pool, (
        f"★공고가 뽑지 않는 타입의 세대가 공약에 묶였다 — 그 세대 상태가 바뀌면 "
        f"무관한 이유로 추첨이 영구 거부된다: {pool}"
    )
    assert seen_types and seen_types[-1] == "scoped", (
        f"★재고 조회가 타입으로 좁혀지지 않았다: {seen_types}"
    )


# ── ⑳ ★무효화는 **지우기 전에 기록**한다 ────────────────────────────────────
def test_void_records_before_deleting_and_requires_a_reason():
    """★무효화가 재공약을 가능하게 하는 유일한 경로다 — 그러므로 **흔적이 곧 방어**다.

    기록 없이 지우면 *"마음에 안 들어 다시 뽑았다"* 가 **사라진다.**
    """
    order: list[str] = []

    class _R:
        def first(self):
            return ("cafe" * 16, 900, "p" * 64, "u" * 64, "t0", None)

    class _Count:
        def first(self):
            return (3,)

    class _D:
        async def execute(self, stmt, params=None):
            q = " ".join(str(stmt).split())
            if "INSERT INTO sales_draw_commitment_voids" in q:
                order.append("record")
            elif "DELETE FROM sales_draw_commitments" in q:
                order.append("delete")
            elif "count(*)" in q:
                return _Count()
            return _R()

        async def commit(self):
            return None

    loop = asyncio.new_event_loop()
    # 사유가 없으면 거부
    with pytest.raises(ValueError) as e:
        loop.run_until_complete(cs.void_commitment(_D(), "s", "dongho", "r", reason="  "))
    assert "사유는 필수" in str(e.value), str(e.value)
    # 사유가 있으면 **기록 → 삭제** 순서
    order.clear()
    out = loop.run_until_complete(
        cs.void_commitment(_D(), "s", "dongho", "r", reason="선착순 계약으로 세대 변동"))
    assert order == ["record", "delete"], (
        f"★기록 없이 지웠거나 순서가 뒤집혔다: {order} — 지운 뒤 기록하면 그 사이 장애에 증거가 사라진다"
    )
    assert out["voided_commit_hash"], out
    assert out["void_count"] == 3, (
        f"★누적 무효화 횟수가 틀렸다({out.get('void_count')}) — 이 숫자가 곧 감시 지표다"
    )
