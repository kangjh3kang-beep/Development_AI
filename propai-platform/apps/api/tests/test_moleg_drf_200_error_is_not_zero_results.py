"""법제처 DRF **200-오류 봉투**가 「결과 0건」으로 위장하던 것을 잠근다.

## 라이브 실측 (2026-08-27)

    GET http://www.law.go.kr/DRF/lawSearch.do?OC=<실제키>&target=admrul&type=JSON&query=표준건축비
    → HTTP 200 · application/json;charset=UTF-8
      {"result":"사용자 정보 검증에 실패하였습니다.",
       "msg":"OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 IP주소 및 도메인주소를 등록해 주세요."}

★**대조군이 원인을 갈랐다** — `.env` 의 실제 키와 **일부러 틀린 키**가 **동일한 오류**를 냈다.
  키가 틀린 게 아니라 **호출 IP 가 미등록**이다(법제처 프로비저닝 2관문).

## 이 봉투가 만든 거짓말 둘

- `search_admrule` → `available=True, results=[]` → `detect_gosi_update` 가
  **`checked=True, changed=False`**(= *"확인했고 고시 안 바뀜"*)
- `check_law_updates` → `raise_for_status()` 통과 → `공포일자=""` → **"변경 없음"**,
  `failures=0` 이라 *"전건 실패 시 RuntimeError"* 가드가 **발화 불가**

## 단언의 형태

*"이 단언이 초록일 때 **반대로 틀린 구현도** 초록인가?"* — 그래서 전부 **두 모집단**이다:
**오류 봉투**와 **정상 응답(0건 포함)** 을 같은 실행에서 가른다. 한쪽만 보면
*"전부 오류로 본다"* 는 구현(정상 조회를 막는 위양성)이 통과한다.
"""

from __future__ import annotations

import pytest

from app.services.legal.moleg_drf_envelope import (
    MolegDrfError,
    drf_error_reason,
    raise_if_drf_error,
)

#: 라이브에서 받은 **실제** 오류 본문(바이트 그대로).
LIVE_ERROR_PAYLOAD = {
    "result": "사용자 정보 검증에 실패하였습니다.",
    "msg": "OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 IP주소 및 도메인주소를 등록해 주세요.",
}
#: 정상 응답 — ★**결과가 0건인 정상 응답**이다. 이것이 오류로 판정되면 위양성이다.
LIVE_OK_EMPTY = {"AdmRulSearch": {"totalCnt": "0", "admrul": []}}
LIVE_OK_HIT = {"AdmRulSearch": {"totalCnt": "1", "admrul": [{"행정규칙명": "표준건축비 고시"}]}}


class TestEnvelopeDetection:
    def test_live_error_payload_is_detected(self):
        reason = drf_error_reason(LIVE_ERROR_PAYLOAD)
        assert reason is not None
        assert "사용자 정보 검증" in reason
        assert "IP주소" in reason, "사유를 표면까지 실어야 조사자가 원인을 안다"

    @pytest.mark.parametrize("ok", [LIVE_OK_EMPTY, LIVE_OK_HIT])
    def test_normal_responses_are_not_errors(self, ok):
        """★반대 모집단 — **0건인 정상 응답**을 오류로 보면 정상 조회를 막는다."""
        assert drf_error_reason(ok) is None

    def test_raise_helper_splits_the_two(self):
        with pytest.raises(MolegDrfError):
            raise_if_drf_error(LIVE_ERROR_PAYLOAD)
        raise_if_drf_error(LIVE_OK_EMPTY)  # 예외 없음
        raise_if_drf_error(LIVE_OK_HIT)

    def test_result_key_alone_does_not_trigger(self):
        """`result` 라는 이름만으로 판정하지 않는다 — 정상 루트키가 있으면 오류가 아니다."""
        assert drf_error_reason({"AdmRulSearch": {}, "result": "ok"}) is None

    def test_empty_error_fields_are_not_an_error(self):
        assert drf_error_reason({"result": "", "msg": ""}) is None
        assert drf_error_reason({}) is None
        assert drf_error_reason("문자열") is None


class TestConsumersStopLying:
    """★진짜 결함이 사는 층 — **소비처가 무엇을 단정하는가**."""

    @staticmethod
    def _patch_response(monkeypatch, payload):
        """`httpx.AsyncClient.get` 이 200 + payload 를 주도록 바꾼다."""
        import httpx

        class _R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return payload

        async def _get(self, *a, **k):
            return _R()

        monkeypatch.setattr(httpx.AsyncClient, "get", _get)

    def test_search_admrule_reports_unavailable_on_error_envelope(self, monkeypatch):
        import asyncio

        from app.services.legal.gosi_search_service import GosiSearchService

        monkeypatch.setattr(GosiSearchService, "_key", staticmethod(lambda: "dummy"))
        self._patch_response(monkeypatch, LIVE_ERROR_PAYLOAD)
        out = asyncio.run(GosiSearchService().search_admrule("표준건축비"))
        assert out["available"] is False, "★조회가 거부됐는데 available=True 면 거짓 0건이 된다"
        assert "인증" in (out.get("reason") or "") or "IP" in (out.get("reason") or "")

    def test_search_admrule_still_reports_available_on_genuine_zero(self, monkeypatch):
        """★반대 모집단 — **진짜 0건**은 여전히 `available=True` 여야 한다(과잉 억제 탐지)."""
        import asyncio

        from app.services.legal.gosi_search_service import GosiSearchService

        monkeypatch.setattr(GosiSearchService, "_key", staticmethod(lambda: "dummy"))
        self._patch_response(monkeypatch, LIVE_OK_EMPTY)
        out = asyncio.run(GosiSearchService().search_admrule("없는고시명"))
        assert out["available"] is True
        assert out["results"] == []

    def test_detect_gosi_update_says_checked_false_not_unchanged(self, monkeypatch):
        """★종단 — 「확인했고 안 바뀜」이라는 **거짓 단정**이 사라져야 한다."""
        import asyncio

        from app.services.cost.basic_building_cost import detect_gosi_update
        from app.services.legal.gosi_search_service import GosiSearchService

        monkeypatch.setattr(GosiSearchService, "_key", staticmethod(lambda: "dummy"))
        self._patch_response(monkeypatch, LIVE_ERROR_PAYLOAD)
        out = asyncio.run(detect_gosi_update())
        assert out["checked"] is False, "★조회 불가를 「확인함」이라고 하면 개정이 영원히 안 잡힌다"
        assert out.get("changed") is not False or out["checked"] is False

    def test_detect_gosi_update_genuine_zero_is_still_checked(self, monkeypatch):
        """★반대 모집단 — 진짜 0건이면 `checked=True`(조회는 됐다)."""
        import asyncio

        from app.services.cost.basic_building_cost import detect_gosi_update
        from app.services.legal.gosi_search_service import GosiSearchService

        monkeypatch.setattr(GosiSearchService, "_key", staticmethod(lambda: "dummy"))
        self._patch_response(monkeypatch, LIVE_OK_EMPTY)
        out = asyncio.run(detect_gosi_update())
        assert out["checked"] is True

    def test_check_law_updates_raises_instead_of_reporting_no_change(self, monkeypatch):
        """★`regulation_monitor` — **전건 200-오류**면 「변경 없음」이 아니라 시끄럽게 죽어야 한다.

        이 함수는 주석에 *"빈 [] 와 감지 불가를 구분한다"* 고 **선언**해 놓고
        `raise_for_status()` 에만 의존해 그 위장에 뚫려 있었다.
        """
        import asyncio

        from app.services.regulation_monitor.regulation_monitor import RegulationMonitorService

        self._patch_response(monkeypatch, LIVE_ERROR_PAYLOAD)
        with pytest.raises(RuntimeError):
            asyncio.run(RegulationMonitorService().check_law_updates())

    def test_check_law_updates_returns_empty_on_genuine_no_change(self, monkeypatch):
        """★반대 모집단 — 정상 응답이고 최근 개정이 없으면 **빈 리스트**(예외 아님)."""
        import asyncio

        from app.services.regulation_monitor.regulation_monitor import RegulationMonitorService

        self._patch_response(monkeypatch, {"법령": {"기본정보": {"공포일자": "19900101"}}})
        out = asyncio.run(RegulationMonitorService().check_law_updates())
        assert out == [], "정상 조회 + 오래된 공포일 = 변경 없음(빈 리스트)"
