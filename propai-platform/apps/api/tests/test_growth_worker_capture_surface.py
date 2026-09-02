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
    assert p1["queue_depth"] == 0
    assert p1.get("at"), "★시각이 없다 — 「비울 게 없다」와 「멈췄다」를 못 가른다"

    # ② 깊이 N + 시각 있음(쌓이는 중)
    s2 = _Store()
    for i in range(7):
        cs._QUEUE.append({"event_id": f"e{i}", "event_type": "t", "created_at": None})
    await cs.publish_capture_status(s2, scope="worker")
    p2 = _published(s2)
    assert p2["queue_depth"] == 7, "★깊이가 안 실린다 — 「안 비운다」를 말할 수 없다"

    # ★①과 ②가 **실제로 갈렸는가**(두 모집단 대조 — 같지 않아야 한다)
    assert p1["queue_depth"] != p2["queue_depth"], "★두 모집단이 안 갈렸다 = 공허한 초록"

    # ③ 발행 자체가 없으면 **행이 없다**(호출 안 하면 저장소가 빈다)
    s3 = _Store()
    assert not s3.rows, "★부르지도 않았는데 행이 있다 — 세 번째 모집단이 성립 안 한다"


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
    expected = set(cs.capture_status()) | {"at"}
    # ★대조군 — 파생이 죽으면(빈 집합) 아래가 공허해진다
    assert len(expected) >= 5, f"★capture_status 파생이 죽었다: {expected}"
    assert got == expected, f"★계약 불일치 — 빠짐 {expected - got} · 남음 {got - expected}"


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
