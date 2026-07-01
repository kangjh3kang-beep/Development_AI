# 사통팔땅 100% 완성도 — 4차 그라운드-트루스 검증·보정 개선안

- 작성일: 2026-07-01 (통합자/검증 세션)
- 입력: 코덱스 3문서 — `REDTEAM_COMPLETENESS_INTEGRITY_AUDIT`, `INTEGRATED_100_COMPLETION_IMPROVEMENT_PLAN`(2·3차 자기레드팀 포함), `LAW_REVIEW_ENGINE_COMPLETION_PLAN`
- 방법: 코덱스 계획을 **실행검증(execution ground-truth)** 으로 재감사 — grep 코드스캔이 아니라, 검증환경을 실제 복구해 테스트를 돌리고 각 P0의 배선을 추적. 이 저장소의 과거 감사 ~90% 오탐 전례(고아경로를 실경로로 오인)를 전제로 각 주장을 반증 우선으로 검증.

---

## 0. 한 줄 결론

코덱스의 계획은 **구조·시야가 탁월**하다(3패스 자기레드팀은 진짜 강점). 그러나 **원본 감사가 스스로 인정한 "백엔드 검증환경 실패" 때문에 P0 판정이 전부 grep 스캔에 기반**했고, 그 결과 **P0 4건 중 3건이 과대평가/오탐, 실제 라이브 결함은 1건뿐**임이 실행검증으로 드러났다. 진짜 해야 할 일은 "거대한 신규 아키텍처 구축"이 아니라 **①검증환경 근본원인 고정 ②라이브 fail-open 1건 수정 ③CAD커널 드리프트 1건 정합 ④기존자산(evidence_contract·LegalHub·zone_limit_contract) 위에 LawScope/특수데이터를 얹기**다. 계획의 상당 부분은 이미 코드에 존재하거나(SSOT 단일심판·evidence 계약·특이필지 게이트), 안전측이라 P0가 아니다.

---

## 1. 검증환경 근본원인 확정 (계획 Plan-P0-4의 진짜 원인)

원본 감사·계획은 "`fastapi`/`sqlalchemy` 미설치로 pytest 수집 중단 → 검증체계가 100% 게이트가 아니다"라고 했다. **실행검증 결과 이것은 코드 무결성 문제가 아니라 순수 환경 프로비저닝 문제였고, 진짜 근본원인은 Python 버전 불일치다.**

| 검증 단계 | 환경 | 결과 |
|---|---|---|
| 감사 재현(miniforge 기본 py3.10) | 3.10 | 수집 128 errors — 상당수 `ImportError: cannot import name 'UTC' from datetime`, `StrEnum from enum` |
| 근본원인 | pyproject `requires-python = ">=3.12"` | 코드는 3.12 전용 기능(`datetime.UTC`·`enum.StrEnum`) 사용. **감사는 3.10으로 돌려서 실패한 것** |
| 올바른 환경(py3.12 + 의존성) | 3.12 | **5396개 수집, 실코드오류 0건** (잔여는 전부 미설치 의존성) |
| 핵심 도메인 실행 | 3.12 | 법령·zoning·조례·특이필지·precheck·evidence 관련 **542 passed, 0 failed** (11 skipped) |
| SSOT/evidence 계약 | 3.10에서도 | `test_zone_limits_engine_sync`·`test_integrated_zoning_aggregate`·`test_evidence_contract` **28 passed** |

**결론:** 감사의 "법령/법규 무결성 58~64/100" 점수는 **테스트를 못 돌린 상태 + grep 과대해석**의 산물이다. 코드를 실제로 돌리면 법령엔진 도메인 테스트 542개가 통과한다. 이는 "코드가 100%다"가 아니라, **"감사가 진단한 결함 대부분이 실코드에 없다"** 는 뜻이다.

**보강(계획 Gate 0 대체·구체화):** `scripts/verify-backend.sh` 를 만들어 ①`python3.12` 강제(3.11 이하면 즉시 non-zero) ②`requirements.txt` 전량 설치 ③핵심 도메인 테스트 실행 ④수집오류 0 검증. 이걸 CI/로컬 공용 게이트로 고정하면 "검증환경 무결성" 항목은 즉시 닫힌다. (거대한 Docker/uv 이중경로 신설보다 **버전 핀 하나가 근본 처방**이다.)

---

## 2. P0 재판정 — 그라운드-트루스 (핵심 보정)

각 P0를 **패턴 실재성 + 라이브 배선 + 정답기준선 격차**로 3중 검증했다.

### P0-1. RegulationService fail-open → **CONFIRMED-ORPHAN (감사 과대평가)**
- **패턴 실재**: `apps/api/services/regulation_service.py:236-244` — LLM 예외 시 `is_compliant=True, confidence=0.3, violations=[]`. Qdrant 실패 시 7-zone `BUILTIN_REGULATION_DB` 폴백. 맞다.
- **배선 실측**: 이 서비스 소비 엔드포인트는 `/regulation/check`(`routers/regulation.py:107`)·`/agents/orchestrate` 둘뿐인데, **프론트엔드 전수 grep 호출 0건**. 죽은 경로.
- **실사용자 1차 경로**: 프론트(`ProjectLegalWorkspaceClient`·`RegulationsWorkspaceClient`)는 **`POST /regulation/analyze`** → `RegulationAnalysisService` → **`legal_limits_for()`(SSOT, fail-CLOSED)**. 미인식 zone을 `matched=False, max_*=None`으로 강등(적합 위장 없음). fail-open 코드는 이 경로에 **없다.**
- **재판정**: 라이브 P0 아님. **정리(하드닝) 백로그** — 죽은 fail-open 엔드포인트를 fail-closed로 전환하거나 제거(직접 API호출·추후 재배선 시 재발 방지).

### P0-2. `/building-compliance/legal-check` 미등록 zone 통과 → **CONFIRMED-LIVE (유일한 실 라이브 결함)**
- **패턴+배선 실측**: `apps/api/routers/building_compliance.py:709-715` — 미등록 용도지역이면 `overall_pass=True` + "수동 확인 필요". 이 라우터는 `/api/v1/building-compliance`로 등록(`main.py:719`), **프론트가 `/legal-check`를 실제 호출(`ProjectLegalWorkspaceClient.tsx:469,660`)** → 라이브 도달 가능.
- **근본원인**: 자체 정적표 `_LEGAL_LIMITS_PCT`(:505)를 쓰고 SSOT `resolve_zone_limits()`(`zone_limit_contract.py:86`, fail-closed) 미배선. 같은 파일의 `/check`(`_pre_design_review`)는 미등록 zone을 `overall_status="warning"`으로 정직 처리(:238) — **한 파일 안에 정답기준선이 이미 있다.**
- **재판정**: ★**실수정 대상 1순위(그러나 소규모)**. 미등록 zone → `overall_pass`를 `True`가 아니라 `None`+`overall_status="needs_verification"`로 강등하거나 `resolve_zone_limits()` 경유로 통일. 단일 엔드포인트·회귀테스트 1개.

### P0-3. 법정 한도표 drift → **PARTIALLY-REAL → 실질 LOW (감사 과대평가)**
- **실측**: 7개 표 중 `ZONE_LIMITS`(`auto_zoning_service.py:31`)가 SSOT 원본이고 `legal_limits_for`/`resolve_zone_limits`가 **이미 15+ 라이브 심판서비스**(site_score·regulation_analysis·buildable_options·far_tier·precheck·design_audit·permits·verification·site_analysis_interpreter·upzoning·cad/design_reference)의 단일 소비원. 나머지 `NATIONAL_LIMITS`·`ORDINANCE_CACHE`·`BUILTIN_REGULATION_DB`는 폴백/시드, `_LEGAL_LIMITS_PCT`·`ZONE_DEFAULTS`는 값이 **SSOT와 정합**.
- **진짜 드리프트는 1곳**: `auto_design_engine.ZONE_LIMITS`(CAD 매스 커널) — `2R far=200%`(SSOT 250%), `GC far=1000%`(SSOT 1300%). 코드 스스로 인지(`drawing.py:390` 주석)하고 `min()` 재클램프. **과소방향=안전측**(과대산정 아님).
- **재판정**: P0 아님. **CAD커널 표를 SSOT import로 정합**(1개 파일)하는 정리 작업. 사용자에게 다른 숫자가 보일 수 있으니 우선순위는 P2.

### P0-4. 조례 법정폴백 저장·재사용→과대산정 → **감사 프레이밍은 FALSE-POSITIVE, 그러나 인접 실결함 존재(4차 재발견)**
- **감사 주장("법정상한 재사용→용적률 과대산정")은 좁게 오탐**: 저장값 `effective_far = national_far`(=법정상한, 그 이상 아님)이고 소비처 `calc_effective_far`(`far_tier_service.py:56-71`)가 `national_far`를 **SSOT에서 재도출**해 `min(national_far, ordinance_far)`로 **재클램프**. 재사용값은 **법정최대를 결코 초과 불가**. "법정최대 초과 과대산정" 결함은 없음.
- **★그러나 4차 레드팀이 다른 실결함 발견 → R-7로 승격**: 폴백 캐시(`ordinance_service.py:82-119`)가 **`(sigungu, zone_type)` 전역키 + 테넌트/프로젝트 스코프 없음 + 자동만료 없음**(`_load_stored` "자동만료 없음"). statutory 폴백(confidence 0.60 = "조례 미보유")도 이 전역캐시에 저장(:361). → **실제 지자체 조례가 법정상한보다 낮은 경우**(조례가 법정 이하로 제한하는 흔한 케이스), 전역캐시가 **법정상한을 그 시군구의 모든 테넌트·모든 프로젝트에 서빙** = ①실 조례 대비 과대(법정최대 대비는 아님) ②계정격리 위반(테넌트 A의 fetch 실패가 B에게 전파). MEMORY `project_account_isolation` 위반 패턴.
- **재판정**: 감사의 "과대산정" = 오탐. **인접 결함(전역캐시 격리·statutory 영속) = R-7(P1)**. 완화요인: provenance에 `confidence=0.60·recheck=True·disclaimer="실제 조례 확인 필요"`가 이미 부착(정직신호 존재) → 완전 무방비 아님. 그래서 P0 아닌 P1.

**P0 종합**: 감사가 라이브 P0 4건이라 한 것 중 **라이브 실결함 1건(P0-2), 정리성 3건(P0-1 하드닝·P0-3 CAD정합·P0-4 배지)**. 감사의 "완성도 58~64%"는 실코드 대비 과소평가다.

---

## 3. 진짜 남은 결함 — 실행검증으로 확인된 것만

| # | 항목 | 등급 | 근거(file:line) | 수정 |
|---|---|---|---|---|
| R-1 | `/legal-check` 미등록 zone `overall_pass=True` | **P0(라이브)** | `building_compliance.py:709-715` | SSOT `resolve_zone_limits` 경유 or `needs_verification` 강등 + 회귀테스트 |
| R-2 | 검증환경 Python 3.12 미핀 → 감사 재발 | **P1** | `pyproject requires-python>=3.12` vs 로컬 3.10 | `verify-backend.sh` 버전핀+의존성+테스트 게이트 |
| R-3 | CAD커널 `auto_design_engine.ZONE_LIMITS` 드리프트(2R·GC) | **P2** | `auto_design_engine.py:49,51` | SSOT import로 정합(과소→정합, 안전측) |
| R-4 | 죽은 fail-open 엔드포인트 `/regulation/check`·`/agents/orchestrate` | **P2(하드닝)** | `regulation_service.py:236`, `routers/regulation.py:107` | fail-closed 전환 or 제거 |
| R-5 | `removeParcel` 마지막필지 제거 시 컨텍스트 stale | **P2(경미)** | `SatongMapShell.tsx:452-464`(next.length>0 조건) | 빈 배열도 `commitParcelsToContext([])` clear |
| R-6 | 면적 미보강 필지 다필지행에서 탈락 | P2 | `satong-map-selection.ts` `areaSqm>0` 필터 | `needs_enrichment` 상태로 전달(감사 P1-3 유효) |
| R-7 | 조례 폴백 캐시 전역키(cross-tenant) + statutory 영속 | **P1(격리)** | `ordinance_service.py:82-119`(ON CONFLICT (sigungu,zone_type)), :361 | statutory는 전역캐시 저장 금지 + statutory provenance면 항상 재조회 |
| R-8 | 정직 실패상태(NEEDS_VERIFICATION 등) 하드코딩 한국어 | **P1(i18n)** | DesignWorkspace/SatongMapShell 등 상태문자열, `useTranslation` 미사용 | 상태 enum→i18n 키(ko/en/zh) + 차단배너 `role="alert"` |
| R-9 | 법령 판정응답에 면책·의존자 audit 계약 부재 | P2 | `RegulationCheckResponse` 등 판정면(면책은 818건 산발) | evidence 계약에 `legal_boundary`+`reliance_audit` additive |
| R-10 | verdict에 적용 법령 시행일 각인 부재 | P2 | legal 도메인 `as_of_date`/`effective_at` 전무 | evidence에 `law_effective_date`+`analysis_as_of` 필드 |

> 위 10건이 **실행검증으로 확인된 실제 오점 전부**다(R-1~R-6 실측·R-7~R-10 4차 레드팀 코드확인). 나머지 감사 항목(fail-open 대량·drift 대량·조례 법정최대초과)은 과대/오탐.

### ★감사가 "미구현"이라 오판했으나 이미 구현된 것 (over-scope 교정)
- **감사 P2-1("설계 스튜디오 stale 감지하나 차단 안 함") = 틀림**: `apps/web/components/design/DesignWorkspace.tsx:56-92`가 `hasAddressMismatch`→`generateState/drawState="blocked"`로 **Top-N·CAD/BIM을 실제 잠금**(3중 차단 UI, 13회 참조). → "구현"이 아니라 **회귀락(Playwright: 주소불일치 시 버튼 disabled)** 으로 강등. 진짜 잔여갭은 site-hash/pnu 기반 불일치까지 확장(현재는 주소토큰만).
- 즉 계획 Phase 6/Gate 5는 **이미 도는 게이트를 재작성하려다 회귀 유발 위험** — "만들기"가 아니라 "지키기"로.

---

## 4. 계획이 무시한 기존자산 — "재구현 금지" 위반 방지 (★플랫폼 핵심원칙)

코덱스 계획은 다수 **신규 추상**을 제안하나, 상당수가 **이미 코드에 존재**한다. 재구현은 이 저장소의 "그린필드 금지·기존자산 매핑" 원칙 위반이며 경쟁 시스템을 낳는다. **신설이 아니라 확장으로 전환**하라.

**★4차 레드팀 실측: 계획이 재발명하려는 신규 추상 중 8~10개가 이미 라이브 자산이다.** 계획의 근본진단("판정권한 분산")과 처방("신규 서비스 대량 추가")이 자기모순 — 재발명은 분산을 **악화**시킨다.

| 계획 신규 제안 | 이미 존재하는 라이브 자산(file) | 조치(재구현→확장) |
|---|---|---|
| `EvidenceLedger` | `data_validation/evidence_contract.py` `build_evidence_block()`{evidence,legal_refs,provenance,trust} + `schemas/evidence.py` `BaseEvidenceResponse`(상속만으로 4필드) | evidence 계약에 `counter_evidence[]·ledger_id·legal_ref_key·evidence_span·legal_boundary·law_effective_date` additive |
| `LegalVerdictEnvelope` | `design_ingest/provenance.py` `Evidence`{claim,basis,source,confidence,link} | verdict 상태(PASS/FAIL/NEEDS_VERIFICATION)+시점 필드 추가 |
| `LawScopeInventory` | `design_ingest/law_coverage.py` `DESIGN_LAW_MAP`(13도메인·70+키)+`verify_coverage()`/`laws_for()` | 특이조건(산지/농지/도시계획시설/지구단위) 키 추가 + `special_parcel` 연결 |
| `LawScopeAgent`(LLM 앙상블) | `legal/legal_discovery_service.py` `discover()`+`_crossvalidate()`(verified_ssot vs llm_unverified) | 결정론 트리거(special_parcel)+공간 트리거(land_info)를 합집합으로 배선 |
| `Rule DSL / IDS-like` | `cad/rule_trace.py` `build_rule_trace()`(applied/basis/source/legal_link) | applicability/exception 필드 추가, IDS-like 정형화 |
| `CounterEvidenceLoop` | `data_validation/trust.py` `cross_validate()`(verdict pass/warn/fail) | 데이터 교차검증 패턴을 법령 반증질의로 확장 |
| `SourceHealthMonitor`·`EvidenceInvalidationPolicy` | `regulation_monitor/regulation_monitor.py`(60법령 폴링) + evidence FreshnessChecker | 변경감지→evidence stale 콜백 배선, per-원천 readiness 라벨 |
| `LegalZoneLimitsRegistry 단일 export` | `zoning/zone_limit_contract.py` `resolve_zone_limits`/`legal_limits_for`(이미 fail-closed) | **이미 SSOT**. 남은 건 CAD커널(R-3) import 정합 + 26개 우회표 교체(유일한 진짜 대작업) |
| `OrdinanceResolution 상태화` | `ordinance_service.py`(이미 source·confidence·recheck 분기) | `resolution_state` enum만 추가 + 저장 스코프 격리(R-7) |
| `OfficialDataEnvelope`·토지이음 커넥터 | `legal/tojieum_supplement.py`, `legal_hub.py`, `land_info_service.py`(VWorld) | 신규 커넥터 신설 대신 기존 래핑+readiness 라벨 |
| 특수조건 게이트 | `zoning/special_parcel.py`(855줄, POSSIBLE/CAUTION/CONDITIONAL/PRECONDITION/BLOCKED+prerequisites) | 산지/임목/경사 공식데이터 항목 추가, blocking_unknown을 기존 게이트에 매핑 |
| `AnalysisRunBudget` 과금 | `billing/billing_service.py`, `base_interpreter.record_llm_response_billing`, `llm_usage_log` | per-원천 계측을 기존 billing에 연결(재발명 금지) |
| 면책/비법률자문 | `apps/web/components/common/Disclaimer.tsx`(+818 산발 참조) | registry화(단일문구) + 판정응답 전수 부착 |

> 플랫폼 원칙(MEMORY): **"재구현금지·그린필드 금지·기존자산 매핑(조립)"**. 계획 §4/5/6/13/19의 신규 서비스명을 전부 위 "확장 태스크"로 재작성하지 않으면 원칙 정면위반 + 경쟁 시스템 양산.

---

## 5. 4차 레드팀 — 3패스가 놓친 신규 갭

(코덱스 2·3차 자기레드팀이 이미 다룬 항목 제외. 신규만.)

### 4G-1. 검증환경 근본원인 미진단 (P1)
계획 Plan-P0-4는 "fastapi 설치/venv 고정"만 말하고 **진짜 원인(Python 3.12 요구)** 을 못 짚었다. 3.11 이하 venv를 아무리 만들어도 `datetime.UTC`/`StrEnum` ImportError로 계속 실패한다. → §1 처방(버전핀).

### 4G-2. 결정론/재현성 주장 ↔ LLM 비결정성 모순 (P1)
`LAW_REVIEW` 게이트 #9 "동일 입력→동일 결과"와 §5.1 "LLM adversarial expansion 스코프 생성"은 **직접 모순**(LLM 비결정적). 계획 어디에도 해소책 없음. → 보강: **LLM은 스코프 "후보 확장"에만 쓰고, 결정론 트리거(지목·용도·면적·공간교차)를 재현성 기준선으로 고정**. LLM 산출은 캐시+시드고정+공식ID 매칭 통과분만 스코프에 편입. 재현성 게이트는 "결정론 코어 동일"로 정의(LLM 후보는 superset 허용).

### 4G-3. "100% 완성" 정의가 외부 국가API 가용성에 인질 (P0-계획설계결함)
계획은 "critical 누락 0·필지별 fetch 성공률 100%"를 100% 조건으로 두는데, 원천 자신이 **열람중심(토지이음)·약관제약·쿼터**임을 인정한다. 외부 API가 다운되면 영원히 100% 선언 불가 = **달성불가 바(bar)**. → 보강: 100%를 "**모든 원천이 성공**"이 아니라 "**모든 원천이 분류(ready/limited/manual_only/unavailable)되고, 미확보는 정직하게 차단·표기**"로 재정의. 즉 **완성도 = 성공률이 아니라 정직성·차단 무결성**. (이게 무목업·정직표기 원칙과도 정합.)

### 4G-4. 시행일 기반 법령 버전관리 부재 (P2, 실갭)
`시행일/effective_date/기준일` 처리는 `gosi_search_service` 1곳뿐. "지난달 착수 프로젝트에 어느 시행일 법령이 적용되는가"의 temporal 계약이 없다. 산출물 재현·감사에 필요. → LawScope evidence에 `law_version`·`enforced_at`·`as_of_date` 필드 추가(P2).

### 4G-5. 멀티세션 동시성 — 같은 프로젝트 필지목록 동시편집 (P2)
이 저장소는 명시적 멀티세션인데, 계획의 stale 전파(§19.4)는 **원천 변경**만 다루고 **동시 사용자/세션이 같은 프로젝트를 편집**하는 경우(필지목록 레이스)를 안 다룬다. → 프로젝트 컨텍스트 낙관적 락/버전 스탬프.

### 4G-6. deep-path 과금 귀속 (P2)
"모든 공식원천 조회" deep-path는 LLM+외부API 비용을 유발하나, 계획은 성능/쿼터(§19.7)만 다루고 **과금 귀속**을 안 다룬다. 플랫폼 원칙(과금=관리자설정·미설정무료)과 배선 필요.

### 4G-7. 전면 BLOCKED 시 인간 에스컬레이션 경로 (P2)
계획은 미확인→차단을 강조하나, **모두 BLOCKED일 때 사용자가 벽에 부딪히는지, 전문가 핸드오프가 있는지** 미정의. "인간개입 최소·비전문가 대행" 원칙상 **"전문가 검토 요청" 라우팅**이 100%의 일부. 실코드상 legal/design 경로에 전문가 의뢰 CTA 없음(발견된 "escalate"는 무관한 approval-operations). → BLOCKED/NEEDS_OFFICIAL_SURVEY에 기존 `expert-panel`/`senior_agents` 라우터로 인계 CTA + "필요서류·자격·예상절차" 카드.

### 4G-8. ★계획이 "선언 불가능한 게이트"를 쌓아 done을 영원히 못 선언하는 구조 (계획 설계결함 P0)
4차 레드팀의 최상위 메타발견. 계획은 "좋은 계획"이 아니라 **달성불가 지표를 게이트로 박아 완료 서사 자체를 봉쇄**한 구조에 가깝다. 구체적 달성불가 바:
1. `LAW_REVIEW §7-2 "critical fetch 성공률 100%"` — 열람전용(토지이음)·파일데이터(임상도) 원천에서 **구조적 불가**(계획 스스로 §2.1/§2.2에서 한계 인정). → **"fetch 100%" 폐기 → "silent-drop 0%(모든 critical이 fetched|manual_only|unavailable로 분류+미확보는 차단·정직표기)"로 교체.**
2. `LAW_REVIEW §7-9 재현성 + §5 LLM expansion` — 미해소 모순(4G-2). → 재현성을 **저장된 스코프 스냅샷 경계**에 걸기.
3. `LAW_REVIEW §7-8 "반증루프 신규 critical 누락 0건"` — LLM 반증으로 **"누락 0"을 증명 불가**(부재 증명). → "직전 2라운드 신규발견 0"(loop-until-dry)으로 조작적 정의.
4. `INTEGRATED §14/§21 "P0 1건이라도 100% 불가 + 수집실패 시 최고 70점"` — all-or-nothing → 점진적 완료 봉쇄. → **"라이브 P0"만 절대차단**(고아/오탐 제외), 검증환경은 병렬(선행 아님).
5. `INTEGRATED §20 Evidence Pack 8종 필수 선행` — 첫 사용자-위험 수정보다 산출물 스캐폴딩 프론트로딩. → Evidence Pack은 **배포 게이트**로만(구현 착수 선행 조건 아님).

**핵심 재정의: 완성도 = "외부API 성공률"이 아니라 "사용자가 false 적합/확정을 볼 수 있는 경로 0건 + 미확보의 정직차단"** — 측정가능·유의미하며 무목업·정직표기 원칙과 정합. 이래야 **선언 가능한 100%**가 된다.

---

## 6. 보정된 100% 게이트 (코덱스 v3 → 실측 반영)

코덱스 v3 점수체계는 유지하되, **"검증환경/CI 재현성" 항목의 100% 조건을 "Python 3.12 핀 + 핵심 도메인 테스트 pass + 수집오류 0"으로 구체화**하고, **절대차단 조건에서 "P0 1건 이상"을 "라이브 P0 1건 이상"으로 정정**(고아/오탐을 라이브와 동급 차단하면 영원히 미완). 나머지 v1~v3 게이트·30 fixtures·Evidence Pack·traceability matrix는 **전부 채택**(계획의 진짜 강점).

**보정 절대차단 조건:**
- **라이브** fail-open 1건 이상(현재 R-1 하나 → 이것만 닫으면 fail-open 게이트 통과)
- 핵심 도메인 백엔드 테스트 실패 or 수집 실코드오류>0 (현재 0 — 통과)
- 확정 산출물에 evidence 없음 (evidence_contract 확장으로)
- production 판정 경로 mock/fallback (NoMockProductionGate — 채택)
- statutory_only를 "확정 조례"로 표기 (배지 강화)

---

## 7. 보정된 구현 우선순위 (leaner critical path)

계획은 Gate 0(증거체계) 선행을 강제하나, **사용자가 실제로 틀린 "적합"을 보는 위험(R-1)은 Gate 0 없이도 즉시 닫을 수 있다.** front-load 관료주의로 실위험 수정을 늦추지 말 것.

**임계경로(사용자 오판 제거 — 즉시).** 실제 사용자-오판 위험은 **정확히 3개 파일의 소수 반환지점**에 집중(실측):
1. **R-1 라이브 fail-open 제거** — 3지점:
   - `routers/building_compliance.py:709-715` 미등록 zone `overall_pass=True` → `None`+`overall_status="needs_verification"` (★라이브·최우선)
   - `services/regulation_service.py:239`(+`:273`,`:290`의 `.get("is_compliant", True)` 기본값) `True`→`None`/UNKNOWN (고아지만 하드닝)
   - `land_intelligence/ordinance_service.py:361` statutory 폴백 `_save_resolution` 전역캐시 저장 제거 = R-7 동시해소
   + 회귀락 3개(fail-open→fail-closed 단위테스트).
2. **R-2 검증환경**: `verify-backend.sh`(py3.12 핀+의존성+핵심테스트+수집오류0). ★**병렬 진행이지 선행 블로커 아님** — R-1은 소스 grep+단위테스트로 검증 가능하므로 fastapi 미설치가 fail-open 수정을 막지 않는다(계획 Gate 0의 프론트로딩 오류 교정).
3. **R-3/R-7/R-8**: CAD커널 SSOT 정합 · 조례 전역캐시 격리 · 실패상태 i18n. (각 소규모)
4. **R-4/R-5/R-6/R-9/R-10**: 하드닝·프론트 clear·면적 needs_enrichment·면책계약·시행일각인. (각 소규모)

**확장경로(기존자산 위 진짜 신기능 — 순차):**
5. `special_parcel` 확장: 산지/임목/경사 공식데이터 항목 + `NEEDS_OFFICIAL_SURVEY` 게이트(계획 §6·법령엔진 §3의 진짜 가치).
6. `LawScopeInventory`를 LegalHub 서브모듈로 신설(결정론 트리거 코어 + LLM 후보확장, 4G-2 재현성 계약).
7. evidence_contract 확장(legal_ref_key/evidence_span/enforced_at) + statutory_only 차단 배지.
8. 산림청/토지이음 커넥터 `ConnectorReadiness` 분류(계획 Plan-P0-1 — 실가치).
9. 30 redteam fixtures + traceability matrix + Evidence Pack(계획의 강점 — 전량 채택).

**차이의 핵심:** 코덱스 계획 ≈ "9-Gate 대공사". 보정안 = **"실위험 4건 즉시 + 기존자산 확장 5단계"**. 무결성은 1~4로 확보하고, 5~9는 제품 심화(법규 커버리지)로 순차 진행. "달성불가 바(4G-3)"를 정직성 기준으로 재정의해 **선언 가능한 100%**로 만든다.

---

## 8. 통합자 판단 (배포 관점)

- 위 R-1~R-6은 **코드 변경**이라 성장루프(executor→code-reviewer≥9.5→통합자 머지→블루그린 배포→라이브검증) 필요. 문서(본 계획)는 배포 무관 → 기록·머지.
- **P0-2(R-1)만이 라이브 무결성에 직결** — 이것부터 단독 PR로 처리 권장(작고 검증 쉬움).
- 코덱스 3문서는 **폐기하지 말 것**: 시야·게이트·fixtures·Evidence Pack은 확장경로(5~9)의 설계도로 유효. 본 문서는 그 위에 **실측 보정**을 얹은 것.

## 9. 실행검증 증거(재현 명령)

```
cd apps/api
/usr/bin/python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
JWT_SECRET_KEY=x APP_SECRET_KEY=x PYTHONPATH=. .venv/bin/python -m pytest tests/ \
  -k "legal or zone or ordinance or special_parcel or precheck or evidence" -q
# → 542 passed, 11 skipped (2026-07-01 실측)
PYTHONPATH=. .venv/bin/python -m pytest tests/ --collect-only -q  # → 5396 collected, 코드오류 0
```
