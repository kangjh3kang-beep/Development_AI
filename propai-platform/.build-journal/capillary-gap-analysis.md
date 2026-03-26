# PropAI v30.0 모세혈관 구현계획 vs 실제 구축 — 전수 Gap 분석 보고서

> **작성일**: 2026-03-20
> **기준 문서**: `PropAI_모세혈관구현계획_마스터인덱스.md` (Part 1~4, Phase 00~15)
> **비교 대상**: `propai-platform/` 실제 코드베이스 전수조사
> **품질 게이트**: ruff ✓ | mypy 0 errors (담당 파일) | pytest 131 passed / 18 skipped

---

## I. 전수조사 총괄 요약

| 등급 | 설명 | 파일 수 | 비율 |
|------|------|---------|------|
| **REAL** | 실제 비즈니스 로직 완전 구현 | 45 | 56% |
| **PARTIAL** | 골격은 있으나 핵심 로직 일부 스텁/하드코딩 | 8 | 10% |
| **SHELL** | TODO 주석만 있는 빈 껍데기 | 5 | 6% |
| **MISSING** | 모세혈관 계획에 있으나 파일 자체 미존재 | 22 | 28% |
| **합계** | | **80** | |

---

## II. PHASE별 Gap 상세 비교

### Phase 00: 프로젝트 부트스트랩 — ✅ 완료 (Gemini)

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| Monorepo 구조 | Turborepo + pnpm | ✅ 존재 | — |
| docker-compose.dev.yml | 15개 서비스 | ✅ 존재 | — |
| CI/CD | GitHub Actions | ✅ 3개 워크플로 | — |
| .env.example | 40+ 변수 | ✅ 존재 | — |

---

### Phase 01: 데이터베이스 — 🟡 PARTIAL

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| DB 모델 | 22개 테이블 완전 스키마 | 14개 모델 파일 존재 | ❌ **8개 누락** |
| RLS 정책 | 15개 테이블 | session.py에 `SET LOCAL` 구현 | 🟡 SQL 정책 미적용 |
| Alembic 마이그레이션 | 22개 테이블 CREATE | 001_initial 1개 존재 | 🟡 내용 미확인 |
| Qdrant 초기화 | 컬렉션 자동 생성 | init_qdrant.py 구현 | ✅ |

**누락 DB 모델** (모세혈관 계획 기준):
1. `refresh_tokens` — JWT 리프레시 토큰 관리
2. `jeonse_analyses` — 전세 리스크 분석 결과
3. `auction_listings` — 경매/공매 물건
4. `webhooks` — 웹훅 구독 관리
5. `webhook_deliveries` — 웹훅 발송 이력
6. `api_keys` — API 키 관리 (테넌트별)
7. `esign_requests` — 전자서명 요청
8. `data_lineage` / `ab_test_events` — 데이터 계보/AB테스트

---

### Phase 02: 인증/권한 — ✅ 대부분 완료

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| JWT 발급/검증 | HS256 + refresh | ✅ jwt_handler.py (115줄) | — |
| RBAC (Casbin) | 4역할 × 11리소스 | ✅ rbac.py (148줄) | — |
| 카카오 OAuth | 소셜 로그인 | ❌ 미구현 | **G1** |
| 라우터 (register/login/refresh) | 6개 엔드포인트 | auth.py 존재 | 🟡 확인 필요 |

---

### Phase 03: 외부 API 통합 — 🟡 PARTIAL

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| BaseAPIClient | Circuit Breaker + 캐시 + Slack 알림 | ✅ base_client.py (222줄) | ✅ |
| VWorldClient | 필지/용도지역/지하시설물/주소변환 (4개 메서드) | get_land_info/building_info/geocode (3개) | ❌ **지하시설물/용도지역 누락** |
| MolitClient | 실거래가 6종 + 인허가 + XML 파싱 | get_apartment_trades/rent/land_price (3개) | ❌ **오피스텔/상업/인허가 누락** |
| Slack 장애 알림 | Circuit OPEN → #propai-alerts | base_client에 미구현 | ❌ **G2** |
| DB 폴백 | API 장애 시 DB 조회 | 미구현 | ❌ **G3** |

---

### Phase 04: AVM 시세 엔진 — 🔴 PARTIAL (핵심 로직 부재)

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| 16개 특징 컬럼 | PostGIS 공간 + 실거래 통계 | **4개** (면적/연식/층/비교사례수) | ❌ **12개 누락 (G4-핵심)** |
| PostGIS 공간 특징 | 지하철/학교 거리 SQL | 미구현 | ❌ |
| MLflow 모델 3단계 | Production→Staging→Fallback | Production만 시도, 실패 시 미학습 XGBoost | ❌ **G5** |
| SHAP 특징 중요도 | 동적 계산 | 하드코딩 폴백값 반환 | ❌ |
| 비교 실거래 3건 | DB 조회 | `_fetch_comparables()` → `return []` (스텁) | ❌ **G6** |
| 신뢰구간 ±7% | 분위 회귀 | 미구현 | ❌ |
| CTGAN 합성 데이터 | 콜드스타트 대응 | 미구현 | ❌ |
| MAPE ≤ 5% | CoVe O1 | **달성 불가** (폴백: area × 500만원) | 🔴 |

---

### Phase 05: 법규 AI (RAG) — ✅ 완료

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| RAG 파이프라인 | 임베딩→Qdrant→LLM 분석 | ✅ regulation_service.py (180줄) | — |
| 건축법 컨텍스트 | 건폐율/용적률/높이제한 | 🟡 프롬프트에 내장 | 내장 법령 DB 부족 |
| violations/warnings 반환 | 구조화 JSON | ✅ 구현됨 | — |

---

### Phase 06: 설계 AI (SSE) — ✅ 완료

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| SSE 스트리밍 | StreamingReportEvent | ✅ design_ai_service.py (101줄) | — |
| 동기 호출 | generate_design_sync | ❌ 미구현 | **G7** |
| AI 비용 자동 기록 | ai_usage_log 테이블 | ❌ 미구현 | **G8** |

---

### Phase 07: 금융/세금 AI — 🟡 PARTIAL

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| 세금 계산 | 양도소득세 누진세율 8구간 + 장기보유특별공제 | tax_ai_service.py: 7개 세금 유형 기본 세율 | ❌ **누진세율 8구간 미구현 (G9)** |
| Monte Carlo 절세 | N=1,000 시뮬레이션 | ❌ 미구현 | **G10** |
| 최적 매도 시기 | AI 제안 | ❌ 미구현 | |
| 조합원 분담금 | 비례율법 | ✅ union_management_service.py | — |

---

### Phase 08: 한국특화 AI (전세) — 🟡 PARTIAL

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| 전세 사기 7대 패턴 | 탐지 로직 | 기본 전세가율 계산만 | ❌ **7대 패턴 미구현 (G11)** |
| HUG 보증보험 판단 | 수도권 7억/지방 5억 | ❌ 미구현 | **G12** |
| 리스크 등급 A~F | 세분화 등급 | CRITICAL/HIGH/MEDIUM/LOW/SAFE만 | 🟡 |
| 실거래가 시장 데이터 | 국토부 API | `_fetch_market_data()` → `return {0,0,0}` (스텁) | ❌ **G13** |

---

### Phase 09: 시공/ESG AI — 🔴 MISSING (파일 미존재)

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| ConstructionAIService | 전체 파일 | ❌ **파일 미존재** | **G14-핵심** |
| BIM4D 시공 일정 | 국토부 표준품셈 기반 | ❌ | |
| 탄소 배출 계산 (상세) | 자재+장비+전력 3분류 | carbon_calculation_service.py에 기본만 | 🟡 |
| ZEB 에너지 시뮬레이션 | EnergyPlus 수학 모델 | ❌ | **G15** |
| 기후 리스크 정량화 | KMA RCP 8.5 | ❌ | **G16** |
| 하자 사진 AI 분류 | Claude Vision | ❌ | **G17** |

---

### Phase 10: MLOps — 🔴 SHELL (5개 워커 전부 빈 껍데기)

| 파일 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| embed_regulations.py | Qdrant 벡터 적재 | **TODO 주석 4개, return {"processed": 0}** | 🔴 **SHELL** |
| mlops.py | AVM 재학습 파이프라인 | **TODO 주석 6개, return {"mape": 0.0}** | 🔴 **SHELL** |
| parse_large_ifc.py | 100MB+ IFC 파싱 | **TODO 주석 5개, return {"element_count": 0}** | 🔴 **SHELL** |
| generate_floor_plan.py | SDXL 비동기 생성 | **TODO 주석 4개, return {"image_url": ""}** | 🔴 **SHELL** |
| generate_report_pdf.py | ReportLab PDF 생성 | **TODO 주석 5개, return {"pdf_url": ""}** | 🔴 **SHELL** |

---

### Phase 11: 프론트엔드 — (Codex 담당, 참고용)

| 항목 | 현재 상태 |
|------|----------|
| Zustand store | ✅ 구현 (Codex) |
| CadastralMap (지적도) | ✅ 구현 (Codex) |
| DesignAIPanel (SSE) | 🟡 하드코딩 Mock 데이터 잔존 |
| AgentTimeline (WS) | 🟡 하드코딩 Mock 데이터 잔존 |

---

### Phase 13: AI 고도화 — 🔴 PARTIAL (오케스트레이터 6/7 스텁)

| 항목 | 모세혈관 계획 | 현재 상태 | Gap |
|------|-------------|----------|-----|
| LangGraph StateGraph | 9단계 전주기 상태 머신 | 7단계, **6/7 스텁** | ❌ **G18-핵심** |
| Step 1: 필지분석 | VWorldClient 호출 | 하드코딩 `{"status": "analyzed"}` | ❌ |
| Step 2: 법규검토 | RegulationService 호출 | ✅ 유일한 실제 호출 | — |
| Step 3: 설계생성 | DesignAIService 호출 | 하드코딩 `{"status": "design_generated"}` | ❌ |
| Step 4: AVM 시세 | AVMService 호출 | 하드코딩 `{"estimated_price": 0}` | ❌ |
| Step 5: 사업성분석 | 재무 분석 로직 | 하드코딩 `{"npv": 0, "irr": 0}` | ❌ |
| Step 6: 인허가검토 | 법규 준거 체크 | 하드코딩 `{"permit_ready": True}` | ❌ |
| Step 7: 종합보고서 | Claude LLM 생성 | 하드코딩 `{"status": "generated"}` | ❌ |
| WebSocket 진행률 | 실시간 전송 | SSE만 구현 (WS 미구현) | ❌ **G19** |
| ReportLab PDF | 나눔고딕 한글 PDF | ❌ 미구현 | **G20** |

---

## III. 전수조사 결과: 껍데기(SHELL) 목록

아래 파일은 **함수 시그니처만 존재하고 내부 로직이 TODO 주석 또는 하드코딩 반환**입니다.

| # | 파일 | 핵심 문제 | 심각도 |
|---|------|----------|--------|
| S1 | `worker/tasks/embed_regulations.py` | TODO 4개, `return {"processed": 0}` | 🔴 |
| S2 | `worker/tasks/mlops.py` | TODO 6개, `return {"mape": 0.0}` | 🔴 |
| S3 | `worker/tasks/parse_large_ifc.py` | TODO 5개, `return {"element_count": 0}` | 🔴 |
| S4 | `worker/tasks/generate_floor_plan.py` | TODO 4개, `return {"image_url": ""}` | 🔴 |
| S5 | `worker/tasks/generate_report_pdf.py` | TODO 5개, `return {"pdf_url": ""}` | 🔴 |
| S6 | `agents/propai_orchestrator.py` | 6/7 스텝 하드코딩 반환 | 🔴 |
| S7 | `services/avm_service.py:_fetch_comparables()` | `return []` (스텁) | 🔴 |
| S8 | `services/avm_service.py:_build_features()` | 4개 특징만, TODO 12개 | 🟡 |
| S9 | `services/jeonse_risk_service.py:_fetch_market_data()` | `return {0,0,0}` (스텁) | 🔴 |
| S10 | `services/avm_service.py:_create_fallback_model()` | 미학습 XGBoost | 🟡 |

---

## IV. 상세 구현/구축안 — 우선순위별

### 🔴 Priority 1 (크리티컬 — 핵심 비즈니스 로직 부재)

#### P1-1: 오케스트레이터 실제 서비스 연결 (G18)
**파일**: `apps/api/agents/propai_orchestrator.py`
**작업 범위**: `_execute_step()` 메서드를 각 서비스에 실제 연결

```
Step 0 (parcel_analysis):
  - VWorldClient.get_parcel_info(pnu) 호출
  - VWorldClient.get_land_use_zone(pnu) 호출
  - 결과: {parcel_info, land_use_zone, centroid_lat, centroid_lon}

Step 2 (design):
  - DesignAIService(db).stream_design_report() 동기 래퍼 호출
  - FloorPlanImageService(db).generate() 호출 (이미지 생성)
  - 결과: {design_id, design_text, image_url}

Step 3 (avm):
  - AVMService(db).estimate(request, tenant_id) 호출
  - 결과: {estimated_price, confidence_score, comparables}

Step 4 (feasibility):
  - TaxAIService(db).calculate() 호출 (세금 산출)
  - NPV/IRR 계산 로직 구현 (할인율 5%, 투자기간 10년)
  - JeonseRiskService(db).analyze() 호출
  - 결과: {npv, irr, tax_amount, jeonse_risk}

Step 5 (permit):
  - RegulationService 결과 기반 인허가 준비도 판단
  - 위반 0건 → permit_ready=True
  - 결과: {permit_ready, violation_count, warnings}

Step 6 (report):
  - Claude LLM으로 전체 결과 종합 보고서 생성
  - 투자매력도 A~F 등급 산출
  - 결과: {final_report_text, investment_grade}
```

**예상 작업량**: ~200줄 추가/수정
**의존성**: AVM/Tax/Jeonse 서비스가 먼저 개선되어야 완전 동작

---

#### P1-2: AVM 특징 엔지니어링 확장 (G4, G5, G6)
**파일**: `apps/api/services/avm_service.py`
**작업 범위**:

```
1. _build_features() 확장 — 16개 특징 컬럼:
   기존 4개: area_sqm, building_age_years, floor, comparable_count
   추가 12개:
   - total_floors: int (프로젝트 정보에서)
   - distance_to_subway_m: float (PostGIS ST_Distance)
   - distance_to_school_m: float (PostGIS ST_Distance)
   - land_official_price: int (VWorldClient 공시지가)
   - recent_trans_avg_10k: float (MolitClient 최근 3개월 평균)
   - floor_area_ratio: float (VWorldClient 용적률)
   - building_coverage_ratio: float (VWorldClient 건폐율)
   - school_score: float (학업성취도 데이터 — 초기 75.0 기본값)
   - noise_db: float (소음 — 초기 55.0 기본값)
   - view_score: float (조망 — 초기 60.0 기본값)
   - month_sin: float = sin(2π × month / 12)
   - month_cos: float = cos(2π × month / 12)

2. _fetch_comparables() 실제 구현:
   - MolitClient.get_apartment_trades(sigungu_cd, deal_ymd) 호출
   - 유사 면적 ±15㎡ 필터링
   - 최근 3건 반환

3. MLflow 3단계 폴백:
   models:/PropAI-AVM/Production → /Staging → SimplePriceModel

4. 신뢰도 계산 개선:
   base_confidence = {"xgboost": 0.87, "staging": 0.70, "fallback": 0.40}
   + 실거래 데이터 보정 (50건↑ +0.05, 10건↓ -0.10)
```

**예상 작업량**: ~150줄 수정

---

#### P1-3: 워커 태스크 실제 구현 (S1~S5)
**파일**: `apps/worker/tasks/*.py`

```
embed_regulations.py (법령 임베딩):
  1. DB에서 regulations 테이블의 embedded=False 레코드 배치 조회
  2. OpenAI text-embedding-3-small로 벡터 생성
  3. Qdrant "regulations" 컬렉션에 upsert
  4. DB에 embedded=True 업데이트

mlops.py (AVM 재학습):
  1. MolitClient로 최근 30일 실거래 데이터 수집
  2. pandas DataFrame 특징 엔지니어링
  3. train_test_split(0.8) → XGBoost 학습
  4. MAPE 계산 → 챔피언 비교 → MLflow 등록
  5. Evidently 데이터 드리프트 리포트 생성

parse_large_ifc.py (대용량 IFC):
  - BIMIFCService._download_ifc() + _parse_ifc() 재사용
  - 결과 DB 저장

generate_floor_plan.py (SDXL 비동기):
  - FloorPlanImageService.generate() 재사용
  - 비동기 큐에서 실행

generate_report_pdf.py (PDF 보고서):
  1. 프로젝트 관련 전체 데이터 DB 조회
  2. ReportLab Canvas로 커버페이지/목차/본문 렌더링
  3. 나눔고딕 한글 폰트 등록
  4. matplotlib 차트 삽입
  5. MinIO 업로드
```

**예상 작업량**: 각 50~100줄, 총 ~400줄

---

### 🟡 Priority 2 (중요 — 기능 확장)

#### P2-1: ConstructionAIService 신규 생성 (G14~G17)
**파일**: `apps/api/services/construction_ai_service.py` (신규)
**모세혈관 계획 Phase 09 전체 이식**

```
기능:
1. generate_construction_schedule() — BIM4D 시공 일정 (표준품셈 13공정)
2. calculate_carbon_emission() — 자재/장비/전력 3분류 탄소 계산
3. estimate_zeb_energy() — ZEB 에너지 시뮬레이션
4. analyze_climate_risk() — 기후 리스크 (홍수/폭염 확률)
5. classify_defect_image() — 하자 사진 AI 분류 (Claude Vision)

라우터: /api/v1/construction (신규)
DB 모델: construction_logs (기존 활용)
```

**예상 작업량**: ~350줄 (서비스) + ~80줄 (라우터)

---

#### P2-2: 전세 서비스 시장 데이터 연동 (G11~G13)
**파일**: `apps/api/services/jeonse_risk_service.py`

```
1. _fetch_market_data() 실제 구현:
   - MolitClient.get_apartment_rent(sigungu_cd, deal_ymd) 호출
   - MolitClient.get_apartment_trades(sigungu_cd, deal_ymd) 호출
   - 평균 전세가/매매가/거래건수 계산

2. HUG 보증보험 판단 추가:
   - 수도권: 전세가 ≤ 7억 → 가입 가능
   - 지방: 전세가 ≤ 5억 → 가입 가능
   - HugClient.check_guarantee_eligibility() 연동

3. 7대 사기 패턴 탐지:
   - 갭투자 (전세가율 80%↑)
   - 다주택 임대인
   - 근저당 설정 과다
   - 빌라 신축 대출 사기
   - 깡통전세
   - 전세금 반환 보증 미가입
   - 등기부 확인 불일치
```

**예상 작업량**: ~120줄 수정

---

#### P2-3: 세금 계산 고도화 (G9, G10)
**파일**: `apps/api/services/tax_ai_service.py`

```
1. 양도소득세 누진세율 8구간:
   1,400만원↓ 6% → 5,000만원↓ 15% → 8,800만원↓ 24% →
   1.5억↓ 35% → 3억↓ 38% → 5억↓ 40% → 10억↓ 42% → 10억↑ 45%

2. 장기보유특별공제:
   3년↑ 6% ~ 10년 30% (1세대1주택 40%)

3. 중과세:
   2주택 기본세율+20%p, 3주택↑ 기본세율+30%p

4. Monte Carlo 절세 시나리오:
   - N=1,000 시뮬레이션
   - 보유기간/매도시기/증여 등 변수
   - 최적 전략 3개 제안
```

**예상 작업량**: ~200줄 수정

---

#### P2-4: VWorld/MOLIT 클라이언트 확장 (G2, G3)
**파일**: `apps/api/integrations/vworld_client.py`, `molit_client.py`

```
VWorldClient 추가:
- get_land_use_zone(pnu) — 용도지역 조회
- get_underground_facilities(lat, lon) — 지하시설물
- address_to_coordinates(address) — 주소→좌표 변환
- _parse_parcel_response() — VWORLD 응답 파싱
- _parcel_fallback() — DB 폴백

MolitClient 추가:
- ENDPOINTS 딕셔너리 6종 (apt/villa/house/officetel/land/commercial)
- get_building_permit() — 건축 인허가 조회
- _parse_transactions() — XML 파싱 (xmltodict)
- _transaction_fallback() — DB 폴백

BaseAPIClient 추가:
- _alert_ops() — Slack 알림 (#propai-alerts)
```

**예상 작업량**: ~200줄 수정

---

### 🟢 Priority 3 (보강 — 운영 품질)

#### P3-1: 설계 서비스 동기 호출 + AI 비용 기록 (G7, G8)
```
- DesignAIService.generate_design_sync() 추가
- ai_usage_log 테이블에 모든 LLM 호출 기록
  (모델명, 입력토큰, 출력토큰, 비용, 응답시간)
```

#### P3-2: 누락 DB 모델 생성
```
- refresh_tokens, jeonse_analyses, webhooks,
  webhook_deliveries, api_keys 모델 추가
- Alembic 마이그레이션 생성
```

#### P3-3: 카카오 OAuth 로그인 (G1)
```
- auth/kakao_handler.py 신규
- 카카오 REST API 연동 (인가코드 → 토큰 → 사용자정보)
- auth 라우터에 /kakao/callback 추가
```

#### P3-4: WebSocket 에이전트 진행률 (G19)
```
- agents 라우터에 WebSocket 엔드포인트 추가
- /api/v1/agents/analyze/ws/{project_id}
- 기존 SSE 오케스트레이터를 WS로 브릿지
```

#### P3-5: PDF 보고서 생성 서비스 (G20)
```
- DocumentService 신규
- ReportLab + 나눔고딕 한글 폰트
- 커버페이지/목차/본문/차트 자동 생성
```

---

## V. 실행 순서 (의존성 기반)

```
Phase 1 (즉시 착수 가능):
  ├── P2-4: VWorld/MOLIT 클라이언트 확장
  ├── P2-2: 전세 시장 데이터 연동
  └── P2-3: 세금 계산 고도화

Phase 2 (Phase 1 완료 후):
  ├── P1-2: AVM 특징 엔지니어링 확장 (MOLIT 의존)
  └── P2-1: ConstructionAIService 신규 생성

Phase 3 (Phase 2 완료 후):
  ├── P1-1: 오케스트레이터 실제 서비스 연결 (모든 서비스 의존)
  └── P1-3: 워커 태스크 실제 구현

Phase 4 (최종 보강):
  ├── P3-1~P3-5: 운영 품질 보강
  └── 전체 품질 게이트 재검증
```

---

## VI. Gap 총 개수 요약

| 카테고리 | Gap 수 | 비고 |
|---------|--------|------|
| **SHELL (빈 껍데기)** | 10건 | S1~S10 |
| **MISSING (파일 미존재)** | 1건 | ConstructionAIService |
| **기능 부재** | 20건 | G1~G20 |
| **합계** | **31건** | |

**현재 실질 구현률**: 약 **62%** (모세혈관 계획 대비)
**껍데기 제거 후 예상 구현률**: 약 **90%** (P1+P2 완료 기준)
