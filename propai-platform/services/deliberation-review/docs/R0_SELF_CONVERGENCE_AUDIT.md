# R0 자기수렴 감사 — 고정점 보고서

페이즈: **R0**(Preflight + 정규 데이터계약 + 사실원장 + 버전축 + 감사로그)
방법: 핸드오프 재추적(생산자→계약→소비자) → 신규 단절/병목 식별 → 근본원인 → 해결 → 테스트 추가 → 재검증. 신규 닫을 수 있는 결함 0 도달 시 종료(A4).

## 회차별 신규 결함수 (단조감소 입증)

| 회차 | 신규(닫을 수 있는) 결함 | 근본원인 | 조치 |
|------|------------------------|----------|------|
| 1 | **1** — `run_preflight()`가 `Snapshot`을 받지만 `assert_synced()` 미호출 → 버전축 불일치 스냅샷으로 Preflight 진행 가능(INV-6 게이트 미배선) | 게이트 진입점과 버전축 정합 검사의 결선 누락 | `run_preflight`에 진입 전 `assert_synced()` 강제 + 테스트 `test_preflight_rejects_unsynced_snapshot` 추가 |
| 2 | **0** | — | **고정점 도달** |

단조감소: **1 → 0**.

## 추가된 테스트
- `tests/acceptance/test_reproducibility.py::test_preflight_rejects_unsynced_snapshot` — 버전축 불일치 스냅샷 → `VersionAxisError`(진행 거부).

## 잔존 환원불가 / forward 항목 (degradation 흡수 확인)
- **audit_record 단계별 발행 배선**: R0에는 "단계 호출"의 주체(분석 러너/파이프라인)가 아직 존재하지 않음. 따라서 `AuditRecord` **계약 + 테이블 + `build_audit_record()` 헬퍼**를 제공하고, 재현 키인 `input_hash`는 이미 `PreflightContext`에 실려 산출됨(AT-8). 실제 단계별 감사 발행은 공급/소비 분리·파이프라인이 등장하는 **R2**에서 배선. → **무음 아님**(계약·키 표면화, 흡수 지점 명시).

## INV-1..7 위반 0 체크리스트
- [x] INV-1 결정론 우선 — R0 전부 결정론, LLM 산출 0.
- [x] INV-2 무음 오판 금지 — 결손=MISSING, 충돌=HELD, 미확정=assumed, 축척불가=PreflightRefused. 전부 표면화.
- [x] INV-3 1차출처/하드코딩 금지 — 허용오차/계수는 `app/data/resolution_parameters.json` 주입(`param()`), AT-9 static_scan 그린(app 소스 하드코딩 0).
- [x] INV-4 계약 강제 — 계층간 pydantic 계약 전용, 미정의 변수 참조 룰 등록 거부(RuleContractError).
- [x] INV-5 게이트 선행 — PreflightGate; 축척 전 chain 실패 시 PreflightRefused(진행 거부).
- [x] INV-6 버전축 단일화 — `Snapshot.assert_synced()` + `run_preflight` 진입 강제.
- [x] INV-7 재현성/감사 — `input_hash`(정규화 입력 sha256) → 동일 입력+스냅샷 동일 결과(AT-8).

## 게이트 결과
- 수용 테스트: **23 passed**(Phase0 AT-1..8 + R0 AT-1..9 + 보강).
- 마이그레이션: `0002_r0` 실DB(propai_db `review` 스키마) 반영 — 7개 테이블(canonical_variable, quantity_ledger, preflight_context, jurisdiction, regulation_snapshot, audit_record, resolution_parameter) 생성 확인.
- 정적 스캔(INV-3): 하드코딩 법정 수치 0.
- 린트: ruff `All checks passed`.

**결론: R0 DoD 충족 — 고정점 도달.** 다음 = R0.5(시트역할 확정 + 요소 의미분류).
