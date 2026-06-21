# 건축설계 라이프사이클 스킬(시스템 2) — 설계문서

- 작성일: 2026-06-21
- 대상: `services/deliberation-review`(엔진) — 시스템 1(인·허가/심의) 실행기·스펙엔진 재사용
- 상태: 설계 승인됨(brainstorming, 사용자 "제안대로 진행") → 구현

## 1. 목적·정합

설계사·도시계획 전문가의 **건축설계 실무 전과정(기획→법규검토→매스→배치→평면→결과물 검증)** 을 런타임 스킬로
엔진에 심어, 에이전트가 단계별 산출물·검증을 실무적으로 만든다. **시스템 1의 아키텍처(접근법 C: 선언적 프로세스
스펙 + 얇은 결정론 실행기)를 그대로 재사용** — 자세한 공유 아키텍처는 `2026-06-21-permit-deliberation-skill-design.md` 참조.

기존 정합(중복 금지): 플랫폼엔 11단계 프로젝트 라이프사이클(부지/설계/공사비/금융/법규/ESG/인허가)·`routers/lifecycle.py`
(시공·감리·리스크)·design_gen 설계도면 멀티모달 인제스천이 존재. 본 스킬은 그 중 **"설계" 단계의 내부 전문
프로세스를 분해·검증**하는 역할(프로젝트 라이프사이클의 설계 단계 완결성·검증을 채워 환류). design_gen 인제스천을 입력으로 활용.

## 2. 재사용 일반화 (process-agnostic)

시스템 1의 실행기/계측/검증은 이미 프로세스-불문에 가깝다. 안전한 별칭 일반화(기존 permit 코드 무파손):
- `contracts/permit_process.py`: `ProcessSpec`(= 기존 PermitProcessSpec 리네임) + `PermitProcessSpec = ProcessSpec` 별칭.
- `contracts/permit_result.py`: `ProcessResult`(= PermitProcessResult) + `PermitProcessResult = ProcessResult` 별칭.
- `services/permit/executor.py`: `run_process`(= run_permit_process) + `run_permit_process = run_process` 별칭.
- StageSpec/CriterionRef/CriterionKind/StageResult/CriterionResult는 이미 일반 명칭 — 그대로.
→ permit·design 두 스펙이 동일 코어를 공유(코드 무중복). 영속도 동일 `permit_process_run` 테이블 재사용(spec_id로 구분).

## 3. 설계 라이프사이클 스펙 (신규 데이터)

`services/design/design_spec_loader.py` — `load_design_spec() -> ProcessSpec`(spec_id="design-default"). 6단계:
1. `programming`(기획) — required_inputs: use_zone, program(용도·소요면적). 완결성 기준.
2. `legal_precheck`(법규 사전검토) — QUANTITATIVE far/bcr/height(reg SSOT 여유) — 시스템1 measure 재사용.
3. `massing`(매스 스터디) — required_inputs: 가능 볼륨·층수(완결성).
4. `site_layout`(배치) — QUANTITATIVE 일조/인동/주차 가능 + 완결성. predecessors=[massing].
5. `floor_plan`(평면/면적) — required_inputs: 전용/공용·세대·면적표(완결성). predecessors=[site_layout].
6. `deliverable_verify`(결과물 검증) — 시스템1 검증(finding.gated_status) 재사용. predecessors=[floor_plan].

법정 한도는 reg SSOT 참조(INV-3). 단계 추가·조정 = 스펙만 변경.

## 4. 입력 완결성 계측 (신규)

설계 단계는 "법규 부합"뿐 아니라 **"필요 산출물이 갖춰졌는가(완결성)"** 가 핵심. `services/design/completeness.py`:
- 단계 required_inputs 중 입력에 존재하는 비율 → COMPLETE/PARTIAL/MISSING(무음 금지, 결손 표면화).
- 정량 기준은 시스템1 measure_quantitative(비율 vs SSOT) 재사용, 정성은 measure_qualitative 재사용.
- 단계 종합 = worst-of(완결성 + 부합도 + 검증). 생성(매스/세대수)은 Phase 1 비범위 — 완결성/검증만.

## 5. 노출·영속

- `services/design/design_executor.py` 또는 run_process 직접 호출(design 스펙 주입) → ProcessResult(spec_id="design-default").
- 라우트 `api/routes/design_routes.py`: POST /api/v1/design/process(AnalysisInput 또는 run_id), GET /api/v1/design/process/{run_id}, GET /api/v1/projects/{id}/design. require_token·#8a 격리. 영속=permit_store 재사용(spec_id 구분) 또는 동일 테이블.
- 플랫폼: 후속(설계 SpecialistAgent) — Phase 1은 엔진 라우트까지.

## 6. 불변식·품질

결정론(스펙 버전드+순수 매핑) · INV-3(한도 SSOT) · INV-13(AnalysisResult 소비 read-only) · 무음 금지(완결성 결손→MISSING/PARTIAL 표면화) · #8a 격리 · 설명가능성(calc_trace) · 각 증분 9.5 적대 게이트.

## 7. 증분 계획

- INC-DL1: process-agnostic 별칭 일반화(ProcessSpec/ProcessResult/run_process) + 회귀 그린.
- INC-DL2: design_spec_loader(6단계) + completeness 계측 + 결정론 테스트.
- INC-DL3: design 라우트(process/run/project) + 영속 재사용 + smoke.
- (후속) DL4 설계 SpecialistAgent(플랫폼), Phase 2 생성형(매스/세대수 — design_gen 정합).
- 각 INC = 9.5 적대 게이트(HIGH 0) 후 커밋·푸시.

## 8. 비범위(YAGNI)

- 생성형 설계(매스/세대수/배치 자동 생성) — Phase 2(design_gen 정합).
- 프로젝트 라이프사이클 프론트/공사·금융 단계 — 기존 인프라 소관(본 스킬은 "설계" 단계 내부).
