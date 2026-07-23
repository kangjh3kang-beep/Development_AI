"""레인C(R2b, HIGH 봉합) — VWorldService.get_land_use_plan의 None(하드 실패) vs
[](확인 완료·규제 없음) 구분 계약 테스트.

근본원인(R1 재지적): 키 미설정·HTTP 실패가 모두 []로 뭉개져 design_audit_orchestrator의
special_districts 배선점에서 "조회 못 함"이 "확인 결과 규제구역 없음"으로 둔갑했다(과대낙관
방향 — 개발제한구역 필지인데 "제약 없음"). 이 파일은 상류(get_land_use_plan) 계약 자체를
검증한다. design_audit_orchestrator 소비처 검증은 test_design_audit_core.py 참조.
"""
from __future__ import annotations

import httpx

from app.core import config as _cfg
from app.services.external_api.vworld_service import VWorldService


def _mock_transport(responses: list[httpx.Response | Exception]):
    """호출 순서대로 응답(또는 예외)을 돌려주는 MockTransport."""
    calls = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = min(calls["i"], len(responses) - 1)
        calls["i"] += 1
        item = responses[i]
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.MockTransport(handler)


def _land_use_response(fields: list[dict], total: int | None = None) -> httpx.Response:
    return httpx.Response(200, json={
        "landUses": {
            "field": fields,
            "totalCount": total if total is not None else len(fields),
        }
    })


async def _run(monkeypatch, *, api_key: str, responses: list[httpx.Response | Exception]):
    monkeypatch.setattr(_cfg.settings, "VWORLD_API_KEY", api_key)
    transport = _mock_transport(responses)
    _orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: _orig(transport=transport, headers=kw.get("headers")),
    )
    return await VWorldService().get_land_use_plan("4159010500100010000")


# ─────────────────────────────────────────────────────────────────────────────
# 케이스 A — 실값(성공 + 규제 N건)
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_a_success_with_districts_returns_list(monkeypatch):
    out = await _run(
        monkeypatch, api_key="TESTKEY",
        responses=[_land_use_response([{"prposAreaDstrcCodeNm": "개발제한구역"}])],
    )
    assert out == [{
        "district_name": "개발제한구역", "district_code": "", "conflict_status": "",
        "land_name": "", "register_date": "", "last_updated": "",
    }]


# ─────────────────────────────────────────────────────────────────────────────
# 케이스 B — 조회 성공 + 규제 0건("확인완료·규제없음" — 진짜 빈 리스트, None 아님)
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_b_success_zero_districts_returns_empty_list_not_none(monkeypatch):
    out = await _run(monkeypatch, api_key="TESTKEY", responses=[_land_use_response([])])
    assert out == []
    assert out is not None


# ─────────────────────────────────────────────────────────────────────────────
# 케이스 C — 예외(HTTP 실패) — None(하드 실패, [] 아님)
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_c_http_failure_returns_none_not_empty_list(monkeypatch):
    out = await _run(
        monkeypatch, api_key="TESTKEY",
        responses=[httpx.ConnectError("connection refused")],
    )
    assert out is None, "HTTP 실패는 None이어야 한다 — []는 '확인완료·규제없음'으로 오독됨"


async def test_case_c_partial_success_then_failure_keeps_partial_results(monkeypatch):
    """1페이지 성공(총 200건 신호) 후 2페이지에서 실패 — 이미 확보한 실데이터는 보존(전체 None 아님)."""
    out = await _run(
        monkeypatch, api_key="TESTKEY",
        responses=[
            _land_use_response([{"prposAreaDstrcCodeNm": "도시지역"}], total=200),
            httpx.ConnectError("connection refused"),
        ],
    )
    assert out == [{
        "district_name": "도시지역", "district_code": "", "conflict_status": "",
        "land_name": "", "register_date": "", "last_updated": "",
    }]


# ─────────────────────────────────────────────────────────────────────────────
# 케이스 D — VWORLD_API_KEY 미설정(조회 자체를 시도하지 않음) — None
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_d_no_api_key_returns_none_not_empty_list(monkeypatch):
    monkeypatch.setattr(_cfg.settings, "VWORLD_API_KEY", "")
    out = await VWorldService().get_land_use_plan("4159010500100010000")
    assert out is None, "키 미설정은 조회 자체를 시도 안 한 것 — []는 '규제없음 확인'으로 오독됨"
