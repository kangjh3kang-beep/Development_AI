# MemoryHub follow-up 검증 + reconcile 인계서 (2026-06-25)

> 작성: `memory-hub-verify-reconcile` 레인(OMC 5에이전트 적대검증 워크플로 wwckktyay). 라이브 재확인 완료.
> ★결론: 사용자 follow-up(#3 schema_guard 부팅배선 · #4 인프라 graceful · MEDIUM1 qdrant 싱글톤)은 **이미 origin/main(763cf05c)에 존재** → 신규 구현 금지(100% 중복충돌). 진짜 잔여는 2건.

## 0. Load-bearing 사실 (라이브 git 재확인)
- `git merge-base --is-ancestor 3870cbdc origin/main` = **YES** → `feat/memory-hub-loop-recovery`(3870cbdc)는 **이미 origin/main에 머지됨**. recovery = 사실상의 정본.
- `origin/main:.../memory_hub/schema_guard.py` 존재 + `main.py` `ensure_memory_schema` 호출 1건 → **#3 부팅배선 main에 존재**.
- `origin/main:.../qdrant_client.py` `_CLIENT` 5건 + `memory_service.py` `wait_for/TIMEOUT` 6건 → **#4 graceful·qdrant 싱글톤·recall timeout main에 존재**.

## 1. 이미 완료 (재구현 절대 금지 — 충돌)
| follow-up 항목 | 상태 | 위치 |
|---|---|---|
| #3 schema_guard 부팅배선(agent_memories 멱등 CREATE + lifespan 훅) | ✅ DONE | origin/main |
| #4 graceful(langchain/Qdrant 옵셔널·recall 3s timeout·DB-always·celery import 킬러버그 FIX) | ✅ DONE | origin/main |
| MEDIUM1 qdrant `:memory:` 미메모이즈 → 프로세스 싱글톤 | ✅ DONE | origin/main |
| #1 comprehensive→specialist 비차단 트리거(.delay) | ✅ DONE | origin/main |

## ★ 업데이트(2026-06-25): R1·R2 구현 완료 — `fix/memhub-recall-residuals`(origin/main 기반, ba3a819b·353d612b 푸시)
> 사용자 승인으로 R1·R2 + 전역전파를 origin/main 기반 additive 브랜치로 구현·검증·푸시(적대리뷰 APPROVE crit/high0·pytest 회상17 회귀0). 통합자는 이 브랜치를 PR 머지. 아래 §2 R1/R2는 **DONE**, 잔여=§3 소비처 택일·R3 Alembic·R4 원자성·브랜치 정리(통합자).

## 2. 진짜 잔여 (어디에도 미반영 — 정본=main 위 후속 증분)
> ★R1·R2 = **DONE**(`fix/memhub-recall-residuals`). R3~R5 = 통합자 후속.
### R1. uuid4 point-id 위조 (실버그) — `memory_service.py:159`
```python
id=uuid.UUID(scored_point.id) if '-' in str(scored_point.id) else uuid.uuid4(),
```
- 비대시 Qdrant point id면 **실레코드와 무관한 랜덤 UUID로 위조** → `recalled_memory_ids` provenance 신뢰성 훼손(silent data corruption). 인접개선(created_at 안전파싱)이 추가돼 '고친 것처럼' 보이나 **위조 라인은 loop 베이스라인과 1바이트도 안 변함**(거짓완료).
- 현재 store는 항상 dashed uuid4 point_id라 미발화이나 외부/레거시 point 노출 시 발화.
- **수정안**: 비대시 id면 회상 항목 스킵(또는 결정론 해시 id) — `uuid4()` 날조 금지. 정직 표기.

### R2. loop(48127c56) #2 디커플 가치 main 미흡수 (라이브: main에 0건)
- `recalled_memory_ids`/`recalled_count` ingest provenance (loop `specialist_agent.py:196-197) — 회상→저장 폐루프 추적.
- `_format_recall_block` 헬퍼(loop `:29`) + 원장 결정론 미주입 의도 주석(loop `:136`).
- (선택) `recaller`/`ingester` DI 주입 — 테스트 용이성.
- 회상경로 신규 6테스트(loop `tests/agents/test_specialist_agent.py` 12 vs main 6): format_recall_block · recall_surfaces_in_return_and_ingest · ledger_payload_excludes_recall(결정론) · recall_failure_graceful · recall_injected_into_interpreter_prompt · default_path_graceful.
- ★흡수 방식: **hunk 단위 additive**(loop 통짜 머지 금지 — loop은 memory_service에 하드 langchain import·qdrant 싱글톤 부재 회귀 보유). main의 graceful memory_service/qdrant_client는 그대로 두고 specialist_agent + 테스트만 흡수.

### R3 (minor). agent_memories Alembic 정식 마이그레이션 부재
- recovery는 schema_guard 단독. growth 선례는 **v62_5 마이그레이션 + schema_guard 듀얼트랙** → '선례=schema_guard만'이라는 이연 정당화는 부정확. 단 부팅 자체는 schema_guard로 보장(비차단).
- 현재 alembic 단일헤드 → 신규 마이그레이션 단일연결 가능(versions/ claim 필요). CI `alembic upgrade head` 경로 schema drift 보강용.

### R4 (minor). store_experience 원자성 — Qdrant upsert 성공 후 db.commit() 실패 시 고아벡터 보상 delete 없음.
### R5 (minor). memory_hub 테스트 0건 (graceful/timeout/싱글톤/celery-noop 회귀방지 픽스처 부재).

## 3. 소비처 충돌 (통합자 택일 — ★머지 전 필수)
`comprehensive_analysis_service.py` `analyze()` `return result` 직전에서:
- **landtools(54c4aa7e)**: `run_specialist_domains(...)` **동기 인라인** + 귀속게이트(`include_specialists and zone_type and (project_id or tenant_id)`) + 응답표면화(`result['specialists']`).
- **main(recovery)**: `run_domain_specialists_task.delay(...)` **fire-and-forget Celery**.
- → 같은 hunk 텍스트 충돌 + far/zoning **이중 디스패치**(원장 이중 append·detect_contradictions 자가모순 위험).
- **권고**: 귀속게이트 있는 **동기 경로(landtools) 우선**, main의 comprehensive `.delay` 제거로 이중 디스패치 차단. (또는 .delay만 남기고 동기 제거 — 택일.)

## 4. 중복 브랜치 정리 (통합자)
- **정본 채택**: `feat/memory-hub-loop-recovery`(3870cbdc) = 이미 origin/main.
- **폐기**: `c29ca954`(feat-tmp 구base 사본), `deploy/memory-hub-recovery`(21:52 푸시본 — recovery와 동일물).
- **부분 흡수 후 폐기**: `feat/memory-hub-loop`(48127c56) — R2 hunk만 cherry-pick 후 폐기.
- `fix/land-tools-multiparcel-responsive`(54c4aa7e) — 소비처 택일(§3) 반영 후 머지.

## 5. 인프라 deploy-pending (코드 아닌 운영 — graceful 완비)
- `OPENAI_API_KEY`(임베딩) 관리자 시크릿 입력 · `QDRANT_HOST`(공유 호스트, 미설정 시 프로세스로컬 `:memory:`=워커↔API 교차 불가) · Celery 워커 기동(ingest `.delay`) · `langchain_openai` 설치.
- 미비 시 전부 graceful degrade(크래시 0·가짜 회상/저장 0) — 이미 검증됨.

## 6. 충돌 안전 메모
- R1·R2·R3은 전부 **정본=main 동일파일 편집면**(recovery가 방금 머지). 단독 커밋 시 병행 recovery 푸시세션 침범 위험 → **versions/·memory_service·specialist_agent claim 선행 + recovery 소유세션 보드 조율** 필수.
- 안전 행동: 본 인계서 + 보드 note. 코드는 통합자/소유세션 권한.
