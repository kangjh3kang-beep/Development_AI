# R1.5 자기수렴 감사 — 고정점 보고서

페이즈: **R1.5**(법정 산정 계층 — 시행령 제119조 면적/높이/층수 + 산정규칙 버저닝)
키스톤: WB1(기하면적 ≠ 법정면적) 해소 → 결정론 판정의 무결점 입력 확보.
선행: R0, R0.5. A절 프리앰블 재사용 + INV-10(calc_trace 추적)/INV-11(산정 파라미터 주입)/INV-12(분류 신뢰도 상속·HELD).

## 회차별 신규 결함수 (단조감소)

| 회차 | 신규(닫을 수 있는) 결함 | 근본원인 | 조치 |
|------|------------------------|----------|------|
| 1 | **1** — `CalcEngine.compute`가 `snapshot`을 받지만 `assert_synced()` 미호출 → 버전축 불일치 스냅샷이 법정 산정에 유입 가능(INV-6) | 산정 진입점과 버전축 정합 검사 결선 누락(R0 감사와 동일 계열) | compute 진입 시 snapshot.assert_synced() 강제 + 테스트 `test_calc_engine_rejects_unsynced_snapshot` |
| 2 | **0** | — | **고정점 도달** |

단조감소: **1 → 0**.

## 추가된 테스트
- `tests/services/test_calc_version.py::test_calc_engine_rejects_unsynced_snapshot` — 버전축 불일치 스냅샷 → 산정 거부(VersionAxisError).

## 핵심 명제 재확인 (감사 D절)
"결정론 무결점 = 법정 산정값 정확성" 명제는 **입력 분류 정확도에 종속**된다. 본 구현에서 불확실 경로는 전부 HELD로 귀결됨을 확인:
- 입력 CalcElement에 UNKNOWN 포함 또는 min(confidence) < `calc_min_input_confidence` → `status=HELD`(무음 계산 금지).
- 산정 confidence = 입력 분류 confidence 최솟값 상속(INV-12).
- 모든 값 보유 산정값은 calc_trace(rule_id/excluded_elements/basis_article) 동반, 부재 시 `emit`가 `CalcTraceMissing`(INV-10).

## 잔존 forward 항목 (degradation 흡수)
- **필수 요소 '부재' 감지**: 엔진은 제공된 elements에 대해서만 판단. "있어야 할 요소타입이 아예 없음"의 감지는 R0.5 routing(시트 결손→MISSING)·변수 required 플래그가 담당. R3 게이팅에서 결합.
- **LegalQuantity DB 영속화 + audit 연계**: 모델·테이블(0004) 제공, 분석 단위 적재는 R2 파이프라인에서 배선.
- **R1.5 → R3 핸드오프**: LegalQuantity(변수사전 id 바인딩 + status + confidence + calc_trace)가 R3 판정엔진 입력. HELD/저신뢰는 R3 게이팅으로 전파.

## INV 위반 0 체크리스트
- [x] INV-10 산정근거 추적 — 전 산정값 calc_trace 동반, emit 강제.
- [x] INV-11 산정 파라미터 주입 — 제외 임계(발코니 깊이/처마 길이/옥탑 비율)는 `app/data/calc_params.json`·룰셋·override 주입. legal_calc 소스 static_scan 0(AT-3) + 전역 AT-9 0.
- [x] INV-12 분류 신뢰도 상속 — confidence 상속 + UNKNOWN/저신뢰 → HELD.
- [x] INV-1..9(승계) — 결정론, 표면화, 계약(변수사전 1:1), 버전축(산정규칙↔법규셋 axis), 재현성 유지.

## 게이트 결과
- 수용 테스트: **44 passed**(누적; R1.5 AT-1..8 + 변수사전 1:1/registry 거부/스냅샷 동기화 보강 포함).
- 마이그레이션: `0004_r1_5` 실DB(review) 반영 — legal_quantity, calc_rule, calc_rule_set, calc_param.
- 정적 스캔(INV-3/11): 하드코딩 법정 수치 0(legal_calc 포함).
- 린트: ruff `All checks passed`.

**결론: R1.5 DoD 충족 — 고정점 도달.** 다음 = R2(공급/소비 분리 + HITL SLA + HWP 파이프 + 외부API fallback/법규셋 versioned 미러).
