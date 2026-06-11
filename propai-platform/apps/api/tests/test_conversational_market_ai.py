"""ConversationalMarketAI 단위 테스트 (WP-12).

검증 계약:
1. LLM API 키 부재(get_llm ValueError) 시 템플릿 분석으로 폴백 + analysis_source="template"
2. LLM 사용 가능 시 LLM 분석 우선 + analysis_source="llm" (chart_data는 실데이터 계산값)
3. 실거래 통계가 없으면 LLM을 호출하지 않고 정직한 '데이터 없음' 템플릿 응답
4. LLM 응답이 JSON이 아니면 템플릿 폴백
5. 기존 analyze() 응답 키 계약 유지 (additive — analysis_source만 추가)
6. 템플릿 분석·월별 차트의 고정 수치 (정답값 고정)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import app.services.ai.llm_provider as llm_provider
from apps.api.app.services.market.conversational_market_ai import (
    ConversationalMarketAI,
)

# ── 고정 실거래 데이터 (MOLIT 조회 스텁) ──

FIXED_DATA = {
    "source": "국토교통부 실거래가 공개시스템",
    "records": [
        {"deal_date": "20260301", "price_10k": 80000, "area_sqm": 84.0},
        {"deal_date": "20260315", "price_10k": 90000, "area_sqm": 84.0},
        {"deal_date": "20260410", "price_10k": 85000, "area_sqm": 84.0},
    ],
    "total_count": 3,
    "period": "최근 6개월",
    "statistics": {
        "avg_price_10k": 85000,
        "min_price_10k": 80000,
        "max_price_10k": 90000,
        "median_price_10k": 85000,
        "count": 3,
    },
}

NO_DATA = {
    "source": "국토교통부 실거래가 공개시스템",
    "records": [],
    "total_count": 0,
    "period": "최근 6개월",
}

# 정답값 고정 — 템플릿 분석 산식 (avg 85000만 → 8.5억)
EXPECTED_TEMPLATE_SUMMARY = (
    "강남 지역 최근 6개월간 총 3건 거래. "
    "평균 거래가 8.5억원 (최저 80000만~최고 90000만)."
)

# 정답값 고정 — 월별 차트 (202603: [80000, 90000], 202604: [85000])
EXPECTED_CHART = [
    {"month": "2026.03", "avg_price_10k": 85000, "count": 2},
    {"month": "2026.04", "avg_price_10k": 85000, "count": 1},
]


def _stub_retrieve(data: dict):
    async def _retrieve(self, intent, params):
        return dict(data)

    return _retrieve


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    """ainvoke 호출을 기록하고 고정 응답을 반환하는 LLM 스텁."""

    def __init__(self, content: str):
        self._content = content
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return _FakeResponse(self._content)


class TestTemplateFallback:
    """키 부재 시 템플릿 폴백 계약."""

    async def test_키부재시_템플릿_폴백(self, monkeypatch):
        monkeypatch.setattr(
            ConversationalMarketAI, "_retrieve_data", _stub_retrieve(FIXED_DATA)
        )

        def _raise(*args, **kwargs):
            raise ValueError("anthropic API key not configured")

        monkeypatch.setattr(llm_provider, "get_llm", _raise)

        result = await ConversationalMarketAI().analyze("강남 아파트 실거래가")

        assert result["analysis_source"] == "template"
        assert result["analysis"]["summary"] == EXPECTED_TEMPLATE_SUMMARY
        assert result["analysis"]["chart_data"] == EXPECTED_CHART
        assert len(result["analysis"]["recommendations"]) == 2

    async def test_LLM_JSON파싱실패시_템플릿_폴백(self, monkeypatch):
        monkeypatch.setattr(
            ConversationalMarketAI, "_retrieve_data", _stub_retrieve(FIXED_DATA)
        )
        fake = _FakeLLM("이것은 JSON이 아닌 자유 텍스트 응답입니다.")
        monkeypatch.setattr(llm_provider, "get_llm", lambda *a, **k: fake)

        result = await ConversationalMarketAI().analyze("강남 아파트 실거래가")

        assert result["analysis_source"] == "template"
        assert result["analysis"]["summary"] == EXPECTED_TEMPLATE_SUMMARY


class TestLLMPreferred:
    """LLM 사용 가능 시 LLM 분석 우선 계약."""

    async def test_LLM_성공시_llm_분석_우선(self, monkeypatch):
        monkeypatch.setattr(
            ConversationalMarketAI, "_retrieve_data", _stub_retrieve(FIXED_DATA)
        )
        fake = _FakeLLM(
            '{"summary": "강남 평균 8.5억원 수준의 거래가 형성되어 있습니다.", '
            '"details": "총 3건 분석.", "recommendations": ["참고 A", "참고 B"]}'
        )
        monkeypatch.setattr(llm_provider, "get_llm", lambda *a, **k: fake)

        result = await ConversationalMarketAI().analyze("강남 아파트 실거래가")

        assert result["analysis_source"] == "llm"
        assert (
            result["analysis"]["summary"]
            == "강남 평균 8.5억원 수준의 거래가 형성되어 있습니다."
        )
        assert result["analysis"]["recommendations"] == ["참고 A", "참고 B"]
        # chart_data는 LLM이 아닌 실데이터에서 계산된다(수치 변조 방지)
        assert result["analysis"]["chart_data"] == EXPECTED_CHART

    async def test_LLM_코드펜스_JSON_허용(self, monkeypatch):
        monkeypatch.setattr(
            ConversationalMarketAI, "_retrieve_data", _stub_retrieve(FIXED_DATA)
        )
        fake = _FakeLLM(
            '```json\n{"summary": "펜스 요약", "details": "d", '
            '"recommendations": []}\n```'
        )
        monkeypatch.setattr(llm_provider, "get_llm", lambda *a, **k: fake)

        result = await ConversationalMarketAI().analyze("강남 아파트 실거래가")

        assert result["analysis_source"] == "llm"
        assert result["analysis"]["summary"] == "펜스 요약"

    async def test_프롬프트는_MOLIT_데이터_근거_한정(self, monkeypatch):
        monkeypatch.setattr(
            ConversationalMarketAI, "_retrieve_data", _stub_retrieve(FIXED_DATA)
        )
        fake = _FakeLLM('{"summary": "s", "details": "d", "recommendations": []}')
        monkeypatch.setattr(llm_provider, "get_llm", lambda *a, **k: fake)

        await ConversationalMarketAI().analyze("강남 아파트 실거래가")

        assert len(fake.calls) == 1
        sys_content = fake.calls[0][0].content
        usr_content = fake.calls[0][1].content
        assert "데이터에 없는 수치는 만들지 말 것" in sys_content
        assert "85000" in usr_content  # 실거래 통계가 근거로 동봉된다


class TestNoDataHonesty:
    """데이터 없음 시 정직 표기 + LLM 미호출 계약."""

    async def test_데이터없음시_LLM_미호출_정직_표기(self, monkeypatch):
        monkeypatch.setattr(
            ConversationalMarketAI, "_retrieve_data", _stub_retrieve(NO_DATA)
        )
        called = []

        def _track(*args, **kwargs):
            called.append(True)
            return _FakeLLM('{"summary": "호출되면 안 됨"}')

        monkeypatch.setattr(llm_provider, "get_llm", _track)

        result = await ConversationalMarketAI().analyze("강남 아파트 실거래가")

        assert called == []  # 근거 데이터 없음 → LLM 미호출
        assert result["analysis_source"] == "template"
        assert (
            result["analysis"]["summary"]
            == "강남 지역의 최근 6개월 거래 데이터를 찾을 수 없습니다."
        )
        assert result["analysis"]["chart_data"] is None


class TestResponseContract:
    """기존 analyze() 응답 키 계약 — additive 하위호환."""

    async def test_기존_응답_키_유지(self, monkeypatch):
        monkeypatch.setattr(
            ConversationalMarketAI, "_retrieve_data", _stub_retrieve(FIXED_DATA)
        )

        def _raise(*args, **kwargs):
            raise ValueError("no key")

        monkeypatch.setattr(llm_provider, "get_llm", _raise)

        result = await ConversationalMarketAI().analyze("강남 아파트 실거래가")

        # 기존 키 전부 유지 + analysis_source만 추가
        assert {
            "query", "intent", "parameters", "data", "analysis",
            "analysis_source", "timestamp", "tools_used",
        } <= set(result.keys())
        assert result["tools_used"] == ["실거래가_조회"]
        assert result["intent"] == {"tool": "실거래가_조회", "type": "transactions"}
        assert result["parameters"]["region_name"] == "강남"
        assert result["parameters"]["lawd_cd"] == "11680"


class TestTemplateFixedValues:
    """템플릿 분석·차트 정답값 고정 (동기 경로)."""

    def test_템플릿_분석_고정수치(self):
        ai = ConversationalMarketAI()
        analysis = ai._generate_analysis(
            "강남 아파트 실거래가",
            {"tool": "실거래가_조회", "type": "transactions"},
            FIXED_DATA,
            {"region_name": "강남", "lawd_cd": "11680", "months": 6},
        )
        assert analysis["summary"] == EXPECTED_TEMPLATE_SUMMARY
        assert analysis["recommendations"] == [
            "강남 평균 시세 기준 분양가 책정 시 8.5억원 수준 참고",
            "거래 건수 3건으로 보통 수준의 시장 활동",
        ]

    def test_월별_차트_고정수치(self):
        ai = ConversationalMarketAI()
        chart = ai._generate_monthly_chart(FIXED_DATA["records"])
        assert chart == EXPECTED_CHART
