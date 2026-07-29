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
        "권한이 없는 API 입니다.",          # 라이브 실측 원문
        "해당 API 에 대한 권한 없음",
        "미승인 API 입니다",
    ])
    def test_detects_permission_denial(self, msg):
        assert hc._is_forbidden_message(msg) is True

    @pytest.mark.parametrize("msg", [
        "", "조회 결과가 없습니다.", "고유번호를 확인하세요",
        # ★'API 권한'이 아니라 '그 물건에 대한' 권한 — 전역 강등을 유발하면 안 된다.
        "열람 권한 없음 - 비공개 등기",
        "해당 부동산에 대한 조회 권한이 없습니다.",
    ])
    def test_data_errors_are_not_permission_denial(self, msg):
        assert hc._is_forbidden_message(msg) is False


class TestClassifyProbeResponse:
    """★기본값이 낙관이면 안 된다: '권한' 문구가 없는 거절도 전부 통과시키던 결함 방지."""

    @pytest.mark.parametrize("msg", [
        "인증키가 유효하지 않습니다.",
        "허용되지 않은 IP 입니다.",
        "등록되지 않은 사용자입니다.",
        "계약이 만료되었습니다.",
        "일일 호출 한도를 초과했습니다.",
        "Unauthorized",
    ])
    def test_other_rejections_must_not_be_ok(self, msg):
        access, _ = hc.classify_probe_response({"common": {"errYn": "Y", "errMsg": msg}})
        assert access != "ok", f"거절인데 통과로 판정됨: {msg}"

    def test_success_is_ok(self):
        access, _ = hc.classify_probe_response({"common": {"errYn": "N"}})
        assert access == "ok"

    @pytest.mark.parametrize("payload", [
        {"common": {"errYn": "Y", "errMsg": "[C0000-002] 입력하신 검색조건에 대한 결과가 없습니다."}},
        {"common": {"errYn": "Y", "errMsg": "[C0000-088] 고유번호에 해당하는 소재지번을 확인할 수 없습니다."}},
    ])
    def test_live_data_level_errors_are_ok(self, payload):
        """라이브 실측 응답 — 데이터가 없을 뿐 관문은 통과했다."""
        access, _ = hc.classify_probe_response(payload)
        assert access == "ok"

    def test_permission_denial_is_forbidden(self):
        access, msg = hc.classify_probe_response(
            {"common": {"errYn": "Y", "errMsg": "권한이 없는 API 입니다."}})
        assert access == "forbidden" and "권한" in msg

    @pytest.mark.parametrize("payload", [{}, {"common": {}}, {"common": {"errCd": "E403"}}])
    def test_unparseable_is_not_ok(self, payload):
        access, _ = hc.classify_probe_response(payload)
        assert access != "ok"


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

    async def test_sync_status_contract_unchanged(self):
        """status()는 동기 계약 유지 — 호출부(테스트·admin)를 깨지 않는다."""
        st = RegistryService().status()
        assert isinstance(st, dict) and "configured" in st and "hyphen_ready" in st
