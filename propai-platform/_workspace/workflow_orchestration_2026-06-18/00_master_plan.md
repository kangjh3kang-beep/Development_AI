# 마스터 플랜 — 디벨로퍼 워크플로우 정밀배선 + 유연조합 고도화

작성: 2026-06-18 / 오케스트레이터-기획자 / 근거: 4개 도메인 병렬 코드 감사(추측 없음, 파일경로 근거)

---

## 0. 한 줄 진단

> **분석 엔진(빌딩블록)은 이미 ~90% 구축돼 있다. 진짜 과제는 무에서 짓는 게 아니라 — (1) 끊긴 배선을 잇고(단선 해소), (2) 이들을 "분석 DAG"로 오케스트레이션하고, (3) 사용자가 순서·범위를 자유 조합하게 하는 것이다.**

> 사용자 요청(별도분석/선택분석/순서 자유/성향별 확장)은 신규 발명이 아니라, 이미 만들어둔 `AnalysisModuleSelector`(선택형 분석 공용 컴포넌트)와 `useProjectContextStore.MODULE_UPSTREAM`(모듈 의존성 맵)을 **분석 DAG + 4실행모드**로 승격하면 그대로 실현된다.

---

## 1. 디벨로퍼 실무 스토리라인 ↔ 현재 자산 매핑

사용자 스토리라인: **① 토지분석 → ② 법률분석 → ③ 건축개요/설계 → ④ 분양성·예상분양가 → ④' 수지분석 → ⑤ 금융설계** + 핵심1(AI 심의 멀티모달)·핵심2(BIM 적산).

| 단계 | 엔진(구현됨) | 배선 상태 | 단선/갭 |
|------|------------|----------|---------|
| ① 토지분석 | `far_tier_service`(실효용적률 SSOT)·`auto_zoning_service`·`special_parcel`(특이부지 게이트)·`scenario_simulator`(20정책)·`permit_validator`(허용유형) | `/zoning/analyze` 단일호출로 집약, 프론트 tiles 표시 | **store에 effectiveFar/upzoning/specialParcel/다필지집계 미보존** → 하류가 재호출. 종상향·특이부지 전용 카드 없음 |
| ② 법률/인허가 | `permit_analysis_service`(7방식 AI)·`regulation_analysis_service`(4계층)·`check_permit_feasibility` | permit/regulation 페이지 배선됨 | special_parcel·upzoning 컨텍스트 미주입. M코드↔scheme명 체계 이원화. **심의엔진 미연결** |
| (②.5) 개발방식 추천 | `integrated_recommender`(현행/종상향 2계층 순위, **방금 배포**)·`/development-methods/evaluate`(AHP) | `POST /optimal-recommend` 라이브 | **프론트 미연동** |
| ③ 건축개요/설계 | `AutoDesignEngine`(매스·대안ABC)·`unit_mix`·`IfcGenerator`→`IfcToGltf`(IFC4→glb)·`DesignInterpreter`·CAD에디터·design_versions | `/bim/generate`→프론트 GLTFLoader 폐루프 | 조례한도 미주입. zone_code(2R)↔zone_type(풀네임) 어댑터 없음 |
| ④ 분양성·분양가 | `pricing_band_service`(거래사례비교+PIR/DSR/LTV)·`molit_service`·`nearby_map`·`site_score`(POI)·`trust.cross_validate` | 시장보고서→PricingBandPanel | **fair_price→수지 자동주입 없음**(수동 입력) |
| ④' 수지 | `feasibility_service_v2`(M01~M15, calculate_multi/compare)·`finance_cost_engine`(브릿지/PF/중도금)·`integrated_tax_engine`(38종) | `/api/v2/feasibility/*` 정상 | **모세혈관 autoRecalc 미연결**(공사비 변경→수지 자동갱신 안 됨) |
| ⑤ 금융설계 | `/development-finance`·`/cashflow`(월별DCF·IRR)·`bank_ready_report`(10섹션) | 프론트 패널 배선, store 시드 | 독립모듈 정상. 통합 진입동선 부재 |
| 핵심1 AI심의 | `DesignAuditOrchestrator`(8엔진)·`brief_extractor`(PDF텍스트)·`geometry_adapter`(IFC/DXF) | `/design-audit/run`·`/run-upload` 배선 | **LLM 비전 미구현**(도면 이미지/스캔PDF 직접분석 불가). 설계→심의 자동 핸드오프 없음 |
| 핵심2 BIM적산 | `boq_parametric`(5공종)·`boq_bim_merge`·`geometry_qto`·`QtoBreakdown`·`estimate-overview` | bim-studio 배선 | **IFC 바이너리 업로드→파싱→적산 미완. 시공 4D 시뮬·설계개선 제안 AI 미구현**. QTO결과→costData 저장 배선 없음 |

> ※ 감사 에이전트가 `integrated_recommender/orchestrator.py`를 "미존재"로 보고한 것은 **메인 체크아웃이 origin/main보다 뒤처져 있어서**다. 이 엔진은 feat-tmp에서 구현·푸시(HEAD 8ec0a35a)·백엔드 배포·라이브검증 완료된 실재 코드다.

---

## 2. 설계 철학 — "가이드 기본 + 자유 조합" (분석 DAG 모델)

사용자 통찰("사용자 성향·업무스타일에 따라 워크플로우가 달라진다")을 정면으로 수용한다. 선형 파이프라인을 강요하지 않고, **방향성 비순환 그래프(DAG)** 로 모델링한다.

### 2-1. 노드(분석 단위) 정의

각 분석은 **입력(업스트림 의존)** 과 **출력(SSOT 기여)** 을 선언하는 노드다. `MODULE_UPSTREAM`이 곧 DAG의 엣지다 — 확장해서 정식 레지스트리화한다.

```
land ──┬─→ legal ──┬─→ recommend ──→ design ──→ audit(핵심1)
       │           │                   │
       └─→ sales ──┘                   └─→ qto(핵심2) ──┐
                                                          ├─→ feasibility ──→ finance
                                       sales ─────────────┘
```

| 노드 | 스토리라인 | 입력 | 출력(SSOT) |
|------|-----------|------|-----------|
| `land` | ① | 주소(들) | siteAnalysis{면적·용도·effectiveFar·bcr·upzoning·specialParcel·**areaTotal·parcelCount·zoneMixed**} |
| `legal` | ② | siteAnalysis | complianceData{허용유형·인허가가능성·규제계층·개발방향} |
| `recommend` | ②.5 | siteAnalysis+compliance | recommendData{현행/종상향 순위 Top-N} |
| `design` | ③ | siteAnalysis+선택방식 | designData{매스·GFA·층수·세대·bim·도면} |
| `audit` | 핵심1 | designData 또는 업로드도서 | auditData{심의findings·verdict·사각지대} |
| `sales` | ④ | siteAnalysis | salesData{적정분양가·비교사례·POI점수} |
| `qto` | 핵심2 | designData | costData{공사비·부위별물량} |
| `feasibility` | ④' | site+design+sales+qto | feasibilityData{순이익·수익률·NPV·ROI / 개발방식별} |
| `finance` | ⑤ | feasibilityData | financeData{PF·현금흐름·IRR·은행보고서} |

### 2-2. 4가지 실행 모드 (= 유연성의 본체)

1. **가이드 모드(기본)** — DAG를 위상정렬 순서로 안내. 각 단계 보고서 + "다음 단계" CTA. 현재 `LifecycleStageViews`가 씨앗.
2. **별도 모드(standalone)** — 임의 단일 노드 실행. 입력을 SSOT에서 자동 해소, 없으면 (a) 최소 업스트림 자동 실행 제안 또는 (b) 수동 입력(`manualFields` provenance가 이미 지원).
3. **선택 모드(selective)** — `AnalysisModuleSelector`로 부분집합 선택 → **의존성 폐포(closure) 자동 계산** → 의존순서 실행, `isStale` 신선분은 스킵. **선택분만 과금**(과금 원칙 준수).
4. **프로필 모드(성향별)** — 프리셋 워크플로우(노드 부분집합+순서) + **사용자 커스텀 저장**(확장성). 예: 「지주 빠른검토」(land+legal+약식수지), 「디벨로퍼 풀패키지」(전체), 「PF·금융 중심」(수지+금융+은행보고서), 「설계사」(건축개요+심의+적산).

### 2-3. 단계별 보고서 계약(표준 산출물)

모든 노드는 표준 `StageReport{summary, keyMetrics[], evidence[], honestDisclosure, verification, downstreamImpact}`를 반환. 누적 → **통합 사업검토서(PDF)**. 보고서 인프라는 이미 존재(`pipeline_report_pdf`·`design_audit_pdf`·`market_report`) — 계약만 표준화.

### 2-4. ★모든 노드의 불변 계약 — "사실기반 + 전문가 LLM 협업" (cross-cutting)

DAG의 모든 노드는 아래 4단을 **반드시** 거친다(노드 표준 계약). 이것이 "단계별 사실기반 분석 + 전문가 LLM 배치·협업"의 체계화다.

1. **사실기반 입력(grounding)** — 공공데이터/실거래 실값을 출처와 함께 입력. 미확보 시 0 강제 금지·`unavailable` 정직 표기. (기존: VWorld/NED/MOLIT/KOSIS/SGIS, `special_parcel` 할루시네이션 게이트, `far_tier` 법정→조례→계획상한 SSOT, `validator`/`public_data_registry`/`calculation_metadata`)
2. **전문가 LLM 해석(node별 전담 에이전트)** — 노드마다 전담 interpreter가 사실기반 입력을 그라운딩 컨텍스트로 해석. (기존 10 interpreter: `SiteAnalysisInterpreter`·`DesignInterpreter`·`CostInterpreter`·`PermitAnalysis(LLM)`·`Regulation(LLM)`·`DesignBrief`·`blindspot` 등, `BaseInterpreter` 단일계측·LangSmith 추적)
3. **다관점 협업(필요 노드)** — 판단 분기가 큰 노드(인허가·규제·시장·부지·사업성)는 `/expert-panel/analyze`(다관점 토론·통합) 부착.
4. **교차검증 + 할루시네이션 가드** — `trust.cross_validate`(이상치배제·신뢰도) + `/verify/analysis`(pass/warn/fail, VerificationBadge) → 정직 고지로 표면화.

**노드 간 협업(=모세혈관)**: 상류 노드의 사실기반 산출(SSOT)이 하류 전문가 LLM의 그라운딩 컨텍스트가 된다(토지 `effectiveFar`→설계 LLM→수지 LLM). 즉 SSOT rich 필드(Phase A)는 단순 캐시가 아니라 **하류 전문가 LLM의 사실근거 공급선**이다.

**현재 갭(정직)**: 인프라는 강하나 *균일하지 않다* — `trust.cross_validate`는 3곳만, interpreter는 feature별 부착(단계 표준 계약 아님), expert-panel은 일부만. **Phase B에서 이 4단을 노드 표준 계약으로 강제**해 전 단계 균일 적용한다(신규 발명이 아니라 기존 자산의 표준화·확산).

---

## 3. 성장루프 기반 단계별 구현 로드맵

각 Phase = (구현 → fresh code-reviewer ≥4.5 → 반영 → 커밋 → 푸시 HEAD:main → 배포 → 라이브검증). 의존성·리스크 순.

### Phase A — 데이터 정합 기반 (P0, 최우선)
- SSOT 확장: `SiteAnalysisData`에 effectiveFar/nationalFar/upzoning/specialParcel + **다필지 집계 landAreaSqmTotal·parcelCount·zoneMixed** 보존. `AutoZoningBadge`가 풍부한 `/zoning/analyze` 결과 전량 기록.
- 모세혈관 실연결: `feasibility`·`finance`·`compliance`에 `useStageAutoRecalc` 훅 연결(인프라 완비, 훅 연결만).
- **효과**: 다필지 과소산출 위험 즉시 해소, "공사비 변경→수지 자동 갱신" 실제 작동. 모든 하류가 이 위에서 돈다.

### Phase B — 분석 오케스트레이션 코어 (유연성의 심장)
- 분석 DAG 레지스트리(노드 입출력·의존성 단일 정의) + 4실행모드 엔진(의존성 폐포·신선분 스킵·선택 과금).
- `AnalysisModuleSelector` 전 분석 모듈 확산(현재 2개 파일 → 부지/수지/인허가/규제/설계/적산 전체).
- **효과**: 사용자가 방금 요청한 별도/선택/순서자유가 실제로 동작.

### Phase C — 폐루프 배선
- 추천(`integrated_recommender`)→설계(`AutoDesignEngine`) handoff 어댑터 + **zone_code↔zone_type 정규화**. (★설계→심의 구간은 Phase E로 위임 — 아래 참조)
- `fair_price`→수지 `avg_sale_price_per_pyeong` 자동주입.
- 목업 3탭(legal/permit/operations) 실데이터 배선(백엔드 엔드포인트는 이미 존재).
- `/development-methods/evaluate`·`/optimal-recommend` 프론트 연동.

### Phase D — 단계별 보고서 표준화 + 통합 사업검토서
- `StageReport` 계약 표준화, 노드별 보고서 자동 산출, 누적 통합 PDF.

### Phase E — 핵심1: AI 심의 멀티모달 ★다른 세션 산출물 연동(직접구현 아님)
- **결정(2026-06-18, 사용자 지시):** AI 심의·설계도서 자동분석(LLM 비전 포함)은 **별도 세션이 `feature/deliberation-review`(엔진)·`feature/deliberation-integration`(연동)에서 구현 중.** 내가 만들지 않는다.
- 그 세션이 이미 구축한 연동 계약: `app/services/deliberation/_engine_contract.py`·`binding_service.py`(engine_run_binding)·`POST /deliberation/analyze`(BFF)·`GET /deliberation/analyze/{run_id}`·`MirrorAnalysisInput`(분석 미러 입력)·프론트 `DeliberationConsole`/`EngineHealthCard`.
- **내 역할(엔진 main 머지 후):** 워크플로우 산출(설계·추천 결과)을 `MirrorAnalysisInput` 형태로 `POST /deliberation/analyze`에 공급하는 **얇은 어댑터 1개**만 추가(plug-in). 그 전까지 설계 노드는 "심의 보내기" CTA를 비활성/대기 표기.
- **충돌 방지:** `services/deliberation/**`·`routers/deliberation.py`·`apps/web/components/deliberation/**`는 **건드리지 않는다**(그 세션 소유).

### Phase F — 핵심2: BIM 적산 완성 ★진짜 신규
- IFC 바이너리 업로드→ifcopenshell 파싱→bim_quantities 적재→상세적산 파이프라인 완성.
- 시공 시뮬레이션(4D 공정·자원), 공사비 절감/설계개선·변경 제안 AI(`CostInterpreter` 확장, 목업 제거).

### Phase G — 워크플로우 프로필 & 관리자 템플릿
- 성향별 프리셋 + 사용자 커스텀 워크플로우 저장(확장성).
- 관리자: 분석모듈 과금 게이트 실배선(`charge_service` 호출), 워크플로우 템플릿 관리.

---

## 4. 권장 시작점
- **Phase A부터** — 데이터 정합(P0)은 B의 전제이자 가장 작고 빠른 고위험 수정. A 완료 후 B(유연조합 본체)로 진입하면 사용자 요청이 즉시 체감된다.
- 각 Phase는 독립 배포 가능(회귀 0 설계). 한 번에 하나씩 완벽 구현(작업 원칙 준수).
