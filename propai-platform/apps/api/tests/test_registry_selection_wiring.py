"""등기 조회 — 물건 선택 '배선' 통합 회귀망.

순수함수 테스트(test_registry_realty_kind_contract)만으로는 부족하다는 것이 적대적
리뷰에서 드러났다: 하이픈/틸코 경로의 select_registry_item 호출을 통째로 지우고
items[0] 맹목 선택으로 되돌려도 순수함수 테스트는 전부 통과했다.

이 파일은 프로바이더 응답을 위조해 **실제 배선**을 관통 검증한다.
    · get_one이 구분/동·호를 프로바이더 경로까지 전달하는가
    · 요청한 구분의 물건을 고르는가(첫 건 맹목 선택이 아닌가)
    · 정직성 필드(select_note·realty_gubun)가 결과까지 실려 나오는가
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.registry.registry_service import RegistryService


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload
        self.status_code = 200
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


# 한 주소에 토지·건물·집합건물 2세대가 함께 잡히는 실제 상황.
# ★어느 구분도 목록 첫 자리에 두지 않는다 — 첫 건을 집어도 우연히 정답이 되면
#   "구분을 전달하지 않는" 회귀를 테스트가 못 잡는다(동어반복 방지).
_SEARCH_ITEMS = [
    {"get부동산고유번호": "3333-333", "get구분": "집합건물",
     "get부동산소재지번": "○○동 1-1 제1101동 제1502호"},
    {"get부동산고유번호": "1111-111", "get구분": "토지", "get부동산소재지번": "○○동 1-1"},
    {"get부동산고유번호": "2222-222", "get구분": "건물", "get부동산소재지번": "○○동 1-1"},
    {"get부동산고유번호": "4444-444", "get구분": "집합건물",
     "get부동산소재지번": "○○동 1-1 제101동 제502호"},
]


@pytest.fixture
def hyphen_env(monkeypatch):
    monkeypatch.setenv("REGISTRY_PROVIDER", "hyphen")
    monkeypatch.setenv("HYPHEN_HKEY", "test-key")
    monkeypatch.setenv("HYPHEN_USER_ID", "test-user")
    monkeypatch.delenv("REGISTRY_API_URL", raising=False)
    monkeypatch.delenv("REGISTRY_API_KEY", raising=False)


@pytest.fixture
def captured(monkeypatch, hyphen_env):
    """하이픈 HTTP를 위조하고, 실제로 열람 요청된 고유번호를 포착."""
    seen: dict[str, Any] = {"fetched_uno": None}

    async def fake_post(self, url, *args, **kwargs):  # noqa: ANN001, ARG001
        body = kwargs.get("json") or {}
        # ★★2026-08-08 추가 — 권한 관문(`/in0004000169`).
        #   `hyphen_client.check_access()` 가 조회 전용·무과금 호출로 **관문만 통과 확인**한다.
        #   이 위조가 없으면 여기서 `AssertionError` 가 나고 → "하이픈 연결 실패" →
        #   **Tilko 자동 폴백** → 최종 `status=not_configured` 가 되어, 아래 선택 배선
        #   단언들이 전부 `fetched_uno is None` 으로 무너진다.
        #   즉 **선택 로직과 무관한 관문 하나 때문에** 배선 회귀망 5개가 통째로 죽었다.
        #   ★관문은 `common.errYn` 만 본다(hyphen_client:107-125) — 정상 통과를 위조한다.
        if url.endswith("/in0004000169"):
            return _FakeResponse({"common": {"errYn": "N"}, "data": {}})
        if url.endswith("/in0004000168"):  # 간편주소 검색
            return _FakeResponse({"common": {"errYn": "N"},
                                  "data": {"list": _SEARCH_ITEMS, "totCnt": len(_SEARCH_ITEMS)}})
        if url.endswith("/in0004000948"):  # 등기부 열람
            seen["fetched_uno"] = body.get("uniqNo") or body.get("uniqueNo")
            return _FakeResponse({"common": {"errYn": "N"},
                                  "data": {"outList": {"get소유자": "홍길동"}}})
        raise AssertionError(f"예상 밖 하이픈 호출: {url}")

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return seen


@pytest.mark.asyncio
class TestSelectionWiring:
    async def test_picks_requested_kind_not_first_item(self, captured):
        """★핵심: '건물'을 고르면 첫 결과(토지)가 아니라 건물이 열람돼야 한다."""
        res = await RegistryService().get_one(address="○○동 1-1", realty_type="3")
        assert captured["fetched_uno"] == "2222222", "요청한 구분이 프로바이더까지 전달되지 않음"
        assert res.get("realty_gubun") == "건물"
        assert not res.get("select_note")

    async def test_picks_exact_unit_not_substring(self, captured):
        """★실결함: '101'이 '제1101동'에 부분일치해 남의 세대를 열람하면 안 된다."""
        res = await RegistryService().get_one(
            address="○○동 1-1", realty_type="1", dong="101", ho="502"
        )
        assert captured["fetched_uno"] == "4444444"
        assert not res.get("select_note")

    async def test_kind_miss_falls_back_with_note(self, captured):
        """요청 구분이 결과에 없으면 조회는 하되 반드시 고지가 실려야 한다."""
        res = await RegistryService().get_one(address="○○동 1-1", realty_type="9")
        assert res.get("select_note"), "구분 미적용 사실이 결과에 실리지 않음"

    async def test_no_kind_keeps_first(self, captured):
        await RegistryService().get_one(address="○○동 1-1")
        assert captured["fetched_uno"] == "3333333"  # 필터 없음 = 목록 첫 건

    async def test_bulk_passes_kind(self, captured):
        """다필지 일괄도 구분을 넘겨야 한다(토지조서 기본=토지)."""
        out = await RegistryService().bulk([{"address": "○○동 1-1"}])
        assert out["count"] == 1
        assert captured["fetched_uno"] == "1111111", "bulk가 구분을 넘기지 않아 첫 물건이 선택됨"


@pytest.mark.asyncio
class TestTilkoSelectionWiring:
    """틸코 폴백 경로도 하이픈과 대칭으로 선택기를 거쳐야 한다(형제 경로 스윕)."""

    @pytest.fixture
    def tilko_captured(self, monkeypatch):
        monkeypatch.setenv("REGISTRY_PROVIDER", "tilko")
        monkeypatch.delenv("HYPHEN_HKEY", raising=False)
        monkeypatch.delenv("HYPHEN_API_KEY", raising=False)
        monkeypatch.delenv("HYPHEN_USER_ID", raising=False)
        monkeypatch.delenv("REGISTRY_API_URL", raising=False)
        monkeypatch.delenv("REGISTRY_API_KEY", raising=False)

        seen: dict[str, Any] = {"fetched_uno": None}
        items = [
            {"unique_no": "3333333", "gubun": "집합건물", "jibun": "○○동 1-1 제1101동 제1502호"},
            {"unique_no": "1111111", "gubun": "토지", "jibun": "○○동 1-1"},
            {"unique_no": "2222222", "gubun": "건물", "jibun": "○○동 1-1"},
        ]

        async def fake_search(address, page="1"):  # noqa: ANN001, ARG001
            return {"ok": True, "status": "ok", "items": items}

        async def fake_fetch(*, unique_no, **kwargs):  # noqa: ANN001, ARG001
            seen["fetched_uno"] = unique_no
            return {"ok": True, "pdf_data": "ZmFrZQ=="}

        from app.services.registry import tilko_client as tk

        monkeypatch.setattr(tk, "tilko_ready", lambda: True)
        monkeypatch.setattr(tk, "search_unique_no", fake_search)
        monkeypatch.setattr(tk, "fetch_realty_registry", fake_fetch)
        return seen

    async def test_tilko_picks_requested_kind(self, tilko_captured):
        res = await RegistryService().get_one(address="○○동 1-1", realty_type="2")
        assert tilko_captured["fetched_uno"] == "1111111", "틸코 경로가 구분을 무시하고 첫 건 선택"
        assert res.get("realty_gubun") == "토지"

    async def test_tilko_surfaces_note(self, tilko_captured):
        res = await RegistryService().get_one(address="○○동 1-1", realty_type="9")
        assert res.get("select_note"), "틸코 경로에서 정직성 고지가 유실됨"


@pytest.mark.asyncio
class TestHonestyReachesUserSurface:
    """고지가 최종 응답(fetched)까지 실려야 한다 — 중간에서 유실되면 사용자는 모른다."""

    async def test_select_note_in_analyze_output(self, monkeypatch):
        from app.services.registry import registry_analysis_service as ras

        async def fake_get_one(self, **kwargs):  # noqa: ANN001, ARG001
            return {
                "status": "ok", "origin": "hyphen", "owner": "홍길동",
                "registry_text": "소유자 홍길동 / 근저당 없음",
                "realty_gubun": "토지",
                "select_note": "요청 구분을 적용하지 못했습니다.",
            }

        async def fake_llm(self, address, registry):  # noqa: ANN001, ARG001
            return {"summary": "테스트"}

        monkeypatch.setattr(RegistryService, "get_one", fake_get_one)
        monkeypatch.setattr(ras.RegistryAnalysisService, "_llm", fake_llm)

        out = await ras.RegistryAnalysisService().analyze(
            address="○○동 1-1", realty_type="9", land_hint={"jimok": "대"}
        )
        fetched = out.get("fetched") or {}
        assert fetched.get("select_note"), "고지가 최종 응답까지 도달하지 않음"
        assert fetched.get("realty_gubun") == "토지"


@pytest.mark.asyncio
class TestGroundingWiring:
    """★H4의 교훈 재적용: 순수함수만 고정하면 '호출부'는 지워도 초록이다.
    그라운딩 판정·출처 표기·정직성 게이트가 analyze() 실경로에서 동작하는지 관통 검증."""

    @staticmethod
    def _reg(pdf_text_ok: bool) -> dict[str, Any]:
        import base64
        return {
            "status": "ok", "origin": "hyphen", "owner": "홍길동",
            "out_list": {"get소유자": "홍길동"},          # 머리말만 — 등기사항 없음
            "pdf_base64": base64.b64encode(b"%PDF-1.4").decode(),
            "has_pdf": True, "_pdf_ok": pdf_text_ok,
        }

    async def _run(self, monkeypatch, *, pdf_text: str):
        from app.services.registry import registry_analysis_service as ras

        async def fake_get_one(self, **kwargs):  # noqa: ANN001, ARG001
            return TestGroundingWiring._reg(bool(pdf_text))

        async def fake_llm(self, address, registry):  # noqa: ANN001, ARG001
            return {"summary": "분석함", "safety_grade": "안전", "_source_seen": registry}

        monkeypatch.setattr(RegistryService, "get_one", fake_get_one)
        monkeypatch.setattr(ras.RegistryAnalysisService, "_llm", fake_llm)
        monkeypatch.setattr(ras, "_pdf_to_text", lambda b: pdf_text)

        async def no_upload(*a, **k):  # noqa: ANN002, ANN003, ARG001
            return {}

        monkeypatch.setattr("apps.api.services.storage_service.upload_registry_pdf",
                            no_upload, raising=False)
        return await ras.RegistryAnalysisService().analyze(address="○○동 1-1", realty_type="2")

    async def test_pdf_grounding_replaces_thin_summary(self, monkeypatch):
        """머리말뿐이면 PDF 전문으로 갈아끼워 LLM에 넘겨야 한다."""
        out = await self._run(monkeypatch, pdf_text="【갑구】소유권이전\n【을구】근저당권설정 3억")
        assert out["status"] == "ok"
        assert "근저당권설정" in (out["ai"]["_source_seen"] or ""), "PDF 전문이 분석 소스로 안 쓰임"
        assert out["origin"].startswith("hyphen"), f"출처 오표기: {out['origin']}"

    async def test_image_pdf_must_not_produce_fake_safe_grade(self, monkeypatch):
        """★N1: 이미지 PDF로 추출 실패 시 머리말만으로 '안전' 등급을 내면 안 된다."""
        out = await self._run(monkeypatch, pdf_text="")
        assert out["status"] == "empty", "껍데기 소스로 권리분석이 진행됨(거짓 안전등급 위험)"
        assert out.get("ai") is None
        assert "본문" in (out.get("message") or "")

    async def test_origin_reflects_actual_provider(self, monkeypatch):
        """★H3-b: 하이픈 결과를 'codef'로 오표기하면 안 된다.
        등기사항이 이미 있어 PDF 그라운딩이 일어나지 않는 경로에서 검증한다
        (그라운딩이 origin을 덮어쓰면 오표기가 가려지기 때문)."""
        from app.services.registry import registry_analysis_service as ras

        async def fake_get_one(self, **kwargs):  # noqa: ANN001, ARG001
            return {
                "status": "ok", "origin": "hyphen", "owner": "홍길동",
                "entries": [{"resRegistrationSumList": [{
                    "resType": "을구",
                    "resContentsList": [{"resDetailList": [
                        {"resContents": "근저당권설정 채권최고액 금 300,000,000원"}]}],
                }]}],
            }

        async def fake_llm(self, address, registry):  # noqa: ANN001, ARG001
            return {"summary": "분석함"}

        monkeypatch.setattr(RegistryService, "get_one", fake_get_one)
        monkeypatch.setattr(ras.RegistryAnalysisService, "_llm", fake_llm)
        out = await ras.RegistryAnalysisService().analyze(address="○○동 1-1", realty_type="2")
        assert out["status"] == "ok"
        assert out["origin"] == "hyphen", f"실제 프로바이더가 아닌 '{out['origin']}'로 표기됨"


@pytest.mark.asyncio
class TestRouterSelectionWiring:
    """/registry/tilko/realty 라우터도 선택기를 거쳐야 한다 — 1,200원 과금 경로."""

    async def test_router_picks_kind_and_surfaces_note(self, monkeypatch):
        import routers.registry as rr
        from app.services.registry import tilko_client as tk

        seen: dict[str, Any] = {}

        async def fake_search(address, page="1"):  # noqa: ANN001, ARG001
            return {"ok": True, "status": "ok", "items": [
                {"unique_no": "3333333", "gubun": "집합건물", "jibun": "○○동 1-1 제101동 제502호"},
                {"unique_no": "1111111", "gubun": "토지", "jibun": "○○동 1-1"},
            ]}

        async def fake_fetch(**kwargs):  # noqa: ANN003
            seen["uno"] = kwargs.get("unique_no")
            return {"ok": True, "status": "ok"}

        async def no_charge(*a, **k):  # noqa: ANN002, ANN003, ARG001
            return None

        monkeypatch.setattr(tk, "search_unique_no", fake_search)
        monkeypatch.setattr(tk, "fetch_realty_registry", fake_fetch)
        monkeypatch.setattr(rr, "_charge_registry_issue", no_charge)

        # ★`CurrentUser` 계약대로 tenant_id 도 준다 — 스텁이 실제보다 좁으면 그 필드를 쓰는
        #   코드가 테스트에서만 터진다(이 세션에서 형제 파일 3곳이 같은 이유로 깨졌다).
        user = type("U", (), {"user_id": "u1", "tenant_id": "t1"})()
        # ★핸들러를 **키워드로** 부른다. 위치인자로 부르면 시그니처에 인자가 하나 추가될
        #   때마다 조용히 밀려서 깨진다(실제로 그렇게 깨졌다).
        from starlette.requests import Request as _R

        def _http_req() -> _R:
            return _R({"type": "http", "method": "POST", "path": "/",
                       "headers": [], "client": ("127.0.0.1", 0), "query_string": b""})
        out = await rr.tilko_realty(
            _http_req(), {"address": "○○동 1-1", "realty_type": "2"}, current_user=user
        )
        assert seen["uno"] == "1111111", "라우터가 구분을 무시하고 첫 건을 발급함(과금 경로)"

        out2 = await rr.tilko_realty(
            _http_req(), {"address": "○○동 1-1", "realty_type": "9"}, current_user=user
        )
        assert out2.get("select_note"), "라우터에서 정직성 고지가 유실됨"
        assert out is not None


class TestRegistryTextGrounding:
    """머리말만 있는 구조화 텍스트는 '분석 가능'으로 취급되면 안 된다(껍데기 권리분석 방지)."""

    def test_header_only_text_is_not_substantive(self):
        from app.services.registry.registry_analysis_service import (
            _has_registry_entries,
            _registry_text_from_codef,
        )

        # 하이픈 응답 shape — entries 없음
        hyphen = {"status": "ok", "origin": "hyphen", "owner": "홍길동",
                  "out_list": {"get소유자": "홍길동"}}
        text = _registry_text_from_codef(hyphen)
        assert text.strip(), "머리말은 생성된다"
        assert _has_registry_entries(text) is False, (
            "머리말뿐인데 '등기사항 있음'으로 판정되면 PDF 그라운딩이 스킵돼 "
            "근저당·압류가 빠진 분석이 나간다"
        )

    def test_codef_entries_are_substantive(self):
        from app.services.registry.registry_analysis_service import (
            _has_registry_entries,
            _registry_text_from_codef,
        )

        codef = {
            "status": "ok", "origin": "codef", "owner": "홍길동",
            "entries": [{"resRegistrationSumList": [{
                "resType": "을구",
                "resContentsList": [{"resDetailList": [
                    {"resContents": "근저당권설정 채권최고액 금 300,000,000원"}
                ]}],
            }]}],
        }
        text = _registry_text_from_codef(codef)
        assert _has_registry_entries(text) is True
        assert "근저당권설정" in text


class TestProbeFailureIsNotForbidden:
    """권한 점검이 **실패한 것**과 자격증명이 **거부된 것**을 가른다.

    ★2026-08-08 실사고: 권한 점검(`/in0004000169`)이 추가되면서 `access == "ok"` 만 통과하게 됐고,
      점검이 예외로 끝나면(`unreachable`) **주 프로바이더를 통째로 건너뛰고** 2순위로 갔다.
      점검이 주 경로 앞의 **단일 실패점**이 된 셈이다 — 하이픈이 멀쩡해도 점검만 타임아웃 나면
      모든 등기 조회가 다른 프로바이더로 샌다(다른 데이터·다른 과금).
    ★#595 가 픽스처와 린트를 봉합했지만 **이 판정은 남아 있었다** — 여기서 가른다.
    """

    @pytest.mark.asyncio
    async def test_unreachable_probe_still_tries_hyphen(self, captured, monkeypatch):
        """점검을 못 했으면(unreachable) **본 호출은 시도한다** — 일시 오류로 프로바이더를 갈아타지 않는다."""
        async def probe_unreachable():
            return {"access": "unreachable", "checked": True, "message": "하이픈 연결 실패: timeout"}

        monkeypatch.setattr(
            "app.services.registry.hyphen_client.probe_api_access", probe_unreachable
        )
        await RegistryService().get_one(address="○○동 1-1")
        assert captured["fetched_uno"] == "3333333", (
            "권한 점검이 실패했다는 이유로 하이픈 본 호출을 건너뛰었다 — 일시 오류가 프로바이더를 갈아치운다"
        )

    @pytest.mark.asyncio
    async def test_forbidden_probe_skips_hyphen(self, captured, monkeypatch):
        """자격증명이 거부됐으면(forbidden) 시도할 가치가 없으므로 **건너뛴다**(두 모집단 분리)."""
        async def probe_forbidden():
            return {"access": "forbidden", "checked": True, "message": "하이픈 인증 실패"}

        monkeypatch.setattr(
            "app.services.registry.hyphen_client.probe_api_access", probe_forbidden
        )
        await RegistryService().get_one(address="○○동 1-1")
        assert captured["fetched_uno"] is None, "자격증명 거부인데도 하이픈을 호출했다"
