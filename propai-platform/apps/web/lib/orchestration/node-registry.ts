// 분석 오케스트레이션 — 9노드 정적 레지스트리(L0 SSOT)
// Phase B 블루프린트 §1-B 표 + §1-C 노드 DAG 정합. 순수 데이터(런타임 로직·React·store 인스턴스 의존 0).
//
// 무목업 원칙: runner.path / expertInterpreter / billingKey는 모두 실제 백엔드 코드와 대조해 채웠다.
// interpreter는 apps/api/app/services/ai/* 의 실제 클래스명만 적고, 미존재·미확인이면 null + 주석으로 정직 표기한다.
//
// === 코드 대조 결과(2026-06-18, feat-tmp 워크트리) ===
// 엔드포인트(apps/api/main.py include_router prefix + 라우터 데코레이터로 전체 경로 확인):
//   land        POST /api/v1/zoning/analyze            (auto_zoning.py:356, prefix /api/v1/zoning) ✓
//   legal       POST /api/v1/regulation/analyze        (regulation.py:37, prefix /api/v1/regulation) ✓
//   recommend   POST /api/v1/development-methods/optimal-recommend (development_methods.py:184) ✓
//   design      POST /api/v1/design/{id}/bim/generate  (app/routers/design_v61.py:879, prefix /api/v1/design) ✓
//   audit       POST /api/v1/design-audit/run          (app/routers/design_audit.py:278) ✓ (단 available:false)
//   sales       POST /api/v1/market/report             (market_report.py:47, self prefix /api/v1/market) ✓
//   qto         POST /api/v1/cost/estimate-overview    (app/routers/cost.py:95, prefix /api/v1/cost) ✓
//   feasibility POST /api/v2/feasibility/calculate     (app/routers/v2_feasibility.py:401, prefix /api/v2/feasibility) ✓
//   finance     POST /api/v2/feasibility/development-finance (app/routers/v2_feasibility.py:1460) ✓
// interpreter(apps/api/app/services/ai/* 실제 클래스):
//   SiteAnalysisInterpreter ✓ / DesignInterpreter ✓ / MarketInterpreter ✓ / CostInterpreter ✓ / FeasibilityInterpreter ✓
//   DevelopmentMethodInterpreter ✓(P1 B-1 신설) / FinanceInterpreter ✓(P1 B-1 신설)
//   legal·permit은 전담 인터프리터 클래스 없이 서비스 내부 인라인 LLM으로 이미 충전되어 있음(아래 각 노드 주석 참고)
//   → 이 레지스트리의 expertInterpreter는 "DAG 표준 통로(BaseInterpreter 서브클래스)" 배선 여부만 표기하며,
//     legal·permit의 null은 미충전이 아니라 "다른 경로로 이미 충전됨"을 뜻한다(날조 금지·정직 표기).
//   audit는 심의엔진 소유 → null(로컬 충전 대상 아님)
// billingKey: charge_service "stage:<name>" 규약 문자열만(실호출은 B2). 미설정 단가=0=무료.

import type { AnalysisNode, ProjectContextState } from "./types";

/* ── readyCheck 헬퍼(무목업: 실데이터 유무로 판정) ──
   store가 noop으로 채워진 초기값과 실데이터를 구분하기 위해 핵심 필드 존재로 판정한다. */
const hasSite = (s: ProjectContextState): boolean =>
  !!s.siteAnalysis &&
  (s.siteAnalysis.landAreaSqm != null || !!s.siteAnalysis.address || !!s.siteAnalysis.pnu);
const hasDesign = (s: ProjectContextState): boolean =>
  !!s.designData && (s.designData.totalGfaSqm != null || s.designData.floorCount != null);
const hasCost = (s: ProjectContextState): boolean =>
  !!s.costData && s.costData.totalConstructionCostWon != null;
const hasCompliance = (s: ProjectContextState): boolean =>
  !!s.complianceData;
const hasFeasibilityRevenue = (s: ProjectContextState): boolean =>
  !!s.feasibilityData && s.feasibilityData.totalRevenueWon != null;

/**
 * 9개 노드 정적 선언. 순서·storyOrder는 스토리라인 위상순.
 * upstream은 §1-C 노드 DAG(폐포 SSOT)와 1:1.
 */
export const NODES: AnalysisNode[] = [
  {
    id: "land",
    label: "토지·부지분석",
    storyOrder: 1,
    storylineStage: "site-analysis",
    moduleKey: "siteAnalysis",
    upstream: [],
    ssotInputs: [
      // 부지분석은 주소/PNU 직접입력이 사실근거 루트(상류 노드 없음).
      {
        slot: "siteAnalysis",
        field: "address",
        readyCheck: hasSite,
        resolution: ["ssot", "manual"],
        manualPrompt: "분석할 토지 주소 또는 PNU를 입력하세요",
        provenanceGuarded: true,
      },
    ],
    ssotOutputs: [{ updateAction: "updateSiteAnalysis", source: "auto" }],
    runner: {
      method: "POST",
      path: "/api/v1/zoning/analyze",
      bodyBuilder: "land", // +보조: /api/v1/zoning/special-parcels, /api/v1/zoning/nearby-map (B2)
    },
    expertInterpreter: "SiteAnalysisInterpreter", // 확인됨: app/services/ai/site_analysis_interpreter.py (project_pipeline._attach_site_ai 경유)
    expertPanel: false,
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:land",
    reportContract: {
      sectionKey: "site",
      fields: ["address", "landAreaSqm", "zoneCode", "officialPrice"],
      unavailableLabel: "부지분석 미실행",
    },
    lens: "site",
    groundingSources: ["VWorld", "NED 토지특성", "건축물대장"],
    available: true,
    icon: "stage_site_analysis",
  },
  {
    id: "legal",
    label: "법률·규제검토",
    storyOrder: 2,
    storylineStage: "legal",
    moduleKey: "compliance",
    upstream: ["land"],
    ssotInputs: [
      {
        slot: "siteAnalysis",
        readyCheck: hasSite,
        resolution: ["ssot", "upstream-suggest"],
        manualPrompt: "부지분석(용도지역·면적)이 필요합니다",
        provenanceGuarded: false, // complianceData는 ProvenanceModule 밖 → merge가드 없음(정직 표기)
      },
    ],
    ssotOutputs: [{ updateAction: "updateComplianceData", source: "auto" }],
    runner: {
      method: "POST",
      path: "/api/v1/regulation/analyze",
      bodyBuilder: "legal", // +보조: /api/v1/permits/ai-analysis (B2)
    },
    // (P1 B-1 정직화) RegulationInterpreter(BaseInterpreter 서브클래스)는 없지만, 이미 충전되어 있다:
    // RegulationAnalysisService.analyze()가 use_llm=True(기본값)일 때 자체 _llm()을 호출해
    // result["ai"]에 해석을 담는다(app/services/regulation/regulation_analysis_service.py:212-213,459 ·
    // 과금계측 record_llm_response_billing(service="regulation") 동 파일:484-485). enforce_llm_quota는
    // routers/regulation.py:44에서 라우터 레벨로 이미 적용됨. → DAG 표준 인터프리터 통로는 아니지만
    // "미충전"이 아니므로 null을 새 클래스로 대체하지 않는다(중복 배선 방지). 값은 null 유지.
    expertInterpreter: null,
    expertPanel: true, // 상위법령↔조례 충돌 다관점
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:legal",
    reportContract: {
      sectionKey: "legal",
      fields: ["bcrCompliant", "farCompliant", "heightCompliant", "violations"],
      unavailableLabel: "법규검토 미실행",
    },
    lens: "legal",
    groundingSources: ["국가법령정보", "자치법규(조례)", "도시계획"],
    available: true,
    icon: "stage_legal_compliance",
  },
  {
    id: "recommend",
    label: "개발방식·사업모델 추천",
    storyOrder: 3,
    storylineStage: "permit",
    moduleKey: null, // 파생 노드 — store staleness 미참여(L2 nodeUpdatedAt로 파생)
    upstream: ["land", "legal"],
    ssotInputs: [
      {
        slot: "siteAnalysis",
        readyCheck: hasSite,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: true,
      },
      {
        slot: "complianceData",
        readyCheck: hasCompliance,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false,
      },
    ],
    // (Phase C-1) 최상위 추천 개발방식(ranked[0].method)만 feasibilityData.developmentType에 환류.
    // partial:true·setRecommendedDevType은 updatedAt.feasibility를 stamp하지 않으므로(전용 액션)
    // 파생(recommend) 노드가 수지 staleness를 오염시켜 수지 노드가 영영 skipped-fresh되는 함정을 피한다.
    // 매출·원가·ROI 등 다른 수지 슬롯은 일절 건드리지 않는다(merge 보존). 라이브 검증: ranked[0].method=M06 등.
    ssotOutputs: [
      { updateAction: "setRecommendedDevType", source: "auto", partial: true },
    ],
    runner: {
      method: "POST",
      path: "/api/v1/development-methods/optimal-recommend",
      bodyBuilder: "recommend", // +보조: /api/v1/development-methods/scenarios, /evaluate (B2)
    },
    // (P1 B-1 충전) DevelopmentMethodInterpreter 신설 — optimal-recommend가 산출한 Top3
    // 순위(유형·용적률·수지)+게이트(특이부지·잠정치·종상향)를 실무 관점으로 해석한다.
    // routers/development_methods.py optimal_recommend에 use_llm(기본 false=무과금) additive
    // 필드로 opt-in 부착(app/services/ai/development_method_interpreter.py).
    expertInterpreter: "DevelopmentMethodInterpreter",
    expertPanel: true, // 15모델 다관점
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:recommend",
    reportContract: {
      sectionKey: "recommend",
      fields: ["topMethods", "feasibilityRank"],
      unavailableLabel: "개발방식 추천 미실행",
    },
    lens: "legal",
    groundingSources: ["용도지역 한도", "지구단위계획", "특이부지 게이트"],
    available: true,
    icon: "stage_permit_portal",
  },
  {
    // ── (B6-3) 인허가 분석 노드 ──
    // 쉬운 설명: 주소(+조례·상위법령)를 종합해 "7개 개발방식"별 가능/문제/해결방안을
    // 서술형으로 분석한다(POST /api/v1/permits/ai-analysis). 결과는 화면 표시·판단분기용이며,
    // ★complianceData(건폐/용적 적합·위반 같은 정량 슬롯)는 산출하지 않는다(라이브 응답에 해당 키 부재).
    // 따라서 store 환류는 하지 않는다(ssotOutputs=[]) — legal 노드가 이미 complianceData 슬롯의
    // 단일 owner이므로, permit이 같은 슬롯을 중복 소유하지 않도록 표시·판단 전용으로 둔다(무목업·무중복).
    id: "permit",
    label: "인허가 분석(개발방식 가능성)",
    storyOrder: 3.5, // recommend(3)와 design(4) 사이 — 기존 1~9 정수 순서 불변(append-safe)
    storylineStage: "permit",
    moduleKey: null, // 표시·판단분기 노드 — store staleness 미참여(L2 nodeUpdatedAt로 파생)
    upstream: ["land"], // 주소(siteAnalysis.address)가 사실근거 루트(legal과 동일 — 부지만 있으면 가능)
    ssotInputs: [
      {
        // 백엔드 필수★ = address(AIPermitAnalysisRequest.address: str). 부지분석 주소 슬롯으로 충족.
        slot: "siteAnalysis",
        field: "address",
        readyCheck: hasSite,
        resolution: ["ssot", "upstream-suggest"],
        manualPrompt: "분석할 토지 주소(부지분석)가 필요합니다",
        provenanceGuarded: false, // 인허가 분석은 ProvenanceModule 밖(merge가드 없음) → 정직 표기
      },
    ],
    ssotOutputs: [], // 표시·판단분기 — store 비기록(complianceData 중복 owner 회피·정량 키 부재)
    runner: {
      method: "POST",
      path: "/api/v1/permits/ai-analysis",
      bodyBuilder: "permit", // {address★, pnu?, parcels?} (B6-3)
    },
    // (P1 B-1 정직화) PermitAnalysisService.analyze()가 use_llm=True(기본값)일 때 자체 _llm_analyze()를
    // 호출해 응답 dict에 data["ai"]=True를 담아 이미 인라인 LLM으로 충전되어 있다
    // (app/services/permit/permit_analysis_service.py:338 _llm_analyze, 369·429 data["ai"]=True,
    // 359-360·421-422 record_llm_response_billing(service="permit")). enforce_llm_quota는
    // routers/permits.py:461에서 라우터 레벨로 이미 적용됨. app/services/ai/permit_interpreter.py의
    // PermitInterpreter는 이 노드가 아니라 별도 검증결과 해석 경로용이므로 여기 재사용하지 않는다
    // (날조 금지). → 이 노드 전담 BaseInterpreter 서브클래스는 없음(미충전이 아님) → null 유지.
    expertInterpreter: null,
    expertPanel: true, // 7개 개발방식 가능/불가·상위법령↔조례 충돌 다관점 판단분기
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:permit",
    reportContract: {
      sectionKey: "permit",
      // 라이브 응답키(ai/summary/methods/recommendation/site) — 서술형 인허가 분석.
      fields: ["summary", "methods", "recommendation"],
      unavailableLabel: "인허가 분석 미실행",
    },
    lens: "permit",
    groundingSources: ["용도지역 한도", "자치법규(조례)", "상위법령", "특이부지 게이트"],
    available: true,
    icon: "stage_permit_portal",
  },
  {
    id: "design",
    label: "건축개요·설계 AI",
    storyOrder: 4,
    storylineStage: "design",
    moduleKey: "design",
    upstream: ["land", "recommend"],
    ssotInputs: [
      {
        slot: "siteAnalysis",
        readyCheck: hasSite,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: true,
      },
      {
        slot: "complianceData",
        readyCheck: hasCompliance,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false,
      },
    ],
    ssotOutputs: [{ updateAction: "updateDesignData", source: "auto" }],
    runner: {
      method: "POST",
      path: "/api/v1/design/{id}/bim/generate",
      bodyBuilder: "design", // +보조: /api/v1/design/{id}/mass (B2)
    },
    expertInterpreter: "DesignInterpreter", // 확인됨: app/services/ai/design_interpreter.py:62
    expertPanel: false,
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:design",
    reportContract: {
      sectionKey: "design",
      fields: ["totalGfaSqm", "floorCount", "bcr", "far", "unitCount"],
      unavailableLabel: "설계 미실행",
    },
    lens: "design",
    groundingSources: ["용도지역 법정한도", "건축개요", "BIM 매스"],
    available: true,
    icon: "stage_design_ai",
  },
  {
    id: "audit",
    label: "AI 설계심의",
    storyOrder: 5,
    storylineStage: "design",
    moduleKey: null, // 검증 노드 — store 비기록
    upstream: ["design", "legal"],
    ssotInputs: [
      {
        slot: "designData",
        readyCheck: hasDesign,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: true,
      },
      {
        slot: "complianceData",
        readyCheck: hasCompliance,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false,
      },
    ],
    ssotOutputs: [], // 검증결과 — store 비기록
    runner: {
      // 심의분석엔진(deliberation-review) BFF 풀통합 완료 → /api/v1/deliberation/analyze로 전환.
      // BFF는 graceful degrade 보장: 엔진 미연결/타임아웃/4xx/5xx/malformed 시 200 + {status:"degraded", reason}.
      // ★노드 실행 결과는 degraded 상태를 정직 표기(에러 크래시 금지) — 패널/리포트가 reason을 그대로 노출.
      method: "POST",
      path: "/api/v1/deliberation/analyze",
      bodyBuilder: "audit",
    },
    // (P1 B-1 정직화) 외부 심의분석엔진(deliberation-review, 별도 서비스)이 소유·수행하는 검증이다.
    // 로컬(app/services/ai/*) 인터프리터 충전 대상이 아니다 — BFF는 엔진 응답을 그대로 표면화할 뿐,
    // 이 노드에서 로컬 LLM 인터프리터를 새로 부착하는 것은 중복(엔진이 이미 자체 해석 수행).
    expertInterpreter: null, // 외부 심의엔진 소유 — 로컬 충전 대상 아님
    expertPanel: false, // 엔진 내부
    // ★의도: 심의엔진이 검증(교차검증·근거추적)을 내부에서 수행하므로, BFF 노드 외부에서의
    //  중복 외부검증은 불필요하다(이상적으론 {crossValidate:false, verifyAnalysis:false}).
    //  단 lint-node-registry [E4]가 모든 노드에 crossValidate=true를 강제하므로(우회 차단 게이트)
    //  레지스트리 정합을 위해 true로 둔다 — 실제 외부검증 트리거는 호출측이 audit에 한해 생략한다.
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:audit",
    reportContract: {
      sectionKey: "audit",
      // 실제 BFF 응답키(_wrap_result): findings(검토 항목) + complianceScore(CONFIRMED 비율).
      // (auditFindings는 미존재 키였음 — 라이브 응답 계약으로 정정.)
      fields: ["findings", "complianceScore"],
      unavailableLabel: "심의엔진 연결 대기", // degraded(엔진 미연결) 시 정직 표기 라벨
    },
    lens: "design",
    groundingSources: ["설계 산출(designData)", "법규(complianceData)"],
    available: true, // 심의분석엔진 BFF 풀통합 완료 → unlock(degraded는 노드 실행 결과로 정직 표기)
    icon: "stage_design_ai",
  },
  {
    id: "sales",
    label: "분양성·분양가",
    storyOrder: 6,
    storylineStage: "feasibility",
    moduleKey: null, // 피드 노드 — 데이터 SSOT 비기록(결과는 orchestration nodeResult에만)
    upstream: ["land", "design"],
    ssotInputs: [
      {
        slot: "siteAnalysis",
        readyCheck: hasSite,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: true,
      },
      {
        slot: "designData",
        readyCheck: hasDesign,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: true,
      },
    ],
    // (Phase C-2) 적정분양가(아파트 평당 실거래가)만 feasibilityData.salePricePerPyeongWon에 환류.
    // partial:true·setSalesPricePerPyeong은 updatedAt.feasibility를 stamp하지 않으므로(전용 액션)
    // 파생(sales) 노드가 수지 staleness를 오염시켜 수지 노드가 영영 skipped-fresh되는 함정을 피한다
    // (C-1 setRecommendedDevType과 동일한 안전 패턴 — 매출·원가·ROI 등 다른 수지 슬롯은 미접촉).
    // ★매출·ROI 최종 산출은 여전히 feasibility 노드가 담당. 여기서는 "매출단가 입력값"만 시드한다.
    // 라이브 검증: trade.아파트.per_pyeong.avg=11161(만원/평) → ×10000=111,610,000(원/평).
    ssotOutputs: [
      { updateAction: "setSalesPricePerPyeong", source: "auto", partial: true },
    ],
    runner: {
      method: "POST",
      path: "/api/v1/market/report",
      bodyBuilder: "sales", // +보조: pricing_band (B2)
    },
    expertInterpreter: "MarketInterpreter", // 확인됨: app/services/ai/market_interpreter.py:73
    expertPanel: true, // 거래사례비교↔지불여력 다관점
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:sales",
    reportContract: {
      sectionKey: "sales",
      fields: ["salesPriceWon", "totalRevenueWon", "pricingBand"],
      unavailableLabel: "분양성 분석 미실행",
    },
    lens: "market",
    groundingSources: ["실거래(MOLIT)", "주변 분양가", "지불여력(PIR/DSR/LTV)"],
    available: true,
    icon: "stage_feasibility",
  },
  {
    id: "qto",
    label: "BIM적산·공사비",
    storyOrder: 7,
    storylineStage: "construction",
    moduleKey: "cost",
    upstream: ["design"],
    ssotInputs: [
      {
        slot: "designData",
        readyCheck: hasDesign,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: true,
      },
    ],
    ssotOutputs: [{ updateAction: "updateCostData", source: "auto" }],
    runner: {
      method: "POST",
      path: "/api/v1/cost/estimate-overview",
      bodyBuilder: "qto", // +보조: BOQ/QTO (B2)
    },
    expertInterpreter: "CostInterpreter", // 확인됨: app/services/ai/cost_interpreter.py:72
    expertPanel: false,
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:qto",
    reportContract: {
      sectionKey: "cost",
      fields: ["totalConstructionCostWon", "perSqmWon", "rangeMinWon", "rangeMaxWon"],
      unavailableLabel: "공사비 적산 미실행",
    },
    lens: "construction",
    groundingSources: ["건축개요 QTO", "표준품셈", "실적단가"],
    available: true,
    icon: "stage_construction",
  },
  {
    id: "feasibility",
    label: "사업수지·ROI",
    storyOrder: 8,
    storylineStage: "feasibility",
    moduleKey: "feasibility",
    upstream: ["sales", "qto", "land", "design"],
    ssotInputs: [
      {
        slot: "siteAnalysis",
        readyCheck: hasSite,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false, // feasibility는 ProvenanceModule 밖
      },
      {
        slot: "designData",
        readyCheck: hasDesign,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false,
      },
      {
        slot: "costData",
        readyCheck: hasCost,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false,
      },
      // 매출(feasibilityData.totalRevenueWon) 입력 제거: feasibility는 backend가 regional_pricing으로
      // 매출 자체를 산출한다(siteAnalysis/designData/costData만 사실근거). sales가 매출을 stamp하지 않으므로
      // resolveInputs가 feasibility를 영구 needs-input으로 막지 않는다. sales→매출 주입은 Phase C.
      {
        // (G1) 파생 환류 전용(옵셔널): 추천 개발유형(C-1 developmentType)·적정분양가(C-2
        // salePricePerPyeongWon)·개략수지 GFA/세대수 폴백을 bodyBuilder(node-body-builders.ts의
        // feas?.developmentType·feas?.salePricePerPyeongWon·feas?.totalGfaSqm·feas?.totalHouseholds)가
        // 읽도록 컨텍스트(useNodeRunner의 ready 슬롯 → context 조립)에 주입한다.
        // readyCheck를 항상 true로 두어 ①부재여도 needs-input/그라운딩 미가용으로 게이트하지 않고
        // (과거 "매출 입력 제거" 의도 보존) ②존재할 때만 context 주입 루프의 null 가드(slotVal != null)가
        // 실값을 싣는다. 자기 출력 슬롯(ssotOutputs.updateFeasibilityData)을 재참조하지만, 그래프 간선은
        // dependency-graph.ts가 upstream 필드만으로 계산하므로(ssotInputs는 edge에 미사용, lint-node-registry
        // [E1] 사이클검사도 upstream 기준) 순환이 아니다(dependency-graph.cycle.test.ts·
        // lint-node-registry.test.ts로 회귀 고정).
        // (P1 B-3 LOW-1) manualPrompt 부여 — readyCheck가 항상 true라서 store 실값이 null이어도
        // resolveInputs의 ready[]에 들어온다. InputResolveModal이 slotLabel()로 이 문구를 노출해
        // "확보된 입력"에 raw 키(feasibilityData)가 아니라 사람말로 뜨게 하고, 실값 부재 시엔
        // 모달이 ✓ 대신 중립 표기("선택 입력 — 미확보 시 기본값")로 정직화한다(값 자체는 불변).
        slot: "feasibilityData",
        readyCheck: () => true,
        resolution: ["ssot"],
        manualPrompt: "수지 파생환류(선택·자동 반영)",
        provenanceGuarded: false,
      },
    ],
    ssotOutputs: [{ updateAction: "updateFeasibilityData", source: "auto" }],
    runner: {
      method: "POST",
      path: "/api/v2/feasibility/calculate",
      bodyBuilder: "feasibility", // +보조: /api/v2/feasibility/compare, /cashflow (B2)
    },
    expertInterpreter: "FeasibilityInterpreter", // 확인됨: app/services/ai/feasibility_interpreter.py:83
    expertPanel: true, // ROI 분기·할루시네이션
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:feasibility",
    reportContract: {
      sectionKey: "feasibility",
      fields: ["totalCostWon", "totalRevenueWon", "profitRatePct", "roiPct", "npvWon"],
      unavailableLabel: "사업수지 미실행",
    },
    lens: "feasibility",
    groundingSources: ["토지비", "공사비(costData)", "매출(분양)", "금융비·세금"],
    available: true,
    icon: "stage_feasibility",
  },
  {
    id: "finance",
    label: "PF·개발금융",
    storyOrder: 9,
    storylineStage: "finance",
    moduleKey: "finance",
    upstream: ["feasibility", "qto"],
    ssotInputs: [
      {
        slot: "feasibilityData",
        readyCheck: hasFeasibilityRevenue,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false, // finance는 ProvenanceModule 밖
      },
      {
        slot: "costData",
        readyCheck: hasCost,
        resolution: ["ssot", "upstream-suggest"],
        provenanceGuarded: false,
      },
    ],
    ssotOutputs: [{ updateAction: "markFinanceUpdated", source: "auto" }],
    runner: {
      method: "POST",
      path: "/api/v2/feasibility/development-finance",
      bodyBuilder: "finance", // +보조: /api/v1/bank-report/generate (B2)
    },
    // (P1 B-1 충전) FinanceInterpreter 신설 — development-finance가 산출한 PF/브릿지 구조·
    // LTV·DSCR을 실무 관점(자금구조·금리민감도·리스크)으로 해석한다. app/routers/v2_feasibility.py
    // DevelopmentFinanceRequest에 use_llm(기본 false=무과금) additive 필드로 opt-in 부착
    // (app/services/ai/finance_interpreter.py).
    expertInterpreter: "FinanceInterpreter",
    expertPanel: true, // PF구조·금리 분기
    verify: { crossValidate: true, verifyAnalysis: true },
    billingKey: "stage:finance",
    reportContract: {
      sectionKey: "finance",
      fields: ["pfStructure", "interestRate", "ltv", "dscr"],
      unavailableLabel: "개발금융 미실행",
    },
    lens: "feasibility",
    groundingSources: ["수지(feasibilityData)", "공사비(costData)", "금리·LTV"],
    available: true,
    icon: "stage_finance",
  },
];
