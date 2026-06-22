# 인·허가/심의 실무 스킬 — 설계문서 (접근법 C)

- 작성일: 2026-06-21
- 대상 저장소: `services/deliberation-review` (심의분석엔진) + 플랫폼 BFF/living-agent 노출
- 상태: 설계 승인 대기(brainstorming) → 승인 시 writing-plans로 구현계획 수립

## 1. 목적·배경

설계사·도시계획 전문가의 **개발사업 인·허가/심의 실무 전과정**을 런타임 "스킬"로 엔진에 심어, 플랫폼 에이전트가
더 실무적인 결과물(인허가 로드맵 + 심의 계측 스코어카드 + 단계별 대응 패키지 + 검증)을 산출하게 한다.

현황(실제 코드 확인):
- 심의엔진은 **검증(review) 전용** 11페이즈 파이프라인 — 주어진 설계를 규제에 대조해 구획 리포트 산출
  (`apps/api/app/services/pipeline/analysis_pipeline.py`).
- 플랫폼은 `SpecialistAgent`(결정론 tool→prior→LLM+citation_gate→ledger) + `AgentCoordinator.dispatch`,
  도메인 레지스트리(permit/zoning/far/cost/market) 보유(`apps/api/app/services/agents/registry.py`).
- **인·허가 단계 절차·심의 계측·결과예측은 부재** — 이 스킬이 그 공백을 채운다.

결정사항(brainstorming):
- 결과물 성격 = **프로세스 오케스트레이션 + 단계검증**(Phase 1) → **생성형/결과예측**(Phase 2) 단계적.
- 선행 시스템 = **인·허가/심의**(검증 백본). 이후 설계 라이프사이클(시스템 2)이 동일 실행기 재사용.
- 첫 완결 범위 = **건축심의 + 건축허가 중심**(+ 직접 연계 의제심의), 아키텍처는 개발사업 전체로 확장 가능.
- 아키텍처 = **C: 선언적 프로세스 스펙(데이터) + 얇은 결정론 실행기**(엔진의 규제 SSOT 패턴과 정렬).

## 2. 아키텍처 개요

```
입력(도면·사업정보) → [프로세스 스펙 SSOT(데이터)] → 프로세스 실행기(얇은 결정론)
   → 단계별 반복{ 엔진 분석 호출(11페이즈 재사용) → 심의 계측 → 대응 패키지 → 검증 게이트(FinalGate 재사용) }
   → PermitProcessResult → 프로젝트 DB 영속(project_id·per-field 재사용) + BFF/심의 SpecialistAgent 노출
   → (Phase 2) 단계별 결과예측 슬롯
```

핵심 원칙: **"절차를 데이터로"**. 인허가·심의 전과정을 버전드 선언 데이터(프로세스 스펙)로 만들고, 실행기는
스펙을 읽어 기존 엔진 능력을 소비/계측/검증만 한다. 단계 추가·법 개정 = 스펙/SSOT 버전 갱신(코드 무변경).

## 3. 구성요소

### 3.1 프로세스 스펙 (SSOT · 선언 데이터 = "스킬" 본체)

pydantic 계약으로 정의하고 버전드 데이터(JSON 시드 + snapshot 결속, 규제 SSOT와 동일 방식)로 적재.

```
PermitProcessSpec : spec_id, version, effective_date, applicability(사업유형·용도지역 조건), stages: StageSpec[]
StageSpec         : stage_id, name, stage_type(본허가|의제심의), predecessors[stage_id],
                    required_inputs[str], criteria_refs[CriterionRef], deliverables[str],
                    verification: VerificationSpec, authority(관계기관), submittals(제출물),
                    outcome_predictor: str|None   # Phase 2 슬롯(Phase 1=None)
CriterionRef      : criterion_id, kind(QUANTITATIVE|QUALITATIVE), ssot_ref(규제 SSOT variable_id 또는 조문),
                    measure(부합도 산식 식별자), basis_article
```

- 법정 한도(건폐/용적/높이/일조/주차 등)는 **스펙에 수치로 박지 않고 규제 SSOT를 참조**(INV-3 준수).
- 첫 스펙(기본 1종): 건축허가 + 보편 의제심의(경관·교통·환경·재해 — 해당 조건 시 applicability로 on/off).

### 3.2 프로세스 실행기 (얇은 결정론 소비자)

`run_permit_process(analysis_result, spec) -> PermitProcessResult`

1. applicability로 적용 단계 선별 → predecessors 위상정렬(결정론 순서).
2. 단계별:
   - required_inputs 확보 검사 → 결손 시 stage status=HELD/NEEDS_INPUT (무음 금지, 표면화).
   - 기준별 계측:
     - QUANTITATIVE: 엔진 산출값(legal_quantities/findings/sim_metrics를 variable_id로 조회) ÷ 규제 SSOT 한도
       → 부합/조건부/미흡 + margin. calc_trace = {measured, limit, basis_article, source}.
     - QUALITATIVE: L3-C QualAssessment 등급 매핑(없으면 HELD).
   - StageScore = 기준 계측 집계(게이팅=worst-of + 기준별 상세 보존).
   - 대응 패키지: 미흡·조건부 기준 → 보완 가이드(근거조문, 규제 SSOT) + 예상 쟁점.
   - 검증: 엔진 FinalGate/L5 재사용 → CONFIRMED/NEEDS_REVIEW/BLOCKED.
3. PermitProcessResult 조립(로드맵 + 단계 결과 + overall).

설계 불변: 실행기는 **재계산하지 않고 AnalysisResult를 소비**한다(SSOT 일관 — 한 번 분석, 여러 관점). INV-13 read-only.

### 3.3 심의 계측 (Measurement)

각 기준의 부합도를 정량/정성으로 산정하며 모든 점수에 `calc_trace`/`legal_refs`(설명가능성 표준, land/sim/legal_calc와
동일) 동반 — 도출이유·법령본문·한계·정량근거를 함께 보존. 부합도 밴드(여유/근접/초과)는 측정용 운영 상수로
명명·문서화(법정 파라미터 아님; static_scan 충돌 시 allowlist).

### 3.4 출력 계약

```
PermitProcessResult : spec_id, spec_version, run_id,
                      roadmap(단계순서·의존·관계기관·제출물),
                      stages: StageResult[],
                      overall(종합 부합도 + 최악 검증상태)
StageResult         : stage_id, name, status(DONE|HELD|NEEDS_INPUT), score(StageScore),
                      criteria: CriterionResult[], deliverables_status, verification_status,
                      remediation(대응 패키지), issues(예상 쟁점), authority, submittals
CriterionResult     : criterion_id, kind, measured, limit, conformance(부합|조건부|미흡), margin,
                      calc_trace, legal_refs, basis_article
```

### 3.5 영속

`PermitProcessResult`를 **프로젝트 DB**(project_id·organization_id)에 원자 저장 — 우리가 구축한 per-field/project
패턴 재사용. 신규 테이블: `permit_process_run`(blob + 메타, CommonMixin) + (선택) `permit_stage_result`/
`permit_criterion_score` per-stage 행. alembic 신규 마이그레이션 1건(0016). 조회: run_id + 프로젝트 스코프.

### 3.6 노출 (API / 에이전트)

- 엔진 라우트:
  - `POST /api/v1/permit/process` (require_token; X-Tenant-Id/X-Project-Id) — 본문은 둘 중 하나:
    (a) AnalysisInput → 11페이즈 실행 후 프로세스, 또는 (b) {run_id} → 기존 분석 재사용(재계산 0).
    → run_permit_process → 영속 → PermitProcessResult
  - `GET /api/v1/permit/process/{run_id}` (테넌트 격리)
  - `GET /api/v1/projects/{project_id}/permit` (프로젝트 스코프 집계)
- 플랫폼: BFF 프록시 + `심의`(deliberation) SpecialistAgent를 registry.py에 등록(결정론 tool=엔진 호출) →
  AgentCoordinator.dispatch("심의")로 living-agent가 산출.

### 3.7 데이터 동역학·소싱 모델 (정적 vs 실시간 — 핵심 보완)

원칙: **하드코딩(정적)도, 순수 실시간(무버전)도 부적합. "버전드 동적 SSOT"가 정답**이며, 엔진이 이미 그 골격을
보유한다. 실시간 소스 → 수집·다출처 교차검증(출처·as-of·confidence) → 버전드 스냅샷(effective_date·snapshot_id)
→ 분석/심의는 스냅샷 결속(재현·감사·결정론). 드리프트 감지 → 신규 스냅샷 → 재분석(유동성 대응).

재사용 자산(실제 코드):
- `apps/api/app/adapters/network.py` — LiveNetwork 단일 choke + allowlist(law.go.kr·elis.go.kr·eum.go.kr) + LIVE_NETWORK 게이트.
- `apps/api/app/tasks/reconcile_tasks.py` — reconcile_mirror: 라이브 해시 드리프트 → 신규 스냅샷 → reanalyze.
- `apps/api/app/contracts/cross_validation.py` — 다출처 교차검증 + is_stale·data_vintage·needs_review(staleness 표면화).
- `contracts/versioning.py` — Snapshot.assert_synced(버전축 동기), 분석의 snapshot_id 결속(재현).
- `tools/static_scan.py` — INV-3(법정 수치 하드코딩 0) AST 강제.

4축 처리 방식:
- 법규변경: reconcile_mirror(국가법령 law.go.kr) 재사용 — 스펙은 SSOT 참조라 개정이 자동 반영.
- 지자체별: JurisdictionModel + StageSpec.applicability로 조례 스코프. **자치법규(elis) 어댑터를 Phase 1에 포함**
  — LiveNetwork allowlist(elis.go.kr) 재사용, 지자체별 조례를 버전드 스냅샷에 결속·교차검증(국가법령 reconcile 패턴 차용).
- 개발방식별: applicability(사업유형)로 단계·기준 선택 — 데이터 구동(하드코딩 아님).
- 시장상황: **컴플라이언스 판정과 분리.** 시장 데이터(공시지가/시세/금리)는 결정론 심의 판정을 오염시키지 않도록
  **예측-only 피드**로 Phase 2 결과예측·사업성에만 as-of·confidence 동반 투입(컴플라이언스 경로와 격리).

따라서 본 스킬은 신규 정적 테이블을 만들지 않고 **버전드 동적 SSOT에 criteria_refs로 결속**한다(정적 스냅샷의
재현성 + 실시간 소싱의 최신성 동시 확보).

소싱 범위 결정(2026-06-21): Phase 1 = 스냅샷 골격 + 점진 소싱 + **자치법규(elis) 어댑터 포함**. 시장 예측 피드는
Phase 2(예측-only). **결정 원칙: 모든 선택은 결과물 신뢰성·정확성·안전성 + 플랫폼 가치를 높이는 방향**(사용자 지침)
— 그래서 순수 실시간이 아닌 버전드 동적 SSOT(재현+최신 양립), 하드코딩 금지(INV-3), 결정론·설명가능성 우선.

## 4. 불변식·품질

- **결정론**: 스펙 버전드 + 실행기 순수 매핑 → 동일 입력+스펙 = 동일 결과(input_hash/snapshot 결속).
- **INV-3**: 법정 수치 하드코딩 0 — 한도는 규제 SSOT 참조. 측정 밴드만 명명 운영 상수.
- **INV-13**: 실행기는 AnalysisResult 소비 read-only — 재계산·라이브 호출 없음(live_call_scan 0 유지).
- **무음 금지**: 입력/기준 결손 → HELD/NEEDS_INPUT으로 표면화(엔진 skipped/preflight_blocked 패턴).
- **#8a 테넌트 격리**: 모든 행 project_id/organization_id, 조회 테넌트 필터.
- **설명가능성**: 모든 계측·검증 산출에 calc_trace/legal_refs.
- **9.5 게이트**: 각 구현 증분을 다렌즈 적대 게이트(HIGH 0)로 통과 후 커밋·푸시.

## 5. 테스트 전략

- 스펙: 로딩·버전·applicability 필터(사업유형/용도지역).
- 실행기: 결정론 매핑(엔진 결과→단계 점수), 위상정렬, HELD on 결손.
- 계측: 정량 부합도 경계(부합/조건부/미흡), 한도=SSOT(하드코딩 부재), 정성 등급 매핑.
- 검증 재사용: FinalGate 상태 전파.
- 영속: 프로젝트 DB 라운드트립 + 테넌트 격리(store 레벨).
- 라우트 smoke: 인증(401)·경로검증(422)(라운드트립은 store 레벨, 교차 이벤트루프 회피 — repo 패턴).
- 게이트: INV-3·INV-13(live_call_scan 0)·ruff·전체 스위트 그린.

## 6. 단계별 구현 계획(개요 — 상세는 writing-plans)

- INC-PD1: 프로세스 스펙 계약 + 기본 스펙(건축허가+의제) 시드 + 로더(버전·applicability) + 테스트.
- INC-PD2: 실행기 + 심의 계측(정량/정성) + 대응 패키지 + 검증 재사용 + 결정론 테스트.
- INC-PD3: PermitProcessResult 영속(테이블+alembic 0016) + 프로젝트 DB 통합 + 라운드트립/격리 테스트.
- INC-PD4: 엔진 라우트(process/run/project) + smoke.
- INC-PD5: BFF 프록시 + `심의` SpecialistAgent 등록.
- INC-PD6: 자치법규(elis) 어댑터 — 지자체 조례 실소싱(LiveNetwork allowlist elis.go.kr 재사용) + 버전드 스냅샷
  결속 + 교차검증/드리프트(reconcile 패턴). 인터페이스 → 실연동(키·운영 준비 시 LIVE_NETWORK 점등). **Phase 1 포함**.
- 각 INC = 9.5 적대 게이트 통과 후 커밋·푸시.

## 7. Phase 2 / 시스템 2 확장점

- **결과예측(Phase 2)**: StageSpec.outcome_predictor 슬롯 — 휴리스틱→pluggable ML(플랫폼 risk_predictor 패턴),
  단계별 승인/조건부 확률·예상 보완사이클. 골격 재구조화 없음.
- **설계 라이프사이클(시스템 2)**: 동일 실행기·스펙엔진 재사용 — 다른 프로세스 스펙(기획→법규검토→매스→배치→
  평면→검증)만 추가. 실행기는 프로세스-불문(process-agnostic).

## 8. 비범위(YAGNI)

- 생성형 설계(매스/세대수/배치 자동 생성) — 시스템 2 Phase 2.
- 개발사업 전체 인허가(사업계획승인·지구단위계획 등) — 스펙 확장으로 후속.
- 실 ML 결과예측 모델 학습 — 데이터/배포팀 협업(Phase 2).
