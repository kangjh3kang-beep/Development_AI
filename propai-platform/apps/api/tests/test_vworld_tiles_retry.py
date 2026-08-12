"""VWorld 타일 프록시의 **간헐 5xx 재시도**를 잠근다.

★왜 (2026-08-12 프로덕션 실측):
    같은 GetCapabilities 요청을 두 서버에서 각 6회 보냈더니
      168 → 200 200 200 200 200 200
      158 → 502 502 502 000 502 502
    상류(VWorld)가 **간헐적으로 502** 를 내고, 그때마다 화면에 "지적 타일 오류"가 떴다.
    이 프록시 로그에 최근 6시간 502 가 171건·연결 실패가 144건 쌓여 있었는데, 같은
    파라미터를 그 자리에서 5회 재요청하면 **5/5 성공**(34,824B)했다.
    → 재시도 한 번이면 대부분 살아난다.

★재시도하지 않는 것: 4xx 는 우리 요청이 잘못된 것이라 다시 보내도 같다(키 무효·레이어 오기).
  헛수고 + 상류 부담 + 오류 원인 은폐가 된다. 그래서 5xx·네트워크 예외에만 건다.
"""

from __future__ import annotations

import httpx
import pytest

from app.routers import vworld_tiles as vt


def _resp(status: int, *, body: bytes = b"\x89PNG\r\n", ctype: str = "image/png") -> httpx.Response:
    return httpx.Response(
        status, content=body, headers={"content-type": ctype},
        request=httpx.Request("GET", "https://api.vworld.kr/req/wms"),
    )


@pytest.mark.asyncio
async def test_간헐_502는_재시도해서_살린다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vt, "_RETRY_BACKOFF_S", 0)  # 테스트를 실시간으로 끌지 않는다
    calls: list[int] = []

    async def send(_client: httpx.AsyncClient) -> httpx.Response:
        calls.append(1)
        return _resp(502) if len(calls) == 1 else _resp(200)

    got = await vt._fetch_with_retry(send, kind="WMS", ctx={})

    assert len(calls) == 2, f"재시도하지 않았다(호출 {len(calls)}회) — 간헐 502 가 그대로 사용자에게 간다"
    assert isinstance(got, httpx.Response) and got.status_code == 200


@pytest.mark.asyncio
async def test_4xx는_재시도하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """우리 요청이 잘못된 것이라 다시 보내도 같다 — 헛수고이자 원인 은폐다."""
    monkeypatch.setattr(vt, "_RETRY_BACKOFF_S", 0)
    calls: list[int] = []

    async def send(_client: httpx.AsyncClient) -> httpx.Response:
        calls.append(1)
        return _resp(401, body=b"<xml/>", ctype="application/xml")

    got = await vt._fetch_with_retry(send, kind="WMS", ctx={})

    assert len(calls) == 1, f"4xx 를 재시도했다({len(calls)}회) — 같은 답이 올 뿐이다"
    assert isinstance(got, httpx.Response) and got.status_code == 401


@pytest.mark.asyncio
async def test_네트워크_예외도_재시도하고_끝내_실패하면_정직하게_알린다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vt, "_RETRY_BACKOFF_S", 0)
    calls: list[int] = []

    async def send(_client: httpx.AsyncClient) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("Server disconnected without sending a response.")

    got = await vt._fetch_with_retry(send, kind="WMS", ctx={})

    assert len(calls) == vt._RETRY_ATTEMPTS, f"네트워크 예외를 재시도하지 않았다({len(calls)}회)"
    # ★끝내 실패하면 성공한 척하지 않는다 — 빈 타일로 덮으면 '데이터 없음'과 구분이 사라진다.
    assert not isinstance(got, httpx.Response), "실패했는데 상류 응답인 척했다"
    assert got.status_code == 502


@pytest.mark.asyncio
async def test_재시도가_무한이_아니다(monkeypatch: pytest.MonkeyPatch) -> None:
    """타일은 사용자가 기다리는 경로다 — 상한이 없으면 지연이 곱해진다."""
    monkeypatch.setattr(vt, "_RETRY_BACKOFF_S", 0)
    calls: list[int] = []

    async def send(_client: httpx.AsyncClient) -> httpx.Response:
        calls.append(1)
        return _resp(503)

    await vt._fetch_with_retry(send, kind="WMTS", ctx={})
    assert len(calls) == vt._RETRY_ATTEMPTS, f"시도 횟수가 상한과 다르다: {len(calls)}"
    assert vt._RETRY_ATTEMPTS <= 3, "재시도 상한이 과하다 — 타일 대기가 곱으로 늘어난다"
