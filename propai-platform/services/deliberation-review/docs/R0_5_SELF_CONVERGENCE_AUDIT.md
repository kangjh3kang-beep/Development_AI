# R0.5 자기수렴 감사 — 고정점 보고서

페이즈: **R0.5**(시트역할 확정 L0.5 + 요소 의미분류 L1.1 + cross-sheet WB18)
선행: R0. A절 프리앰블 재사용 + 추가 불변식 INV-8(3원 합의 라우팅)/INV-9(분류 무가정).

## 회차별 신규 결함수 (단조감소)

| 회차 | 신규(닫을 수 있는) 결함 | 근본원인 | 조치 |
|------|------------------------|----------|------|
| 1 | **1** — `CrossSheetIdentity.match`가 이미 복수 시트(평면+단면)에 걸친 요소를 외부 counterpart 부재 시 무조건 UNMATCHED+신뢰도 하향 처리 → 이미 식별된 요소를 부당 격하 | 자기증거(self-evidenced) 분기 누락 | source_sheets가 ≥2 시트면 하향 없이 MATCHED 처리 + 테스트 `test_cross_sheet_self_evidenced_multi_sheet` |
| 2 | **0** | — | **고정점 도달** |

단조감소: **1 → 0**.

## 추가된 테스트
- `tests/services/test_cross_sheet.py::test_cross_sheet_self_evidenced_multi_sheet` — 평면+단면 동시 존재 요소는 자기증거로 MATCHED(하향 없음).

## 잔존 forward 항목 (degradation 흡수)
- **SheetRoleAssignment / SemanticElement DB 영속화 배선**: 모델·테이블(0003)·계약 제공. 실제 분석 단위(analysis_id/snapshot_id) 결속 적재는 분석 러너 등장 페이즈(R2)에서 배선. 무음 아님(계약·테이블 존재).
- **SemanticElement ↔ R1.5 변수사전 정합**: semantic_type 태그가 R1.5 산정계층 입력. 실제 소비 계약 정합은 R1.5에서 확정.

## INV 위반 0 체크리스트
- [x] INV-8 합의 라우팅 — SheetRoleResolver는 분류기/표제란/내용 3원 만장일치에서만 role 확정. 불합의/신호결손 → isolated=True, routing 제외. 분류기 vs 표제란 충돌 → flags "conflict".
- [x] INV-9 분류 무가정 — ElementClassifier 불확실 시 UNKNOWN+confidence 하향(임의 타입 금지). CrossSheetIdentity 매칭 실패 시 UNMATCHED(날조 금지).
- [x] INV-1..7(R0 승계) — 결정론, 표면화(MISSING/UNKNOWN/UNMATCHED/isolated), 파라미터 주입(min_confidence/penalty JSON), pydantic 계약, 게이트, 재현성 유지.

## 게이트 결과
- 수용 테스트: **33 passed**(누적; R0.5 AT-1..7 + 보강 포함).
- 마이그레이션: `0003_r0_5` 실DB(review) 반영 — sheet_role_assignment, semantic_element.
- 정적 스캔(INV-3): 하드코딩 0(신규 서비스 포함).
- 린트: ruff `All checks passed`.

**결론: R0.5 DoD 충족 — 고정점 도달.** 다음 = R1.5(법정 산정 계층, 시행령 제119조 산정규칙 + 버저닝).
