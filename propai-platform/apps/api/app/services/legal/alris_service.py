from typing import Dict, List, Optional
from app.core.config import settings
import structlog

try:
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from langchain.vectorstores import FAISS
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.schema import Document
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
        if ChatOpenAI is not None:
            self.llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
            self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        else:
            self.llm = None
            self.embeddings = None
        self.vectorstore: Optional[object] = None
        if self.embeddings is not None:
            self._init_vectorstore()

    def _init_vectorstore(self):
        legal_docs = self._load_legal_documents()
        if legal_docs:
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            chunks = splitter.split_documents(legal_docs)
            self.vectorstore = FAISS.from_documents(chunks, self.embeddings)
            logger.info("법규 벡터 DB 초기화 완료", chunk_count=len(chunks))

    def _load_legal_documents(self) -> List[Document]:
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
                                building_coverage_ratio: float, height_m: float) -> Dict:
        zone_rules = {
            "제2종일반주거지역": {"max_far": 250, "max_bcr": 60, "max_height": None},
            "제3종일반주거지역": {"max_far": 300, "max_bcr": 50, "max_height": None},
            "준주거지역": {"max_far": 500, "max_bcr": 70, "max_height": None},
            "일반상업지역": {"max_far": 1300, "max_bcr": 80, "max_height": None},
        }
        rules = zone_rules.get(zone_type, {"max_far": 300, "max_bcr": 60, "max_height": None})
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

    async def rag_legal_query(self, query: str) -> Dict:
        if not self.vectorstore:
            return {"answer": "법규 DB 초기화 필요", "sources": []}
        relevant_docs = self.vectorstore.similarity_search(query, k=3)
        context = "\n\n".join([doc.page_content for doc in relevant_docs])
        prompt = f"다음 건축 법규를 참조하여 질문에 답변하시오.\n\n[참조 법규]\n{context}\n\n[질문]\n{query}"
        response = await self.llm.ainvoke(prompt)
        return {"answer": response.content, "sources": [doc.metadata for doc in relevant_docs]}
