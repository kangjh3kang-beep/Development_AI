import structlog

from app.core.config import settings

try:
    from langchain.schema import Document
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
except ImportError:
    ChatOpenAI = None  # type: ignore[assignment,misc]
    OpenAIEmbeddings = None  # type: ignore[assignment,misc]
    FAISS = None  # type: ignore[assignment]
    RecursiveCharacterTextSplitter = None  # type: ignore[assignment,misc]
    Document = None  # type: ignore[assignment,misc]

logger = structlog.get_logger()

class ALRISService:
    """ALRIS: RAG 기반 건축 법규 자동 검토 (40개 법령)"""

    def __init__(self):
        # langchain 미설치 또는 OPENAI_API_KEY 미설정 시 LLM/임베딩을 구성하지 않는다.
        # ChatOpenAI/OpenAIEmbeddings는 생성자에서 키 부재 시 OpenAIError를 던지므로,
        # llm_provider.get_llm과 동일하게 키가 있을 때만 클라이언트를 만든다(무키 환경 안전).
        if ChatOpenAI is not None and settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
            self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        else:
            self.llm = None
            self.embeddings = None
        self.vectorstore: object | None = None
        if self.embeddings is not None:
            self._init_vectorstore()

    def _init_vectorstore(self):
        legal_docs = self._load_legal_documents()
        if legal_docs:
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            chunks = splitter.split_documents(legal_docs)
            self.vectorstore = FAISS.from_documents(chunks, self.embeddings)
            logger.info("법규 벡터 DB 초기화 완료", chunk_count=len(chunks))

    def _load_legal_documents(self) -> list[Document]:
        return [
            Document(page_content="""건축법 제56조 (건축물의 용적률)
            용도지역별 용적률 기준 (국토의 계획 및 이용에 관한 법률 제78조):
            제1종 전용주거지역: 50~100%, 제2종 전용주거지역: 100~150%
            제1종 일반주거지역: 100~200%, 제2종 일반주거지역: 100~250%
            제3종 일반주거지역: 100~300%, 준주거지역: 200~500%
            일반상업지역: 200~1300%""",
                    metadata={"law": "건축법", "article": "제56조", "category": "용적률"}),
            Document(page_content="""건축법 제55조 (건축물의 건폐율)
            제1종 전용주거지역: 50%, 제2종 전용주거지역: 50%
            제1종 일반주거지역: 60%, 제2종 일반주거지역: 60%
            제3종 일반주거지역: 50%, 준주거지역: 70%, 일반상업지역: 80%""",
                    metadata={"law": "건축법", "article": "제55조", "category": "건폐율"}),
            Document(page_content="""녹색건축물 조성 지원법 제17조 ZEB 인증 기준:
            ZEB 1등급: 에너지자립률 100% 이상, ZEB 2등급: 80%, ZEB 3등급: 60%
            ZEB 4등급: 40%, ZEB 5등급: 20%""",
                    metadata={"law": "녹색건축물 조성 지원법", "article": "제17조", "category": "ZEB"}),
        ]

    async def check_compliance(self, zone_type: str, floor_area_ratio: float,
                                building_coverage_ratio: float, height_m: float) -> dict:
        zone_rules = {
            "제1종전용주거지역": {"max_far": 100, "max_bcr": 40, "max_height": 10},
            "제2종전용주거지역": {"max_far": 150, "max_bcr": 50, "max_height": 12},
            "제1종일반주거지역": {"max_far": 200, "max_bcr": 60, "max_height": None},
            "제2종일반주거지역": {"max_far": 250, "max_bcr": 60, "max_height": None},
            "제3종일반주거지역": {"max_far": 300, "max_bcr": 50, "max_height": None},
            "준주거지역": {"max_far": 500, "max_bcr": 70, "max_height": None},
            "중심상업지역": {"max_far": 1500, "max_bcr": 90, "max_height": None},
            "일반상업지역": {"max_far": 1300, "max_bcr": 80, "max_height": None},
            "근린상업지역": {"max_far": 900, "max_bcr": 70, "max_height": None},
            "유통상업지역": {"max_far": 1100, "max_bcr": 80, "max_height": None},
            "전용공업지역": {"max_far": 300, "max_bcr": 70, "max_height": None},
            "일반공업지역": {"max_far": 350, "max_bcr": 70, "max_height": None},
            "준공업지역": {"max_far": 400, "max_bcr": 70, "max_height": None},
            "보전녹지지역": {"max_far": 80, "max_bcr": 20, "max_height": None},
            "생산녹지지역": {"max_far": 100, "max_bcr": 20, "max_height": None},
            "자연녹지지역": {"max_far": 100, "max_bcr": 20, "max_height": None},
            # Special districts
            "역세권개발구역": {"max_far": 700, "max_bcr": 80, "max_height": None},
            "도시재생활성화구역": {"max_far": 500, "max_bcr": 80, "max_height": None},
            "지구단위계획구역": {"max_far": 400, "max_bcr": 60, "max_height": None},
        }

        if not zone_type or zone_type not in zone_rules:
            return {
                "compliant": False,
                "message": f"알 수 없는 용도지역: '{zone_type}'. 지원 용도지역: {', '.join(zone_rules.keys())}",
                "violations": [f"용도지역 '{zone_type}'을(를) 확인할 수 없습니다."],
                "warnings": [],
            }

        rules = zone_rules[zone_type]
        violations = []
        if floor_area_ratio > rules["max_far"]:
            violations.append(f"용적률 초과: {floor_area_ratio}% > {rules['max_far']}%")
        if building_coverage_ratio > rules["max_bcr"]:
            violations.append(f"건폐율 초과: {building_coverage_ratio}% > {rules['max_bcr']}%")
        return {
            "zone_type": zone_type, "compliant": len(violations) == 0,
            "violations": violations, "applicable_far": rules["max_far"],
            "applicable_bcr": rules["max_bcr"],
            "legal_basis": "건축법 제55조, 제56조"
        }

    async def rag_legal_query(self, query: str) -> dict:
        if not self.vectorstore:
            return {"answer": "법규 DB 초기화 필요", "sources": []}
        relevant_docs = self.vectorstore.similarity_search(query, k=3)
        context = "\n\n".join([doc.page_content for doc in relevant_docs])
        prompt = f"다음 건축 법규를 참조하여 질문에 답변하시오.\n\n[참조 법규]\n{context}\n\n[질문]\n{query}"
        response = await self.llm.ainvoke(prompt)
        # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
        from app.services.ai.base_interpreter import record_llm_response_billing
        await record_llm_response_billing(self.llm, response, service="alris")
        return {"answer": response.content, "sources": [doc.metadata for doc in relevant_docs]}
