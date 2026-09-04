# v4.0 계약층 반영 실행계획 (2026-07-22)

> 입력: `PLATFORM_V4_GAP_ANALYSIS_2026-07-22.md` v2(사용자 제공 — repo 미등재) + 본 세션 코드 실증(8건 표본 검증).
> 위상: 기존 완성도 감사(07-17, 기능 커버리지 91→97%)와 상호보완 — 이번 트랙은 **횡단 "정합성 계약층"**(신뢰·추적·차단·승인)을 세우는 차세대 캠페인. 재작성 아님, 기존 자산 관통.

## 1. 갭 문서 신뢰도 실증 (착수 전 표본 8건)

문서 스스로 "정적 스캔·MISSING=검색 히트 0" 경고 → 실행 우선순위를 지배하는 판정을 코드로 재검증했다.

| # | 문서 판정 | 실증 결과 | 근거 |
|---|---|---|---|
| W1-1 SoD dual-control | MISSING | **확증** — approve()가 승인자 신원 없이 status만 변경 | deliberation-review hitl_queue.py:42-47, hitl_task.py |
| W1-2/P13 승인 상태머신 | 🔴 MISSING | **오판** — site_basis `artifact_status`(DRAFT/ANALYZED/REVIEW_REQUIRED/APPROVED/STALE)+`approve_site_basis`(approved_by 강제)·design_runs DRAFT/APPROVED 실재 | schemas/basis.py:82, site_basis_service.py:360-433, design_run_store.py:259 |
| W1-3 golden false-pass=0 | MISSING | **오판(부분)** — `test_no_false_negative_across_scan`·golden_set.json accuracy==1.0 회귀바·IFC golden 실재. 단 "전문가 확정" 골든은 미비 | tests/test_design_basis.py:127, test_extraction_eval.py |
| W1-4 claim 분류·발행차단 | MISSING | **확증** — Evidence에 confidence만, FACT/CALC/ASSUMPTION 분류·미승인 가정 발행차단 없음 | report/render/model.py:107-116, evidence_contract.py:8-16 |
| W2-1 SourceSnapshot·DLQ | MISSING | **확증** — base_client=캐시+CB+재시도만, raw+checksum 불변저장·dead-letter 없음 | integrations/base_client.py |
| P2 ParcelGraph | 🔴 MISSING | **확증(부분)** — 그래프/articulation 없음. 단 boolean 인접·접도판정·면적가중은 실재(조립 재료 있음) | upzoning_potential.py:207, access_basis_service.py |
| W4-6 CPM | MISSING | **오판** — ES/EF/LS/LF·total_float·주공정선 추출 정식 CPM 실재 | services/construction_ai_service.py:114-150 |
| EVM 완구현 | EXISTS | **확증** — compute_evm(PV/EV/AC/SPI/CPI)+supervision PMBOK식(EAC/ETC) | billing_service.py:58-91, supervision_service.py:8-24 |

**결론: 문서의 부재 판정 신뢰도 ≈62%(5/8 일치).** 오판 공통원인 = 명칭 변형(state machine→artifact_status, CPM→construction_ai_service)·비표준 경로를 정적 키워드 스캔이 놓침. → **모든 Wave 항목은 착수 전 "부재 재확증 스파이크"(tracer/explore) 의무**(§3 원칙).

핵심 진단 자체("기능·엔진은 강하나 횡단 계약층이 비어 있다")는 **유효** — 확증 4건(SoD·claim발행차단·SourceSnapshot·ParcelGraph)이 모두 계약층이고, 오판 3건은 국소 자산이 이미 있어 오히려 "공용화로 관통" 접근을 가능케 한다.

## 2. Phase 0 — 사전 정비 (Wave 1 착수 전)

| ID | 항목 | 내용 | 상태 |
|---|---|---|---|
| P0-1 | **측정 기준 정본 등재** | ✅ **완료(07-22)**: `SPEC_v4_master_execution_prompt_2026-07-22.md`(원본 /mnt/d/플랫폼제작/개발사업AI전주기자동화시스템/gpt_기획,설계안/) + `GAP_v4_analysis_v2_2026-07-22.md` 등재 | 완료 |
| P0-2 | 갭 문서 v3 정정 | ✅ **완료(07-22)**: `ANALYSIS_v4_spec_vs_implementation_2026-07-22.md` §4가 수행 — 18건 실증 반영 재집계(🟢1·🟡10·🟠3·🔴1), 계약 매트릭스 "MISSING 다수"→"PARTIAL 다수(심의엔진 국소 실재)" 정정 | 완료 |
| P0-3 | 스코프 결정 3건 확정 | MEP·소방 / 교통 대기행렬·신호 / 시공단계(W4-7 감리·기성·준공). **권고=문서 제안대로 보류·최소화**(전문 외부지식 의존·플랫폼 적용범위 사전결정 필요). ★사용자 확정 필요 | 대기 |
| P0-4 | 기존 백로그 선행 처리 | GlobalAddressSearch ordinance write측 가드(=Zero-Trust 승격의 국소 선행 사례·W2-4 전초전)·AVM unresolved 혼입·고아 avm_service — 기존 백로그 그대로 | 별도 트랙 |

## 3. 반영 원칙 (전 Wave 공통)

1. **부재 재확증 스파이크**: 각 항목 착수 시 첫 단계 = 해당 "MISSING" 재검증(오판율 38% 실측). 오판이면 공용화·확장으로 전환.
2. **기존 자산 관통·재구현 금지**: site_basis 상태기계·해시체인 원장·calc_ledger·성장루프 게이트 등 국소 패턴을 공용 계약으로 추출(그린필드 금지 — 메모리 교훈).
3. **성장루프 게이트**: 항목별 진단→구현→R1 적대리뷰→REVISE→게이트(tsc·eslint·vitest·pytest 정본 venv)→머지→기록. Wave DoD는 §6.
4. **멀티세션 규약**: 항목별 전용 워크트리+보드 claim. 공유파일(main.py 라우터 등) claim 필수. alembic 마이그레이션은 병합 최후단.
5. **무목업·정직**: 계약층 도입 시에도 미확보 데이터는 정직 표기(UNKNOWN 보존) — 기존 DNA 유지.

## 4. Wave 1 — 거버넌스 골격 (최우선 · 실증 반영 재편)

문서의 W1 5건을 실증 결과로 재편. 순서: **W1-D(측정기) 선행·병렬** → W1-A→W1-B→W1-C 연접(상태머신→SoD→워터마크 소비) · W1-E 독립 병렬. 2트랙 병렬 권장.

| ID | 항목 | 접근 (실증 반영) | 재사용 자산 | 규모 |
|---|---|---|---|---|
| W1-D | golden false-pass=0 **확장** | 신설 아님 — 기존 no_false_negative·golden_set 패턴을 법규엔진(실효FAR·조례·건폐율)으로 확장. **전문가/라이브 확정 케이스를 golden fixture로 승격**(신봉동 56-16 자연녹지 80%, 의정부 224 등 라이브 검증 이력 활용). hard-rule false-pass=0 스위트 | test_design_basis 패턴·golden_set.json·eval 계약 | 소~중 |
| W1-A | 승인 상태머신 **공용화** | 신설 아님 — site_basis artifact_status(5상태·approved_by 강제)+design_runs 승인 흐름을 공용 `ApprovalState` 계약으로 추출 → 보고서/분석 산출물 발행경로에 적용. Gate 테스트: "승인 없이 Published 경로 0" 기계검증 | site_basis_service 상태기계·design_run_store·analysis_ledger | 중 |
| W1-B | SoD dual-control | approve()에 승인자 신원 인자+기록, author≠approver 차단, HITLTask/RuleCandidate에 author/reviewer/approver 필드, 감사원장(해시체인) 연결 | hitl_queue·rule_candidate·audit ledger | 소~중 |
| W1-C | claim schema+발행차단+watermark | Evidence/ReportModel에 claim 분류(FACT/CALCULATION/ASSUMPTION/INTERPRETATION/RECOMMENDATION) 추가, ASSUMPTION 미승인 시 발행차단 게이트, PDF/API 승인등급 워터마크(W1-A 상태 소비). '확정/보장/완벽' 결정론 금지어 게이트 | ReportModel→3렌더러(단일 정본 흐름이라 관통점 1곳)·evidence_contract | 중 |
| W1-E | 법령 위계 precedence resolver | authority/specificity/delegation(상위법·특별법·조례) 상충 해소기 + 상충 rule graph 검출 | reg_graph·calc_rule effective_on·조례 파서 | 중 |

**Wave 1 DoD**: ①각 항목 성장루프 완주 ②무-DB 전체 pytest 무-hang ③해당 v4.0 Gate 조항의 기계검증 테스트 신설(예: W1-A "승인 없이 Published=0") ④배포·인계 기록(옵시디언+보드).

## 5. Wave 2~4 개요 (조정 반영)

- **Wave 2 (추적성·데이터 계약)**: W2-1 Fact Ledger+SourceSnapshot(raw+checksum 불변저장·dead-letter — **확증된 진짜 공백**, VWorld/G2B부터) → W2-2 필드수준 계보+UNTRACED 차단 → W2-3 Stage Handoff bundle 일반화(submission_bundle 확장) → W2-4 Required Data Matrix+Zero-Trust 승격(site_basis 승격게이트의 전역화·P0-4 write가드가 전초전) → W2-5 ParcelGraph(**기존 재료 조립**: adjacency_contiguous+접도판정+면적가중 위에 그래프층·articulation·N-1) → W2-6 CSM 조립체+Risk Register(P×I×D).
- **Wave 3 (얕은 도메인 심화)**: W3-1 수익 KPI(MOIC·Equity IRR·LTV/LTC·break-even·covenant — LTV 70% 하드코딩 교정 포함·golden spreadsheet 대조) / W3-2 3D exact solid Envelope / W3-3 적산 Q등급+back-test / W3-4 최적화 파이프라인 / W3-5 주차 stall·swept path / W3-6 RFI 루프 / W3-7 Rule DSL / W3-8 시장·분양 정밀화. W3-1·W3-2 병렬 가능.
- **Wave 4 (운영·릴리스 성숙도)**: W4-1 CorrectionLog+에러 택소노미 / W4-2 다층 시뮬레이션+오라클 규격 / W4-3 결함예산·릴리스 계약+Tolerance Register / W4-4 Evidence 아티팩트+traceability.csv+검증 지시서 / W4-5 Interface Register+CR / **W4-6 CPM: 스코프 축소** — 엔진 기구현(construction_ai_service) → WBS↔activity↔기성 공통코딩+EVM 기준선 연결만 / W4-7 시공단계 게이트(P0-3 결정 대기).

## 6. 착수 순서·게이트

```
Phase 0 (P0-1·P0-3 사용자 입력) ──▶ Wave 1 (W1-D∥, W1-A→B→C, W1-E∥)
                                        │ DoD 게이트
                                        ▼
                              Wave 2 ──▶ Wave 3 ──▶ Wave 4
```
- 우선순위 근거(문서 §7 동의): 성숙도 M=min(R,C,T,V,O,S)에서 지배 경로가 V(전문가 검증)·R(요구추적)·S(승인·SoD) — 정확히 Wave 1+W4-4에 해당.
- **운영 리스크 명시**: 승인 상태머신·SoD는 "구조"일 뿐, V를 올리려면 **실제 사람 전문가의 승인 행위**가 필요(LLM 페르소나 승인은 V에 불산입 — 문서·실증 일치). 승인자 풀(사용자/외부 전문가) 운영 설계가 코드와 별도로 필요.

## 7. 결정 대기 (사용자)

1. ~~P0-1: v4.0 원본 제공~~ → **해소(07-22)**.
2. **P0-3**: MEP·교통·시공단계 스코프(권고: 보류·최소화 — 문서 제안 채택).
3. **Wave 1 착수 승인**: 승인 시 W1-D·W1-A부터 전용 워크트리로 착수(항목별 보드 claim).

## 8. 추기 (07-22 — 스펙 원문 확보·2차 실증 10건 반영)

상세 = `ANALYSIS_v4_spec_vs_implementation_2026-07-22.md`. 핵심 조정:
- **공통 전략 확정**: "심의엔진(deliberation-review)·site_basis의 검증된 계약 원형 → 공용 추출 → 메인(tax/finance/feasibility/report) 관통". 2차 실증 결과 계약층 다수가 심의엔진에 파일럿 실재(CalcRule·VariableRegistry·Unit enum·CrossStatus.CONFLICT·golden_set) — 문제는 부재가 아니라 전역 승격 미완.
- W1-A: 승인 SM 3원형(site_basis artifact_status·design_runs·run_state DRAFT→HUMAN_APPROVED→LOCKED) 단일 계약화로 재정의.
- W1-C: watermark는 정본 렌더 흐름 1곳 관통(PDF 렌더러 4종 모두 워터마크 0건 실측 — 유일한 순수 MISSING).
- W3-7: 심의엔진 CalcRule/CalcRuleSet 기반 FormulaRegistry 전역화와 병합.
- **W3-9 신설**: Decimal 코어 승격 — 세금(tax_ai_service:98 float)·수지(feasibility) → 분양정산 엔진의 Decimal(ROUND_HALF_UP) 패턴 이식.
- 실질충족 확인(작업 불요): seed 재현성(test_seed_reproducible)·UNKNOWN/CONFLICT 보존(cross_validate=None 보존·CONFLICT 표면화).
