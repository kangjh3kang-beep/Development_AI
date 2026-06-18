# 중심 엔진 통합 설계 (Central Analysis Engine Integration Design) — v7

> 근거: 9-에이전트 설계 + 4-렌즈 코드대조 + **7-렌즈 9.5 시뮬레이션 5라운드**(R1 36·R2 29·R3 29·R4 23·R5 20 정정). **수렴 추이 min 7.0→7.5→7.5→8.5→8.0**(R5 8.0은 v6 회귀[vendored 4필드 forbid]+신규 §6A+실질 통합결함 발견 때문). v7=R5 정정(★vendored 모델 회귀 복구=전체 25필드 미러 extra=ignore·request_id @staticmethod·DISCRETION_HELD는 qualitative만·element_id Optional·#8(a) P1 필수·apiClient 별오리진·BimElement.storey 미충전·멱등 조회키 snapshot 포함·divergence nullable+verdict 정규화·storage Supabase 현실·mirror/vision 교차스냅샷·circuit-breaker outcome 분류·config 키). **루프가 발견한 핵심: 통합은 순수 additive 아님 — 플랫폼+엔진 소규모 수정 묶음(#8·storage prefix·config·rate-limit) 필요.**
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
- **결정론(확장 단위)**: `input_hash`=AnalysisInput만 해싱(`analysis_pipeline.py:57`). 라이브 어댑터 산출(geocode/land_card/surrounding/cross_facts via `cached_get`) 반영 시 input_hash 동일≠결과 동일. **진짜 단위=(input_hash, snapshot_id, source_cache 적재상태, vision 추출 캐시 적재상태)**. ⚠️ **VLLM 도면 자동해석**(`drawing_extractor.py:139`, temperature=0 best-effort, vision_cache는 snapshot 없음·프로세스로컬) 포함 run은 **"순수 경로" 아님**. **순수경로=다음 라이브/비결정 발화 필드가 전부 비어/거짓인 입력만**: drawings/ifc/elements(VLLM), address(빈값 또는 pnu 19자리 — `pipeline:205` geocoder 미발화), cross_facts(law_query/building_pnu/land_pnu/land_use_pnu 자동합류 라이브 `:285-312`), collect_land_card/collect_surrounding(라이브 수집), mirror_rules 미제공+SUPPLY_STORE 적재상태 의존(`:187`). 즉 순수경로=pnu(19자리)·application_date·axis_date·snapshot_id·calc_targets·rules·sim_inputs·citations·qual_facts만. 그 외는 snapshot 워밍(clear()+warm_from_db)으로만 재현성. 결정론 게이트 픽스처는 위 라이브필드 0을 어서션. ⚠️ **`cached_get` L1 조회키=cache_key(adapter,endpoint,params)로 snapshot_id 미포함**(`source_cache.py:62-69,91-99`) → 스냅샷 A 캐시가 B 분석에 반환되는 교차스냅샷 오염 가능. 운영 재현성 보증엔 (a) cache_key에 snapshot 결합(엔진 수정#8) 또는 (b) 스냅샷 경계마다 `source_cache.clear()+warm_from_db(snapshot_id)`. 결정론 게이트는 **순수 경로(rules/calc_targets만)**에서만 input_hash 동치 검증; 네트워크 경로는 snapshot 워밍으로만.
- **무음0**: `skipped[]` 보존. 매핑 실패는 **자동 422 아님**(§6 KeyError→500) → BFF 선검증으로 422/skipped.
- **INV-13(실계약)**: 강제 스캐너 2개 — (1) `test_consume_static.py`(consume/+services/verify/에서 httpx/aiohttp/openai/anthropic **전면 0**, `:19="aiohttp"`), (2) `test_live_call_scan.py`(adapters/regulation·legal, services/land·cross_validate는 `cached_get` 경유만 허용). *라이브 0 아님*. run_analysis는 키 보유 시 `cached_get→httpx.get`(`source_cache.py:157`)로 law/molit/vworld/geocode/land_card fetch. ⚠️ **두 스캐너가 vision/jurisdiction/embedding 어댑터는 미커버** — `drawing_extractor.py:139`·`vllm_sheet_classifier.py:75`·`jurisdiction/vworld.py`·`embedding/embedding_client.py`는 cached_get·LIVE_NETWORK **우회 직접 httpx 라이브**(키 보유 시 발신). **`LIVE_NETWORK`은 공급 `network.py`(LiveNetwork)만 게이트**. 운영 전면 차단엔 전역 게이트 `settings.CONSUMER_LIVE_OFF` 신설(엔진 수정#8 (b), vision/jurisdiction/embedding 포함) 또는 BFF가 drawings/address/issue+corpus 입력을 명시 동의 없이 미전달.
- **설명가능성(중첩)**: 최상위=`findings[]`·`legal_quantities[]`·`cross_validations[]`·`reg_graph`·`report`·`skipped[]`. 중첩=`legal_basis`/`gate_reason`/`dual_path`(`report.items[].evidence`), `CalcTrace`(`legal_quantities[].calc_trace`), `rationale`(`precedent.rationale`). BFF 평탄화 금지·report 전체 직렬화. TS=evidence 스키마 기준(§6).

## 4. 아키텍처
```
[apps/web] DeliberationConsole → apiClient(API 오리진·Bearer) → BFF  ※웹≠API 동일출처 아님(api-client.ts:63-76); CORS_ORIGINS에 웹 오리진 포함
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
- **circuit-breaker**: `from apps.api.integrations.base_client import CircuitBreaker` — `__init__(failure_threshold, recovery_timeout=60.0, half_open_max)`만, **`service_name` 인자 없음**(`base_client.py:162`); `can_execute()/record_success()/record_failure()`만(httpx 미래핑, `:159-216`). ⚠️ **인스턴스 상태=프로세스 로컬**(`apps/api/app/core/rate_limit.py:7` 선례) → 다중워커 미공유. **운영(워커>1)은 Redis 공유 breaker 필수**: 키 `deliberation_engine:cb:{state,failures,half_open_tokens}`, 전이 Lua(EVAL) 원자화, half-open 동시진입은 `SET NX EX` 토큰버킷, **Redis 장애 시 fail-safe(CLOSED 간주+타임아웃 단축+경보, 무음 금지)**. **P1 기본=단일워커 강제**(uvicorn -w 1; `-w>1`이면 부팅 거부 — 매니페스트 게이트) + in-memory `cb = CircuitBreaker(failure_threshold=5, recovery_timeout=75.0, half_open_max=3)` 단일 인스턴스 → P1 완전 구현 가능·발명요소 0. **Redis 공유 breaker는 후속 Phase(P1 비범위, 별도 설계)**. OPEN 중=엔진 skip→shadow기 폴백/authoritative기 즉시 NEEDS_REVIEW. ⚠️ **outcome 분류**(CircuitBreaker는 httpx 미래핑 → BFF 수동 record): `record_failure`=**서버측 장애만**(connect/read timeout·ConnectError·HTTP 5xx); `record_success`=엔진 도달(<500, 4xx 포함). **엔진 422(매핑오류=클라)·401·quota_exceeded·malformed-body(200 비-dict/JSON 파손)는 breaker 카운트 제외**(client-error/한도/도달-후-본문 storm로 OPEN→정상요청 동반붕괴 방지; 이들은 record_success로 도달 사실만 기록=중립). ⚠️ **단 200+parity 위반(input_hash 불일치/run_id 비UUID)은 record_failure**(엔진 계약 장애=서버측 drift — 격리된 클라 4xx와 달리 반복 시 systemic이므로 OPEN으로 무음 지속 차단; v8 구현결정, R-impl 검증). reuse/GET 조회(_engine_get_analysis)도 동일 분류 대칭(can_execute 가드+5xx/예외 record_failure+도달 record_success). config(`apps/api/app/core/config.py` Settings 신규): `DELIBERATION_ENGINE_URL=""`(빈값→degrade engine_unreachable)·`_API_TOKEN`·`_CONNECT_TIMEOUT_S=5.0`·`_READ_TIMEOUT_S=30.0`·`_ASYNC_READ_TIMEOUT_S=60.0`(`httpx.Timeout(connect,read)`).
- **패키지 격리(중요)**: BFF(플랫폼 패키지 `app`)와 엔진(top-level 패키지명도 `app` `analysis_pipeline.py:13`) **import 충돌** → 엔진 import 불가. → 플랫폼 `apps/api/app/services/deliberation/_engine_contract.py`에 **vendoring**(엔진 버전 핀+parity 테스트 drift 검출): ① `def canonical(d): return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",",":"), default=str)` (엔진 `core/hashing.py:9-11`과 **글자단위 동일** — 3파라미터 어긋나면 멱등/parity 무음파손), `input_hash=sha256(canonical({"input": inp.model_dump(mode="json")}).encode()).hexdigest()`; ② AnalysisInput 미러 모델(동일 필드·default); ③ **응답 무결성=명시적 필수필드 게이트**(v8 구현결정): 엔진 결과를 클라이언트에 **verbatim 전달**(평탄화 금지·report 전체)하므로 25필드 전체 미러 역직렬화 대신 `_integrity_ok`(isinstance dict AND `report` not None AND `input_hash==선계산`) + POST 게이트 `_is_uuid(run_id)`로 엔진 AnalysisResult 필수(snapshot_id·input_hash·report; run_id는 Optional이라 BFF가 UUID 별도강제)를 강제. 전 결과반환 경로(신규 POST·reuse 저장본/라이브·race 승자·GET)에 대칭 적용. **입력측은 엔진 서브모델 제약을 vendored 선검증**(prevalidate: CalcElement.semantic_type 필수·confidence∈[0,1]·Rule.rule_id·SourceValue source+value+타입·PrecedentCase.case_id·rules row confidence∈[0,1])해 엔진 ValidationError→500을 422로 선차단. (전체 25필드 미러는 유지비/false-422 위험 대비 이득 낮아 미채택 — 필수필드 게이트로 동일 안전 달성.)
- **타임아웃**: connect=5s; 순수 동기 read=30s; 네트워크입력 동기는 누적 15~20s×N(N≈3) → read=60s 또는 async 강제. settings 노출.
- **degrade 봉투**: HTTP **200**, `{"degraded":true,"final_status":"NEEDS_REVIEW","reason":"engine_unreachable|engine_rejected|timeout|circuit_open|invalid_response|result_missing|engine_task_failed|async_result_lost|async_timeout","engine_configured":bool,"result":null,"audit_degraded":bool,"audit_skipped":[str]}`. ⚠️ **내부 엔진 URL 비노출**(`engine_url` 대신 `engine_configured:bool` — 보안태세 핑거프린트 차단, v8 구현결정). reason 추가분: `engine_rejected`=엔진 4xx(토큰/계약, breaker 중립), `result_missing`=엔진 404(저장 run 분실). 정상=`{"degraded":false,"result":<AnalysisResult>,"audit_degraded":bool,"audit_skipped":[str]}`. ⚠️ **audit 정책(v8 개정)**: read 경로 quota/실패는 `audit_degraded=true`로 표면화·결과 반환(502 아님); **write 경로(analyze/reuse)의 quota_exceeded·write_failed·not_ok는 502 fail-closed**(원장 미적재=감사 없는 권위 판정 제공 금지 — quota도 write_failed와 위험 동일). degrade 봉투에도 `audit_degraded:false` 포함해 양 봉투 일관(§6 TS 동일). 합성 AnalysisResult 미생성(report 필수·emit EvidenceMissing 회피, `analysis.py:94`/`report.py:43`).
- **부분응답**: HTTP200이나 본문 결손/파손 → pydantic `AnalysisResult` strict 역직렬화, ValidationError·필수(run_id/input_hash/report) 결손 시 NEEDS_REVIEW+`invalid_response`(shadow는 별도 기록=false divergence 차단), 절단은 breaker 실패 카운트.
- **감사(audit)**: raw INSERT 금지. **`await app.services.ledger.audit_ledger.append_audit(*, action=…, user_id=str(user.id), resource_type="deliberation", resource_id=engine_run_id, tenant_id=user.tenant_id.hex, metadata={input_hash, content_input_hash, http_status, decision, engine_url, request_id})`** — **전 인자 keyword-only**(`audit_ledger.py:52`). analysis_type은 라이브러리 고정 `"audit"`(`AUDIT_ANALYSIS_TYPE :18`; "deliberation_audit" 불가 — deliberation 구분은 `resource_type`/`metadata`). 합성 체인주소 `__audit__/<tenant>`(`:21-23`), dedup은 내부 `event_id=uuid4().hex`+`event_ts=time.time()`로 회피(`:65`). ⚠️ **append_analysis는 raise 안 함**(`analysis_ledger_service.py:242` 전예외→`{ok:False}`; `:218` content_hash 동일 시 `unchanged`; `:226` `quota_exceeded`). 반환 dict 분기: `ok or unchanged` → 통과; **일반 실패(`not ok and not unchanged and not quota_exceeded`) → 502 fail-closed**; **`quota_exceeded` → 분석 결과는 반환하되 응답 `audit_degraded=true`+skipped 표면화+운영경보**(감사 무음 금지·가용성 보존, 502 아님). ⚠️ **audit은 분석과 동일 테넌트 quota 공유**(`_count_entries` analysis_type 무필터 `:95`) → **P0 선행 플랫폼 수정**: `_count_entries`에 `AND analysis_type<>'audit'` 추가(감사가 분석 quota 잠식 방지).

### 동기/비동기 (코드 현실)
- 분류: 네트워크 의존 입력(collect_land_card/collect_surrounding/address/실어댑터)→**async 강제**; 동기는 순수 결정론 입력만. (엔진 `analysis_routes.py`가 `async def`인데 `run_analysis` 동기 호출+동기 httpx 15~20s+`run_in_executor` 부재 → 이벤트루프 블로킹.)
- ⚠️ **run_id는 동기 `save_analysis`(`analysis_store.py:19`)에서만 부여**. async `/analyze/async`(`analysis_routes.py:57-65`)는 `{task_id}` 반환·`analyze_task`는 결과 미저장(run_id None, `analysis.py:69`). → **run_id↔tenant 결속·GET 프록시는 동기 전용**. async 필요 시: BFF가 task SUCCESS 수신 시 `platform_run_id=uuid4()` 발급, `engine_run_binding(run_id=platform_run_id, engine_task_id=task_id, source='async')` 저장+결과 플랫폼 영속, GET은 BFF 영속본 반환(엔진 미저장). 폴링 분기: `status==FAILURE`→즉시 `engine_task_failed`; `SUCCESS and result is None`→`async_result_lost`(redis TTL); `PENDING/STARTED/RETRY and <timeout`→재폴링; `≥timeout`→`async_timeout`. (엔진 비동기 영속 원하면 엔진 수정#8.)

### shadow 모드 (데이터모델 §12)
- 비교: verdict·핵심정량(면적/far/bcr)·FinalStatus·cross_validation.
- **divergence_score 산식**(0=완전일치~1=verdict 불일치): `max(verdict_mismatch, quant_rel_err)`. ⚠️ **verdict 정규화 필수**(엔진 enum COMPLIANT/NON_COMPLIANT/CONDITIONAL vs 플랫폼 한국어 적합/부적합/조건부적합 직접비교는 항상 거짓 divergence): `_norm`: COMPLIANT|적합→pass, NON_COMPLIANT|부적합→fail, CONDITIONAL|조건부적합→conditional, None|DISCRETION_HELD|판정불가→None. `verdict_mismatch`=1.0 if `_norm(eng)!=_norm(plat)` else 0(둘 중 하나라도 None=0 관측제외). `quant_rel_err`=max over k∈{area,far,bcr} of `|eng_k−plat_k|/max(|eng_k|,1e-9)`(한쪽 None은 k 제외, 둘 다 None=0). 승격 ε: 면적=quant_rel_err≤0.01 AND verdict 일치, 법규=verdict 완전일치(quant 무관). `field_diffs[]`={field, engine, platform, rel_err}.
- **쓰기 경로**: INSERT 시점=sync 응답 직후(async는 BFF 영속 직후), best-effort(실패는 분석 응답 미차단·warn). `platform_verdict` 출처=도메인 기존 플랫폼 산출(P3 면적=`project_pipeline._calculate_area_from_geometry`+efficiency_metrics, P4 판정=`design_audit_orchestrator` overall.verdict); **P1/P2는 platform_verdict=NULL(divergence 미산출·관측 전용)**. 환경필드: `mirror_loaded`=(result.mirror_source is not None), `cache_warm`=(cache 적재실패 skipped 부재), `engine_degraded`=(degrade 봉투 degraded). degrade로 run 없으면 미기록.
- **환경 분리**: `engine_degraded/mirror_loaded/cache_warm`(doctor/skipped[] 도출) 기록 → `engine_degraded OR not mirror_loaded`=`environmental`로 승격 모수 제외(미러 미적재 시 엔진 보수판정→체계적 divergence).
- **storm 가드**: divergence율 임계 초과 시 도메인 자동 warn-only+알림.
- **승격(측정)**: `SELECT count(*) FROM shadow_comparison WHERE domain=? AND tenant_id=? AND divergence_score<:eps AND environmental=false ORDER BY ts DESC LIMIT :N` — 최근 N건 전부 <ε이면 후보(사람 확인). 기본: 면적 N=50/ε=0.01, 법규 N=100/ε=0.

## 6. 계약 매핑 (목표 9.5)

### 입력 `AnalysisInput`(`contracts/analysis.py:25-65`) — 전 필드 출처/도출
| AnalysisInput 필드 | 플랫폼 출처/도출 | 미제공 시 |
|---|---|---|
| `pnu` | `site.pnu`(`design_audit_orchestrator.py:433` 존재) 또는 address→PNU 지오코딩(Phase2, BFF 선해소) | 빈값 → 미러 무음공백 → BFF가 422/skipped |
| `application_date` | ⚠️ 플랫폼 design_audit에 **직접 필드 없음**(grep 0) → BFF가 신청서 메타/프로젝트 생성일에서 도출·명시 주입(date ISO) | 미주입 시 axis만 `axis_date or application_date or date(2026,1,1)` 보정(`pipeline:63`)·application_date 자체는 None → calc base_date(`:107`)·신선도 as_of(`:312`)·인용 시행일(`:198`) None=보수 게이팅 |
| `address` | design_audit `site.address`(`orchestrator:431`) 또는 사용자 지번/도로명 | `len(pnu)<19`일 때만 VWORLD 지오코딩 발화(`pipeline:205`); 키 없으면 `geocode: 지오코더 미설정` skip; `collect_surrounding`은 geocoded.lon 필요(`:219`)→미해소 시 주변/일조 skip |
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
| `cross_facts[]` | `[{fact_key(필수·결손=KeyError→500 `pipeline:312`), sources:[SourceValue], law_query?, law_expect?, building_pnu?+building_metric?, land_pnu?+land_year?, land_use_pnu?+land_use_contains?}]`. 키 보유 시 law/MOLIT/VWORLD landprice·landuse 자동합류(`pipeline:283-312`). `SourceValue`(`cross_validation.py:16-30`)={source, value(str\|float\|int\|None), ref?, collected_at?, data_vintage?, max_age_days?}. **BFF가 fact_key/SourceValue 서브모델 선검증→422/skip**(KeyError/ValidationError→500 우회) | cross-validate skip |
| `mirror_rules[]` | 미제공 시 엔진 `default_store().get(pnu)`(`pipeline:182`, SUPPLY_STORE) | 미적재 보수 게이팅 |
| `collect_land_card`/`collect_surrounding` | BFF 기본 False(라이브 게이트, async) | — |
| `land_year` | '2024' 기본(`pipeline:253`) | — |
| `surrounding_radius_m` | 150 기본 | — |
| `proposed_floors` | 경관심의(collect_surrounding 동반) | skip |
| `qual_facts` | 정성(L3-C) | skip |

**design_audit RunRequest 실제 필드**(`design_audit.py:257-275`): `{project_id, site, params(far_pct/bcr_pct/building_height_m), geometry?, ifc_file_url?(URL), rooms?, use_llm, use_verification_retry}` — ⚠️ `ifc` 필드 없음(`ifc_file_url`만 → BFF 다운로드 필요), `site.pnu` 존재.

**`calc_targets[]`**(`calc_engine.py:119-149`): `{target(CalcTarget enum: building_area|gross_floor_area|far_floor_area|plot_area|building_height|floor_count), payload(target별 필수키), elements:[CalcElement], declared?}`. 필수 payload: building_area→`outer_area`; gross_floor_area→`floor_areas`; far_floor_area→`gross_floor_area`; plot_area→`parcel_area`; building_height→`raw_height`; floor_count→`above_ground_floors`. ⚠️ **필수 payload 키 결손만 `RuleContractError→422`**(`calc_engine.py:128`); **`target` 키 자체 결손·CalcElement/Rule 오형은 KeyError/ValidationError→500**(`pipeline:110-111`, DomainError만 422) → BFF 선검증 422/skipped. `CalcElement`(`legal_quantity.py:56-70`)={semantic_type(SemanticType enum, `semantic_element.py:15-27`), confidence, area, length, depth, element_id?, underground?(None=미상), accessory?(None=미상)}.

**`rules[]` 정적 룰 카탈로그**(check_id→Rule): `{rule:{rule_id, target_variable, comparator(Comparator enum `<= >= < > ==`, `enums.py:57-69`), depends_on:[], relaxations:[{relaxation_id, prerequisite_rule_id, effect, basis_article}], basis_article}, measured, limit, relaxation_states, confidence, conflicts}`(`analysis_pipeline.py:128`, `rule.py:12-29`). **relaxation_states**(검증 로직=`services/judge/relaxation.py:14-58`; Relaxation 모델=`contracts/rule.py:12-19`): `dict[str,str]`, 키=`prerequisite_rule_id or relaxation_id`, 값∈{MET,PROVIDED,UNVERIFIABLE,UNMET}, **누락=UNVERIFIABLE**(`relaxation.py:36` 거짓불합격 금지); MET→완화해소, PROVIDED→CONDITIONAL, UNVERIFIABLE→CONDITIONAL+requires_committee, 전부 UNMET→완화 미적용. ⚠️ **매핑 실패=KeyError/ValidationError→500**(`/analyze`는 DomainError만 422, `analysis_routes.py:38`) → **BFF 선검증 체크리스트(전부 422/skip, 미선검증 시 500)**: (1) `calc_targets[i]["target"]`∈CalcTarget enum 6값(미정의=ValueError→500 `pipeline:111`), (2) `calc_targets[i]["elements"][j]`=CalcElement(`legal_quantity.py:56-70`): `confidence`∈[0,1](Probability `_types.py:12`)·`semantic_type`∈SemanticType·`area/length/depth` finite·**`element_id`는 Optional(None 허용 `legal_quantity.py:68`)**; ⚠️ 별개 경로 `inp.elements[]`(의미분류)는 `element_classifier.py:39`가 `el["element_id"]`로 접근→**이 경로만 element_id 필수**(결손=KeyError→500), (3) `rules[i]["rule"]` 키 필수+Rule 유효(`comparator`∈Comparator)·`measured/limit` FiniteFloat(nan/inf 거부 `_types.py:16`)·`confidence`∈[0,1], (4) `cross_facts[i]["fact_key"]` 필수+`sources[]` SourceValue. 각 pydantic 서브모델(CalcTarget/Rule/CalcElement/SourceValue) 인스턴스화로 선검증.

### 의미분류 어댑터 I/O 계약
- **elements[] 입력**(`dual_path.py:13`, `element_classifier.py:26-44`): 요소 dict=`{element_id, features:{semantic_hint(SemanticType 이름 또는 UNKNOWN), hint_strength(0~1)}, present_in_sheets?}`; hint이 SemanticType 멤버+strength≥param('element_classify_min_confidence')여야 채택, 아니면 UNKNOWN 하향. cad_upload_hub design_raw(px)·params_hint는 의미타입 없음 → **직매핑 불가**, 의미분류 후에만.
- **IFC**(`ifc_parser.py:39-116`): 엔진 `ifc`=STEP 텍스트 → `BimModel{elements:[BimElement{ifc_type, semantic_type, name, guid, storey, area, length}], source}`(타입맵 IFCWALL→EXT_WALL + 이름키워드 '지하'→BASEMENT, 미매핑 UNKNOWN). ⚠️ **BimElement엔 underground/accessory/depth 없음**(`bim.py:12-19`) → FAR 제외적격(§119①4 지하AND부속) CalcElement 변환은 name/storey 키워드로 추론하되 **미상은 None 유지→CalcEngine HELD 표면화**(`calc_engine.py:92-97`). 이 BimElement→CalcElement 규칙을 **신규 배선**으로 명문화(현재 플랫폼 BIM 물량→엔진 calc 경로 전무): **area is not None인 요소만 채택**(area=`BimElement.area`; CalcElement.area는 비널 float=0.0 `legal_quantity.py:65` → None 주입 시 ValidationError→500, area None은 제외+`skipped` 표면화), length=`.length or 0.0`, depth=0.0. ⚠️ **underground/accessory 추론은 `BimElement.name` 키워드만**(`ifc_parser._NAME_HINTS :48-55`); **`BimElement.storey`는 경량 IfcParser가 미충전(`:108-115` 항상 None)이라 추론 근거로 사용 불가** — storey 기반은 IfcRelContainedInSpatialStructure 파싱 신설(엔진수정#8) 후에만. 미상 None→CalcEngine HELD(`calc_engine.py:92-97`). `calc_target_builder.py:23-28` 도면경로와 동일 가드.

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
- ④**ReportStatus**(`report.py:14-18` +DISCRETION_HELD). ⚠️ **실측 도달성**: `run_analysis` items.append 3곳(`pipeline:348/381/397`)이 no_criterion/discretion 키를 미설정 → `report.items[].status`는 **CONFIRMED/NEEDS_REVIEW/BLOCKED만** 산출(DISCRETION_HELD 미발화, `report_builder.py:25-27`). **DISCRETION_HELD(판정불가, verdict=None)는 `AnalysisResult.qualitative[].status`(QualStatus, `qual_evaluator.py:41-43`)에만 존재** → 플랫폼 '판정불가' 표시는 report.items가 아니라 **result.qualitative[]를 별도 소비**해 매핑(report.items 경유 가정 금지).
- 플랫폼 `overall.verdict`(부적합/조건부적합/적합/판정불가=fail/conditional/pass/None). → Verdict와 status는 독립 차원, **둘 다 보존**(DISCRETION_HELD는 verdict=None 예외).
- **셀 매핑**(Verdict × ReportStatus → 플랫폼 표시): (COMPLIANT,CONFIRMED)→적합 · (NON_COMPLIANT,CONFIRMED)→부적합 · (CONDITIONAL,CONFIRMED)→조건부적합 · (any,NEEDS_REVIEW)→판정 보존+검증보류 배지 · (any,BLOCKED)→검증실패(인용 미검증 등) · (—,DISCRETION_HELD)→판정불가(verdict=None). GatedStatus(②)는 `result.findings[]`에만 존재, report item.status로 미사용 — 혼동 금지.
- ⚠️ **항목 종류 축(무손실)**: `report.items[]`는 3종 혼재 — **verdict 보유는 finding뿐**. sim_metric item(`pipeline:381-386`)·precedent item(`:397-401`)은 verdict 키 없음(→ReportItem.verdict=None)·status 고정 NEEDS_REVIEW·item-level basis_article 없음(sim은 evidence.basis_article에만, precedent는 없음). **플랫폼은 evidence 키로 종류 식별**: `metric`→공학지표 확인필요 배지, `distribution`→유사사례 참고 배지, `legal_basis`+`measured`+`limit`→compliance finding. 즉 (verdict=None,NEEDS_REVIEW,evidence.metric)은 "판정 보존"이 아니라 "공학지표 권고"로 표시. §6 ReportItem 행의 verdict/basis_article은 sim/precedent에선 None 가능.
- ⚠️ **per-item input_hash 구분**: `report.items[].input_hash`는 `audit_binder.py`가 항목별로 `input_hash({item_id, raw, snapshot_id})`로 산출하는 **감사 해시**로, 최상위 `AnalysisResult.input_hash`(`{"input": inp.model_dump}`)와 **다른 차원**(§9 R7 parity는 최상위만 대상).

### image_ref SSRF (전면 차단)
BFF는 외부 URL을 엔진에 전달하지 않는다. ⚠️ **실 스토리지=Supabase Storage**(`apps/api/services/storage_service.py:upload_image`, 키=`site-images/<uuid>.<ext>` public URL·**tenant 미포함** → `storage://<bucket>/<tenant>/` 규약은 현재 부재). → **선행 플랫폼 수정**: ① `uploads.py:36` 업로드를 `deliberation/<tenant_id.hex>/<uuid>.<ext>` prefix·버킷 public=False로 저장, ② BFF는 입력으로 외부 URL이 아닌 `{bucket, object_key}`만 수용+`object_key`가 `^deliberation/<요청자 tenant_id.hex>/` 정규식 일치 시만 허용(불일치=403 IDOR), ③ Supabase `GET {SUPABASE_URL}/storage/v1/object/{bucket}/{key}`+service-role 헤더로 **서버측 다운로드→매직바이트 재검증→`data:image/<mime>;base64`로 `drawings[].image_ref` 주입**(엔진 외부 fetch 0). http(s)·외부도메인·legacy public-URL 키 전면 422. 엔진 `_is_safe_url`(`:37-48` 디나이리스트)은 방어심화로만.

## 6A. 업로드 인테이크 · 포맷 지원 · 콘솔 UX (사용자 편의 혁신)

> 현 콘솔(`DeliberationConsole.tsx` 272줄)은 **JSON textarea→`fetch(ENGINE_URL/api/v1/analyze)` 직결, 파일 업로드 0**(개발 프리뷰). 엔드유저가 JSON을 손작성해야 하는 최대 진입장벽. 포맷 **파서는 존재**하나 업로드→AnalysisInput 자동변환·검증·표시가 미배선.

### 현 포맷 처리 능력(실측)
| 포맷 | 파싱 | 위치 |
|---|---|---|
| PDF | ✅ | 엔진 `supply/parser/pdf_parser.py`(텍스트) / INC-17 PyMuPDF 페이지→시트는 **미구현** |
| HWP | ✅ | 엔진 `supply/parser/hwp_parser.py` |
| IFC(BIM) | ✅ | 엔진 `adapters/bim/ifc_parser.py`(STEP) + 플랫폼 `services/bim/*`(ifcopenshell) |
| DXF(CAD) | ✅ | 플랫폼 `services/cad/dxf_import_service.py`(ezdxf) |
| DWG | ⚠️ 직접불가 | ezdxf는 DXF만 → DWG는 변환(ODA File Converter 등) 선행 필요 |
| 이미지(PNG/JPG) | ✅ | 엔진 `adapters/vision/image_source.py`+`drawing_extractor.py`(VLLM) |
| JSON | ✅ | 콘솔 textarea(현 유일) |
**결손**: (a) 콘솔 업로드 UI 0, (b) 엔진 HTTP 업로드 엔드포인트 0(analyze는 JSON만), (c) 지원포맷 표시·검증 0, (d) DWG 변환경로 없음.

### 설계(엔진 무수정 — 업로드/파싱은 플랫폼·BFF측)
- **BFF `POST /api/v1/deliberation/upload`**(multipart, `Depends(get_current_user)`+테넌트+감사): 파일 수신 → ① **포맷 감지=매직바이트 sniff**(확장자 불신: PDF `%PDF`, PNG `\x89PNG`, JPEG `\xFF\xD8`, IFC `ISO-10303`/`FILE_DESCRIPTION`, DXF `0\nSECTION`/AutoCAD 마커, HWP `HWP Document File`/OLE `\xD0\xCF`, ZIP/DWG 시그니처) → ② **검증**(MIME 일치·크기 상한·암호화PDF·손상·미지원 → 전부 표면화, 무음0) → ③ **포맷 어댑터 디스패치** → ④ **AnalysisInput 부분 조립** 후 기존 `/deliberation/analyze`로 연결(또는 즉시 분석).
- **포맷 어댑터 레지스트리(확장성)**: `FORMAT_ADAPTERS: dict[FormatId, FormatAdapter]`(plugin). `FormatAdapter`=`{detect(head_bytes)->bool, validate(bytes)->ValidationReport, to_analysis_input(bytes, hints)->dict}`. 신규 포맷은 어댑터 1개 등록만으로 추가(DWG 변환기·추가 CAD·XLSX 면적표 등). 지원목록은 레지스트리에서 자동 도출(UI 칩·검증 양쪽 SSOT).
- **AnalysisInput 매핑**(§6 계약 재사용): 이미지→플랫폼 스토리지 저장(`storage://<bucket>/<tenant>/…`)→BFF가 data-uri 변환→`drawings[].image_ref`(SSRF 차단 경로 §6). IFC→STEP 텍스트→`ifc`. DXF→`cad_upload_hub`/`dxf_import_service`로 기하 추출→의미분류→`elements[]`/`calc_targets[]`(§6 의미분류 어댑터·area=None 가드 준수). PDF→(INC-17 신규)PyMuPDF 페이지→PNG 시트→`drawings[]`(원본 파일명·페이지 인덱스 provenance). HWP→텍스트→표제란/면적표 힌트. **DWG→변환(ODA)후 DXF 경로**(변환기 미설치 환경 graceful: `unsupported_dwg_no_converter` 표면화).
- **콘솔 UX 재설계**(`DeliberationConsole.tsx`): (1) **드래그앤드롭 + 지원포맷 칩**(레지스트리 도출, 허용 확장자/크기 표시), (2) 업로드 즉시 **검증 결과 패널**(통과/경고/거부 사유·페이지수·감지 포맷), (3) **가이드 폼**(시트 역할 선택·신청일·PNU/주소), (4) 결과 **시각화**(verdict/근거 legal_basis/skipped 배지 — §6 evidence), (5) **raw JSON은 "고급(개발자) 모드" 토글로 보존**(전문가 편의 유지). degrade 봉투 표시(§5).
- **불변식**: 업로드 파싱은 **수집 보조**(산정/판정 게이트와 분리 — 결정론 영향 0). 파싱 실패/부분추출은 `skipped`/검증리포트로 표면화(무음0). 원본 파일명·바이트해시·페이지 인덱스 provenance. 업로드 파일은 테넌트 스코프 스토리지(IDOR 차단). 크기·요청수 상한(REQUESTS_PER_MINUTE) 강제.
- **실패모드**: 암호화/손상 PDF→`pdf_encrypted`/`pdf_corrupt`; 미지원 포맷→`unsupported_format`(감지된 시그니처 표면화); 과대 파일→413; 매직바이트≠확장자→경고+감지포맷 우선; VLLM/파서 미가동→해당 추출 skip(전체 분석은 진행).
- **로드맵 편입**: §7 **Phase 1.5(업로드 인테이크+포맷 매트릭스+콘솔 드래그앤드롭, INC-17 PyMuPDF 포함)** 신설 — Phase 1(BFF) 직후, Phase 2(입력 어댑터)와 결합. 9.5 게이트·TDD(포맷별 감지·검증·매핑·실패모드 테스트) 적용.

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
|(7) 비원자 2단계 쓰기|**input_hash BFF 선계산**(vendored 헬퍼 §5 패키지격리): `inp=AnalysisInput(**payload)` 인스턴스화 → `dump=inp.model_dump(mode="json")`(pydantic 기본값 채움: snapshot_id "snap-1" 등) → `input_hash=sha256(canonical({"input": dump}))`(**래퍼 키 `"input"` 필수**, 엔진 `pipeline:57`+`core/hashing.py:11-20` 비트동일). **content_input_hash=`sha256(canonical({k:v for k,v in dump.items() if k!="snapshot_id"}))`**(snapshot_id 단 하나만 제외, reconcile가 snapshot 주입해 input_hash 변동 `reconcile_tasks.py:191`). 흐름: **(tenant, content_input_hash, snapshot_id) 조회**(UNIQUE와 일치 §12 — content_input_hash는 snapshot 제외라 reconcile 분기 2건 구분 위해 snapshot_id 포함)→미존재 시만 엔진 호출→응답 `AnalysisResult.input_hash==선계산` 검증(불일치=invalid_response)→UNIQUE INSERT, IntegrityError 시 기존 재사용. ⚠️ drawings 포함 run은 VLLM 비결정이라 멱등 조회 자체 건너뜀(§3).|
|(8) 이벤트루프 블로킹|네트워크 입력 async 강제|
|(9) image_ref SSRF|storage:// 객체키만→BFF data-uri 변환(§6)|
|(10) 비동기 결과 유실|task SUCCESS시 BFF 영속+platform run_id, FAILURE/TTL/timeout 분기(§5)|
|(11) 부분응답 무음|pydantic strict→NEEDS_REVIEW|
**롤백**: feature flag 병존 원복. 엔진 수정 Phase(#8)는 별도 합의.

## 10. 미해결 결정 (추천)
1. 전환: A 점진→B 수렴 [추천]. 2. SSOT: B 변환 [추천]. 3. 재현성 컬럼: P5 [추천]. 4. 게이트: warn-only→enforce [추천]. 5. 실연동 인프라(운영/데이터팀). 6. 동기/async [추천]. 7. 테넌트: BFF binding [추천]+#8 병행.
8. **엔진 소규모 수정 묶음**(일부 P1 필수·일부 후속): **(a) ★테넌트 격리 write+read — P1 필수**(BFF binding은 read 우회만, 엔진 직결 교차read는 못 막음): (a-1) write — `/analyze` POST가 신원에서 테넌트 수신(공유 베어러+필수 헤더 `X-Tenant-Id`=BFF가 `user.tenant_id.hex` 주입·32자 검증), `save_analysis(session, result, *, tenant_id)`가 `AnalysisRunModel.organization_id=UUID(tenant_id)` 채움(`analysis_store.py:24`); (a-2) read — `get_analysis(session, run_id, *, tenant_id)`에 `WHERE id=:uid AND organization_id=:tid`, 불일치=None→404(`:38`); (a-3) legacy NULL org 행은 GET 404 격리(필요 시 백필); (a-4) 엔진 loopback/사설망 bind+NetworkPolicy(BFF 파드만 ingress). (b) 전역 `CONSUMER_LIVE_OFF` 게이트(`cached_get`+vision/jurisdiction/embedding 라이브 오프)+**`cache_key`에 snapshot 결합(source_cache `:64`+vision_cache `vision_cache.py:22`+mirror 모두 — 교차스냅샷)**+`load_active_snapshot_from_db(*,snapshot_id)` 필터·`MirrorStore.clear()` 신설(`mirror_store.py:77,39` 전역싱글톤 stale/교차테넌트 누출)+엔진 레이트리밋 키를 `X-Tenant-Id` 우선(`main.py:53` 공유베어러 단일버킷=교차테넌트 DoS). (c) 비동기 결과 영속. (d) **모든 비-health 라우트 require_token**(/doctor·/reports/build·/analyze/async·/task·/UI). (e) `AnalysisResult` `extra="forbid"`+run_id 필수화. (f) (플랫폼) `_count_entries` audit quota 제외.

## 11. 첫 증분 (P0+P1) — 구현 가능 수준
- **P0**: 엔진 `.env.secrets` API_TOKEN(≥32B)+플랫폼 `.env` 수기 동일값. `/deliberation/health`(엔진 doctor 인증후 화이트리스트 재발행). 게이트=무토큰 401.
- **P1**: `apps/api/app/routers/deliberation.py` = `APIRouter(prefix="/api/v1/deliberation")`; **실 가동 ASGI app `apps/api/main.py`(include_router 군집 `:591-602`)에 등록**(`apps/api/app/main.py`는 별개 공존 — 가동 app 확인). POST/GET 모두 `response_model=None`(degrade 봉투 result=null이 강타입 충돌 → 명시 dict 반환). `request_id`=헤더 `X-Request-ID` 있으면 사용, 없으면 **`StructuredLogger.generate_request_id()`**(`structured_logging.py:111-114` — 모듈함수 아님·클래스 @staticmethod, 반환 `f"req-{uuid4().hex[:12]}"`; 또는 BFF가 동일형식 인라인 생성)로 1회 생성·응답 헤더 echo·감사 metadata 동일값. P0 어댑터 키 주입=`apps/api`(venv)서 `python scripts/export_scoped_secrets.py --target <engine>/.env.secrets --with-db`(ALLOWLIST=ANTHROPIC/OPENAI/VWORLD/MOLIT/MOLEG, `:42-47`; API_TOKEN은 미포함→수기 별도).
  - `POST /deliberation/analyze`: `Depends(get_current_user)`(auth_service — DB-backed User·is_active 강제; `jwt_handler.CurrentUser`는 DB 미조회라 미사용) → 입력 pydantic 선검증 → **input_hash/content_input_hash 선계산**(vendored 헬퍼 §9 R7) → `engine_run_binding`(tenant, content_input_hash) 조회(있으면 GET 재사용) → httpx(Bearer, §5 timeout/breaker) → 응답 역직렬화·`input_hash==선계산` 검증 → ⚠️ **`run_id is None or not _is_uuid(run_id)` 가드**(엔진 `run_id: str|None` `analysis.py:69` → None 통과 가능; None이면 NEEDS_REVIEW+invalid_response·binding INSERT 안 함) → 정상/`degraded` 봉투 → UNIQUE INSERT(IntegrityError 시 재조회) → `append_audit`(반환 dict ok/unchanged/quota_exceeded 분기, §5).
  - `GET /deliberation/analyze/{run_id}`: `engine_run_binding`(tenant 일치, `tenant_id.hex`) 확인 후만 엔진 GET 프록시(source=async면 BFF 영속본); 불일치/미존재 404. 엔진 GET 외부 비노출.
  - `DeliberationConsole.tsx`(**최소범위**): ENGINE_URL/NEXT_PUBLIC_* 제거→**공용 `apiClient`(api-client.ts:381)** 경유 `POST /api/v1/deliberation/analyze`(apiClient가 resolveApiOrigin+`propai_access_token` Bearer 자동부착 `:305`; 웹≠API 동일출처 아니므로 raw fetch 금지·API CORS_ORIGINS에 웹 오리진 포함); 미인증 401→로그인 유도; 응답 봉투 `{degraded,result,reason,audit_degraded}` 처리; **기존 간이 렌더 보존**. §6 evidence 풀스키마 TS는 **P2**.
  - ⚠️ **#8(a) 테넌트 격리 write+read+loopback bind는 P1 필수**(BFF binding 단독은 엔진 직결 교차read 미차단, §9 R6 — 엔진 `save_analysis(*,tenant_id)` org 주입+`get_analysis(*,tenant_id)` 필터+`X-Tenant-Id` 헤더). #8(b~f)·RBAC 세분화·비-analyze 인증은 P1 비범위(후속). (대안: P1을 POST+shadow 기록만으로 한정하고 GET /{run_id}를 P2로 미루면 #8(a) read 필터는 P2로 연기 가능.)

## 12. 데이터모델 (신규 alembic — 플랫폼 **public** 스키마)
⚠️ **alembic 정본=`apps/api/database/migrations/versions/`**(`031_analysis_ledger.py` 소재; `apps/api/alembic/`는 004/005만 있는 **미사용** 별도 트리 — 혼동 금지). 신규 리비전 `032_deliberation_binding` 헤더: `cd apps/api && alembic heads`로 head 실측 → 다중 head면 `alembic merge` 선행, `down_revision=<merge 또는 단일 head(예: 031_analysis_ledger)>`. 신규 2객체(engine_run_binding/shadow_comparison)는 **플랫폼 public**(엔진 review 아님); run_id는 `review.analysis_run.id` 논리참조하나 **외래키 없음**(엔진 무수정+BFF 응답 후 INSERT). `gen_random_uuid` 가용. **`downgrade()`**: `drop_index idx_shadow_domain; drop_table shadow_comparison; drop_index idx_binding_tenant_run; drop_table engine_run_binding`(가역 관례). ✅ **`analysis_ledger`는 정식 alembic `031_analysis_ledger`(revision="031_analysis_ledger", down_revision="030_livekit_recordings")로 생성**(런타임 `analysis_ledger_service.py:23-39 _ensure` lazy-DDL을 흡수 — **둘 다 `CREATE TABLE IF NOT EXISTS`로 멱등 공존**). 컬럼 추가는 (1) 신규 리비전에서 `ALTER TABLE analysis_ledger ADD COLUMN IF NOT EXISTS input_hash text / snapshot_id text`(CREATE 금지·downgrade 무동작) + (2) `_DDL` 문자열에도 두 컬럼 반영(_ensure 신규환경 정합).
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
  field_diffs JSONB NOT NULL DEFAULT '[]', divergence_score NUMERIC(6,4),  -- nullable: P1/P2 관측행=NULL(승격쿼리 divergence_score IS NOT NULL 필터)
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
