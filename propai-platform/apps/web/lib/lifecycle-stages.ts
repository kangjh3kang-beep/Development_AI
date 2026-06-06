/**
 * 라이프사이클 단계 SSOT(단일 진실원) 모듈 — P1 구조재편.
 *
 * 진실원은 `store/useProjectContextStore.ts`의 `LIFECYCLE_STAGES`(10단계)다.
 * 이 모듈은 그 배열을 **재export**하고(새 배열을 만들지 않음), 각 단계에 대한
 * 표시 메타(`{ id, label, route, group, icon }`)와 상단탭 그룹 정의(`STAGE_GROUPS`)를
 * 단일 위치에 둔다. 네비게이션 3종(상단탭/진행바/컴팩트 파이프라인)이 모두 이 모듈을
 * import 하여 라벨·순서·라우트·개수 불일치(4중 중복)를 제거한다.
 *
 *  - 진행바(LifecycleProgressRail): 10단계 SSOT를 그대로 상태 시각화
 *  - 상단탭(Lifecyclenavigator): 같은 10단계를 그룹뷰(STAGE_GROUPS)로 진입 제공
 *  - route는 실제 존재하는 서브라우트 세그먼트(404 방지). 死라우트는 진입점만 정합.
 */

import {
  LIFECYCLE_STAGES,
  type LifecycleStage,
} from "@/store/useProjectContextStore";

// SSOT 재export — 다른 모듈은 store 대신 이 모듈에서 가져와도 동일 진실원을 본다.
export { LIFECYCLE_STAGES };
export type { LifecycleStage };

/** 상단탭 그룹 식별자(개요/입지/법규/설계/사업성/인허가/시공/보고서). */
export type StageGroupId =
  | "overview"
  | "site"
  | "legal"
  | "design"
  | "feasibility"
  | "permit"
  | "construction"
  | "report";

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
 * 단계 SSOT 메타 — 키는 store의 LifecycleStage(10단계)와 1:1.
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
};

/** 단계 라우트 세그먼트(프로젝트 상세 하위 경로 빌더 보조). */
export function stageRoute(locale: string, projectId: string, stage: LifecycleStage): string {
  return `/${locale}/projects/${projectId}/${STAGE_META[stage].route}`;
}

/**
 * 상단탭 그룹 정의 — 같은 10단계를 8그룹으로 묶은 "진입 뷰".
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
    label: "입지 분석",
    icon: "site_analysis",
    stages: ["site-analysis"],
  },
  {
    id: "legal",
    label: "법규 검토",
    icon: "legal_compliance",
    stages: ["legal"],
  },
  {
    id: "design",
    label: "건축 설계",
    icon: "design_ai",
    stages: ["design", "bim"],
  },
  {
    id: "feasibility",
    label: "사업성 검토",
    icon: "feasibility",
    stages: ["feasibility", "finance", "esg"],
  },
  {
    id: "permit",
    label: "인허가/계약",
    icon: "permit_portal",
    stages: ["permit"],
    extraRoutes: [{ route: "contracts", label: "전자 계약", icon: "permit_portal" }],
  },
  {
    id: "construction",
    label: "시공 관리",
    icon: "construction",
    stages: ["construction"],
  },
  {
    id: "report",
    label: "보고서",
    icon: "permit_portal",
    stages: ["report"],
  },
];
