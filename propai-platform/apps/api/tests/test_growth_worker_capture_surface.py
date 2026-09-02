"""워커 수집 상태가 **프로세스 경계 밖으로** 나오는지 잠근다.

## 왜 필요한가 (실측 2026-09-02)

성장루프 큐는 **모듈 전역 deque**(프로세스 로컬)다. 그래서 arq 워커가 담은 이벤트의 깊이를
API 프로세스가 볼 방법이 없었고, `/growth/effectors` 의 `capture` 는 **API 자기 큐**만 말한다.

그 결과 **「워커가 안 비운다」와 「워커가 비울 게 없다」가 같은 관측(0)** 이었다.
동료 세션 `development-ai-62` 가 `#928`(워커 배수) 배포 후 그것을 실측으로 확인했다 —
워커 이벤트는 효과기 발화 때만 생기는데 효과기가 침묵이라 **flush 배선을 태울 수 없었다**
(출처: 그쪽 측정이고 내 관측이 아니다).

★그리고 그 침묵은 `#928` 하나가 아니라 **효과기 팔 전체**의 검증을 막는다.

## ★세 모집단 — 둘로 만들면 「표면이 죽은 것」이 「정상 유휴」로 읽힌다

    깊이 0 · `at` 갱신됨   → 비울 게 없다(정상 유휴)
    깊이 N · `at` 정지     → 안 비운다(고장)
    ★행 자체가 없음        → 관측이 안 온다(워커·발행 부재)
"""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path

import pytest

from app.services.growth import capture_service as cs

_SRC = Path(cs.__file__)


@pytest.fixture(autouse=True)
def _clean():
    cs._reset_stats_for_test()
    yield
    cs._reset_stats_for_test()


class _Store:
    """`set_setting` 이 실제로 쓰는 SQL 을 받아 두는 가짜 세션(그 층을 우회하지 않는다)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def __call__(self):
        outer = self

        class _Db:
            async def execute(self, *a, **k):
                params = a[1] if len(a) > 1 else k.get("params")
                if "platform_settings" in str(a[0] if a else ""):
                    outer.rows.append(dict(params or {}))

            async def commit(self): return None
            async def rollback(self): return None

        class _Ctx:
            async def __aenter__(self): return _Db()
            async def __aexit__(self, *a): return False

        return _Ctx()


def _published(store: _Store) -> dict:
    import json
    assert store.rows, "★발행이 한 건도 안 나갔다 — 조회기가 죽었거나 배선이 끊겼다"
    return json.loads(store.rows[-1]["v"])


# ═══════════════════════════════════════════════════════════════════════════
# 1. ★세 모집단이 **서로 다른 답**을 낸다
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_three_populations_are_distinguishable() -> None:
    """★①비울 게 없다 ②안 비운다 ③관측이 안 온다 — 셋이 갈려야 한다.

    되살리는 변이: `at` 을 payload 에서 빼면 ①과 ②가 **구별 불가**가 되어 죽는다.
    """
    # ① 깊이 0 + 시각 있음
    s1 = _Store()
    await cs.publish_capture_status(s1, scope="worker")
    p1 = _published(s1)
    assert p1["depth"] == 0
    assert p1.get("at"), "★시각이 없다 — 「비울 게 없다」와 「멈췄다」를 못 가른다"

    # ② 깊이 N + 시각 있음(쌓이는 중)
    s2 = _Store()
    for i in range(7):
        cs._QUEUE.append({"event_id": f"e{i}", "event_type": "t", "created_at": None})
    await cs.publish_capture_status(s2, scope="worker")
    p2 = _published(s2)
    assert p2["depth"] == 7, "★깊이가 안 실린다 — 「안 비운다」를 말할 수 없다"

    # ★①과 ②가 **실제로 갈렸는가**(두 모집단 대조 — 같지 않아야 한다)
    assert p1["depth"] != p2["depth"], "★두 모집단이 안 갈렸다 = 공허한 초록"

    # ③ ★**관측이 끊기면 행이 스스로 사라진다** — TTL 이 그것을 만든다.
    #
    #   ★★종전 이 자리는 `s3 = _Store(); assert not s3.rows` 였다. **프로덕션 심볼을
    #     하나도 참조하지 않는 항진명제**라 어떤 변경으로도 실패할 수 없었다(파서 확인:
    #     참조 이름이 `_Store`·`s3`·`.rows` 뿐). **공허한 단언을 경계하는 문서를 쓰던
    #     같은 세션에 내가 공허한 단언을 썼다.**
    #
    #   ★그리고 그것은 **설계 결함**이기도 했다: TTL 이 없으면 행이 한 번 쓰이면
    #     영영 안 사라져(`clear_setting` 은 치유 롤백 전용) 「워커 사망」이 **행 부재로
    #     나타나지 못하고** 낡은 값으로 남는다 = ①과 구별 불가.
    #   → **TTL 을 걸어 실제로 만료되게** 하고, 그 만료를 **`/heal-log` 의 필터와 같은 식**으로 판정한다.
    from datetime import UTC, datetime

    ttl = s1.rows[-1]["ttl"]
    assert ttl is not None, "★TTL 이 없다 — 행이 영영 안 사라져 세 번째 모집단이 성립 안 한다"
    now = datetime.now(UTC)
    assert ttl > now, "★TTL 이 이미 지났다 — 갓 쓴 행이 곧바로 사라진다"
    # ★`/heal-log` 의 필터: `ttl_expires_at IS NULL OR > now()`. 관측이 끊긴 뒤를 흉내 낸다.
    dead = now + timedelta(seconds=cs._PUBLISH_TTL_S + 1)
    assert not (ttl is None or ttl > dead), (
        "★관측이 끊겨도 행이 남는다 — 「워커 사망」이 「정상 유휴」와 구별되지 않는다"
    )


@pytest.mark.asyncio
async def test_scope_separates_processes() -> None:
    """★`scope` 가 프로세스를 가른다 — 워커 값이 API 값을 덮어쓰면 안 된다."""
    s = _Store()
    await cs.publish_capture_status(s, scope="worker")
    await cs.publish_capture_status(s, scope="api")
    scopes = [r["s"] for r in s.rows]
    assert scopes == ["worker", "api"], f"★scope 가 안 실린다: {scopes}"
    keys = {r["k"] for r in s.rows}
    assert keys == {cs.CAPTURE_STATUS_SETTING_KEY}, f"★키가 갈렸다: {keys}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. ★계약은 **파생**한다 — 손 목록은 상한이 된다
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_payload_is_derived_from_capture_status_not_hand_listed() -> None:
    """★발행 payload 가 `capture_status()` **전 키**를 싣는다(+ `at`).

    ★오늘 `#901` 에서 **손으로 고른 모집단이 상한**이 되어 HTTP 500 을 놓쳤다.
      그래서 여기서는 기대값을 **구현에서 파생**시킨다 — 새 키가 생기면 자동으로 태워진다.
    """
    s = _Store()
    await cs.publish_capture_status(s, scope="worker")
    got = set(_published(s))
    # ★계약 = `capture_status()` **전 키**(단 `scope` 는 이름 충돌로 `counter_scope` 로 개명)
    #   + 발행이 덧붙이는 둘(`at` · `producer_build_id`).
    #   ★**손으로 나열하지 않는다** — `capture_status()` 에 키가 생기면 자동으로 태워진다.
    base = set(cs.capture_status())
    # ★판별 3종은 **짧은 이름**으로 실린다(jsonb 정렬에서 앞자리를 얻기 위해 — 위 참조).
    #   나머지는 원본 이름 그대로. `scope` 는 바깥 scope 와 충돌해 `counter_scope` 로 개명.
    expected = (base - {"scope", "queue_depth", "lost_total"}) | {
        "counter_scope", "at", "depth", "lost", "build",
    }
    # ★대조군 — 파생이 죽으면(빈 집합) 아래가 공허해진다
    assert len(base) >= 5, f"★capture_status 파생이 죽었다: {base}"
    assert got == expected, f"★계약 불일치 — 빠짐 {expected - got} · 남음 {got - expected}"

    # ★★**바깥 `scope` 와 안쪽 계수기 범위가 같은 이름이면 안 된다** — 같은 화면에
    #   나란히 뜨는데 뜻이 다르다(프로세스 vs 계수기 범위). 렌즈가 실제 응답에서 잡았다.
    assert "scope" not in got, "★안쪽 scope 가 바깥 scope 와 이름이 충돌한다"


# ═══════════════════════════════════════════════════════════════════════════
# 3. ★★순환 금지 — **측정 대상으로 측정하지 않는다**
# ═══════════════════════════════════════════════════════════════════════════
def test_publish_path_never_uses_record_event() -> None:
    """★큐 깊이를 `record_event` 로 보고하면 **자기가 재려는 큐에 자기 관측을 넣는** 순환이다.

    ①유실이 나면 **관측치가 먼저 사라진다**(가장 필요한 순간에 없다)
    ②유휴일 때 *"비었다"* 와 *"관측이 안 왔다"* 를 **못 가른다**(판별력 자체)

    ★`grep` 이 아니라 파서로 본다 — 이 파일의 설명 문장에 그대로 걸린다.
    """
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "publish_capture_status"), None)
    assert fn is not None, "★발행 함수를 못 찾았다 — 추출기가 죽었다(위반 아님)"

    called = {getattr(c.func, "attr", getattr(c.func, "id", None))
              for c in ast.walk(fn) if isinstance(c, ast.Call)}
    # ★양성 대조군 먼저 — 추출기가 살아 있나(빈 집합이면 아래 단언이 공허하다)
    assert "set_setting" in called, f"★발행 경로가 set_setting 을 안 쓴다: {sorted(x for x in called if x)}"
    assert "record_event" not in called, "★측정 대상으로 측정하고 있다(순환)"
    assert "record_fallback" not in called, "★측정 대상으로 측정하고 있다(순환)"


def test_timestamp_lives_in_the_payload_not_updated_at() -> None:
    """★시각은 **payload 안**에 있어야 한다.

    `/growth/heal-log` 의 `active_flags` 는 `key·scope·value·ttl_expires_at·updated_by` 만
    내보내고 **`updated_at` 은 안 준다**(실측). `updated_at` 에 기대면 **밖에서**
    「멈췄다」를 못 본다 — 세 모집단의 ②가 사라진다.
    """
    from app.routers.growth import ActiveFlagOut
    assert "updated_at" not in ActiveFlagOut.model_fields, (
        "★응답이 updated_at 을 내보내게 됐다면 이 설계 근거를 다시 재라"
    )
    assert "value" in ActiveFlagOut.model_fields


# ═══════════════════════════════════════════════════════════════════════════
# 4. ★관측이 배수를 죽이지 않는다
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_publish_failure_does_not_raise() -> None:
    """★발행이 터져도 **예외를 올리지 않는다** — 관측이 배수를 막으면 본말전도다."""
    class _Boom:
        def __call__(self):
            raise RuntimeError("설정 저장소 장애")

    ok = await cs.publish_capture_status(_Boom(), scope="worker")
    assert ok is False, "★실패를 성공으로 보고했다"


def test_worker_publishes_under_its_own_scope() -> None:
    """★워커가 **자기 scope** 로 발행한다 — API 값과 안 섞인다.

    되살리는 변이: `publish_scope="worker"` 를 지우면 워커가 `api` 로 발행해
    **두 프로세스가 한 행을 덮어쓴다**(그러면 깊이가 누구 것인지 알 수 없다).
    """
    # ★깊이에 의존하지 않는다 — `apps` 디렉토리를 **이름으로** 거슬러 찾는다.
    #   `parents[N]` 은 임포트 문맥에 따라 다른 곳을 가리킨다(실측으로 한 번 틀렸다).
    apps = next((q for q in _SRC.parents if q.name == "apps"), None)
    assert apps is not None, f"★apps 디렉토리를 못 찾았다: {_SRC}(위반 아님)"
    w = apps / "worker" / "main.py"
    assert w.is_file(), f"★워커 진입점을 못 찾았다: {w}(위반 아님)"
    tree = ast.parse(w.read_text(encoding="utf-8"))
    scopes = [
        kw.value.value
        for c in ast.walk(tree) if isinstance(c, ast.Call)
        and getattr(c.func, "attr", getattr(c.func, "id", None)) == "start_flush_loop"
        for kw in c.keywords
        if kw.arg == "publish_scope" and isinstance(kw.value, ast.Constant)
    ]
    assert scopes == ["worker"], f"★워커가 자기 scope 로 발행하지 않는다: {scopes}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. ★★배선 — **루프가 실제로 발행하는가**(함수를 직접 부르는 것으로는 안 잠긴다)
#
# 독립 적대 렌즈 실측(2026-09-02): 발행 호출 한 줄을 `pass` 로 지워도
# **성장루프 테스트 219건 전부 초록**이었다. 위 테스트들이 전부
# `publish_capture_status` 를 **직접** 부르고, **루프를 태우는 것이 하나도 없었기** 때문이다.
# → 저장소 교훈 *"함수 안에만 변이를 넣으면 배선은 무잠금"* 의 정확한 재발이다.
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_the_flush_loop_actually_publishes_with_its_own_scope(monkeypatch) -> None:
    """★루프를 **돌려서** 발행이 나가는지, 그리고 **그 프로세스의 scope** 로 나가는지 본다.

    되살리는 변이(둘 다 이 테스트가 죽인다):
      · 루프에서 `publish_capture_status(...)` 호출을 지운다 → 발행 0건
      · `scope=publish_scope` → `scope="api"` 로 고정 → 워커 행이 API 를 덮어쓴다
    """
    import asyncio

    monkeypatch.setattr(cs, "_FLUSH_INTERVAL_S", 0.01, raising=False)
    store = _Store()
    ctx: dict = {}
    assert cs.start_flush_loop(ctx, store, publish_scope="worker") is True
    try:
        for _ in range(200):
            if store.rows:
                break
            await asyncio.sleep(0.01)
        # ★①효과: 루프가 **실제로** 발행했다(직접 호출이 아니다)
        assert store.rows, "★루프가 발행하지 않는다 — 배선이 끊겼다"
        # ★②그 발행이 **이 프로세스의 scope** 를 달고 나간다
        scopes = {r["s"] for r in store.rows}
        assert scopes == {"worker"}, f"★루프가 남의 scope 로 발행한다: {scopes}"
    finally:
        t = ctx.get(cs._FLUSH_TASK_CTX_KEY)
        if t is not None:
            t.cancel()


@pytest.mark.asyncio
async def test_api_and_worker_do_not_clobber_each_other(monkeypatch) -> None:
    """★기본값이 `worker` 로 바뀌면 **API 가 워커 행을 덮어쓴다** — 두 모집단으로 잠근다.

    `(key, scope)` 가 유일키라 scope 가 같아지는 순간 **한 행을 두 프로세스가 공유**하고,
    그러면 화면의 깊이가 **누구 것인지 알 수 없다.**
    """
    import asyncio

    monkeypatch.setattr(cs, "_FLUSH_INTERVAL_S", 0.01, raising=False)
    store = _Store()
    a: dict = {}
    b: dict = {}
    cs.start_flush_loop(a, store)                            # 기본값 = api
    cs.start_flush_loop(b, store, publish_scope="worker")
    try:
        for _ in range(200):
            if {r["s"] for r in store.rows} >= {"api", "worker"}:
                break
            await asyncio.sleep(0.01)
        scopes = {r["s"] for r in store.rows}
        assert scopes == {"api", "worker"}, (
            f"★두 프로세스가 서로 다른 scope 로 안 쓴다: {scopes} — 한 행을 덮어쓴다"
        )
    finally:
        for c in (a, b):
            t = c.get(cs._FLUSH_TASK_CTX_KEY)
            if t is not None:
                t.cancel()


# ═══════════════════════════════════════════════════════════════════════════
# 6. ★★★화면 — **판별 필드가 사람에게 닿는가**
#
# 독립 적대 렌즈 실측: `summarizeParams` 는 **삽입 순서로 앞 4키만** 그린다.
# `at` 이 16키 중 15번째라 **화면에 아예 안 나왔고**, 「정상 유휴」와 「워커 사망」이
# **바이트 동일**한 문자열로 렌더됐다 — 이 기능이 존재하는 이유가 그 둘을 가르는 것인데.
# ★**프론트를 「범위 밖」으로 뺐더니, 그 전제가 검증되는 유일한 곳을 뺀 것이었다.**
# ═══════════════════════════════════════════════════════════════════════════
def _dashboard_src() -> str:
    tsx = next(q for q in _SRC.parents if q.name == "apps") / "web" / "components" / "settings" / "GrowthDashboard.tsx"
    assert tsx.is_file(), f"★화면 소스를 못 찾았다: {tsx}(위반 아님)"
    return tsx.read_text(encoding="utf-8")


def _render_cap() -> int:
    """플래그 표면의 키 상한을 **TSX 소스에서 파생**한다(손으로 안 적는다).

    ★★**추출기는 하나여야 한다.** 리베이스 전 이 파일에는 상한 추출기가 **둘**이었고,
      `#947` 이 상한을 인자화하자 **한쪽만 낡아** 「추출기가 죽었다」로 빨개졌다.
      사본이 갈리면 하나가 낡는다 — 그 실증이 바로 이 함수였다. 그래서 합쳤다.

    ★상한은 **호출부마다 다르다**: 액션 `params` 는 기본값, 플래그 `value` 는
      `FLAG_VALUE_RENDER_CAP`. 이 파일이 흉내 내는 것은 **플래그 표면**이다.
    """
    import re

    src = _dashboard_src()
    m = re.search(r"const\s+FLAG_VALUE_RENDER_CAP\s*=\s*(\d+)", src)
    assert m, "★화면의 키 상한을 못 찾았다 — 추출기가 죽었다(위반 아님)"
    # ★★**배선까지 확인한다**(동료 세션 development-ai-62 가 건 축) — 상한 상수가 있어도
    #   플래그 소비처가 그것을 **안 넘기면** 이 흉내는 화면과 **다른 것**을 그린다.
    #   ★복제본 락을 없앨 수 없을 때, **어긋남을 감지하는 축**을 거는 것이 정답이다.
    assert re.search(r"summarizeParams\(f\.value,\s*FLAG_VALUE_RENDER_CAP\)", src), (
        "★플래그 표면이 그 상한을 안 쓴다 — 이 흉내가 화면과 다른 것을 그린다(추출기 사망)"
    )
    return int(m.group(1))


def _expected_payload_keys() -> set[str]:
    """발행 payload 의 키 — `capture_status()` 에서 **파생**한다."""
    base = set(cs.capture_status())
    return (base - {"scope", "queue_depth", "lost_total"}) | {
        "counter_scope", "at", "depth", "lost", "build",
    }


def _as_stored(payload: dict) -> dict:
    """**저장소를 왕복한 뒤의 키 순서**로 바꾼다 — `jsonb` 는 삽입 순서를 안 지킨다.

    ★★이 함수가 없어서 **라이브에서 결함이 남았다**(2026-09-02 실측).
      종전 렌더 락은 **Python dict(삽입 순서)** 를 그려 봤고, 그래서
      *"판별 필드를 앞에 넣었다"* 가 초록이었다. 그런데 Postgres `jsonb` 는
      **(키 길이, 바이트순)** 으로 재정렬해 저장하므로 그 처방이 **저장을 통과하며 무효화**됐다.

    ★규칙이 맞다는 근거는 **라이브 실측**이다 — 예측과 실제가 정확히 일치했다:
        at(2) · flushed(7) · requeued(8) · max_queue(9) · lost_total(10) · flush_limit(11)
      (`test_jsonb_ordering_model_matches_the_measured_live_order` 가 이 규칙을 따로 잠근다.)

    ★자문: *"내 락이 태우는 값이 **저장소를 왕복한 값**인가, 그 전의 값인가?"*
    """
    return {k: payload[k] for k in sorted(payload, key=lambda k: (len(k), k))}


def test_jsonb_ordering_model_matches_the_measured_live_order() -> None:
    """★위 모델이 **실제 관측**과 같은지 따로 잠근다 — 모델도 검증 대상이다.

    아래는 2026-09-02 12:41Z 라이브 `/growth/heal-log` 에서 **실제로 관측된** 앞 6키다.
    모델이 이것을 재현하지 못하면 위 렌더 락 전체가 **틀린 전제** 위에 선다.
    """
    observed_first_6 = ["at", "flushed", "requeued", "max_queue", "lost_total", "flush_limit"]
    # 그 시점 payload 가 갖고 있던 키(짧은 이름 도입 **전** 판)
    keys_then = [
        "at", "queue_depth", "lost_total", "producer_build_id", "max_queue", "flush_limit",
        "max_sustained_per_sec", "dropped_overflow", "dropped_after_retry", "requeued",
        "flush_failures", "flushed", "cancelled_requeued", "consecutive_failures",
        "max_flush_retry", "counter_scope", "loss_rate_pct",
    ]
    modeled = list(_as_stored(dict.fromkeys(keys_then, 0)))[:6]
    assert modeled == observed_first_6, (
        f"★jsonb 정렬 모델이 라이브 관측과 다르다\n  모델 {modeled}\n  관측 {observed_first_6}"
    )


def _render_like_dashboard(payload: dict, cap: int | None = None) -> str:
    """`GrowthDashboard.summarizeParams` 의 규칙을 **소스에서 파생**해 흉내 낸다.

    ★상한(4)을 손으로 적지 않는다 — TSX 에서 뽑는다. 화면이 6개로 늘면 이 테스트도 따라간다.
    """
    import json

    # ★**추출·배선 확인은 `_render_cap()` 하나가 한다** — 여기서 다시 뽑지 않는다.
    #   종전엔 이 파일에 추출기가 **둘**이었고 `#947` 이 상한을 인자화하자 **한쪽만 낡았다.**
    #   *"사본이 갈리면 하나가 낡는다"* 의 실증이 이 파일 자신이었다.
    #
    # ★상한은 기본적으로 **소스에서 파생**한다. 주입(`cap=`)은 **두 갈래를 다 태우기 위한 것**이고
    #   화면 값을 우회하려는 것이 아니다 — 파생 경로는 아래 단언들이 그대로 태운다.
    if cap is None:
        cap = _render_cap()

    # ★**이 흉내가 잠그는 것과 안 잠그는 것**(변이 실측 2026-09-02 — 점수 부풀리기 방지):
    #     CAUGHT  상수 이름 변경 · **배선 제거** → 판정 거부(추출기 사망)
    #     SURVIVED 상한 40→4     — 이 테스트의 단언은 «유휴 ≠ 쌓임» 이고 `at`(2글자)이 항상
    #                              첫째라 상한이 4여도 둘은 갈린다. **구멍이 아니라 범위 밖**이다
    #     SURVIVED `외 N종` 제거 — 상한 40 에 17키라 여기서는 절단 자체가 안 난다
    #   위 두 축은 **프론트 락**이 잡는다(`GrowthDashboard.flagValueTruncation.test.tsx` —
    #   17키가 다 보이는가 · 상한 초과 시 버린 수를 말하는가). 여기서 다시 잠그지 않는다.
    parts: list[str] = []
    # ★두 축을 **합성**한다(양쪽 다 필요하다):
    #   ①`_as_stored` — 저장소 왕복 후의 **jsonb 키 순서**(삽입 순서가 아니다)
    #   ②`shown` 을 루프 **앞**에서 만든다 — 그래야 아래 `rest` 가 「보여 줄 수 있었는데
    #     안 보여 준 수」가 된다. 루프 안에서 `continue` 하면 **빈 칸 수가 섞여** 거짓말이 된다
    #     (동료 세션 development-ai-62 지적).
    shown = [(k, v) for k, v in _as_stored(payload).items() if v is not None]
    for k, v in shown:
        if len(parts) >= cap:
            break
        parts.append(f"{k} {json.dumps(v) if isinstance(v, (dict, list)) else v}")
    out = " · ".join(parts)
    # ★잘라낸 몫을 **말한다** — 화면이 그렇게 바뀌었다(`GrowthDashboard.summarizeParams`).
    #   이 흉내가 그것을 안 따라가면 "화면과 같다" 는 전제가 거짓이 된다.
    rest = len(shown) - len(parts)
    return f"{out} 외 {rest}종" if rest > 0 else out


@pytest.mark.asyncio
async def test_the_discriminating_field_survives_the_dashboard_truncation() -> None:
    """★①정상 유휴와 ②쌓이는 중이 **화면에서 서로 다르게** 보인다.

    ★★**프로덕션이 만든 payload 를 태운다 — 손으로 만든 dict 가 아니다.**
      종전 이 테스트는 리터럴 dict 를 그려 봤다. 그래서 프로덕션에서 `at` 을 통째로
      빼는 변이가 **SURVIVED** 했다(내 변이 배터리가 잡았다) — 락이 **사본**을 태우고
      있었고, 정작 **키 순서를 만드는 코드**는 한 번도 안 태웠다.
      ★이 파일이 잡으려는 결함이 바로 그것(판별 필드가 순서 때문에 잘림)인데
        **순서를 만드는 쪽을 안 보고 있었다.**

    되살리는 변이: payload 에서 `at` 을 빼거나 뒤로 밀면 앞 4키가 정적 상수로 채워져
    두 모집단이 **같은 문자열**이 된다 → 죽는다.
    """
    # ★프로덕션 경로로 두 모집단을 **실제로 만든다**
    s_idle = _Store()
    await cs.publish_capture_status(s_idle, scope="worker")
    idle = _published(s_idle)

    s_pile = _Store()
    for i in range(412):
        cs._QUEUE.append({"event_id": f"e{i}", "event_type": "t", "created_at": None})
    await cs.publish_capture_status(s_pile, scope="worker")
    piling = _published(s_pile)

    # ★대조군 — 두 모집단이 실제로 갈렸는가(안 갈렸으면 아래 비교가 공허하다)
    assert idle["depth"] != piling["depth"], "★두 모집단이 안 갈렸다"

    r_idle, r_piling = _render_like_dashboard(idle), _render_like_dashboard(piling)
    # ★대조군 — 렌더가 아무것도 안 만들면 아래 비교가 공허하다
    assert r_idle and r_piling, "★렌더가 비었다 — 흉내가 죽었다(위반 아님)"
    assert r_idle != r_piling, (
        f"★두 모집단이 **화면에서 구별되지 않는다**\n  ①{r_idle}\n  ②{r_piling}"
    )
    # ★그리고 **판별 필드 자체**가 잘려 나가지 않았는가
    assert "at " in r_idle, f"★시각이 화면에서 잘렸다: {r_idle}"
    assert "depth " in r_piling, f"★깊이가 화면에서 잘렸다: {r_piling}"


# ═══════════════════════════════════════════════════════════════════════════
# 7. ★★**저장소 왕복** — 리터럴 dict 로는 절대 안 잡히는 것을 잡는다
#
# 동료 세션 development-ai-62 와 왕복해 굳힌 축이다(그쪽 실측이 근거를 만들었다).
# 내 종전 락은 **Python dict(삽입 순서)** 를 그려 봤고, 그래서
# *"판별 필드를 앞에 넣었다"* 가 초록인 채 **라이브에서는 잘려 나갔다.**
# ═══════════════════════════════════════════════════════════════════════════
def _round_trip(payload: dict) -> dict:
    """**저장 → 조회**를 흉내 낸다: 직렬화 → `jsonb` 키 재정렬 → 역직렬화.

    ★리터럴 dict 를 그려 보는 것과 **결과가 다르다** — 그 차이가 이 파일이 존재하는 이유다.
    """
    import json as _json

    return _as_stored(_json.loads(_json.dumps(payload, default=str)))


@pytest.mark.asyncio
async def test_discriminating_fields_survive_a_full_storage_round_trip() -> None:
    """★**왕복 뒤에도** 판별 필드가 화면에 남는가 — 삽입 순서가 아니라 저장 결과로 본다.

    되살리는 변이: 판별 필드 이름을 길게 되돌리면(`depth`→`queue_depth`) 죽는다.
    """
    s = _Store()
    await cs.publish_capture_status(s, scope="worker")
    stored = _round_trip(_published(s))

    cap = _render_cap()
    visible = [k for k in list(stored) if stored[k] is not None][:cap]
    # ★대조군 — 화면 상한을 소스에서 못 읽었으면 아래가 공허하다
    assert cap >= 1, f"★화면 상한을 못 읽었다: {cap}(위반 아님)"
    assert "at" in visible, f"★시각이 왕복 뒤 잘렸다: {visible}"
    assert "depth" in visible, f"★깊이가 왕복 뒤 잘렸다: {visible}"


@pytest.mark.asyncio
async def test_screen_either_shows_everything_or_says_how_many_it_hid() -> None:
    """★★**파티션형 — 양방향으로 건다.** 상한만 걸면 하한이 0 으로 붕괴한다.

    종전 이 락은 `안 보이는 키 <= 13` 한 방향이었다. 그런데 `#947` 이 상한을 **40** 으로
    올리자 `17 − 40 = −23` 이라 **항상 참** — **판별력이 0** 이 됐다(동료 세션이 그 자리를
    짚어 줬고, 나도 계산으로 확인했다).

    ★이 저장소가 이름 붙여 둔 형태다: *"경계를 걸면 양방향으로"* — 상한만 걸었더니
      하한이 0 으로 붕괴해 **프로덕션에서 대화 영역이 0px** 이 된 전례가 있다.

    두 갈래가 **각각 다른 답**을 낸다:

        cap >= 보여줄키수  →  숨긴 것이 **0** 이어야 한다(전부 보인다)
        cap <  보여줄키수  →  숨긴 수가 **정확히 그 차이**이고, 화면이 **그 수를 말한다**

    되살리는 변이: 상한을 다시 작게 하면 두 번째 갈래로 넘어가고, 그때 화면이
    `외 N종` 을 안 말하면 죽는다.
    """
    s = _Store()
    await cs.publish_capture_status(s, scope="worker")
    stored = _round_trip(_published(s))
    # ★분모는 **보여 줄 수 있었던 것**(non-null)이다 — 빈 칸을 섞으면 「숨긴 수」가 거짓이 된다.
    shown_keys = [k for k, v in stored.items() if v is not None]

    # ★대조군 — 모집단이 비면 아래가 공허하다
    assert len(shown_keys) >= 5, f"★보여 줄 키가 {len(shown_keys)}개뿐 — 파생이 죽었다(위반 아님)"

    # ★★**두 갈래를 다 태운다** — 라이브 상한(40)이 키 수(17)보다 커서 ②갈래가
    #   **도달 불가**였다(실측). **도달 불가한 갈래는 공허하다.** 그래서 상한을 주입해
    #   양쪽을 같은 실행에서 본다.
    n = len(shown_keys)

    # ①전부 보인다 — 숨긴 것이 없고 판별 필드가 다 보인다
    wide = _render_like_dashboard(stored, cap=n + 5)
    assert "외 " not in wide, f"★다 보이는데 「외 N종」이 붙었다: {wide[-40:]}"
    for k in ("at", "depth", "lost"):
        assert f"{k} " in wide, f"★{k} 가 안 보인다: {wide[:120]}"

    # ②잘렸다면 **몇 개 잘렸는지 말해야** 한다(조용한 절단 금지)
    narrow = _render_like_dashboard(stored, cap=3)
    assert f"외 {n - 3}종" in narrow, (
        f"★{n - 3}개를 숨기고도 **말하지 않는다**(조용한 절단): {narrow[-60:]}"
    )

    # ★대조군 — 두 갈래가 **실제로 다른 답**을 냈는가(안 갈리면 공허하다)
    assert wide != narrow, "★두 갈래가 같은 답을 냈다 = 상한 주입이 안 먹었다"

    # ★그리고 **라이브 상한**에서 지금 조용히 잘리는 것이 없는지 따로 본다
    live_cap = _render_cap()
    assert live_cap >= n or f"외 {n - live_cap}종" in _render_like_dashboard(stored), (
        f"★라이브 상한 {live_cap} 에서 {n - live_cap}개가 조용히 잘린다"
    )


def test_the_axis_this_file_does_not_lock_is_locked_by_the_front_test() -> None:
    """★★**이 파일이 안 잡는 축**을 명시하고, **그 축을 잡는 락이 실재함**을 확인한다.

    ## 이 파일이 **안 잡는 것**

    위 `_render_like_dashboard` 는 화면을 **파이썬으로 흉내 낸 사본**이다. 그래서
    `외 N종` 접미를 **스스로 만들어 붙인다** — 즉 **TSX 에서 그 접미를 지워도 이 파일은
    모른다.** 복제본 락의 남은 구멍이고, 여기서 잡을 수 없다.

    ## 그 축은 **프론트 락**이 잡는다 (동료 세션 development-ai-62 가 실측)

        외 N종 접미 제거(TSX)            → CAUGHT
        rest 를 0 으로 고정(같은 축 다른 형태) → CAUGHT

    ★**같은 축을 두 형태로** 넣은 것이 중요하다 — 하나만 넣으면 *"그 한 형태만 잡는 락"*
      일 수 있다(문구를 지우는 것과 계산을 죽이는 것은 다르다).

    ## ★왜 주석이 아니라 **테스트**인가

    *"프론트 락이 잡는다"* 를 **주석으로만** 적으면 **그 파일이 사라져도 조용하다**
    (동료 지적). 이 저장소 원장이 말하는 **산문 77%** 가 정확히 그 형태다 —
    원칙은 적혀 있는데 **강제하는 것이 없다.**
    → 그래서 **파일과 그 안의 테스트 이름까지** 여기서 확인한다.
      프론트 락이 지워지거나 이름이 바뀌면 **이 파일이 빨개진다.**
    """
    front = (next(q for q in _SRC.parents if q.name == "apps")
             / "web" / "components" / "settings" / "__tests__"
             / "GrowthDashboard.flagValueTruncation.test.tsx")
    assert front.is_file(), (
        f"★내가 「저쪽이 잡는다」고 적은 락이 **사라졌다**: {front}\n"
        "   그 축(절단을 말하는가)이 지금 **아무도 안 잡는다** — 여기서 잡거나, 그쪽을 되살려라."
    )
    src = front.read_text(encoding="utf-8")

    # ★대조군 먼저 — 조회기가 살아 있나(빈 파일이면 아래가 공허하다)
    assert "summarizeParams" in src or "flag" in src.lower(), "★프론트 락이 비었다(위반 아님)"

    # 그 파일 안에서 **이 축을 잡는 테스트**가 실재하는가
    for marker in ("상한 초과", "음성 대조군"):
        assert marker in src, (
            f"★프론트 락에서 「{marker}」 축이 사라졌다 — "
            "절단을 말하는지 확인하는 쪽이 없어졌다"
        )
