---
name: propai-ai-ml
description: "PropAI 부동산개발 플랫폼 AI/ML 서비스 개발 스킬. LangChain/LangGraph 에이전트, RAG 파이프라인, Qdrant 벡터 검색, XGBoost/scikit-learn ML 모델, MLflow 실험 관리, 프롬프트 엔지니어링 구현. AVM 자동감정평가, 법규 AI, 설계 AI, 금융/세금 분석, 시공/ESG AI 개발 요청 시 이 스킬을 사용. AI 분석, ML 모델 학습, 프롬프트 최적화, 벡터 검색, LLM 통합 요청에도 사용."
---

# PropAI AI/ML Development Skill

PropAI 부동산개발 플랫폼의 AI/ML 서비스 구현 가이드.

## 프로젝트 구조

```
apps/api/
├── app/services/ai_services/     # AI 서비스 메인
│   ├── prompts/                  # 14개 도메인별 프롬프트 파일
│   ├── avm_service.py            # 자동 감정평가
│   ├── legal_ai_service.py       # 법규 AI (RAG)
│   ├── design_ai_service.py      # 설계 AI (IFC/BIM)
│   ├── finance_ai_service.py     # 금융/세금 분석
│   └── construction_ai_service.py # 시공/ESG
├── agents/                       # LangGraph 에이전트 오케스트레이션
├── ml/                           # ML 모델 학습/예측
│   ├── models/                   # 모델 정의
│   ├── features/                 # 피처 엔지니어링
│   └── pipelines/                # 학습/예측 파이프라인
└── integrations/
    ├── openai_client.py          # OpenAI API 래퍼
    ├── anthropic_client.py       # Claude API 래퍼
    ├── qdrant_client.py          # 벡터DB 래퍼
    └── replicate_client.py       # 이미지 생성 API
```

## AI 서비스 패턴

### 로컬 계산 + AI 해석 분리

```python
class AVMService:
    async def evaluate(self, property_data: PropertyInput) -> AVMResult:
        # 1단계: 로컬 계산 (확정적, 비용 없음)
        local_result = self._calculate_local(property_data)
        
        # 2단계: AI 해석 (LLM, 비용 발생)
        ai_analysis = await self._get_ai_analysis(property_data, local_result)
        
        return AVMResult(
            estimated_value=local_result.value,
            confidence=local_result.confidence,
            ai_commentary=ai_analysis.commentary,
            risk_factors=ai_analysis.risks,
        )
    
    def _calculate_local(self, data: PropertyInput) -> LocalResult:
        """XGBoost 모델 + 통계 공식 기반 계산. LLM 호출 없음."""
        prediction = self.model.predict(self._extract_features(data))
        return LocalResult(value=prediction, confidence=self._calc_confidence(data))
    
    async def _get_ai_analysis(self, data, local_result) -> AIAnalysis:
        """LLM으로 해석/추천/리스크 분석. 폴백 있음."""
        try:
            return await self.llm_client.analyze(
                prompt=self._load_prompt("avm_analysis"),
                context={"data": data, "result": local_result}
            )
        except Exception:
            return self._fallback_analysis(local_result)
```

**핵심:** 수치 계산은 ML 모델/공식으로 처리. LLM은 해석·추천·분석 텍스트 생성에만 사용. LLM 실패 시 규칙 기반 폴백을 반드시 구현한다.

### RAG 파이프라인 (법규 AI)

```python
class LegalAIService:
    async def query(self, question: str) -> LegalAnswer:
        # 1. 벡터 검색
        docs = await self.qdrant.search(
            collection="legal_docs",
            query=question,
            limit=5,
            score_threshold=0.7,  # 관련성 임계값
        )
        
        # 2. 컨텍스트 필터링 (저품질 제거)
        relevant_docs = [d for d in docs if d.score >= 0.7]
        
        # 3. LLM 응답 생성
        answer = await self.llm_client.generate(
            prompt=self._load_prompt("legal_qa"),
            context=self._format_context(relevant_docs),
            question=question,
        )
        
        return LegalAnswer(
            answer=answer.text,
            sources=[d.metadata for d in relevant_docs],
            confidence=min(d.score for d in relevant_docs),
        )
```

## 프롬프트 관리

모든 프롬프트는 파일로 관리한다. 인라인 프롬프트 금지.

```
prompts/
├── avm_analysis.txt          # AVM 감정평가 해석
├── legal_qa.txt              # 법규 Q&A
├── design_review.txt         # 설계 검토
├── financial_analysis.txt    # 금융 분석
├── risk_assessment.txt       # 리스크 평가
└── ...                       # 14개 도메인별
```

프롬프트 파일 형식:
```
[System]
당신은 부동산 개발 전문 AI 분석가입니다.

[Context]
{context}

[Instructions]
주어진 데이터를 기반으로 다음을 분석하라:
1. ...
2. ...

[Output Format]
JSON 형식으로 응답:
{ "commentary": "...", "risks": [...], "recommendations": [...] }
```

## ML 모델 관리

### MLflow 실험 추적

```python
import mlflow

with mlflow.start_run(run_name="avm_xgboost_v3"):
    mlflow.log_params({"max_depth": 6, "n_estimators": 300})
    model.fit(X_train, y_train)
    mlflow.log_metrics({"rmse": rmse, "r2": r2_score})
    mlflow.sklearn.log_model(model, "avm_model")
```

### 피처 엔지니어링

부동산 도메인 피처:
- 위치: 좌표, 행정구역, 교통 접근성, 학군
- 물리: 면적, 층수, 건축연도, 구조
- 시장: 주변 거래가, 추세, 수급 지표
- 법규: 용도지역, 건폐율, 용적률 제한

## 에러 폴백 전략

| AI 서비스 | 폴백 방식 |
|----------|----------|
| AVM 감정평가 | 주변 실거래가 평균 ± 표준편차 |
| 법규 AI | "관련 법규를 확인해주세요" + 검색 키워드 제안 |
| 설계 AI | 기본 설계 템플릿 반환 |
| 금융 분석 | 단순 수지분석 공식 결과만 반환 |
| 이미지 생성 | 플레이스홀더 이미지 반환 |

AI 서비스 실패는 전체 요청 실패로 이어지면 안 된다. 항상 폴백으로 부분 기능을 제공한다.
