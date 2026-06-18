# 중심 엔진 통합 설계 (Central Analysis Engine Integration Design) — v5

> 근거: 9-에이전트 설계 + 4-렌즈 코드대조 + **7-렌즈 9.5 시뮬레이션 3라운드**(R1 36·R2 29·R3 29 결함 정정, 누적 94). R3 점수: code-fact 9.0/contract 7.5/impl 7.5/failure 8.5/invariant 8.0/security 8.5/completeness 8.5(min 7.5). v5는 R3 정정 반영(append_audit 키워드전용·analysis_type 고정 "audit"·CircuitBreaker service_name 부재·패키지 격리 vendoring·input_hash {"input":...} 래핑·vision/jurisdiction/embedding 라이브 우회·alembic 위치·/reports/build 무인증·staging fail-closed 등).
> 상태: **9.5 수렴 중**(목표 전 렌즈 ≥9.5). 품질기준=[[quality-gate-95]].
> 결정: 전환=상세설계먼저, 협업=Workflow, 플랫폼 브랜치=trust_infra 기반 신규 통합 워크트리.
> **경로 규약**: 엔진=`services/deliberation-review/apps/api/app/`("엔진 …"). 플랫폼은 `apps/api/app/...`와 `apps/api/{services,routers,database}/...` **직속 혼재** — 경로 정확 표기.

## 0. 요약
엔진=분석 커널(결정론 판정·정량·설명 두뇌), 플랫폼=수집·UI·오케스트레이션. 점진 어댑터(additive)+circuit-breaker/degrade/shadow+3경계. 판정 SSOT는 shadow→authoritative, 엔진 미연결/무결성실패→무음 폴백 금지·`NEEDS_REVIEW`+사유.

⚠️ **"엔진 무수정"의 정직한 경계** — 다음은 무수정 불가, BFF 우회 또는 **엔진 소규모 수정 Phase(§10 결정#8)**: (1) 비동기 결과 영속(`analyze_task` 미저장), (2) `get_analysis` 테넌트 필터(교차read), (3) mirror가 `inp.pnu` 사용(address-only 무음공백), (4) `cached_get`이 `LIVE_NETWORK`·snapshot_id 무시(라이브 오프 불가·교차스냅샷 오염), (5) 비-analyze 라우트(/doctor,/reports,/UI) 무인증. (2)(4)는 컬럼 추가가 아니라 **쓰기/조회 경로 수정 수준**(엔진 `analysis_run`은 CommonMixin으로 org 컬럼 이미 보유, `base.py`).

## 1. 배경 — 중복 현실 (코드 실측)
1. **종합 판정**: 플랫폼 `apps/api/app/services/design_audit/design_audit_orchestrator.py`(8엔진, 1066줄) ↔ 엔진 `services/pipeline/analysis_pipeline.py:run_analysis`(447줄) — 평행 두뇌.
2. **면적 정량**: 엔진 `services/extraction/geometry_area.py`+`area_sanity.py`+`services/legal_calc/area_calculator.py`(§119+CalcTrace) ↔ 플랫폼 **전용 라우트 없음**: `apps/api/app/services/pipeline/project_pipeline.py:1084 _calculate_area_from_geometry`(슈레이스, sanity·§119 미적용)+`design_audit` efficiency_metrics. (초안 `routers/drawing.py /calculate-area` **부재** → Phase 3 BFF 신규.)
3. **도면 자동해석**: 엔진 `adapters/vision/drawing_extractor.py`(VLLM→ExtractedElement) ↔ 플랫폼 `dxf_import_service`+`cad_upload_hub`+`cnn_design_service`(ResNet-50). 의미타입 vs 기하좌표 — 비호환(§6).
4. **BIM/IFC**: 엔진 `adapters/bim/ifc_parser.py`(경량 STEP) ↔ 플랫폼 BIM 2스택 — (a) `apps/api/app/services/bim/{ifc_generator_service.py(생성), ifc_to_gltf_service.py(glTF), bim_service.py}`, (b) `apps/api/services/bim_ifc_service.py:25 class BIMIFCService`(ifcopenshell 파싱·물량, 반환=`packages.schemas.models.BIMQuantityResponse`). 출력은 STEP 아닌 **BIMQuantityResponse(물량 dict)** → 엔진 `ifc`(STEP 원문)와 비호환(§6 (b) CalcElement 변환).
5. **규제 룰셋 중복**: `ZONE_LIMITS` apps/api 전역 **19파일**(비테스트 16): `apps/api/services/building_compliance_service.py:384`(정의)·`apps/api/app/services/{zoning/legal_zone_limits,zoning/auto_zoning_service,zoning/far_incentive_calculator,zoning/development_type_analyzer,cad/auto_design_engine,cad/design_spec,design_risk/design_change_predictor,land_intelligence/land_info_service,precheck/precheck_service,development/scenario_simulator,design_audit/brief_extractor}.py`·`apps/api/app/routers/v2_feasibility.py`·`apps/api/routers/{drawing,building_compliance,auto_zoning}.py`(`permit/building_code_rules.py`엔 없음). → P5 단일주입 회귀범위 큼.

**엔진 대비 결손**: 재현성(input_hash/snapshot) 부재·area sanity·§119·체계적 cross-validate 부재·무음(FAILED후진행/None/섹션결손). 플랫폼 `analysis_ledger`는 content_hash/prev_hash 해시체인 보유(P5).

## 2. 목표·비목표
목표=설계/규제/검증/정량의 단일 판정·정량·설명 SSOT, 중복 제거, 엔진 원칙 전역 확산. 비목표=UI/협업/빌링/시장수집 중심 아님; 감정/시장/재무는 품질 레이어; 일괄 전환 아님(도메인별 파리티 후 컷오버).

## 3. 보존 불변식 (코드 정합)
- **결정론(확장 단위)**: `input_hash`=AnalysisInput만 해싱(`analysis_pipeline.py:57`). 라이브 어댑터 산출(geocode/land_card/surrounding/cross_facts via `cached_get`) 반영 시 input_hash 동일≠결과 동일. **진짜 단위=(input_hash, snapshot_id, source_cache 적재상태, vision 추출 캐시 적재상태)**. ⚠️ **VLLM 도면 자동해석**(`drawing_extractor.py:139`, temperature=0 best-effort, vision_cache는 snapshot 없음·프로세스로컬) 포함 run은 **"순수 경로" 아님** — 결정론 게이트 모수에서 제외(drawings/ifc/elements 없는 입력만 input_hash 동치 검증). ⚠️ **`cached_get` L1 조회키=cache_key(adapter,endpoint,params)로 snapshot_id 미포함**(`source_cache.py:62-69,91-99`) → 스냅샷 A 캐시가 B 분석에 반환되는 교차스냅샷 오염 가능. 운영 재현성 보증엔 (a) cache_key에 snapshot 결합(엔진 수정#8) 또는 (b) 스냅샷 경계마다 `source_cache.clear()+warm_from_db(snapshot_id)`. 결정론 게이트는 **순수 경로(rules/calc_targets만)**에서만 input_hash 동치 검증; 네트워크 경로는 snapshot 워밍으로만.
- **무음0**: `skipped[]` 보존. 매핑 실패는 **자동 422 아님**(§6 KeyError→500) → BFF 선검증으로 422/skipped.
- **INV-13(실계약)**: 강제 스캐너 2개 — (1) `test_consume_static.py`(consume/+services/verify/에서 httpx/aiohttp/openai/anthropic **전면 0**, `:19="aiohttp"`), (2) `test_live_call_scan.py`(adapters/regulation·legal, services/land·cross_validate는 `cached_get` 경유만 허용). *라이브 0 아님*. run_analysis는 키 보유 시 `cached_get→httpx.get`(`source_cache.py:157`)로 law/molit/vworld/geocode/land_card fetch. ⚠️ **두 스캐너가 vision/jurisdiction/embedding 어댑터는 미커버** — `drawing_extractor.py:139`·`vllm_sheet_classifier.py:75`·`jurisdiction/vworld.py`·`embedding/embedding_client.py`는 cached_get·LIVE_NETWORK **우회 직접 httpx 라이브**(키 보유 시 발신). **`LIVE_NETWORK`은 공급 `network.py`(LiveNetwork)만 게이트**. 운영 전면 차단엔 전역 게이트 `settings.CONSUMER_LIVE_OFF` 신설(엔진 수정#8 (b), vision/jurisdiction/embedding 포함) 또는 BFF가 drawings/address/issue+corpus 입력을 명시 동의 없이 미전달.
- **설명가능성(중첩)**: 최상위=`findings[]`·`legal_quantities[]`·`cross_validations[]`·`reg_graph`·`report`·`skipped[]`. 중첩=`legal_basis`/`gate_reason`/`dual_path`(`report.items[].evidence`), `CalcTrace`(`legal_quantities[].calc_trace`), `rationale`(`precedent.rationale`). BFF 평탄화 금지·report 전체 직렬화. TS=evidence 스키마 기준(§6).

## 4. 아키텍처
```
[apps/web] DeliberationConsole → (동일출처) BFF만
[apps/api] BFF POST /api/v1/deliberation/analyze ← 인증·테넌트·RBAC·감사·run_id↔tenant·input_hash 선계산
   + 입력 어댑터(pydantic 선검증) + 공유 circuit-breaker(Redis) + degrade 봉투 + shadow 비교기
   ▼ httpx(Bearer=DELIBERATION_ENGINE_API_TOKEN; 순수=sync, 네트워크입력=async+task 폴링)
[engine] POST /api/v1/analyze(run_analysis 11계층) ← 결정론 판정·정량·설명 SSOT
   ▼ 공급 adapters(LIVE_NETWORK 게이트) · cached_get(별개) · mirror(read-only) · reconcile(라이브)
```
**3경계**: 추출(플랫폼)/판정(엔진)/라이브공급(엔진, INV-13).
**배포**: 동일 `propai_db` 공유·엔진 schema `review`/플랫폼 public 격리(분리 DB 아님). 일관성 리스크=HTTP 경계 비원자 2단계 쓰기(§9 R7).
**현 보안**: `CORS=*`는 엔진 dev 기본, `ENV=production`은 와일드카드 CORS·무토큰 fail-closed(`settings.py:84-89`). `/analyze*` 4개만 `require_token`; **`/api/v1/doctor`(`ops_routes.py:11`)·`/api/v1/reports/build`(`report_routes.py:30` 무인증·임의 `items:list[dict]` 연산=DoS 표면)·`/`(UI) 무인증**(`main.py` include 시 dependencies 없음; doctor의 integration_status가 api_auth.enabled·*_key_present 평문 노출=핑거프린트). → §10#8에서 **모든 비-health 라우트 require_token**. ⚠️ 격리 1차방어(비노출+토큰)가 코드 강제되는 건 `ENV==production`뿐(`settings.py:84`) → **staging fail-closed 확장**: `_production_fail_closed`를 `ENV in {production,staging}`로 + `ENV!=production이고 API_TOKEN 없고 바인드가 비-loopback이면 부팅 거부`. → 엔진 **외부 비노출 네트워크+BFF만 접근**(1차), 비-health 인증(2차).
> (플랫폼) `apps/api/app/routers/ai_analyze.py:22 POST /api/v1/ai/llm`은 `get_current_user`만 있고 RBAC/테넌트/레이트리밋 없음 — **엔진 아님, Phase 6 플랫폼 수렴 대상**.

## 5. 통합 패턴 (구체 계약)

### BFF (`apps/api/app/routers/deliberation.py`)
- **인증**: `from app.services.auth.auth_service import get_current_user`(core/rbac와 동일 출처). 반환=`apps.api.database.models.user.User`(TenantMixin, `tenant_id:UUID`). `jwt_handler.py:110 CurrentUser`(동명 별개) 사용 금지. **RBAC**: admin 전용 아님 → `require_role` 미적용(인증 사용자 허용; `rbac.py:100-125` 비-ADMIN 통과). 세분화는 Phase1 비범위.
- **토큰**: API_TOKEN(≥32B 랜덤)은 운영자가 1회 생성해 **엔진 `.env.secrets`와 플랫폼 BFF `.env`(`DELIBERATION_ENGINE_API_TOKEN`·`DELIBERATION_ENGINE_URL`) 두 곳 수기 동일값**. `export_scoped_secrets.py`는 플랫폼→엔진 단방향(`docstring:3-8`)이라 엔진 자체 생성 토큰엔 **미사용**(--allow 금지). 회전 시 두 .env 동시 갱신+엔진 재시작.
- **circuit-breaker**: `from apps.api.integrations.base_client import CircuitBreaker` — `__init__(failure_threshold, recovery_timeout=60.0, half_open_max)`만, **`service_name` 인자 없음**(`base_client.py:162`); `can_execute()/record_success()/record_failure()`만(httpx 미래핑, `:159-216`). ⚠️ **인스턴스 상태=프로세스 로컬**(`apps/api/app/core/rate_limit.py:7` 선례) → 다중워커 미공유. **운영(워커>1)은 Redis 공유 breaker 필수**: 키 `deliberation_engine:cb:{state,failures,half_open_tokens}`, 전이 Lua(EVAL) 원자화, half-open 동시진입은 `SET NX EX` 토큰버킷, **Redis 장애 시 fail-safe(CLOSED 간주+타임아웃 단축+경보, 무음 금지)**. 단일워커(uvicorn -w 1)면 in-memory `cb = CircuitBreaker(failure_threshold=5, recovery_timeout=75.0, half_open_max=3)` 단일 인스턴스 허용(매니페스트 워커=1 게이트). OPEN 중=엔진 skip→shadow기 폴백/authoritative기 즉시 NEEDS_REVIEW.
- **패키지 격리(중요)**: BFF는 플랫폼 패키지 `app`(`apps/api/app`) 안이고 엔진도 top-level 패키지명 `app`(`analysis_pipeline.py:13`) → **엔진 import 불가**(충돌). → canonical/input_hash·`{"input":...}` 래퍼·AnalysisInput 기본값을 플랫폼 `apps/api/app/services/deliberation/_engine_contract.py`에 **vendoring**(엔진 버전 핀 + parity 단위테스트로 drift 검출). AnalysisResult는 엔진 import 대신 플랫폼 동등 모델(필수 input_hash/report만 검증, run_id/그외 extra=allow)로 역직렬화.
- **타임아웃**: connect=5s; 순수 동기 read=30s; 네트워크입력 동기는 누적 15~20s×N(N≈3) → read=60s 또는 async 강제. settings 노출.
- **degrade 봉투**: HTTP **200**, `{"degraded":true,"final_status":"NEEDS_REVIEW","reason":"engine_unreachable|timeout|circuit_open|invalid_response|engine_task_failed|async_result_lost|async_timeout","engine_url":<url>,"result":null}`. 정상=`{"degraded":false,"result":<AnalysisResult>}`. 합성 AnalysisResult 미생성(report 필수·emit EvidenceMissing 회피, `analysis.py:94`/`report.py:43`).
- **부분응답**: HTTP200이나 본문 결손/파손 → pydantic `AnalysisResult` strict 역직렬화, ValidationError·필수(run_id/input_hash/report) 결손 시 NEEDS_REVIEW+`invalid_response`(shadow는 별도 기록=false divergence 차단), 절단은 breaker 실패 카운트.
- **감사(audit)**: raw INSERT 금지. **`await app.services.ledger.audit_ledger.append_audit(*, action=…, user_id=str(user.id), resource_type="deliberation", resource_id=engine_run_id, tenant_id=user.tenant_id.hex, metadata={input_hash, content_input_hash, http_status, decision, engine_url, request_id})`** — **전 인자 keyword-only**(`audit_ledger.py:52`). analysis_type은 라이브러리 고정 `"audit"`(`AUDIT_ANALYSIS_TYPE :18`; "deliberation_audit" 불가 — deliberation 구분은 `resource_type`/`metadata`). 합성 체인주소 `__audit__/<tenant>`(`:21-23`), dedup은 내부 `event_id=uuid4().hex`+`event_ts=time.time()`로 회피(`:65`). ⚠️ **append_analysis는 raise 안 함**(`analysis_ledger_service.py:242` 전예외→`{ok:False}`; `:218` content_hash 동일 시 `unchanged`; `:226` `quota_exceeded`). 반환 dict 분기: `ok or unchanged` → 통과; **일반 실패(`not ok and not unchanged and not quota_exceeded`) → 502 fail-closed**; **`quota_exceeded` → 분석 결과는 반환하되 응답 `audit_degraded=true`+skipped 표면화+운영경보**(감사 무음 금지·가용성 보존, 502 아님). ⚠️ **audit은 분석과 동일 테넌트 quota 공유**(`_count_entries` analysis_type 무필터 `:95`) → **P0 선행 플랫폼 수정**: `_count_entries`에 `AND analysis_type<>'audit'` 추가(감사가 분석 quota 잠식 방지).

### 동기/비동기 (코드 현실)
- 분류: 네트워크 의존 입력(collect_land_card/collect_surrounding/address/실어댑터)→**async 강제**; 동기는 순수 결정론 입력만. (엔진 `analysis_routes.py`가 `async def`인데 `run_analysis` 동기 호출+동기 httpx 15~20s+`run_in_executor` 부재 → 이벤트루프 블로킹.)
- ⚠️ **run_id는 동기 `save_analysis`(`analysis_store.py:19`)에서만 부여**. async `/analyze/async`(`analysis_routes.py:57-65`)는 `{task_id}` 반환·`analyze_task`는 결과 미저장(run_id None, `analysis.py:69`). → **run_id↔tenant 결속·GET 프록시는 동기 전용**. async 필요 시: BFF가 task SUCCESS 수신 시 `platform_run_id=uuid4()` 발급, `engine_run_binding(run_id=platform_run_id, engine_task_id=task_id, source='async')` 저장+결과 플랫폼 영속, GET은 BFF 영속본 반환(엔진 미저장). 폴링 분기: `status==FAILURE`→즉시 `engine_task_failed`; `SUCCESS and result is None`→`async_result_lost`(redis TTL); `PENDING/STARTED/RETRY and <timeout`→재폴링; `≥timeout`→`async_timeout`. (엔진 비동기 영속 원하면 엔진 수정#8.)

### shadow 모드 (데이터모델 §12)
- 비교: verdict·핵심정량(면적/far/bcr)·FinalStatus·cross_validation. 동치=정량 허용오차(`area_tol` 등 param).
- **환경 분리**: `engine_degraded/mirror_loaded/cache_warm`(doctor/skipped[] 도출) 기록 → `engine_degraded OR not mirror_loaded`=`environmental`로 승격 모수 제외(미러 미적재 시 엔진 보수판정→체계적 divergence).
- **storm 가드**: divergence율 임계 초과 시 도메인 자동 warn-only+알림.
- **승격(측정)**: `SELECT count(*) FROM shadow_comparison WHERE domain=? AND tenant_id=? AND divergence_score<:eps AND environmental=false ORDER BY ts DESC LIMIT :N` — 최근 N건 전부 <ε이면 후보(사람 확인). 기본: 면적 N=50/ε=0.01, 법규 N=100/ε=0.

## 6. 계약 매핑 (목표 9.5)

### 입력 `AnalysisInput`(`contracts/analysis.py:25-65`) — 전 필드 출처/도출
| AnalysisInput 필드 | 플랫폼 출처/도출 | 미제공 시 |
|---|---|---|
| `pnu` | `site.pnu`(`design_audit_orchestrator.py:433` 존재) 또는 address→PNU 지오코딩(Phase2, BFF 선해소) | 빈값 → 미러 무음공백 → BFF가 422/skipped |
| `application_date` | design_audit `params.application_date`/신청서 | `axis_date`→`date(2026,1,1)` 폴백(`pipeline:63`) |
| `axis_date` | 규제 적용시점(BFF 고정) | application_date |
| `snapshot_id` | BFF가 `snap-<tenant>-<yyyymmdd>` 결정론 생성(`set_snapshot`, `pipeline:60`) | "snap-1" |
| `model_version` | 'engine-v1'(미주입) | — |
| `drawing` | 축척/관할 힌트 dict(scale_unit/preflight, `pipeline:164`) | preflight skipped 표면화 |
| `drawings[].image_ref` | ⚠️SSRF(아래) | — |
| `ifc` | design_audit `ifc_file_url`(URL) **다운로드 후 STEP 텍스트** 또는 §6(b) | extraction BIM skip |
| `elements[]` | 의미분류 후(아래 어댑터) | VLLM/elements skip |
| `calc_targets[]` | 아래 스키마 | calc skip |
| `rules[]` | 정적 룰 카탈로그+design_audit findings measured/limit(아래) | 판정 skip |
| `sim_inputs` | {sunlight,egress,parking,view} 키만(`pipeline:148-157`) | 그 외 키 skipped |
| `issue`/`corpus` | 유사사례(L4) | skipped 'precedent: no issue/corpus' |
| `citations` | 미러검증 인용 [{ref}] | 'verify: no citations' 보수게이팅 |
| `cross_facts[]` | 다출처 fact(VWORLD/MOLIT/law)[{fact_key,sources}]. 자동합류 키 `law_query`/`building_pnu`/`land_pnu`(`pipeline:285-310`) | cross-validate skip |
| `mirror_rules[]` | 미제공 시 엔진 `default_store().get(pnu)`(`pipeline:182`, SUPPLY_STORE) | 미적재 보수 게이팅 |
| `collect_land_card`/`collect_surrounding` | BFF 기본 False(라이브 게이트, async) | — |
| `land_year` | '2024' 기본(`pipeline:253`) | — |
| `surrounding_radius_m` | 150 기본 | — |
| `proposed_floors` | 경관심의(collect_surrounding 동반) | skip |
| `qual_facts` | 정성(L3-C) | skip |

**design_audit RunRequest 실제 필드**(`design_audit.py:257-275`): `{project_id, site, params(far_pct/bcr_pct/building_height_m), geometry?, ifc_file_url?(URL), rooms?, use_llm, use_verification_retry}` — ⚠️ `ifc` 필드 없음(`ifc_file_url`만 → BFF 다운로드 필요), `site.pnu` 존재.

**`calc_targets[]`**(`calc_engine.py:119-149`): `{target(CalcTarget enum: building_area|gross_floor_area|far_floor_area|plot_area|building_height|floor_count), payload(target별 필수키), elements:[CalcElement], declared?}`. 필수 payload: building_area→`outer_area`; gross_floor_area→`floor_areas`; far_floor_area→`gross_floor_area`; plot_area→`parcel_area`; building_height→`raw_height`; floor_count→`above_ground_floors`. ⚠️ **필수 payload 키 결손만 `RuleContractError→422`**(`calc_engine.py:128`); **`target` 키 자체 결손·CalcElement/Rule 오형은 KeyError/ValidationError→500**(`pipeline:110-111`, DomainError만 422) → BFF 선검증 422/skipped. `CalcElement`(`legal_quantity.py:56-70`)={semantic_type(SemanticType enum, `semantic_element.py:15-27`), confidence, area, length, depth, element_id?, underground?(None=미상), accessory?(None=미상)}.

**`rules[]` 정적 룰 카탈로그**(check_id→Rule): `{rule:{rule_id, target_variable, comparator(Comparator enum `<= >= < > ==`, `enums.py:57-69`), depends_on:[], relaxations:[{relaxation_id, prerequisite_rule_id, effect, basis_article}], basis_article}, measured, limit, relaxation_states, confidence, conflicts}`(`analysis_pipeline.py:128`, `rule.py:12-29`). **relaxation_states**(`relaxation.py:13-55`): `dict[str,str]`, 키=`prerequisite_rule_id or relaxation_id`, 값∈{MET,PROVIDED,UNVERIFIABLE,UNMET}, **누락=UNVERIFIABLE**(거짓불합격 금지); MET→완화해소, PROVIDED→CONDITIONAL, UNVERIFIABLE→CONDITIONAL+requires_committee, 전부 UNMET→완화 미적용. ⚠️ **매핑 실패=KeyError→500**(`rules[i]["rule"]`/`calc_targets[i]["target"]` 결손; `/analyze`는 DomainError만 422, `analysis_routes.py:36-40`) → **BFF 어댑터가 pydantic 서브모델(Rule/CalcTarget) 선검증해 422/skipped**.

### 의미분류 어댑터 I/O 계약
- **elements[] 입력**(`dual_path.py:13`, `element_classifier.py:26-44`): 요소 dict=`{element_id, features:{semantic_hint(SemanticType 이름 또는 UNKNOWN), hint_strength(0~1)}, present_in_sheets?}`; hint이 SemanticType 멤버+strength≥param('element_classify_min_confidence')여야 채택, 아니면 UNKNOWN 하향. cad_upload_hub design_raw(px)·params_hint는 의미타입 없음 → **직매핑 불가**, 의미분류 후에만.
- **IFC**(`ifc_parser.py:39-116`): 엔진 `ifc`=STEP 텍스트 → `BimModel{elements:[BimElement{ifc_type, semantic_type, name, guid, storey, area, length}], source}`(타입맵 IFCWALL→EXT_WALL + 이름키워드 '지하'→BASEMENT, 미매핑 UNKNOWN). ⚠️ **BimElement엔 underground/accessory/depth 없음**(`bim.py:12-19`) → FAR 제외적격(§119①4 지하AND부속) CalcElement 변환은 name/storey 키워드로 추론하되 **미상은 None 유지→CalcEngine HELD 표면화**(`calc_engine.py:92-97`). 이 BimElement→CalcElement 규칙(area=`BimElement.area`, length=`.length`, underground/accessory는 name/storey 추론·미상 None→HELD)을 **신규 배선**으로 명문화(현재 플랫폼 BIM 물량→엔진 calc 경로 전무).

### 출력 `report.items[]`(3종 evidence 전수) — `analysis_pipeline.py:348-410`
- ReportItem 직속(`report.py:21-32`): `{item_id,title,verdict,status,confidence_grade,recommendation,basis_article,snapshot_id,model_version,input_hash,evidence}`.
- ① finding evidence(`:356-373`): `{basis_article, legal_basis(dict 또는 {ref,resolved:None,note}), measured, limit, requires_committee, conditional_relaxations, verified, gate_reason(|None), dual_path({table_value,geom_value,delta,status,caveat}|None)}`.
- ② sim_metric evidence(`:387-392`): `{metric, value, required, flags, model, basis_article, legal_basis}`.
- ③ precedent evidence(`:401-409`): `{distribution, common_conditions, n, source, search_meta, rationale, caveats}`.
- 최상위 `cross_validations[]`·`reg_graph`·`skipped[]`; 중첩 `legal_quantities[].calc_trace`·`precedent.rationale`. BFF 평탄화 금지.

### 어휘 4축 매핑 (무손실)
- ①**Verdict**(준수, `finding.py:14-17` COMPLIANT/NON_COMPLIANT/CONDITIONAL; `evaluator.py:42-55`).
- ②**GatedStatus**(finding 신뢰, `finding.py:20-22` CONFIRMED/NEEDS_REVIEW; FindingGate→`result.findings`에만, `pipeline:332`; **report item.status로 미사용** — 혼동 금지).
- ③**FinalStatus**(검증신뢰, `verification.py:27-30` CONFIRMED/NEEDS_REVIEW/BLOCKED; FinalGate `final_gate.py:18-47`; report item.status 실제 출처 `pipeline:354 gated.status.value`; BLOCKED 사유 incl `citation_unverified` `final_gate.py:23`).
- ④**ReportStatus**(`report.py:14-18` +**DISCRETION_HELD**; `report_builder.py:_STATUS_MAP`가 FinalStatus 매핑, no_criterion/discretion→DISCRETION_HELD+verdict=None `:24-27,41`).
- 플랫폼 `overall.verdict`(부적합/조건부적합/적합/판정불가=fail/conditional/pass/None). → Verdict와 status는 독립 차원, **둘 다 보존**(DISCRETION_HELD는 verdict=None 예외).
- **셀 매핑**(Verdict × ReportStatus → 플랫폼 표시): (COMPLIANT,CONFIRMED)→적합 · (NON_COMPLIANT,CONFIRMED)→부적합 · (CONDITIONAL,CONFIRMED)→조건부적합 · (any,NEEDS_REVIEW)→판정 보존+검증보류 배지 · (any,BLOCKED)→검증실패(인용 미검증 등) · (—,DISCRETION_HELD)→판정불가(verdict=None). GatedStatus(②)는 `result.findings[]`에만 존재, report item.status로 미사용 — 혼동 금지.
- ⚠️ **per-item input_hash 구분**: `report.items[].input_hash`는 `audit_binder.py`가 항목별로 `input_hash({item_id, raw, snapshot_id})`로 산출하는 **감사 해시**로, 최상위 `AnalysisResult.input_hash`(`{"input": inp.model_dump}`)와 **다른 차원**(§9 R7 parity는 최상위만 대상).

### image_ref SSRF (전면 차단)
BFF는 외부 URL을 엔진에 전달하지 않는다. 허용=플랫폼 스토리지 객체키(`^storage://<bucket>/<tenant_id>/.+`, tenant 일치로 IDOR 차단)만 → **BFF가 서버측 직접 읽어 `data:image/<mime>;base64,...`로 변환해 `drawings[].image_ref`에 주입**(엔진 외부 fetch 0 → SSRF/DNS rebinding 무효; 엔진 `image_source.py:56-66` data: 분기만). http(s)·외부도메인 전면 422. 엔진 `_is_safe_url`(`:37-48` 디나이리스트, DNS rebinding 취약)은 방어심화로만.

## 7. 로드맵 (Phase 0~6)
- **P0**: API_TOKEN(≥32B) 엔진 `.env.secrets`+플랫폼 `.env` 수기 동일값(export 스크립트 미사용). `project_dashboard` 헬스카드(BFF `/deliberation/health`가 엔진 `/api/v1/doctor` 인증 후 **화이트리스트 필드만**{database.configured,sheet_classifier.live,jurisdiction.live,embedder.semantic} 재발행; api_auth.enabled·*_key_present·model 미전달). 게이트: 무토큰 `/analyze`→401; staging도 ENV=production/토큰 강제.
- **P1**(BFF): `routers/deliberation.py` — §5 계약(인증·degrade·breaker·감사·input_hash 선계산·run_id↔tenant). `DeliberationConsole.tsx`: `${ENGINE_URL}/api/v1/analyze` 직결(`:138`)→동일출처 `/api/v1/deliberation/analyze`(ENGINE_URL/NEXT_PUBLIC_* 제거); TS 타입=§6 evidence 1:1. 기존 경로 무손상.
- **P2**(입력 어댑터): 컨텍스트→AnalysisInput(§6 전 필드, pnu 선해소·rules 카탈로그·의미분류). 네트워크 입력→async.
- **P3**(면적·검증 shadow): `project_pipeline._calculate_area_from_geometry`·efficiency_metrics→엔진 geometry_area+area_sanity+§119+CalcTrace shadow(BFF). VerifierService/calc_ledger/range_rules→엔진 final_gate/cross_validate thin.
- **P4**(Blocking+SSOT): `_verify_stage` fail→후속 SKIPPED+사유. 8엔진→엔진 R3+FinalGate (변환)위임. warn-only→enforce.
- **P5**(교차검증·SSOT·재현성): 1차출처 어댑터 엔진 일원화. **ZONE_LIMITS 16곳→reg_graph 단일주입**. 플랫폼 `analysis_ledger`(public, 031)에 `input_hash`/`snapshot_id` 컬럼 additive(`ADD COLUMN IF NOT EXISTS`, downgrade 무동작). `regulation_monitor`→reconcile 트리거.
- **P6**(오케스트레이션 통일): comprehensive/pipeline/ai_analyze→엔진 게이트웨이. SIGUNGU_BASE_PRICES→교차검증. BaseInterpreter 9종·ExpertPanel→Rationale/legal_refs/CalcTrace.

## 8. 도메인 수렴
① 면적 → ② 법규(rules 카탈로그) → ③ 교차검증(P5) → ④ 도면·BIM. 각 shadow→divergence→warn-only→authoritative.

## 9. 리스크·완화·롤백
| 리스크 | 완화 |
|---|---|
|(1) 단일 진입점|Redis 공유 breaker(§5)+degrade+/async 격리|
|(2) 계약 단절·중첩 rules[]|pydantic 선검증+정적 카탈로그+422/skipped(KeyError→500 우회)|
|(3) 이중 호출|P5 어댑터 일원화까지 한시|
|(4) 결정론 오염|as_of 치환·LLM 배제·3튜플·cached_get 교차스냅샷 가드(§3)|
|(5) 판정 SSOT 회귀|shadow 병존+divergence 후 전환|
|(6) 멀티테넌시|엔진 `analysis_run` org 컬럼 보유(`base.py`)나 save 미채움·get 무필터·RLS 없음 → BFF `engine_run_binding`로 1차 강제 + **#8 엔진 get_analysis(org 필터) 병행 필수**(BFF 단일계층은 토큰유출/네트워크누락 단일실패 취약). 테넌트 정규화=`tenant_id.hex`(32자 소문자) 고정|
|(7) 비원자 2단계 쓰기|**input_hash BFF 선계산**(vendored 헬퍼 §5 패키지격리): `inp=AnalysisInput(**payload)` 인스턴스화 → `dump=inp.model_dump(mode="json")`(pydantic 기본값 채움: snapshot_id "snap-1" 등) → `input_hash=sha256(canonical({"input": dump}))`(**래퍼 키 `"input"` 필수**, 엔진 `pipeline:57`+`core/hashing.py:11-20` 비트동일). **content_input_hash=`sha256(canonical({k:v for k,v in dump.items() if k!="snapshot_id"}))`**(snapshot_id 단 하나만 제외, reconcile가 snapshot 주입해 input_hash 변동 `reconcile_tasks.py:191`). 흐름: (tenant,content_input_hash) 조회→미존재 시만 엔진 호출→응답 `AnalysisResult.input_hash==선계산` 검증(불일치=invalid_response)→UNIQUE INSERT, IntegrityError 시 기존 재사용. ⚠️ drawings 포함 run은 VLLM 비결정이라 멱등 재사용 제외(§3).|
|(8) 이벤트루프 블로킹|네트워크 입력 async 강제|
|(9) image_ref SSRF|storage:// 객체키만→BFF data-uri 변환(§6)|
|(10) 비동기 결과 유실|task SUCCESS시 BFF 영속+platform run_id, FAILURE/TTL/timeout 분기(§5)|
|(11) 부분응답 무음|pydantic strict→NEEDS_REVIEW|
**롤백**: feature flag 병존 원복. 엔진 수정 Phase(#8)는 별도 합의.

## 10. 미해결 결정 (추천)
1. 전환: A 점진→B 수렴 [추천]. 2. SSOT: B 변환 [추천]. 3. 재현성 컬럼: P5 [추천]. 4. 게이트: warn-only→enforce [추천]. 5. 실연동 인프라(운영/데이터팀). 6. 동기/async [추천]. 7. 테넌트: BFF binding [추천]+#8 병행.
8. **엔진 소규모 수정 묶음 승인**(BFF 우회로 1차 가능하나 근본 해결): (a) `get_analysis` org 필터(교차read 차단), (b) 전역 `CONSUMER_LIVE_OFF` 게이트(`cached_get`+vision/jurisdiction/embedding 라이브 오프)+`cache_key`에 snapshot 결합(교차스냅샷), (c) 비동기 결과 영속, (d) **모든 비-health 라우트 require_token**(/doctor·/reports/build·/analyze/async·/task·/UI), (e) `AnalysisResult` `model_config=ConfigDict(extra="forbid")`+run_id 필수화(부분응답 의미오염 차단), (f) (플랫폼) `_count_entries` audit quota 제외. — 묶어 별도 Phase로 할지.

## 11. 첫 증분 (P0+P1) — 구현 가능 수준
- **P0**: 엔진 `.env.secrets` API_TOKEN(≥32B)+플랫폼 `.env` 수기 동일값. `/deliberation/health`(엔진 doctor 인증후 화이트리스트 재발행). 게이트=무토큰 401.
- **P1**: `routers/deliberation.py`
  - `POST /deliberation/analyze`: `Depends(get_current_user)`(auth_service) → 입력 pydantic 선검증 → **input_hash/content_input_hash 선계산**(vendored 헬퍼 §9 R7) → `engine_run_binding`(tenant, content_input_hash) 조회(있으면 GET 재사용) → httpx(Bearer, §5 timeout/breaker) → 응답 역직렬화·`input_hash==선계산` 검증 → ⚠️ **`run_id is None or not _is_uuid(run_id)` 가드**(엔진 `run_id: str|None` `analysis.py:69` → None 통과 가능; None이면 NEEDS_REVIEW+invalid_response·binding INSERT 안 함) → 정상/`degraded` 봉투 → UNIQUE INSERT(IntegrityError 시 재조회) → `append_audit`(반환 dict ok/unchanged/quota_exceeded 분기, §5).
  - `GET /deliberation/analyze/{run_id}`: `engine_run_binding`(tenant 일치, `tenant_id.hex`) 확인 후만 엔진 GET 프록시(source=async면 BFF 영속본); 불일치/미존재 404. 엔진 GET 외부 비노출.
  - `DeliberationConsole.tsx`(**최소범위**): ENGINE_URL/NEXT_PUBLIC_* 제거→동일출처 `fetch("/api/v1/deliberation/analyze")`(`:13-14,138`); 응답 봉투 `{degraded,result,reason}` 처리(degraded면 reason 배너); **기존 간이 렌더(report.sections·findings) 보존(무손상)**. §6 evidence 풀스키마 TS 재작성은 **P2 UI에서**(P1 비범위).
  - RBAC 세분화·비-analyze 인증·엔진수정(#8)은 P1 비범위.

## 12. 데이터모델 (신규 alembic — 플랫폼 **public** 스키마)
⚠️ **alembic 디렉터리는 `apps/api/database/migrations/versions/`(정본, alembic.ini script_location; `031_analysis_ledger` 소재) — `apps/api/alembic/`(별도 2파일)는 미사용**. 신규 리비전 전 **`cd apps/api && alembic heads`로 head 집합 직접 재실측**(환경/워크트리별 상이 — trust_infra 기준 다수 head; 현 워크트리는 004/005만일 수 있음). 다중 head면 `alembic merge`로 묶는 merge 리비전 선행 후 그 위에. 신규 2객체(engine_run_binding/shadow_comparison)는 **플랫폼 public**(엔진 review 아님); run_id는 `review.analysis_run.id` 논리참조하나 **외래키 없음**(엔진 무수정+BFF 응답 후 INSERT). `gen_random_uuid` 가용. ⚠️ **`analysis_ledger`는 alembic이 아니라 런타임 `analysis_ledger_service.py:23-39 _DDL`(`CREATE TABLE IF NOT EXISTS`)로 생성** → 컬럼 추가는 (1) `_DDL`에 `input_hash text, snapshot_id text` 추가 + (2) `_ensure` 직후 멱등 `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. 별도 alembic 리비전을 둘 경우 `CREATE` 두지 말고 `ADD COLUMN IF NOT EXISTS`만(테이블이 _ensure로 선생성됐을 수 있음).
```sql
CREATE TABLE engine_run_binding (
  run_id UUID PRIMARY KEY,            -- sync=엔진 analysis_run.id, async=BFF 발급 uuid
  engine_task_id TEXT, source TEXT NOT NULL CHECK(source IN ('sync','async')),
  tenant_id TEXT NOT NULL,            -- current_user.tenant_id.hex (32자 소문자)
  project_id TEXT, created_by TEXT,
  input_hash TEXT NOT NULL,           -- 엔진 AnalysisResult.input_hash
  content_input_hash TEXT NOT NULL,   -- snapshot_id 제외 정규화 해시(멱등·lineage)
  snapshot_id TEXT, status TEXT,
  result JSONB,                       -- async 영속본(엔진 미저장 대비)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_run_tenant_content UNIQUE (tenant_id, content_input_hash, snapshot_id)
);
CREATE INDEX idx_binding_tenant_run ON engine_run_binding(tenant_id, run_id);

CREATE TABLE shadow_comparison (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL, tenant_id TEXT NOT NULL, domain TEXT NOT NULL,
  engine_verdict TEXT, platform_verdict TEXT,
  field_diffs JSONB NOT NULL DEFAULT '[]', divergence_score NUMERIC(6,4) NOT NULL,
  environmental BOOLEAN NOT NULL DEFAULT false,
  engine_degraded BOOLEAN NOT NULL DEFAULT false, mirror_loaded BOOLEAN, cache_warm BOOLEAN,
  as_of DATE, ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_shadow_domain ON shadow_comparison(tenant_id, domain, ts DESC);

ALTER TABLE analysis_ledger ADD COLUMN IF NOT EXISTS input_hash TEXT;
ALTER TABLE analysis_ledger ADD COLUMN IF NOT EXISTS snapshot_id TEXT;  -- downgrade 무동작(031 정책)
```
감사는 신규 컬럼 없이 **`append_audit`→payload.metadata JSONB**에 {input_hash,content_input_hash,http_status,decision,engine_url,request_id} 적재(전용 컬럼 없음; 내부 `event_id`/`event_ts` 유일로 dedup 회피, `audit_ledger.py:65`). audit은 라이브러리 고정 `analysis_type="audit"`(오버라이드 불가)·합성주소 `__audit__/<tenant>` 체인.

## 13. 검증 게이트 (9.5)
- 엔진 전체 스위트 무회귀(현 419, 무수정 구간)+플랫폼 신규 테스트(BFF 인증·degrade 봉투·매핑 422·부분응답·테넌트 격리 404·감사 fail-closed·**input_hash canonical parity**·**교차스냅샷 캐시 격리**) green.
- 결정론: 순수 경로 input_hash 동치; 네트워크 경로는 snapshot 워밍.
- 무음0: 엔진 미연결·무결성·매핑·계층결손·감사실패(dict ok 검사) 전부 표면화.
- INV-13: 소비경로 직접 httpx 0(정적스캔)+cached_get 토글 OFF시 fetch 0.
- 테넌트: run_id 교차테넌트 404(`tenant_id.hex` 정규화) + (#8 채택 시) 엔진 get_analysis org 필터.
- 감사: 모든 요청 audit 행, write 실패 시 거부.
- shadow: `shadow_comparison` 집계 승격 쿼리·(N,ε)·environmental 제외.
- 각 Phase 적대 리뷰 **전 렌즈 ≥9.5**.

---
부록 A. 트랙: 플랫폼=trust_infra 기반 신규 통합 워크트리, 엔진=`feature/deliberation-review` 무수정(엔진수정#8 별도 합의). 협업=Workflow.
부록 B. 근거: 9-에이전트 설계+4-렌즈 코드대조+7-렌즈 9.5 시뮬 2R(65결함 정정). 다음 라운드 코드 재대조로 ≥9.5 수렴 확인.
