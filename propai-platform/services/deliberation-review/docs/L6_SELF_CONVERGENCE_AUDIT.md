# L6 자기수렴 감사 — 고정점 보고서

페이즈: **L6**(산출물 — 판정/산정근거/시뮬/유사사례/보완권고/신뢰등급/출처/감사를 심의분석 보고서로 구조화).
선행: R0~R3 + L3-B + L4 + L5. A절 재사용 + INV-28(분류 보존)/INV-29(근거 동반 출력)/INV-30(재량경계 표기).

## 회차별 신규 결함수 (단조감소)

| 회차 | 신규 결함 | 조치 |
|------|-----------|------|
| 1 | **1** — DISCRETION_HELD(재량) 항목이 입력의 단정 verdict(예: COMPLIANT)를 보존 → INV-30("재량영역, 판정 보류 — 단정 금지") 위반 | 재량 항목 verdict 무효화(None) + 테스트 `test_discretion_does_not_assert_verdict` |
| 2 | **0** | **고정점 도달** |

단조감소: **1 → 0**.

## 감사 D절 — 최종 출력단 "무음 오판 0" 표적 재검증
- L5 분류(CONFIRMED/NEEDS_REVIEW/BLOCKED)를 구획(sections)으로 분리 보존 — 병합/은폐 없음(AT-1/AT-6).
- 미상 status → NEEDS_REVIEW(보수, CONFIRMED로 누출 안 함). 재량 → DISCRETION_HELD + verdict 무효화.
- 모든 항목 근거 강제(emit) + 감사 결속(snapshot_id/model_version/input_hash). 근거 없는 항목 → 라우트 400.

## INV 위반 0 체크리스트
- [x] INV-28 분류 보존 — 구획 분리, BLOCKED/NEEDS_REVIEW 별도 노출, CONFIRMED 누출 0.
- [x] INV-29 근거 동반 출력 — emit가 근거 없는 항목 차단 + 감사 결속(snapshot/model/hash).
- [x] INV-30 재량경계 표기 — 기준 미존재 → DISCRETION_HELD, 단정 verdict 무효화.
- [x] INV-1..27(승계) — 재현(input_hash)·결정론·게이팅 분류 보존.

## 게이트 결과
- 수용 테스트: **112 passed**(누적; L6 AT-1..6 + 라우트/재량 단정금지 보강).
- 마이그레이션: `0010_l6` 실DB(review) — review_report, report_item, recommendation.
- API: POST /api/v1/reports/build(구획 보존 + 체크리스트 + 대시보드, 근거 없는 항목 400).
- 정적 스캔/린트: 하드코딩 0, ruff clean.

**결론: L6 DoD 충족 — 고정점.** 다음 = L3-C(정성 심의 평가 — 인용접지 + 재현성 temp0/핀, 마지막 페이즈).
