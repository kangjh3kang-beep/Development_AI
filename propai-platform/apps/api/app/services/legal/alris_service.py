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
    """ALRIS: RAG 기반 건축 법규 자동 검토 프로토타입.

    현재 시드 코퍼스는 건축·녹색건축 법령 스니펫 3종(건폐율·용적률·ZEB)뿐이다.
    (과거 docstring의 '40개 법령'은 실제 보유량과 어긋난 과대 표기라 실수로 정정.)
    용도지역 법정 상한(check_compliance)은 자체 표가 아니라 정본(legal_zone_limits SSOT)에 위임한다.
    """

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
            # 용도지역별 용적률의 실제 근거 조문은 국토계획법 제78조다(건축법 제56조는 이 조항에
            # 위임). 과거 이 스니펫은 건축법 제56조를 1차 근거로 오표기했다 → 정본 조문으로 교정.
            Document(page_content="""국토의 계획 및 이용에 관한 법률 제78조 (용도지역의 용적률)
            — 건축법 제56조가 위임하는 용도지역별 용적률 상한:
            제1종 전용주거지역: 50~100%, 제2종 전용주거지역: 100~150%
            제1종 일반주거지역: 100~200%, 제2종 일반주거지역: 100~250%
            제3종 일반주거지역: 100~300%, 준주거지역: 200~500%
            일반상업지역: 200~1300%""",
                    metadata={"law": "국토의 계획 및 이용에 관한 법률", "article": "제78조",
                              "delegated_by": "건축법 제56조", "category": "용적률"}),
            # 건폐율의 실제 근거 조문은 국토계획법 제77조(건축법 제55조가 위임) — 오표기 교정.
            Document(page_content="""국토의 계획 및 이용에 관한 법률 제77조 (용도지역의 건폐율)
            — 건축법 제55조가 위임하는 용도지역별 건폐율 상한:
            제1종 전용주거지역: 50%, 제2종 전용주거지역: 50%
            제1종 일반주거지역: 60%, 제2종 일반주거지역: 60%
            제3종 일반주거지역: 50%, 준주거지역: 70%, 일반상업지역: 80%""",
                    metadata={"law": "국토의 계획 및 이용에 관한 법률", "article": "제77조",
                              "delegated_by": "건축법 제55조", "category": "건폐율"}),
            Document(page_content="""녹색건축물 조성 지원법 제17조 ZEB 인증 기준:
            ZEB 1등급: 에너지자립률 100% 이상, ZEB 2등급: 80%, ZEB 3등급: 60%
            ZEB 4등급: 40%, ZEB 5등급: 20%""",
                    metadata={"law": "녹색건축물 조성 지원법", "article": "제17조", "category": "ZEB"}),
        ]

    async def check_compliance(self, zone_type: str, floor_area_ratio: float,
                                building_coverage_ratio: float, height_m: float) -> dict:
        # 용도지역 법정 상한은 자체 표가 아니라 정본(legal_zone_limits SSOT = 국토계획법 시행령
        # §84/§85 재노출)에 위임한다. 과거 자체 zone표는 제1종전용주거 건폐율 40%(법정 50%) 등
        # 오값 부비트랩이었다 — 소비 0이어도 부활 시 즉시 오염되므로 정본으로 일원화한다.
        from app.services.zoning.auto_zoning_service import ZONE_LIMITS as _SSOT_ZONES
        from app.services.zoning.legal_zone_limits import legal_limits_for

        legal = legal_limits_for(zone_type) if zone_type else None
        if legal is None:
            return {
                "compliant": False,
                "message": f"알 수 없는 용도지역: '{zone_type}'. 지원 용도지역: {', '.join(_SSOT_ZONES.keys())}",
                "violations": [f"용도지역 '{zone_type}'을(를) 확인할 수 없습니다."],
                "warnings": [],
            }

        max_far = legal.get("max_far_pct")
        max_bcr = legal.get("max_bcr_pct")
        violations = []
        if max_far is not None and floor_area_ratio > max_far:
            violations.append(f"용적률 초과: {floor_area_ratio}% > {max_far}%")
        if max_bcr is not None and building_coverage_ratio > max_bcr:
            violations.append(f"건폐율 초과: {building_coverage_ratio}% > {max_bcr}%")
        return {
            "zone_type": legal.get("zone_type", zone_type),
            "compliant": len(violations) == 0,
            "violations": violations,
            "applicable_far": max_far,
            "applicable_bcr": max_bcr,
            # 건폐율 근거=국토계획법 제77조, 용적률 근거=제78조(건축법 §55/§56은 이 조항에 위임).
            "legal_basis": "국토의 계획 및 이용에 관한 법률 제77조(건폐율)·제78조(용적률)",
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
