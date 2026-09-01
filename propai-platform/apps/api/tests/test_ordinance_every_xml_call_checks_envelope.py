"""★**모든** 법제처 XML 호출부가 200-오류 봉투를 검사한다 — **파생형** 배선 락.

## 왜 이 파일이 따로 필요한가 (2026-09-01 실측)

형제 락 `test_ordinance_drf_failure_is_not_silent.py` 는 **`_fetch_from_moleg_api` 한 함수만**
태운다(목록형). 그래서 같은 파일의 **형제 함수 `_fetch_ordinance_xml` 이 무방비인 채로
전부 초록**이었다 — 봉투 검사가 붙은 XML 호출부는 **4곳 중 2곳**뿐이었다.

    줄  716 / 747  `_fetch_from_moleg_api`   → 검사 있음
    줄 1551 / 1567 `_fetch_ordinance_xml`    → **검사 0건**  ← 형제 미러 누락

`_fetch_ordinance_xml` 의 소비처는 `resolve_slope_criteria`(T2 경사도)이고, 그 함수는
`None` 을 **"해당 지자체 조례 없음 → 국가기준 25도 폴백"** 으로 읽는다. 즉 **인증/IP 실패가
「조례 미보유」로 오귀속**된다.

★**사람이 센 목록은 곧 상한이 된다.** 그래서 여기서는 호출부를 **`ast` 로 파생**시킨다 —
  다섯 번째 XML 호출부가 생기면 **아무도 이 파일을 고치지 않아도** 자동으로 감시망에 들어온다.

★판정을 정규식이 아니라 **파서**로 한다(주석·문자열·독스트링에 뚫리지 않게).

## 라이브 실측 — `expect` 루트태그의 출처 (2026-09-01, 대조군 포함)

    목록 정상            HTTP 200 · 루트 <OrdinSearch>
    본문 정상            HTTP 200 · 루트 <LawService>
    인증실패(틀린 OC)    **HTTP 200** · 루트 <Response><result>사용자 정보 검증에 실패하였습니다.
    본문 대상없음        HTTP 200 · 루트 <Law>일치하는 자치법규가 없습니다.

`raise_for_status()` 는 **어느 실패에서도 발화하지 않는다.**
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.services.land_intelligence import ordinance_service as OS

_SRC = Path(OS.__file__)

_GUARD = "raise_unless_expected_xml"


def _module() -> ast.Module:
    return ast.parse(_SRC.read_text(encoding="utf-8"))


def _is_xml_call(node: ast.AST) -> bool:
    """`client.get(..., params={... "type": "XML" ...})` 인가 — **ast 로** 판정."""
    if not isinstance(node, ast.Call):
        return False
    for kw in node.keywords:
        if kw.arg != "params" or not isinstance(kw.value, ast.Dict):
            continue
        for k, v in zip(kw.value.keys, kw.value.values):
            if (isinstance(k, ast.Constant) and k.value == "type"
                    and isinstance(v, ast.Constant) and v.value == "XML"):
                return True
    return False


def xml_call_sites() -> dict[str, list[int]]:
    """XML DRF 호출부를 **감싸는 함수 이름 → 줄번호들** 로 파생시킨다."""
    out: dict[str, list[int]] = {}
    for fn in ast.walk(_module()):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lines = [n.lineno for n in ast.walk(fn) if _is_xml_call(n)]
        if lines:
            out.setdefault(fn.name, []).extend(lines)
    return out


def guarded_functions() -> set[str]:
    """`raise_unless_expected_xml` 를 **실제로 호출**하는 함수 이름들(ast)."""
    out: set[str] = set()
    for fn in ast.walk(_module()):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == _GUARD:
                out.add(fn.name)
    return out


def test_derivation_is_alive_before_any_assertion():
    """★생존 단언을 **비교 앞에** 둔다 — 파생이 비면 «전부 통과» 가 공허하게 참이 된다."""
    sites = xml_call_sites()
    total = sum(len(v) for v in sites.values())
    assert total >= 4, f"XML 호출부 파생이 {total}건 — 추출기가 죽었다(시그니처가 바뀌었나?)"
    assert len(sites) >= 2, f"호출부를 가진 함수가 {len(sites)}개 — 형제 축이 사라졌다"
    # 음성 대조군 — 가드 탐지기가 아무 함수나 집지 않는다.
    assert "_parse_ordin_id" not in guarded_functions()


def test_every_function_that_calls_drf_xml_checks_the_envelope():
    """★**모든** XML 호출부가 봉투를 검사한다(파생형 — 다섯 번째가 생겨도 자동 감시).

    법제처는 인증/IP 실패를 **HTTP 200** 으로 돌려주므로 `raise_for_status()` 로는
    못 잡는다. 검사가 없으면 그 실패가 **「조례 미보유」로 오귀속**된다.
    """
    unguarded = {fn: lines for fn, lines in xml_call_sites().items()
                 if fn not in guarded_functions()}
    assert not unguarded, (
        f"XML 을 부르면서 봉투 검사가 없는 함수: {unguarded} — "
        f"인증 실패가 「조례 미보유」로 오귀속된다")


# ---------------------------------------------------------------------------
# ★형제 함수 `_fetch_ordinance_xml` 의 **행위** 락 — 배선만 보지 않는다
# ---------------------------------------------------------------------------

FAILURE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<Response><result>사용자 정보 검증에 실패하였습니다.</result>"
    "<msg>IP주소 및 도메인주소를 등록해 주세요.</msg></Response>"
)
OK_LIST_XML = (
    '<?xml version="1.0"?><OrdinSearch><totalCnt>1</totalCnt>'
    "<law><자치법규ID>2097518</자치법규ID><자치법규명>오산시 도시계획 조례</자치법규명>"
    "</law></OrdinSearch>"
)
OK_TEXT_XML = (
    '<?xml version="1.0"?><LawService><자치법규기본정보>'
    "<자치법규명>오산시 도시계획 조례</자치법규명></자치법규기본정보>"
    "<조문내용>개발행위허가 경사도 20도 이하</조문내용></LawService>"
)


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:  # ★DRF 는 실패도 200 이라 여기선 아무 일도 없다
        return None


class _Client:
    """httpx.AsyncClient 대역 — **네트워크만** 가로챈다(파서·검증기는 진짜가 돈다)."""

    def __init__(self, bodies: list[str]) -> None:
        self._bodies, self._i = list(bodies), 0

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
    """키가 비면 함수가 **조기 반환**해 검증기까지 가지도 않는다(공허한 초록 차단)."""
    monkeypatch.setattr(OS.settings, "MOLEG_API_KEY", "test-oc", raising=False)


def _run(monkeypatch: pytest.MonkeyPatch, bodies: list[str], caplog):
    # ★대역 **인스턴스를 공유**한다 — 매번 새로 만들면 순번이 리셋돼 Step 2 에도
    #   Step 1 의 본문이 가고, 그 자리가 무잠금으로 남는다(형제 락이 겪은 실패).
    client = _Client(bodies)
    monkeypatch.setattr(OS.httpx, "AsyncClient", lambda *a, **k: client)
    svc = OS.OrdinanceService()
    with caplog.at_level("WARNING"):
        out = asyncio.run(svc._fetch_ordinance_xml("오산시"))
    return out, caplog.text


def test_step1_auth_failure_surfaces_the_reason(monkeypatch, caplog):
    """목록조회가 인증 실패면 **사유가 로그에 실린다** — 반환값은 성공/실패가 같다(`None`)."""
    out, log = _run(monkeypatch, [FAILURE_XML], caplog)
    assert out is None
    assert "사용자 정보 검증에 실패" in log, f"실패 사유가 로그에 없다: {log!r}"


def test_step2_body_failure_also_surfaces_the_reason(monkeypatch, caplog):
    """★본문조회 실패도 잡힌다 — Step 1 만 잠그면 Step 2 가 무잠금으로 남는다."""
    out, log = _run(monkeypatch, [OK_LIST_XML, FAILURE_XML], caplog)
    assert out is None
    assert "사용자 정보 검증에 실패" in log, f"Step 2 실패 사유가 로그에 없다: {log!r}"


def test_success_path_is_not_reported_as_failure(monkeypatch, caplog):
    """★**두 번째 모집단** — 정상 응답은 본문을 돌려주고 실패 로그를 남기지 않는다.

    이것이 없으면 *"항상 실패로 처리하는 구현"* 이 위 두 락을 전부 통과한다.
    """
    out, log = _run(monkeypatch, [OK_LIST_XML, OK_TEXT_XML], caplog)
    assert out is not None and "LawService" in out, f"정상 경로가 막혔다: {out!r}"
    assert "검증에 실패" not in log, f"정상인데 실패 로그가 났다(과잉 억제): {log!r}"


def test_no_match_envelope_is_not_mistaken_for_a_body(monkeypatch, caplog):
    """본문조회 「대상 없음」(`<Law>…없습니다`)도 **본문이 아니다** — 파싱으로 넘기지 않는다."""
    no_match = '<?xml version="1.0"?><Law>일치하는 자치법규가 없습니다.</Law>'
    out, _ = _run(monkeypatch, [OK_LIST_XML, no_match], caplog)
    assert out is None, f"오류 봉투가 조례 본문으로 통과했다: {out!r}"
