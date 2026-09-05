"""성장루프 라우트 키 정규화 — 한 라우트가 두 어휘로 갈리지 않게.

## 왜 (2026-09-05 라이브 실측 · `GET /growth/insights?sort=created_at&limit=500`)

서버 미들웨어는 `/api/v1` 접두사를 보존하고 id 를 `{id}` 로 치환하는데, 웹 계측
(`apps/web/lib/api-client.ts:trackApiCall`)은 **쿼리스트링만** 뗀다. 그래서 같은
라우트가 두 키로 갈렸다 — **접두사만 다른 쌍 9개**, `/store/projects` 는
bare 17행(open 7) + 접두사판 20행(open 7) = **한 라우트에 open 14건**.

귀결 셋: ①`IDENTITY_FIELDS["latency_regression"] == ("key",)` 라 승계가
**원리적으로 불가** ②웹 키는 원시 UUID 를 품어 카디널리티가 무한 → 표본이 하한(20)에
못 닿는다(실측 `judged_pct 6.9% · withheld 432/464`) ③baseline·평소값이 두 벌이 된다.

★임계는 건드리지 않는다 — `analyzer.py:98~130` 이 이 route 군의 임계 변경을
**이미 기각**했다(MAD 스케일 → 실효임계 166초 → 가장 망가진 route 가 발화 불가 = 굿하트).
"""
import pytest

from app.middleware.growth_telemetry import normalize_route
from app.routers.growth import _canonical_route


class TestIdempotent:
    """① 멱등 — 서버 미들웨어가 만든 형태는 **고정점**이다(회귀가 아닌 근거)."""

    @pytest.mark.parametrize("server_form", [
        "/api/v1/store/projects",
        "/api/v1/registry/analyze/jobs/{id}",
        "/api/v1/projects/{id}",
        "/api/v1/tiles/vworld/wmts/Hybrid/{id}/{id}/{id}.png",
    ])
    def test_server_form_unchanged(self, server_form):
        assert _canonical_route("api_call", server_form) == server_form


class TestConvergence:
    """② 합류 — 두 모집단이 **같은 실행에서** 같은 키로 수렴한다.

    ★한쪽만 단언하면 "전부 같은 값으로 뭉개는 구현"과 구별되지 않는다.
    """

    @pytest.mark.parametrize("web_form,server_form", [
        ("/store/projects", "/api/v1/store/projects"),
        ("/registry/analyze/jobs/0f1f795ca34a42dbb4c73e16ff7ce343",
         "/api/v1/registry/analyze/jobs/{id}"),
        ("/projects/c974ebf3-1669-4d01-bdad-49346c4e5550", "/api/v1/projects/{id}"),
        ("/auth/me", "/api/v1/auth/me"),
    ])
    def test_web_and_server_converge(self, web_form, server_form):
        web = _canonical_route("api_call", web_form)
        srv = _canonical_route("api_call", server_form)
        assert web == srv == server_form, f"{web!r} != {srv!r}"

    def test_distinct_routes_stay_distinct(self):
        """★뭉개기 방지 — 다른 라우트는 **여전히 달라야** 한다."""
        a = _canonical_route("api_call", "/store/projects")
        b = _canonical_route("api_call", "/auth/me")
        assert a != b

    def test_query_string_removed(self):
        assert _canonical_route("api_call", "/store/projects?x=1") == "/api/v1/store/projects"


class TestScope:
    """③ ★범위 — `page_view` 의 route 는 **브라우저 경로**라 건드리지 않는다.

    붙이면 존재하지 않는 API 라우트를 합성하고, 같은 이름의 진짜 라우트와 키가 충돌한다.
    """

    @pytest.mark.parametrize("event_type", ["page_view", "js_error", "selection_contamination"])
    def test_non_api_events_untouched(self, event_type):
        assert _canonical_route(event_type, "/projects") == "/projects"

    def test_api_events_are_touched(self):
        """★대조군 — 범위 안의 것은 실제로 바뀐다(공허한 통과 방지)."""
        assert _canonical_route("api_call", "/projects") == "/api/v1/projects"
        assert _canonical_route("api_error", "/projects") == "/api/v1/projects"


class TestNegativeControls:
    """④ 음성 대조군 — 이미 버전이 있으면 덧붙이지 않는다."""

    @pytest.mark.parametrize("already", ["/api/v1/x", "/api/v2/x", "/api/v10/x"])
    def test_no_double_prefix(self, already):
        out = _canonical_route("api_call", already)
        assert out.count("/api/v") == 1, out
        assert out.startswith(already.split("/x")[0])

    def test_none_and_empty(self):
        assert _canonical_route("api_call", None) is None
        assert _canonical_route("api_call", "") == ""

    def test_normalizer_itself_preserves_version(self):
        """SSOT 자신이 버전을 ID 로 오인하지 않는지 — 한 층 아래를 직접 태운다."""
        assert normalize_route("/api/v1/projects/123") == "/api/v1/projects/{id}"
        assert normalize_route("/api/v2/projects/123") == "/api/v2/projects/{id}"


class TestWiring:
    """★배선 — 수신부가 실제로 이 함수를 **부르는가**(이름이 있다 ≠ 값이 실린다)."""

    def test_ingest_uses_canonical_route(self, monkeypatch):
        import app.routers.growth as g

        seen: list[tuple[str, dict]] = []

        class _Cap:
            @staticmethod
            def record_event(etype, payload):
                seen.append((etype, payload))

        import sys, types
        mod = types.ModuleType("app.services.growth.capture_service")
        mod.record_event = _Cap.record_event
        monkeypatch.setitem(sys.modules, "app.services.growth.capture_service", mod)
        pkg = sys.modules.get("app.services.growth")
        if pkg is not None:
            monkeypatch.setattr(pkg, "capture_service", mod, raising=False)

        batch = g.GrowthEventBatch(events=[
            g.GrowthEventIn(event_type="api_call", route="/store/projects?a=1",
                            status_code=200, latency_ms=12),
            g.GrowthEventIn(event_type="page_view", route="/projects"),
        ])

        class _Req:
            headers: dict = {}
            state = type("S", (), {})()

        import asyncio
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            g.ingest_events(batch, _Req())  # type: ignore[arg-type]
        )
        routes = {t: p.get("route") for t, p in seen}
        assert routes.get("api_call") == "/api/v1/store/projects", routes
        assert routes.get("page_view") == "/projects", routes


# ── ★부채(초록 안에 보이게) ────────────────────────────────────────────────
@pytest.mark.xfail(reason="★범위 밖 — `llm_call` 이벤트의 route 어휘는 미조사(계획서 §3-3)",
                   strict=False)
def test_llm_call_route_vocabulary_unmeasured():
    raise AssertionError("llm_call 생산자의 route 어휘를 아직 재지 않았다")
