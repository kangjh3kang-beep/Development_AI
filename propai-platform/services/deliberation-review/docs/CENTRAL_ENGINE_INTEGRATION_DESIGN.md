# 중심 엔진 통합 설계 (Central Analysis Engine Integration Design) — v2

> 작성: 2026-06-18. 근거: 9-에이전트 통합설계 워크플로(플랫폼 50+ 분석 서브시스템 5클러스터 매핑 → 3안 설계 → 심사) + 4-렌즈 코드대조 검증 워크플로(정정 HIGH 7 반영).
> 상태: **설계문서(코딩 전 검토용)**. 구현은 별도 트랙(trust_infra 기반 신규 통합 워크트리)에서 단계별 착수.
> 결정(2026-06-18): 전환방식=**상세 설계 먼저**, 협업도구=**Workflow**, 작업브랜치=**trust_infra 기반 신규 통합 워크트리**.
> **경로 규약**: 엔진 코드 인용은 모두 `services/deliberation-review/apps/api/app/` 하위(이하 "엔진 …"으로 축약). 플랫폼은 `apps/api/...`·`apps/web/...`.

## 0. 요약 (TL;DR)

심의/설계도면 자동분석 엔진을 플랫폼의 **분석 커널(결정론 판정·정량·설명 두뇌)**로 삼고, 플랫폼의 흩어진 분석 기능을 그 위의 **얇은 어댑터(입력 수집·도메인 프레이밍·표현)**로 점진 재편한다.

- **방식**: 점진 어댑터(additive, **엔진 코드 무수정 목표**, 엔진 전체 스위트 무회귀 — 현 419 테스트 함수, CI 기준선)를 골격으로, 통합안의 *circuit-breaker/degrade/shadow*와 척추안의 *3경계(추출/판정/라이브공급) 분리* 접목.
- **판정 SSOT 전환**(플랫폼 8엔진 심사 → 엔진 R3+FinalGate)은 **반드시 shadow(비교만)→authoritative 승격** 순서. 엔진 미연결 시 **무음 폴백 금지 → `NEEDS_REVIEW`+사유**.
- **효과**: 중복 제거 + "중심 한 번 개선 → 전 분석 향상". 단 이는 **도메인별 마이그레이션의 종착점**이며 라우팅·계약 어댑터 자체가 일회성 작업(회귀 안전 필수)이다(정직).
- ⚠️ **"엔진 무수정"의 한계**: 테넌트 격리·운영 영속(아래 §9 R-멀티테넌시)에서 엔진 수정이 필요할 수 있음 — 그 지점은 별도 Phase로 명시하고 무수정 가정을 깨는 비용을 인정한다.

## 1. 배경 — 현 중복 현실 (워크플로 + 코드대조 확인)

플랫폼은 이미 엔진과 **심하게 겹치는 분석 기능을 분산 보유**한다. 핵심 충돌 4축:

1. **종합 판정 오케스트레이션**: 플랫폼 `apps/api/app/services/design_audit/design_audit_orchestrator.py`(8엔진 병렬 설계심사 + 결정론 verdict + legal_refs + 모순감지, 1066줄)가 엔진 `services/pipeline/analysis_pipeline.py:run_analysis`(11계층, 447줄)와 **사실상 동일 철학·역할** — 두 '심사 두뇌'가 평행 존재.
2. **면적 정량산정**: 엔진 `services/extraction/geometry_area.py`(슈레이스)+`area_sanity.py`(제외area≤외곽 부등식 게이트)+`services/legal_calc/area_calculator.py`(건축법 시행령 §119 제외규정+CalcTrace+param 주입)가 플랫폼 `routers/drawing.py /calculate-area`·`design_audit` efficiency_metrics(전용률)와 직접 경합. **엔진이 압도적 엄밀**(플랫폼은 area sanity·법령 제외규정 미적용).
3. **도면 자동해석**: 엔진 `adapters/vision/drawing_extractor.py`(VLLM→ExtractedElement, provenance/UNKNOWN 날조금지)가 플랫폼 `dxf_import_service`+`cad_upload_hub`+`cnn_design_service`(ResNet-50)와 같은 '도면→구조화요소' 문제. 엔진=의미타입·provenance, 플랫폼=기하좌표(px/DXF) — **상보적이나 스키마 비호환**(아래 §6 매핑 함정).
4. **BIM/IFC·규제 룰셋**: 엔진 `adapters/bim/ifc_parser.py`(경량 STEP, 보수적 의미분류) ↔ 플랫폼 `bim_ifc_service`(ifcopenshell 물량/glTF, 강). **`ZONE_LIMITS` 리터럴이 10+개 파일에 분산 중복**(zoning/ 클러스터 중심: `zoning/auto_zoning_service.py`·`zoning/legal_zone_limits.py`·`zoning/far_incentive_calculator.py`·`zoning/development_type_analyzer.py`·`cad/auto_design_engine.py`·`cad/design_spec.py`·`services/building_compliance_service.py`·`design_risk/design_change_predictor.py`·`land_intelligence/land_info_service.py`·`precheck/precheck_service.py`·`development/scenario_simulator.py` 등; `permit/building_code_rules.py`엔 없음). → Phase 5 단일주입 작업량이 문서 초안보다 큼.

### 엔진 원칙 대비 플랫폼 결손 (품질 갭)
- **재현성**: design_audit는 모순감지(ledger)는 있으나 엔진식 `input_hash`/`snapshot` 재현 보증이 명시적이지 않음. (플랫폼 `analysis_ledger`는 content_hash/prev_hash 해시체인 보유 — §7 Phase 5 참조.)
- **area sanity 미적용**: 플랫폼 면적계산에 '제외 area 합 ≤ 외곽면적' 결정론 부등식 게이트 부재 → 환각/모순 면적 무음 승계 위험.
- **법령 제외규정 부재**: 플랫폼은 슈레이스 면적만 — §119 제외규정·CalcTrace 근거기록 없음.
- **교차검증 부재**: 단일 출처 산정 다수. IFC면적 vs 도면면적 vs 입력 파라미터 체계적 cross-validate 없음.
- **무음 위험**: `project_pipeline`의 'FAILED 마킹 후 계속 진행', `comprehensive`의 'AI해석 실패 시 None', 보고서 섹션 결손 무음.

## 2. 목표 · 비목표

**목표**: 엔진을 설계/규제/검증/정량 도메인의 **단일 판정·정량·설명 SSOT**로. 중복 제거 → 한 번 개선이 전 기능 반영. 결정론·무음0·설명가능성·교차검증·재현성을 **플랫폼 전역 확산**.

**비목표(정직한 경계)**: 엔진이 UI·협업·빌링·시장데이터 수집의 중심은 아님(그것들은 엔진을 소비/공급). 감정평가/시장/재무/사업성은 엔진의 **검증·교차검증·설명 품질 레이어**(전면 대체 아님). "한 번에 다 바꾸기" 아님 — 도메인별 파리티 후 컷오버.

## 3. 보존 불변식 (절대 제약)

- **결정론**: 엔진 `core/hashing.input_hash`(canonical sort_keys sha256)·`snapshot_id` 유지. 어댑터는 **순수함수**, 비결정 입력(`datetime.now`·LLM 서술·MLflow 분기)은 AnalysisInput 진입 전 `as_of`/결정론 도구값으로 정규화해 해시 오염 차단. BFF는 변환만, 산정 미개입.
- **무음0**: `run_analysis`의 미제공/거부 계층 `skipped[]` 표면화 계약 보존. 플랫폼의 무음(FAILED 후 진행·None·섹션 결손)을 엔진 게이트의 `SKIPPED`+사유로 **대체**해 무음0 전역 확산. 어댑터 매핑 실패도 `skipped`/422 표면화.
- **INV-13(라이브 공급측 한정)**: 엔진 `settings.USE_MOCK_ADAPTERS=True`·`LIVE_NETWORK=False` 기본과 `supply/mirror` read-only(소비측 sync get은 DB-backed 미러만, `warm_mirror_from_db`) 경계 불가침. **플랫폼/BFF는 라이브 fetch 미수행**.
- **설명가능성 — ⚠️ 중첩 구조 보존(검증 정정)**: 엔진 `AnalysisResult` **최상위 필드는** `findings[]`(Finding)·`legal_quantities[]`·`cross_validations[]`·`reg_graph`·`report`·`skipped[]` 등. 그러나 **`legal_basis` 본문·`gate_reason`·`dual_path`는 `report.items[].evidence{}` dict 키**(`analysis_pipeline.py:344/359/366`), **`CalcTrace`는 `legal_quantities[].calc_trace`**, **`rationale`는 `precedent.rationale`(및 `contracts/rationale.py`)**에 중첩된다 — AnalysisResult 직속이 아님. → **BFF는 이 중첩 구조를 평탄화하지 말고 그대로 직렬화**해야 설명 손실 0. TS 타입(§11)은 `report.items[].evidence` dict 스키마 기준으로 설계.

## 4. 아키텍처 — 엔진=두뇌, 플랫폼=수집/UI/오케스트레이션

```
[apps/web]  DeliberationConsole · 도메인 화면들
    │ (브라우저→내부 BFF만; 엔진 직결 제거)
    ▼
[apps/api]  BFF: POST /api/v1/deliberation/analyze   ← 인증·테넌트·RBAC·감사 경계
    │  + 입력 어댑터(플랫폼 컨텍스트→AnalysisInput)   ← 순수변환, 결정론 정규화, pydantic 검증
    │  + circuit-breaker / degrade(엔진 down→NEEDS_REVIEW+사유)
    │  + shadow 비교기(엔진 vs 기존 플랫폼 판정 로깅, §5)
    │  + run_id↔tenant 결속(엔진이 테넌트-블라인드 → 플랫폼이 격리 강제, §9)
    ▼ (서버사이드 httpx, Bearer=API_TOKEN; 소형=sync, 네트워크입력=async+run_id)
[engine]    POST /api/v1/analyze (run_analysis 11계층)   ← 결정론 판정·정량·설명 SSOT
    │  R0~L3-C 게이트 · area_sanity · §119 CalcTrace · cross_validate · FinalGate
    ▼  공급측 adapters(VWORLD/MOLIT/law.go.kr) · mirror(read-only 소비) · reconcile(라이브)
```

**3경계 분리**(척추안 접목): 추출(플랫폼 수집·정규화) / 판정(엔진 결정론 게이트) / 라이브공급(엔진 공급측만, INV-13).

**배포 사실(검증 정정)**: 엔진과 플랫폼은 **분리된 DB가 아니라 동일 물리 인스턴스 `propai_db`를 공유**하고 **schema만 `review`로 격리**(엔진 `settings.DATABASE_URL=…propai_db`, `DB_SCHEMA='review'`). 따라서 진짜 일관성 리스크는 'DB 분리'가 아니라 **BFF↔엔진 HTTP 경계로 인한 비원자적 2단계 쓰기**(엔진 `analysis_run` 저장 vs 플랫폼 `analysis_ledger` append)다 — §9 참조.

**현 보안 상태(검증 정정, 과장 제거)**: 브라우저 직결의 `CORS=*`는 **엔진 개발 기본값**(`settings.CORS_ORIGINS="*"`)이며, **`ENV=production` 부팅 시 와일드카드 CORS·무토큰을 fail-closed 거부**(`settings.py` model_validator). 또 `/api/v1/analyze`는 `require_token` 의존이라 **API_TOKEN 설정 시 콘솔 직결 fetch(Authorization 헤더 미전송)는 401**. → 보안 구멍은 **dev 기본 상태에 한정**되나, BFF로 인증·테넌트·감사 경계를 일원화하는 것은 여전히 정당.

**additive 원칙**: 기존 플랫폼 분석 경로는 **병존**(무손상). 엔진 호출은 신규 경로로 추가되고, 도메인별 shadow→authoritative 승격 시에만 기존 판정 대체.

## 5. 통합 패턴

- **BFF 프록시**(`apps/api/app/routers/deliberation.py`): `get_current_user`(JWT)+테넌트+RBAC+감사 → 서버사이드 `httpx.AsyncClient`로 엔진 호출. 단일 진입점.
- **입력 어댑터**: 플랫폼 컨텍스트→`AnalysisInput`(평평한 dict 다발) 자동 매핑. **pydantic 서브모델 검증**으로 타입 단절 방어, 매핑 실패는 422/skipped 표면화(§6 함정 주의).
- **shadow 모드 — ⚠️ 데이터모델 정의 필요(검증 정정 HIGH)**: 현재 shadow 비교의 스키마·저장처·divergence 기준이 **어디에도 없다**(빈 약속). 본 설계가 정의:
  - **저장처**: 플랫폼 신규 테이블 `shadow_comparison`(신규 alembic).
  - **스키마(안)**: `{run_id, domain, tenant, engine_verdict, platform_verdict, field_diffs[](field, engine_val, platform_val), divergence_score, as_of, ts}`.
  - **비교 대상**: verdict(준수)·핵심 정량(면적/far/bcr)·FinalStatus·주요 cross_validation 결과. 동치 판정은 정량 허용오차(엔진 `area_tol` 등 param 재사용).
  - **승격 기준**: 도메인별 'N건 연속 divergence_score<ε' 충족 시 authoritative 후보(사람 확인 후 flag).
- **circuit-breaker / degrade**: 엔진 타임아웃/장애 — shadow 단계면 기존 경로 폴백, authoritative 단계면 `NEEDS_REVIEW`+'엔진 미가동' 사유(무음 폴백 금지). `GET /api/v1/doctor` 상태를 헬스카드로 표면화.
- **동기/비동기 — ⚠️ 기준 재정의(검증 정정)**: 위험의 핵심은 산정 길이가 아니라 **동기 블로킹 네트워크 I/O가 async 라우트 이벤트루프를 막는 것**(엔진 `analysis_routes.py`는 `async def`인데 `run_analysis`를 `await` 없이 동기 호출, 내부 geocode/collect_land_card/collect_surrounding가 동기 httpx timeout=15s, `run_in_executor` 부재). → **분류 기준**: `collect_land_card`/`collect_surrounding`/`address`(geocode)/실어댑터 등 **네트워크 의존 입력이 있으면 무조건 async**(`/analyze/async`+run_id 폴링). 동기 경로는 **순수 결정론 입력(rules/calc_targets만)**으로 한정. BFF circuit-breaker 타임아웃은 누적 외부 타임아웃(15s×N)보다 크게.

## 6. 계약 매핑 (플랫폼 ↔ 엔진) — ⚠️ 검증 반영(가장 약했던 영역, accuracy 6.5)

엔진 입력 `AnalysisInput`(`contracts/analysis.py`, 평평한 dict 다발)·출력 `AnalysisResult`. **무음 손실 지점을 명시**한다.

### 입력 매핑 (함정 포함)
| 플랫폼 산출 | → 엔진 입력 | 함정/보강 |
|---|---|---|
| `design_audit` RunRequest{site, params(far_pct/bcr_pct/building_height_m), geometry, ifc} | `rules[]`, `calc_targets[]`, (`pnu`) | **RunRequest엔 pnu 없음** → `site.pnu`(있으면) 또는 address→PNU 지오코딩(Phase2)으로 도출. `params`는 **measured(제안값)만** 보유; **limit은 RunRequest에 없고** `applicable_limits_for(zone_type)`/zone_rules로 별도 도출(아래 행). |
| `rules[]` 항목 (엔진) | — | **중첩 구조**(검증 HIGH): `{rule:{rule_id, target_variable, comparator, depends_on, relaxations, basis_article}, measured, limit, relaxation_states, confidence, conflicts}`(`analysis_pipeline.py:128`, `rule.py`). 플랫폼 AuditFinding은 평탄 `{check_id, status, current, limit, legal_refs, improvement}`. → **measured/limit만 직결 가능**; `comparator`·`target_variable`·`relaxations`·`relaxation_states`는 **check_id별 정적 룰 카탈로그로 어댑터가 합성** 필요(없으면 완화판정·이중경로 누락). |
| `cad_upload_hub` design_raw(px points/lines/surfaces)·params_hint(building_width/area_sqm) | `calc_targets[].payload` / `rules[].measured` (design_raw는 직매핑 불가) | **검증 HIGH**: design_raw·params_hint는 **의미타입 없는 순수 기하/수치** → 엔진 `elements[]`(CalcElement는 `semantic_type` enum 필요)에 **직접 매핑 불가**. params_hint→`rules[].measured`/`calc_targets[].payload`로, design_raw→**의미분류(VLLM/라벨링) 후에만** `elements[]`. |
| `bim_ifc_service` 물량(IFC) | `ifc`(STEP 원문) **또는** `calc_targets[].elements` | 엔진 `ifc`는 **STEP 텍스트 문자열**(엔진 ifc_parser가 BimElement 해석). 그러나 bim_ifc_service 출력은 STEP이 아니라 ifcopenshell 파싱 dict `{element_type, quantity, unit, global_id}`. → **(a)** 원본 IFC STEP을 엔진 `ifc`로 그대로(중복 파싱 감수) **또는 (b)** `{element_type,quantity}`→CalcElement 변환 어댑터(IFC타입→SemanticType + underground/accessory 추론) 신설(의미·플래그 합성이 막히는 지점). |
| `zone_rules`/ZONE_LIMITS (출처: alris/design_review/zoning) | `rules[].limit`, `mirror_rules[]` | 규제 한도. design_audit가 아니라 zone 한도 resolution이 출처. |
| 다출처 fact(VWORLD/MOLIT/law) | `cross_facts[]`(fact_key+sources) | 교차검증 투입. |

### 출력 매핑 (검증 정정)
| 엔진 출력 | → 플랫폼 표현 | 비고 |
|---|---|---|
| `report.items[]`( verdict·status·`evidence.legal_basis`·`evidence.gate_reason`·`evidence.dual_path` ) | `AuditFinding[]` | **검증 HIGH**: status/legal_basis는 원시 `findings[]`(Finding: rule_id/verdict/gated_status/measured_value/limit_value/basis_article)에 **없고** `report.items[].evidence` dict에 있음. BFF는 report 전체를 통과(평탄화 금지). |
| `cross_validations[]`, `reg_graph`, `skipped[]` (최상위) | 교차검증·근거그래프·결손 UI | 실제 최상위 필드(정확). |
| `legal_quantities[].calc_trace`(CalcTrace), `precedent.rationale` | 정량 근거·유사사례 근거 | 중첩 — 경로대로 직렬화. |

### 어휘 3축 매핑 (검증 추가 — 무음 손실 방지)
판정 어휘가 **3개 독립 체계**라 1:1이 아니다. **둘 다 보존**해야 한다(verdict=준수 차원, FinalStatus=검증신뢰 차원).
- 플랫폼 `overall.verdict`: 부적합 / 조건부적합 / 적합 / 판정불가 (영문 fail/conditional/pass/None)
- 엔진 `Finding.verdict`: COMPLIANT / NON_COMPLIANT / CONDITIONAL
- 엔진 `FinalStatus`: CONFIRMED / NEEDS_REVIEW / BLOCKED
→ 예: `verdict=CONDITIONAL` + `status=NEEDS_REVIEW`를 **동시 표현**(준수성·신뢰도 분리). §3 설명가능성·§12 무음0 게이트와 연결.

**판정 SSOT 전환 방식(결정 #2, 추천 B)**: design_audit 8엔진 산출을 폐기 않고 `rules[]`/`sim_inputs[]`/`calc_targets[]`로 **변환**해 엔진 게이팅 통과. ⚠️ 단 위 'rules[] 중첩·정적 룰 카탈로그' 보강이 전제.

## 7. 단계별 로드맵 (Phase 0~6)

각 Phase는 **additive·회귀게이트 통과**를 완결 조건으로.

- **Phase 0** (무코드~소, 즉시): `export_scoped_secrets.py`로 엔진 `API_TOKEN`을 `apps/api`에 주입, `NEXT_PUBLIC_DELIBERATION_ENGINE_URL` 실설정, **`GET /api/v1/doctor`**를 `project_dashboard` 헬스카드로 노출(live/mock·키 가시화). 엔진 `ENV=production` fail-closed 확인.
- **Phase 1** (BFF 교두보): `apps/api/app/routers/deliberation.py` — `POST /api/v1/deliberation/analyze`(JWT+RBAC+테넌트+감사). 서버사이드 httpx 프록시. `DeliberationConsole`을 내부 엔드포인트로 전환(브라우저 직결 제거). `AnalysisResult` 풍부 출력(**중첩 evidence 포함**)을 TS 타입에 반영. **run_id↔tenant 결속**(§9). 기존 경로 무손상.
- **Phase 2** (입력 어댑터, 원클릭): 플랫폼 컨텍스트→`AnalysisInput` 자동매핑(§6 함정 반영: pnu 도출·rules[] 카탈로그·의미분류). address→PNU·collect_land_card 자동 ON(단 네트워크 입력 → async 경로, §5).
- **Phase 3** (면적·검증 위임, 최대 품질점프, shadow): `drawing /calculate-area`·`design_audit` efficiency_metrics가 엔진 `geometry_area`+`area_sanity`+§119+`CalcTrace`를 **shadow로** 호출(비교 로깅). `VerifierService`/`calc_ledger`/`range_rules`를 엔진 `final_gate`/`cross_validate` thin client로.
- **Phase 4** (Blocking 게이트 + 판정 SSOT): `_verify_stage` fail/강등 시 후속 `SKIPPED`+사유(무음0 실현). `design_audit_orchestrator` 8엔진 판정을 엔진 R3+FinalGate로 (변환)위임. **warn-only→enforce 단계 적용**(결정 #4).
- **Phase 5** (교차검증·SSOT·재현성 일원화): 1차출처 어댑터(VWORLD/MOLIT/law.go.kr) 호출 엔진 일원화(중복 호출 제거). **`ZONE_LIMITS` 10+곳→엔진 reg_graph R3 룰셋 단일주입**(작업량 큼). **플랫폼 `analysis_ledger`(이미 존재 — `031_analysis_ledger`, content_hash/prev_hash 해시체인)에 엔진 `input_hash`/`snapshot_id` 컬럼을 additive 추가하는 신규 alembic**(신규 테이블 아님). `regulation_monitor` 변경감지→미러 reconcile 트리거.
- **Phase 6** (오케스트레이션 진입점 통일): `comprehensive_analysis`·`pipeline`·`ai_analyze`가 엔진을 백엔드로 호출하는 게이트웨이로 수렴. 분양가/공사비 단일상수(`SIGUNGU_BASE_PRICES`)→엔진 다출처 교차검증. `BaseInterpreter` 9종·`ExpertPanel`을 엔진 `Rationale`/`legal_refs`/`CalcTrace` 스키마로 정규화. 가드 전무한 `ai_analyze.py` 프록시 흡수.

## 8. 도메인 수렴 순서 (shadow→authoritative)

품질 갭이 크고 위험이 낮은 순: **① 면적 정량**(area_sanity·§119 부재 명확) → **② 법규 판정**(rules[] 변환+정적 룰 카탈로그) → **③ 교차검증**(Phase 5) → **④ 도면 자동해석·BIM**(스키마 통합 필요). 각 도메인: shadow(차이 로깅) → divergence 분석 → warn-only → authoritative 승격.

## 9. 리스크 · 완화 · 롤백 (검증 보강)

| 리스크 | 완화 |
|---|---|
| (1) 단일 진입점 집중(엔진 장애=전 분석 정지) | BFF circuit-breaker + degrade(shadow기 폴백, auth기 NEEDS_REVIEW+사유) + 엔진 /async 격리 |
| (2) 계약 타입 안전성 단절(dict[] 다발·중첩 rules[]) | 어댑터 pydantic 서브모델 검증, **check_id별 정적 룰 카탈로그**, 매핑 실패 422/skipped(무음 통과 금지) |
| (3) 이중 호출·성능(같은 1차출처 중복 fetch) | Phase 5 엔진 adapters 일원화(캐시 경유)까지 한시 비용 |
| (4) 결정론 오염(datetime.now·MLflow·LLM 경로) | 어댑터 as_of 치환·LLM 산출 엔진 입력 배제 |
| (5) 판정 SSOT 전환 회귀 | **shadow 병존 + divergence 로깅 후 전환**(즉시 대체 금지) |
| (6) **멀티테넌시 — 엔진 테넌트-블라인드(검증 HIGH)** | 엔진 `analysis_run`은 org_id NULL 저장·`get_analysis(run_id)` 테넌트 필터 없음·RLS 없음 → **run_id 유출 시 교차테넌트 조회 가능**. 완화: BFF가 run_id↔tenant 매핑을 **플랫폼 측 테이블(analysis_ledger 등)에서 강제**(엔진 run_id를 플랫폼 원장에 결속), 또는 `save_analysis`에 org/project 주입을 위한 **엔진 수정(=무수정 가정 깨짐)을 별도 Phase로**. 플랫폼 BFF는 자기 run_id만 조회 허용. |
| (7) **비원자적 2단계 쓰기(검증)** | 동일 propai_db이나 HTTP 경계라 엔진 `analysis_run` 커밋 vs 플랫폼 `analysis_ledger` append가 분리 세션 → 부분실패 비원자. saga/보상 또는 엔진 run_id 사후 결속 + 멱등 재시도. |
| (8) **동기 이벤트루프 블로킹(검증)** | 네트워크 의존 입력은 async 강제(§5). 동기는 순수 결정론 입력 한정. |

**롤백**: 각 도메인 authoritative 승격 전까지 기존 경로 병존 → feature flag 즉시 원복. 엔진 무수정 구간은 엔진 롤백 불필요(테넌시 Phase는 예외).

## 10. 미해결 결정 (사용자 확정 필요, 추천 포함)

1. **전환 속도/권위 모델**: (A)점진 어댑터→도메인별 B 수렴 **[추천]** vs (B)즉시 전면 척추화.
2. **판정 SSOT 전환 방식**: (A)8엔진 대체 vs **(B)8엔진 산출을 rules[]/sim_inputs[]로 변환 [추천]** — ⚠️ rules[] 중첩·정적 룰 카탈로그 보강 전제.
3. **재현성 일원화 시점**: 플랫폼 `analysis_ledger`(이미 존재)에 input_hash/snapshot **컬럼 additive 추가**를 Phase 1 동반 vs **Phase 5 [추천]**.
4. **blocking 게이트 수위**: 처음부터 enforce vs **warn-only→blocking 단계 [추천]**.
5. **실연동 인프라 가동 책임/시점**: VWORLD/MOLIT/law.go.kr 키·Qdrant·Celery broker·실 VLLM(운영/데이터팀 병렬; 엔진 기본 mock).
6. **엔진 호출 동기/비동기**: 순수 결정론 입력=동기 / 네트워크 의존 입력=async+run_id 폴링 **[추천]**.
7. **(신규) 테넌트 격리 방식**: BFF가 플랫폼 측에서 run_id↔tenant 강제 **[추천, 엔진 무수정 유지]** vs 엔진 `save_analysis`에 org/project 주입(엔진 수정).

## 11. 첫 증분 상세 (Phase 0 + Phase 1)

**왜 1순위인가**: 엔진 무수정(전체 스위트 무회귀) · 전부 신규 additive(기존 50+ 분석 산출 불변) · 즉시 인증/테넌트/감사 경계 확보 · 이후 모든 어댑터·게이트 위임의 단일 진입점.

- **Phase 0**: `project_dashboard`에 엔진 **`GET /api/v1/doctor`** 헬스카드(live/mock·키). `export_scoped_secrets`로 `API_TOKEN` 주입, `ENGINE_URL` 설정.
- **Phase 1**: `apps/api/app/routers/deliberation.py` 신설
  - `POST /api/v1/deliberation/analyze`: `Depends(get_current_user)`+RBAC+테넌트+감사 → `httpx.AsyncClient`로 엔진 **`POST /api/v1/analyze`**(Bearer=API_TOKEN, timeout, circuit-breaker) → 엔진 미연결 시 `NEEDS_REVIEW`+사유(무음0). **run_id를 플랫폼 원장에 tenant와 결속**(§9 R6).
  - `DeliberationConsole.tsx`: 브라우저 직결(현 ENGINE_URL·fetch) → 내부 엔드포인트로 전환.
  - **TS 타입은 `report.items[].evidence` 중첩 스키마 기준**(legal_basis·gate_reason·dual_path) + 최상위(cross_validations·reg_graph·skipped) 반영(무음 손실 0).

## 12. 검증 게이트 (각 Phase 완결 조건)

- 엔진 **전체 스위트 무회귀**(현 419 테스트 함수, CI 기준; 엔진 무수정 구간) + 플랫폼 신규 테스트(BFF 인증/degrade/매핑 422/테넌트 격리) green.
- **결정론**: 동일 입력 동일 결과(BFF 변환 input_hash 오염 0).
- **무음0**: 엔진 미연결·매핑 실패·계층 결손 전부 표면화(NEEDS_REVIEW/skipped/422, 무음 폴백 0).
- **INV-13**: 플랫폼/BFF 라이브 호출 0.
- **테넌트 격리**: run_id 교차테넌트 조회 차단 테스트.
- **shadow**: 측정 가능한 divergence 스키마·기준 충족 후에만 authoritative.
- 각 Phase 적대적 다관점 리뷰(determinism/무음0/보안/회귀) gate 통과.

---

### 부록 A. 작업 트랙
- 플랫폼측 통합 코드: **trust_infra 기반 신규 통합 워크트리**(`feature/trust-infra-2026-06-11`에서 분기). 엔진은 `feature/deliberation-review`에서 **무수정 유지**(테넌시 Phase는 예외로 별도 합의).
- 협업: Workflow 멀티에이전트 오케스트레이션(팬아웃·shadow 비교·적대 검증).

### 부록 B. 근거 · 검증
- 통합설계 워크플로(9 에이전트): maps(5클러스터)·designs(incremental 8.7 / unified 7.9 / spine 7.2)·verdict.
- 코드대조 검증 워크플로(4 렌즈): platform 8.5 / engine 7.5 / contract-mapping 6.5 / completeness 7.5 → **HIGH 7건 등 정정 반영**(analysis_ledger 기존 존재·rules[] 중첩·findings 비보유·cad 의미부재·테넌트-블라인드·동기 이벤트루프·shadow 모델 부재·DB 공유·ZONE_LIMITS 10+곳·doctor 경로·테스트 수). 본 v2는 그 합성.
