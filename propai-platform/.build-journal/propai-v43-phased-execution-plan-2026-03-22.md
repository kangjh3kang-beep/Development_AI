# PropAI v43 단계별 구현·구축 실행계획

작성일: 2026-03-22

기준 문서:
- `.build-journal/propai-v43-gap-analysis-implementation-plan-2026-03-21.md`
- `.build-journal/current-stage.json`
- `apps/api/config.py`
- `tests/`

## 1. 현재 기준선

검증 기준을 다시 잡은 현재 상태는 다음과 같다.

- 코드 기준 버전은 아직 `v30.0.0`이다.
- v43 문서의 핵심 범위인 `G81~G95`는 대부분 서비스, 라우터, DB 테이블이 비어 있다.
- 프론트는 여전히 `mock-first` 구조가 강하다.
- 오늘 기준으로 실행한 유지 관리 대상 테스트 스위트는 `python -m pytest -q` 기준 `732 passed, 34 skipped`다.
- 이 결과가 안정적으로 나오도록 `DEBUG=release` 같은 문자열 환경값을 허용하도록 설정 정규화를 넣었고, 루트 `pytest` 기본 탐색 범위를 `tests/`로 고정했다.
- 추가로 `system`, `dashboard`, `ai-costs`, `energy` 운영 API와 공통 계약 모델을 먼저 올려 v43 Phase 1 착수를 시작했다.
- 이어서 `notifications`, `esign` 운영 API와 대응 테이블/권한까지 추가해 Part E 운영 계층 1차분을 구현했다.

정리하면 현재 저장소는 "v43 완성본"이 아니라 "v30.x 기반 플랫폼 + 일부 후속 기능 + v43 확장 예정 상태"다. 따라서 구현계획은 기능 추가보다 먼저 기준선 복구, 계약 고정, 이후 순차 확장 방식으로 가야 한다.

## 2. 실행 원칙

이번 v43 추진은 아래 원칙으로 진행한다.

1. Contract-first
API, 스키마, 권한, 이벤트 계약을 먼저 고정한 뒤 서비스와 UI를 붙인다.

2. Default command stability
루트 기준 `python -m pytest -q`와 문서상의 품질게이트가 일치해야 한다.

3. Mock retirement by phase
백엔드 계약이 완료된 모듈부터 순차적으로 mock을 제거한다.

4. Shared engine before feature explosion
보고서 생성, 점수 산정, AI 비용 추적, 에너지 계산처럼 공통 엔진이 필요한 기능은 먼저 기반을 만든 뒤 각 G번호에 재사용한다.

## 3. 단계별 구현 로드맵

### Phase 0. 기준선 복구

목표:
- 현재 저장소가 동일한 명령으로 재현 가능하게 동작하도록 만든다.

세부 작업:
- 설정 정규화
  - `DEBUG` 문자열 값을 bool로 정규화
  - 배포 모드 문자열과 실제 디버그 플래그를 분리
- 테스트 진입점 고정
  - 루트 `pytest` 기본 탐색 범위를 `tests/`로 고정
  - 유지 관리 중인 스위트와 레거시 테스트 트리를 분리
- 품질게이트 기록 정합화
  - `.build-journal/current-stage.json`을 실제 결과와 일치시킴
- 레거시 테스트 분류
  - `apps/api/tests/`는 별도 복구 트랙으로 관리
  - `asyncpg` 같은 선택 의존성 때문에 기본 게이트를 깨지 않도록 분리

산출물:
- `apps/api/config.py` 설정 정규화
- `tests/unit/test_config_settings.py`
- `pytest.ini`
- 갱신된 `.build-journal/current-stage.json`

완료 기준:
- 루트 기준 `python -m pytest -q` 성공
- 환경값 오염으로 인한 Settings 초기화 실패 제거
- 품질게이트 문서와 실제 실행값 일치

실행 상태:
- 완료

### Phase 1. 공통 데이터 모델/계약 확장

목표:
- `G81~G95` 구현이 올라갈 공통 DB/API/RBAC 기반을 먼저 확정한다.

세부 작업:
- Alembic 마이그레이션 3묶음 설계
  - Part E 묶음: underwriting, compliance, lease, esg, climate
  - Part F 묶음: marketing, domain agents, maintenance, tenant, digital twin
  - Part G 묶음: ai-cost budgets, portals, investor reports, kepco, energy certification
- ORM 모델 추가
  - `investment_underwriting`, `lp_reports`, `data_room_docs`
  - `compliance_checks`, `kyc_documents`, `aml_screenings`
  - `lease_abstractions`, `lease_ifrs16_schedules`
  - `esg_reports`, `gresb_assessments`, `carbon_footprints`
  - `climate_risk_assessments`, `insurance_recommendations`
  - `marketing_contents`, `offering_memorandums`
  - `domain_agent_tasks`, `domain_agent_approvals`
  - `equipment_sensors`, `predictive_maintenance_alerts`, `work_orders`
  - `tenant_tickets`, `tenant_sentiment_scores`, `tenant_financial_health`
  - `asset_intelligence_snapshots`, `capex_optimization_results`
  - `ai_cost_budgets`, `portal_listings`, `portal_performance`
  - `multilingual_reports`, `kepco_rate_cache`, `energy_certifications`, `energy_cert_scores`
- 스키마/이벤트 계약 확장
  - `packages/schemas/`와 OpenAPI 응답 모델 선행 정의
- RBAC 확장
  - `underwriting`, `compliance`, `leases`, `esg`, `climate`
  - `marketing`, `maintenance`, `tenant_experience`, `asset_intelligence`
  - `ai_costs`, `portals`, `energy`

완료 기준:
- 마이그레이션 up/down 성공
- OpenAPI 생성 가능
- 신규 모델 import 순환참조 없음
- 기본 CRUD 단위 테스트 통과

의존성:
- Phase 0 완료

실행 상태:
- 진행 중
- 공통 계약 모델과 `system/dashboard/ai-costs/energy` 라우터 선반영 완료

### Phase 2. Part E 구현

목표:
- 사업 출시에 필요한 운영/투자/준법/임대/ESG/기후 리스크 기능을 API 수준까지 완성한다.

작업 묶음:

1. Launch/Ops 보강
- `/api/v1/notifications/alimtalk`
- `/api/v1/esign/request`
- `/api/v1/esign/{id}/status`
- `/api/v1/dashboard/stats`
- `/api/v1/dashboard/portfolio/timeline`
- `/api/v1/dashboard/activity/recent`
- `/api/v1/system/health/full`
- `/api/v1/system/version`

2. G81 투자 언더라이팅
- 투자 점수화, 리스크 등급 A~E
- LP 리포트 생성
- DataRoom 문서 분류

3. G82 준법감시/KYC/AML
- KYC 문서 분류
- AML 리스크 0~100 점수
- STR 후보 플래그

4. G83 리스 추상화/IFRS16
- 계약서 핵심 조건 추출
- IFRS16 리스부채/사용권자산 스케줄

5. G84 ESG 평가
- GRESB score/star
- CDP grade
- 탄소/ZEB/기후 데이터 재사용

6. G85 기후 리스크
- AEL 계산
- 보험 추천
- 기존 `/construction/climate-risk` 로직을 공통 서비스로 흡수

완료 기준:
- Part E API 응답 스키마 고정
- 단위 테스트 + 계약 테스트 통과
- 샘플 프로젝트 기준 end-to-end smoke pass

### Phase 3. Part F 구현

목표:
- 마케팅, 도메인 에이전트, 유지보수, 테넌트 경험, 디지털트윈 계층을 완성한다.

작업 묶음:

1. G86 AI 마케팅/OM
- 채널별 콘텐츠 생성
- OM 보고서 생성

2. G87 도메인 에이전트
- asset, development, transaction, finance 전용 실행 경로
- 승인/재실행/비교 분석 구조

3. G88 예지보전/HVAC 최적화
- 센서 이상탐지
- RUL 추정
- maintenance alert/work order 발행

4. G89 테넌트 경험
- 감성 분석
- AI 응답 초안
- NPS/CSAT/CES 집계

5. G90 디지털트윈/자산 인텔리전스
- composite score
- capex 최적화
- adjusted value 산정

완료 기준:
- G86~G90 응답 계약 확정
- 도메인 에이전트 결과 저장/재조회 가능
- G90이 G88/G89/G91 데이터를 결합해 스냅샷 생성

의존성:
- Phase 1 완료
- G90은 G88/G89/G91 선행 데이터 구조 필요

### Phase 4. Part G 구현

목표:
- AI 비용 통제, 포털 자동화, 투자자 보고서, 에너지 계산/인증 계층을 완성한다.

작업 묶음:

1. G91 AI 비용 제어
- 비용 대시보드
- budget gate
- endpoint별 누적/월간 제한

2. G92 멀티 포털 연동
- 포털 어댑터 레지스트리
- posting history/performance
- mock/live 전환 전략

3. G93 다국어 투자자 보고서
- ko/en/ja/zh 템플릿
- 섹션별 생성
- PDF export pipeline

4. G94 KEPCO 전기요금 계산
- tariff calculator
- rate cache

5. G95 에너지 인증
- energy grade
- ZEB grade
- BEMS saving

완료 기준:
- G91~G95 API 및 배치 경로 통과
- 비용/포털/에너지 모듈에 대한 권한 모델 반영
- 보고서와 계산 결과가 저장/재조회 가능

의존성:
- Phase 1 완료
- G93은 G81/G84/G85/G90 결과를 재사용
- G95는 G94와 기존 ZEB/carbon 로직 정리가 선행되어야 함

### Phase 5. 프론트 실연동 전환

목표:
- 현재 mock-first UI를 실제 계약 기반 UI로 전환한다.

세부 작업:
- `NEXT_PUBLIC_USE_MOCKS` 기본 동작 재정의
- 대시보드/프로젝트 상세 실데이터 연결
- v43 신규 모듈 페이지 추가
- 각 화면별 loading/error/empty state 고정
- mock placeholder 제거 기준 수립

완료 기준:
- 신규 v43 화면이 실제 API 응답을 렌더링
- mock 없이 핵심 시나리오 데모 가능
- 권한/테넌트 분기 반영

### Phase 6. 통합검증 및 배포 준비

목표:
- v43 범위를 실제 릴리스 가능한 수준으로 마감한다.

세부 작업:
- API smoke/E2E 시나리오
- load test/locust 보강
- build journal, 버전, 릴리스 노트 정합화
- mock/live 전환 체크
- 운영 알람, 예산 한도, 감사 로그 점검

완료 기준:
- 루트 테스트 게이트 통과
- Part E/F/G 대표 시나리오 smoke pass
- 운영 체크리스트 완료 후 버전 승격 준비

## 4. 우선순위 백로그

### 즉시 착수

1. Phase 1 스키마 설계 초안 작성
2. 신규 RBAC scope 목록 확정
3. Part E 라우터/서비스 인터페이스 설계
4. 기후 리스크 공통 서비스 분리안 작성
5. 프론트 mock 제거 기준표 작성

### 선행 의존성 이후 착수

1. G90 자산 인텔리전스
2. G93 다국어 투자자 보고서
3. G95 에너지 인증

## 5. 오늘 실행한 항목

실행 완료:
- `apps/api/config.py`
  - `DEBUG=release`, `DEBUG=development` 같은 문자열을 허용하도록 설정 정규화
- `tests/unit/test_config_settings.py`
  - 환경값/직접주입값에 대한 회귀 테스트 추가
- `pytest.ini`
  - 루트 기준 기본 테스트 탐색 범위를 `tests/`로 고정
- `packages/schemas/models.py`
  - v43 운영성 모듈용 공통 계약 모델 추가
- `apps/api/routers/system.py`
  - `/api/v1/system/version`, `/api/v1/system/health/full` 추가
- `apps/api/routers/dashboard.py`
  - `/api/v1/dashboard/stats`, `/portfolio/timeline`, `/activity/recent` 추가
- `apps/api/routers/ai_costs.py`
  - `/api/v1/ai-costs/dashboard`, `/budget-gate/{endpoint:path}` 추가
- `apps/api/routers/energy.py`
  - `/api/v1/energy/kepco/calculate`, `/certification` 추가
- `apps/api/auth/rbac.py`
  - `dashboard`, `system`, `ai_costs`, `energy` 읽기 권한 추가
- `tests/unit/test_v43_phase1_contracts.py`
  - 신규 라우터/계약/RBAC 회귀 테스트 추가
- `apps/api/database/models/notification_message.py`
  - 알림 발송 로그 테이블 추가
- `apps/api/database/models/esign_request.py`
  - 전자서명 요청 테이블 추가
- `apps/api/routers/notifications.py`
  - `/api/v1/notifications/alimtalk` 추가
- `apps/api/routers/esign.py`
  - `/api/v1/esign/request`, `/{request_id}/status` 추가
- `apps/api/database/migrations/versions/003_add_notifications_esign_tables.py`
  - notifications/esign 테이블 및 RLS 마이그레이션 추가
- `tests/unit/test_notifications_esign.py`
  - notifications/esign 모델/스키마/라우터/RBAC 회귀 테스트 추가
- `.build-journal/current-stage.json`
  - 현재 품질게이트와 실행 포커스를 실제 상태로 갱신

검증 결과:
- `python -m pytest -q`
  - `732 passed, 34 skipped`

주의사항:
- `apps/api/tests/` 레거시 트리는 기본 게이트에서 분리했다.
- 해당 트리는 `asyncpg` 의존성과 별도 서비스 구조를 갖고 있어, 필요하면 별도 복구 태스크로 다뤄야 한다.

## 6. 다음 실행 순서

다음 턴에서 바로 이어서 할 작업은 아래 순서가 가장 합리적이다.

1. G81~G85용 DB 스키마와 신규 권한 scope를 묶음으로 확정
2. G81, G82, G83, G85 순으로 핵심 비즈니스 기능 구현
3. 그 결과를 바탕으로 G84 ESG와 Part F/G 의존 기능 연결
4. 이후 포털/투자자 보고서/에너지 인증 고도화로 확장

이 순서를 따르면 v43 문서 번호를 그대로 따라가는 것보다 재작업이 적고, 프론트 실연동 시점도 더 빨라진다.
