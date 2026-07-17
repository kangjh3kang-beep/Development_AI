/**
 * Platform route registry.
 *
 * This is the non-visual source of truth for primary IA, sitemap generation,
 * route status audits, and later dashboard shortcuts. Visual navigation maps
 * these records to icons in components/layout/nav-config.tsx.
 */

export type RouteStatus = "live" | "beta" | "placeholder" | "hidden";
export type RouteScope = "global" | "project" | "admin";
export type LifecyclePhase =
  | "control"
  | "intake"
  | "project"
  | "land-rights"
  | "market"
  | "acquisition"
  | "business"
  | "design"
  | "operations"
  | "account"
  | "admin";

export type PrimaryNavSectionId =
  | "control"
  | "projects"
  | "market-acquisition"
  | "design-center"
  | "sales-management"
  | "my"
  | "admin";

export interface PrimaryNavSectionMeta {
  id: PrimaryNavSectionId;
  title: string;
  order: number;
  adminOnly?: boolean;
  assetOpsOnly?: boolean;
}

export interface RouteRegistryItem {
  id: string;
  label: string;
  sectionId: PrimaryNavSectionId;
  order: number;
  parentId?: string;
  path?: `/${string}`;
  iconKey?: string;
  status: RouteStatus;
  scope: RouteScope;
  lifecyclePhase: LifecyclePhase;
  adminOnly?: boolean;
  assetOpsOnly?: boolean;
  prefetch?: false;
  apiDependencies?: string[];
}

export interface RegistryNavNode extends RouteRegistryItem {
  href?: string;
  children?: RegistryNavNode[];
}

export interface RegistryNavSection extends PrimaryNavSectionMeta {
  items: RegistryNavNode[];
}

export const PRIMARY_NAV_SECTIONS: PrimaryNavSectionMeta[] = [
  { id: "control", title: "관제", order: 10 },
  { id: "projects", title: "프로젝트", order: 20 },
  { id: "market-acquisition", title: "시장·획득", order: 30 },
  { id: "design-center", title: "설계 센터", order: 40 },
  // 분양 관리 — 구 IA의 "분양 현장 관리" 그룹 복원. IA 통합 리팩토링(800e7477)이 이 그룹을
  //   registry로 미이관(메뉴 소실)하고, 구 IA가 의도적으로 숨겼던 자산운영(운영 센터)을 되살리는
  //   이중 역전이 있었음 → 운영 센터를 분양 관리로 대체(자산운영 라우트·페이지는 보존, 향후 복원 가능).
  { id: "sales-management", title: "분양 관리", order: 50 },
  // 마이페이지 — SaaS 계정 셀프서비스(코인·결제·사용내역·프로필·개인정보). 전 회원 노출.
  { id: "my", title: "마이페이지", order: 55 },
  { id: "admin", title: "관리", order: 60, adminOnly: true },
];

export const PRIMARY_ROUTE_REGISTRY: RouteRegistryItem[] = [
  {
    id: "center",
    label: "중앙분석센터",
    sectionId: "control",
    order: 10,
    path: "/",
    iconKey: "dashboard",
    status: "live",
    scope: "global",
    lifecyclePhase: "control",
    apiDependencies: ["/dashboard/kpi", "/projects"],
  },
  {
    id: "precheck",
    label: "90초 사업성 진단",
    sectionId: "control",
    order: 20,
    path: "/precheck",
    iconKey: "permit",
    status: "live",
    scope: "global",
    lifecyclePhase: "intake",
    apiDependencies: ["/precheck"],
  },
  {
    id: "comprehensive-analysis",
    label: "종합 부지분석",
    sectionId: "control",
    order: 30,
    path: "/analysis",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "control",
    apiDependencies: ["/analysis"],
  },
  {
    // 내 구독·팀 관리(MY PAGE) — 관리자 전용이 아니라 전 회원(팀장·일반회원 공통) 개인 화면이라
    // adminOnly 섹션(admin)이 아닌 관제(control, 게이트 없음)에 배선한다.
    id: "team",
    label: "내 구독·팀 관리",
    sectionId: "control",
    order: 40,
    path: "/settings/team",
    iconKey: "team",
    status: "live",
    scope: "global",
    lifecyclePhase: "control",
    apiDependencies: ["/teams"],
  },
  {
    id: "projects",
    label: "프로젝트 관리",
    sectionId: "projects",
    order: 10,
    path: "/projects",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "project",
    apiDependencies: ["/projects"],
  },
  {
    id: "land-rights",
    label: "토지·권리",
    sectionId: "projects",
    order: 20,
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
  },
  {
    id: "land-schedule",
    label: "토지조서",
    sectionId: "projects",
    parentId: "land-rights",
    order: 10,
    path: "/land-schedule",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
    apiDependencies: ["/land-schedule"],
  },
  {
    id: "registry-analysis",
    label: "등기부등본 열람",
    sectionId: "projects",
    parentId: "land-rights",
    order: 20,
    path: "/registry-analysis",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
    apiDependencies: ["/registry/analyze"],
  },
  {
    id: "desk-appraisal",
    label: "AI 시세추정 보고서",
    sectionId: "projects",
    parentId: "land-rights",
    order: 30,
    path: "/desk-appraisal",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
    apiDependencies: ["/desk-appraisal"],
  },
  {
    // 사업성·비용(2항목) 얇은 L2 그룹 해체 — 기본 접힘 그룹이 핵심 사업기능(투자·적산)을 가려
    // 발견성이 나빴다. 투자 수익성·적산·공사비 관리를 프로젝트 섹션 직속 L2 리프로 승격(상시 노출).
    // 프로젝트 섹션 항목수는 여전히 7개 미만이라 IA 그룹화 규칙(§6) 위반 아님.
    id: "investment",
    label: "투자 수익성",
    sectionId: "projects",
    order: 30,
    path: "/analytics/investment",
    iconKey: "roi",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/analytics/investment"],
  },
  {
    // "공사비 분석"→"적산·공사비 관리" 개칭. /analytics/cost 허브가 개략 산정 + 상세 내역서(BOQ,
    // BoqDetailTable) 탭을 담당. 사업성·비용 그룹 해체로 프로젝트 섹션 직속 승격(적산관리 발견성 개선).
    id: "cost",
    label: "적산·공사비 관리",
    sectionId: "projects",
    order: 40,
    path: "/analytics/cost",
    iconKey: "cost",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/analytics/cost"],
  },
  {
    // ESG(GRESB) 분석 페이지 — 투자·적산과 나란히 사업성 분석군 직속 리프로 승격(orphan 배선 해소).
    id: "esg",
    label: "ESG 분석",
    sectionId: "projects",
    order: 50,
    path: "/analytics/esg",
    iconKey: "esg",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/ai/llm"],
  },
  {
    id: "market-sales",
    label: "시장·분양",
    sectionId: "market-acquisition",
    order: 10,
    iconKey: "market",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
  },
  {
    id: "market-insights",
    label: "시장·시세 분석",
    sectionId: "market-acquisition",
    parentId: "market-sales",
    order: 10,
    path: "/market-insights",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/market"],
  },
  {
    // 대화형 시장분석 AI — 자연어 질의 → /zoning/nearby-map(국토부 실거래) → 차트. 그동안
    // 컴포넌트(ConversationalMarketPanel)만 있고 라우트가 없어 orphan 이던 것을 전용 라우트로 배선.
    id: "market-ai",
    label: "대화형 시장분석 AI",
    sectionId: "market-acquisition",
    parentId: "market-sales",
    order: 15,
    path: "/market-ai",
    status: "beta",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/zoning/nearby-map"],
  },
  {
    id: "sales-info",
    label: "분양정보",
    sectionId: "market-acquisition",
    parentId: "market-sales",
    order: 20,
    path: "/sales-info",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/presale"],
  },
  {
    id: "acquisition",
    label: "사업 획득",
    sectionId: "market-acquisition",
    order: 20,
    iconKey: "auction",
    status: "live",
    scope: "global",
    lifecyclePhase: "acquisition",
  },
  {
    id: "auction",
    label: "경매·공매",
    sectionId: "market-acquisition",
    parentId: "acquisition",
    order: 10,
    path: "/auction",
    status: "live",
    scope: "global",
    lifecyclePhase: "acquisition",
    apiDependencies: ["/auction"],
  },
  {
    id: "g2b",
    label: "공공입찰",
    sectionId: "market-acquisition",
    parentId: "acquisition",
    order: 20,
    path: "/g2b",
    status: "live",
    scope: "global",
    lifecyclePhase: "acquisition",
    apiDependencies: ["/g2b"],
  },
  {
    id: "permit-reg",
    label: "인허가·규제",
    sectionId: "market-acquisition",
    order: 30,
    iconKey: "regulation",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
  },
  {
    id: "permits",
    label: "인허가 가능성",
    sectionId: "market-acquisition",
    parentId: "permit-reg",
    order: 10,
    path: "/permits",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/permits"],
  },
  {
    id: "regulations",
    label: "개발 규제",
    sectionId: "market-acquisition",
    parentId: "permit-reg",
    order: 20,
    path: "/regulations",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/regulations"],
  },
  {
    id: "design-studio",
    label: "AI 설계도면(CAD)",
    sectionId: "design-center",
    order: 10,
    path: "/design-studio",
    iconKey: "design",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/design"],
  },
  {
    id: "design-audit",
    label: "AI 설계분석",
    sectionId: "design-center",
    order: 20,
    path: "/design-audit",
    iconKey: "permit",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/design-audit"],
  },
  {
    id: "deliberation-review",
    label: "AI 심의분석 엔진",
    sectionId: "design-center",
    order: 30,
    path: "/deliberation-review",
    iconKey: "regulation",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/deliberation-review"],
  },
  {
    id: "bim-studio",
    label: "3D 모델·공사물량",
    sectionId: "design-center",
    order: 40,
    path: "/bim-studio",
    iconKey: "cost",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/bim"],
  },
  {
    id: "meeting-rooms",
    label: "프로젝트 회의방",
    sectionId: "design-center",
    order: 50,
    path: "/meeting-rooms",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/collaboration"],
  },
  {
    id: "design-refs",
    label: "표준설계 라이브러리",
    sectionId: "design-center",
    order: 60,
    path: "/settings/design-references",
    iconKey: "design",
    status: "live",
    scope: "admin",
    lifecyclePhase: "design",
    prefetch: false,
    apiDependencies: ["/design-references"],
  },
  // ── 분양 관리(구 "분양 현장 관리" 복원) — 분양 ERP는 코어 워크플로우(개발→분양)라 일반 노출.
  //    자산운영 4종(디지털트윈 /digital-twin·임대 /operations/lease·임차인 /tenant·시설 /maintenance)은
  //    구 IA 정책대로 네비에서 숨김(라우트·페이지 보존 — 준공 후 운영 단계 성숙 시 재등록).
  {
    id: "sales-mgmt",
    label: "분양 현장 관리",
    sectionId: "sales-management",
    order: 10,
    path: "/sales",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/sales"],
  },
  {
    id: "sales-sites",
    label: "내 분양 현장(현장앱)",
    sectionId: "sales-management",
    parentId: "sales-mgmt",
    order: 10,
    path: "/sales/sites",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/sales/sites"],
  },
  {
    id: "sales-projection",
    label: "분양관리요약(관리자)",
    sectionId: "sales-management",
    parentId: "sales-mgmt",
    order: 20,
    path: "/sales/projection",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/sales/projection"],
  },
  {
    id: "settings",
    label: "관리자 설정",
    sectionId: "admin",
    order: 10,
    path: "/settings",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/settings"],
  },
  {
    id: "users",
    label: "사용자 관리",
    sectionId: "admin",
    order: 20,
    path: "/settings/users",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/auth/users"],
  },
  {
    id: "billing",
    label: "과금 금액 설정",
    sectionId: "admin",
    order: 30,
    path: "/settings/billing",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/billing"],
  },
  {
    id: "lists",
    label: "편집 목록 관리",
    sectionId: "admin",
    order: 40,
    path: "/settings/lists",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/settings/lists"],
  },

  // ── 마이페이지(SaaS 계정 셀프서비스, 2026-07-17) — 코인·결제·사용내역·프로필·개인정보 ──
  //    스펙=docs/design/MYPAGE_SAAS_SPEC_2026-07-17.md. 계정 보안(/account)은 기존 검증
  //    화면을 재사용하고 여기서는 메뉴 진입만 제공한다.
  {
    id: "mypage",
    label: "내 계정 요약",
    sectionId: "my",
    order: 10,
    path: "/mypage",
    iconKey: "dashboard",
    status: "live",
    scope: "global",
    lifecyclePhase: "account",
    apiDependencies: ["/billing/balance", "/billing/ledger"],
  },
  {
    id: "mypage-coins",
    label: "코인 충전·결제내역",
    sectionId: "my",
    order: 20,
    path: "/mypage/coins",
    iconKey: "cost",
    status: "live",
    scope: "global",
    lifecyclePhase: "account",
    apiDependencies: ["/billing/packages", "/billing/orders", "/billing/ledger"],
  },
  {
    id: "mypage-usage",
    label: "AI 사용내역",
    sectionId: "my",
    order: 30,
    path: "/mypage/usage",
    iconKey: "roi",
    status: "live",
    scope: "global",
    lifecyclePhase: "account",
    apiDependencies: ["/billing/token-usage"],
  },
  {
    id: "mypage-profile",
    label: "프로필 관리",
    sectionId: "my",
    order: 40,
    path: "/mypage/profile",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "account",
    apiDependencies: ["/auth/me"],
  },
  {
    id: "mypage-privacy",
    label: "개인정보·약관",
    sectionId: "my",
    order: 50,
    path: "/mypage/privacy",
    iconKey: "regulation",
    status: "live",
    scope: "global",
    lifecyclePhase: "account",
    apiDependencies: ["/auth/me/consents"],
  },
  {
    id: "mypage-security",
    label: "계정 보안",
    sectionId: "my",
    order: 60,
    path: "/account",
    iconKey: "permit",
    status: "live",
    scope: "global",
    lifecyclePhase: "account",
    apiDependencies: ["/auth/me"],
  },
];

export function localizedHref(locale: string, path: RouteRegistryItem["path"]): string | undefined {
  if (!path) return undefined;
  if (path === "/") return `/${locale}`;
  return `/${locale}${path}`;
}

export function buildPrimaryRegistrySections(locale: string): RegistryNavSection[] {
  const childrenByParent = new Map<string, RegistryNavNode[]>();
  const topLevelBySection = new Map<PrimaryNavSectionId, RegistryNavNode[]>();

  const nodes = PRIMARY_ROUTE_REGISTRY.map<RegistryNavNode>((item) => ({
    ...item,
    href: localizedHref(locale, item.path),
  }));

  for (const node of nodes) {
    if (node.parentId) {
      const children = childrenByParent.get(node.parentId) ?? [];
      children.push(node);
      childrenByParent.set(node.parentId, children);
    } else {
      const sectionItems = topLevelBySection.get(node.sectionId) ?? [];
      sectionItems.push(node);
      topLevelBySection.set(node.sectionId, sectionItems);
    }
  }

  const attachChildren = (node: RegistryNavNode): RegistryNavNode => {
    const children = (childrenByParent.get(node.id) ?? [])
      .sort((a, b) => a.order - b.order)
      .map(attachChildren);
    return children.length ? { ...node, children } : node;
  };

  return [...PRIMARY_NAV_SECTIONS]
    .sort((a, b) => a.order - b.order)
    .map((section) => ({
      ...section,
      items: (topLevelBySection.get(section.id) ?? [])
        .sort((a, b) => a.order - b.order)
        .map(attachChildren),
    }));
}

export function visibleRouteRegistryItems(): RouteRegistryItem[] {
  return PRIMARY_ROUTE_REGISTRY.filter((item) => item.status !== "hidden" && Boolean(item.path));
}
