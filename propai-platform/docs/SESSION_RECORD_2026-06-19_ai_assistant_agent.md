# 세션 기록 — AI 비서 에이전트화 (2026-06-19)

> 기록·저장·공유 원칙(MEMORY `feedback_record_and_share`)에 따른 전 과정·결과 기록.
> 브랜치 `feat/ai-assistant-agent` (origin/main b6100bd4 분기). 영향: **백엔드(Micro)만, 프론트 무변경.**

## 1. 배경/문제
스크린샷 제보: AI비서가 신규 주소(의정부동 224)에 대해 "실제 데이터를 보유하지 않으니 공공데이터를 직접
확인하라"고 **되묻기**. 원인 진단 — 백엔드 `ai_assistant.py`가 도구 0개의 **단발 채팅**이고 프롬프트가
"모르면 모른다고 답하라"로 묶여 있어, 플랫폼 536 API가 있어도 **스스로 호출 못 함**. → "AI 비서"가 아닌
"컨텍스트 주입형 챗봇". (사용자 지적 정확)

## 2. 과정 (오케스트레이터-기획자)
1. **리서치 3종 병렬**: ① 경쟁 프롭테크 코파일럿/에이전트 UX(Feasable·ArkDesign·밸류맵·스페이스워크,
   Anthropic Claude Code 분류기·Bedrock x-requireConfirmation·LangGraph HITL) ② LangGraph/bind_tools
   기술패턴 ③ 도구화할 엔드포인트·서비스 인벤토리.
2. **환경 실측(설계 결정의 근거)**: langgraph 로컬 부재·prod 0.2.40 구버전·langchain-core 버전스큐 →
   **langgraph 미사용**. langchain-anthropic `bind_tools`는 양쪽 존재 → 채택. 모델ID는 get_llm() 경유만
   (origin/main은 현행ID, 로컬 main은 94커밋 stale였음).
3. **설계서 작성**(docs/AI_ASSISTANT_AGENT_DESIGN.md) — 「행동 우선·질문 최소」, 읽기툴 자동/쓰기·과금툴 후속.
4. **구현**: `assistant_agent.py`(bind_tools 수동 ReAct 루프 + 읽기도구 3개 + 계측) + `ai_assistant.py`
   배선(에이전트 우선 + 단발 폴백, 프론트 무변경).
5. **검증 루프(성장루프 ≥9.5 게이트)**: 1차 리뷰 9.2 → MED 4건 수정 → 2차 리뷰 **9.6, Critical/High 0, APPROVE.**

## 3. 결과 (무엇이 바뀌나)
- 주소/부지 질문 시 비서가 **스스로 도구 호출** → 실데이터로 답(되묻기 해소).
- 도구(읽기전용·무료·in-process): `analyze_site`(용도지역·대지면적·공시지가·특이부지),
  `feasibility_precheck`(개발방식·사업성 90초), `estimate_land_price`(적정 매입가).
- 도구 진행("🔍 부지 분석 조회 중… ✓ 완료")을 **기존 SSE `{"delta":...}` 텍스트로 합성** → 프론트 0 변경.
- 가드레일: 실데이터만·실패 정직고지(무목업), 추론값(keyword_inference) [주의] 경고(할루시네이션 가드),
  용적률 실효+특이부지 우선·법정 별도, recursion 상한(요청당 LLM ≤4회), 도구에러 자가복구 안내문,
  계측 단일경유(record_llm_response_billing 매 라운드), 에이전트 미가용 시 단발 폴백(무회귀).

## 4. 검증 증거
- `ruff`(E/F/W/I/N/UP/B/SIM) **클린**, `py_compile` OK.
- 모의 ReAct 단위테스트 PASS: 이벤트순서(tool_start/end→최종델타), **매 라운드 계측 토큰>0**,
  추론값 [주의] 경고, str-args 정규화, collect 경로, 실데이터 포맷.
- 코드리뷰 2회(fresh): 9.2 → **9.6/10**, Critical/High 0.

## 5. 설계 결정 핵심 (ainvoke 채택)
각 라운드를 `astream` 아닌 **`ainvoke`**로: ① 모든 버전에서 `usage_metadata` 보장(계측 누락 0,
stream_usage 공유파일 수정 회피) ② tool_calls 버전무관 파싱(prod 조용한 무효화 방지). 트레이드오프=최종
답변 토큰스트리밍 대신 완성 후 1회 델타(도구 진행은 실시간).

## 6. 미적용(후속) — 프론트 조율 필요
- **B. 쓰기·과금 도구 확인게이트**(프로젝트 생성/다필지 배치/현장 생성): 확인 UI가 프론트 변경 수반 →
  `AIAssistant.tsx` WIP 세션과 조율 후. 설계는 설계서 §6.
- **C. 페이지 행동 전파**(부지분석 자동 트리거·페이지 이동/프리필): 프론트 액션 프로토콜 공동설계.
- `llm_provider.get_llm`에 `stream_usage` 전달 보강 시 토큰스트리밍 복원 가능(인프라 후속).

## 7. 배포 (다른 Claude=통합/배포 담당 인계)
- 영향: **백엔드 Micro만**(프론트 무변경). 신규 의존성 0(langchain-anthropic/core 기존).
- ★라이브 검증(키 보유 서버): 신규 주소(예: 의정부동 224) 질의 → **tool_start 이벤트 실관측** +
  실데이터(용도지역·공시지가) 응답 + billing token-usage에 service=ai_assistant 집계 확인.
- 모델ID drift(로컬/origin은 stale ID, prod는 서버 직접 패치) 정합은 deploy-coordinator 영역.
