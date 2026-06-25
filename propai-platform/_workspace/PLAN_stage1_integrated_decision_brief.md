# 기획·구현·배선 계획 — Stage 1 「통합 사업성 판단(Decision Brief)」

> 작성 2026-06-25. 목적: 과세분화된 라이프사이클을 압축하고, **첫 단계에서 부지·시장·법규·인허가·설계개요(추천순위)를 통합분석→각 파트 요약→사업 추진여부(Go/NoGo)를 전문가·일반인 모두 결정**할 수 있는 단일 페이지를 신설. 기존 자산 최대 재사용(additive·무회귀).
> 작업은 origin/main 기준 전용 워크트리에서. 머지/배포는 통합자.

---

## 1. 진단 (왜 비효율적인가)
- **현재 = 8단계 평면 나열**: 입지분석 → 법규검토 → AI설계 → 사업성 → ESG → 인허가 → 시공 → 운영 (`LifecycleStageViews.tsx`). 단계마다 별도 페이지·별도 분석 실행.
- **추진여부 판단 정보가 8곳에 분산** → 사용자가 부지를 받고 "이 사업 할까?"를 결정하려면 4~5개 단계를 각각 돌려 머릿속에서 합성해야 함. 일반인은 불가능, 전문가도 비효율.
- 기존 `comprehensive_analysis`는 site+market+입지+주변규제만 집계(7섹션). **법규 심화·인허가 가능성·설계개요 추천(Top3)·종합 Go/NoGo가 빠짐** → "기본 정보로 추진결정"이 안 됨.
- 기본원칙(메모리)과의 정렬: 인간개입 최소화·전문가효율·비전문가대행 + 누락없는 통합수집→사이트부합 취합→파트별 요약 = 정확히 이 페이지가 구현해야 할 것.

---

## 2. 기획 (재구성안)

### 2-1. 라이프사이클 3-tier 압축 (8 → 3 계층)
- **Tier 1 「통합 사업성 판단」(신설·기본 진입점)** = Decision Brief. 부지/입지 + 시장 + 법규 + 인허가 + 설계개요(추천Top3)를 **한 번에 통합분석**하고 파트별 요약 + 종합 판정.
- **Tier 2 「상세 실행분석」** = 기존 단계를 드릴다운으로 흡수: 설계 스튜디오 · 사업성 정밀(수지/ROI) · 인허가 진행 · ESG. (Tier1 통과 후 깊게.)
- **Tier 3 「실행/운영」** = 시공 · 자산관리.
- ★기존 8단계는 **삭제 아님** — Tier2/3 상세 페이지로 유지(무회귀). Tier1이 새 진입점·요약 허브가 되고 각 카드의 "상세보기"가 기존 단계로 연결.

### 2-2. Stage 1 페이지 구성 (전문가 + 일반인 동시 대응)
```
┌─ [종합 판정 카드]  GO / 조건부 / 보류   신뢰도 ●●●○   ──────────┐
│  핵심 KPI: 통합면적 · 실효용적률 · 예상 GFA · 예상 분양가 · 개략 사업성(ROI)  │
│  한 줄 결론(일반인) + 핵심 근거 3개 + [전문가/일반인 모드 토글]              │
└──────────────────────────────────────────────────────────────┘
┌ 1.부지/입지 ┐┌ 2.시장 ┐┌ 3.법규 ┐┌ 4.인허가 ┐┌ 5.설계개요 추천 Top3 ┐
│ 용도지역·면적 ││ 실거래·시세 ││ 상위법령→ ││ 개발방식별 ││ ① 추천모델/규모/배치   │
│ 실효용적률   ││ 예상분양가  ││ 조례 한도  ││ 가능성·리스크││ ② …  ③ …            │
│ 특이부지·POI ││ 수요·경쟁  ││ 핵심제약   ││ 해결방안   ││ (인허가검증 통과순)   │
│ [근거][상세→]││[근거][상세]││[근거][상세]││[근거][상세]││ [근거][설계스튜디오→] │
└────────────┘└────────┘└────────┘└─────────┘└──────────────────────┘
[다음 단계: 상세 사업성 정밀분석 →]
```
- **모드 토글**: 일반인(쉬운설명·결론 중심) ↔ 전문가(수치·산식·법령조문). 기본=일반인 결론 + 펼치면 전문가 디테일.
- **근거·신뢰도 기본 표기**(전역 원칙): 각 카드에 evidence/법령링크/신뢰도. 미확보는 정직 "데이터없음"(가짜 금지).
- **선택형 분석**(전역 원칙): 기본 5파트 자동 통합실행, 옵션으로 특정 파트만 재실행. 과금=관리자설정·미설정 무료.
- 다필지: 통합면적(effectiveLandAreaSqm)·면적가중 통합값 사용(메모리 규칙).

---

## 3. 구현계획

### 3-1. 백엔드 — Stage1 통합 오케스트레이터
- 신규 `decision_brief_service`(또는 `comprehensive_analysis_service` 확장): 입력 SSOT(projectId·address·parcels) 1회 수집 → **5개 도메인을 `asyncio.gather` 병렬 집계**.
- 도메인별 **재사용 + 표준 요약 계약**으로 어댑팅(신규 분석엔진 만들지 않음):
  | 파트 | 재사용 소스 |
  |---|---|
  | 부지/입지 | `zoning/analyze`·`/site-score/poi-infra`·`/zoning/integrated-analysis`·`detect_special_parcel`·`comprehensive_analysis_service`(실효용적률·공급면적) |
  | 시장 | `market_report_service`·`/zoning/nearby-map`(실거래)·적정분양가(거래사례비교) |
  | 법규 | `/regulation/analyze`(계층 한도)·`legal_reference_registry`(법령조문·verified URL)·`/permits/guide` |
  | 인허가 | `/permits/ai-analysis`·`permit_validator.auto_recommend_top3` |
  | 설계개요 Top3 | `auto_recommend_top3`(주소→15모델→인허가검증→Top3)·`design_ingest/orchestrator`(개략 배치/규모) |
- **표준 요약 계약**(각 도메인 반환): `{ summary_oneliner, key_metrics[], evidence[], legal_links[], confidence, detail_route, status:"ok|partial|unavailable" }`. → 프론트가 도메인 무관하게 동일 렌더.
- **종합 판정 레이어**: 디벨로퍼 페르소나 Go/NoGo(이미 4-페르소나 종합) 또는 규칙기반 점수화 재사용 → `verdict:{decision:GO|CONDITIONAL|HOLD, confidence, reasons[], blockers[]}`. 특이부지·법규 BLOCKED는 자동 강등.
- **부분실패 graceful**: 한 도메인 실패→해당 카드만 `unavailable` 정직표기, 전체 안 깨짐. SQLSTATE/예외 분류 로깅(silent-fail 금지).
- **성능**: 무거운 5병렬 → 영속 analysis_cache(입력 동일시 재사용·변경시 재분석 제안). LLM 호출 단일경유 계측. 응답 점진 스트리밍(SSE) 또는 파트별 로딩 옵션.
- 엔드포인트(안): `POST /api/v1/projects/{id}/decision-brief` (또는 `/comprehensive` 확장 + `parts=[...]`).

### 3-2. 프론트 — DecisionBriefPage (Tier 1)
- 신규 `DecisionBriefPage`(또는 `LifecycleStageViews` 기본탭 교체): 종합판정 카드 + 5 표준 요약카드(공용 `DomainSummaryCard`) + 모드토글 + 공용 '근거보기' + 드릴다운 CTA(→기존 단계).
- `LifecycleStageViews` 3-tier 재구성: 상단 Tier1(Decision Brief) 강조, Tier2/3는 접근가능하되 "상세" 위치. 기존 stage path 보존(무회귀).
- 다필지·SSOT: `useProjectContextStore`의 통합면적·address·parcels 단일출처 소비(`effectiveLandAreaSqm`).

---

## 4. 배선계획 (data-flow / SSOT / 모세혈관)

### 4-1. 입력 SSOT (수렴)
- projectId·address·parcels·통합면적 = `useProjectContextStore` 단일출처. Stage1 오케스트레이터가 **입력 1회 수집 → 5도메인 fan-out**(각 도메인이 주소를 따로 지오코딩하지 않게 좌표/PNU 공유).

### 4-2. 결과 모세혈관 (발산·재사용)
- Stage1 통합결과 → 컨텍스트 store 적재(`siteAnalysis·market·legal·permit·designTop3·verdict`). **Tier2+ 상세단계가 이 값을 재사용**(중복 재분석 방지). 인터프리터/AI보고서에 통합값 주입.
- **staleness cascade**: 주소/필지/통합면적 변경 → Stage1 + 하류 모듈 자동 stale 표기·재분석 제안(자동 재실행 금지). `MODULE_UPSTREAM`에 decision_brief→[전 모듈] 선언.
- **드릴다운 일관**: 각 요약카드 "상세→"가 기존 단계로 이동 시 동일 분석결과 표시(재계산 X).

### 4-3. 근거·신뢰 모세혈관
- 각 도메인 evidence/legal_refs/trust → 표준 evidence 계약(`{value,basis,source,data_provenance,legal_link,confidence}`) → 프론트 공용 '근거보기' 컴포넌트. verified 법령 URL만(죽은링크 금지).

### 4-4. 엔진 배선 (선택·후속)
- 종합 판정에 도시계획/디벨로퍼 **페르소나** + (배포된) **심의분석엔진** graceful 연결(미배포시 폴백). 설계개요 Top3에 설계자동분석엔진.

---

## 5. 로드맵 (additive·무회귀)
- **P0 백엔드 오케스트레이터**: 5도메인 표준요약 집계(기존 재사용)·부분실패 graceful·종합판정·캐시. 단위테스트(표준계약·부분실패·다필지). 라이브검증.
- **P1 프론트 DecisionBriefPage**: 5요약카드 + 판정카드 + 모드토글 + 근거보기 + 드릴다운. 라이프사이클 3-tier 재구성(기존 path 보존).
- **P2 모세혈관 배선**: 컨텍스트 적재·staleness·드릴다운 SSOT·통합값 인터프리터 주입.
- **P3 고도화**: 페르소나/심의엔진 판정 강화·의사결정 브리프 PDF(은행제출용 재사용)·SSE 스트리밍.

## 6. 리스크 / 함정
- **정보 과부하 역전**: 통합한다고 한 페이지에 다 쏟으면 또 비효율 → 요약(1-2줄)+드릴다운 원칙 엄수, 일반인 모드 기본.
- **5병렬 지연**: 무거운 LLM/외부API → 캐시·파트별 로딩·SSE. 도메인 타임아웃 시 unavailable graceful.
- **무회귀**: 기존 8단계·comprehensive 패널 보존(Stage1은 신규 진입점·additive). LifecycleStageViews 재구성 시 path/탭 무손상.
- **반쪽출하 금지**: 백엔드 표준요약 신설 시 프론트 카드 동시 배선. 종합판정 산출하나 미표시 금지.
- **가짜 Go/NoGo 금지**: 데이터 미확보 도메인은 판정 신뢰도 강등·정직표기(특이부지/법규 BLOCKED는 HOLD 자동).
- **다필지**: 통합면적·면적가중 통합값 사용(대표값 덮어쓰기 버그 주의 — 메모리 규칙).

## 7. 결정 확정 (2026-06-25 사용자 승인)
1. ✅ **라이프사이클 3-tier 압축**(Tier1 통합판단 / Tier2 상세 / Tier3 실행운영, 기존 8단계 무회귀 흡수).
2. ✅ **디벨로퍼 페르소나 Go/NoGo 재사용**(persona_registry의 4-페르소나 종합 판정을 verdict 레이어로 연결, 신규 점수화 미구축).
3. ✅ **자동 전체실행**(주소 입력만으로 5파트 자동 통합분석 = 인간개입 최소화. 무거운 파트는 캐시·파트별 로딩/SSE로 지연 완화).
4. ✅ **SiteCanvas 요약탭에 통합**(별도 페이지 아님) — 아래 8 의존성 참조.

## 8. ★확정에 따른 조정 — SiteCanvas 통합 & 시퀀싱
- **Decision Brief = SiteCanvas(`/projects/[id]/canvas`) 요약탭의 콘텐츠**로 구현(별도 라우트 신설 안 함). 현 요약탭(토지/규제/개발방식/일조/구획도 + ParcelBoundaryMap)을 **종합 판정 카드 + 5 표준 요약카드(부지/시장/법규/인허가/설계Top3) + 모드토글**로 재구성. 지도(좌)+의사결정 브리프(우) 단일창.
- **★선행 의존성**: SiteCanvas는 **PR#8 `feat/analysis-ultrawork` 미머지**(origin/main에 `/canvas` 부재) → Decision Brief UI(P1) 전에 **PR#8을 origin/main에 머지(통합자)**해야 함. 
  - **백엔드 P0(오케스트레이터·표준요약·페르소나 판정)는 canvas와 독립** → PR#8 머지와 병행 착수 가능(프론트 비의존).
  - 시퀀싱: P0 백엔드(독립 착수) ∥ PR#8 머지(통합자) → 둘 다 준비되면 P1(canvas 요약탭에 Decision Brief 배선).
- 페르소나 판정(②)·persona_registry는 백엔드라 canvas 무관 — P0에 포함.

## 9. 다음 액션
- **즉시(P0)**: origin/main 기준 워크트리에서 백엔드 Decision Brief 오케스트레이터 착수 — 5도메인 표준요약 집계(재사용)·디벨로퍼 페르소나 verdict·부분실패 graceful·캐시·`POST /projects/{id}/decision-brief`. 성장루프(9.5 게이트)로 검증.
- **병행(통합자)**: PR#8 SiteCanvas를 origin/main 머지(또는 사용자 승인 시 본 세션이 머지준비).
- **P1**: canvas 요약탭을 Decision Brief로 재구성(종합판정+5카드+근거보기+드릴다운).

---

## 10. 실행 로그 (성장루프·멀티세션 안전)
- 워크트리: `~/My_Projects/Development_AI_decision` 브랜치 `feat/decision-brief`(origin/main 88b7d799 기준). 공유보드 claim 완료(decision-brief 영역). main 직접조작·머지·배포 안 함(통합자).
- 재사용 앵커 확정: `ComprehensiveAnalysisService.analyze(address,*,tenant_id,project_id)`(부지+시장+특이부지+evidence+legal_refs)·`feasibility_service_v2.auto_recommend_top3`(인허가검증+설계Top3)·`persona/{runner,registry,developer_report}`(디벨로퍼 Go/NoGo).
- 성장루프 워크플로우: `decision-brief-growth-loop-wf_a81fd9e4-d63.js`(구현→완결게이트→3관점리뷰→min게이트). 매 phase iter, critical/high0+IMPROVED 커밋, MED/LOW backlog.
- 시퀀스: **P0 백엔드 오케스트레이터(진행중)** → P1 프론트(canvas 요약탭, PR#8 의존) → P2 모세혈관 배선 → 3-tier 재구성 → P3 고도화.
- ★P1 의존: SiteCanvas(PR#8 feat/analysis-ultrawork) origin/main 미머지 → P1 전 머지 필요(통합자/승인). P0 백엔드는 canvas 비의존 선행.
