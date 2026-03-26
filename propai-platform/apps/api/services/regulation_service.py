"""법규 RAG 검토 서비스.

Qdrant 벡터 DB + LLM 기반 법규 적합성 검토.
목표: Top-5 Recall ≥ 80%.

흐름:
1. 프로젝트 정보 기반 쿼리 벡터 생성
2. Qdrant에서 관련 법령 문서 검색 (Top-K)
3. LLM(Claude/GPT)으로 적합성 분석
4. 위반 사항, 권고 사항, 신뢰도 반환

Qdrant 미연결 시 BUILTIN_REGULATION_DB를 폴백으로 사용한다.
"""

from typing import Any
from uuid import UUID

import structlog
from packages.schemas.models import RegulationCheckResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.regulation import Regulation

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────
# 내장 법규 DB — Qdrant 미연결 시 폴백
# ──────────────────────────────────────────────
BUILTIN_REGULATION_DB = {
    "제1종일반주거지역": {
        "max_bcr": 60,  # 건폐율 60%
        "max_far": 200,  # 용적률 200%
        "max_height_m": None,  # 높이 제한 없음 (일조권 사선 적용)
        "allowed_uses": ["단독주택", "공동주택", "제1종근린생활시설", "교육연구시설"],
        "prohibited_uses": ["공장", "위락시설", "숙박시설", "공동주택(아파트 제외)"],
        "description": "주거의 편안한 환경을 보호하기 위한 지역",
        "legal_basis": "국토의 계획 및 이용에 관한 법률 시행령 제71조",
    },
    "제2종일반주거지역": {
        "max_bcr": 60,
        "max_far": 250,
        "max_height_m": None,
        "allowed_uses": ["단독주택", "공동주택", "제1종근린생활시설", "제2종근린생활시설", "교육연구시설"],
        "prohibited_uses": ["공장", "위락시설"],
        "description": "주거 기능을 중심으로 일부 상업 허용",
        "legal_basis": "국토계획법 시행령 제71조",
    },
    "제3종일반주거지역": {
        "max_bcr": 50,
        "max_far": 300,
        "max_height_m": None,
        "allowed_uses": ["단독주택", "공동주택", "제1종근린생활시설", "제2종근린생활시설", "업무시설"],
        "prohibited_uses": ["공장", "위락시설"],
        "description": "주거 기능과 준주거 기능을 혼합",
        "legal_basis": "국토계획법 시행령 제71조",
    },
    "일반상업지역": {
        "max_bcr": 80,
        "max_far": 1300,
        "max_height_m": None,
        "allowed_uses": ["업무시설", "판매시설", "숙박시설", "공동주택", "근린생활시설", "문화집회시설"],
        "prohibited_uses": ["공장(인쇄 제외)", "위험물 저장"],
        "description": "일반적인 상업 및 업무 기능을 담당하는 지역",
        "legal_basis": "국토계획법 시행령 제71조",
    },
    "근린상업지역": {
        "max_bcr": 70,
        "max_far": 900,
        "max_height_m": None,
        "allowed_uses": ["근린생활시설", "판매시설", "업무시설", "공동주택"],
        "prohibited_uses": ["공장", "위험물 저장"],
        "description": "근린 지역의 일용품 및 서비스 공급을 위한 지역",
        "legal_basis": "국토계획법 시행령 제71조",
    },
    "준공업지역": {
        "max_bcr": 70,
        "max_far": 400,
        "max_height_m": None,
        "allowed_uses": ["공장", "창고", "업무시설", "근린생활시설", "공동주택"],
        "prohibited_uses": ["위락시설", "숙박시설"],
        "description": "경공업 및 기타 산업을 수용하되 주거/상업 혼합 가능",
        "legal_basis": "국토계획법 시행령 제71조",
    },
    "준주거지역": {
        "max_bcr": 70,
        "max_far": 500,
        "max_height_m": None,
        "allowed_uses": ["공동주택", "근린생활시설", "업무시설", "판매시설", "숙박시설"],
        "prohibited_uses": ["공장", "위험물 저장"],
        "description": "주거 기능을 위주로 이를 지원하는 일부 상업/업무 허용",
        "legal_basis": "국토계획법 시행령 제71조",
    },
}


class RegulationService:
    """법규 RAG 검토 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def _embed_query(self, text: str) -> list[float]:
        """쿼리 텍스트를 임베딩 벡터로 변환한다."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return list(response.data[0].embedding)

    @staticmethod
    def _fallback_search(regulation_type: str, project_info: dict) -> list[dict]:
        """Qdrant 미연결 시 내장 법규 DB에서 검색한다."""
        results = []
        zoning = project_info.get("zoning_type", "") or project_info.get("address", "")

        for zone_name, data in BUILTIN_REGULATION_DB.items():
            if zone_name in zoning or zoning in zone_name:
                results.append({
                    "id": f"builtin_{zone_name}",
                    "score": 0.95,
                    "payload": {
                        "text": (
                            f"{zone_name}: 건폐율 {data['max_bcr']}%, "
                            f"용적률 {data['max_far']}%. {data['description']}. "
                            f"허용: {', '.join(data['allowed_uses'][:3])}. "
                            f"근거: {data['legal_basis']}"
                        ),
                        "zone_name": zone_name,
                        **data,
                    },
                })

        # 매칭 없으면 전체 반환
        if not results:
            for zone_name, data in BUILTIN_REGULATION_DB.items():
                results.append({
                    "id": f"builtin_{zone_name}",
                    "score": 0.5,
                    "payload": {
                        "text": f"{zone_name}: 건폐율 {data['max_bcr']}%, 용적률 {data['max_far']}%",
                        "zone_name": zone_name,
                        **data,
                    },
                })
        return results

    async def _search_regulations(
        self,
        query_vector: list[float],
        top_k: int = 10,
        *,
        regulation_type: str = "",
        project_info: dict | None = None,
    ) -> list[dict]:
        """Qdrant에서 관련 법령을 검색한다. 실패 시 내장 DB 폴백."""
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import SearchParams

        client = QdrantClient(
            host=self.settings.qdrant_host,
            port=self.settings.qdrant_port,
        )

        try:
            results = client.search(
                collection_name="regulations",
                query_vector=query_vector,
                limit=top_k,
                search_params=SearchParams(hnsw_ef=128, exact=False),
            )
            return [
                {
                    "id": str(hit.id),
                    "score": hit.score,
                    "payload": hit.payload or {},
                }
                for hit in results
            ]
        except Exception:
            logger.warning("Qdrant 검색 실패 — 내장 법규 DB 폴백")
            return self._fallback_search(regulation_type, project_info or {})

    async def _analyze_compliance(
        self,
        regulation_type: str,
        project_info: dict,
        retrieved_docs: list[dict],
    ) -> dict:
        """LLM으로 법규 적합성을 분석한다."""
        try:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model="claude-sonnet-4-5-20250929",
                api_key=self.settings.anthropic_api_key,
                temperature=0,
            )

            doc_texts = "\n\n".join(
                f"[문서 {i+1}] (유사도: {d['score']:.3f})\n{d['payload'].get('text', '내용 없음')}"
                for i, d in enumerate(retrieved_docs[:5])
            )

            prompt = f"""당신은 한국 부동산 법규 전문가입니다. 아래 프로젝트 정보와 관련 법령을 검토하여
법규 적합 여부를 판정하세요.

## 검토 유형: {regulation_type}

## 프로젝트 정보
{project_info}

## 관련 법령 문서
{doc_texts}

## 응답 형식 (JSON):
{{
  "is_compliant": true/false,
  "confidence": 0.0~1.0,
  "violations": [{{"법령": "...", "조항": "...", "내용": "...", "심각도": "HIGH/MEDIUM/LOW"}}],
  "recommendations": ["..."],
  "summary": "요약 설명"
}}"""

            response = await llm.ainvoke(prompt)
            import json
            # JSON 블록 추출
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            result: dict[str, Any] = json.loads(content.strip())
            return result
        except Exception as e:
            logger.error("LLM 분석 실패", error=str(e))
            return {
                "is_compliant": True,
                "confidence": 0.3,
                "violations": [],
                "recommendations": ["자동 분석 실패 — 수동 검토 필요"],
                "summary": "자동 분석을 수행할 수 없습니다.",
            }

    async def check_regulation(
        self,
        project_id: UUID,
        tenant_id: UUID,
        regulation_type: str,
        project_info: dict,
    ) -> RegulationCheckResponse:
        """법규 적합성을 검토한다."""
        logger.info("법규 검토 시작", project_id=str(project_id), type=regulation_type)

        # 1. 쿼리 임베딩
        query_text = f"{regulation_type} {project_info.get('address', '')} {project_info.get('description', '')}"
        query_vector = await self._embed_query(query_text)

        # 2. 관련 법령 검색 (Qdrant 실패 시 내장 DB 폴백)
        retrieved_docs = await self._search_regulations(
            query_vector, regulation_type=regulation_type, project_info=project_info
        )

        # 3. LLM 분석
        analysis = await self._analyze_compliance(regulation_type, project_info, retrieved_docs)

        # 4. DB 저장
        regulation = Regulation(
            tenant_id=tenant_id,
            project_id=project_id,
            regulation_type=regulation_type,
            is_compliant=analysis.get("is_compliant", True),
            confidence_score=analysis.get("confidence", 0.5),
            violations=analysis.get("violations", []),
            recommendations=analysis.get("recommendations", []),
            source_documents=[d["id"] for d in retrieved_docs[:5]],
            summary=analysis.get("summary"),
        )
        self.db.add(regulation)
        await self.db.commit()
        await self.db.refresh(regulation)

        logger.info("법규 검토 완료", regulation_id=str(regulation.id))

        return RegulationCheckResponse(
            id=regulation.id,
            project_id=regulation.project_id,
            regulation_type=regulation.regulation_type,
            is_compliant=regulation.is_compliant,
            violations=regulation.violations or [],
            recommendations=regulation.recommendations or [],
            confidence_score=regulation.confidence_score,
            source_documents=[d["id"] for d in retrieved_docs[:5]],
            created_at=regulation.created_at,
        )
