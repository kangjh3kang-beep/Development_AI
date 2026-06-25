# 진단 — MemoryHub 자동 회상/저장 폐루프 단절 (2026-06-25)

> 사용자 질문: "모든 도메인 에이전트(SpecialistAgent)가 기동될 때마다 지식 읽기/쓰기가 백그라운드에서 100% 자동 구동되는 것 아닌가?"
> 답: **아니다. 코드는 generic run()에 배선됐으나 현재 사실상 0% 구동.** 4중 단절(아래).

## 그라운드 트루스 (코드 추적)

말씀하신 설계(Step 2.5 recall_experience→prior_context / Step 6 ingest_experience_task.delay)는 `SpecialistAgent.run()`의 **공통 메서드**에 실재한다(domain별 아님 → 구조상 모든 도메인 트리거). 그러나:

### ① 소비처 0 (★치명 — 첫 도미노)
- `SpecialistAgent.run()`(=MemoryHub 보유)을 **프로덕션에서 호출하는 코드가 없음**.
- 라우터 `/api/v1/agents/domain`(main.py:649)은 **별개 시스템** `DomainAgentsService.run_domain`(asset/development/transaction/finance)을 호출 — SpecialistAgent·get_specialist·MemoryHub 일절 미사용(grep 0).
- `SpecialistAgent.run()` 호출처 = **단위테스트 6곳뿐**(tests/agents/test_specialist_agent.py).
- → MemoryHub 회상/저장이 라이브에서 **한 번도 발화하지 않음**.

### ② interpreter=None (회상→출력 미반영)
- 회상결과 `rag_memories`는 `if self._interpreter is not None:` 블록 안에서만 prior_block에 주입(specialist_agent.py:91-104).
- registry 7도메인(permit·zoning·far·cost·market·심의·설계) **전부 `interpreter=None`**(registry.py:29,64,69,105,110,185,190).
- → run()이 호출돼도 회상은 계산 후 **버려짐**(LLM·반환·원장 어디에도 미반영). = 성장 뇌 감사(project_growth_brain_audit) "저장만·출력 미반영" 단절과 동일 패턴.

### ③ agent_memories 테이블 미생성
- `agent_memories` Alembic 마이그레이션 **부재** → ingest 태스크가 `db.add(AgentMemory)` 단계서 실패(테이블 없음).
- 회상은 Qdrant 연결 + OPENAI_API_KEY(text-embedding-3-small) 필요(memory_service.py:23-26). 미설정 시 graceful 스킵.

### ④ 미커밋·미머지
- `services/memory_hub/`(memory_service.py·qdrant_client.py)·`tasks/memory_tasks.py`·`models/memory.py`·`schemas/memory.py` 전부 untracked(feat-tmp 로컬).
- senior 브랜치 등 타 브랜치엔 아예 없음. models/__init__.py·specialist_agent.py·registry.py는 feat-tmp Modified(미커밋).

## "진짜 폐루프 복구"에 필요한 작업 (순서)

1. **소비처 결정·배선(P0)**: SpecialistAgent를 실제 분석 흐름에 연결. 후보=(a) decision_brief/comprehensive가 도메인별 get_specialist().run() 호출 (b) DomainAgentsService에 MemoryHub graft (이미 라우터 연결됨) (c) 둘 통합. ★이게 없으면 나머지는 dead-wire.
2. **interpreter 주입(P0)**: 회상이 LLM·출력에 반영되도록. 최소복구=rag_memories를 interpreter 유무와 무관히 run() 반환/원장/ingest에 표면화(decouple) + 도메인에 실 인터프리터(base_interpreter 등) 주입.
3. **마이그레이션(P1)**: agent_memories Alembic + 부팅 schema_guard(런타임 DDL 금지·AD-4).
4. **인프라(P1·deploy-pending)**: Qdrant 컬렉션 부트스트랩·OPENAI_API_KEY(관리자 시크릿)·Celery 워커 가동 확인. 미설정 시 graceful(정직).
5. **커밋/머지 정리(P0)**: 미커밋 MemoryHub 일체 커밋(소유 세션 확인). 머지=통합자.

## 안전수칙
- feat-tmp는 다수 미커밋 작업 공존(MemoryHub + decision_brief PLAN + legal/presale/expert_panel Modified). 남의 미커밋 임의 커밋 금지 — 범위 합의 후.
- 무목업·정직: 인프라 미비 시 "미설정"으로 표면화(가짜 회상/저장 위장 금지).
