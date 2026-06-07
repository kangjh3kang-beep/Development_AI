# PropAI 백엔드 아키텍처 감사 보고서 (읽기전용)

- 감사일: 2026-06-05
- 대상 루트: `propai-platform/apps/api`
- 라우터 등록: `apps/api/main.py:327-475` (FastAPI `include_router`)
- 엔드포인트 총계: 약 **371개** (라우터 데코레이터 기준) + sales 43개
- 서비스 레이어: **3중 구조** — `app/services/**`(도메인·AI·전주기), `apps/api/services/**`(64개 운영 서비스), `app/api/endpoints/sales/**`(분양 ERP)

---

## 1. 라우터/엔드포인트 인벤토리

라우터는 **두 패키지**로 분산되어 main.py가 통합 마운트한다.
- `apps/api/routers/**` (약 68개, `main.py:29-96` 일괄 import → `:327-405` 마운트)
- `apps/api/app/routers/**` (약 25개, `main.py:98-165` 개별 try-import → `:408-475` 격리 마운트, 로드 실패해도 앱 부팅 유지)

| 도메인 그룹 | 주요 라우터(prefix) | 근거 |
|---|---|---|
| 부지/입지 | site_score(`/api/v1/site-score`), auto_zoning(`/api/v1/zoning`), land_price(`/api/v1/land-price`), registry(`/api/v1`) | `app/routers/site_score.py:13`, `routers/auto_zoning.py`, `app/routers/land_price.py:12` |
| 설계/CAD/BIM | design(`/api/v1/design`), design_v61, drawing(`/api/v1/drawing`), bim(`/api/v1/bim`), cad_correction | `app/routers/design_v61.py:20`, `routers/bim.py` |
| 인허가/법규 | permits(`/api/v1/permits`), regulation, building_compliance(420줄), development_methods | `routers/building_compliance.py`, `routers/permits.py` |
| 사업성/재무 | v2_feasibility(`/api/v2/feasibility`), finance, v2_tax(`/api/v2/tax`), monte_carlo, lcc, underwriting | `app/routers/v2_feasibility.py:37`, `app/routers/v2_tax.py:17` |
| 공사비 | cost(`/api/v1/cost`), cost_intelligence | `app/routers/cost.py:21` |
| ESG/탄소 | esg(중복 마운트 2곳, first-match 무해), gresb, re100, eu_taxonomy, energy, climate | `app/routers/esg.py:10`, `main.py:364,459` |
| 입찰(G2B) | g2b_bid(`/g2b`→`/api/v1/g2b`) | `app/routers/g2b_bid.py:25` |
| 분양 ERP | sales_router(`/api/v1/sales`) + WS, lifecycle_p5/p6 | `app/api/endpoints/sales/__init__.py:67-79` |
| 운영(시설) | maintenance, tenant, digital_twin, parking, safety, facility_reservations, leases | `routers/*.py` |
| AI/원장/검증 | ai_analyze(`/api/v1/ai`), analysis_ledger, verification, expert_panel, agents, domain_agents | `app/routers/analysis_ledger.py:17` |
| 신뢰/메타 | data_integrity(`/api/v1`), admin_secrets | `app/routers/admin_secrets.py:23` |

리스크: 라우터 이원화 + esg 이중 마운트. first-match로 충돌은 없으나 신규 개발 시 **어느 패키지에 추가할지 혼선** 유발.

---

## 2. 서비스 레이어 성숙도 매트릭스

분류: ✅구현완료(실로직+영속/외부연동) · 🟡부분(휴리스틱/단순모델) · 🟧스텁(폴백 위주) · ❌미구현

| 도메인 | 등급 | 근거 |
|---|---|---|
| **land_intelligence** (토지·시세·약식감정) | ✅ | `comprehensive_analysis_service.py`, `land_info_service.py`, `nearby_map_service.py`, `desk_appraisal_service.py` — VWorld/MOLIT/NED 실연동(`grep: vworld_service/molit_service/land_price_estimator`) |
| **ledger** (해시체인 원장) | ✅ | `ledger/analysis_ledger_service.py:188-342` — append-only, content/prev_hash, 멱등, verify_chain 변조탐지, 쿼터·prune 완비 |
| **verification** (검증·할루시네이션) | ✅ | `verifier_service.py:1-60` — 규칙 prescan + LLM 근거검증 + 폴백; `range_rules.py`, `calc_ledger.py` |
| **data_validation** (무결성) | ✅ | `validator.py`(Pydantic 검증+IQR 이상치+FreshnessChecker), `public_data_registry.py`(소스 상태 중앙관리), `calculation_metadata.py` |
| **ai (인터프리터)** | ✅ | `ai/base_interpreter.py:157-388` — 공통 LLM 호출/그라운딩/2단 캐시(L1+Redis)/prompt-caching/과금 누적. 9~10개 인터프리터 공유 |
| **external_api** (공공데이터) | ✅ | `external_api/{vworld,molit,reb_client,building_registry,commercial_area}.py` — httpx 실호출 |
| **registry** (등기) | ✅ | `registry_service.py`, `apick_client.py`, `tilko_client.py` — 유료API 클라이언트 실연동 |
| **g2b (입찰분석)** | ✅(규칙)+🟡(LLM옵션) | `ai_services/bid_analyzer.py:146-160` — 6엔진 규칙기반 + 선택적 `BidInterpreter` LLM. `random.seed(42)`는 결정적 시뮬용 |
| **site_score / solar_envelope** | ✅ | `site_score_service.py`, `solar_envelope_service.py` |
| **report** (PDF/은행보고서) | ✅ | `report/bank_ready_report_service.py`, `pipeline_report_pdf.py`(reportlab) |
| **feasibility/finance/tax/cost** | ✅ | `feasibility/feasibility_service_v2.py`, `finance_cost_engine.py`, v2 라우터 연결 |
| **pipeline (전주기 오케스트레이션)** | ✅ | `pipeline/project_pipeline.py:201-242,757-788` — 단계별 interpreter 인라인 부착 |
| **safety (CV 안전관리)** | ✅ | `services/safety_service.py:41-170` — 실제 YOLOv8(ultralytics)+cv2, 모델 미설치 폴백 |
| **parking (번호판 OCR)** | ✅ | `services/parking_service.py:37-71` — cv2+easyocr, 미설치 시 Mock OCR 폴백 |
| **digital_twin / demand_forecast** | 🟡 | `services/digital_twin_service.py:194-208` 단순 선형회귀, `demand_forecast_service.py:98-111` 이동평균/SES — 동작하나 모델 단순 |
| **drone_iot** | 🟧 | 메모리상 Fallback 구조화 스텁(라이브 IoT 디바이스 미연동) |
| **kdx / digital twin 실시간** | 🟡 | `kdx_integration_service.py` WS/메트릭 실DB, 그러나 외부 KDX 피드 연동은 환경의존 |

운영 서비스(`apps/api/services/` 64개: maintenance/tenant/lease/auction/contractor/underwriting 등)는 **전부 ORM 모델+RBAC+영속 로직 보유**(스텁 아님). 단, 이들 다수는 **localStorage 기반 프론트와 미연동**(아래 6번).

---

## 3. AI/LLM 인터프리터 현황

공통기반 `ai/base_interpreter.py`를 상속하는 **10개 인터프리터** 전부 존재·연결:

| 인터프리터 | 단계 | 연결처(근거) |
|---|---|---|
| site_analysis | 부지분석 | `pipeline/project_pipeline.py:786-788` (`_attach_site_ai`) |
| design | 설계 | `project_pipeline.py:219,226` / `app/routers/design_v61.py` |
| cost | 공사비 | `project_pipeline.py:220,227` / `app/routers/cost.py` |
| feasibility | 사업성 | `project_pipeline.py:221,228` / `feasibility_service_v2.py` |
| tax | 세금 | `project_pipeline.py:222,229` |
| esg | ESG | `project_pipeline.py:223,230` / `routers/esg.py` |
| avm | 시세추정 | `services/avm_service.py` |
| market | 시장 | `market/market_report_service.py` |
| permit | 인허가 | `routers/auto_zoning.py`, permit_analysis |
| report | 보고서 | `services/investor_report_service.py` |
| (bid) | 입찰 | `ai_services/bid_interpreter.py` (G2B 전용) |

- 공통기반 강점: 그라운딩 규칙 자동 주입(`base_interpreter.py:44-50`), 2단 캐시(L1 TTL + L2 Redis, `:256-268`), Anthropic prompt-caching(`:297-300`), 구독자 LLM 과금 누적(`:132-154`), JSON 파싱 폴백(`:354-388`). 9곳 반복 버그를 단일화한 설계.
- **RAG/벡터**: `legal/alris_service.py`, `permit_interpreter.py`, `esg/lca_service.py`, `market/conversational_market_ai.py`, `registry_analysis_service.py` 등에서 사용. Qdrant 초기화 `main.py:23`(`init_qdrant_collections`). **단, 법규 RAG 임베딩은 OpenAI SDK 미설치 의존**(메모리상 제약).

---

## 4. 데이터 무결성/검증 인프라 (깊이)

| 컴포넌트 | 깊이 | 근거 |
|---|---|---|
| analysis_ledger | **깊음** | 해시체인+계보+멱등+쿼터+prune+verify (`analysis_ledger_service.py` 343줄, raw SQL `_ensure` DDL 자가생성) |
| validator | **중상** | Pydantic field_validator(가격/면적/층/PNU/세율/용적률 범위) + IQR 이상치 + 신선도(`validator.py:14-171`) |
| public_data_registry | **중** | 소스별 상태/신선도 중앙관리(`public_data_registry.py:1-40`), in-memory 상태(영속 DB 아님) |
| verifier_service | **중상** | 규칙 prescan + LLM 근거검증 + 폴백(`verifier_service.py`) |
| calc_ledger / range_rules | **중** | 계산 검증·범위규칙(`verification/`) |

핵심 리스크: `analysis_ledger`·`quota` 테이블은 **Alembic 마이그레이션이 아니라 런타임 `CREATE TABLE IF NOT EXISTS`**(`analysis_ledger_service.py:23-51,85-90`)로 생성 — 스키마 버전관리 밖. `public_data_registry`는 **프로세스 메모리**라 다중워커/재시작 시 상태 유실.

---

## 5. 전주기 9단계 커버리지 갭

| 단계 | 백엔드 성숙도 | 비고 |
|---|---|---|
| 1 부지발굴 | ✅ 강 | site_score, auto_zoning, land_price, nearby_map |
| 2 분석(시세/법규/입지) | ✅ 강 | comprehensive_analysis, MOLIT/REB, regulation |
| 3 설계(CAD/BIM) | ✅ 중상 | design_v61, IFC→glTF, drawing. 자동산출 zone_code 한글매핑 부정확 |
| 4 인허가 | ✅ 중상 | permits, building_compliance, dev_methods, seumter |
| 5 사업성/재무 | ✅ 강 | v2_feasibility, finance, tax, monte_carlo, underwriting |
| 6 시공 | 🟡 **약** | construction_ai 존재하나 공정/원가관리 ERP 깊이 부족, safety(CV)는 별개 강점 |
| 7 분양(ERP) | 🟡 **부분** | sales ERP Part1(66테이블 모델)만, lifecycle_p5/p6 엔드포인트 소수, RLS/마이그레이션 보류 |
| 8 ESG | ✅ 강 | gresb, eu_taxonomy, re100, lca, carbon |
| 9 운영(시설/자산) | 🟡 **약** | maintenance/digital_twin/tenant 서비스는 있으나 단순모델+프론트 미연동, drone_iot 스텁 |

**갭 Top (우선순위순):**
1. **운영(9단계)** — digital_twin 단순 선형회귀, drone_iot 스텁, 실시간 센서 파이프라인 부재.
2. **분양 ERP(7단계)** — 데이터 모델만 존재, lifecycle 상태전이·RLS·마이그레이션 미완.
3. **시공(6단계)** — 공정·기성·원가 실시간 관리 ERP 빈약(QTO/적산은 강하나 시공 실행관리 약).

---

## 6. 기술부채/리스크

1. **라우터 이원화·중복마운트** — `routers/**` vs `app/routers/**`, esg 2중 마운트(`main.py:364,459`). 신규 개발 혼선·라우트 충돌 잠재.
2. **런타임 DDL(마이그레이션 우회)** — `analysis_ledger`(`:23-90`), 메모리상 다수 `CREATE TABLE IF NOT EXISTS`. Alembic 밖이라 스키마 드리프트·롤백 불가.
3. **public_data_registry 휘발성** — 프로세스 메모리 상태, 다중워커 비일관·재시작 유실(`public_data_registry.py`).
4. **localStorage 의존** — 프로젝트/부지분석/스냅샷이 프론트 localStorage(백엔드 `/projects` 부분연동). `apps/api/services/` 운영 서비스 64개와 프론트가 대부분 미연결 — 기기간 동기화·서버 권위 데이터 부재.
5. **단일워커 한계** — platform_secrets env 오버레이/메모리 레지스트리/in-process L1캐시가 단일워커 가정. 수평확장 시 캐시 비일관·시크릿 리로드 문제.
6. **키 의존/폴백** — OpenAI SDK 미설치(법규 RAG 임베딩 영향), apps/api/.env 더미키(루트 .env 의존, CWD 함정), MOLIT 외 다수 공공API 미승인(403 폴백).
7. **격리 try-import 마운트** — `app/routers` 로드 실패 시 조용히 누락(`main.py:455-475`). 부팅은 살지만 **엔드포인트 404가 은폐**됨(관측성 부족).
8. **CV/IoT 모델 가중치 의존** — safety YOLOv8(`yolov8n.pt`), parking easyocr 미설치 시 Mock — 운영서버 모델배포 누락 시 무성(無聲) 저품질.

---

## 혁신 기회 (다음 리서치팀용, 백엔드 약점 기반)

1. **운영(O&M) 디지털트윈 고도화** — 단순 선형회귀(`digital_twin_service.py:208`)를 시계열/이상탐지 모델로 교체, 실시간 센서 스트림(drone_iot 스텁→MQTT/Kafka) 연동. 9단계 최대 공백.
2. **분양 ERP 상태기계 완성** — sales lifecycle_p5/p6를 상태전이 완전성 갖춘 워크플로 엔진으로(계약→중도금→입주). 66테이블 모델 자산 활용.
3. **시공 실행관리(공정·기성) ERP** — QTO/적산(강점)을 공정표·기성청구·원가실적과 연결해 5단계 사업성↔6단계 시공 폐루프.
4. **분석원장 외부 앵커링** — 해시체인(`analysis_ledger_service.py`)에 일배치 Merkle 루트 외부 앵커링 추가 → "블록체인급 증명" 차별화(코드 주석에 이미 설계 언급 `:10`).
5. **public_data_registry 영속화+SLA 대시보드** — 메모리→DB 영속, 소스별 신선도/장애 SLA 모니터링·자동 폴백 라우팅. 할루시네이션 방지의 운영 백본.
6. **라우터/스키마 단일화 리팩토링** — 이원 패키지 통합 + 격리 try-import 마운트 실패의 가시화(헬스체크에 라우트 등록현황 노출).
7. **수평확장 대응** — in-process L1캐시·메모리 레지스트리·env 시크릿 오버레이를 Redis/DB 권위소스로 이전(단일워커 탈피).
8. **RAG 임베딩 자립** — OpenAI 의존 법규 RAG를 로컬/한국어 임베딩(예: bge-m3) + Qdrant로 자립화, 키 장애 무관 동작.
9. **운영 서비스↔프론트 풀스택 연결** — `apps/api/services/` 64개 운영서비스(lease/maintenance/tenant 등)와 프론트 localStorage를 서버 권위 데이터로 통합(기기간 동기화).
10. **검증에이전트→자동교정 루프** — verifier_service의 fail/warn 판정을 인터프리터 재생성 피드백으로 연결(현재는 배지 표시 종착).

---

## References
- `apps/api/main.py:327-475` — 라우터 통합 마운트, esg 이중·격리 try-import
- `apps/api/app/services/ledger/analysis_ledger_service.py:23-90,188-342` — 해시체인 원장·런타임 DDL
- `apps/api/app/services/ai/base_interpreter.py:44-50,132-154,256-300,354-388` — 공통 LLM 기반·그라운딩·캐시·과금
- `apps/api/app/services/data_validation/validator.py:14-171` — Pydantic 검증·IQR·신선도
- `apps/api/app/services/data_validation/public_data_registry.py:1-40` — 메모리 상태(휘발성)
- `apps/api/app/services/verification/verifier_service.py:1-60` — 규칙+LLM 검증
- `apps/api/app/services/ai_services/bid_analyzer.py:146-160` — G2B 규칙+LLM옵션
- `apps/api/services/safety_service.py:41-170` — YOLOv8 실연동+폴백
- `apps/api/services/parking_service.py:37-71` — cv2+easyocr+Mock폴백
- `apps/api/services/digital_twin_service.py:194-208` — 단순 선형회귀(약점)
- `apps/api/app/services/pipeline/project_pipeline.py:201-242,757-788` — 단계별 interpreter 부착
