---
name: propai-orchestrator
description: "PropAI 부동산개발 플랫폼의 에이전트 팀을 조율하는 오케스트레이터. 백엔드 API 구현, 프론트엔드 페이지 구현, AI/ML 서비스 개발, QA 검증 등 개발 작업을 전문 에이전트 팀이 협업하여 수행. '개발 시작', '구현해줘', '빌드해줘', '모듈 구현', 'STEP 구현' 요청 시 이 스킬을 사용. 후속 작업: 결과 수정, 부분 재실행, 업데이트, 보완, 다시 실행, 이전 결과 개선 요청 시에도 반드시 이 스킬을 사용."
---

# PropAI Development Orchestrator

PropAI 부동산개발 전주기 AI 자동화 플랫폼의 에이전트 팀을 조율하여 개발 작업을 수행하는 통합 스킬.

## 실행 모드: 에이전트 팀

## 에이전트 구성

| 팀원 | 에이전트 파일 | 역할 | 스킬 | 주요 출력 |
|------|-------------|------|------|----------|
| backend-dev | `backend-dev` | 백엔드 API/서비스 구현 | propai-backend | API 라우트, 서비스, 스키마 |
| frontend-dev | `frontend-dev` | 프론트엔드 UI/UX 구현 | propai-frontend | 페이지, 컴포넌트, 훅 |
| ai-ml-dev | `ai-ml-dev` | AI/ML 서비스 개발 | propai-ai-ml | AI 서비스, 프롬프트, ML 모델 |
| qa-validator | `qa-validator` | 품질 검증 | propai-qa | 검증 보고서 |

## 워크플로우

### Phase 0: 컨텍스트 확인

기존 산출물 존재 여부를 확인하여 실행 모드를 결정한다:

1. `_workspace/` 디렉토리 존재 여부 확인
2. 실행 모드 결정:
   - **`_workspace/` 미존재** → 초기 실행. Phase 1로 진행
   - **`_workspace/` 존재 + 사용자가 부분 수정 요청** → 부분 재실행. 해당 에이전트만 재호출하고, 기존 산출물 중 수정 대상만 덮어쓴다
   - **`_workspace/` 존재 + 새 입력 제공** → 새 실행. 기존 `_workspace/`를 `_workspace_{YYYYMMDD_HHMMSS}/`로 이동한 뒤 Phase 1 진행
3. 부분 재실행 시: 이전 산출물 경로를 에이전트 프롬프트에 포함

### Phase 1: 준비

1. 사용자 요청 분석 — 구현 대상 모듈/기능/STEP 파악
2. 프로젝트 현황 확인:
   - `build-plan-overview.md`에서 STEP별 진행 상황 확인
   - 기존 코드베이스에서 관련 파일 탐색
   - `packages/types/api.ts`에서 공유 타입 확인
3. 작업 분배 계획 수립:
   - 백엔드 작업: API 엔드포인트, 서비스 로직, DB 모델
   - 프론트엔드 작업: 페이지, 컴포넌트, API 연동
   - AI/ML 작업: AI 서비스, 프롬프트, ML 파이프라인
   - QA 작업: 각 모듈 완성 시점의 경계면 검증
4. `_workspace/` 생성, 입력 데이터를 `_workspace/00_input/`에 저장

### Phase 2: 팀 구성

1. 팀 생성:
   ```
   TeamCreate(
     team_name: "propai-dev-team",
     members: [
       { name: "backend-dev", agent_type: "backend-dev", model: "opus",
         prompt: "PropAI 백엔드 개발자. {구현 대상 상세}. propai-backend 스킬을 참조하여 API 라우터, 서비스, 스키마를 구현하라. 산출물은 _workspace/에 저장." },
       { name: "frontend-dev", agent_type: "frontend-dev", model: "opus",
         prompt: "PropAI 프론트엔드 개발자. {구현 대상 상세}. propai-frontend 스킬을 참조하여 페이지, 컴포넌트, 훅을 구현하라. 산출물은 _workspace/에 저장." },
       { name: "ai-ml-dev", agent_type: "ai-ml-dev", model: "opus",
         prompt: "PropAI AI/ML 개발자. {구현 대상 상세}. propai-ai-ml 스킬을 참조하여 AI 서비스, 프롬프트, ML 파이프라인을 구현하라. 산출물은 _workspace/에 저장." },
       { name: "qa-validator", agent_type: "qa-validator", model: "opus",
         prompt: "PropAI QA 검증자. 다른 팀원들의 산출물이 완성되면 경계면 교차 비교 검증을 수행하라. propai-qa 스킬을 참조. 검증 보고서를 _workspace/에 저장." }
     ]
   )
   ```

2. 작업 등록:
   ```
   TaskCreate(tasks: [
     // 백엔드 작업
     { title: "API 라우터 구현", description: "{상세}", assignee: "backend-dev" },
     { title: "서비스 로직 구현", description: "{상세}", assignee: "backend-dev" },
     { title: "Pydantic 스키마 정의", description: "{상세}", assignee: "backend-dev" },
     
     // 프론트엔드 작업
     { title: "페이지 컴포넌트 구현", description: "{상세}", assignee: "frontend-dev" },
     { title: "API 연동 훅 구현", description: "{상세}", assignee: "frontend-dev" },
     { title: "상태관리 스토어 구현", description: "{상세}", assignee: "frontend-dev" },
     
     // AI/ML 작업
     { title: "AI 서비스 구현", description: "{상세}", assignee: "ai-ml-dev" },
     { title: "프롬프트 작성", description: "{상세}", assignee: "ai-ml-dev" },
     
     // QA 작업 (의존성 있음)
     { title: "백엔드 경계면 검증", description: "API↔DB, 스키마 정합성", assignee: "qa-validator", depends_on: ["API 라우터 구현", "서비스 로직 구현"] },
     { title: "프론트↔백엔드 통합 검증", description: "API 응답↔훅 타입, 라우트 경로", assignee: "qa-validator", depends_on: ["페이지 컴포넌트 구현", "API 연동 훅 구현"] },
     { title: "AI↔API 통합 검증", description: "AI 입출력↔API 스키마", assignee: "qa-validator", depends_on: ["AI 서비스 구현"] },
   ])
   ```

### Phase 3: 병렬 구현 (팬아웃)

**실행 방식:** 팀원들이 자체 조율

백엔드·프론트엔드·AI/ML 에이전트가 병렬로 작업을 수행한다. QA는 의존 작업 완료를 대기하며 점진적으로 검증한다.

**팀원 간 통신 규칙:**
- backend-dev는 API 응답 shape 확정 시 frontend-dev와 qa-validator에게 SendMessage로 알림
- frontend-dev는 필요한 API가 없으면 backend-dev에게 요청
- ai-ml-dev는 AI 서비스 인터페이스 확정 시 backend-dev에게 알림
- qa-validator는 경계면 불일치 발견 시 해당 에이전트에게 즉시 수정 요청

**산출물 저장:**

| 팀원 | 출력 경로 |
|------|----------|
| backend-dev | `_workspace/02_backend_{module}.md` |
| frontend-dev | `_workspace/02_frontend_{module}.md` |
| ai-ml-dev | `_workspace/02_aiml_{module}.md` |
| qa-validator | `_workspace/03_qa_{module}_report.md` |

**리더 모니터링:**
- TaskGet으로 전체 진행률 확인
- 팀원이 막혔을 때 SendMessage로 지시 또는 작업 재할당
- QA 보고서의 Critical 이슈는 즉시 해당 팀원에게 전달

### Phase 4: 통합 및 최종 검증 (팬인)

1. 모든 팀원의 작업 완료 대기 (TaskGet으로 상태 확인)
2. 각 팀원의 산출물을 Read로 수집
3. QA 보고서의 FAIL 항목이 모두 해소되었는지 확인
4. 미해소 항목이 있으면 해당 에이전트에게 수정 요청 (최대 2회 반복)
5. 최종 통합 결과 정리

### Phase 5: 정리 및 보고

1. 팀원들에게 종료 요청 (SendMessage)
2. 팀 정리 (TeamDelete)
3. `_workspace/` 디렉토리 보존 (사후 검증·감사 추적용)
4. 사용자에게 결과 요약 보고:
   - 구현된 모듈 목록
   - 파일 변경 사항
   - QA 검증 결과 요약
   - 남은 TODO (있는 경우)
5. 사용자 피드백 요청: "결과에서 개선할 부분이 있나요?"

## 데이터 흐름

```
[리더/오케스트레이터]
    │
    ├─ TeamCreate ─┬─ [backend-dev]   ←SendMessage→ [frontend-dev]
    │              ├─ [frontend-dev]   ←SendMessage→ [ai-ml-dev]
    │              ├─ [ai-ml-dev]      ←SendMessage→ [backend-dev]
    │              └─ [qa-validator]   ←SendMessage→ [all devs]
    │
    ├─ Phase 3: 팬아웃 (병렬 구현)
    │   ├─ backend: API, 서비스, 스키마 → _workspace/02_backend_*
    │   ├─ frontend: 페이지, 컴포넌트 → _workspace/02_frontend_*
    │   ├─ ai-ml: AI 서비스, 프롬프트 → _workspace/02_aiml_*
    │   └─ qa: 점진적 검증 → _workspace/03_qa_*
    │
    ├─ Phase 4: 팬인 (통합 검증)
    │   └─ QA FAIL 해소 루프 (최대 2회)
    │
    └─ Phase 5: 결과 보고
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| 팀원 1명 실패/중지 | 리더가 SendMessage로 상태 확인 → 재시작 또는 다른 팀원에게 재할당 |
| QA에서 Critical 이슈 다수 | 해당 팀원에게 수정 요청, 2회 후에도 미해결 시 사용자에게 보고 |
| 타임아웃 | 현재까지 완성된 부분 결과 사용, 미완료 팀원 종료 |
| 팀원 간 타입 충돌 | QA가 중재, API 응답 shape을 정본으로 통일 |
| 기존 코드와 충돌 | 기존 코드 우선 존중, 리더에게 보고 후 판단 |

## 테스트 시나리오

### 정상 흐름
1. 사용자가 "프로젝트 관리 모듈 구현해줘" 요청
2. Phase 1: build-plan에서 관련 STEP 확인, 작업 분배 계획 수립
3. Phase 2: 4명 팀 구성 + 10개 작업 등록
4. Phase 3: 백엔드(API 3개), 프론트(페이지 2개), AI(서비스 1개) 병렬 구현, QA 점진 검증
5. Phase 4: QA 보고서 FAIL 2건 → backend-dev 수정 → 재검증 PASS
6. Phase 5: 팀 정리, 결과 보고

### 에러 흐름
1. Phase 3에서 ai-ml-dev가 LLM API 연결 오류로 중지
2. 리더가 유휴 알림 수신 → SendMessage로 상태 확인
3. AI 서비스를 폴백 모드(규칙 기반)로 구현하도록 지시
4. 나머지 결과로 Phase 4 진행
5. 최종 보고서에 "AI 서비스: 폴백 모드로 구현, LLM 연동은 후속 작업" 명시


## G2B(나라장터) 공공입찰 연동 작업

나라장터 입찰/낙찰 또는 공공입찰 AI 분석 작업 요청 시, `propai-g2b-integration` 스킬을 참조하여 다음 순서로 팀에 위임한다.

1. **backend-dev**: `app/services/ai_services/bid_analyzer.py`(6엔진 연동), `app/schemas/g2b_bid.py`, `app/routers/g2b_bid.py` 구현/수정. 추정가격 역산 + QTO/수지/용도지역/인허가/ESG/시장 체인. (propai-g2b-integration + propai-backend 스킬)
2. **frontend-dev**: `apps/web/components/g2b/`(G2BBidDashboard/G2BBidAnalysisModal/G2BAwardStats), `g2b/page.tsx`. /api/v1/g2b/* 연동. (propai-g2b-integration + propai-frontend 스킬)
3. **qa-validator**: Pydantic(G2BBidAnalyzeResponse)↔TS(AnalysisResult) 타입 정합, 라우트 경로(/api/v1/g2b/*)↔apiClient 호출 교차검증, 역산→QTO→원가 체인 비-0 검증. (propai-qa 스킬)

데이터 흐름: `G2BClient 수집 → g2b_bid_service 저장 → bid_analyzer.analyze_feasibility(6엔진) → /feasibility 라우트 → G2BBidAnalysisModal`.
