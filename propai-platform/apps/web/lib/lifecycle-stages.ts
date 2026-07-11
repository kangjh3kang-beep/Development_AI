/**
 * 라이프사이클 단계 SSOT(단일 진실원) 모듈 — P1 구조재편.
 *
 * 진실원은 `store/useProjectContextStore.ts`의 `LIFECYCLE_STAGES`(11단계 — WP-17 operations append)다.
 * 이 모듈은 그 배열을 **재export**하고(새 배열을 만들지 않음), 각 단계에 대한
 * 표시 메타(`{ id, label, route, group, icon }`)와 상단탭 그룹 정의(`STAGE_GROUPS`)를
 * 단일 위치에 둔다. 네비게이션 3종(상단탭/진행바/컴팩트 파이프라인)이 모두 이 모듈을
 * import 하여 라벨·순서·라우트·개수 불일치(4중 중복)를 제거한다.
 *
 *  - 진행바(LifecycleProgressRail): 11단계 SSOT를 그대로 상태 시각화
 *  - 상단탭(Lifecyclenavigator): 같은 11단계를 그룹뷰(STAGE_GROUPS)로 진입 제공
 *  - route는 실제 존재하는 서브라우트 세그먼트(404 방지). 死라우트는 진입점만 정합.
 */

import {
  LIFECYCLE_STAGES,
  type LifecycleStage,
} from "@/store/useProjectContextStore";

// SSOT 재export — 다른 모듈은 store 대신 이 모듈에서 가져와도 동일 진실원을 본다.
export { LIFECYCLE_STAGES };
export type { LifecycleStage };

/** 상단탭 그룹 식별자(개요/입지/법규/설계/사업성/인허가/시공/보고서/운영). */
export type StageGroupId =
  | "overview"
  | "site"
  | "legal"
  | "design"
  | "feasibility"
  | "permit"
  | "construction"
  | "report"
  // WP-17: 여정 출구 — 운영 그룹(자산운영 진입). supervision/drone은 extraRoutes로 함께 노출.
  | "operations";

/** 단계 메타 — StageIcon 아이콘 키는 components/common/StageIcon.tsx의 ICONS 키에 정합. */
export interface StageMeta {
  /** 라우트 세그먼트(프로젝트 상세 하위). */
  route: string;
  /** 한글 라벨(전문가+일반인 직관). */
  label: string;
  /** StageIcon id. */
  icon: string;
  /** 소속 상단탭 그룹. */
  group: StageGroupId;
}

/**
 * 단계 SSOT 메타 — 키는 store의 LifecycleStage(11단계)와 1:1.
 * route는 실제 존재 라우트 세그먼트로 정합(404 방지).
 */
export const STAGE_META: Record<LifecycleStage, StageMeta> = {
  "site-analysis": { route: "site-analysis", label: "부지분석", icon: "site_analysis", group: "site" },
  legal: { route: "legal", label: "법규검토", icon: "legal_compliance", group: "legal" },
  design: { route: "design", label: "설계", icon: "design_ai", group: "design" },
  bim: { route: "bim", label: "BIM", icon: "design_ai", group: "design" },
  construction: { route: "construction", label: "시공계획", icon: "construction", group: "construction" },
  feasibility: { route: "feasibility", label: "수지분석", icon: "feasibility", group: "feasibility" },
  finance: { route: "finance", label: "금융분석", icon: "feasibility", group: "feasibility" },
  esg: { route: "esg", label: "ESG", icon: "esg_dashboard", group: "feasibility" },
  permit: { route: "permit", label: "인허가", icon: "permit_portal", group: "permit" },
  report: { route: "report", label: "보고서", icon: "permit_portal", group: "report" },
  // WP-17: 운영 단계 — route "operations" 기존재(404 없음), 아이콘 키 "operations"는
  // StageIcon ICONS에 이미 존재(톱니). 보고서 다음 단계로 진행레일·CTA에 자동 노출.
  operations: { route: "operations", label: "운영", icon: "operations", group: "operations" },
};

/** 단계 라우트 세그먼트(프로젝트 상세 하위 경로 빌더 보조). */
export function stageRoute(locale: string, projectId: string, stage: LifecycleStage): string {
  return `/${locale}/projects/${projectId}/${STAGE_META[stage].route}`;
}

/**
 * (G9) 백엔드 파이프라인 스텝(project_pipeline.PipelineStage 8종, StrEnum 리터럴 값) —
 * apps/api/app/services/pipeline/project_pipeline.py:22-32의 8종을 그대로 옮긴 유니언.
 * BE가 스텝을 추가/변경하면 이 타입과 아래 PIPELINE_STAGE_TO_LIFECYCLE, 그리고 계약 테스트
 * (lifecycle-stages.test.ts·apps/api/tests/test_pipeline_stage_contract.py)를 함께 갱신한다.
 */
export type PipelineStageBE =
  | "site_analysis"
  | "design"
  | "design_review"
  | "cost"
  | "feasibility"
  | "tax"
  | "esg"
  | "report";

/**
 * (G9) 백엔드 파이프라인 스텝(project_pipeline.PipelineStage 8종) → 프론트 라이프사이클
 * 단계 매핑. FE(11단계 UI 네비)와 BE(8단계 컴퓨트)는 의도적으로 입도가 다르다 — 이 표가
 * 유일한 공식 번역이며, 계약 테스트가 양쪽 enum을 핀 고정한다(드리프트=CI 실패).
 * BE에만 있는 스텝: design_review→(FE) permit(심의·인허가 검토 표면), cost→construction,
 * tax→feasibility(수지 내 세금). FE에만 있는 단계(bim·finance·operations·legal)는 BE 스텝
 * 없음(null) — 파이프라인이 산출하지 않는 UI 전용 단계임을 명시(이 표에는 값으로도 등장하지
 * 않는다 — BE→FE 단방향 매핑이므로).
 *
 * 각 매핑의 근거(STAGE_META 실라벨 대조로 가장 자연스러운 대응을 선택):
 *  - site_analysis → "site-analysis" : 라벨·역할 1:1("부지분석").
 *  - design        → "design"        : 라벨·역할 1:1("설계"). BIM 3D 뷰(FE 전용 "bim")는
 *                     파이프라인이 별도 산출하지 않는 UI 하위 화면이라 매핑 대상이 아니다.
 *  - design_review → "permit"        : 설계도면 자동심의(BE 컴퓨트 스텝, 외부 심의엔진 BFF
 *                     경유)는 FE에 별도 "심의" 탭이 없고 인허가 그룹(permit)이 그 검토 결과를
 *                     표면화한다.
 *  - cost          → "construction"  : BE cost 스텝은 공사비 산정(QTO/BOQ)이며, FE에서는
 *                     시공계획 그룹(construction)이 이 산출물을 표시한다.
 *  - feasibility   → "feasibility"   : 라벨·역할 1:1("수지분석").
 *  - tax           → "feasibility"   : BE tax 스텝(취득세·양도세 등)은 수지분석 결과에 세금
 *                     항목으로 포함되어 표시된다. FE의 "finance"는 PF/개발금융 전용(별도
 *                     v2_feasibility API)이라 tax와 역할이 다르므로 오매핑하지 않는다.
 *  - esg           → "esg"           : 라벨·역할 1:1("ESG").
 *  - report        → "report"        : 라벨·역할 1:1("보고서").
 */
export const PIPELINE_STAGE_TO_LIFECYCLE: Record<PipelineStageBE, LifecycleStage | null> = {
  site_analysis: "site-analysis",
  design: "design",
  design_review: "permit",
  cost: "construction",
  feasibility: "feasibility",
  tax: "feasibility",
  esg: "esg",
  report: "report",
};

/**
 * 상단탭 그룹 정의 — 같은 11단계를 9그룹으로 묶은 "진입 뷰"(개요 그룹 포함 시 10탭).
 *  - 개요는 SSOT 단계가 아닌 프로젝트 루트 진입(별도 처리).
 *  - 설계 그룹 = design + bim, 사업성 그룹 = feasibility + finance + esg.
 *  - 인허가 그룹 = permit (+ 전자계약 contracts: SSOT 단계는 아니나 같은 그룹 진입점).
 * stages 배열의 순서는 SSOT(LIFECYCLE_STAGES) 순서와 동일하게 유지.
 */
export interface StageGroup {
  id: StageGroupId;
  label: string;
  /** 그룹 대표 아이콘(StageIcon id). */
  icon: string;
  /** 그룹에 속한 SSOT 단계들(상단탭 클릭 → 첫 단계 라우트로 진입). */
  stages: LifecycleStage[];
  /**
   * SSOT 단계 외 추가 진입 링크(死라우트 보존·정합). 라우트 세그먼트만 보관.
   * (예: 인허가 그룹의 전자계약 contracts)
   */
  extraRoutes?: { route: string; label: string; icon: string }[];
}

export const STAGE_GROUPS: StageGroup[] = [
  {
    id: "overview",
    label: "개요",
    icon: "operations",
    stages: [], // 프로젝트 루트(/projects/{id}) 진입 — SSOT 단계 없음
  },
  {
    id: "site",
    label: "부지분석", // STAGE_META["site-analysis"].label과 1:1 정합(상단탭↔진행레일 라벨 통일)
    icon: "site_analysis",
    stages: ["site-analysis"],
  },
  {
    id: "legal",
    label: "법규검토", // STAGE_META.legal.label과 1:1 정합
    icon: "legal_compliance",
    stages: ["legal"],
  },
  {
    id: "design",
    label: "설계", // 다단계 그룹(설계+BIM) — 대표 단계 STAGE_META.design.label로 통일
    icon: "design_ai",
    stages: ["design", "bim"],
  },
  {
    id: "feasibility",
    label: "사업성", // 다단계 그룹(수지·금융·ESG) — 그룹 대표 라벨 유지(톤 통일)
    icon: "feasibility",
    stages: ["feasibility", "finance", "esg"],
  },
  {
    id: "permit",
    label: "인허가", // STAGE_META.permit.label과 1:1 정합(계약은 extraRoutes로 분리)
    icon: "permit_portal",
    stages: ["permit"],
    extraRoutes: [{ route: "contracts", label: "전자 계약", icon: "permit_portal" }],
  },
  {
    id: "construction",
    label: "시공계획", // STAGE_META.construction.label과 1:1 정합
    icon: "construction",
    stages: ["construction"],
  },
  {
    id: "report",
    label: "보고서",
    icon: "permit_portal",
    stages: ["report"],
  },
  {
    // WP-17: 여정 출구 — 운영 그룹. SSOT 단계 "operations"를 펼치고,
    // 라우트 기존재(404 없음)인 시공감리(supervision)·드론측량(drone)을 extraRoutes로 함께 노출.
    id: "operations",
    label: "운영",
    icon: "operations",
    stages: ["operations"],
    extraRoutes: [
      { route: "supervision", label: "시공감리", icon: "supervision" },
      { route: "drone", label: "드론측량", icon: "drone" },
    ],
  },
];

/**
 * 프로젝트 도구(독립 라우트) — 라이프사이클 11단계(STAGE_META)에도, STAGE_GROUPS의
 * extraRoutes(contracts·supervision·drone)에도 속하지 않아 **어느 네비에도 노출되지 않던**
 * 프로젝트 상세 하위 라우트들. "프로젝트 도구 인덱스"(접이식, ProjectToolIndex)로 surface한다.
 *
 *  - route: 실제 존재하는 서브라우트 세그먼트(404 방지). STAGE_META 단계와 중복 없음(additive).
 *  - label: 해당 라우트 page.tsx의 실제 제목/용도 기준(정직).
 *  - icon: components/common/StageIcon.tsx의 ICONS 키(tool_*).
 * 진행레일·STAGE_GROUPS는 무수정 — 본 구조만 신설한다.
 */
export interface ProjectTool {
  route: string;
  label: string;
  icon: string;
}

export const PROJECT_TOOLS: ProjectTool[] = [
  { route: "canvas", label: "중앙분석센터", icon: "tool_map" },
  { route: "cad", label: "설계도면(CAD)", icon: "tool_cad" },
  { route: "collaboration", label: "회의방", icon: "tool_collab" },
  { route: "cost", label: "공사비", icon: "tool_cost" },
  { route: "boq", label: "공내역서(BOQ)", icon: "tool_boq" },
  { route: "multi-parcel", label: "다필지 통합", icon: "tool_parcel" },
  { route: "blockchain", label: "블록체인", icon: "tool_chain" },
  { route: "agent", label: "AI 분석", icon: "tool_agent" },
];

/** 프로젝트 도구 라우트(프로젝트 상세 하위 절대경로 빌더). */
export function projectToolHref(locale: string, projectId: string, route: string): string {
  return `/${locale}/projects/${projectId}/${route}`;
}
