"""공개 비콘(drand)이 **실제로** 추첨 seed 를 바꾸는가 — Phase 1 잠금.

★**주입 가능한 fetcher** 로 짠다. 네트워크를 타면 CI 에서 **조용히 skip** 되고, 그러면
  「락이 있다」와 「락이 돈다」가 갈린다(이 저장소가 반복해 데인 자리다).
  라이브 대조는 `_workspace/PLAN_draw_multiparty_entropy_2026-09-13.md` §1 에 실측으로 적는다.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib

import pytest

from app.services.sales.draw import beacon, vrng

_API = "https://api.drand.sh"
_CF = "https://drand.cloudflare.com"
_API2 = "https://api2.drand.sh"          # ★api.drand.sh 와 **같은 운영자**의 예비


def _canned(values: dict[str, str], latest: int = 100):
    """`{엔드포인트: 랜덤값}` 을 돌려주는 가짜 fetcher. 목록에 없는 곳은 **죽는다**."""
    def fetch(url: str) -> dict:
        # 체인 해시가 URL 경로에 들어가므로 **접두 일치**로 운영자를 가른다.
        base = next((b for b in values if url.startswith(b + "/")), None)
        if base is None:
            raise OSError(f"연결 불가(가짜): {url}")
        assert f"/{beacon.CHAIN_HASH}/public/" in url, (
            f"★체인 해시가 URL 에 없다 — 엔드포인트가 자기 기본 체인을 준다: {url}"
        )
        tail = url.rsplit("/public/", 1)[1]
        rnd = latest if tail == "latest" else int(tail)
        return {"round": rnd, "randomness": values[base]}
    return fetch


# ── ① 두 곳이 갈리면 거부한다 (+ 같으면 통과하는 대조군) ────────────────────
def test_disagreeing_endpoints_are_refused():
    f = _canned({_API: "aa" * 32, _CF: "bb" * 32})
    with pytest.raises(beacon.BeaconError) as e:
        beacon.fetch_round(90, (_API, _CF), f)
    assert "다르다" in str(e.value), str(e.value)


def test_agreeing_endpoints_pass_control():
    """★대조군 — 갈릴 때만 거부하는지, 아니면 **항상** 거부하는지를 가른다.

    이것이 없으면 ①은 「비콘이 늘 죽어 있어서」 통과할 수 있다(공허한 참).
    """
    f = _canned({_API: "cc" * 32, _CF: "cc" * 32})
    got = beacon.fetch_round(90, (_API, _CF), f)
    assert got.randomness == "cc" * 32
    assert got.round == 90


# ── ② 「2곳」이 아니라 「서로 다른 운영자 2곳」이다 ──────────────────────────
def test_two_mirrors_of_one_operator_are_not_a_cross_check():
    """★가용성과 독립성은 **다른 축**이다. 같은 운영자 예비 두 곳이 같은 값을 주는 것은
    대조가 아니다 — 그 운영자가 거짓말하면 두 곳이 **함께** 거짓말한다."""
    f = _canned({_API: "dd" * 32, _API2: "dd" * 32})
    with pytest.raises(beacon.BeaconError) as e:
        beacon.fetch_round(90, (_API, _API2), f)
    assert "운영자" in str(e.value), str(e.value)
    # 대조군: 한 곳을 **다른 운영자**로 바꾸면 통과한다 ⇒ 거부 사유가 「개수」가 아니라 「운영자」다
    ok = beacon.fetch_round(90, (_API, _CF), _canned({_API: "dd" * 32, _CF: "dd" * 32}))
    assert ok.randomness == "dd" * 32


def test_operator_of_separates_the_two_operators():
    assert beacon.operator_of(_CF) != beacon.operator_of(_API)
    assert beacon.operator_of(_API2) == beacon.operator_of(_API), "같은 운영자로 세야 한다"


# ── ③ 아직 안 나온 라운드는 **몇 초 남았는지 말하며** 거부한다 ──────────────
def test_future_round_is_refused_with_the_remaining_seconds():
    f = _canned({_API: "ee" * 32, _CF: "ee" * 32}, latest=100)
    with pytest.raises(beacon.BeaconNotReadyError) as e:
        beacon.randomness_for(104, (_API, _CF), f)
    expect = 4 * beacon.ROUND_PERIOD_S
    assert e.value.seconds_remaining == expect, e.value.seconds_remaining
    assert str(expect) in str(e.value), (
        "★남은 시간이 **사람이 읽는 문구에도** 있어야 한다 — 「아직입니다」만 말하면 "
        "운영자는 언제 다시 올지 모르고 새로고침을 반복한다"
    )


def test_ready_round_passes_control():
    """대조군 — ③이 「늘 거부」가 아니라 **미래일 때만** 거부하는지 가른다."""
    f = _canned({_API: "ee" * 32, _CF: "ee" * 32}, latest=100)
    assert beacon.randomness_for(100, (_API, _CF), f) == "ee" * 32


def test_not_ready_is_a_distinct_exception_from_failure():
    """★「아직 시각이 안 됐다」와 「비콘 장애」가 **같은 신호면** 운영자가 기다리면 되는
    상황에서 장애 대응을 시작한다 — 한 신호가 두 사건을 덮는 클래스."""
    assert issubclass(beacon.BeaconNotReadyError, beacon.BeaconError)
    assert beacon.BeaconNotReadyError is not beacon.BeaconError
    dead = _canned({}, latest=100)                     # 전부 죽은 비콘
    with pytest.raises(beacon.BeaconError) as e:
        beacon.randomness_for(90, (_API, _CF), dead)
    assert not isinstance(e.value, beacon.BeaconNotReadyError), (
        "장애가 「아직 안 나왔다」로 둔갑하면 fail-closed 가 대기로 오독된다"
    )


# ── ④ 비콘을 못 가져오면 **거부**한다(조용히 진행 금지) ─────────────────────
def test_unreachable_beacon_refuses_instead_of_dropping_the_contribution():
    dead = _canned({})
    with pytest.raises(beacon.BeaconError):
        beacon.seed_contributions(90, (_API, _CF), dead)


# ── ⑤ ★비콘 값이 **실제로 seed 를 바꾼다** — 두 모집단 ──────────────────────
def test_beacon_value_actually_changes_the_draw():
    """★존재를 잠그지 말고 **효과**를 잠근다. 「기여값이 목록에 들어간다」가 아니라
    「그 값이 바뀌면 **뽑히는 대상이 바뀐다**」를 본다."""
    nonce = "ab" * 32
    pool = sorted(f"u-{i:02d}" for i in range(16))
    domain = "dongho:g:c"

    def draw_with(randomness: str, rnd: int = 90) -> str:
        f = _canned({_API: randomness, _CF: randomness})
        parts, _label = beacon.seed_contributions(rnd, (_API, _CF), f)
        key = vrng.seed_key(nonce, "g", "c", *parts)
        return vrng.pick(key, domain, pool)[0]

    # 같은 라운드·같은 값 → **같은 결과**(결정적 — 재현 가능해야 검증이 성립한다)
    assert draw_with("11" * 32) == draw_with("11" * 32)
    # 값이 다르면 **결과가 달라진다** — 여러 값을 태워 「우연히 같음」을 배제한다
    seen = {draw_with(f"{i:02x}" * 32) for i in range(1, 12)}
    assert len(seen) > 1, (
        f"★비콘 값을 11가지로 바꿔도 결과가 하나뿐이다({seen}) — 기여값이 seed 에 "
        "**닿지 않는다**(있는데 안 쓰이는 상태)"
    )
    # 라운드 번호만 달라도 기여값이 달라진다(값이 같아도 `drand:{round}:{값}` 이므로).
    # ★여기서 **뽑힌 결과**로 단언하지 않는다 — pool 16건이면 서로 다른 seed 라도 우연히 같은
    #   대상이 나올 수 있다(1/16). **기여값 문자열**을 단언하는 것이 옳은 축이다.
    a, _ = beacon.seed_contributions(90, (_API, _CF), _canned({_API: "11" * 32, _CF: "11" * 32}))
    b, _ = beacon.seed_contributions(91, (_API, _CF), _canned({_API: "11" * 32, _CF: "11" * 32}))
    assert a != b, "라운드 번호가 기여값에 안 들어간다 — 다른 라운드가 같은 seed 를 만든다"


def test_no_beacon_and_beacon_give_different_seeds():
    """★「비콘을 섞었다」가 **참인지** — 안 섞은 것과 결과가 같으면 배선이 죽은 것이다."""
    nonce = "ab" * 32
    with_parts, label_on = beacon.seed_contributions(
        90, (_API, _CF), _canned({_API: "11" * 32, _CF: "11" * 32}))
    assert vrng.seed_key(nonce, "g", *with_parts) != vrng.seed_key(nonce, "g")
    assert "미사용" not in label_on and "90" in label_on, label_on
    # ★비콘 없는 공약은 **말하는 것으로 끝내지 않고 거부**한다(리뷰 M-5/M-6):
    #   라벨만 바꾸면 `UPDATE … SET beacon_round=NULL` 한 줄이 곧 우회로다.
    with pytest.raises(beacon.BeaconError) as e:
        beacon.seed_contributions(None)
    assert "비콘 없이는 추첨하지 않습니다" in str(e.value), str(e.value)


# ── ⑥ 공약 시점에 라운드는 **미래**여야 한다 ────────────────────────────────
def test_target_round_refuses_a_non_positive_lead():
    with pytest.raises(beacon.BeaconError):
        beacon.target_round((_API, _CF), _canned({_API: "a" * 64, _CF: "a" * 64}), lead=0)


def test_target_round_is_in_the_future_control():
    f = _canned({_API: "a" * 64, _CF: "a" * 64}, latest=100)
    assert beacon.target_round((_API, _CF), f, lead=3) == 103


def test_commit_refuses_a_past_round():
    """★과거 라운드는 **이미 공개된 값**이라 공약 시점에 결과를 계산할 수 있다 —
    그러면 공약이 무의미하다. `commit_draw` 가 그것을 거부하는지 본다."""
    from app.services.sales.draw import commitment_store as cs

    class _Res:
        def first(self):
            return None

    class _DB:
        async def execute(self, *_a, **_k):
            return _Res()

        async def commit(self):
            return None

    f = _canned({_API: "a" * 64, _CF: "a" * 64}, latest=100)
    kw = {"participants": ["c1", "c2"], "pool_ids": ["u1", "u2"], "fetch": f}
    with pytest.raises(ValueError) as e:
        asyncio.new_event_loop().run_until_complete(
            cs.commit_draw(_DB(), "s", "dongho", "r", beacon_round=99, **kw))
    assert "이미 공개된" in str(e.value), str(e.value)
    # ★**등호 경계도 태운다** — `beacon_round == latest` 는 «지금 공개돼 있는» 라운드다.
    #   종전 락은 99(과거)와 101(미래)만 봐서 `<=` → `<` 변이가 **생존**했다(리뷰 MED-3).
    with pytest.raises(ValueError) as e2:
        asyncio.new_event_loop().run_until_complete(
            cs.commit_draw(_DB(), "s", "dongho", "r", beacon_round=100, **kw))
    assert "이미 공개된" in str(e2.value), str(e2.value)
    # 대조군 — 미래 라운드는 통과하고 **공개 반환에 라운드·지문이 실린다**(제3자 재현에 필요)
    got = asyncio.new_event_loop().run_until_complete(
        cs.commit_draw(_DB(), "s", "dongho", "r", beacon_round=101, **kw))
    assert got["participants_hash"] and got["pool_hash"], got
    assert got["beacon_round"] == 101, got
    assert "nonce" not in got, f"★공개 반환에 nonce 가 실리면 누구나 사전 계산한다: {got}"


# ── ⑦ 검증기의 **복제본**이 프로덕션과 같은 문자열을 만드는가 ───────────────
def test_verifier_builds_the_same_beacon_contribution():
    """★검증기는 저장소를 설치하지 않은 제3자용이라 프로덕션을 임포트할 수 없다 —
    **의도적 중복**이다. 형식이 갈리면 검증기는 *"결과가 다르다"*(=조작 의심)라고 말하는데
    실제로 다른 것은 **기여값 문자열**이다. ***가장 나쁜 종류의 거짓 신고다.***"""
    import importlib.util

    vp = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "verify_draw.py"
    assert vp.exists(), f"검증기를 못 찾았다: {vp}"
    spec = importlib.util.spec_from_file_location("verify_draw", vp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for rnd, value in ((90, "11" * 32), (6461127, "9cc4" + "0" * 60)):
        prod, _ = beacon.seed_contributions(
            rnd, (_API, _CF), _canned({_API: value, _CF: value}, latest=rnd))
        assert prod == [mod.beacon_contribution(rnd, value)], (
            f"프로덕션 {prod} ↔ 검증기 {mod.beacon_contribution(rnd, value)}"
        )
    # 검증기도 **운영자 2곳**을 요구하는가(한 곳만 보면 대조가 아니다)
    assert len({("cloudflare" if "cloudflare" in b else "drand.sh")
                for b in mod._BEACON_ENDPOINTS}) >= 2, mod._BEACON_ENDPOINTS


# ── ⑧ cloudflare 403 회귀 방지 — **User-Agent 를 실제로 싣는가** ────────────
def test_http_request_carries_a_user_agent():
    """★실측(2026-09-13): `drand.cloudflare.com` 은 기본 `Python-urllib` 를 **403** 으로 막고
    UA 를 주면 200 이다. UA 를 지우면 **운영자 한 곳이 통째로 죽어** 대조가 성립하지 않는다
    (그리고 그 증상은 「비콘 간헐 장애」로 **오진**된다 — 실제로 그럴 뻔했다)."""
    import urllib.request

    seen = {}

    class _Resp:
        def read(self):
            return b'{"round": 1, "randomness": "00"}'

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def _fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        return _Resp()

    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen
    try:
        beacon._http_json(f"{_CF}/public/1")
    finally:
        urllib.request.urlopen = orig
    assert seen.get("ua"), "★User-Agent 없이 요청한다 — cloudflare 가 403 으로 막는다"


# ── ⑨ 두 추첨 경로가 **같은 함수**를 통과하는가(한쪽만 빠지는 것 방지) ──────
@pytest.mark.parametrize("module_path", [
    "app/services/sales/draw/draw_engine.py",
    "app/services/sales/subscription/engine.py",
])
def test_both_draw_paths_go_through_seed_contributions(module_path):
    """★각 경로가 자기 `if beacon_round:` 를 쓰면 **한쪽만 조용히 비콘을 빼는** 경로가 생긴다.
    호출부를 **AST 로 파생**해 확인한다(문자열 grep 은 주석·독스트링에 뚫린다)."""
    root = pathlib.Path(__file__).resolve().parents[1]
    tree = ast.parse((root / module_path).read_text(encoding="utf-8"))
    calls = {
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "seed_contributions" in calls, f"{module_path} 가 공용 비콘 경로를 안 탄다: {sorted(calls)[:20]}"
    assert "reveal_commitment" in {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }, f"{module_path} 가 공약을 읽지 않는다"


# ── ⑩ 엔드포인트가 두 사건을 **다른 상태코드**로 가르는가 ───────────────────
@pytest.mark.parametrize(("path", "func"), [
    ("app/api/endpoints/sales/actions.py", "draw_run"),
    ("app/api/endpoints/sales/lifecycle_p5.py", "draw"),
])
def test_draw_endpoints_split_not_ready_from_failure(path, func):
    root = pathlib.Path(__file__).resolve().parents[1]
    tree = ast.parse((root / path).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func)
    codes: dict[str, int] = {}
    for h in (x for n in ast.walk(fn) if isinstance(n, ast.Try) for x in n.handlers):
        names = {m.id for m in ast.walk(h.type) if isinstance(m, ast.Name)} if h.type else set()
        if not names & {"BeaconError", "BeaconNotReadyError"}:
            continue
        for raise_ in (r for r in ast.walk(h) if isinstance(r, ast.Raise)):
            for c in ast.walk(raise_):
                if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "HTTPException" and c.args:
                    if isinstance(c.args[0], ast.Constant):
                        codes[sorted(names)[0]] = int(c.args[0].value)
    assert codes.get("BeaconNotReadyError") == 425, f"{func}: 대기를 425 로 안 준다 — {codes}"
    assert codes.get("BeaconError") == 503, f"{func}: 장애를 503 으로 안 준다 — {codes}"
    assert codes["BeaconNotReadyError"] != codes["BeaconError"], (
        "★두 사건이 같은 코드면 클라이언트가 가를 수 없다"
    )


# ── ⑪ 공약이 **라운드 없이** 만들어질 수 없는가 ─────────────────────────────
def test_commit_cannot_be_made_without_a_round():
    """★`beacon_round` 를 안 주면 **자동으로 미래 라운드를 잡고**, 비콘이 죽으면
    **공약 자체를 거부**한다 — 라운드 없는 공약을 남기면 그것이 조용한 우회로다."""
    from app.services.sales.draw import commitment_store as cs

    src = inspect.getsource(cs.commit_draw)
    assert "target_round" in src, "공약이 미래 라운드를 잡지 않는다"
    assert "beacon_round" in inspect.getsource(cs.public_commitment), (
        "공개 조회가 라운드를 안 준다 — 제3자가 재현할 수 없다"
    )


def test_reveal_records_the_reveal_time():
    """★`revealed_at` 은 **아무도 안 쓰던 칸**이었다(공개 API 가 늘 `null`). 시각이 있어야
    「공약이 추첨보다 앞섰다」를 말할 수 있다."""
    from app.services.sales.draw import commitment_store as cs

    src = inspect.getsource(cs.reveal_commitment)
    assert "revealed_at" in src and "UPDATE" in src, "공개 시각을 기록하지 않는다"
    assert "COALESCE" in src, "★재시도마다 시각이 뒤로 밀리면 증거가 흐려진다 — 첫 공개만 찍는다"


def test_chain_hash_is_pinned_and_matches_the_verifier():
    """★체인 해시를 URL 에 박지 않으면 엔드포인트가 **자기 기본 체인**을 준다. 그러면
    두 곳이 함께 다른 체인으로 갈아탈 때 교차 대조가 **눈이 먼다**."""
    import importlib.util

    assert len(beacon.CHAIN_HASH) == 64 and int(beacon.CHAIN_HASH, 16) >= 0, beacon.CHAIN_HASH
    assert "/public/" in beacon.public_url("https://x", "latest")
    assert beacon.CHAIN_HASH in beacon.public_url("https://x", "latest")

    vp = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "verify_draw.py"
    spec = importlib.util.spec_from_file_location("verify_draw_chain", vp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._CHAIN_HASH == beacon.CHAIN_HASH, (
        f"★검증기가 **다른 체인**을 본다 — 프로덕션 {beacon.CHAIN_HASH[:12]}… ↔ "
        f"검증기 {mod._CHAIN_HASH[:12]}… ⇒ 정직한 추첨도 「결과가 다르다」로 신고된다"
    )
