# PropAI v43 대비 현재 구현/구축현황 분석 및 상세 구현계획

작성일: 2026-03-21  
분석 기준선:
- 문서: `PropAI_v43_완전구축_마스터인덱스.md`, `PropAI_v43_PartE_비즈인프라_G81-G85.md`, `PropAI_v43_PartF_G86-G90.md`, `PropAI_v43_PartG_G91-G95.md`, `PropAI_v43_PartH_통합검증_배포_운영.md`
- 코드: `propai-platform/apps/api`, `propai-platform/apps/web`, `propai-platform/apps/worker`, `propai-platform/tests`
- 현재 상태 기록: `propai-platform/.build-journal/current-stage.json`, `propai-platform/.build-journal/capillary-gap-analysis.md`

## 1. 결론 요약

현재 저장소는 `v43 완전체`가 아니라 `v30.x 기반 + 일부 후속 확장` 상태다.

- 백엔드 기준:
  - v30 핵심축은 상당 부분 구현됨.
  - 카카오 OAuth, 웹훅, API Key, 시공/ESG, SSE/WS 오케스트레이션, 외부 API 클라이언트, AI 비용 추적 등 일부 후속 확장은 이미 존재함.
  - 그러나 v43 핵심 범위인 `G81~G95 전용 도메인 서비스/라우터/DB 스키마`는 대부분 부재함.
- 데이터 모델 기준:
  - 현재 ORM 모델은 `19개 핵심 테이블 + 2개 타임시리즈 테이블` 수준이다.
  - v43 마스터 인덱스는 60개 테이블 체계를 목표로 하며, G81~G95 확장 테이블군은 사실상 미구현이다.
- 프론트엔드 기준:
  - 다국어 라우팅과 대시보드 쉘은 존재하지만, 현재 웹은 `mock-first` 모드가 기본값이다.
  - 주요 프로젝트 화면 다수가 `ModulePlaceholder` + mock data 기반이며, v43 확장 모듈 UI는 없다.
- 검증 기준:
  - `current-stage.json`의 `634 passed, 3 skipped`는 최신 실상과 불일치한다.
  - 2026-03-21 재검증 결과 `python -m pytest -q`는 `560 passed, 74 failed, 28 skipped`였다.
  - 주요 실패 원인은 `DEBUG=release` 환경값으로 인한 `Settings.debug` bool 파싱 오류다.

판정:
- 현재 구현 수준은 `Part D ~ 초기 Part E 기반`에 가깝다.
- v43 문서 기준으로는 `Part E/F/G 완료` 상태로 볼 수 없다.
- 따라서 구현계획은 `신규 기능 추가` 전에 `기반 정합성 복구`부터 시작해야 한다.

## 2. 현재 구현/구축현황 실측

### 2.1 버전/스테이지 상태

- API 버전 문자열은 아직 `30.0.0`이다.
- `apps/api/config.py`의 `app_version` 기본값도 `30.0.0`이다.
- `apps/api/pyproject.toml` 버전도 `30.0.0`이다.
- `current-stage.json`은 `current_stage = 11`로 기록되어 있으며, v43 Part E~G 완료 상태를 반영하지 못한다.

해석:
- 현재 코드베이스의 공식 기준선은 여전히 `v30 계열`이다.
- v43 문서는 저장소 밖 또는 저장소 상위 설계 기준선으로 존재할 뿐, 코드와 동기화되지 않았다.

### 2.2 백엔드 현재 구현 범위

현재 FastAPI에 등록된 주요 라우터:
- `/api/v1/auth`
- `/api/v1/projects`
- `/api/v1/avm`
- `/api/v1/regulation`
- `/api/v1/tax`
- `/api/v1/design`
- `/api/v1/bim`
- `/api/v1/finance`
- `/api/v1/drone`
- `/api/v1/blockchain`
- `/api/v1/reports`
- `/api/v1/construction`
- `/api/v1/agents`
- `/api/v1/webhooks`
- `/api/v1/api-keys`

이미 구현된 강한 기반:
- 인증/권한: JWT, refresh token, RBAC, 카카오 OAuth
- 멀티테넌시: tenant 기반 세션/RLS 구조
- 외부 API 통합: VWorld, MOLIT, HUG, NICE, Court, KEPCO client, KMA, LH
- 분석 엔진: AVM, 법규검토, 세금, 전세 리스크, BIM/IFC, 시공 일정, ZEB, 하자 분류
- AI 운영 기반: AI usage tracking, Prometheus AI cost/token metrics
- 실시간성: SSE 스트리밍, 에이전트 WebSocket 브릿지
- 운영 도구: Webhook CRUD/dispatch, API key 발급/폐기

### 2.3 데이터 모델 현재 범위

현재 모델 패키지 기준 테이블:
- core/ops:
  - `tenants`, `users`, `projects`, `parcels`
  - `refresh_tokens`, `webhooks`, `webhook_deliveries`, `api_keys`
  - `legal_audit_trail`, `ai_usage_log`, `model_performance`
- AI/분석:
  - `designs`, `regulations`, `avm_valuations`, `financial_analyses`, `tax_calculations`, `jeonse_analyses`, `construction_logs`
- 기타:
  - `drone_inspections`, `escrow_transactions`
  - `iot_carbon_sensors`, `drone_detection_events`

정량 비교:
- 현재 SQLAlchemy 모델 기준: 22개 테이블
- 초기 Alembic 마이그레이션 기준: 17 + 4 = 21개 테이블
- v43 마스터 인덱스 목표: 60개 테이블 체계

판정:
- 현재 DB는 v43가 요구하는 비즈니스 확장 스키마를 수용할 준비가 되어 있지 않다.
- 특히 G81~G95 전용 테이블군은 거의 전부 없다.

### 2.4 프론트엔드 현재 범위

현재 웹 구조 특징:
- 국제화 라우팅과 대시보드 셸은 준비됨.
- `api-client.ts`는 `NEXT_PUBLIC_USE_MOCKS !== "false"`일 때 mock을 우선 사용한다.
- mock handler는 사실상 `/dashboard/overview`, `/integration/status`, `/projects`, `/projects/{id}` 수준만 지원한다.
- 프로젝트 상세의 `design / finance / report / bim / drone / blockchain` 화면 상당수는 `ModulePlaceholder`와 mock data 기반이다.

판정:
- 웹은 “화면 껍데기 + 일부 체험형 mock” 단계다.
- v43 확장 모듈의 실제 API/상태/권한/UI 플로우는 아직 없다.

### 2.5 검증/품질 상태

실행 검증:
- `python -m pytest -q` 실행 결과:
  - `560 passed`
  - `74 failed`
  - `28 skipped`

주요 실패 원인:
- `DEBUG=release` 환경값이 `Settings.debug: bool` 파싱과 충돌
- 설정 객체가 생성자 단계에서 깨지면서 단위 테스트 다수가 연쇄 실패

의미:
- 현재 저장소는 “기능 추가만 하면 되는 상태”가 아니다.
- 테스트 환경/설정 계층을 먼저 정상화하지 않으면 v43 구현을 올릴수록 실패 표면이 더 넓어진다.

## 3. v43 대비 상세 갭 분석

### 3.1 Phase 14~15 비즈 인프라/출시 검증

#### 현재 구현됨
- Webhook CRUD/전송 이력/테스트 발송
- API Key 생성/목록/폐기
- 카카오 OAuth 로그인
- 기본 `/health`, Prometheus `/metrics`

#### 부분 구현
- Slack ops alert: 외부 API base client에 존재
- AI 비용 메트릭: 존재하지만 예산 제어/대시보드 없음

#### 미구현
- `/api/v1/notifications/alimtalk`
- `/api/v1/esign/request`
- `/api/v1/esign/{id}/status`
- `/api/v1/dashboard/stats`
- `/api/v1/dashboard/portfolio/timeline`
- `/api/v1/dashboard/activity/recent`
- `/api/v1/system/health/full`
- `/api/v1/system/version`

판정:
- Part E의 “비즈 인프라 + 출시 검증”은 절반 이하만 구현된 상태다.

### 3.2 G81: AI 투자 언더라이팅 + DataRoom

v43 요구:
- 투자 언더라이팅 서비스
- 리스크 점수/등급 A~E
- LP 보고서
- DataRoom 문서 분류
- `/api/v1/underwriting/{project_id}`, `/history`
- 관련 테이블: `investment_underwriting`, `lp_reports`, `data_room_docs`

현재 상태:
- 직접 대응 서비스/라우터/모델 없음
- 일부 재사용 가능한 기반은 존재:
  - AVM
  - tax
  - jeonse risk
  - financial analysis 모델
  - report streaming 기반

판정:
- `미구현`

### 3.3 G82: AI 준법 감시 + KYC/AML

v43 요구:
- KYC 문서 분류
- AML 리스크 스코어 0~100
- STR 탐지
- `/api/v1/compliance/kyc`, `/history/{project_id}`
- 관련 테이블: `compliance_checks`, `kyc_documents`, `aml_screenings`

현재 상태:
- 일반 법규검토(`regulation`)는 구현돼 있음
- 금융 AML/KYC 전용 서비스/라우터/모델은 없음
- NICE client는 존재하지만 실사용 KYC flow는 없음

판정:
- `미구현`

### 3.4 G83: 임대 추상화 + IFRS16

v43 요구:
- 계약서 추출
- IFRS16 리스부채/사용권자산 스케줄
- `/api/v1/leases/abstract`, `/api/v1/leases/ifrs16`
- 관련 테이블: `lease_abstractions`, `lease_ifrs16_schedules`

현재 상태:
- 전용 서비스/라우터/모델 없음
- PDF/문서 처리 기반 일부는 문서 수준에만 존재, 현재 코드에서 전용 흐름 없음

판정:
- `미구현`

### 3.5 G84: GRESB + CDP ESG 평가

v43 요구:
- GRESB management/performance scoring
- CDP 등급
- `/api/v1/esg/gresb-assessment`
- 관련 테이블: `esg_reports`, `carbon_footprints`, `gresb_assessments`

현재 상태:
- 탄소 계산 서비스 존재
- ZEB/기후 리스크/시공 서비스 존재
- 그러나 GRESB/CDP 전용 서비스, 점수 모델, 저장 스키마, 라우터가 없다

판정:
- `부분 구현(기초 재사용 가능), 기능 자체는 미구현`

### 3.6 G85: 기후 리스크 + 재해 보험 추천

v43 요구:
- AEL(Annual Expected Loss)
- 지역별 기후 시나리오
- 보험 추천
- `/api/v1/climate/risk`
- 관련 테이블: `climate_risk_assessments`, `insurance_recommendations`

현재 상태:
- `construction_ai_service`에 `analyze_climate_risk()` 존재
- `/api/v1/construction/climate-risk` 존재
- 그러나 v43 요구와 차이:
  - 라우트 네임스페이스 다름
  - AEL 계산 없음
  - 보험 추천 없음
  - 전용 저장 테이블 없음

판정:
- `부분 구현`

### 3.7 G86: AI 마케팅 자동화 + OM 보고서

v43 요구:
- 채널별 마케팅 콘텐츠 생성
- OM 보고서
- `/api/v1/marketing/generate`, `/api/v1/marketing/om-report`
- 관련 테이블: `marketing_contents`, `offering_memorandums`

현재 상태:
- 전용 서비스/라우터/모델 없음

판정:
- `미구현`

### 3.8 G87: McKinsey 4대 도메인 AI 에이전트

v43 요구:
- asset/development/transaction/finance domain agent
- `/api/v1/agents/domain/run`, `/multi-analysis`
- 관련 테이블: `domain_agent_tasks`, `domain_agent_approvals`

현재 상태:
- 일반 7단계 오케스트레이터는 존재
- WebSocket/SSE 브릿지도 존재
- 그러나 4대 도메인 에이전트 전용 분기, 프롬프트, 결과 저장 구조는 없다

판정:
- `부분 구현(에이전트 프레임 있음), 기능 자체는 미구현`

### 3.9 G88: IoT 예측 유지보수 + HVAC 최적화

v43 요구:
- anomaly/RUL/maintenance_due
- HVAC 효율
- `/api/v1/maintenance/detect-anomaly`
- 관련 테이블: `equipment_sensors`, `predictive_maintenance_alerts`, `work_orders`

현재 상태:
- `iot_carbon_sensors` 시계열 테이블은 존재
- `drone_iot_service.py`가 있으나 G88 전용 스키마/알고리즘/라우트와 일치하지 않음
- maintenance 라우터 없음

판정:
- `부분 구현(센서 기반 일부), v43 요구 기준으로는 미구현`

### 3.10 G89: AI 임차인 경험 + 감성 분석

v43 요구:
- tenant feedback sentiment
- NPS/CSAT/CES
- `/api/v1/tenant/feedback/analyze`, `/satisfaction/nps`
- 관련 테이블: `tenant_tickets`, `tenant_sentiment_scores`, `tenant_financial_health`

현재 상태:
- 전용 서비스/라우터/모델 없음

판정:
- `미구현`

### 3.11 G90: 디지털 트윈 + 자산 인텔리전스

v43 요구:
- composite score
- asset intelligence snapshot
- `/api/v1/digital-twin/asset-intelligence`
- 관련 테이블: `asset_intelligence_snapshots`, `capex_optimization_results`

현재 상태:
- BIM/IFC와 시공/에너지/드론 기반은 존재
- 그러나 digital twin 모델, snapshot scoring, asset intelligence service/route는 없다

판정:
- `부분 구현(입력 소스 일부 보유), 기능 자체는 미구현`

### 3.12 G91: AI 토큰 비용 실시간 제어

v43 요구:
- usage log
- 예산 budget gate
- dashboard
- `/api/v1/ai-costs/dashboard`, `/budget-gate/{endpoint:path}`
- 관련 테이블: `ai_token_usage`, `ai_cost_budgets`

현재 상태:
- `ai_usage_log` 테이블 존재
- `ai_usage_tracker.py` 존재
- Prometheus `AI_COST_TOTAL`, `AI_TOKEN_TOTAL` 존재
- 그러나:
  - 예산 테이블 없음
  - dashboard route 없음
  - hard limit gate 없음
  - Redis/월간 budget 제어 없음

판정:
- `부분 구현`

### 3.13 G92: 외부 부동산 포털 연동

v43 요구:
- multi-portal post
- market data aggregate
- `/api/v1/portals/...`
- 관련 테이블: `portal_listings`, `portal_performance`

현재 상태:
- 전용 서비스/라우터/모델 없음

판정:
- `미구현`

### 3.14 G93: 다국어 AI 투자자 보고서

v43 요구:
- ko/en/ja/zh 등 다국어 투자자 보고서
- `/api/v1/reports/investor/generate`
- 관련 테이블: `multilingual_reports`

현재 상태:
- 웹 i18n은 존재
- SSE 기반 일반 보고서 스트리밍은 존재
- 그러나 투자자 보고서 생성, 다국어 보고서 저장, PDF 산출은 없음

판정:
- `부분 구현(번역/i18n 기반만 있음), 기능 자체는 미구현`

### 3.15 G94: KEPCO 전기요금 자동 계산

v43 요구:
- tariff 계산
- `/api/v1/energy/kepco/calculate`
- 관련 테이블: `kepco_rate_cache`

현재 상태:
- `integrations/kepco_client.py` 존재
- 하지만 실제 요금 계산 서비스/라우터/캐시 테이블은 없음

판정:
- `부분 구현(클라이언트 기반만 있음)`

### 3.16 G95: 에너지 효율 등급 자동화

v43 요구:
- energy grade + ZEB grade + BEMS saving
- `/api/v1/energy/certification`
- 관련 테이블: `energy_certifications`, `energy_cert_scores`

현재 상태:
- construction service의 `estimate_zeb_energy()` 존재
- carbon calculation service 존재
- 그러나 에너지 인증 전용 서비스/등급 분류/저장/라우터는 없음

판정:
- `부분 구현`

## 4. 핵심 보완/수정사항

### 4.1 즉시 수정이 필요한 기반 문제

1. 설정 계층 오류
- `DEBUG=release` 때문에 테스트와 서비스 초기화가 깨진다.
- `debug: bool`와 배포 모드 문자열을 분리해야 한다.

2. 품질게이트 기록 불일치
- `.build-journal/current-stage.json`의 테스트 통과 수치가 최신 코드와 맞지 않는다.
- 품질 상태를 기준 문서로 사용할 수 없으므로 갱신 절차가 필요하다.

3. 버전 체계 불일치
- 코드 버전은 `30.0.0`, 설계 문서는 `43.0`이다.
- 현재 상태를 v43 구현으로 오인하게 만든다.

4. mock/live 경계 불명확
- 웹은 기본적으로 mock을 우선 사용한다.
- 실제 API 구현 여부와 사용자 경험이 분리돼 있다.

### 4.2 설계상 보완이 필요한 사항

1. 스키마 확장 전략 부재
- G81~G95용 테이블/스키마/권한 모델이 아직 정의되지 않았다.

2. 라우터 네임스페이스 정합성 부족
- 예: climate risk가 v43는 `/climate/risk`인데 현재는 `/construction/climate-risk`
- 이후 프론트/문서/테스트 계약을 맞추기 어렵다.

3. 공통 보고서 엔진 재사용 전략 부재
- underwriting report, investor report, OM report, ESG report가 각각 독립 구현되면 중복이 크다.
- 템플릿/생성기/저장 규격을 공통화해야 한다.

4. 데이터 종속성 설계 부족
- G90은 G88/G89/G91/G94/G95 데이터를 재사용해야 한다.
- 선행 모듈 없이 먼저 구현하면 다시 갈아엎게 된다.

## 5. 권장 구현 전략

구현 순서는 v43 문서의 번호 순서를 그대로 따르지 말고, 아래 순서로 재배치하는 것이 맞다.

1. 기반 정합성 복구
2. 데이터 모델/계약 확장
3. Part E
4. Part F
5. Part G
6. 프론트 실연동
7. 통합 검증/출시

이 순서를 권장하는 이유:
- 현재는 신규 모듈보다 테스트/환경 불일치가 더 큰 리스크다.
- G90/G93/G95는 앞선 모듈의 데이터를 먹고 동작하므로 후순위가 맞다.
- 프론트는 아직 mock-first라 백엔드 계약을 먼저 고정해야 재작업이 줄어든다.

## 6. 상세 구현계획

### Phase 0. 기준선 복구 (우선순위 P0, 2~3일)

목표:
- “현재 저장소가 무엇을 통과하고 무엇이 깨지는지”를 신뢰할 수 있게 만든다.

작업:
- `Settings.debug` 파싱 문제 수정
  - `DEBUG`는 bool만 받게 유지
  - 문자열 배포모드는 `ENVIRONMENT` 또는 `APP_MODE`로 분리
  - `.env.test` 또는 pytest 전용 설정 계층 추가
- 테스트 실행 규약 고정
  - `python -m pytest -q`가 로컬/CI에서 동일 결과를 내도록 환경 표준화
- build journal 정정
  - `current-stage.json`의 테스트 통과 수치와 실제 결과 동기화
- 버전 표기 원칙 정의
  - 코드 버전은 아직 `30.x-current`
  - v43 scope 완료 시점에만 `43.0.0`으로 승격

검증 기준:
- pytest가 설정 오류 없이 실행될 것
- 실패가 환경이 아니라 코드/테스트 로직 때문인지 구분 가능할 것
- build journal 상태가 실제 결과와 일치할 것

산출물:
- 설정 패치
- `.env.test` 또는 테스트 fixture 설정
- build journal 갱신

### Phase 1. 데이터 모델/계약 확장 (P0, 4~6일)

목표:
- G81~G95를 수용할 공통 DB/Schema/API 계약을 먼저 고정한다.

작업:
- Alembic 마이그레이션 추가
  - Part E 묶음
  - Part F 묶음
  - Part G 묶음
- SQLAlchemy 모델 추가
  - G81~G95 전용 테이블군
- `packages/schemas/models.py` 확장
  - underwriting/compliance/lease/esg/climate
  - marketing/domain/iot/tenant/digital-twin
  - ai-cost/portal/investor-report/kepco/energy-cert
- RBAC 스코프 추가
  - `underwriting`, `compliance`, `leases`, `esg`, `climate`
  - `marketing`, `maintenance`, `tenant_experience`, `asset_intelligence`
  - `ai_costs`, `portals`, `energy`

검증 기준:
- 신규 모델 import 시 순환참조/타입 오류가 없을 것
- Alembic upgrade/downgrade가 정상 동작할 것
- OpenAPI schema에 신규 계약이 노출될 것

### Phase 2. Part E 구현 (P1, 7~10일)

#### 2-1. 비즈 인프라/출시 검증 보강

작업:
- `notifications` 라우터 추가
  - Mock AlimTalk send
- `esign` 라우터/서비스 추가
  - 요청 생성, 상태 조회
- `dashboard` 라우터 추가
  - stats
  - portfolio timeline
  - recent activity
- `system` 라우터 추가
  - full health
  - version

검증 기준:
- v43 Part E checklist의 Phase 14~15 API 충족

#### 2-2. G81~G85 구현

G81:
- underwriting service
- LP report generator
- data room doc classification
- `/api/v1/underwriting/{project_id}`, `/history`

G82:
- compliance/KYC/AML service
- KYC 문서 분류 + AML 점수 + STR 플래그
- `/api/v1/compliance/kyc`, `/history/{project_id}`

G83:
- lease abstraction service
- IFRS16 schedule service
- `/api/v1/leases/abstract`, `/ifrs16`

G84:
- GRESB/CDP ESG service
- carbon/ZEB/climate 데이터 재사용
- `/api/v1/esg/gresb-assessment`

G85:
- climate risk service 분리
- AEL 계산, 보험 추천
- `/api/v1/climate/risk`
- 현재 `/construction/climate-risk`와 중복 로직은 공통 함수로 흡수

검증 기준:
- Part E 체크리스트 API 전부 통과
- G81 risk_grade A~E
- G82 risk_score 0~100
- G83 IFRS16 상환스케줄
- G84 GRESB 1~5 star
- G85 LOW/MEDIUM/HIGH + insurance recommendation

### Phase 3. Part F 구현 (P1, 7~9일)

#### 3-1. G86 AI 마케팅
- channel content generator
- OM report generator
- `/api/v1/marketing/generate`
- `/api/v1/marketing/om-report`

#### 3-2. G87 4대 도메인 에이전트
- 현재 generic orchestrator와 별도 계층으로 구현
- domain-specific prompt/system/context registry
- `/api/v1/agents/domain/run`
- `/api/v1/agents/domain/multi-analysis`

#### 3-3. G88 예측 유지보수
- sensor/reading/alert/work order 모델 추가
- anomaly detection + RUL + HVAC efficiency
- `/api/v1/maintenance/detect-anomaly`

#### 3-4. G89 임차인 경험
- feedback sentiment
- AI reply
- NPS/CSAT/CES aggregation
- `/api/v1/tenant/feedback/analyze`
- `/api/v1/tenant/satisfaction/nps`

#### 3-5. G90 디지털 트윈/자산 인텔리전스
- digital twin aggregate model
- composite score
- adjusted value
- `/api/v1/digital-twin/asset-intelligence`

의존성:
- G90은 G88/G89/G81/G91 일부 데이터가 들어와야 품질이 난다.
- 최소 구현은 mock aggregation으로 시작하되, 저장 스키마는 최종형으로 설계해야 한다.

검증 기준:
- Part F 체크리스트 API 전부 통과
- G88 anomaly/rul/hvac_efficiency
- G89 sentiment score + AI reply
- G90 composite_score/grade/adjusted_value_krw

### Phase 4. Part G 구현 (P1, 5~7일)

#### 4-1. G91 AI 비용 제어
- 기존 `ai_usage_tracker`와 Prometheus metrics를 재사용
- budget table + budget gate service 추가
- `/api/v1/ai-costs/dashboard`
- `/api/v1/ai-costs/budget-gate/{endpoint:path}`

#### 4-2. G92 외부 포털 연동
- portal adapter registry
- mock/live mode 분리
- posting history/performance 저장
- `/api/v1/portals/{portal_id}/post`
- `/api/v1/portals/post-all`
- `/api/v1/portals/market-data/{region_code}`

#### 4-3. G93 다국어 투자자 보고서
- 기존 i18n과는 별도로 backend investor report service 구성
- 다국어 섹션 생성 + PDF 전략 수립
- `/api/v1/reports/investor/generate`

#### 4-4. G94 KEPCO 요금 계산
- 현재 `KepcoClient`는 사용량 조회 기반
- 여기에 tariff calculator service와 cache table을 붙여 완성
- `/api/v1/energy/kepco/calculate`

#### 4-5. G95 에너지 인증
- 현재 ZEB/탄소 계산 로직을 재사용
- 1차에너지 소요량, 에너지등급, ZEB등급, BEMS saving 추가
- `/api/v1/energy/certification`

검증 기준:
- Part G 체크리스트 API 전부 통과
- G91 month total/budget gate
- G92 posted/success count/market data
- G93 5개 섹션 다국어 생성
- G94 tariff별 계산 정확성
- G95 energy_grade/zeb_grade/bems_saving

### Phase 5. 프론트엔드 실연동 전환 (P1, 5~7일)

목표:
- 현재 mock-first UI를 실제 v43 모듈 중심 UI로 전환한다.

작업:
- `NEXT_PUBLIC_USE_MOCKS` 기본값 재검토
- dashboard/integration status를 실제 API와 연결
- v43 신규 라우트 페이지 추가
  - underwriting
  - compliance
  - leases
  - esg
  - climate
  - marketing
  - maintenance
  - tenant experience
  - digital twin
  - ai costs
  - portals
  - investor reports
  - energy
- mock placeholder 제거 기준 정의
  - backend API + schema + query key + error state까지 완료된 화면만 실연동 전환

검증 기준:
- mock 없이도 최소 핵심 플로우 동작
- 신규 화면이 실제 응답과 상태를 렌더링
- 오프라인/에러 상태 fallback 유지

### Phase 6. 통합 검증/릴리즈 준비 (P0, 4~5일)

작업:
- Part H 기준 E2E 점검표 재작성
- API smoke test
- pytest 전체 재정비
- 필요한 경우 load test/locust 시나리오 추가
- 문서/버전/배포 체크리스트 정리

반드시 확인할 항목:
- 설정 파일만으로 테스트가 깨지지 않는가
- mock/live 전환이 의도대로 동작하는가
- build journal 기록이 실제 테스트 결과와 일치하는가
- v43 신규 API가 RBAC와 tenant isolation을 준수하는가

## 7. 우선순위 백로그

### 즉시 착수해야 할 항목

1. `Settings.debug`/환경 변수 정합성 수정
2. build journal 테스트 수치 갱신
3. Part E~G 공통 스키마/마이그레이션 설계
4. v43 신규 RBAC 스코프 설계
5. Part E 비즈 인프라 라우터 추가
6. G81 underwriting service
7. G82 compliance/KYC service
8. G83 lease abstraction/IFRS16
9. G85 climate risk service 분리 및 AEL 추가
10. 프론트 mock/live 전환 기준 문서화

### 후순위지만 반드시 묶어서 가야 하는 항목

1. G90 asset intelligence는 G88/G89/G91 이후
2. G93 investor report는 G81/G84/G85/G90 이후
3. G95 energy certification은 G94 + 기존 ZEB/carbon 정리 이후

## 8. 최종 판정

현재 저장소는 “v43 문서의 일부 기반을 재사용할 수 있는 상태”이지, “v43 구현 완료 상태”는 아니다.

핵심 판단:
- 현재 구현 현황은 `v30 핵심 모듈 + 일부 후속 기능`
- v43의 본체인 `G81~G95`는 대부분 미구현
- 테스트/환경 정합성 문제로 인해 기능 확대 전에 기반 복구가 필요
- 가장 합리적인 실행 순서는 `기반 복구 → 스키마/계약 → Part E → Part F → Part G → 프론트 실연동 → 통합검증`

권장 운영 원칙:
- v43 신규 기능은 문서 순서보다 의존성 순서로 구현
- mock UI는 backend contract 완료 전까지만 유지
- build journal은 매 단계 실제 검증 결과로 즉시 갱신
