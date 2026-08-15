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
    # 명세가 요구하는 필드 — 빠지면 상세 항목이 안 실린다(값의 효과는 미실측·별도 티켓).
    assert body["detailYn"] == "Y", f"detailYn 이 빠졌거나 바뀌었다: {body.get('detailYn')!r}"


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
    # ★다섯 필드를 **전부** 본다 — 셋만 보던 판에서 `owner`·`sangtae` 줄을 지워도
    #   테스트가 초록이었다(기계 변이가 잡아냈다).
    assert items[0]["owner"] == "강***~"
    assert items[0]["sangtae"] == "현행"


# ── pick_field 자체를 태운다 ────────────────────────────────────────────────
# ★위 검사들의 픽스처는 전부 **접두사 없는** 키다. 그래서 `get` 폴백 분기(`v2 = d.get(f"get{name}")`)
#   를 통째로 지워도 살아남았다 — 두 표기 중 **한 모집단만** 태우고 있었던 것이다.

def test_pick_field는_두_표기를_모두_읽는다() -> None:
    # 모집단 A: 접두사 없음(라이브 실측 형태)
    assert hc.pick_field({"소유자": "김**"}, "소유자") == "김**"
    # 모집단 B: 접두사 있음(벤더 명세 화면 형태) — 이 분기가 없으면 None 이 된다
    assert hc.pick_field({"get소유자": "이**"}, "소유자") == "이**"
    # 두 모집단이 실제로 다른 입력이다(차가 0이면 잠금이 아니다)
    assert {"소유자": "김**"} != {"get소유자": "이**"}


def test_pick_field는_빈_문자열을_값으로_치지_않는다() -> None:
    """두 표기가 공존하고 한쪽이 비었을 때 **찬 쪽**을 고른다."""
    assert hc.pick_field({"소유자": "", "get소유자": "박**"}, "소유자") == "박**"
    # 반대로 폴백도 비었으면 원래 값을 그대로 돌려준다(없는 값을 지어내지 않는다).
    assert hc.pick_field({"소유자": "", "get소유자": ""}, "소유자") == ""
    assert hc.pick_field({}, "소유자") is None


def test_시도_별칭을_전수로_확인한다() -> None:
    """★목록형 금지 — 표에서 **파생**시킨다.

    종전엔 "서울" 하나만 봐서, 별칭 표의 다른 줄을 통째로 지워도 초록이었다.
    새 별칭이 추가돼도 이 검사가 자동으로 감시한다.
    """
    # ★파생 루프는 **삭제에 면역**이다 — 표에서 한 줄을 지우면 그 줄을 안 볼 뿐 초록이다
    #   (기계 변이가 "제주" 줄 삭제로 실증). 그래서 개수를 사실에 결속시킨다:
    #   대한민국 광역자치단체는 **17개**이고, 축약 표기는 그 전부에 있어야 한다.
    # ★잠그는 것은 **커버리지**(17개 시/도가 모두 닿는가)이지 전단사가 아니다.
    #   첫 판은 `len(_SIDO_ALIAS) == 17` + `len(set(values)) == 17` 로 **전단사를 강제**했다.
    #   그러면 "서울시 강남구 …"(현재 `extract_sido` 가 "" 를 내는 실제 결함) 를 고치려고
    #   `"서울시": "서울특별시"` 를 추가하는 **정당한 수정이 빨개진다** — 가드의 위양성도
    #   결함이다(CLAUDE.md §A-6, 2회 재발). 별칭은 늘 수 있고, 빠지는 것만 막으면 된다.
    assert len(hc._SIDO_ALIAS) >= 17, f"별칭이 모자라다 — {len(hc._SIDO_ALIAS)}개"
    assert len(set(hc._SIDO_ALIAS.values())) == 17, (
        f"17개 시/도 중 별칭이 닿지 않는 곳이 있다 — 도달 {len(set(hc._SIDO_ALIAS.values()))}개"
    )
    assert set(hc._SIDO_ALIAS.values()) <= set(hc._SIDO), "별칭이 정식 표기 표에 없는 값을 가리킨다"
    for short, full in hc._SIDO_ALIAS.items():
        assert hc.extract_sido(f"{short} 어느구 어느동 1") == full, (
            f"별칭 {short!r} → {full!r} 매핑이 끊겼다"
        )
    # 정식 표기도 파생으로 전수 확인한다.
    assert len(hc._SIDO) >= 17, f"시/도 표가 비었거나 수집 실패: {len(hc._SIDO)}"
    for full in hc._SIDO:
        assert hc.extract_sido(f"{full} 어느구 어느동 1") == full, f"정식 표기 {full!r} 를 못 뽑는다"


# ── 형제 파서 둘도 같은 규칙을 지키는지 태운다 ──────────────────────────────
# ★리뷰가 "형제 미스윕" 으로 잡은 자리다. 공용화만 하고 락을 안 걸면, 다음 사람이
#   여기를 되돌려도 아무도 모른다(기계 변이에서 이 줄들이 전부 생존했다).

class _UniqNoClient(_CapturingClient):
    async def post(self, url: str, headers: Any = None, json: Any = None) -> Any:  # noqa: A002
        type(self).captured = {"url": url, "body": json}

        class _R:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict[str, Any]:
                # ★여기는 **접두사 있는** 표기로 태운다 — 두 파서가 서로 다른 모집단을 본다.
                return {"common": {"errYn": "N"}, "data": {"list": [{
                    "get부동산고유번호": "1101-2012-009048",
                    "get구분": "토지",
                    "get소유자": "최***",
                    "get부동산소재지번": "서울특별시 강남구 역삼동 737",
                    "get상태": "현행",
                }]}}

        return _R()


@pytest.mark.asyncio
async def test_고유번호검색_파서도_두_표기를_읽는다(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _UniqNoClient)
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(hc, "_headers", lambda: {})
    monkeypatch.setattr(hc, "_host", lambda: "https://example.invalid")

    res = await hc.search_by_unique_no("1101-2012-009048")

    assert res["ok"] is True, res
    it = res["items"][0]
    assert it["unique_no"] == "11012012009048", it
    assert it["gubun"] == "토지"
    assert it["owner"] == "최***"
    assert it["jibun"] == "서울특별시 강남구 역삼동 737"
    assert it["sangtae"] == "현행"


class _RegistryClient(_CapturingClient):
    """등기부 열람 응답 — `outList` 가 dict 인 형태."""

    payload: dict[str, Any] = {}

    async def post(self, url: str, headers: Any = None, json: Any = None) -> Any:  # noqa: A002
        type(self).captured = {"url": url, "body": json}
        body = type(self).payload

        class _R:
            status_code = 200

            @staticmethod
            def json() -> dict[str, Any]:
                return body

        return _R()


@pytest.mark.asyncio
@pytest.mark.parametrize("out_list", [
    {"get소유자": "정***"},          # dict 형태
    [{"get소유자": "정***"}],        # list 형태 — 두 분기를 모두 태운다
])
async def test_등기부_열람_파서도_두_표기를_읽는다(
    monkeypatch: pytest.MonkeyPatch, out_list: Any,
) -> None:
    import httpx

    _RegistryClient.payload = {"common": {"errYn": "N"}, "data": {"outList": out_list, "pdfHex": ""}}
    monkeypatch.setattr(httpx, "AsyncClient", _RegistryClient)
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(hc, "_headers", lambda: {})
    monkeypatch.setattr(hc, "_host", lambda: "https://example.invalid")

    res = await hc.fetch_realty_registry(unique_no="1101-2012-009048")

    assert res["ok"] is True, res
    assert res["owner"] == "정***", (
        f"소유자 파싱이 끊겼다(형제 파서가 명세 표기만 읽던 자리다): {res.get('owner')!r}"
    )


# ── 두 표기가 공존할 때의 우선순위 ────────────────────────────────────────
# ★승격 전 형제 파서 둘은 `get` 접두사 **만** 읽었다. 승격 후엔 접두사 없는 쪽이 우선이다.
#   두 표기가 라이브에서 공존하고 값이 다르면 **읽는 값이 조용히 바뀐다**(리뷰 지적).
# ★정직하게: 라이브 실측(2026-08-12)은 주소검색(`in0004000168`) **한 엔드포인트뿐**이다.
#   고유번호검색·등기부열람의 실제 응답 형태는 아직 캡처하지 않았다. 그래서 여기서 잠그는
#   것은 "관측된 사실" 이 아니라 **의도된 우선순위**다 — 그 사실을 적어 둔다.

class _CoexistUniqNoClient(_UniqNoClient):
    async def post(self, url: str, headers: Any = None, json: Any = None) -> Any:  # noqa: A002
        class _R:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict[str, Any]:
                return {"common": {"errYn": "N"}, "data": {"list": [{
                    "부동산고유번호": "1101-2012-009048", "get부동산고유번호": "9999-9999-999999",
                    "소유자": "마스킹본", "get소유자": "원본",
                }]}}

        return _R()


@pytest.mark.asyncio
async def test_공존시_접두사_없는_쪽을_채택한다(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _CoexistUniqNoClient)
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(hc, "_headers", lambda: {})
    monkeypatch.setattr(hc, "_host", lambda: "https://example.invalid")

    it = (await hc.search_by_unique_no("1101-2012-009048"))["items"][0]
    # 두 값이 실제로 다르다 — 차가 0이면 우선순위를 잠그지 못한다.
    assert it["unique_no"] == "11012012009048" != "999999999999999"
    assert it["owner"] == "마스킹본", f"우선순위가 뒤집혔다: {it['owner']!r}"


@pytest.mark.asyncio
async def test_등기부_열람도_공존시_접두사_없는_쪽을_채택한다(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    _RegistryClient.payload = {"common": {"errYn": "N"}, "data": {
        "outList": {"소유자": "마스킹본", "get소유자": "원본"}, "pdfHex": ""}}
    monkeypatch.setattr(httpx, "AsyncClient", _RegistryClient)
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(hc, "_headers", lambda: {})
    monkeypatch.setattr(hc, "_host", lambda: "https://example.invalid")

    res = await hc.fetch_realty_registry(unique_no="1101-2012-009048")
    assert res["owner"] == "마스킹본", f"우선순위가 뒤집혔다: {res.get('owner')!r}"
