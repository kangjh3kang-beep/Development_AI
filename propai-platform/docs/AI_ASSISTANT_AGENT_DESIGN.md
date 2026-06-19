# AI 비서 에이전트화 설계서 (PropAI Orchestrator → Tool-Use Agent)

**작성:** 2026-06-19 · **브랜치:** `feat/ai-assistant-agent` (origin/main b6100bd4 분기)
**상태:** Phase A(읽기도구 자동실행) 구현 대상. Phase B/C는 후속(프론트 조율 필요).

---

## 1. 문제 (As-Is)

기존 `apps/api/routers/ai_assistant.py`는 **단발 채팅**이다(`llm.ainvoke`/`astream`, 도구 0개).
시스템 프롬프트가 "데이터에 없으면 모른다고 답하라"로 묶여 있어, 신규 주소(예: 의정부동 224)를
물으면 플랫폼에 536개 API가 있는데도 **스스로 호출하지 못하고** 사용자에게 "공공데이터를 직접
확인하라"고 되묻는다. 프론트 `buildSsotContext`는 store에 이미 있는 값만 2KB로 주입하므로,
프로젝트가 없으면 컨텍스트가 비어 비서가 답할 근거 자체가 없다.

→ **AI 비서가 아니라 "컨텍스트 주입형 챗봇"**. 사용자 지적이 정확하다.

## 2. 목표 (To-Be) — 「행동 우선, 질문 최소」

주소만 받으면 비서가 **스스로 도구를 호출해 실데이터를 가져와** 답한다.
- **읽기·조회·계산(무료·비가역 아님)**: 사용자에게 묻지 않고 자동 실행.
- **사용자에게 묻는 경우는 3가지뿐**: ① 진짜 모호 ② 비가역/쓰기 ③ 과금 발생.
- **실데이터만**: 도구 결과만 근거로 답하고, 실패 시 "확인 불가"로 정직 고지(무목업 원칙 유지).

## 3. 외부 벤치마크 핵심 (리서치 요약)

- 프롭테크 코파일럿(Feasable·ArkDesign·밸류맵·스페이스워크) 공통 P0 = **단일 입력 → 전주기 자동충전**.
- 도구 UX: 진행표시(도구명·상태), **가짜 진행바 금지**, 추론단계 정직 라벨.
- 확인게이트(Anthropic Claude Code 분류기 · Bedrock `x-requireConfirmation` · LangGraph HITL):
  **읽기=자동, 쓰기·과금·비가역·외부영향=게이트**. 확인피로 방지 위해 **동적 임계**.
- 함정: 536 API 1:1 도구화 금지 → **태스크 단위 소수 도구**(질의당 3~5개), 의미있는 식별자,
  근거추적성 1급화, recursion 상한, 도구 에러는 모델이 읽을 안내문으로.

## 4. 환경 제약 (실측) — 설계 결정의 근거

| 항목 | 실측 | 결정 |
|------|------|------|
| `langgraph` | **로컬 .venv 부재**, prod는 **0.2.40(구버전)** | LangGraph 미사용 |
| `langchain-core` | 로컬 1.2 / prod 0.3 (**버전 스큐**) | 버전 의존 API 회피 |
| `langchain-anthropic` (`bind_tools`) | **양쪽 존재**(로컬 1.4 / prod 0.3) | ✅ bind_tools 기반 |
| `record_llm_response_billing(llm, resp, service)` | base_interpreter.py:196 | 계측 단일경유 재사용 |
| 모델ID | origin/main 현행(sonnet-4-6 등) | **get_llm() 경유만**(하드코딩 금지) |
| 도구화 서비스 | AutoZoning/precheck/land_price 모두 **db 불필요·주소기반** | in-process 직접 호출 |

→ **결론: langgraph 없이 `bind_tools` + 수동 ReAct 루프**. 의존성 0 추가, 로컬 검증 가능, 버전스큐 무관.

## 5. 아키텍처 (Phase A)

```
/api/v1/ai/chat(/stream)  ─→  assistant_agent.run_agent_events(msgs)
                                  │  (bind_tools 수동 ReAct 루프, 최대 3라운드)
   ┌──────────────────────────────┼───────────────────────────────┐
   │ llm = get_llm() ; llm.bind_tools(READ_TOOLS)                   │
   │ loop: ainvoke → tool_calls 있으면 ToolMessage 채워 재호출,    │
   │        없으면 최종 답변 텍스트를 델타로 송출 후 종료          │
   │        매 라운드 record_llm_response_billing(계측 단일경유)   │
   └──────────────────────────────┬───────────────────────────────┘
   READ_TOOLS(읽기전용·무료·in-process):
     • analyze_site(address)        → AutoZoningService.analyze_by_address  (용도지역·대지면적·공시지가·특이부지)
     • feasibility_precheck(address) → run_instant_precheck(use_llm=False)   (개발방식·사업성 90초)
     • estimate_land_price(address)  → estimate_land_price                    (적정 매입가)
```

### 프론트 무변경 핵심
에이전트 이벤트(`delta`/`tool_start`/`tool_end`)를 라우터가 **기존 SSE `{"delta": ...}` 텍스트로 합성**한다.
- `delta` → 그대로 텍스트
- `tool_start` → `"\n\n🔍 {라벨} 조회 중…\n"`
- `tool_end` → `"✓ {라벨} 완료\n\n"`

→ 새 SSE 이벤트 타입을 만들지 않으므로 `AIAssistant.tsx`(다른 세션 WIP) **0 변경 = 충돌 0**.

### ainvoke 채택(스트림 아님)의 이유 — 신뢰성 > 토큰 스트리밍
각 라운드를 `astream`이 아닌 **`ainvoke`**로 수행한다. 이유:
1. **계측 확실성**: `ChatAnthropic.astream`은 `stream_usage=True` 없이는 청크에 `usage_metadata`를
   싣지 않는 버전이 있는데, `get_llm()`이 해당 kwarg를 전달하지 않는다(공유파일 수정 회피).
   `ainvoke`는 모든 버전에서 `usage_metadata`를 채우므로 **토큰 계측이 누락되지 않는다**.
2. **도구호출 신뢰성**: prod(langchain-anthropic 0.3)에서 `astream` 청크의 `tool_calls` 누적이
   불확실하면 에이전트가 조용히 무효화될 위험이 있다. `ainvoke`는 버전 무관하게 파싱된 `tool_calls`를 보장.
- 트레이드오프: 최종 답변이 토큰 단위로 흐르지 않고 완성 후 1회 델타로 송출(도구 진행표시는 실시간).
  토큰 스트리밍을 되살리려면 `llm_provider.get_llm`이 `stream_usage`를 전달하도록 보강(후속·인프라 담당).

### 가드레일
- **recursion 상한** 4라운드 → 초과 시 도구 없이 1회 최종 답변 강제.
- **도구 에러**: 예외를 삼키지 않고 "조회 실패 … 데이터 없이 정직 고지하라"는 안내문을 `ToolMessage`로 반환(자가복구).
- **그라운딩 프롬프트**: 도구 결과만 근거, 추정 금지, **용적률은 실효(조례)+특이부지 우선·법정 별도**(전역규칙 `project_shallow_zone_analysis_parity`).
- **계측 단일경유**: 매 LLM 라운드 `record_llm_response_billing(base_llm, agg, service="ai_assistant")` (best-effort).
- **폴백**: bind_tools 미지원/에이전트 예외 시 **기존 단발 채팅으로 자동 강등**(무회귀).
- **키 미설정/no_key**: 기존 정직 안내 경로 보존.

## 6. 미적용(후속, 프론트 조율 필요) — Phase B/C

- **B. 쓰기·과금 도구 확인게이트**: 프로젝트 생성/다필지 배치/현장 생성 등은 "제안→사용자 확인 후 실행".
  확인 UI가 프론트 변경을 수반하므로(현재 `AIAssistant.tsx` WIP) 프론트 세션과 조율 후 진행.
  설계: 쓰기 도구는 실행 대신 `needs_confirmation` 제안 반환 + 동적 임계(과금>관리자한도일 때만 게이트) + 멱등키.
- **C. 페이지 행동 전파**: "부지분석 시작"을 주소 프리필로 자동 트리거, 수지/설계 페이지 이동·입력 채움.
  프론트 액션 이벤트 프로토콜 필요 → 프론트 세션과 공동 설계.

## 7. 검증 게이트 (성장루프)

- py_compile · import 스모크 · 모의 에이전트 루프(가짜 LLM) 단위 검증.
- **코드리뷰 10점 만점 ≥9.5 통과**(critical/high 0). 미달 시 반복 개선 후 재검증.
- 라이브 검증(키 보유 서버): 의정부동 224 등 신규 주소 → 비서가 도구 호출해 실데이터 응답 확인(배포 담당).

## 8. 배포

origin/main 분기 전용 브랜치 `feat/ai-assistant-agent`, main 직푸시 금지.
보드 HANDOFF로 통합/배포 담당(다른 Claude)에게 인계. 영향: **백엔드(Micro)만**, 프론트 무변경.
