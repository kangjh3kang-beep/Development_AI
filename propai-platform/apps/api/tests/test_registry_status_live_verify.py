"""등기 연동 상태 — '키 있음'이 아니라 '실제 호출 가능'으로 판정하는지.

배경(라이브 실측):
    관리자 화면에 하이픈 키를 정상 입력했고 서버도 인식(hyphen_ready=True)했지만,
    실제 호출은 하이픈이 errYn=Y "권한이 없는 API 입니다"로 거절했다(계약 미포함).
    그런데 /registry/status는 "하이픈 부동산 등기부 API 1순위 연결됨"이라 답했고,
    관리자 '테스트' 버튼도 ok=true를 띄웠다 — 사용자가 원인을 알 수 없는 거짓 안심.
    틸코 status는 공개키를 실제로 받아 검증(public_key_ok)하는데 하이픈만 그 검증이
    없던 형제 비대칭이 근본원인.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.registry import hyphen_client as hc
from app.services.registry.registry_service import RegistryService


class _Resp:
    def __init__(self, payload: dict[str, Any], status: int = 200):
        self._p = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._p


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    hc._ACCESS_CACHE.clear()
    monkeypatch.setenv("HYPHEN_HKEY", "k")
    monkeypatch.setenv("HYPHEN_USER_ID", "u")
    monkeypatch.delenv("REGISTRY_PROVIDER", raising=False)
    monkeypatch.delenv("TILKO_API_KEY", raising=False)
    yield
    hc._ACCESS_CACHE.clear()


def _patch_hyphen(monkeypatch, payload: dict[str, Any], status: int = 200):
    async def fake_post(self, url, *a, **k):  # noqa: ANN001, ARG001
        return _Resp(payload, status)

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


class TestForbiddenMessage:
    @pytest.mark.parametrize("msg", [
        "권한이 없는 API 입니다.",
        "권한이 없습니다",
        "해당 API 에 대한 권한 없음",
    ])
    def test_detects_permission_denial(self, msg):
        assert hc._is_forbidden_message(msg) is True

    @pytest.mark.parametrize("msg", ["", "조회 결과가 없습니다.", "고유번호를 확인하세요"])
    def test_data_errors_are_not_permission_denial(self, msg):
        assert hc._is_forbidden_message(msg) is False


@pytest.mark.asyncio
class TestProbeApiAccess:
    async def test_forbidden_is_reported(self, monkeypatch):
        """★라이브에서 실제로 돌아온 응답 — 권한 없음을 잡아야 한다."""
        _patch_hyphen(monkeypatch, {"common": {"errYn": "Y", "errMsg": "권한이 없는 API 입니다."}})
        r = await hc.probe_api_access()
        assert r["access"] == "forbidden"
        assert "권한" in r["message"]

    async def test_data_error_counts_as_access_ok(self, monkeypatch):
        """더미 고유번호라 데이터가 없는 것은 '권한 있음'이다(관문 통과)."""
        _patch_hyphen(monkeypatch, {"common": {"errYn": "Y", "errMsg": "조회 결과가 없습니다."}})
        r = await hc.probe_api_access()
        assert r["access"] == "ok"

    async def test_success_is_access_ok(self, monkeypatch):
        _patch_hyphen(monkeypatch, {"common": {"errYn": "N"}, "data": {"list": []}})
        r = await hc.probe_api_access()
        assert r["access"] == "ok"

    async def test_http_error_is_unreachable(self, monkeypatch):
        _patch_hyphen(monkeypatch, {}, status=500)
        r = await hc.probe_api_access()
        assert r["access"] == "unreachable"

    async def test_not_configured_short_circuits(self, monkeypatch):
        monkeypatch.delenv("HYPHEN_HKEY", raising=False)
        monkeypatch.delenv("HYPHEN_API_KEY", raising=False)
        r = await hc.probe_api_access()
        assert r["access"] == "not_configured" and r["checked"] is False


@pytest.mark.asyncio
class TestLiveStatusHonesty:
    async def test_forbidden_must_not_say_connected(self, monkeypatch):
        """★핵심: 권한이 없으면 '연결됨'이라 말하면 안 되고 ready도 내려가야 한다."""
        _patch_hyphen(monkeypatch, {"common": {"errYn": "Y", "errMsg": "권한이 없는 API 입니다."}})
        st = await RegistryService().live_status()
        assert st["hyphen_access"] == "forbidden"
        assert "연결됨" not in st["message"], f"권한 없는데 연결됨으로 표기: {st['message']}"
        assert st["register_ready"] is False
        assert "권한" in st["message"]

    async def test_access_ok_keeps_connected(self, monkeypatch):
        _patch_hyphen(monkeypatch, {"common": {"errYn": "N"}})
        st = await RegistryService().live_status()
        assert st["hyphen_access"] == "ok"
        assert st["register_ready"] is True

    async def test_unreachable_keeps_ready_but_surfaces_reason(self, monkeypatch):
        """★점검을 **못 했을 때**(unreachable)는 ready 를 내리지 않는다 — 상태가 동작과 같아야 한다.

        `get_one` 은 unreachable 이면 **하이픈 본 호출을 시도**한다(2026-08-08). 그런데 상태만
        '준비 안 됨'이라 말하면 **조회는 하이픈으로 가는데 화면은 아니라고 하는 발산**이 생긴다.
        동시에 점검이 실패했다는 사실 자체는 숨기지 않는다(관리자가 원인을 봐야 한다).
        """
        import httpx

        async def boom(self, url, *args, **kwargs):  # noqa: ANN001, ARG001
            raise httpx.ConnectTimeout("timeout")

        monkeypatch.setenv("HYPHEN_HKEY", "k")
        monkeypatch.setenv("HYPHEN_USER_ID", "u")
        import app.services.registry.hyphen_client as hc

        hc._ACCESS_CACHE.pop("v", None)
        monkeypatch.setattr(httpx.AsyncClient, "post", boom)

        st = await RegistryService().live_status()
        assert st["hyphen_access"] == "unreachable"
        assert st["register_ready"] is True, (
            "점검을 못 했다는 이유로 ready 를 내렸다 — 실제로는 하이픈 본 호출을 시도한다(상태↔동작 발산)"
        )
        assert "실패" in (st["message"] or ""), "점검 실패 사실이 상태 메시지에 실리지 않았다"

    async def test_sync_status_contract_unchanged(self):
        """status()는 동기 계약 유지 — 호출부(테스트·admin)를 깨지 않는다."""
        st = RegistryService().status()
        assert isinstance(st, dict) and "configured" in st and "hyphen_ready" in st
