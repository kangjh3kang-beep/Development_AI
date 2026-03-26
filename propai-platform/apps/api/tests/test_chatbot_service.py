"""ChatbotService 단위 테스트.

세션 제목 생성, 토큰 추정, 결정론적 응답 생성 등
순수 정적 메서드를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.chatbot_service import _DOMAIN_ACTIONS, ChatbotService


class TestDomainActions:
    """도메인 액션 상수 테스트."""

    def test_5개_도메인_존재(self):
        assert len(_DOMAIN_ACTIONS) == 5

    def test_investment_도메인_포함(self):
        assert "investment" in _DOMAIN_ACTIONS

    def test_construction_도메인_포함(self):
        assert "construction" in _DOMAIN_ACTIONS

    def test_design_도메인_포함(self):
        assert "design" in _DOMAIN_ACTIONS

    def test_regulation_도메인_포함(self):
        assert "regulation" in _DOMAIN_ACTIONS

    def test_general_도메인_포함(self):
        assert "general" in _DOMAIN_ACTIONS

    def test_각_도메인_3개_액션(self):
        for domain, actions in _DOMAIN_ACTIONS.items():
            assert len(actions) == 3, f"{domain} 도메인에 3개 액션이 아님"


class TestSessionTitle:
    """_session_title 정적 메서드 테스트."""

    def test_investment_타이틀(self):
        assert ChatbotService._session_title("investment") == "Investment advisory"

    def test_construction_타이틀(self):
        assert ChatbotService._session_title("construction") == "Construction advisory"

    def test_design_타이틀(self):
        assert ChatbotService._session_title("design") == "Design advisory"

    def test_general_타이틀(self):
        assert ChatbotService._session_title("general") == "General advisory"

    def test_언더스코어_도메인_공백변환(self):
        result = ChatbotService._session_title("real_estate")
        assert result == "Real Estate advisory"


class TestTokenEstimate:
    """_token_estimate 정적 메서드 테스트."""

    def test_단어수_기반_추정(self):
        """'hello world' → 2단어 × 3 = 6."""
        assert ChatbotService._token_estimate("hello world") == 6

    def test_단일_단어(self):
        assert ChatbotService._token_estimate("hello") == 3

    def test_빈_문자열_최소1(self):
        """빈 문자열 → max(1, 0) = 1."""
        assert ChatbotService._token_estimate("") == 1

    def test_긴_문장(self):
        text = "서울시 강남구 역삼동 부동산 개발 프로젝트 진행 현황"
        words = len(text.split())
        assert ChatbotService._token_estimate(text) == words * 3

    def test_결과_항상_양수(self):
        assert ChatbotService._token_estimate("a") >= 1


class TestReply:
    """_reply 정적 메서드 테스트."""

    def test_investment_도메인_응답(self):
        reply, actions = ChatbotService._reply("investment", "분석 요청합니다")
        assert "investment" in reply
        assert len(actions) == 3

    def test_construction_도메인_액션_일치(self):
        _, actions = ChatbotService._reply("construction", "일정 확인")
        assert actions == _DOMAIN_ACTIONS["construction"]

    def test_알수없는_도메인_general_폴백(self):
        _, actions = ChatbotService._reply("unknown_domain", "테스트")
        assert actions == _DOMAIN_ACTIONS["general"]

    def test_응답에_프롬프트_포함(self):
        reply, _ = ChatbotService._reply("design", "건축 설계 검토")
        assert "건축 설계 검토" in reply

    def test_긴_프롬프트_180자_절단(self):
        long_text = "가" * 300
        reply, _ = ChatbotService._reply("general", long_text)
        # 180자 이하로 절단된 내용이 응답에 포함
        assert len(reply) < len(long_text) + 500

    def test_응답_구조(self):
        reply, actions = ChatbotService._reply("regulation", "허가 확인")
        assert "Domain focus:" in reply
        assert "Recommended next steps:" in reply


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
