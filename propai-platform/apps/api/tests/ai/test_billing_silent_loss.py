"""과금 실패가 **조용히** 사라지지 않는다.

## 왜 이 파일이 생겼나 (2026-08-21)

`_record_llm_billing` 은 본체 전체가 `try` 안에 있고 `except Exception: pass` 로 끝났다.
이 파일에 `logger` 가 **있는데도 쓰지 않았다.** 결과:

  · LLM 호출 비용은 **이미 발생**했는데 청구·계측이 실패하면 **아무 흔적이 없다**
  · 그래서 "손실이 있었나?"라는 질문에 **원리적으로 답할 수 없었다**

★인계 백로그는 `parcel_excel_service` 의 `except: pass` 2건을 범인으로 지목했지만
  **그 층이 아니다**(실행으로 확증): 싱크가 예외를 밖으로 내보내지 않으므로 그 바깥
  except 는 과금 실패를 **잡을 수조차 없다**. 그것만 고치는 것은 환자에게 닿지 않는 처방이다.
  진짜 지점은 싱크 하나이고, 거기로 호출처 30곳이 전부 흘러든다.

## 이 파일이 두 모집단을 가르는 이유

"실패하면 경고한다"만 잠그면 **모든 경로에서 경고**해도 통과한다(정상 무동작까지 시끄러워지는
것도 결함이다 — 로그가 노이즈가 되면 다음 사람이 끈다). 그래서 같은 실행에서
**①실패는 경고한다** 와 **②정당한 무동작은 조용하다** 를 함께 단언한다.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.ai import base_interpreter as bi


class _Resp:
    def __init__(self, usage): self.usage_metadata = usage


class _Llm:
    model = "claude-opus-5"


@pytest.mark.asyncio
async def test_과금_쓰기_실패는_경고로_드러난다():
    """★손실 지점 — 비용은 났는데 기록이 없다. 침묵하면 셀 수조차 없다."""
    with patch("app.core.request_context.get_current_user_id", return_value="u1"), \
         patch("app.core.billing.model_cost_usd", side_effect=RuntimeError("DB 폭발")), \
         patch.object(bi.logger, "warning") as warn:
        r = await bi._record_llm_billing("claude-opus-5", 100, 50, service="probe")

    assert r is None, "본기능 회귀 금지 — 예외는 여전히 밖으로 나가지 않는다"
    assert warn.call_count == 1, "과금 실패가 조용히 사라졌다"
    kw = warn.call_args.kwargs
    # 귀속에 필요한 정보가 실제로 실려야 로그가 쓸모 있다(빈 경고 방지).
    assert kw["service"] == "probe"
    assert kw["input_tokens"] == 100 and kw["output_tokens"] == 50
    assert "RuntimeError" in kw["err"]
    # ★문구도 잠근다 — 변이검증에서 이 문자열 변경이 **생존**했다. 문구가 무의미해지면
    #   로그를 읽는 사람이 사유를 못 가른다(래퍼 실패와 구분되지 않는다).
    msg = warn.call_args.args[0]
    assert "과금" in msg and "실패" in msg, f"싱크 경고 문구가 사유를 말하지 않는다: {msg!r}"
    assert "추출" not in msg, "래퍼(추출 실패) 문구와 구분되지 않는다"
    # ★개인식별 최소화 — uid 는 싣지 않는다.
    assert "uid" not in kw and "user_id" not in kw


@pytest.mark.asyncio
async def test_정당한_무동작은_조용하다():
    """★대조군 — 이것이 없으면 '전부 경고'해도 위 테스트가 통과한다.

    비로그인(uid 없음)·토큰 0 은 **실패가 아니라 설계된 무동작**이다. 여기서 경고하면
    익명 요청마다 로그가 쏟아져 진짜 손실 신호가 묻힌다.
    """
    with patch("app.core.request_context.get_current_user_id", return_value=None), \
         patch.object(bi.logger, "warning") as warn:
        await bi._record_llm_billing("claude-opus-5", 100, 50, service="probe")
    assert warn.call_count == 0, "비로그인 무동작에 경고가 붙었다(노이즈)"

    with patch("app.core.request_context.get_current_user_id", return_value="u1"), \
         patch.object(bi.logger, "warning") as warn2:
        await bi._record_llm_billing("claude-opus-5", 0, 0, service="probe")
    assert warn2.call_count == 0, "토큰 0(캐시 적중) 무동작에 경고가 붙었다(노이즈)"


@pytest.mark.asyncio
async def test_토큰_추출_실패는_다른_문구로_드러난다():
    """★싱크와 **다른 사유**다 — 위임 전에 끊긴 것이라 문구를 갈라야 원인 추적이 된다."""
    class _Bad:
        @property
        def usage_metadata(self): raise ValueError("형태 불일치")

    with patch.object(bi.logger, "warning") as warn:
        await bi.record_llm_response_billing(_Llm(), _Bad(), service="probe")
    assert warn.call_count == 1
    assert "추출" in warn.call_args.args[0], "싱크 문구와 구분되지 않는다"


def test_동기_판본도_과금_생략을_드러낸다():
    """실행 중 루프가 없으면 과금이 **생략**된다 — 회귀는 0 이어도 손실은 손실이다."""
    with patch.object(bi.logger, "warning") as warn:
        bi.record_llm_response_billing_sync(_Llm(), _Resp({"input_tokens": 1}), service="probe")
    assert warn.call_count == 1, "동기 호출처의 과금 누락이 조용히 사라졌다"
    # ★문구 잠금 — 변이검증 생존 건. 동기 경로임이 문구에서 드러나야 추적이 된다.
    msg = warn.call_args.args[0]
    assert "과금" in msg and "동기" in msg, f"동기 판본 경고가 경로를 말하지 않는다: {msg!r}"


@pytest.mark.asyncio
async def test_엑셀_LLM_은_공용_계측기를_통과한다():
    """★배선 락 — 손수 복제로 되돌아가면 싱크의 로깅이 다시 우회된다.

    소스 검사가 아니라 **실제 함수를 태워** 공용 헬퍼 호출을 관측한다
    (주석·문자열 변이로 뚫리지 않는다).
    """
    from app.services.land_intelligence import parcel_excel_service as pes

    class _StubLlm:
        model = "claude-opus-5"
        async def ainvoke(self, _msgs):
            return type("R", (), {
                "content": '{"header_row":0}',
                "usage_metadata": {"input_tokens": 7, "output_tokens": 3},
            })()

    pes._STRUCT_CACHE.clear()
    with patch("app.services.ai.llm_provider.get_llm", return_value=_StubLlm()), \
         patch("app.services.ai.base_interpreter.record_llm_response_billing") as billed:
        data, called = await pes._llm_analyze_structure(
            sheet_previews={"Sheet1": [["소재지", "지번"]]},
            current_sheet="Sheet1",
            headers=["소재지", "지번"],
            sample_rows=[{"소재지": "오산시 내삼미동", "지번": "741"}],
        )

    assert called is True, "LLM 을 태우지 못했다 — 이 단언이 없으면 아래가 공허해진다"
    assert billed.await_count == 1, "공용 계측기를 우회했다(손수 복제 회귀)"
    assert billed.await_args.kwargs["service"] == "parcel_excel_structure_detect"


@pytest.mark.asyncio
async def test_엑셀_행재질의도_공용_계측기를_통과한다():
    """★형제 미러 — 첫 호출부만 잠갔더니 **두 번째가 변이에서 생존**했다.

    `_llm_analyze_structure` 와 `_llm_reverify_row` 는 각각 LLM 을 태우고 각각 과금한다.
    한쪽만 잠그면 다른 쪽이 손수 복제로 되돌아가도 초록이다(고친 자리의 형제를 반드시 쓸어라).
    """
    from app.services.land_intelligence import parcel_excel_service as pes

    class _StubLlm:
        model = "claude-opus-5"
        async def ainvoke(self, _msgs):
            return type("R", (), {
                "content": '{"jibun":"741"}',
                "usage_metadata": {"input_tokens": 5, "output_tokens": 2},
            })()

    with patch("app.services.ai.llm_provider.get_llm", return_value=_StubLlm()), \
         patch("app.services.ai.base_interpreter.record_llm_response_billing") as billed:
        _vals, called = await pes._llm_reverify_row(
            raw_cells={"소재지": "오산시 내삼미동 741"}, issues=["jibun 없음"],
        )

    assert called is True, "LLM 을 태우지 못했다 — 이 단언이 없으면 아래가 공허해진다"
    assert billed.await_count == 1, "공용 계측기를 우회했다(손수 복제 회귀)"
    assert billed.await_args.kwargs["service"] == "parcel_excel_row_reverify"
