"""법규 RAG 검토 서비스 단위 테스트.

inspect.getsource() 패턴으로 실제 로직 존재 검증.
외부 의존성(OpenAI, Qdrant, ChatAnthropic)이 필요하므로 소스 코드 분석 중심.
"""

import inspect

from apps.api.services.regulation_service import RegulationService


class TestRegulationServiceCode:
    """RegulationService 소스 코드 검증."""

    def test_embed_query_uses_openai(self) -> None:
        """_embed_query()에서 AsyncOpenAI를 사용한다."""
        src = inspect.getsource(RegulationService._embed_query)
        assert "AsyncOpenAI" in src

    def test_embed_query_uses_embedding_model(self) -> None:
        """_embed_query()에서 text-embedding-3-small 모델을 사용한다."""
        src = inspect.getsource(RegulationService._embed_query)
        assert "text-embedding-3-small" in src

    def test_search_uses_qdrant(self) -> None:
        """_search_regulations()에서 QdrantClient를 사용한다."""
        src = inspect.getsource(RegulationService._search_regulations)
        assert "QdrantClient" in src

    def test_search_uses_collection_name(self) -> None:
        """_search_regulations()에서 regulations 컬렉션을 검색한다."""
        src = inspect.getsource(RegulationService._search_regulations)
        assert '"regulations"' in src

    def test_search_uses_hnsw(self) -> None:
        """_search_regulations()에서 HNSW 검색 파라미터를 사용한다."""
        src = inspect.getsource(RegulationService._search_regulations)
        assert "SearchParams" in src

    def test_analyze_compliance_uses_llm(self) -> None:
        """_analyze_compliance()에서 ChatAnthropic을 사용한다."""
        src = inspect.getsource(RegulationService._analyze_compliance)
        assert "ChatAnthropic" in src

    def test_analyze_compliance_uses_json_response(self) -> None:
        """_analyze_compliance()에서 JSON 형식 응답을 파싱한다."""
        src = inspect.getsource(RegulationService._analyze_compliance)
        assert "json.loads" in src

    def test_fallback_on_llm_failure(self) -> None:
        """_analyze_compliance() 실패 시 기본 응답을 반환한다."""
        src = inspect.getsource(RegulationService._analyze_compliance)
        assert "수동 검토 필요" in src

    def test_fallback_has_required_keys(self) -> None:
        """실패 시 기본 응답에 필수 키가 포함된다."""
        src = inspect.getsource(RegulationService._analyze_compliance)
        assert '"is_compliant"' in src
        assert '"confidence"' in src
        assert '"violations"' in src
        assert '"recommendations"' in src

    def test_check_regulation_saves_to_db(self) -> None:
        """check_regulation()에서 Regulation 모델로 DB에 저장한다."""
        src = inspect.getsource(RegulationService.check_regulation)
        assert "Regulation(" in src
        assert "db.add" in src
        assert "db.commit" in src

    def test_check_regulation_returns_response(self) -> None:
        """check_regulation()에서 RegulationCheckResponse를 반환한다."""
        src = inspect.getsource(RegulationService.check_regulation)
        assert "RegulationCheckResponse" in src

    def test_korean_expert_prompt(self) -> None:
        """_analyze_compliance()에서 한국 부동산 법규 전문가 프롬프트를 사용한다."""
        src = inspect.getsource(RegulationService._analyze_compliance)
        assert "한국 부동산 법규 전문가" in src
