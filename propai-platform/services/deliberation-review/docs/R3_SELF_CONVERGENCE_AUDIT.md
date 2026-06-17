# R3 자기수렴 감사 — 고정점 보고서

페이즈: **R3**(룰 의존 DAG + 완화 3값 판정 L3-A + 신뢰도 합성 게이팅 L5 + 매핑 게이트) — **판정엔진 코어**.
단절 해소: WB14(룰 상호의존)·WB8(완화 표현불가→거짓 불합격)·WB6/B(신뢰도 합성)·WB5(오매핑 degrade).
선행: R0~R2. A절 재사용 + INV-16(3값 판정)/INV-17(의존 평가순서)/INV-18(합성 게이팅).

## 회차별 신규 결함수 (단조감소)

| 회차 | 신규(닫을 수 있는) 결함 | 근본원인 | 조치 |
|------|------------------------|----------|------|
| 1 | **2** — ① `evaluate_relaxations`가 완화 전제 **상태 미상을 UNMET 기본값** 처리 → 거짓 불합격(NON_COMPLIANT) 위험(INV-16) ② `Finding.gated_status` 기본값 `CONFIRMED` → 미게이트 finding이 확정으로 표면화(무음 오통과 위험, INV-18) | ① 미상↔불충족 혼동 ② 비보수적 기본값 | ① 기본값 UNVERIFIABLE(→위원확인) + 테스트 2건 ② 기본값 NEEDS_REVIEW + 테스트 1건 |
| 2 | **0** | — | **고정점 도달** |

단조감소: **2 → 0**.

## 감사 D절 — 두 핵심 보증 표적 재검증
- **거짓 불합격 0**: 위반이라도 완화 여지(MET/PROVIDED/UNVERIFIABLE/미상)가 있으면 NON_COMPLIANT 단정 안 함. **오직 전제가 '검증된 UNMET'일 때만** NON_COMPLIANT(test_explicit_unmet…). 미상은 위원확인(test_missing_prerequisite…).
- **무음 오통과 0**: finding은 게이트 전 NEEDS_REVIEW(보수). FindingGate가 composite<임계 또는 충돌 시 NEEDS_REVIEW 분리. MappingGate는 저신뢰 매핑을 HELD+silent_pass=False로 분리.

## 추가된 테스트
- `test_missing_prerequisite_state_does_not_false_fail` — 완화 전제 미상 → 위원확인(거짓 불합격 금지).
- `test_explicit_unmet_relaxation_is_noncompliant` — 검증된 불충족만 NON_COMPLIANT.
- `test_finding_defaults_to_needs_review_until_gated` — 미게이트 finding은 확정 아님.

## 잔존 forward 항목 (degradation 흡수)
- **prose→술어 추출 등 환원불가 항목**: R2 RuleExtractor(DRAFT)+HITL 승인으로 흡수. R3는 ACTIVE 룰만 평가.
- **finding ↔ L6 산출/감사로그 결속**: FindingModel(0006) 제공, 분석 단위 적재·리포트는 L6에서 배선.
- **R1.5 산정값 + R2 미러 룰셋 결합**: EvalCase(measured=LegalQuantity.value, limit=미러 룰 파라미터)로 결합. snapshot_id 정합 유지.

## INV 위반 0 체크리스트
- [x] INV-16 3값 판정 — COMPLIANT/NON_COMPLIANT/CONDITIONAL, 완화 여지 시 거짓 불합격 금지.
- [x] INV-17 의존 평가순서 — 위상정렬(전제→의존), 순환 시 crash 없이 위원 판단 degrade.
- [x] INV-18 합성 게이팅 — composite<임계(param)/충돌 → NEEDS_REVIEW 분리. 임계 파라미터화(AT-9 static_scan 0).
- [x] INV-1..15(승계) — 결정론·표면화·계약·버전축·공급소비분리·HITL게이트 유지.

## 게이트 결과
- 수용 테스트: **76 passed**(누적; R3 AT-1..9 + 거짓불합격/무음통과 보강).
- 마이그레이션: `0006_r3` 실DB(review) — rule, rule_edge, finding, mapping_assignment.
- 정적 스캔(INV-3/18): judge/gate/mapping 하드코딩 임계 0.
- 린트: ruff `All checks passed`.

**결론: R3 DoD 충족 — 고정점 도달. R 시리즈(R0~R3) 완료, 판정엔진 코어 확보.**
다음 = L 확장: L3-B(공학 시뮬) → L4(유사사례 성숙도) → L5(인용검증 통합) → L6(산출/감사 리포트) → L3-C(정성 인용접지+재현성).
