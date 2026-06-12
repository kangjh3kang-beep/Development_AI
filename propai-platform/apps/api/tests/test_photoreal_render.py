"""포토리얼 렌더 서비스 단위 테스트 — Replicate 202(Prefer:wait 초과) 수리 검증.

검증 경로(httpx MockTransport — 실제 네트워크 호출 없음):
1. 202 접수 → 서버측 폴링 → succeeded (수리 핵심)
2. 202 접수 → 폴링 중 failed → 정직 에러(가짜 이미지 없음)
3. 202 접수 → 폴링 한도 초과 → status="pending" + prediction_id (렌더 지연 안내)
4. 200 즉시완료 하위호환 + 201 starting → 폴링 + 비(200/201/202) 에러 분기 유지
5. REPLICATE_API_TOKEN 부재 시 기존 no_key 폴백 유지(외부 호출 0회)
"""

import httpx
import pytest

from app.services.drawing import photoreal_render_service as svc

# 패치 전 실제 클래스 보관 — factory가 MockTransport를 주입해 재생성한다.
_REAL_ASYNC_CLIENT = httpx.AsyncClient

_PRED_ID = "pred-123"
_GET_URL = f"https://api.replicate.com/v1/predictions/{_PRED_ID}"
_OUT_URL = "https://replicate.delivery/pbxt/out.png"
_FAKE_IMAGE_B64 = "iVBORw0KGgoAAAANSUhEUg=="
_FAKE_TOKEN = "test-token-not-real"


def _prediction(status: str, **extra) -> dict:
    """Replicate prediction 객체 모사(id·urls.get 포함)."""
    body = {"id": _PRED_ID, "status": status, "urls": {"get": _GET_URL}}
    body.update(extra)
    return body


def _make_handler(post: tuple, gets: list[tuple]):
    """(상태코드, 본문) 튜플로 MockTransport 핸들러 생성. 호출 횟수 카운터 동봉."""
    calls = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls["post"] += 1
            code, body = post
            return httpx.Response(code, json=body)
        calls["get"] += 1
        code, body = gets[min(calls["get"] - 1, len(gets) - 1)]
        return httpx.Response(code, json=body)

    return handler, calls


def _install_transport(monkeypatch, handler) -> None:
    """httpx.AsyncClient 생성 시 MockTransport 주입(서비스 코드는 무수정 그대로 동작)."""
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _fast_poll(monkeypatch, *, max_s: float = 5.0, interval_s: float = 0.01) -> None:
    """테스트 속도를 위해 폴링 간격·한도만 단축(로직은 동일)."""
    monkeypatch.setattr(svc, "_POLL_INTERVAL_S", interval_s)
    monkeypatch.setattr(svc, "_POLL_MAX_S", max_s)


@pytest.fixture
def render_key(monkeypatch):
    """렌더 API 키 설정(가짜 토큰 — 외부 전송 없음, MockTransport로 차단)."""
    monkeypatch.setenv("REPLICATE_API_TOKEN", _FAKE_TOKEN)


# ──────────────────────────────────────────────
# 1~3. 202 접수 → 서버측 폴링 3경로
# ──────────────────────────────────────────────


class TestAccepted202Polling:
    """Prefer:wait(60s) 초과로 202가 와도 에러가 아닌 접수로 처리하고 폴링한다."""

    @pytest.mark.asyncio
    async def test_202_폴링_성공(self, monkeypatch, render_key):
        """202 + processing → GET 폴링 2회 후 succeeded → status=ok + image_url."""
        _fast_poll(monkeypatch)
        handler, calls = _make_handler(
            post=(202, _prediction("processing")),
            gets=[
                (200, _prediction("processing")),
                (200, _prediction("succeeded", output=[_OUT_URL])),
            ],
        )
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64)

        assert result["status"] == "ok"
        assert result["image_url"] == _OUT_URL
        assert calls["post"] == 1
        assert calls["get"] >= 2
        # 토큰은 응답에 절대 노출되지 않는다.
        assert _FAKE_TOKEN not in str(result)

    @pytest.mark.asyncio
    async def test_202_폴링_실패_정직_에러(self, monkeypatch, render_key):
        """202 접수 후 failed → 가짜 이미지 없이 status=error + 사유."""
        _fast_poll(monkeypatch)
        handler, calls = _make_handler(
            post=(202, _prediction("starting")),
            gets=[(200, _prediction("failed", error="NSFW detected"))],
        )
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64)

        assert result["status"] == "error"
        assert "image_url" not in result  # 가짜값 금지
        assert "failed" in result["message"]
        assert calls["get"] >= 1

    @pytest.mark.asyncio
    async def test_202_폴링_타임아웃_pending(self, monkeypatch, render_key):
        """폴링 한도 초과 → status=pending + '렌더 지연' 안내 + prediction_id."""
        _fast_poll(monkeypatch, max_s=0.05, interval_s=0.01)
        handler, calls = _make_handler(
            post=(202, _prediction("processing")),
            gets=[(200, _prediction("processing"))],  # 계속 진행 중
        )
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64)

        assert result["status"] == "pending"
        assert "렌더 지연" in result["message"]
        assert result["prediction_id"] == _PRED_ID
        assert "image_url" not in result  # 가짜값 금지
        assert calls["get"] >= 1


# ──────────────────────────────────────────────
# 4. 하위호환 — 즉시완료·201 starting·에러 분기
# ──────────────────────────────────────────────


class TestBackwardCompat:
    """기존 동작(200/201 즉시완료, 비정상 코드 에러)이 그대로 유지된다."""

    @pytest.mark.asyncio
    async def test_200_즉시완료(self, monkeypatch, render_key):
        """200 + succeeded(output 문자열) → 폴링 없이 즉시 status=ok."""
        _fast_poll(monkeypatch)
        handler, calls = _make_handler(
            post=(200, _prediction("succeeded", output=_OUT_URL)),
            gets=[],
        )
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64)

        assert result["status"] == "ok"
        assert result["image_url"] == _OUT_URL
        assert calls["get"] == 0  # 폴링 GET 없음(즉시완료)

    @pytest.mark.asyncio
    async def test_201_starting_폴링_성공(self, monkeypatch, render_key):
        """201 + starting(미완료)도 에러가 아니라 폴링으로 이어진다."""
        _fast_poll(monkeypatch)
        handler, calls = _make_handler(
            post=(201, _prediction("starting")),
            gets=[(200, _prediction("succeeded", output=[_OUT_URL]))],
        )
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64)

        assert result["status"] == "ok"
        assert result["image_url"] == _OUT_URL
        assert calls["get"] >= 1

    @pytest.mark.asyncio
    async def test_500_에러_분기_유지(self, monkeypatch, render_key):
        """200/201/202 외 코드(예: 500)는 기존대로 status=error."""
        handler, calls = _make_handler(post=(500, {"detail": "server error"}), gets=[])
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64)

        assert result["status"] == "error"
        assert "HTTP 500" in result["message"]
        assert calls["get"] == 0


# ──────────────────────────────────────────────
# 5. 키 부재 폴백(no_key) 유지
# ──────────────────────────────────────────────


class TestNoKeyFallback:
    """REPLICATE_API_TOKEN 부재 시 기존 no_key 폴백이 유지된다."""

    @pytest.mark.asyncio
    async def test_키_부재_no_key_외부호출_없음(self, monkeypatch):
        """키 미설정 → status=no_key 정직 안내, 외부 호출 0회."""
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        monkeypatch.delenv("REPLICATE_API_KEY", raising=False)
        handler, calls = _make_handler(post=(200, {}), gets=[])
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64)

        assert result["status"] == "no_key"
        assert "키" in result["message"]
        assert calls["post"] == 0 and calls["get"] == 0

    @pytest.mark.asyncio
    async def test_빈_이미지_입력_에러(self, monkeypatch, render_key):
        """입력 이미지가 비면 외부 호출 없이 status=error(기존 동작)."""
        handler, calls = _make_handler(post=(200, {}), gets=[])
        _install_transport(monkeypatch, handler)

        result = await svc.render_photoreal("   ")

        assert result["status"] == "error"
        assert calls["post"] == 0
