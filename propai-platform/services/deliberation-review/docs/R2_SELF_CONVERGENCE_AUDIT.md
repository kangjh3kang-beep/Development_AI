# R2 자기수렴 감사 — 고정점 보고서

페이즈: **R2**(공급/소비 분리 + HITL 우선순위 SLA + HWP 파이프 + 외부API fallback)
병목 해소: BN1(on-demand 차단)·BN4(HWP)·BN6(HITL 적체)·WB10(인용검증 라이브의존).
선행: R0, R0.5, R1.5. A절 재사용 + INV-13(공급/소비 분리)/INV-14(HITL 활성화 게이트)/INV-15(비차단 degrade).

## 회차별 신규 결함수 (단조감소)

| 회차 | 신규(닫을 수 있는) 결함 | 근본원인 | 조치 |
|------|------------------------|----------|------|
| 1 | **2** — ① DoD가 명시한 "공급 비동기 ↛ 소비 지연" 타이밍 테스트 부재 ② `RulesetReader.load`가 store의 MirrorSnapshot 정본을 그대로 반환 → 소비자 in-place 변형이 미러 오염(AT-6 immutable 미충족) | ① DoD 테스트 누락 ② 공유 객체 반환(immutability 미강제) | ① `test_supply_async_does_not_block_consumer`(큐잉만+즉시반환) ② MirrorSnapshot `frozen=True` + load가 `model_copy(deep=True)` 반환 + `test_mirror_immutable_for_consumer` |
| 2 | **0** | — | **고정점 도달** |

단조감소: **2 → 0**.

## 추가된 테스트
- `test_supply_async_does_not_block_consumer` — 미수집 관할 load는 동기 수집을 수행하지 않고 HarvestJob 큐잉만 후 즉시 반환.
- `test_mirror_immutable_for_consumer` — 소비자가 받은 룰셋 변형이 store 정본 미러에 영향 없음.

## 감사 D절 재확인 (타이밍)
공급측 비동기 경로(Harvester/HITL/MirrorWriter)는 Celery 태스크(tasks/supply_tasks.py)로 분리. 소비측 `RulesetReader.load`는 미러 조회 + (미수집 시) 큐잉만 수행 → 동기 수집 미실행, 즉시 반환(타이밍 테스트로 입증).

## 잔존 forward 항목 (degradation 흡수)
- **Celery 실 broker 배선**: 태스크 정의(supply.run_harvest_job, verify.live_citation_check) 제공. enqueue는 dev in-memory(`_PENDING_JOBS`), 실 broker 연결 시 `.delay`로 교체. 무음 아님(큐잉 표면화).
- **미러/후보 DB 영속화**: 모델·테이블(0005) 제공, in-memory store→DB 적재는 후속 배선.
- **R2 미러 ↔ R1.5/R3 snapshot 정합**: MirrorSnapshot.snapshot_id로 결속. R3 판정엔진이 미러 룰셋 + R1.5 산정값을 결합.

## INV 위반 0 체크리스트
- [x] INV-13 공급/소비 분리 — consume/ + services/verify/ 라이브호출/인라인LLM 0(정적검사 `test_consume_static`), spy_network live_calls==0. 라이브 정합은 tasks/ 주기잡으로 분리.
- [x] INV-14 HITL 활성화 게이트 — RuleExtractor→DRAFT, ACTIVE만 미러 적재, DRAFT는 is_active=False.
- [x] INV-15 비차단 degrade — 미수집 관할 → degraded(national)+ETA+enqueue, blocked=False.
- [x] INV-1..12(승계) — 결정론·표면화·계약·버전축·재현성·파라미터 주입 유지.

## 게이트 결과
- 수용 테스트: **58 passed**(누적; R2 AT-1..7 + DoD 정적검사 + immutability/타이밍 보강).
- 마이그레이션: `0005_r2` 실DB(review) 반영 — source_document, rule_candidate, mirror_snapshot, hitl_task, harvest_job, citation_check.
- 정적 스캔(INV-3): 하드코딩 0. 소비경로 정적검사: 라이브/LLM 토큰 0.
- 린트: ruff `All checks passed`.

**결론: R2 DoD 충족 — 고정점 도달.** 다음 = R3(룰 의존 DAG + 완화 3값 + 신뢰도 합성 게이팅 — R1.5 산정값 + R2 미러 룰셋 결합 판정).
