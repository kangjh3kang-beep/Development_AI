"""forest_service_client 단위 테스트 (T3 — 임목축적 커넥터).

원칙 검증:
- 무날조/정직: env(FOREST_API_KEY/FOREST_API_BASE) 미설정 시 즉시 None,
  네트워크 시도 자체가 없어야 한다(현행 정직 게이트 완전 보존).
- 특정 공공 API 스펙 하드코딩 금지 — 응답 매핑은 설정가능 필드맵.
- 실패 시 None + warning (호출부로 예외 전파 금지).

전 케이스 네트워크 미사용(가짜 httpx.Client 주입).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.integrations import forest_service_client as fsc
from app.integrations.forest_service_client import get_forest_facts

PNU = "1111010100100010000"  # 형식 예시 PNU (19자리)


# ──────────────────────────────────────────
# 테스트 더블
# ──────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """httpx.Client 대역 — 호출 기록 + 지정 응답/예외 반환."""

    instances: list[_FakeClient] = []

    payload: dict[str, Any] = {}
    status_code: int = 200
    raise_exc: Exception | None = None

    def __init__(self, *args: Any, **kwargs: Any):
        self.init_kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        _FakeClient.instances.append(self)

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResponse:
        self.calls.append({"url": url, "params": params})
        if _FakeClient.raise_exc is not None:
            raise _FakeClient.raise_exc
        return _FakeResponse(_FakeClient.payload, _FakeClient.status_code)


class _ForbiddenClient:
    """네트워크 시도 자체를 금지 — 생성되면 즉시 실패."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise AssertionError("env 미설정인데 httpx.Client 가 생성됨 — 네트워크 시도 금지 위반")


@pytest.fixture(autouse=True)
def _reset_fake(monkeypatch: pytest.MonkeyPatch):
    _FakeClient.instances = []
    _FakeClient.payload = {}
    _FakeClient.status_code = 200
    _FakeClient.raise_exc = None
    # 기본: 모든 관련 env 제거(격리)
    for key in (
        "FOREST_API_KEY",
        "FOREST_API_BASE",
        "FOREST_API_FIELD_MAP",
        "FOREST_API_KEY_PARAM",
        "FOREST_API_PNU_PARAM",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def _enable_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOREST_API_KEY", "test-key")
    monkeypatch.setenv("FOREST_API_BASE", "https://forest.example.test/api/facts")


# ──────────────────────────────────────────
# 1) env 미설정 → 즉시 None, 네트워크 시도 금지
# ──────────────────────────────────────────


class TestEnvGate:
    def test_env_전부_미설정이면_None_네트워크_금지(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(fsc.httpx, "Client", _ForbiddenClient)
        assert get_forest_facts(PNU) is None

    def test_KEY만_설정되면_None_네트워크_금지(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FOREST_API_KEY", "test-key")
        monkeypatch.setattr(fsc.httpx, "Client", _ForbiddenClient)
        assert get_forest_facts(PNU) is None

    def test_BASE만_설정되면_None_네트워크_금지(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FOREST_API_BASE", "https://forest.example.test")
        monkeypatch.setattr(fsc.httpx, "Client", _ForbiddenClient)
        assert get_forest_facts(PNU) is None

    def test_빈문자열_env는_미설정과_동일(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FOREST_API_KEY", "  ")
        monkeypatch.setenv("FOREST_API_BASE", "")
        monkeypatch.setattr(fsc.httpx, "Client", _ForbiddenClient)
        assert get_forest_facts(PNU) is None


# ──────────────────────────────────────────
# 2) 정상 조회 — 기본 필드맵
# ──────────────────────────────────────────


class TestFetchDefaultFieldMap:
    def test_기본_필드맵_매핑과_float_강제변환(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {
            "입목축적_per_ha": "150.5",
            "관할평균_입목축적_per_ha": 120,
            "산지구분": "준보전산지",
        }
        facts = get_forest_facts(PNU)
        assert facts is not None
        assert facts["입목축적_per_ha"] == pytest.approx(150.5)
        assert facts["관할평균_입목축적_per_ha"] == pytest.approx(120.0)
        assert facts["산지구분"] == "준보전산지"

    def test_요청_파라미터에_key와_pnu_포함(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"입목축적_per_ha": 100}
        get_forest_facts(PNU)
        call = _FakeClient.instances[0].calls[0]
        assert call["url"] == "https://forest.example.test/api/facts"
        assert call["params"]["serviceKey"] == "test-key"
        assert call["params"]["pnu"] == PNU

    def test_타임아웃_10초(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"입목축적_per_ha": 100}
        get_forest_facts(PNU)
        assert _FakeClient.instances[0].init_kwargs.get("timeout") == 10.0

    def test_천단위_콤마_숫자_파싱(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"입목축적_per_ha": "1,250.5"}
        facts = get_forest_facts(PNU)
        assert facts is not None
        assert facts["입목축적_per_ha"] == pytest.approx(1250.5)

    def test_숫자_파싱불가_필드는_None(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"입목축적_per_ha": "알수없음", "산지구분": "보전산지"}
        facts = get_forest_facts(PNU)
        assert facts is not None
        assert facts["입목축적_per_ha"] is None  # 무날조 — 파싱불가는 None
        assert facts["산지구분"] == "보전산지"

    def test_전_필드_미확보시_None(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"무관한필드": 1}
        assert get_forest_facts(PNU) is None

    def test_source_동반_설명가능성(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"입목축적_per_ha": 100}
        facts = get_forest_facts(PNU)
        assert facts is not None
        assert facts.get("source")  # 출처 명기(설명가능성 기본화)


# ──────────────────────────────────────────
# 3) 설정가능 필드맵 (특정 API 스펙 하드코딩 금지)
# ──────────────────────────────────────────


class TestConfigurableFieldMap:
    def test_env_필드맵_중첩_dot_path_매핑(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setenv(
            "FOREST_API_FIELD_MAP",
            json.dumps({
                "입목축적_per_ha": "response.body.items.0.frstStck",
                "관할평균_입목축적_per_ha": "response.body.items.0.avgStck",
                "산지구분": "response.body.items.0.mtnDiv",
            }),
        )
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {
            "response": {
                "body": {
                    "items": [
                        {"frstStck": "180", "avgStck": "120", "mtnDiv": "보전산지"}
                    ]
                }
            }
        }
        facts = get_forest_facts(PNU)
        assert facts is not None
        assert facts["입목축적_per_ha"] == pytest.approx(180.0)
        assert facts["관할평균_입목축적_per_ha"] == pytest.approx(120.0)
        assert facts["산지구분"] == "보전산지"

    def test_필드맵_경로_불일치는_None_필드(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setenv(
            "FOREST_API_FIELD_MAP",
            json.dumps({"입목축적_per_ha": "a.b.c", "산지구분": "mtn"}),
        )
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"mtn": "준보전산지"}
        facts = get_forest_facts(PNU)
        assert facts is not None
        assert facts["입목축적_per_ha"] is None
        assert facts["산지구분"] == "준보전산지"

    def test_잘못된_필드맵_JSON은_기본맵_폴백(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setenv("FOREST_API_FIELD_MAP", "{invalid json")
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"입목축적_per_ha": 90}
        facts = get_forest_facts(PNU)
        assert facts is not None
        assert facts["입목축적_per_ha"] == pytest.approx(90.0)

    def test_파라미터명_env_재정의(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setenv("FOREST_API_KEY_PARAM", "apiKey")
        monkeypatch.setenv("FOREST_API_PNU_PARAM", "pnuCode")
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.payload = {"입목축적_per_ha": 100}
        get_forest_facts(PNU)
        params = _FakeClient.instances[0].calls[0]["params"]
        assert params["apiKey"] == "test-key"
        assert params["pnuCode"] == PNU
        assert "serviceKey" not in params


# ──────────────────────────────────────────
# 4) 실패 → None + warning (예외 전파 금지)
# ──────────────────────────────────────────


class TestFailureHonesty:
    def test_HTTP_오류는_None(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.status_code = 500
        with caplog.at_level("WARNING"):
            assert get_forest_facts(PNU) is None
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_네트워크_예외는_None(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _FakeClient)
        _FakeClient.raise_exc = httpx.ConnectError("connection refused")
        with caplog.at_level("WARNING"):
            assert get_forest_facts(PNU) is None
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_JSON_아닌_응답도_None_예외_전파_금지(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)

        class _BadJsonClient(_FakeClient):
            def get(self, url: str, params: dict[str, Any] | None = None):
                resp = super().get(url, params=params)

                def _boom() -> dict[str, Any]:
                    raise ValueError("not json")

                resp.json = _boom  # type: ignore[method-assign]
                return resp

        monkeypatch.setattr(fsc.httpx, "Client", _BadJsonClient)
        assert get_forest_facts(PNU) is None

    def test_빈_pnu는_None_네트워크_금지(self, monkeypatch: pytest.MonkeyPatch):
        _enable_env(monkeypatch)
        monkeypatch.setattr(fsc.httpx, "Client", _ForbiddenClient)
        assert get_forest_facts("") is None
