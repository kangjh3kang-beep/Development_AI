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

from app.services.legal.gosi_search_service import SEARCH_ROOT_KEYS, TEXT_ROOT_KEYS
from app.services.legal.moleg_drf_envelope import (
    MolegDrfError,
    drf_failure_reason,
    raise_unless_expected,
)

#: 라이브에서 받은 **실제** 오류 본문(바이트 그대로).
LIVE_ERROR_PAYLOAD = {
    "result": "사용자 정보 검증에 실패하였습니다.",
    "msg": "OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 IP주소 및 도메인주소를 등록해 주세요.",
}
#: 정상 응답 — ★**결과가 0건인 정상 응답**이다. 이것이 오류로 판정되면 위양성이다.
LIVE_OK_EMPTY = {"AdmRulSearch": {"totalCnt": "0", "admrul": []}}
LIVE_OK_HIT = {"AdmRulSearch": {"totalCnt": "1", "admrul": [{"행정규칙명": "표준건축비 고시"}]}}
#: ★세 번째 계열(독립 리뷰 실측) — `result`/`msg` 가 **없고** 사유가 루트키 자리에 문자열로 온다.
LIVE_NO_MATCH_PAYLOAD = {"Law": "일치하는 법령이 없습니다.  법령명을 확인하여 주십시오."}


class TestEnvelopeDetection:
    def test_live_error_payload_is_detected(self):
        reason = drf_failure_reason(LIVE_ERROR_PAYLOAD, expect=SEARCH_ROOT_KEYS)
        assert reason is not None
        assert "사용자 정보 검증" in reason
        assert "IP주소" in reason, "사유를 표면까지 실어야 조사자가 원인을 안다"

    @pytest.mark.parametrize("ok", [LIVE_OK_EMPTY, LIVE_OK_HIT])
    def test_normal_responses_are_not_errors(self, ok):
        """★반대 모집단 — **0건인 정상 응답**을 오류로 보면 정상 조회를 막는다."""
        assert drf_failure_reason(ok, expect=SEARCH_ROOT_KEYS) is None

    def test_raise_helper_splits_the_two(self):
        with pytest.raises(MolegDrfError):
            raise_unless_expected(LIVE_ERROR_PAYLOAD, expect=SEARCH_ROOT_KEYS)
        raise_unless_expected(LIVE_OK_EMPTY, expect=SEARCH_ROOT_KEYS)  # 예외 없음
        raise_unless_expected(LIVE_OK_HIT, expect=SEARCH_ROOT_KEYS)

    def test_expected_root_key_wins_even_with_result_field(self):
        """기대 루트키가 있으면 `result` 가 있어도 정상이다(위양성 방지)."""
        assert drf_failure_reason({"AdmRulSearch": {}, "result": "ok"}, expect=SEARCH_ROOT_KEYS) is None

    def test_third_envelope_family_is_caught(self):
        """★독립 리뷰가 찾은 **세 번째 계열** — `result`/`msg` 가 **없다**.

        오류 형태를 열거하는 구현은 이것을 못 잡는다. 「기대 루트키가 없으면 실패」라야 잡힌다.
        """
        reason = drf_failure_reason(LIVE_NO_MATCH_PAYLOAD, expect=("법령",))
        assert reason is not None
        assert "일치하는 법령이 없습니다" in reason, "사유를 표면까지 실어야 한다"

    def test_non_dict_and_empty_payloads_are_failures_not_silence(self):
        """dict 가 아니거나 아무 키도 없으면 **실패**다 — 조용한 0건으로 흘리지 않는다."""
        for bad in ([], None, "문자열", 0):
            assert drf_failure_reason(bad, expect=SEARCH_ROOT_KEYS) is not None
        r = drf_failure_reason({}, expect=SEARCH_ROOT_KEYS)
        assert r is not None and "기대 루트키" in r

    def test_root_level_admrul_fallback_is_expected(self):
        """코드가 방어하는 **루트레벨 폴백**(`data["admrul"]`)도 정상으로 봐야 한다.

        첫 판의 손 목록에는 이것이 **빠져 있었다** — 정상 응답을 오류로 막을 뻔했다.
        """
        assert drf_failure_reason({"admrul": [{"행정규칙명": "x"}]}, expect=SEARCH_ROOT_KEYS) is None


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


class TestDeclaredKeysMatchWhatCodeParses:
    """★선언과 소비의 **정합** — 「선언의 존재」는 그 선언이 옳은지 말해 주지 않는다.

    첫 판의 `_OK_ROOT_KEYS` 는 주석에 *"코드가 이미 방어하던 목록에서 파생"* 이라고 적혀
    있었지만 실제로는 **손 목록**이었고, 독립 리뷰가 **양방향 불일치**를 실측했다:

      · **빠짐** — 코드가 방어하는 루트레벨 폴백 `data["admrul"]` 이 목록에 없었다
      · **잉여** — 어느 소비처도 주지 않는 키 7개가 들어 있었다
      · 그리고 원소를 지워도 **아무 테스트도 빨개지지 않았다**(변이 2종 생존)

    그래서 선언을 **파싱 코드에서 파생**시켜 대조한다. 파싱을 고치면 여기가 빨개진다.
    """

    @staticmethod
    def _parsed_root_keys(func_name: str) -> set[str]:
        """`gosi_search_service` 소스에서 그 함수가 **실제로 읽는** 루트키를 AST 로 뽑는다."""
        import ast
        import pathlib

        src = pathlib.Path("app/services/legal/gosi_search_service.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        target = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name
        )
        keys: set[str] = set()
        for node in ast.walk(target):
            # `data.get("X")` / `root.get("X")` 형태
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "get" and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.add(a.value)
            # `for rk in ("A","B",...)` 형태
            if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
                for e in node.iter.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        keys.add(e.value)
        return keys

    def test_search_declared_keys_are_all_actually_parsed(self):
        parsed = self._parsed_root_keys("search_admrule")
        assert parsed, "★검사기 사망 — 파싱 키를 하나도 못 뽑았다"
        missing = [k for k in SEARCH_ROOT_KEYS if k not in parsed]
        assert not missing, f"선언했는데 코드가 안 읽는 키(잉여): {missing}"

    def test_search_parsed_root_keys_are_all_declared(self):
        """★반대 방향 — 코드가 읽는데 선언에 없으면 **정상 응답을 오류로 막는다**."""
        parsed = self._parsed_root_keys("search_admrule")
        # 루트키 후보만 본다(하위 항목 키·필드명 제외).
        root_like = {k for k in parsed if k in {
            "AdmRulSearch", "admRulSearch", "LawSearch", "admrulSearch", "admrul", "law",
        }} - {"law"}  # `root.get("law")` 는 루트가 아니라 하위 항목
        extra = [k for k in root_like if k not in SEARCH_ROOT_KEYS]
        assert not extra, f"코드가 읽는데 선언에 없는 루트키(누락): {extra}"

    def test_text_declared_key_is_parsed(self):
        parsed = self._parsed_root_keys("fetch_admrule_text")
        assert "AdmRulService" in parsed, "★검사기 사망 — 본문 루트키를 못 뽑았다"
        assert TEXT_ROOT_KEYS == ("AdmRulService",)


class TestTextFetchSurfacesTheReason:
    """★독립 리뷰 ① — 배선해 놓고 **관측 계약이 안 바뀌면** 배선이 아니다.

    `fetch_admrule_text` 는 `MolegDrfError` 를 아래 `except Exception` 에 삼켜
    **종전과 바이트 동일한** `{"found": False, "text": ""}` 를 돌려줬다. 그래서 소비처가
    *"본문을 읽었는데 키워드가 없다"* 와 *"본문을 못 읽었다"* 를 **구별할 수 없었다.**
    """

    @staticmethod
    def _patch(monkeypatch, payload):
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

    def test_failure_carries_a_reason(self, monkeypatch):
        import asyncio

        from app.services.legal.gosi_search_service import GosiSearchService

        monkeypatch.setattr(GosiSearchService, "_key", staticmethod(lambda: "dummy"))
        self._patch(monkeypatch, LIVE_ERROR_PAYLOAD)
        out = asyncio.run(GosiSearchService().fetch_admrule_text("123"))
        assert out["found"] is False
        assert out.get("reason"), "★사유가 없으면 「본문 없음」과 구별 불가 — 로그는 화면에 안 닿는다"

    def test_no_match_envelope_also_carries_a_reason(self, monkeypatch):
        """★계열 ③ — 행정규칙 일련번호는 개정마다 바뀌어 **지금 바로 도달**한다."""
        import asyncio

        from app.services.legal.gosi_search_service import GosiSearchService

        monkeypatch.setattr(GosiSearchService, "_key", staticmethod(lambda: "dummy"))
        self._patch(monkeypatch, {"Law": "일치하는 행정규칙이 없습니다."})
        out = asyncio.run(GosiSearchService().fetch_admrule_text("999"))
        assert out["found"] is False
        assert "일치하는" in (out.get("reason") or "")

    def test_success_has_no_reason(self, monkeypatch):
        """★반대 모집단 — 성공하면 `reason` 이 **없어야** 한다(항상 사유를 다는 구현 탐지)."""
        import asyncio

        from app.services.legal.gosi_search_service import GosiSearchService

        monkeypatch.setattr(GosiSearchService, "_key", staticmethod(lambda: "dummy"))
        self._patch(monkeypatch, {"AdmRulService": {"조문내용": "본문 텍스트입니다"}})
        out = asyncio.run(GosiSearchService().fetch_admrule_text("123"))
        assert not out.get("reason")


class TestRegulationMonitorCatchesThirdFamily:
    """★계열 ③ 으로 **전건 실패**해도 「변경 없음」이던 것(독립 리뷰 ②)."""

    @staticmethod
    def _patch(monkeypatch, payload):
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

    def test_no_match_envelope_raises(self, monkeypatch):
        import asyncio

        from app.services.regulation_monitor.regulation_monitor import RegulationMonitorService

        self._patch(monkeypatch, {"Law": "일치하는 법령이 없습니다.  법령명을 확인하여 주십시오."})
        with pytest.raises(RuntimeError):
            asyncio.run(RegulationMonitorService().check_law_updates())
