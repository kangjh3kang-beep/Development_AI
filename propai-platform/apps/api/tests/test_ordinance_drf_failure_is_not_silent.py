"""조례 조회가 **DRF 200-실패를 조용히 삼키지 않는다** — 배선 락.

【왜 별도 파일인가】
검증기(`moleg_drf_envelope`)를 격리 테스트만 하면 **배선이 무잠금**이다.
실측: `ordinance_service` 안의 `raise_unless_expected_xml(...)` 호출을 `pass` 로 바꾸는
변이가 **SURVIVED** 했다(검증기 단위 테스트는 전부 초록인 채로).

★그리고 이 경로는 **관측 지점이 로그뿐**이다 — 광범위 `except Exception: return None` 이
결과를 `None` 으로 만들어 **성공/실패의 반환값이 같다**. 그래서 반환값이 아니라
**실패 사유가 로그에 실리는가**를 단언한다(그것이 이 봉합이 만든 유일한 관측 가능 차이다).
"""

from typing import Any

import pytest

from app.services.land_intelligence import ordinance_service as OS

FAILURE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<Response><result>사용자 정보 검증에 실패하였습니다.</result>"
    "<msg>IP주소 및 도메인주소를 등록해 주세요.</msg></Response>"
)
# 정상 목록 응답(대조군) — 실측 루트태그 <OrdinSearch>.
OK_LIST_XML = (
    '<?xml version="1.0"?><OrdinSearch><totalCnt>1</totalCnt>'
    "<law><자치법규ID>2097518</자치법규ID><자치법규명>오산시 도시계획 조례</자치법규명>"
    "<지자체기관명>경기도 오산시</지자체기관명></law></OrdinSearch>"
)


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:  # DRF 는 실패도 200 이라 여기선 아무 일도 없다
        return None


class _Client:
    """httpx.AsyncClient 대역 — **네트워크만** 가로챈다(파서·검증기는 진짜가 돈다).

    ★호출 **순서별로 다른 본문**을 줄 수 있어야 한다. 모든 호출에 같은 본문을 주면
    목록조회(Step 1)에서 먼저 예외가 나 **본문조회(Step 2) 검증에 도달하지 못하고**,
    그 자리가 무잠금으로 남는다(변이 실측: Step 2 검증 제거가 SURVIVED 였다).
    """

    def __init__(self, body: str | list[str]) -> None:
        self._bodies = list(body) if isinstance(body, list) else [body]
        self._i = 0

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def get(self, *a: Any, **k: Any) -> _Resp:
        body = self._bodies[min(self._i, len(self._bodies) - 1)]
        self._i += 1
        return _Resp(body)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    """키가 비면 함수가 조기 반환해 **검증기까지 가지도 않는다**(공허한 초록 차단)."""
    monkeypatch.setattr(OS.settings, "MOLEG_API_KEY", "test-oc", raising=False)


def _run(monkeypatch: pytest.MonkeyPatch, body: str, caplog: pytest.LogCaptureFixture):
    import asyncio

    # ★대역 **인스턴스를 공유**한다. `AsyncClient(...)` 가 호출될 때마다 새로 만들면
    #   호출 순번 카운터가 리셋돼 Step 2 에도 Step 1 의 본문이 간다(내 첫 판이 그랬다).
    client = _Client(body)
    monkeypatch.setattr(OS.httpx, "AsyncClient", lambda *a, **k: client)
    svc = OS.OrdinanceService()
    with caplog.at_level("WARNING"):
        out = asyncio.run(
            svc._fetch_from_moleg_api("경기도", "오산시", "제2종일반주거지역", jurisdiction="오산시")
        )
    return out, caplog.text


def test_failure_envelope_reaches_the_log_with_its_reason(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """★배선 — 실패 사유가 **로그까지** 도달한다(검증기를 안 부르면 이 문자열이 없다)."""
    out, log = _run(monkeypatch, FAILURE_XML, caplog)
    assert out is None, "실패인데 값을 냈다"
    assert "사용자 정보 검증에 실패" in log, (
        "DRF 200-실패 사유가 로그에 없다 — 검증기가 배선되지 않았거나 사유가 유실됐다.\n"
        f"로그: {log[:300]!r}"
    )


def test_success_path_does_not_log_that_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """★대조 모집단 — 정상 응답에서는 그 사유가 **찍히지 않는다**(위양성 차단).

    정상 목록이 오면 이후 단계(본문조회·파싱)에서 값을 못 찾아 `None` 이 될 수는 있다.
    그것과 *"인증 실패"* 는 **다른 사건**이고, 로그가 그 둘을 갈라야 한다.
    """
    _out, log = _run(monkeypatch, OK_LIST_XML, caplog)
    assert "사용자 정보 검증에 실패" not in log, f"정상 응답에 실패 사유가 찍혔다: {log[:300]!r}"


def test_step2_body_fetch_failure_also_reaches_the_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """★2단계 배선 — **목록은 정상인데 본문조회가 실패**하는 모집단.

    앞 테스트는 Step 1 에서 예외가 나 Step 2 검증에 **도달조차 못 한다**.
    두 호출을 갈라 줘야 그 자리가 잠긴다(변이 실측으로 확인한 구멍).
    """
    out, log = _run(monkeypatch, [OK_LIST_XML, FAILURE_XML], caplog)
    assert out is None
    assert "사용자 정보 검증에 실패" in log, (
        "본문조회(Step 2) 실패 사유가 로그에 없다 — 그 자리 검증기가 배선되지 않았다.\n"
        f"로그: {log[:300]!r}"
    )


def test_failure_actually_blocks_parsing_not_just_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """★"막았다" 를 본다 — 로그만 보면 *"찍고 그냥 진행"* 구현이 초록이다.

    독립 리뷰가 변이로 적발: 검증기를 `raise` 대신 **같은 사유를 로그만 찍고 반환**하도록
    바꿔도 기존 배선 락 3건이 전부 통과했다. 로그 도달은 **감지**의 증거일 뿐
    **차단**의 증거가 아니다.

    그래서 실패 봉투일 때 **하류 파서가 호출되지 않는지**를 단언한다.
    """
    called: list[str] = []
    real_id = OS.OrdinanceService._parse_ordin_id
    real_bcr = OS.OrdinanceService._parse_bcr_far_from_text

    def spy_id(self, *a, **k):  # type: ignore[no-untyped-def]
        called.append("_parse_ordin_id")
        return real_id(self, *a, **k)

    def spy_bcr(self, *a, **k):  # type: ignore[no-untyped-def]
        called.append("_parse_bcr_far_from_text")
        return real_bcr(self, *a, **k)

    monkeypatch.setattr(OS.OrdinanceService, "_parse_ordin_id", spy_id)
    monkeypatch.setattr(OS.OrdinanceService, "_parse_bcr_far_from_text", spy_bcr)

    # 모집단 A — Step 1 실패: 하류 파싱이 **한 번도** 불리면 안 된다.
    called.clear()
    _out, _log = _run(monkeypatch, FAILURE_XML, caplog)
    assert called == [], f"실패를 감지하고도 파싱을 진행했다(차단 실패): {called}"

    # ★대조 모집단 — 정상이면 하류가 **실제로 불린다**(위 단언이 공허하지 않다는 증거).
    called.clear()
    _run(monkeypatch, [OK_LIST_XML, OK_LIST_XML], caplog)
    assert "_parse_ordin_id" in called, (
        f"정상 경로에서도 파서가 안 불렸다 — 위 '호출 0건' 단언이 공허하다: {called}"
    )
