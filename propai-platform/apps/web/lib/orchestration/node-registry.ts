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
//   finance     POST /api/v2/feasibility/development-finance (app/routers/v2_feasibility.py:1223) ✓
// interpreter(apps/api/app/services/ai/* 실제 클래스):
//   SiteAnalysisInterpreter ✓ / DesignInterpreter ✓ / MarketInterpreter ✓ / CostInterpreter ✓ / FeasibilityInterpreter ✓
//   RegulationInterpreter ✗(미존재) / DevelopmentMethodInterpreter ✗(미존재) / FinanceInterpreter ✗(미존재) → null + B2 배선 주석
//   audit는 심의엔진 소유 → null
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
    // RegulationInterpreter 미존재(app/services/ai/* 부재) → B2에서 확인/배선. 추정 클래스명 날조 금지.
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
    // DevelopmentMethodInterpreter 미존재 → B2에서 확인/배선. 날조 금지.
    expertInterpreter: null,
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
    // /ai-analysis는 PermitInterpreter에 미배선(PermitAnalysisService._llm_analyze가 get_llm 직접 호출,
    // record_llm_response_billing(service="permit")로 계측). PermitInterpreter는 별도 검증결과 해석 경로용 →
    // 이 노드 전담 interpreter는 없음(날조 금지) → null.
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
      // 심의엔진 main머지 후 /api/v1/deliberation/analyze BFF 어댑터로 교체 예정(미접촉).
      // 현재 design-audit/run은 존재하나 available:false라 selector locked·skipped-unavailable 정직.
      method: "POST",
      path: "/api/v1/design-audit/run",
      bodyBuilder: "audit",
    },
    expertInterpreter: null, // 외부 심의엔진 소유 — 미접촉
    expertPanel: false, // 엔진 내부
    verify: { crossValidate: true, verifyAnalysis: true }, // 계약 5단계 충족(엔진이 내부 수행, lint 통과용 true)
    billingKey: "stage:audit",
    reportContract: {
      sectionKey: "audit",
      fields: ["auditFindings", "complianceScore"],
      unavailableLabel: "심의엔진 연동 예정",
    },
    lens: "design",
    groundingSources: ["설계 산출(designData)", "법규(complianceData)"],
    available: false, // 심의엔진 main머지 전까지 locked(B7에서 unlock)
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
    // 매출→feasibility 주입은 Phase C(backend 매출 주입 지원과 함께). B2는 stamp 오염/가짜주입
    // 회피 위해 데이터 미기록 — 결과는 orchestration nodeResult에만.
    // (이유: updateFeasibilityData(partial)이 항상 feasibility를 stamp → feasibility 노드가
    //  skipped-fresh로 영영 건너뛰어져 ROI가 실행되지 않던 결함. 주입은 C로 미룬다.)
    ssotOutputs: [],
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
    // FinanceInterpreter 미존재 → B2에서 확인/배선. 날조 금지.
    expertInterpreter: null,
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
