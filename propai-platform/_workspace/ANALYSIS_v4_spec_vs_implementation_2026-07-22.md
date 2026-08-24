# v4.0 마스터 스펙 원문 vs 현 구현 비교분석 (2026-07-22)

> 입력 정본(이번에 등재): `SPEC_v4_master_execution_prompt_2026-07-22.md`(원본 = /mnt/d/플랫폼제작/개발사업AI전주기자동화시스템/gpt_기획,설계안/사통팔땅_IDE_플랫폼구축_마스터실행프롬프트_v1.0(1).md — 파일명은 v1.0이나 내용 버전은 **v4.0**·1,395행) · `GAP_v4_analysis_v2_2026-07-22.md`(갭분석 v2 원본).
> 실증 기반: 1차 8건 + 2차 10건 = **총 18건 file:line 코드 검증** (PLAN_v4_contract_layer_execution §1 + 본 문서 §4).

## 1. 스펙 정체 분석 (추가 분석)

- **성격**: 완성형 설계서가 아니라 **IDE 에이전트 실행용 프롬프트 패키지** — MODE(BOOTSTRAP/IMPLEMENT/VERIFY_RELEASE/RESUME) 프로토콜, 실행변수(TECH_POLICY: existing-first), docs/evidence/Px 증거 규격, make 지시선, 릴리스 판정 YAML 템플릿까지 포함.
- **★현 플랫폼과의 호환 조항**: 스펙 스스로 "기존 구조·코딩규칙 보존, 합리적 근거 없이 프레임워크 교체 금지, 기존 구현 우선 재사용"(절대원칙 1·3, 권장구조는 '기존 구조가 없으면') — **우리의 재구현 금지·기존자산 관통 원칙과 정합**. packages/* 분리 구조로 이식할 필요 없음.
- **철학 정합**: 절대원칙 12 중 6·7·8·9·11(UNKNOWN 보존·법정오차 설계여유 금지·테스트 회피 금지·목업 금지·과장 완료선언 금지)은 이미 플랫폼 DNA(무목업·정직·완결게이트)와 일치. v4.0은 이를 **기계집행 계약**(차단 게이트·상태머신·등급 필드)으로 승격하라는 요구.
- **자기제한 명시**: "완성 판정은 절대적 무결이 아니라 명시된 범위(SCOPE-BOUND VERIFIED)"(:1108) · "실데이터·전문가 검증 없으면 V≤0.50"(:1294) — 코드만으로 M을 못 올린다는 운영 의존성을 스펙이 스스로 규정.

## 2. 갭분석 v2 충실도 판정 (스펙 원문 확보 후 대조)

- **전사(스펙 표현) = 충실**: 권위계층 6단(:63)·UNTRACED 발행차단(:168)·NOT_READY(:947)·ORPHAN_TASK(:977)·M0~M5(:716)·E0~E4(:981)·S0~S3(:1096)·V캡(:1294) 전부 스펙에 실재 — 갭 문서가 스펙을 왜곡·과장하지 않음.
- **판정(코드측 부재)의 신뢰도 = 62%**: 18건 실증 중 오판·과소평가 다수(§4). 공통 원인 = **심의엔진(`services/deliberation-review`)과 legacy 경로(`apps/api/services/`)를 정적 키워드 스캔이 누락**.

## 3. ★구조적 발견 — "계약층은 무배관이 아니라 국소 배관"

18건 실증의 일관된 패턴: v4.0 계약 요소의 **원형이 심의엔진에 이미 파일럿 구현**되어 있다.

| v4.0 계약 | 심의엔진 내 원형 |
|---|---|
| FormulaRegistry | contracts/calc_rule.py(CalcRule·CalcRuleSet.effective_on)+canonical_vars.py(VariableRegistry: unit·required) |
| 단위 타이핑 | contracts/enums.py Unit enum(미정의 단위 pydantic 거부) |
| CONFLICT 보존 | contracts/cross_validation.py(CrossStatus.CONFLICT·dissent[]·needs_review) |
| golden 회귀 | data/eval/golden_set.json+test_extraction_eval(accuracy==1.0 바) |
| HITL 승인큐 | supply/hitl/hitl_queue.py(단, SoD 부재 — 1차 확증) |
| 데이터 상태 | RecordStatus.MISSING("무음 skip 금지") |

메인 플랫폼에도 국소 배관 존재: site_basis 승격게이트(artifact_status 5상태·approved_by 강제), design_runs DRAFT→APPROVED, 해시체인 원장, CalcTrace, seed 재현(test_seed_reproducible), cross_validate(trusted_value=None 보존), CPM(construction_ai_service), EVM(billing+supervision).

**따라서 정확한 문제 정의는 "계약층 부재"가 아니라 "계약층의 전역 승격·관통 미완"** — 실행 전략은 심의엔진·site_basis의 검증된 계약을 공용 계약으로 추출해 메인 tax/finance/feasibility/report에 관통시키는 것.

## 4. 종합 비교표 (스펙 축 × 현 구현 — 18건 실증+메모리 근거)

범례: ● 실질충족 · ◐ 부분(국소 실재·전역 미승격) · ○ 부재

| 스펙 축 | 판정 | 실측 요지 |
|---|---|---|
| 절대원칙 12·정직성 DNA | ● | UNKNOWN/CONFLICT 보존 EXISTS(trust.py cross_validate=None 보존·CONFLICT 표면화)·무목업·게이트 문화 |
| 권위계층 6단 enforcement | ◐ | 2-티어 신뢰경계만. LLM 그라운딩(할루시네이션 가드·_has_source)은 국소 |
| Zero-Trust 7구역·SourceSnapshot·DLQ | ○ | base_client=캐시+CB+재시도만(1차 확증). raw+checksum 불변저장·dead-letter 없음 |
| 필드수준 계보·UNTRACED 차단 | ◐ | 분석-해석 DAG(lineage)·해시체인 원장 존재. 원본bytes 역추적·발행차단 없음 |
| Stage Handoff bundle | ◐ | submission_bundle(manifest·sha256·provenance) 존재. 일반화(bundle_id/parent/expiry/소비검증) 미완 |
| FormulaRegistry·계산규격 | ◐ | 심의엔진 CalcRule+VariableRegistry+calc_params(버전·단위·근거조문). 메인 tax/finance 미등록. JΣJᵀ 오차산법 없음 |
| Decimal | ◐ | 분양·정산 엔진 Decimal(ROUND_HALF_UP). **세금(tax_ai_service:98)·수지(feasibility_service)는 float** |
| 단위검증(dimensional) | ◐ | Unit enum·평환산·ToleranceTable(mm). 전역 하드블록 없음 |
| Required Data Matrix | ◐ | site_basis P0게이트·접도 BLOCKED·canonical_vars required. 전역 데이터등급 매트릭스 없음 |
| Maturity M0~M5·Evidence E0~E4 | ◐ | artifact_status 5상태 사다리+confidence 3등급 실재. M/E 스키마 자체는 없음 |
| claim 분류·발행차단 | ○ | Evidence={value,basis,source,confidence}뿐(1차 확증) |
| 승인등급 watermark | ○ | 승인 상태모델 완비(run_state DRAFT→HUMAN_APPROVED→LOCKED), **PDF 렌더러 4종 모두 워터마크 0건** — 단, 구현은 정본 렌더 흐름 1곳 관통으로 축소 가능 |
| SoD dual-control | ○ | hitl approve() 승인자 신원 미기록(1차 확증) |
| 승인 상태머신(P13) | ◐ | site_basis+design_runs 실재(1차 반증). 보고서/전 산출물 일반화·전문가 정족수 미완 |
| Interface Register·변경영향 | ◐ | design_change_predictor(실코드·est_impact 정성)+staleness+change_forecast. 형식 매트릭스·의존전파 증명 없음 |
| Tolerance Register 4범주 | ◐ | 측량공차표(coordinate_contract)+국소 tol 산재. 법정한계/모델오차/측량/반올림 분리 레지스터 없음 |
| Seed 재현성 | ● | seed 1급필드→결정론 RNG→**test_seed_reproducible**(2차 확증) |
| golden false-pass=0 | ◐ | no_false_negative 스위트·golden_set 회귀바 실재(1차 반증). "전문가 확정" 골든 미비 |
| CPM·EVM(5D) | ◐ | 둘 다 실구현(1차 반증·확증). WBS↔activity↔기성 공통코딩·ITP·Closeout 없음 |
| 시뮬레이션 L0~L6·오라클 규격 | ◐ | MC(seed)·shadow·stress 일부. 계층 규격·오라클 명시·S1~S12 스위트 없음 |
| 성장루프·결함예산 S0~S3·릴리스 계약 | ◐ | 성장루프 실질 구현(재현테스트·R1·게이트·rollback). 결함예산 형식화·SCOPE-BOUND VERIFIED·릴리스 YAML 없음 |
| ParcelGraph(P2) | ◐→○ | 그래프 구조 없음. 재료(인접 boolean·접도판정·면적가중)는 실재 |

**부합도 재집계(P0~P14, 실증 반영)**: 갭 v2의 🟢1·🟡9·🟠3·🔴2 → **🟢1(P4)·🟡10(P13 승격)·🟠3·🔴1(P2)**. 계약 매트릭스는 "MISSING 다수"에서 "**PARTIAL 다수(심의엔진 국소 실재)**"로 정정.

## 5. 실행계획 조정 (PLAN_v4_contract_layer_execution 델타)

1. **P0-1 완료**: 스펙+갭 v2 정본 등재(본 문서 헤더). **P0-2(갭 v3 정정)는 본 문서 §4가 수행**.
2. **공통 전략 확정**: "심의엔진/site_basis의 검증된 계약 → 공용 추출 → 메인 관통"을 전 Wave 표준 통로로 명시(그린필드 금지의 구체화).
3. Wave 항목 조정:
   - W1-C(claim+watermark): watermark는 정본 렌더 흐름 1곳(report/render) 관통으로 규모 축소. run_state·artifact_status 소비.
   - W1-A(승인 SM 공용화): 대상에 run_state.py(DRAFT→HUMAN_APPROVED→LOCKED)도 통합 — 3원형(site_basis·design_runs·run_state)의 단일 계약화.
   - W3-7(Rule DSL)은 심의엔진 CalcRule/CalcRuleSet를 기반으로 — FormulaRegistry 전역화와 병합.
   - **신규 W3-9 (Decimal 코어 승격)**: 세금(tax_ai_service)·수지(feasibility) float→Decimal — 분양정산 엔진의 기존 패턴 이식. 정밀도 결함 클래스 선제 봉합.
   - W2-4(RDM): canonical_vars required 패턴 재사용 명시.
4. 우선순위 불변: Wave 1(SoD·승인SM 공용화·claim/watermark·golden 전문가화·법령위계)이 여전히 M=min의 지배축(V·S) 직결.

## 6. 결론

- v4.0 스펙은 현 플랫폼과 **철학적으로 정합**하고(existing-first·정직성), 요구하는 것은 재작성이 아니라 **이미 곳곳에 검증된 계약 원형의 전역 승격**이다.
- 갭 v2의 방향(계약층 우선)은 유효하나, 18건 실증으로 **작업 규모는 체감 축소**(신설→승격이 다수)·**정밀도는 상승**(진짜 공백 = SoD·SourceSnapshot/DLQ·claim발행차단·watermark 렌더·ParcelGraph 그래프층·M/E 등급 스키마).
- 다음 실행: PLAN §7 결정 대기 2건(스코프 3건 확정·Wave 1 착수 승인) — P0-1은 해소됨.
