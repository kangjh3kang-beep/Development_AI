"""하이픈 주소검색 요청·응답 계약을 잠근다 — 등기 열람 불가의 **진짜 근본원인**.

2026-08-12 명세 대조 + 라이브 실측으로 확정한 두 결함:

1. **요청 값 형식** — `kindcls`·`cls_flag` 는 **한글 문자열**(전체/토지/…, 현행/폐쇄/…)인데
   내부 코드("0"/"1")를 그대로 보냈다. 그리고 **필수 필드 `admin_regn1`(시/도)를 아예
   보내지 않았다.**
2. **응답 파싱 키** — 실제 응답 키에는 `get` 접두사가 **없다**(`부동산고유번호`).
   명세 화면 스키마는 `get부동산고유번호` 로 표시한다. 종전 파서는 `get…` 만 읽어
   **검색이 성공해도** `unique_no` 가 빈 문자열이 됐다.

★두 결함 모두 겉으로는 `[C0000-002] 입력하신 검색조건에 대한 결과가 없습니다` 로 보였다.
"데이터가 없다" 처럼 읽혀 **약 3주간 원인이 오해**됐다. 실제로는 우리 요청이 불완전했다.

★라이브 확증(수정 후): 역삼동 737 → `11012012009048`(토지) · 논현동 1-1 →
`11462009000054` · 의정부동 224 → `28012005012567`. 수정 전에는 모두 결과 0건.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.registry import hyphen_client as hc


def test_시도를_주소에서_뽑는다() -> None:
    """`admin_regn1` 은 **필수**다 — 빠지면 '결과 없음' 처럼 보인다."""
    assert hc.extract_sido("서울특별시 강남구 역삼동 737") == "서울특별시"
    # 축약 표기도 흔하다("서울 강남구 …").
    assert hc.extract_sido("서울 강남구 역삼동 737") == "서울특별시"
    assert hc.extract_sido("경기도 의정부시 의정부동 224") == "경기도"
    # 못 뽑는 경우를 **빈 문자열로 정직하게** 돌려준다(호출부가 "전체" 로 대체).
    assert hc.extract_sido("역삼동 737") == ""


class _CapturingClient:
    """요청 본문을 가로채는 스텁 — 실제 하이픈을 부르지 않는다."""

    captured: dict[str, Any] = {}

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def __aenter__(self) -> _CapturingClient:
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def post(self, url: str, headers: Any = None, json: Any = None) -> Any:  # noqa: A002
        type(self).captured = {"url": url, "body": json}

        class _R:
            status_code = 200

            @staticmethod
            def json() -> dict[str, Any]:
                # ★실제 응답 형태 — `get` 접두사가 **없다**(라이브 실측).
                return {
                    "common": {"errYn": "N"},
                    "data": {
                        "list": [{
                            "부동산고유번호": "1101-2012-009048",
                            "구분": "토지",
                            "소유자": "강***~",
                            "부동산소재지번": "서울특별시 강남구 역삼동 737",
                            "상태": "현행",
                        }],
                        "totCnt": "1",
                    },
                }

        return _R()


@pytest.mark.asyncio
async def test_요청이_한글값과_필수_시도를_보낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    """숫자 코드를 그대로 보내면 하이픈은 '결과 없음' 을 돌려준다 — 그 회귀를 막는다."""
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    monkeypatch.setattr(hc, "_headers", lambda: {})
    monkeypatch.setattr(hc, "_host", lambda: "https://example.invalid")

    await hc._search_single_address("서울특별시 강남구 역삼동 737", kindcls="2", cls_flag="1")

    body = _CapturingClient.captured["body"]
    assert body["kindcls"] == "토지", f"내부 코드가 그대로 나갔다: {body['kindcls']!r}"
    assert body["cls_flag"] == "현행", f"내부 코드가 그대로 나갔다: {body['cls_flag']!r}"
    assert body["admin_regn1"] == "서울특별시", (
        f"필수 필드 admin_regn1 이 빠졌거나 틀렸다: {body.get('admin_regn1')!r}"
    )
    assert body["simple_address"] == "서울특별시 강남구 역삼동 737"


@pytest.mark.asyncio
async def test_응답을_get접두사_없이도_읽는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """검색이 성공해도 파싱이 틀리면 `unique_no` 가 비어 '고유번호 없음' 으로 떨어진다."""
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    monkeypatch.setattr(hc, "_headers", lambda: {})
    monkeypatch.setattr(hc, "_host", lambda: "https://example.invalid")

    res = await hc._search_single_address("서울특별시 강남구 역삼동 737")

    assert res["ok"] is True, res
    items = res["items"]
    assert len(items) == 1, items
    # 하이픈(-)은 제거해 정규화한다.
    assert items[0]["unique_no"] == "11012012009048", (
        f"응답 키를 못 읽어 고유번호가 비었다: {items[0]!r}"
    )
    assert items[0]["gubun"] == "토지"
    assert items[0]["jibun"] == "서울특별시 강남구 역삼동 737"
